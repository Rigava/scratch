import json
import os
import pandas as pd
import numpy as np

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

def parse_df(records):
    df = pd.DataFrame(records, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = pd.to_datetime(df['date'].astype(str).str.slice(0, 10))
    df = df.sort_values('date').reset_index(drop=True)
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def get_quant_terminal_payload():
    """
    Computes full universe metrics, verified S/R levels, demand/supply boundaries,
    and 100-session candlestick data for all stocks in fo_historical_dump.json.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dump_path = os.path.join(base_dir, 'data', 'fo_historical_dump.json')
    if not os.path.exists(dump_path):
        return [], {}

    with open(dump_path, 'r', encoding='utf-8') as f:
        raw_dump = json.load(f)

    ATR_PERIOD = 14
    records = []
    chart_data_payload = {}

    for symbol, raw_records in raw_dump.items():
        if len(raw_records) < 70:
            continue
        df = parse_df(raw_records)
        
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs()
        ], axis=1).max(axis=1)
        df['atr'] = tr.ewm(alpha=1/ATR_PERIOD, min_periods=ATR_PERIOD, adjust=False).mean()
        df['vol_sma20'] = df['volume'].rolling(20).mean()
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_45'] = df['close'].rolling(45).mean()
        df['sma_90'] = df['close'].rolling(90).mean()
        
        sub = df.iloc[-120:].copy().reset_index(drop=True)
        curr = sub.iloc[-1]
        prev = sub.iloc[-2]
        
        atr = curr['atr'] if not np.isnan(curr['atr']) else curr['close'] * 0.02
        cmp_price = curr['close']
        vol_ratio = curr['volume'] / curr['vol_sma20'] if (curr['vol_sma20'] > 0) else 1.0
        prev_vol_ratio = prev['volume'] / df['vol_sma20'].iloc[-2] if (df['vol_sma20'].iloc[-2] > 0) else 1.0
        day_ret = ((curr['close'] - prev['close']) / prev['close']) * 100.0
        
        # 52W stats
        h52w = df['high'].iloc[-250:].max()
        l52w = df['low'].iloc[-250:].min()
        dist_52wh = ((cmp_price - h52w) / h52w) * 100.0
        dist_52wl = ((cmp_price - l52w) / l52w) * 100.0
        
        # Volatility
        pct_rets = df['close'].pct_change().iloc[-60:].dropna()
        d_vol = pct_rets.std() * 100.0
        a_vol = d_vol * np.sqrt(252)
        
        # Swing Pivots (5-bar window)
        pivot_lows = []
        pivot_highs = []
        for i in range(2, len(sub)-2):
            if sub['low'].iloc[i] == sub['low'].iloc[i-2:i+3].min():
                pivot_lows.append((i, sub['date'].iloc[i], sub['low'].iloc[i]))
            if sub['high'].iloc[i] == sub['high'].iloc[i-2:i+3].max():
                pivot_highs.append((i, sub['date'].iloc[i], sub['high'].iloc[i]))
                
        tol = 0.5 * atr
        def score_level(lvl, is_sup=True):
            touches = 0
            rejections = 0
            vols = []
            for i in range(len(sub)-1):
                bar = sub.iloc[i]
                if (bar['low'] <= lvl + tol) and (bar['high'] >= lvl - tol):
                    touches += 1
                    vols.append(bar['volume'] / sub['vol_sma20'].iloc[i] if sub['vol_sma20'].iloc[i]>0 else 1.0)
                    crange = bar['high'] - bar['low']
                    bmin = min(bar['open'], bar['close'])
                    bmax = max(bar['open'], bar['close'])
                    if crange > 0:
                        if is_sup and ((bmin - bar['low']) / crange >= 0.4): rejections += 1
                        elif (not is_sup) and ((bar['high'] - bmax) / crange >= 0.4): rejections += 1
            if is_sup: flips = len([h for idx, dt, h in pivot_highs if abs(h - lvl) <= tol])
            else: flips = len([l for idx, dt, l in pivot_lows if abs(l - lvl) <= tol])
            
            avg_v = float(np.mean(vols)) if vols else 1.0
            score = min(40, touches*10) + min(25, rejections*8) + (20 if flips > 0 else 0) + (15 if avg_v >= 1.2 else (10 if avg_v >= 1.0 else 5))
            score = min(100, max(0, score))
            if score >= 75: grade = 'A+'
            elif score >= 55: grade = 'A'
            elif score >= 35: grade = 'B'
            else: grade = 'C'
            return lvl, touches, rejections, flips, round(avg_v, 2), score, grade

        p_low_vals = [p[2] for p in pivot_lows if p[2] <= cmp_price + 0.2*atr]
        sup_lvl = max(p_low_vals) if p_low_vals else sub['low'].min()
        
        p_high_vals = [p[2] for p in pivot_highs if p[2] >= cmp_price - 0.2*atr]
        res_lvl = min(p_high_vals) if p_high_vals else sub['high'].max()
        
        sup_val, s_touch, s_rej, s_flips, s_vol, s_score, s_grade = score_level(sup_lvl, True)
        res_val, r_touch, r_rej, r_flips, r_vol, r_score, r_grade = score_level(res_lvl, False)
        
        d_floor = round(sup_val - 0.25 * atr, 2)
        d_ceil = round(sup_val + 0.75 * atr, 2)
        s_floor = round(res_val - 0.75 * atr, 2)
        s_ceil = round(res_val + 0.25 * atr, 2)
        
        # 4 Structural Regimes
        is_breakdown_demand_hv = ((cmp_price < d_floor and vol_ratio >= 1.2) or (prev['close'] < d_floor and prev_vol_ratio >= 1.2))
        is_breakout_supply_hv = ((cmp_price > s_ceil and vol_ratio >= 1.2) or (prev['close'] > s_ceil and prev_vol_ratio >= 1.2))
        is_demand_rebound = ((curr['low'] <= d_ceil) and (cmp_price >= d_floor) and (cmp_price > curr['open']) and (day_ret >= 0.5))
        is_supply_rejection = ((curr['high'] >= s_floor) and (cmp_price <= s_ceil) and (cmp_price < curr['open']) and (day_ret <= -0.5))
        
        ideal_sl = round(d_floor - 0.50 * atr, 2)
        ideal_tgt = round(s_floor, 2) if cmp_price < s_floor else round(s_ceil + 2.0 * atr, 2)
        risk_pts = cmp_price - ideal_sl
        reward_pts = ideal_tgt - cmp_price
        rr = round(reward_pts / risk_pts, 2) if risk_pts > 0 else 0.0
        
        category = "Consolidation / Equilibrium"
        if is_breakdown_demand_hv: category = "Demand Breakdown (High Vol)"
        elif is_breakout_supply_hv: category = "Supply Breakout (High Vol)"
        elif is_demand_rebound: category = "Demand Rebound"
        elif is_supply_rejection: category = "Supply Rejection"
        elif cmp_price <= d_ceil: category = "In Demand Zone"
        elif cmp_price >= s_floor: category = "In Supply Zone"

        records.append({
            'symbol': symbol,
            'close': round(cmp_price, 2),
            'change_pct': round(day_ret, 2),
            'volume': int(curr['volume']),
            'vol_ratio': round(vol_ratio, 2),
            'category': category,
            'demand_floor': d_floor,
            'demand_ceil': d_ceil,
            'supply_floor': s_floor,
            'supply_ceil': s_ceil,
            'support_lvl': round(sup_val, 2),
            'support_grade': s_grade,
            'support_score': int(s_score),
            'support_touches': int(s_touch),
            'support_rejections': int(s_rej),
            'support_flips': int(s_flips),
            'resist_lvl': round(res_val, 2),
            'resist_grade': r_grade,
            'resist_score': int(r_score),
            'resist_touches': int(r_touch),
            'resist_rejections': int(r_rej),
            'resist_flips': int(r_flips),
            'ideal_sl': ideal_sl,
            'ideal_tgt': ideal_tgt,
            'rr_ratio': rr,
            'atr': round(atr, 2),
            'sma_20': round(curr['sma_20'], 2) if not np.isnan(curr['sma_20']) else None,
            'sma_45': round(curr['sma_45'], 2) if not np.isnan(curr['sma_45']) else None,
            'sma_90': round(curr['sma_90'], 2) if not np.isnan(curr['sma_90']) else None,
            'h52w': round(h52w, 2),
            'dist_52wh': round(dist_52wh, 2),
            'l52w': round(l52w, 2),
            'dist_52wl': round(dist_52wl, 2),
            'daily_vol': round(d_vol, 2),
            'annual_vol': round(a_vol, 2),
        })
        
        candles = []
        recent_slice = sub.iloc[-100:].copy()
        for idx, r in recent_slice.iterrows():
            candles.append({
                'time': r['date'].strftime('%Y-%m-%d'),
                'open': round(float(r['open']), 2),
                'high': round(float(r['high']), 2),
                'low': round(float(r['low']), 2),
                'close': round(float(r['close']), 2),
                'volume': int(r['volume']),
                'sma20': round(float(r['sma_20']), 2) if not np.isnan(r.get('sma_20', np.nan)) else None,
                'sma45': round(float(r['sma_45']), 2) if not np.isnan(r.get('sma_45', np.nan)) else None,
                'sma90': round(float(r['sma_90']), 2) if not np.isnan(r.get('sma_90', np.nan)) else None,
                'vol_sma20': int(r['vol_sma20']) if not np.isnan(r.get('vol_sma20', np.nan)) else None
            })
        chart_data_payload[symbol] = candles

    return records, chart_data_payload
