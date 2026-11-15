import os
import json
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
DUMP_PATH = os.path.join(DATA_DIR, 'fo_historical_dump.json')
CSV_5M_PATH = os.path.join(DATA_DIR, 'fo_60d_5m.csv')
PYBROKER_RES_PATH = os.path.join(DATA_DIR, 'pybroker_results.json')

# Cache backtest results if present
_CACHED_BACKTEST = None

def get_backtest_symbol_stats():
    global _CACHED_BACKTEST
    if _CACHED_BACKTEST is not None:
        return _CACHED_BACKTEST
    
    _CACHED_BACKTEST = {}
    if os.path.exists(PYBROKER_RES_PATH):
        try:
            with open(PYBROKER_RES_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _CACHED_BACKTEST = data.get('all_symbols') or data.get('raw_rules', {}).get('symbols', {})
        except Exception as e:
            logger.warning(f"Error loading pybroker_results.json: {e}")
    return _CACHED_BACKTEST


def get_5m_intraday_cache():
    """
    Extracts latest 5-minute opening range (H5, L5, RVOL) for available symbols from fo_60d_5m.csv.
    """
    if not os.path.exists(CSV_5M_PATH):
        return {}
    
    try:
        df_5m = pd.read_csv(CSV_5M_PATH)
        df_5m['datetime'] = pd.to_datetime(df_5m['date'])
        df_5m['day'] = df_5m['datetime'].dt.strftime('%Y-%m-%d')
        df_5m['time_str'] = df_5m['datetime'].dt.strftime('%H:%M')
        
        # Get latest trading day in 5m dataset
        latest_day = df_5m['day'].max()
        df_latest = df_5m[df_5m['day'] == latest_day]
        
        orb_map = {}
        for sym, g in df_latest.groupby('symbol'):
            g = g.sort_values('datetime').reset_index(drop=True)
            # First 2 bars = 09:15 and 09:20 opening range
            open_bars = g[g['time_str'].isin(['09:15', '09:20'])]
            if not open_bars.empty:
                h5 = float(open_bars['high'].max())
                l5 = float(open_bars['low'].min())
                open_vol = float(open_bars['volume'].sum())
            else:
                h5 = float(g.iloc[0]['high'])
                l5 = float(g.iloc[0]['low'])
                open_vol = float(g.iloc[0]['volume'])
                
            # Baseline rolling opening volume across previous days
            prev_days_open = df_5m[(df_5m['symbol'] == sym) & (df_5m['time_str'].isin(['09:15', '09:20'])) & (df_5m['day'] < latest_day)]
            if not prev_days_open.empty:
                avg_open_vol = prev_days_open.groupby('day')['volume'].sum().tail(14).mean()
                rvol = round(open_vol / avg_open_vol, 2) if avg_open_vol > 0 else 1.0
            else:
                rvol = 1.2
                
            latest_close = float(g.iloc[-1]['close'])
            orb_map[sym] = {
                'h5': round(h5, 2),
                'l5': round(l5, 2),
                'open_vol': int(open_vol),
                'rvol': rvol,
                'intraday_close': round(latest_close, 2)
            }
        return orb_map
    except Exception as e:
        logger.warning(f"Error reading 5m dataset: {e}")
        return {}


def scan_orb_universe(
    min_vol=100000, 
    min_atr=50.0, 
    use_atr_pct=False, 
    min_atr_pct=2.0, 
    min_rvol=1.0, 
    capital=1000000, 
    risk_pct=1.0
):
    """
    Runs the 5-Minute ORB Quantitative Screener across all 115+ F&O stocks.
    
    Parameters:
    - min_vol: Minimum 14-day average daily volume (shares), default 100,000
    - min_atr: Minimum 14-day ATR in points (user's raw rule), default 50.0
    - use_atr_pct: If True, uses normalized ATR% (Quant-Optimized) instead of absolute points
    - min_atr_pct: Minimum 14-day ATR as % of CMP, default 2.0%
    - min_rvol: Minimum Relative Volume in 5-minute open, default 1.0 (>= 1.2 is high momentum)
    - capital: Total trading account capital in INR, default ₹10,00,000
    - risk_pct: Maximum risk percentage per trade, default 1.0% (₹10,000 risk)
    """
    if not os.path.exists(DUMP_PATH):
        logger.error(f"Dump path not found: {DUMP_PATH}")
        return []

    try:
        with open(DUMP_PATH, 'r', encoding='utf-8') as f:
            dump_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read historical dump: {e}")
        return []

    backtest_stats = get_backtest_symbol_stats()
    intraday_5m_map = get_5m_intraday_cache()
    
    risk_budget = float(capital) * (float(risk_pct) / 100.0)
    results = []

    for symbol, candles in dump_data.items():
        if not candles or len(candles) < 20 or symbol in ['NIFTY 50', 'NIFTY BANK', 'NIFTY']:
            continue

        df = pd.DataFrame(candles, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna().reset_index(drop=True)

        if len(df) < 15:
            continue

        # 14-day True Range & ATR
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        vol = df['volume'].values

        tr1 = high - low
        tr2 = np.abs(high - np.roll(close, 1))
        tr3 = np.abs(low - np.roll(close, 1))
        tr = np.maximum(tr1, np.maximum(tr2, tr3))
        tr[0] = tr1[0]

        atr_series = pd.Series(tr).rolling(14, min_periods=1).mean()
        vol_series = pd.Series(vol).rolling(14, min_periods=1).mean()

        atr_14 = float(atr_series.iloc[-1])
        vol_14 = float(vol_series.iloc[-1])
        cmp_price = float(close[-1])
        prev_close = float(close[-2])
        day_change_pct = round(((cmp_price - prev_close) / prev_close) * 100.0, 2)

        atr_pct_14 = round((atr_14 / cmp_price) * 100.0, 2)
        turnover_cr = round((vol_14 * cmp_price) / 10_000_000.0, 2)

        # Filters evaluation
        qualifies_liquidity = bool(vol_14 >= min_vol)
        qualifies_atr50 = bool(atr_14 >= min_atr)
        qualifies_atrpct = bool(atr_pct_14 >= min_atr_pct)

        # Active filter matching
        if use_atr_pct:
            qualifies_volatility = qualifies_atrpct
        else:
            qualifies_volatility = qualifies_atr50

        # 5-minute Opening Range & RVOL
        if symbol in intraday_5m_map:
            intra = intraday_5m_map[symbol]
            h5 = intra['h5']
            l5 = intra['l5']
            rvol = intra['rvol']
        else:
            # Procedural intraday estimation from daily bar volatility
            curr_bar = df.iloc[-1]
            open_px = float(curr_bar['open'])
            half_range = max(0.5, 0.25 * atr_14)
            h5 = round(max(open_px + half_range, float(curr_bar['high']) - half_range), 2)
            l5 = round(min(open_px - half_range, float(curr_bar['low']) + half_range), 2)
            if h5 <= l5:
                h5 = round(open_px + half_range, 2)
                l5 = round(open_px - half_range, 2)
            
            vol_ratio = float(vol[-1] / vol_series.iloc[-1]) if vol_series.iloc[-1] > 0 else 1.0
            rvol = round(vol_ratio * 1.15, 2)

        qualifies_rvol = bool(rvol >= min_rvol)

        # Risk Management & Stop Loss calculations
        sl_points_10pct = max(0.05, round(0.10 * atr_14, 2))
        sl_points_35pct = round(0.35 * atr_14, 2)
        
        long_entry = h5
        long_sl = round(long_entry - sl_points_10pct, 2)
        short_entry = l5
        short_sl = round(short_entry + sl_points_10pct, 2)

        # Position Sizing based on 10% ATR Stop
        shares = max(1, int(risk_budget / sl_points_10pct))
        # Cap allocation to 20% of total capital
        max_shares = max(1, int((capital * 0.20) / cmp_price))
        shares = min(shares, max_shares)
        capital_req = round(shares * cmp_price, 2)

        # Targets & R:R (Target is EOD projection: average winner runs 1.5 - 2.0% or 1.5x ATR)
        eod_target_long = round(long_entry + (1.5 * atr_14), 2)
        eod_target_short = round(short_entry - (1.5 * atr_14), 2)
        reward_points = round(1.5 * atr_14, 2)
        rr_ratio = round(reward_points / sl_points_10pct, 1)

        # Signal Status detection
        if cmp_price > h5:
            status = 'LONG_TRIGGERED'
            status_display = '🚀 Long Breakout'
            status_color = '#38bdf8' # sky blue / cyan
            active_trade_dir = 'LONG'
            trade_entry = long_entry
            trade_sl = long_sl
            trade_target = eod_target_long
        elif cmp_price < l5:
            status = 'SHORT_BREAKDOWN'
            status_display = '🔻 Short Breakdown'
            status_color = '#f87171' # red
            active_trade_dir = 'SHORT'
            trade_entry = short_entry
            trade_sl = short_sl
            trade_target = eod_target_short
        elif cmp_price >= h5 * 0.996:
            status = 'TESTING_HIGH'
            status_display = '⚡ Testing 5M High'
            status_color = '#34d399' # emerald
            active_trade_dir = 'WATCH_LONG'
            trade_entry = long_entry
            trade_sl = long_sl
            trade_target = eod_target_long
        elif cmp_price <= l5 * 1.004:
            status = 'TESTING_LOW'
            status_display = '🛡️ Testing 5M Low'
            status_color = '#fbbf24' # amber
            active_trade_dir = 'WATCH_SHORT'
            trade_entry = short_entry
            trade_sl = short_sl
            trade_target = eod_target_short
        else:
            status = 'RANGE_BOUND'
            status_display = '⏳ In Range (Compressing)'
            status_color = '#94a3b8' # muted slate
            active_trade_dir = 'NEUTRAL'
            trade_entry = long_entry
            trade_sl = long_sl
            trade_target = eod_target_long

        # Backtest Intelligence tag
        bt = backtest_stats.get(symbol, {})
        has_backtest = bool(bt)

        results.append({
            'symbol': symbol,
            'close': round(cmp_price, 2),
            'day_change_pct': day_change_pct,
            'vol_14': int(vol_14),
            'turnover_cr': turnover_cr,
            'atr_14': round(atr_14, 2),
            'atr_pct_14': atr_pct_14,
            'h5': h5,
            'l5': l5,
            'rvol': rvol,
            'sl_points_10pct': sl_points_10pct,
            'sl_points_35pct': sl_points_35pct,
            'shares_sized': shares,
            'capital_required': capital_req,
            'risk_budget': risk_budget,
            'long_entry': long_entry,
            'long_sl': long_sl,
            'short_entry': short_entry,
            'short_sl': short_sl,
            'active_trade_dir': active_trade_dir,
            'trade_entry': trade_entry,
            'trade_sl': trade_sl,
            'trade_target': trade_target,
            'rr_ratio': rr_ratio,
            'status': status,
            'status_display': status_display,
            'status_color': status_color,
            'qualifies_liquidity': qualifies_liquidity,
            'qualifies_atr50': qualifies_atr50,
            'qualifies_atrpct': qualifies_atrpct,
            'qualifies_rvol': qualifies_rvol,
            'qualifies_strategy': (qualifies_liquidity and qualifies_volatility and qualifies_rvol),
            'has_backtest': has_backtest,
            'bt_trades': bt.get('trades', 0),
            'bt_win_rate': bt.get('win_rate', 0.0),
            'bt_pnl': bt.get('total_pnl', 0.0),
            'bt_avg_win': bt.get('avg_win', 0.0),
            'bt_avg_loss': bt.get('avg_loss', 0.0),
        })

    # Sort descending by qualifies_strategy, then rvol, then atr_pct_14
    results.sort(key=lambda x: (x['qualifies_strategy'], x['rvol'], x['atr_pct_14']), reverse=True)
    return results
