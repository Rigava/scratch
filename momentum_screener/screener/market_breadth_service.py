import os
import json
import pandas as pd
import numpy as np

# Cache dictionary to avoid recomputing on every request
_BREADTH_CACHE = {}

NIFTY50_CONSTITUENTS = [
    'ADANIENT', 'ADANIPORTS', 'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK', 
    'BAJAJ-AUTO', 'BAJAJFINSV', 'BAJFINANCE', 'BHARTIARTL', 'BPCL', 
    'BRITANNIA', 'CIPLA', 'COALINDIA', 'DIVISLAB', 'DRREDDY', 
    'EICHERMOT', 'GRASIM', 'HCLTECH', 'HDFCBANK', 'HDFCLIFE', 
    'HEROMOTOCO', 'HINDALCO', 'HINDUNILVR', 'ICICIBANK', 'INDUSINDBK', 
    'INFY', 'ITC', 'JSWSTEEL', 'KOTAKBANK', 'LT', 
    'LTIM', 'M&M', 'MARUTI', 'NESTLEIND', 'NTPC', 
    'ONGC', 'POWERGRID', 'RELIANCE', 'SBILIFE', 'SBIN', 
    'SUNPHARMA', 'TATACONSUM', 'TATAMOTORS', 'TATASTEEL', 'TCS', 
    'TECHM', 'TITAN', 'ULTRACEMCO', 'WIPRO', 'TRENT'
]

