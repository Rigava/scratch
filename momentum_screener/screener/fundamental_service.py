import json
import time
import datetime
import logging
import pandas as pd
import numpy as np
from django.utils import timezone
from .models import StockFundamental
from .sector_taxonomy import get_stock_taxonomy

logger = logging.getLogger(__name__)

# Symbol Aliases for Indian stocks where Yahoo Finance ticker differs
SYMBOL_ALIASES = {
    "TATAMOTORS": ["TMPV.NS", "TMCV.NS", "TATAMOTORS.NS"],
    "M&M": ["M&M.NS"],
    "L&TFH": ["L&TFH.NS", "LTF.NS"],
    "BAJAJ-AUTO": ["BAJAJ-AUTO.NS"],
    "MCDOWELL-N": ["MCDOWELL-N.NS", "UNITDSPR.NS"],
}

INDEX_SYMBOLS = {"NIFTY 50", "NIFTY BANK", "NIFTY IT"}

def resolve_yahoo_symbol(ticker):
    """Returns candidate Yahoo Finance symbol(s) for a given NSE ticker."""
    clean = ticker.strip().upper()
    if clean in INDEX_SYMBOLS:
        return []
    if clean in SYMBOL_ALIASES:
        return SYMBOL_ALIASES[clean]
    return [f"{clean}.NS"]

def get_row_data(df, candidate_names):
    """Extracts first matching row from a financial statement DataFrame."""
    if df is None or df.empty:
        return None
    for name in candidate_names:
        if name in df.index:
            return df.loc[name]
    return None

