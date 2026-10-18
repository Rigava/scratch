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

def compute_5y_structural_profile(symbol, df):
    """
    Evaluates 6 core quantitative dimensions over trailing 5 years:
    1. Demand Bounce Probability (Support Integrity)
    2. Demand Breakdown Probability (Falling Zone Cascade Risk)
    3. Supply Breakout vs Rejection Propensity
    4. 200-Day SMA Bullish Persistence (% of trading days above 200 SMA)
    5. Maximum Tail Drawdown (Max DD)
    6. Annualized Realized Volatility
    """
    df = df.copy()
    df['sma_200'] = df['close'].rolling(200).mean()
    valid_200 = df.dropna(subset=['sma_200'])
    pct_above_200 = float((valid_200['close'] > valid_200['sma_200']).mean() * 100.0) if len(valid_200) > 0 else 50.0
    
    peak = df['close'].cummax()
    dd = (df['close'] - peak) / peak
    max_dd = float(abs(dd.min() * 100.0))
    pct_rets = df['close'].pct_change().dropna()
    ann_vol = float(pct_rets.std() * np.sqrt(252) * 100.0)
    
    lows = df['low'].values
    highs = df['high'].values
    
    is_pivot_low = (lows[2:-2] < lows[1:-3]) & (lows[2:-2] < lows[:-4]) & (lows[2:-2] < lows[3:-1]) & (lows[2:-2] < lows[4:])
    pivot_low_indices = np.where(is_pivot_low)[0] + 2
    
    is_pivot_high = (highs[2:-2] > highs[1:-3]) & (highs[2:-2] > highs[:-4]) & (highs[2:-2] > highs[3:-1]) & (highs[2:-2] > highs[4:])
    pivot_high_indices = np.where(is_pivot_high)[0] + 2
    
    bounces, breakdowns, d_tests = 0, 0, 0
    for idx in pivot_low_indices[:-1]:
        p_low = lows[idx]
        fwd_low = lows[idx+1 : min(len(df), idx+15)]
        fwd_high = highs[idx+1 : min(len(df), idx+15)]
        if len(fwd_low) == 0: continue
        d_tests += 1
        if np.min(fwd_low) < p_low * 0.975: breakdowns += 1
        elif np.max(fwd_high) > p_low * 1.04: bounces += 1
        
    demand_bounce_rate = (bounces / d_tests * 100.0) if d_tests > 0 else 50.0
    demand_breakdown_rate = (breakdowns / d_tests * 100.0) if d_tests > 0 else 50.0
    
    breakouts, rejections, s_tests = 0, 0, 0
    for idx in pivot_high_indices[:-1]:
        p_high = highs[idx]
        fwd_high = highs[idx+1 : min(len(df), idx+15)]
        fwd_low = lows[idx+1 : min(len(df), idx+15)]
        if len(fwd_high) == 0: continue
        s_tests += 1
        if np.max(fwd_high) > p_high * 1.025: breakouts += 1
        elif np.min(fwd_low) < p_high * 0.96: rejections += 1
        
    supply_breakout_rate = (breakouts / s_tests * 100.0) if s_tests > 0 else 50.0
    supply_rejection_rate = (rejections / s_tests * 100.0) if s_tests > 0 else 50.0
    
    score = 0
    score += min(30, (demand_bounce_rate / 60.0) * 30)
    score += max(0, min(20, (1.0 - (demand_breakdown_rate - 20) / 40.0) * 20))
    score += max(0, min(20, (1.0 - (max_dd - 20) / 40.0) * 20))
    score += min(15, (pct_above_200 / 70.0) * 15)
    score += 15 if (18 <= ann_vol <= 32) else (10 if ann_vol < 18 else max(0, 15 - (ann_vol - 32)*0.5))
    safety_score = round(min(100.0, max(0.0, score)), 1)
    
    if demand_breakdown_rate >= 42.0 or max_dd >= 58.0:
        label = "High Falling-Zone Risk"
        rec = "AVOID Buying Dips (Cascade traps; demand levels fail repeatedly)"
    elif supply_breakout_rate >= 45.0 and pct_above_200 >= 60.0:
        label = "Expansion Runner"
        rec = "Breakout Favored (Regularly punches through overhead supply)"
    elif safety_score >= 75.0 and demand_breakdown_rate < 38.0 and max_dd < 50.0:
        label = "Safe D&S Anchor"
        rec = "Safe for Demand-Buying (Institutional limit orders absorb supply)"
    elif demand_bounce_rate >= 45.0 and supply_rejection_rate >= 45.0:
        label = "Mean-Reversion Oscillating"
        rec = "Range-Bound Setup (Reliable for buying floor and selling ceiling)"
    else:
        label = "Moderate Integrity / Transitional"
        rec = "Requires Stricter Volume Confirmation"
        
    return {
        'struct_label': label,
        'struct_recommendation': rec,
        'safety_score': safety_score,
        'demand_bounce_rate': round(demand_bounce_rate, 1),
        'demand_breakdown_rate': round(demand_breakdown_rate, 1),
        'supply_breakout_rate': round(supply_breakout_rate, 1),
        'supply_rejection_rate': round(supply_rejection_rate, 1),
        'pct_above_200': round(pct_above_200, 1),
        'max_dd': round(max_dd, 1),
        'ann_vol': round(ann_vol, 1),
    }

