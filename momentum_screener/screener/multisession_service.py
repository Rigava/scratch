import math
from typing import List, Dict, Any, Optional

def calculate_sma(prices: List[float], period: int) -> List[Optional[float]]:
    n = len(prices)
    if n < period:
        return [None] * n
    sma = [None] * (period - 1)
    csum = sum(prices[:period])
    sma.append(csum / period)
    for i in range(period, n):
        csum += prices[i] - prices[i - period]
        sma.append(csum / period)
    return sma

def calculate_ema(prices: List[float], period: int) -> List[Optional[float]]:
    n = len(prices)
    if n < period:
        return [None] * n
    ema = [None] * n
    init_sma = sum(prices[:period]) / period
    ema[period - 1] = init_sma
    mult = 2.0 / (period + 1)
    for i in range(period, n):
        ema[i] = (prices[i] - ema[i - 1]) * mult + ema[i - 1]
    return ema

def calculate_rsi(prices: List[float], period: int = 14) -> List[Optional[float]]:
    n = len(prices)
    if n <= period:
        return [None] * n
    rsi = [None] * n
    deltas = [prices[i] - prices[i - 1] for i in range(1, n)]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        gain = gains[i - 1]
        loss = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14):
    n = len(closes)
    if n <= period:
        return [None] * n, [None] * n, [None] * n

    tr = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n

    for i in range(1, n):
        h, l, prev_c = highs[i], lows[i], closes[i - 1]
        tr[i] = max(h - l, abs(h - prev_c), abs(l - prev_c))
        up_move = h - highs[i - 1]
        down_move = lows[i - 1] - l
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    smoothed_tr = [0.0] * n
    smoothed_plus_dm = [0.0] * n
    smoothed_minus_dm = [0.0] * n

    smoothed_tr[period] = sum(tr[1 : period + 1])
    smoothed_plus_dm[period] = sum(plus_dm[1 : period + 1])
    smoothed_minus_dm[period] = sum(minus_dm[1 : period + 1])

    for i in range(period + 1, n):
        smoothed_tr[i] = smoothed_tr[i - 1] - (smoothed_tr[i - 1] / period) + tr[i]
        smoothed_plus_dm[i] = smoothed_plus_dm[i - 1] - (smoothed_plus_dm[i - 1] / period) + plus_dm[i]
        smoothed_minus_dm[i] = smoothed_minus_dm[i - 1] - (smoothed_minus_dm[i - 1] / period) + minus_dm[i]

    plus_di = [None] * n
    minus_di = [None] * n
    dx = [None] * n

    for i in range(period, n):
        tr_val = smoothed_tr[i]
        if tr_val == 0:
            plus_di[i] = 0.0
            minus_di[i] = 0.0
            dx[i] = 0.0
        else:
            p_di = 100.0 * (smoothed_plus_dm[i] / tr_val)
            m_di = 100.0 * (smoothed_minus_dm[i] / tr_val)
            plus_di[i] = p_di
            minus_di[i] = m_di
            sum_di = p_di + m_di
            dx[i] = 0.0 if sum_di == 0 else 100.0 * (abs(p_di - m_di) / sum_di)

    adx = [None] * n
    dx_start = period
    valid_dxs = [d for d in dx[dx_start : dx_start + period] if d is not None]
    if len(valid_dxs) < period:
        return [None] * n, plus_di, minus_di

    adx[dx_start + period - 1] = sum(valid_dxs) / period
    for i in range(dx_start + period, n):
        if dx[i] is not None and adx[i - 1] is not None:
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx, plus_di, minus_di

def calculate_macd(prices: List[float]):
    n = len(prices)
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)

    macd_line = [None] * n
    for i in range(n):
        if ema12[i] is not None and ema26[i] is not None:
            macd_line[i] = ema12[i] - ema26[i]

    first_valid = 0
    while first_valid < n and macd_line[first_valid] is None:
        first_valid += 1

    signal_line = [None] * n
    if first_valid + 9 <= n:
        sub_signal = calculate_ema(macd_line[first_valid:], 9)
        for i in range(len(sub_signal)):
            signal_line[first_valid + i] = sub_signal[i]

    hist = [None] * n
    for i in range(n):
        if macd_line[i] is not None and signal_line[i] is not None:
            hist[i] = macd_line[i] - signal_line[i]

    return macd_line, signal_line, hist

def calculate_stance(price: float, closes_window: List[float], sma200: Optional[float], ema50: Optional[float]) -> str:
    if not closes_window:
        return 'Stable'
    max_52w = max(closes_window)
    min_52w = min(closes_window)
    if max_52w > 0 and price >= max_52w * 0.985:
        return '52W High'
    elif min_52w > 0 and price <= min_52w * 1.015:
        return '52W Low'
    elif sma200 and abs(price - sma200) / sma200 <= 0.015:
        return 'Near SMA 200'
    elif ema50 and abs(price - ema50) / ema50 <= 0.015:
        return 'Near EMA 50'
    return 'Stable'