def compute_technical_crossovers_from_candles(candles):
    """
    Computes MACD (12, 26, 9) and RSI (14, 9-SMA) crossover signals and their latest dates.
    candles can be a list of lists [date, open, high, low, close, volume] or list of dicts.
    """
    if not candles or len(candles) < 30:
        return {
            "macd_signal": "Neutral",
            "macd_crossover_date": "",
            "rsi_signal": "Neutral",
            "rsi_crossover_date": "",
            "latest_rsi": None,
            "latest_macd": None,
            "latest_signal": None,
        }

    dates = []
    closes = []
    for c in candles:
        if isinstance(c, (list, tuple)):
            dates.append(str(c[0]).split('T')[0])
            closes.append(float(c[4]))
        elif isinstance(c, dict):
            dates.append(str(c.get('date', '')).split('T')[0])
            closes.append(float(c.get('close', 0.0)))

    n = len(closes)
    if n < 30:
        return {
            "macd_signal": "Neutral",
            "macd_crossover_date": "",
            "rsi_signal": "Neutral",
            "rsi_crossover_date": "",
            "latest_rsi": None,
            "latest_macd": None,
            "latest_signal": None,
        }

    def _calc_ema(series, period):
        res = [None] * len(series)
        if len(series) < period:
            return res
        mult = 2.0 / (period + 1.0)
        res[period - 1] = sum(series[:period]) / period
        for i in range(period, len(series)):
            res[i] = (series[i] - res[i - 1]) * mult + res[i - 1]
        return res

    def _calc_sma(series, period):
        res = [None] * len(series)
        for i in range(period - 1, len(series)):
            sub = [v for v in series[i - period + 1 : i + 1] if v is not None]
            if len(sub) == period:
                res[i] = sum(sub) / period
        return res

    # 1. MACD
    ema12 = _calc_ema(closes, 12)
    ema26 = _calc_ema(closes, 26)
    macd_line = [None] * n
    for i in range(n):
        if ema12[i] is not None and ema26[i] is not None:
            macd_line[i] = ema12[i] - ema26[i]

    valid_indices = [i for i, v in enumerate(macd_line) if v is not None]
    valid_values = [macd_line[i] for i in valid_indices]
    sig_sub = _calc_ema(valid_values, 9)
    signal_line = [None] * n
    for idx_in_sub, orig_idx in enumerate(valid_indices):
        signal_line[orig_idx] = sig_sub[idx_in_sub]

    macd_signal_type = "Neutral"
    macd_crossover_date = ""
    for i in range(n - 1, 0, -1):
        if macd_line[i] is not None and signal_line[i] is not None and macd_line[i-1] is not None and signal_line[i-1] is not None:
            if macd_line[i-1] <= signal_line[i-1] and macd_line[i] > signal_line[i]:
                macd_signal_type = "Bullish Crossover"
                macd_crossover_date = dates[i]
                break
            elif macd_line[i-1] >= signal_line[i-1] and macd_line[i] < signal_line[i]:
                macd_signal_type = "Bearish Crossover"
                macd_crossover_date = dates[i]
                break

    if macd_signal_type == "Neutral" and macd_line[-1] is not None and signal_line[-1] is not None:
        macd_signal_type = "Bullish" if macd_line[-1] > signal_line[-1] else "Bearish"
        macd_crossover_date = dates[-1]

    # 2. RSI (14)
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains[i] = diff
        else:
            losses[i] = -diff
    rsi_vals = [None] * n
    if n > 14:
        avg_gain = sum(gains[1 : 15]) / 14.0
        avg_loss = sum(losses[1 : 15]) / 14.0
        rsi_vals[14] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
        for i in range(15, n):
            avg_gain = (avg_gain * 13.0 + gains[i]) / 14.0
            avg_loss = (avg_loss * 13.0 + losses[i]) / 14.0
            rsi_vals[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    rsi_sma9 = _calc_sma(rsi_vals, 9)

    rsi_signal_type = "Neutral"
    rsi_crossover_date = ""
    for i in range(n - 1, 0, -1):
        if rsi_vals[i] is not None and rsi_sma9[i] is not None and rsi_vals[i-1] is not None and rsi_sma9[i-1] is not None:
            if rsi_vals[i-1] <= rsi_sma9[i-1] and rsi_vals[i] > rsi_sma9[i]:
                rsi_signal_type = "Bullish Crossover"
                rsi_crossover_date = dates[i]
                break
            elif rsi_vals[i-1] >= rsi_sma9[i-1] and rsi_vals[i] < rsi_sma9[i]:
                rsi_signal_type = "Bearish Crossover"
                rsi_crossover_date = dates[i]
                break

    if rsi_signal_type == "Neutral" and rsi_vals[-1] is not None:
        rsi_signal_type = "Bullish" if rsi_vals[-1] >= 50 else "Bearish"
        rsi_crossover_date = dates[-1]

    return {
        "macd_signal": macd_signal_type,
        "macd_crossover_date": macd_crossover_date,
        "rsi_signal": rsi_signal_type,
        "rsi_crossover_date": rsi_crossover_date,
        "latest_rsi": round(rsi_vals[-1], 2) if rsi_vals[-1] is not None else None,
        "latest_macd": round(macd_line[-1], 2) if macd_line[-1] is not None else None,
        "latest_signal": round(signal_line[-1], 2) if signal_line[-1] is not None else None,
    }

def get_candles_for_ticker(ticker):
    """Loads historical daily candles from fo_historical_dump.json with yfinance fallback."""
    import os
    clean = ticker.strip().upper()
    dump_path = os.path.join(os.path.dirname(__file__), 'data', 'fo_historical_dump.json')
    if os.path.exists(dump_path):
        try:
            with open(dump_path, 'r', encoding='utf-8') as f:
                dump_data = json.load(f)
                if clean in dump_data and len(dump_data[clean]) >= 30:
                    return dump_data[clean]
        except Exception:
            pass
    # Fallback to yfinance if missing or insufficient
    try:
        import yfinance as yf
        syms = resolve_yahoo_symbol(clean)
        if syms:
            hist = yf.Ticker(syms[0]).history(period='2y')
            if not hist.empty:
                candles = []
                for idx, row in hist.iterrows():
                    candles.append([
                        idx.strftime('%Y-%m-%d'),
                        float(row['Open']),
                        float(row['High']),
                        float(row['Low']),
                        float(row['Close']),
                        int(row['Volume'])
                    ])
                return candles
    except Exception:
        pass
    return []

def fetch_and_calculate_fundamentals(ticker):
    """
    Fetches financial statements and quotes via yfinance for a single stock,
    computes 5-year historical trends, Piotroski F-Score, and Magic Score (0-100).
    """
    import yfinance as yf

    symbols = resolve_yahoo_symbol(ticker)
    if not symbols:
        return {
            "error": f"{ticker} is an index and does not have corporate financial statements.",
            "is_index": True
        }

    yf_ticker = None
    inc = None
    bs = None
    cf = None
    info = {}
    matched_sym = None

    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            temp_inc = t.financials
            temp_bs = t.balance_sheet
            if temp_inc is not None and not temp_inc.empty and temp_bs is not None and not temp_bs.empty:
                yf_ticker = t
                inc = temp_inc
                bs = temp_bs
                cf = t.cashflow
                info = t.info or {}
                matched_sym = sym
                break
        except Exception as e:
            logger.warning("Error trying symbol %s for %s: %s", sym, ticker, e)

    if inc is None or bs is None or inc.empty or bs.empty:
        return {
            "error": f"Financial statements not available for {ticker} on Yahoo Finance.",
            "ticker": ticker
        }

    # Extract Income Statement rows
    rev_s = get_row_data(inc, ['Total Revenue', 'Operating Revenue', 'Gross Revenue'])
    net_inc_s = get_row_data(inc, [
        'Net Income Common Stockholders', 
        'Net Income', 
        'Net Income From Continuing Operation Net Minority Interest',
        'Net Income Continuous Operations'
    ])
    ebit_s = get_row_data(inc, ['EBIT', 'Operating Income', 'Pretax Income'])
    interest_s = get_row_data(inc, ['Interest Expense', 'Interest Expense Non Operating'])

    # Extract Balance Sheet rows
    total_assets_s = get_row_data(bs, ['Total Assets'])
    cur_assets_s = get_row_data(bs, ['Current Assets'])
    cur_liab_s = get_row_data(bs, ['Current Liabilities'])
    total_debt_s = get_row_data(bs, ['Total Debt'])
    long_debt_s = get_row_data(bs, ['Long Term Debt', 'Long Term Debt And Capital Lease Obligation', 'Total Non Current Liabilities Net Minority Interest'])
    equity_s = get_row_data(bs, ['Stockholders Equity', 'Common Stock Equity', 'Total Equity Gross Minority Interest'])
    shares_s = get_row_data(bs, ['Ordinary Shares Number', 'Share Issued'])

    # Extract Cash Flow rows
    cfo_s = get_row_data(cf, ['Operating Cash Flow', 'Cash Flows From Used In Operating Activities']) if cf is not None else None

    # Determine reporting periods (up to 5 years)
    cols = list(inc.columns)[:5]
    years = [c.strftime('%Y') for c in cols]

    # Current metrics from info
    raw_mcap = info.get('marketCap') or 0
    current_mcap_cr = round(raw_mcap / 1e7, 1) if raw_mcap else None
    company_name = info.get('shortName') or info.get('longName') or f"{ticker} Ltd."

    # Build 5-Year Historical Trends
    yearly_trends = []
    for i, col in enumerate(cols):
        yr = years[i]
        ni = float(net_inc_s[col]) if net_inc_s is not None and col in net_inc_s.index and pd.notnull(net_inc_s[col]) else None
        eb = float(ebit_s[col]) if ebit_s is not None and col in ebit_s.index and pd.notnull(ebit_s[col]) else None
        inte = float(interest_s[col]) if interest_s is not None and col in interest_s.index and pd.notnull(interest_s[col]) else None

        d = float(total_debt_s[col]) if total_debt_s is not None and col in total_debt_s.index and pd.notnull(total_debt_s[col]) else None
        eq = float(equity_s[col]) if equity_s is not None and col in equity_s.index and pd.notnull(equity_s[col]) else None
        ta = float(total_assets_s[col]) if total_assets_s is not None and col in total_assets_s.index and pd.notnull(total_assets_s[col]) else None
        cl = float(cur_liab_s[col]) if cur_liab_s is not None and col in cur_liab_s.index and pd.notnull(cur_liab_s[col]) else None
        sh = float(shares_s[col]) if shares_s is not None and col in shares_s.index and pd.notnull(shares_s[col]) else None

        # Debt to Equity
        de = None
        if d is not None and eq and eq > 0:
            de = round(d / eq, 2)
        elif d == 0 and eq and eq > 0:
            de = 0.0

        # Capital Employed & ROCE = (EBIT / Capital Employed) * 100
        cap_emp = None
        if ta is not None and cl is not None:
            cap_emp = ta - cl
        elif d is not None and eq is not None:
            cap_emp = d + eq

        roce = None
        if eb is not None and cap_emp and cap_emp > 0:
            roce = round((eb / cap_emp) * 100, 2)

        # Interest Coverage = EBIT / Interest Expense
        ic = None
        if eb is not None:
            if inte and inte > 0:
                ic = round(eb / inte, 2)
            else:
                ic = 99.0 # Effectively no interest burden

        # Net Margin (%) = (Net Income / Total Revenue) * 100
        net_margin = None
        rev = float(rev_s[col]) if rev_s is not None and col in rev_s.index and pd.notnull(rev_s[col]) else None
        if ni is not None and rev and rev > 0:
            net_margin = round((ni / rev) * 100, 2)

        # Estimated Historical Market Cap (₹ Cr)
        # Uses latest Mcap scaled by book value or share count if historical price is unavailable
        hist_mcap_cr = None
        if i == 0 and current_mcap_cr:
            hist_mcap_cr = current_mcap_cr
        elif current_mcap_cr and len(cols) > 1:
            # Proportionate estimate from stockholders equity / profit ratio
            curr_eq = float(equity_s[cols[0]]) if equity_s is not None and cols[0] in equity_s.index and pd.notnull(equity_s[cols[0]]) else 1
            hist_eq = eq or curr_eq
            if curr_eq > 0:
                hist_mcap_cr = round(current_mcap_cr * (hist_eq / curr_eq), 1)

        yearly_trends.append({
            "year": yr,
            "market_cap_cr": hist_mcap_cr or current_mcap_cr,
            "net_profit_cr": round(ni / 1e7, 1) if ni is not None else None,
            "ebit_cr": round(eb / 1e7, 1) if eb is not None else None,
            "roce_pct": roce,
            "debt_equity": de,
            "net_margin_pct": net_margin,
            "interest_coverage": ic,
        })

    # PEG Ratio with Fallback and Transparency Note
    raw_peg = info.get('pegRatio')
    peg_ratio = None
    peg_is_fallback = False
    peg_note = ""

    if raw_peg is not None:
        try:
            peg_val = float(raw_peg)
            if peg_val > 0:
                peg_ratio = round(peg_val, 2)
                peg_note = "Sourced from Yahoo Finance 5-Year Forward Analyst Consensus"
        except (ValueError, TypeError):
            peg_ratio = None

    if peg_ratio is None:
        pe = info.get('trailingPE') or info.get('forwardPE')
        eg = info.get('earningsGrowth') or info.get('earningsQuarterlyGrowth')
        
        # Fallback 1: Trailing P/E divided by Reported YoY Earnings Growth (%)
        if pe and eg and eg > 0.02:
            peg_ratio = round(pe / (eg * 100), 2)
            peg_is_fallback = True
            peg_note = f"Calculated: Trailing P/E ({pe:.1f}) / Reported YoY Earnings Growth ({eg*100:.1f}%)"
        
        # Fallback 2: Trailing P/E divided by 2-Year Net Profit CAGR (%)
        elif pe and len(yearly_trends) >= 3 and yearly_trends[0]["net_profit_cr"] and yearly_trends[2]["net_profit_cr"] and yearly_trends[2]["net_profit_cr"] > 0:
            p0 = yearly_trends[0]["net_profit_cr"]
            p2 = yearly_trends[2]["net_profit_cr"]
            if p0 > p2:
                cagr2y = ((p0 / p2) ** 0.5 - 1) * 100
                if cagr2y > 2:
                    peg_ratio = round(pe / cagr2y, 2)
                    peg_is_fallback = True
                    peg_note = f"Calculated: Trailing P/E ({pe:.1f}) / 2-Year Net Profit CAGR ({cagr2y:.1f}%)"
        
        if peg_ratio is None:
            if pe and eg and eg <= 0:
                peg_note = f"N/A: Stagnant/Negative Earnings Growth ({eg*100:.1f}%) with P/E ({pe:.1f})"
            elif not pe:
                peg_note = "N/A: P/E unavailable (Net Loss / Nil Earnings)"
            else:
                peg_note = "N/A: Insufficient forward or historical growth data"

    # --- Compute Piotroski F-Score (9 points) ---
    piotroski = 0
    piotroski_breakdown = {}
    if len(cols) >= 2:
        c0, c1 = cols[0], cols[1]

        # 1. Positive Net Income
        ni0 = float(net_inc_s[c0]) if net_inc_s is not None and c0 in net_inc_s.index and pd.notnull(net_inc_s[c0]) else 0
        p1 = 1 if ni0 > 0 else 0
        piotroski += p1
        piotroski_breakdown["positive_net_income"] = p1

        # 2. Positive Return on Assets (ROA)
        ta0 = float(total_assets_s[c0]) if total_assets_s is not None and c0 in total_assets_s.index and pd.notnull(total_assets_s[c0]) else 1
        p2 = 1 if (ni0 / ta0) > 0 else 0
        piotroski += p2
        piotroski_breakdown["positive_roa"] = p2

        # 3. Positive Operating Cash Flow
        cfo0 = float(cfo_s[c0]) if cfo_s is not None and c0 in cfo_s.index and pd.notnull(cfo_s[c0]) else (ni0 * 1.1)
        p3 = 1 if cfo0 > 0 else 0
        piotroski += p3
        piotroski_breakdown["positive_cfo"] = p3

        # 4. Cash Flow from Operations > Net Income (Quality of earnings)
        p4 = 1 if cfo0 > ni0 else 0
        piotroski += p4
        piotroski_breakdown["cfo_gt_net_income"] = p4

        # 5. Lower Long-Term Debt YoY
        ld0 = float(long_debt_s[c0]) if long_debt_s is not None and c0 in long_debt_s.index and pd.notnull(long_debt_s[c0]) else 0
        ld1 = float(long_debt_s[c1]) if long_debt_s is not None and c1 in long_debt_s.index and pd.notnull(long_debt_s[c1]) else 0
        p5 = 1 if ld0 <= ld1 else 0
        piotroski += p5
        piotroski_breakdown["lower_long_debt"] = p5

        # 6. Higher Current Ratio YoY
        ca0 = float(cur_assets_s[c0]) if cur_assets_s is not None and c0 in cur_assets_s.index and pd.notnull(cur_assets_s[c0]) else 1
        cl0 = float(cur_liab_s[c0]) if cur_liab_s is not None and c0 in cur_liab_s.index and pd.notnull(cur_liab_s[c0]) else 1
        ca1 = float(cur_assets_s[c1]) if cur_assets_s is not None and c1 in cur_assets_s.index and pd.notnull(cur_assets_s[c1]) else 1
        cl1 = float(cur_liab_s[c1]) if cur_liab_s is not None and c1 in cur_liab_s.index and pd.notnull(cur_liab_s[c1]) else 1
        cr0 = ca0 / cl0 if cl0 > 0 else 1
        cr1 = ca1 / cl1 if cl1 > 0 else 1
        p6 = 1 if cr0 >= cr1 else 0
        piotroski += p6
        piotroski_breakdown["higher_current_ratio"] = p6

        # 7. No Share Dilution (Shares <= prior year)
        sh0 = float(shares_s[c0]) if shares_s is not None and c0 in shares_s.index and pd.notnull(shares_s[c0]) else 1
        sh1 = float(shares_s[c1]) if shares_s is not None and c1 in shares_s.index and pd.notnull(shares_s[c1]) else 1
        p7 = 1 if sh0 <= sh1 * 1.01 else 0
        piotroski += p7
        piotroski_breakdown["no_dilution"] = p7

        # 8. Higher Gross / Operating Margin YoY
        rev0 = float(rev_s[c0]) if rev_s is not None and c0 in rev_s.index and pd.notnull(rev_s[c0]) else 1
        rev1 = float(rev_s[c1]) if rev_s is not None and c1 in rev_s.index and pd.notnull(rev_s[c1]) else 1
        gm0 = (float(ebit_s[c0]) if ebit_s is not None and c0 in ebit_s.index else 0) / rev0 if rev0 > 0 else 0
        gm1 = (float(ebit_s[c1]) if ebit_s is not None and c1 in ebit_s.index else 0) / rev1 if rev1 > 0 else 0
        p8 = 1 if gm0 >= gm1 else 0
        piotroski += p8
        piotroski_breakdown["higher_margin"] = p8

        # 9. Higher Asset Turnover YoY
        at0 = rev0 / ta0 if ta0 > 0 else 0
        ta1 = float(total_assets_s[c1]) if total_assets_s is not None and c1 in total_assets_s.index and pd.notnull(total_assets_s[c1]) else 1
        at1 = rev1 / ta1 if ta1 > 0 else 0
        p9 = 1 if at0 >= at1 else 0
        piotroski += p9
        piotroski_breakdown["higher_asset_turnover"] = p9

    # --- Compute Magic Score (0 - 100) ---
    curr_roce = 0
    curr_de = 0.5
    curr_ic = 5.0
    curr_net_margin = None
    latest_ebit = None
    latest_np = None

    for tr in yearly_trends:
        if curr_roce == 0 and tr.get("roce_pct") is not None:
            curr_roce = tr["roce_pct"]
        if curr_de == 0.5 and tr.get("debt_equity") is not None:
            curr_de = tr["debt_equity"]
        if curr_ic == 5.0 and tr.get("interest_coverage") is not None:
            curr_ic = tr["interest_coverage"]
        if curr_net_margin is None and tr.get("net_margin_pct") is not None:
            curr_net_margin = tr["net_margin_pct"]
        if latest_ebit is None and tr.get("ebit_cr") is not None:
            latest_ebit = tr["ebit_cr"]
        if latest_np is None and tr.get("net_profit_cr") is not None:
            latest_np = tr["net_profit_cr"]

    # 1. ROCE Score (max 20)
    if curr_roce >= 25: roce_score = 20
    elif curr_roce >= 18: roce_score = 16
    elif curr_roce >= 12: roce_score = 12
    elif curr_roce >= 7: roce_score = 6
    else: roce_score = 2

    # 2. Debt / Equity Score (max 20)
    if curr_de <= 0.10: de_score = 20
    elif curr_de <= 0.40: de_score = 16
    elif curr_de <= 0.80: de_score = 12
    elif curr_de <= 1.20: de_score = 6
    else: de_score = 2

    # 3. Interest Coverage Score (max 15)
    if curr_ic >= 10: ic_score = 15
    elif curr_ic >= 5: ic_score = 12
    elif curr_ic >= 3: ic_score = 8
    elif curr_ic >= 1.5: ic_score = 4
    else: ic_score = 0

    # 4. Piotroski F-Score (max 20, scaled from 9)
    pio_score = round((piotroski / 9.0) * 20, 1)

    # 5. PEG Ratio Score (max 15)
    if peg_ratio and peg_ratio > 0:
        if peg_ratio <= 1.0: peg_score = 15
        elif peg_ratio <= 1.5: peg_score = 12
        elif peg_ratio <= 2.2: peg_score = 8
        elif peg_ratio <= 3.0: peg_score = 4
        else: peg_score = 2
    else:
        peg_score = 8 # Reasonable neutral baseline if PEG is omitted

    # 6. Profit Growth Score (max 10)
    if len(yearly_trends) >= 3 and yearly_trends[0]["net_profit_cr"] and yearly_trends[2]["net_profit_cr"] and yearly_trends[2]["net_profit_cr"] > 0:
        p0 = yearly_trends[0]["net_profit_cr"]
        p2 = yearly_trends[2]["net_profit_cr"]
        cagr2y = ((p0 / p2) ** 0.5 - 1) * 100
        if cagr2y >= 20: growth_score = 10
        elif cagr2y >= 10: growth_score = 7
        elif cagr2y > 0: growth_score = 5
        else: growth_score = 1
    else:
        growth_score = 5

    magic_score = round(roce_score + de_score + ic_score + pio_score + peg_score + growth_score)
    magic_score = max(0, min(100, magic_score))

    score_components = {
        "roce": roce_score,
        "debt_equity": de_score,
        "interest_coverage": ic_score,
        "piotroski": pio_score,
        "peg": peg_score,
        "growth": growth_score
    }

    tax = get_stock_taxonomy(ticker)

    result = {
        "ticker": ticker,
        "company_name": company_name,
        "sector": tax.get("sector", "Diversified"),
        "industry": tax.get("industry", "Diversified Commercial"),
        "market_cap_cr": current_mcap_cr,
        "magic_score": magic_score,
        "piotroski_score": piotroski,
        "peg_ratio": peg_ratio,
        "peg_is_fallback": peg_is_fallback,
        "peg_note": peg_note,
        "roce_pct": curr_roce,
        "debt_equity": curr_de,
        "net_margin_pct": curr_net_margin,
        "ebit_cr": latest_ebit,
        "net_profit_cr": latest_np,
        "interest_coverage": curr_ic,
        "yearly_trends": yearly_trends,
        "score_components": score_components,
        "piotroski_breakdown": piotroski_breakdown,
        "last_updated": timezone.now().isoformat()
    }
    return result


def compute_sector_peers_and_ranks(clean_ticker, sector):
    """
    Computes peer comparison metrics, sector medians, and active stock rankings
    for all corporate stocks sharing the same sector in the TradeKriya universe.
    """
    if not sector:
        return {"peers": [], "sector_medians": {}, "sector_ranks": {}}

    peer_records = StockFundamental.objects.filter(sector=sector).exclude(ticker__in=INDEX_SYMBOLS)
    peers = []
    for p in peer_records:
        peers.append({
            "ticker": p.ticker,
            "company_name": p.company_name,
            "sector": p.sector,
            "industry": p.industry,
            "market_cap_cr": p.market_cap_cr,
            "magic_score": p.magic_score,
            "roce_pct": p.roce_pct,
            "debt_equity": p.debt_equity,
            "net_margin_pct": p.net_margin_pct,
            "peg_ratio": p.peg_ratio,
            "peg_is_fallback": p.peg_is_fallback,
            "is_current": (p.ticker == clean_ticker)
        })

    # Sort peers by magic_score descending (None values last)
    peers.sort(key=lambda x: (x["magic_score"] is not None, x["magic_score"] if x["magic_score"] is not None else -999), reverse=True)

    def calc_median(val_list):
        valid = [float(v) for v in val_list if v is not None]
        if not valid:
            return None
        return round(float(np.median(valid)), 2)

    sector_medians = {
        "magic_score": calc_median([p["magic_score"] for p in peers]),
        "roce_pct": calc_median([p["roce_pct"] for p in peers]),
        "debt_equity": calc_median([p["debt_equity"] for p in peers]),
        "net_margin_pct": calc_median([p["net_margin_pct"] for p in peers]),
        "peg_ratio": calc_median([p["peg_ratio"] for p in peers]),
        "total_peers": len(peers)
    }

    # Relative ranks within the sector
    magic_valid = [p for p in peers if p["magic_score"] is not None]
    magic_valid.sort(key=lambda x: x["magic_score"], reverse=True)
    magic_rank = None
    for idx, p in enumerate(magic_valid):
        if p["ticker"] == clean_ticker:
            magic_rank = idx + 1
            break

    roce_valid = [p for p in peers if p["roce_pct"] is not None]
    roce_valid.sort(key=lambda x: x["roce_pct"], reverse=True)
    roce_rank = None
    for idx, p in enumerate(roce_valid):
        if p["ticker"] == clean_ticker:
            roce_rank = idx + 1
            break

    de_valid = [p for p in peers if p["debt_equity"] is not None]
    de_valid.sort(key=lambda x: x["debt_equity"])  # lower debt is rank 1
    de_rank = None
    for idx, p in enumerate(de_valid):
        if p["ticker"] == clean_ticker:
            de_rank = idx + 1
            break

    sector_ranks = {
        "magic_score_rank": magic_rank,
        "roce_rank": roce_rank,
        "debt_equity_rank": de_rank,
        "total_peers": len(peers)
    }

    return {
        "peers": peers,
        "sector_medians": sector_medians,
        "sector_ranks": sector_ranks
    }


def get_or_fetch_stock_fundamentals(ticker, force_refresh=False, max_age_days=30):
    """
    Retrieves fundamentals from database cache. If missing, stale (> max_age_days),
    or force_refresh is True, fetches fresh data from Yahoo Finance and updates cache.
    Includes sector, granular sub-industry, and peer comparison data.
    """
    clean_ticker = ticker.strip().upper()
    
    # Skip indices
    if clean_ticker in INDEX_SYMBOLS:
        return {
            "ticker": clean_ticker,
            "company_name": f"{clean_ticker} Index",
            "sector": "Index Benchmark",
            "industry": "Index Benchmark",
            "is_index": True,
            "magic_score": None,
            "message": "Market Index (No corporate balance sheet)"
        }

    tax = get_stock_taxonomy(clean_ticker)

    # Check database cache
    cached = StockFundamental.objects.filter(ticker=clean_ticker).first()
    # Cache is considered incomplete if it was stored prior to net_margin_pct or peg_note support
    is_incomplete_cache = cached and (cached.net_margin_pct is None or (cached.peg_ratio is None and not cached.peg_note))
    
    if cached and not force_refresh and not is_incomplete_cache:
        # Ensure sector and industry are populated on cached row
        if not cached.sector or not cached.industry:
            cached.sector = cached.sector or tax.get("sector", "Diversified")
            cached.industry = cached.industry or tax.get("industry", "Diversified Commercial")
            cached.save(update_fields=["sector", "industry"])

        age = timezone.now() - cached.last_updated
        if age.days < max_age_days:
            try:
                yearly_trends = json.loads(cached.yearly_trends_json)
                breakdown = json.loads(cached.score_breakdown_json)
                peer_info = compute_sector_peers_and_ranks(clean_ticker, cached.sector)
                return {
                    "ticker": cached.ticker,
                    "company_name": cached.company_name,
                    "sector": cached.sector,
                    "industry": cached.industry,
                    "market_cap_cr": cached.market_cap_cr,
                    "magic_score": cached.magic_score,
                    "piotroski_score": cached.piotroski_score,
                    "peg_ratio": cached.peg_ratio,
                    "peg_is_fallback": cached.peg_is_fallback,
                    "peg_note": cached.peg_note,
                    "roce_pct": cached.roce_pct,
                    "debt_equity": cached.debt_equity,
                    "net_margin_pct": cached.net_margin_pct,
                    "ebit_cr": cached.ebit_cr,
                    "net_profit_cr": cached.net_profit_cr,
                    "interest_coverage": cached.interest_coverage,
                    "yearly_trends": yearly_trends,
                    "score_components": breakdown,
                    "macd_signal": cached.macd_signal or "Neutral",
                    "macd_crossover_date": cached.macd_crossover_date or "",
                    "rsi_signal": cached.rsi_signal or "Neutral",
                    "rsi_crossover_date": cached.rsi_crossover_date or "",
                    "peers": peer_info["peers"],
                    "sector_medians": peer_info["sector_medians"],
                    "sector_ranks": peer_info["sector_ranks"],
                    "last_updated": cached.last_updated.isoformat(),
                    "cached": True
                }
            except Exception as e:
                logger.warning("Error parsing cached fundamental json for %s: %s", clean_ticker, e)

    # Fetch fresh data
    data = fetch_and_calculate_fundamentals(clean_ticker)
    if "error" in data:
        # If fetch fails but we had older cache, return older cache with warning
        if cached:
            sector = cached.sector or tax.get("sector", "Diversified")
            industry = cached.industry or tax.get("industry", "Diversified Commercial")
            peer_info = compute_sector_peers_and_ranks(clean_ticker, sector)
            return {
                "ticker": cached.ticker,
                "company_name": cached.company_name,
                "sector": sector,
                "industry": industry,
                "market_cap_cr": cached.market_cap_cr,
                "magic_score": cached.magic_score,
                "piotroski_score": cached.piotroski_score,
                "peg_ratio": cached.peg_ratio,
                "peg_is_fallback": cached.peg_is_fallback,
                "peg_note": cached.peg_note,
                "roce_pct": cached.roce_pct,
                "debt_equity": cached.debt_equity,
                "net_margin_pct": cached.net_margin_pct,
                "ebit_cr": cached.ebit_cr,
                "net_profit_cr": cached.net_profit_cr,
                "interest_coverage": cached.interest_coverage,
                "yearly_trends": json.loads(cached.yearly_trends_json),
                "score_components": json.loads(cached.score_breakdown_json),
                "macd_signal": cached.macd_signal or "Neutral",
                "macd_crossover_date": cached.macd_crossover_date or "",
                "rsi_signal": cached.rsi_signal or "Neutral",
                "rsi_crossover_date": cached.rsi_crossover_date or "",
                "peers": peer_info["peers"],
                "sector_medians": peer_info["sector_medians"],
                "sector_ranks": peer_info["sector_ranks"],
                "last_updated": cached.last_updated.isoformat(),
                "cached": True,
                "warning": data["error"]
            }
        return data

    sector_val = data.get("sector") or tax.get("sector", "Diversified")
    industry_val = data.get("industry") or tax.get("industry", "Diversified Commercial")

    # Compute technical crossover signals from historical candles
    stock_candles = get_candles_for_ticker(clean_ticker)
    tech_signals = compute_technical_crossovers_from_candles(stock_candles)

    # Save to database
    StockFundamental.objects.update_or_create(
        ticker=clean_ticker,
        defaults={
            "company_name": data.get("company_name", ""),
            "sector": sector_val,
            "industry": industry_val,
            "market_cap_cr": data.get("market_cap_cr"),
            "magic_score": data.get("magic_score", 0),
            "piotroski_score": data.get("piotroski_score", 0),
            "peg_ratio": data.get("peg_ratio"),
            "peg_is_fallback": data.get("peg_is_fallback", False),
            "peg_note": data.get("peg_note", ""),
            "roce_pct": data.get("roce_pct"),
            "debt_equity": data.get("debt_equity"),
            "net_margin_pct": data.get("net_margin_pct"),
            "ebit_cr": data.get("ebit_cr"),
            "net_profit_cr": data.get("net_profit_cr"),
            "interest_coverage": data.get("interest_coverage"),
            "macd_signal": tech_signals.get("macd_signal", "Neutral"),
            "macd_crossover_date": tech_signals.get("macd_crossover_date", ""),
            "rsi_signal": tech_signals.get("rsi_signal", "Neutral"),
            "rsi_crossover_date": tech_signals.get("rsi_crossover_date", ""),
            "score_breakdown_json": json.dumps(data.get("score_components", {})),
            "yearly_trends_json": json.dumps(data.get("yearly_trends", [])),
        }
    )

    peer_info = compute_sector_peers_and_ranks(clean_ticker, sector_val)
    data["sector"] = sector_val
    data["industry"] = industry_val
    data["macd_signal"] = tech_signals.get("macd_signal", "Neutral")
    data["macd_crossover_date"] = tech_signals.get("macd_crossover_date", "")
    data["rsi_signal"] = tech_signals.get("rsi_signal", "Neutral")
    data["rsi_crossover_date"] = tech_signals.get("rsi_crossover_date", "")
    data["peers"] = peer_info["peers"]
    data["sector_medians"] = peer_info["sector_medians"]
    data["sector_ranks"] = peer_info["sector_ranks"]
    data["cached"] = False
    return data


def scan_fundamentals_batch(tickers, force_refresh=False, delay_seconds=1.2):
    """
    Scans a batch of tickers sequentially with a polite delay between calls
    to prevent Yahoo Finance rate-limiting (HTTP 429).
    """
    results = []
    for i, sym in enumerate(tickers):
        clean = sym.strip().upper()
        if clean in INDEX_SYMBOLS:
            results.append({
                "ticker": clean,
                "skipped": True,
                "reason": "Index symbol"
            })
            continue

        try:
            res = get_or_fetch_stock_fundamentals(clean, force_refresh=force_refresh)
            results.append(res)
        except Exception as e:
            logger.error("Error scanning fundamentals for %s: %s", clean, e)
            results.append({
                "ticker": clean,
                "error": str(e)
            })

        # Polite delay to prevent 429 blocks unless it was purely served from cache
        if i < len(tickers) - 1:
            time.sleep(delay_seconds)

    return results