def parse_df(records):
    df = pd.DataFrame(records, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = pd.to_datetime(df['date'].astype(str).str.slice(0, 10))
    df = df.sort_values('date').reset_index(drop=True)
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def compute_universe_breadth(universe_filter='all'):
    """
    Computes daily market breadth metrics over all available history for the specified universe.
    universe_filter: 'all' (115 F&O stocks) or 'nifty50' (Nifty 50 constituents)
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dump_path = os.path.join(base_dir, 'data', 'fo_historical_dump.json')
    if not os.path.exists(dump_path):
        return None

    with open(dump_path, 'r', encoding='utf-8') as f:
        raw_dump = json.load(f)

    close_dict = {}
    vol_dict = {}
    high_dict = {}
    low_dict = {}

    for sym, records in raw_dump.items():
        if len(records) < 70 or 'NIFTY' in sym:
            continue
        if universe_filter == 'nifty50' and sym not in NIFTY50_CONSTITUENTS:
            continue
            
        df = parse_df(records).set_index('date')
        close_dict[sym] = df['close']
        vol_dict[sym] = df['volume']
        high_dict[sym] = df['high']
        low_dict[sym] = df['low']

    df_closes = pd.DataFrame(close_dict).sort_index()
    df_vols = pd.DataFrame(vol_dict).sort_index()
    df_highs = pd.DataFrame(high_dict).sort_index()
    df_lows = pd.DataFrame(low_dict).sort_index()

    total_active = df_closes.notna().sum(axis=1)

    # 1. Multi-Horizon Moving Average Breadth
    sma200_panel = df_closes.rolling(200, min_periods=100).mean()
    sma50_panel = df_closes.rolling(50, min_periods=25).mean()
    ema20_panel = df_closes.ewm(span=20, min_periods=10, adjust=False).mean()

    pct_above_200 = ((df_closes > sma200_panel).sum(axis=1) / sma200_panel.notna().sum(axis=1)) * 100.0
    pct_above_50 = ((df_closes > sma50_panel).sum(axis=1) / sma50_panel.notna().sum(axis=1)) * 100.0
    pct_above_20 = ((df_closes > ema20_panel).sum(axis=1) / ema20_panel.notna().sum(axis=1)) * 100.0

    # 2. Daily Gainers / Losers Velocity
    prev_closes = df_closes.shift(1)
    is_gainer = (df_closes > prev_closes)
    is_loser = (df_closes < prev_closes)
    gainers_count = is_gainer.sum(axis=1)
    losers_count = is_loser.sum(axis=1)
    pct_gainers = (gainers_count / total_active) * 100.0
    gainers_10sma = pct_gainers.rolling(10).mean()

    # 3. Advance-Decline & McClellan Breadth Oscillator
    net_advances = gainers_count - losers_count
    ad_line = net_advances.cumsum()
    mcclellan_osc = net_advances.ewm(span=19, adjust=False).mean() - net_advances.ewm(span=39, adjust=False).mean()

    # 4. Volume-Weighted Advance Thrust
    up_volume = (df_vols * is_gainer).sum(axis=1)
    down_volume = (df_vols * is_loser).sum(axis=1)
    total_volume = up_volume + down_volume
    pct_up_volume = (up_volume / total_volume) * 100.0
    vol_thrust_10sma = pct_up_volume.rolling(10).mean()

    # 5. Net 52-Week Highs vs. Lows
    rolling_52wh = df_highs.rolling(250, min_periods=120).max()
    rolling_52wl = df_lows.rolling(250, min_periods=120).min()
    near_52wh_pct = ((df_closes >= rolling_52wh * 0.98).sum(axis=1) / total_active) * 100.0
    near_52wl_pct = ((df_closes <= rolling_52wl * 1.02).sum(axis=1) / total_active) * 100.0
    net_52w = near_52wh_pct - near_52wl_pct

    # 6. Composite Market Strength Index (CMSI, 0 to 100)
    cmsi_series = (
        pct_above_200 * 0.25 +
        pct_above_50 * 0.25 +
        pct_above_20 * 0.20 +
        gainers_10sma * 0.15 +
        vol_thrust_10sma * 0.15
    ).round(1)

    df_res = pd.DataFrame({
        'total_stocks': total_active,
        'above_200_count': (df_closes > sma200_panel).sum(axis=1),
        'pct_200': pct_above_200.round(1),
        'pct_50': pct_above_50.round(1),
        'pct_20': pct_above_20.round(1),
        'gainers_count': gainers_count,
        'losers_count': losers_count,
        'pct_gainers': pct_gainers.round(1),
        'gainers_10sma': gainers_10sma.round(1),
        'ad_line': ad_line,
        'mcclellan': mcclellan_osc.round(2),
        'pct_up_vol': pct_up_volume.round(1),
        'vol_thrust_10sma': vol_thrust_10sma.round(1),
        'net_52w': net_52w.round(1),
        'cmsi': cmsi_series
    }).dropna(subset=['pct_200'])

    chart_slice = df_res.iloc[-400:].copy()
    
    series_structural = []
    series_gainers = []
    series_vol_thrust = []
    series_cmsi = []
    
    for dt, row in chart_slice.iterrows():
        t_str = dt.strftime('%Y-%m-%d')
        series_structural.append({
            'time': t_str,
            'pct_200': float(row['pct_200']),
            'pct_50': float(row['pct_50']),
            'pct_20': float(row['pct_20'])
        })
        series_gainers.append({
            'time': t_str,
            'pct_gainers': float(row['pct_gainers']),
            'gainers_10sma': float(row['gainers_10sma']) if not np.isnan(row['gainers_10sma']) else 50.0,
            'gainers_count': int(row['gainers_count']),
            'losers_count': int(row['losers_count'])
        })
        series_vol_thrust.append({
            'time': t_str,
            'pct_up_vol': float(row['pct_up_vol']),
            'vol_thrust_10sma': float(row['vol_thrust_10sma']) if not np.isnan(row['vol_thrust_10sma']) else 50.0
        })
        series_cmsi.append({
            'time': t_str,
            'cmsi': float(row['cmsi'])
        })

    latest = df_res.iloc[-1]
    prev_1w = df_res.iloc[-6] if len(df_res) >= 6 else latest
    prev_1m = df_res.iloc[-22] if len(df_res) >= 22 else latest

    curr_cmsi = float(latest['cmsi'])
    if curr_cmsi >= 70:
        regime_label = "Strong Bull Expansion"
        regime_status = "BULL_EXPANSION"
        regime_color = "#10b981"
        regime_desc = "High-conviction market-wide uptrend. Breakouts follow through with broad institutional participation."
        playbook = "Aggressive long positioning favored. Trade supply breakouts in top momentum runners with standard position sizing."
    elif curr_cmsi >= 50:
        regime_label = "Selective Accumulation"
        regime_status = "SELECTIVE_ACCUMULATION"
        regime_color = "#38bdf8"
        regime_desc = "Constructive swing environment. Market breadth is healthy but requires strict quality stock selection."
        playbook = "Prioritize buying pullbacks to Grade A+ Demand Zones in Safe D&S Anchors. Avoid chasing extended breakouts."
    elif curr_cmsi >= 35:
        regime_label = "Choppy Neutral / Early Turn"
        regime_status = "CHOPPY_NEUTRAL"
        regime_color = "#f59e0b"
        regime_desc = "Range-bound rotation. Short-term breadth is inflecting, but macro structural breadth remains depressed."
        playbook = "Do NOT chase breakouts blindly. Focus on high-reward Demand Rebounds. Size positions at 50-70% and book quick targets."
    else:
        regime_label = "Structural Distribution"
        regime_status = "STRUCTURAL_DISTRIBUTION"
        regime_color = "#ef4444"
        regime_desc = "Widespread selling pressure. Stocks are shattering demand zones and slipping into falling cascade traps."
        playbook = "Defensive capital preservation. Avoid dip buying. Tighten stop losses and increase cash allocation."

    summary = {
        'universe': universe_filter,
        'universe_name': "Nifty 50 (Bluechips)" if universe_filter == 'nifty50' else "Nifty F&O (115 Equities)",
        'date_str': latest.name.strftime('%A, %d %B %Y'),
        'total_stocks': int(latest['total_stocks']),
        'cmsi': curr_cmsi,
        'cmsi_1m_shift': round(curr_cmsi - float(prev_1m['cmsi']), 1),
        'regime_label': regime_label,
        'regime_status': regime_status,
        'regime_color': regime_color,
        'regime_desc': regime_desc,
        'playbook': playbook,
        'above_200_count': int(latest['above_200_count']),
        'pct_200': float(latest['pct_200']),
        'pct_200_1m_shift': round(float(latest['pct_200']) - float(prev_1m['pct_200']), 1),
        'pct_50': float(latest['pct_50']),
        'pct_50_1m_shift': round(float(latest['pct_50']) - float(prev_1m['pct_50']), 1),
        'pct_20': float(latest['pct_20']),
        'pct_20_1m_shift': round(float(latest['pct_20']) - float(prev_1m['pct_20']), 1),
        'gainers_count': int(latest['gainers_count']),
        'losers_count': int(latest['losers_count']),
        'pct_gainers': float(latest['pct_gainers']),
        'gainers_10sma': float(latest['gainers_10sma']),
        'gainers_10sma_1m_shift': round(float(latest['gainers_10sma']) - float(prev_1m['gainers_10sma']), 1),
        'pct_up_vol': float(latest['pct_up_vol']),
        'vol_thrust_10sma': float(latest['vol_thrust_10sma']),
        'vol_thrust_1m_shift': round(float(latest['vol_thrust_10sma']) - float(prev_1m['vol_thrust_10sma']), 1),
        'mcclellan': float(latest['mcclellan']),
        'mcclellan_1m_shift': round(float(latest['mcclellan']) - float(prev_1m['mcclellan']), 2),
        'net_52w': float(latest['net_52w'])
    }

    return {
        'summary': summary,
        'series_structural': series_structural,
        'series_gainers': series_gainers,
        'series_vol_thrust': series_vol_thrust,
        'series_cmsi': series_cmsi
    }

def clear_market_breadth_cache():
    """Explicitly clears the in-memory market breadth cache."""
    global _BREADTH_CACHE
    _BREADTH_CACHE.clear()

def get_market_breadth_payload(force_refresh=False):
    """
    Returns precomputed breadth payloads for both 'all' and 'nifty50' universes.
    Automatically checks fo_historical_dump.json file modification time (mtime),
    invalidating and recomputing immediately whenever data is synced on disk.
    """
    global _BREADTH_CACHE
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dump_path = os.path.join(base_dir, 'data', 'fo_historical_dump.json')
    current_mtime = os.path.getmtime(dump_path) if os.path.exists(dump_path) else 0

    if force_refresh or 'payloads' not in _BREADTH_CACHE or _BREADTH_CACHE.get('mtime') != current_mtime:
        all_data = compute_universe_breadth('all')
        nifty50_data = compute_universe_breadth('nifty50')
        _BREADTH_CACHE['payloads'] = {
            'all': all_data,
            'nifty50': nifty50_data
        }
        _BREADTH_CACHE['mtime'] = current_mtime
    return _BREADTH_CACHE['payloads']

def get_market_pulse_summary(force_refresh=False):
    """
    Returns quick summary metrics for the Quant Terminal header and Drawer.
    """
    payloads = get_market_breadth_payload(force_refresh=force_refresh)
    return {
        'all': payloads['all']['summary'] if payloads and 'all' in payloads else {},
        'nifty50': payloads['nifty50']['summary'] if payloads and 'nifty50' in payloads else {}
    }