def analyze_3session_kinematics(candles: List[List[Any]], symbol: str, offset: int = 0) -> Optional[Dict[str, Any]]:
    if not candles or len(candles) < 220:
        return None

    end_idx = len(candles) - offset
    if end_idx < 220:
        return None

    sub_candles = candles[:end_idx]
    n = len(sub_candles)
    if n < 3:
        return None

    dates = [str(c[0]).split('T')[0] for c in sub_candles]
    opens = [float(c[1]) for c in sub_candles]
    highs = [float(c[2]) for c in sub_candles]
    lows = [float(c[3]) for c in sub_candles]
    closes = [float(c[4]) for c in sub_candles]
    volumes = [float(c[5]) if len(c) > 5 else 1.0 for c in sub_candles]

    sma200 = calculate_sma(closes, 200)
    ema50 = calculate_ema(closes, 50)
    ema20 = calculate_ema(closes, 20)
    rsi14 = calculate_rsi(closes, 14)
    adx14, plus_di, minus_di = calculate_adx(highs, lows, closes, 14)
    macd, signal, macd_hist = calculate_macd(closes)
    vol_sma20 = calculate_sma(volumes, 20)

    idx_t2, idx_t1, idx_t = n - 3, n - 2, n - 1

    p_t2, p_t1, p_t = closes[idx_t2], closes[idx_t1], closes[idx_t]
    r_t2, r_t1, r_t = rsi14[idx_t2] or 50.0, rsi14[idx_t1] or 50.0, rsi14[idx_t] or 50.0
    adx_t2, adx_t1, adx_t = adx14[idx_t2] or 20.0, adx14[idx_t1] or 20.0, adx14[idx_t] or 20.0
    pdi_t, mdi_t = plus_di[idx_t] or 20.0, minus_di[idx_t] or 20.0
    h_t2, h_t1, h_t = macd_hist[idx_t2] or 0.0, macd_hist[idx_t1] or 0.0, macd_hist[idx_t] or 0.0

    vsma_t2 = vol_sma20[idx_t2] or 1.0
    vsma_t1 = vol_sma20[idx_t1] or 1.0
    vsma_t = vol_sma20[idx_t] or 1.0

    vr_t2 = volumes[idx_t2] / vsma_t2 if vsma_t2 > 0 else 1.0
    vr_t1 = volumes[idx_t1] / vsma_t1 if vsma_t1 > 0 else 1.0
    vr_t = volumes[idx_t] / vsma_t if vsma_t > 0 else 1.0

    w_t2 = closes[max(0, idx_t2 - 250) : idx_t2]
    w_t1 = closes[max(0, idx_t1 - 250) : idx_t1]
    w_t = closes[max(0, idx_t - 250) : idx_t]

    stance_t2 = calculate_stance(p_t2, w_t2, sma200[idx_t2], ema50[idx_t2])
    stance_t1 = calculate_stance(p_t1, w_t1, sma200[idx_t1], ema50[idx_t1])
    stance_t = calculate_stance(p_t, w_t, sma200[idx_t], ema50[idx_t])

    delta_p1d = round(((p_t - p_t1) / p_t1) * 100.0, 2)
    delta_p2d = round(((p_t - p_t2) / p_t2) * 100.0, 2)
    delta_r1d = round(r_t - r_t1, 2)
    delta_r2d = round(r_t - r_t2, 2)
    delta_adx2d = round(adx_t - adx_t2, 2)

    candle_range_t = highs[idx_t] - lows[idx_t]
    upper_wick_t = highs[idx_t] - max(opens[idx_t], closes[idx_t])
    upper_wick_ratio = (upper_wick_t / candle_range_t) if candle_range_t > 0 else 0.0

    # 1. STRUCTURAL FAILURE SIGNATURES
    structural_failures = []
    if (stance_t1 == '52W High' or stance_t2 == '52W High' or r_t1 >= 68.0) and delta_p1d <= -1.5 and vr_t >= 1.0:
        structural_failures.append('BULL_TRAP')

    e50_t = ema50[idx_t]
    e50_t1 = ema50[idx_t1]
    if e50_t and e50_t1 and p_t1 >= e50_t1 * 0.995 and p_t < e50_t * 0.985 and delta_p1d < -0.8:
        structural_failures.append('MA50_BREAKDOWN')

    if vr_t >= 1.4 and upper_wick_ratio >= 0.50 and delta_p1d < 0.5:
        structural_failures.append('EXPANSION_FAILURE')

    # 2. MOMENTUM ACCELERATION SIGNATURES
    momentum_accelerations = []
    if delta_r2d >= 8.0 and delta_r1d >= 3.0 and r_t >= 56.0 and p_t > p_t1 > p_t2:
        momentum_accelerations.append('MOMENTUM_IGNITION')

    if adx_t >= 22.0 and delta_adx2d >= 2.5 and pdi_t > (mdi_t + 5.0) and p_t > (sma200[idx_t] or 0):
        momentum_accelerations.append('ADX_IGNITION')

    if vr_t >= 1.8 and vr_t1 >= 1.2 and delta_p2d >= 2.0:
        momentum_accelerations.append('VOLUME_CASCADE')

    # 3. TREND REVERSAL SIGNATURES
    trend_reversals = []
    if (stance_t2 == '52W Low' or stance_t1 == '52W Low' or r_t2 <= 36.0) and delta_p1d >= 1.8 and p_t > highs[idx_t2]:
        trend_reversals.append('BEAR_TRAP_RECLAIM')

    if p_t < p_t2 and r_t >= (r_t2 + 3.0) and r_t <= 55.0 and delta_p1d >= 0.5:
        trend_reversals.append('BULLISH_DIVERGENCE')

    if r_t1 >= 72.0 and vr_t >= 2.5 and (delta_p1d < 0.2 or upper_wick_ratio >= 0.50):
        trend_reversals.append('CLIMAX_EXHAUSTION')

    primary_regime = 'STABLE'
    regime_label = 'Neutral Trend'
    badge_color = '#64748b'
    summary = 'Price and momentum indicators are trending within normal bounds.'

    if structural_failures:
        primary_regime = 'STRUCTURAL_FAILURE'
        regime_label = f"WARNING Failure: {structural_failures[0].replace('_', ' ')}"
        badge_color = '#ef4444'
        if 'BULL_TRAP' in structural_failures:
            summary = f"Bull Trap confirmed: Recent breakout attempt at Rs {highs[idx_t1]} rejected back down to Rs {p_t} (-{abs(delta_p1d)}%) on volume."
        elif 'MA50_BREAKDOWN' in structural_failures:
            summary = f"50 EMA dynamic support violated: Closed at Rs {p_t} below key 50-day average."
        else:
            summary = "Expansion failure: Heavy selling wick rejection at higher prices."
    elif momentum_accelerations:
        primary_regime = 'MOMENTUM_ACCELERATION'
        regime_label = f"IGNITION: {momentum_accelerations[0].replace('_', ' ')}"
        badge_color = '#10b981'
        summary = f"Momentum accelerating: RSI jumped +{delta_r2d} pts to {round(r_t, 1)}, 2-day return +{delta_p2d}% with {round(vr_t, 1)}x volume."
    elif trend_reversals:
        primary_regime = 'TREND_REVERSAL'
        regime_label = f"REVERSAL: {trend_reversals[0].replace('_', ' ')}"
        badge_color = '#8b5cf6'
        if 'BEAR_TRAP_RECLAIM' in trend_reversals:
            summary = f"Bear Trap Reclaim: Deep oversold flush reversed cleanly above prior high with +{delta_p1d}% gain."
        elif 'BULLISH_DIVERGENCE' in trend_reversals:
            summary = f"Bullish divergence: RSI rising (+{round(delta_r2d, 1)}) while price tests recent lows."
        else:
            summary = "Climax volume exhaustion: Volume surge meeting overhead distribution."

    return {
        'symbol': symbol,
        'dates': [dates[idx_t2], dates[idx_t1], dates[idx_t]],
        'prices': [p_t2, p_t1, p_t],
        'highs': [highs[idx_t2], highs[idx_t1], highs[idx_t]],
        'lows': [lows[idx_t2], lows[idx_t1], lows[idx_t]],
        'volumes': [volumes[idx_t2], volumes[idx_t1], volumes[idx_t]],
        'price_change_1d_pct': delta_p1d,
        'price_change_2d_pct': delta_p2d,
        'rsi_values': [round(r_t2, 1), round(r_t1, 1), round(r_t, 1)],
        'rsi_change_1d': delta_r1d,
        'rsi_change_2d': delta_r2d,
        'vol_ratios': [round(vr_t2, 2), round(vr_t1, 2), round(vr_t, 2)],
        'adx_values': [round(adx_t2, 1), round(adx_t1, 1), round(adx_t, 1)],
        'plus_di': round(pdi_t, 1),
        'minus_di': round(mdi_t, 1),
        'macd_hist': [round(h_t2, 2), round(h_t1, 2), round(h_t, 2)],
        'stances': [stance_t2, stance_t1, stance_t],
        'structural_failures': structural_failures,
        'momentum_accelerations': momentum_accelerations,
        'trend_reversals': trend_reversals,
        'primary_regime': primary_regime,
        'regime_label': regime_label,
        'badge_color': badge_color,
        'summary': summary
    }

def scan_all_stocks_multisession(dump_data: Dict[str, List[List[Any]]], offset: int = 0) -> Dict[str, Any]:
    all_results = []
    failures = []
    accelerations = []
    reversals = []

    for symbol, candles in dump_data.items():
        res = analyze_3session_kinematics(candles, symbol, offset=offset)
        if res:
            all_results.append(res)
            if res['primary_regime'] == 'STRUCTURAL_FAILURE':
                failures.append(res)
            elif res['primary_regime'] == 'MOMENTUM_ACCELERATION':
                accelerations.append(res)
            elif res['primary_regime'] == 'TREND_REVERSAL':
                reversals.append(res)

    return {
        'total_scanned': len(all_results),
        'all_results': all_results,
        'structural_failures': failures,
        'momentum_accelerations': accelerations,
        'trend_reversals': reversals
    }
