import json
import time
import datetime
import logging
import pandas as pd
import numpy as np
from django.utils import timezone
from .models import StockFundamental

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

    result = {
        "ticker": ticker,
        "company_name": company_name,
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


def get_or_fetch_stock_fundamentals(ticker, force_refresh=False, max_age_days=30):
    """
    Retrieves fundamentals from database cache. If missing, stale (> max_age_days),
    or force_refresh is True, fetches fresh data from Yahoo Finance and updates cache.
    """
    clean_ticker = ticker.strip().upper()
    
    # Skip indices
    if clean_ticker in INDEX_SYMBOLS:
        return {
            "ticker": clean_ticker,
            "company_name": f"{clean_ticker} Index",
            "is_index": True,
            "magic_score": None,
            "message": "Market Index (No corporate balance sheet)"
        }

    # Check database cache
    cached = StockFundamental.objects.filter(ticker=clean_ticker).first()
    # Cache is considered incomplete if it was stored prior to net_margin_pct or peg_note support
    is_incomplete_cache = cached and (cached.net_margin_pct is None or (cached.peg_ratio is None and not cached.peg_note))
    if cached and not force_refresh and not is_incomplete_cache:
        age = timezone.now() - cached.last_updated
        if age.days < max_age_days:
            try:
                yearly_trends = json.loads(cached.yearly_trends_json)
                breakdown = json.loads(cached.score_breakdown_json)
                return {
                    "ticker": cached.ticker,
                    "company_name": cached.company_name,
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
            return {
                "ticker": cached.ticker,
                "company_name": cached.company_name,
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
                "last_updated": cached.last_updated.isoformat(),
                "cached": True,
                "warning": data["error"]
            }
        return data

    # Save to database
    StockFundamental.objects.update_or_create(
        ticker=clean_ticker,
        defaults={
            "company_name": data.get("company_name", ""),
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
            "score_breakdown_json": json.dumps(data.get("score_components", {})),
            "yearly_trends_json": json.dumps(data.get("yearly_trends", [])),
        }
    )

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