def get_quant_terminal_payload():
    """
    Computes full universe metrics, verified S/R levels, demand/supply boundaries,
    5-year structural behavioral profiling, and 100-session candlestick data for all stocks in fo_historical_dump.json.
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
        
        # 5-Year Structural Personality Inference
        prof = compute_5y_structural_profile(symbol, df)
        
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
        
        # 4 Structural Flow Regimes
        is_breakout = bool(
            (cmp_price >= s_ceil and (vol_ratio >= 1.05 or day_ret >= 0.5)) or
            (cmp_price >= s_floor and vol_ratio >= 1.2 and day_ret >= 0.5) or
            (prev['close'] >= s_ceil and prev_vol_ratio >= 1.1 and cmp_price >= s_floor) or
            (prev['close'] >= s_floor and prev_vol_ratio >= 1.25 and cmp_price >= s_floor and day_ret >= -0.5)
        )
        is_breakdown_demand_hv = bool(
            (cmp_price < d_floor and (vol_ratio >= 1.2 or day_ret <= -0.5)) or
            (prev['close'] < d_floor and (prev_vol_ratio >= 1.2 or day_ret <= -0.5))
        )
        is_demand_rebound = bool((curr['low'] <= d_ceil) and (cmp_price >= d_floor) and (cmp_price > curr['open']) and (day_ret >= 0.5))
        is_supply_rejection = bool((curr['high'] >= s_floor) and (cmp_price <= s_ceil) and (cmp_price < curr['open']) and (day_ret <= -0.5))
        
        ideal_sl = round(d_floor - 0.50 * atr, 2)
        ideal_tgt = round(s_floor, 2) if cmp_price < s_floor else round(s_ceil + 2.0 * atr, 2)
        risk_pts = cmp_price - ideal_sl
        reward_pts = ideal_tgt - cmp_price
        rr = round(reward_pts / risk_pts, 2) if risk_pts > 0 else 0.0
        
        category = "Consolidation / Equilibrium"
        if is_breakout: category = "Supply Breakout (High Vol)"
        elif is_breakdown_demand_hv: category = "Demand Breakdown (High Vol)"
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
            'is_breakout': is_breakout,
            # 5-Year Structural Personality & Safety
            'struct_label': prof['struct_label'],
            'struct_rec': prof['struct_recommendation'],
            'safety_score': prof['safety_score'],
            'demand_bounce_rate': prof['demand_bounce_rate'],
            'demand_breakdown_rate': prof['demand_breakdown_rate'],
            'supply_breakout_rate': prof['supply_breakout_rate'],
            'supply_rejection_rate': prof['supply_rejection_rate'],
            'pct_above_200': prof['pct_above_200'],
            'max_dd': prof['max_dd'],
            # S/R Boundaries & Verification
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
