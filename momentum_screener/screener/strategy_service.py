import json
import logging
import os
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_STRATEGIES = [
    {
        'name': 'Optimized 45/195 Golden Crossover',
        'slug': 'golden-crossover-45-195',
        'category': 'golden_cross',
        'description': 'Optimized swing trading framework using 45-day and 195-day Simple Moving Averages tailored for Indian high-beta equities with volume breakout validation.',
        'parameters': {'fast_ma': 45, 'slow_ma': 195, 'ma_type': 'SMA', 'volume_multiple': 1.25, 'rsi_min': 45},
        'win_rate': 0.0,
        'total_signals': 0,
        'avg_return_pct': 0.0,
        'is_active': True,
    },
    {
        'name': 'RSI Dynamic Momentum Breakout',
        'slug': 'rsi-momentum-breakout',
        'category': 'rsi_breakout',
        'description': 'Momentum surge strategy triggering on 14-day RSI breaking above 62 with 1.5x average 20-day institutional volume expansion.',
        'parameters': {'rsi_length': 14, 'rsi_threshold': 62, 'volume_multiple': 1.5, 'lookback_days': 20},
        'win_rate': 0.0,
        'total_signals': 0,
        'avg_return_pct': 0.0,
        'is_active': True,
    },
    {
        'name': 'MACD Velocity Shift (8/21/5)',
        'slug': 'macd-velocity-shift',
        'category': 'macd_cross',
        'description': 'Fast-reactive MACD momentum crossover system capturing early trend acceleration above the 200 SMA structural support.',
        'parameters': {'fast_period': 8, 'slow_period': 21, 'signal_period': 5, 'confirm_above_200_sma': True},
        'win_rate': 0.0,
        'total_signals': 0,
        'avg_return_pct': 0.0,
        'is_active': True,
    },
    {
        'name': 'Volatility Squeeze & Expansion',
        'slug': 'volatility-squeeze-breakout',
        'category': 'volatility_squeeze',
        'description': 'Identifies multi-week low volatility compression followed by directional volatility expansion and trend impulse.',
        'parameters': {'bollinger_period': 20, 'keltner_period': 20, 'squeeze_threshold': 1.0, 'atr_stop_multiplier': 1.8},
        'win_rate': 0.0,
        'total_signals': 0,
        'avg_return_pct': 0.0,
        'is_active': True,
    },
    {
        'name': 'Trend Pullback & Key Level Re-Test',
        'slug': 'trend-pullback-retest',
        'category': 'pullback',
        'description': 'Buys shallow corrective pullbacks to rising 50 EMA / 200 SMA key support levels within confirmed higher timeframe uptrends.',
        'parameters': {'trend_ema': 50, 'pullback_pct': 2.5, 'support_level': 'EMA50_OR_SMA200'},
        'win_rate': 0.0,
        'total_signals': 0,
        'avg_return_pct': 0.0,
        'is_active': True,
    },
]

def ensure_default_strategies():
    """
    Ensures that default recommendation strategies exist in the database.
    Can be safely called repeatedly (idempotent). Self-heals if empty.
    """
    from .models import RecommendationStrategy
    try:
        for item in DEFAULT_STRATEGIES:
            slug = item['slug']
            params = item.get('parameters', {})
            strat = RecommendationStrategy.objects.filter(slug=slug).first()
            if not strat:
                RecommendationStrategy.objects.create(
                    name=item['name'],
                    slug=slug,
                    category=item['category'],
                    description=item['description'],
                    parameters_json=json.dumps(params),
                    win_rate=item['win_rate'],
                    total_signals=item['total_signals'],
                    avg_return_pct=item['avg_return_pct'],
                    is_active=item['is_active']
                )
    except Exception as e:
        logger.error(f"Error ensuring default strategies: {e}")


def evaluate_strategy_compliance(ticker, strategy):
    """
    Performs real quantitative analysis of a stock against a specific Strategy Framework's tuned parameters.
    Calculates exact indicators and returns a rich audit checklist with parameter comparisons and compliance status.
    """
    ticker = (ticker or '').strip().upper()
    dump_path = os.path.join(os.path.dirname(__file__), 'data', 'fo_historical_dump.json')
    raw_candles = []
    
    if os.path.exists(dump_path):
        try:
            with open(dump_path, 'r', encoding='utf-8') as f:
                dump_data = json.load(f)
                raw_candles = dump_data.get(ticker, [])
        except Exception:
            pass

    candles_list = []
    if raw_candles:
        for c in raw_candles:
            if isinstance(c, (list, tuple)) and len(c) >= 6:
                candles_list.append({
                    'date': c[0],
                    'open': float(c[1]),
                    'high': float(c[2]),
                    'low': float(c[3]),
                    'close': float(c[4]),
                    'volume': float(c[5])
                })
            elif isinstance(c, dict):
                candles_list.append({
                    'date': c.get('date'),
                    'open': float(c.get('open', 0)),
                    'high': float(c.get('high', 0)),
                    'low': float(c.get('low', 0)),
                    'close': float(c.get('close', 0)),
                    'volume': float(c.get('volume', 0))
                })

    params = strategy.parameters if strategy else {}
    category = strategy.category if strategy else 'golden_cross'
    strategy_name = strategy.name if strategy else 'Institutional Strategy'

    if len(candles_list) < 5:
        return {
            'strategy_name': strategy_name,
            'category': category,
            'status': 'INSUFFICIENT DATA',
            'match_score': 50,
            'criteria_checks': [
                {'param': 'Data Depth', 'target': '>= 5 candles', 'actual': f'{len(candles_list)} candles', 'status': 'WARN'}
            ],
            'analysis_summary': f"Insufficient candle history for {ticker} to compute tuned parameters."
        }

    df = pd.DataFrame(candles_list)
    cmp = float(df['close'].iloc[-1])
    
    # Baseline calculations
    sma200 = float(df['close'].rolling(200).mean().iloc[-1]) if len(df) >= 200 else float(df['close'].mean())
    avg_vol_20 = float(df['volume'].rolling(20).mean().iloc[-1]) if len(df) >= 20 else float(df['volume'].mean())
    cur_vol = float(df['volume'].iloc[-1])
    vol_multiple = cur_vol / (avg_vol_20 + 1e-9) if avg_vol_20 > 0 else 1.0

    criteria_checks = []
    pass_count = 0
    total_checks = 0

    if category == 'golden_cross':
        fast_period = int(params.get('fast_ma', 45))
        slow_period = int(params.get('slow_ma', 195))
        ma_type = params.get('ma_type', 'SMA').upper()
        vol_req = float(params.get('volume_multiple', 1.25))
        rsi_min = float(params.get('rsi_min', 45))

        if ma_type == 'EMA':
            fast_ma = float(df['close'].ewm(span=fast_period, adjust=False).mean().iloc[-1])
            slow_ma = float(df['close'].ewm(span=slow_period, adjust=False).mean().iloc[-1])
        else:
            fast_ma = float(df['close'].rolling(fast_period).mean().iloc[-1]) if len(df) >= fast_period else float(df['close'].mean())
            slow_ma = float(df['close'].rolling(slow_period).mean().iloc[-1]) if len(df) >= slow_period else float(df['close'].mean())

        # RSI 14
        deltas = df['close'].diff()
        gain = (deltas.where(deltas > 0, 0)).rolling(14).mean()
        loss = (-deltas.where(deltas < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = float((100 - (100 / (1 + rs))).iloc[-1]) if len(df) >= 15 else 50.0

        dist_fast = round(((cmp - fast_ma) / fast_ma) * 100, 2)
        dist_slow = round(((cmp - slow_ma) / slow_ma) * 100, 2)
        spread = round(((fast_ma - slow_ma) / slow_ma) * 100, 2)

        # Check 1: Price near Fast MA (within 3.5% or above)
        total_checks += 1
        is_fast_pass = abs(dist_fast) <= 3.5 or dist_fast > 0
        if is_fast_pass: pass_count += 1
        criteria_checks.append({
            'param': f'Fast {ma_type} ({fast_period})',
            'target': 'Near or Above Support',
            'actual': f'₹{fast_ma:,.2f} ({dist_fast:+0.2f}%)',
            'status': 'PASS' if is_fast_pass else 'PULLBACK'
        })

        # Check 2: Fast vs Slow MA alignment
        total_checks += 1
        is_spread_pass = fast_ma >= slow_ma
        if is_spread_pass: pass_count += 1
        criteria_checks.append({
            'param': f'Fast vs Slow MA ({fast_period}/{slow_period})',
            'target': 'Fast > Slow (Golden Structure)',
            'actual': f'Spread: {spread:+0.2f}% (₹{slow_ma:,.2f})',
            'status': 'BULLISH' if is_spread_pass else 'COMPRESSION'
        })

        # Check 3: Volume Multiple
        total_checks += 1
        is_vol_pass = vol_multiple >= vol_req
        if is_vol_pass: pass_count += 1
        criteria_checks.append({
            'param': 'Institutional Volume Multiple',
            'target': f'≥ {vol_req:.2f}x 20d Avg',
            'actual': f'{vol_multiple:.2f}x',
            'status': 'PASS' if is_vol_pass else 'NEUTRAL'
        })

        # Check 4: RSI Min
        total_checks += 1
        is_rsi_pass = rsi >= rsi_min
        if is_rsi_pass: pass_count += 1
        criteria_checks.append({
            'param': 'RSI Momentum Baseline',
            'target': f'≥ {rsi_min:.0f}',
            'actual': f'{rsi:.1f}',
            'status': 'PASS' if is_rsi_pass else 'OVERSOLD'
        })

        summary = (
            f"{ticker} trades at ₹{cmp:,.2f} ({dist_fast:+0.2f}% vs {fast_period} {ma_type} ₹{fast_ma:,.2f}). "
            f"The {fast_period}/{slow_period} spread is {spread:+0.2f}% with {vol_multiple:.2f}x volume expansion."
        )

    elif category == 'rsi_breakout':
        rsi_len = int(params.get('rsi_length', 14))
        rsi_thresh = float(params.get('rsi_threshold', 62))
        vol_req = float(params.get('volume_multiple', 1.5))

        deltas = df['close'].diff()
        gain = (deltas.where(deltas > 0, 0)).rolling(rsi_len).mean()
        loss = (-deltas.where(deltas < 0, 0)).rolling(rsi_len).mean()
        rs = gain / (loss + 1e-9)
        rsi_series = (100 - (100 / (1 + rs)))
        rsi = float(rsi_series.iloc[-1]) if len(df) >= rsi_len + 1 else 50.0
        rsi_prev5 = float(rsi_series.iloc[-6]) if len(df) >= rsi_len + 6 else rsi
        rsi_slope = rsi - rsi_prev5

        total_checks += 1
        is_rsi_pass = rsi >= rsi_thresh
        if is_rsi_pass: pass_count += 1
        criteria_checks.append({
            'param': f'RSI ({rsi_len}) Breakout',
            'target': f'≥ {rsi_thresh:.0f}',
            'actual': f'{rsi:.1f}',
            'status': 'PASS' if is_rsi_pass else ('NEAR' if rsi >= rsi_thresh - 5 else 'BELOW')
        })

        total_checks += 1
        is_vol_pass = vol_multiple >= vol_req
        if is_vol_pass: pass_count += 1
        criteria_checks.append({
            'param': 'Breakout Volume Expansion',
            'target': f'≥ {vol_req:.2f}x Avg',
            'actual': f'{vol_multiple:.2f}x',
            'status': 'PASS' if is_vol_pass else 'MODERATE'
        })

        total_checks += 1
        is_slope_pass = rsi_slope > 0
        if is_slope_pass: pass_count += 1
        criteria_checks.append({
            'param': '5-Day Momentum Velocity',
            'target': 'Rising Velocity (+)',
            'actual': f'{rsi_slope:+0.1f} pts',
            'status': 'PASS' if is_slope_pass else 'CONSOLIDATING'
        })

        total_checks += 1
        is_trend_pass = cmp >= sma200
        if is_trend_pass: pass_count += 1
        criteria_checks.append({
            'param': '200 SMA Trend Foundation',
            'target': 'Price > 200 SMA',
            'actual': f'₹{sma200:,.2f} ({((cmp - sma200)/sma200*100):+0.1f}%)',
            'status': 'PASS' if is_trend_pass else 'CAUTION'
        })

        summary = (
            f"RSI({rsi_len}) stands at {rsi:.1f} vs {rsi_thresh:.0f} target with {rsi_slope:+0.1f} 5-day delta. "
            f"Volume is clocking {vol_multiple:.2f}x the 20-day baseline."
        )

    elif category == 'macd_cross':
        fast_p = int(params.get('fast_period', 8))
        slow_p = int(params.get('slow_period', 21))
        sig_p = int(params.get('signal_period', 5))
        confirm_sma200 = bool(params.get('confirm_above_200_sma', True))

        ema_fast = df['close'].ewm(span=fast_p, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow_p, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        sig_line = macd_line.ewm(span=sig_p, adjust=False).mean()
        hist = macd_line - sig_line

        cur_macd = float(macd_line.iloc[-1])
        cur_sig = float(sig_line.iloc[-1])
        cur_hist = float(hist.iloc[-1])
        prev_hist = float(hist.iloc[-2]) if len(hist) >= 2 else cur_hist

        total_checks += 1
        is_cross_pass = cur_macd >= cur_sig
        if is_cross_pass: pass_count += 1
        criteria_checks.append({
            'param': f'MACD ({fast_p}/{slow_p}/{sig_p})',
            'target': 'MACD Line > Signal Line',
            'actual': f'{cur_macd:+0.2f} vs {cur_sig:+0.2f}',
            'status': 'BULLISH' if is_cross_pass else 'BEARISH'
        })

        total_checks += 1
        is_hist_pass = cur_hist > prev_hist
        if is_hist_pass: pass_count += 1
        criteria_checks.append({
            'param': 'Histogram Velocity',
            'target': 'Expanding (+)',
            'actual': f'{cur_hist:+0.2f} (prev: {prev_hist:+0.2f})',
            'status': 'EXPANDING' if is_hist_pass else 'CONTRACTING'
        })

        total_checks += 1
        is_sma_pass = (cmp >= sma200) if confirm_sma200 else True
        if is_sma_pass: pass_count += 1
        criteria_checks.append({
            'param': '200 SMA Trend Filter',
            'target': 'Above 200 SMA',
            'actual': f'₹{sma200:,.2f}',
            'status': 'PASS' if is_sma_pass else 'BELOW'
        })

        summary = (
            f"MACD({fast_p}/{slow_p}/{sig_p}) sits at {cur_macd:+0.2f} vs Signal {cur_sig:+0.2f} (Histogram {cur_hist:+0.2f}). "
            f"Trend is {'supported above' if cmp >= sma200 else 'below'} 200 SMA (₹{sma200:,.2f})."
        )

    elif category == 'volatility_squeeze':
        bb_period = int(params.get('bollinger_period', 20))
        kc_period = int(params.get('keltner_period', 20))
        
        sma_bb = df['close'].rolling(bb_period).mean()
        std_bb = df['close'].rolling(bb_period).std()
        bb_upper = sma_bb + (2 * std_bb)
        bb_lower = sma_bb - (2 * std_bb)
        bb_width = float(((bb_upper - bb_lower) / sma_bb).iloc[-1]) if len(df) >= bb_period else 0.1

        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift()).abs()
        tr3 = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = float(tr.rolling(14).mean().iloc[-1]) if len(df) >= 14 else float(tr.mean())

        total_checks += 1
        is_squeeze = bb_width < 0.12
        if is_squeeze: pass_count += 1
        criteria_checks.append({
            'param': f'Bollinger Bandwidth ({bb_period})',
            'target': 'Compression (< 12%)',
            'actual': f'{bb_width * 100:.1f}% width',
            'status': 'SQUEEZE' if is_squeeze else 'EXPANDING'
        })

        total_checks += 1
        is_atr_pass = atr14 > 0
        if is_atr_pass: pass_count += 1
        criteria_checks.append({
            'param': 'ATR(14) Volatility Buffer',
            'target': 'Active Volatility',
            'actual': f'₹{atr14:,.2f}',
            'status': 'STABLE'
        })

        summary = f"Bollinger Bandwidth is {bb_width * 100:.1f}% with ATR(14) volatility risk at ₹{atr14:,.2f}."

    else:  # pullback or custom
        trend_ema_p = int(params.get('trend_ema', 50))
        pullback_target = float(params.get('pullback_pct', 2.5))
        ema50 = float(df['close'].ewm(span=trend_ema_p, adjust=False).mean().iloc[-1])
        dist_ema = round(((cmp - ema50) / ema50) * 100, 2)

        total_checks += 1
        is_dist_pass = abs(dist_ema) <= pullback_target
        if is_dist_pass: pass_count += 1
        criteria_checks.append({
            'param': f'{trend_ema_p} EMA Support Level',
            'target': f'Within ±{pullback_target}%',
            'actual': f'₹{ema50:,.2f} ({dist_ema:+0.2f}%)',
            'status': 'PASS' if is_dist_pass else 'EXTENDED'
        })

        total_checks += 1
        is_sma_pass = cmp >= sma200
        if is_sma_pass: pass_count += 1
        criteria_checks.append({
            'param': '200 SMA Macro Trend',
            'target': 'Above 200 SMA',
            'actual': f'₹{sma200:,.2f}',
            'status': 'PASS' if is_sma_pass else 'BELOW'
        })

        summary = f"Price is {dist_ema:+0.2f}% from the {trend_ema_p} EMA (₹{ema50:,.2f}), anchored {'above' if cmp >= sma200 else 'below'} 200 SMA (₹{sma200:,.2f})."

    # Score out of 100
    score = int(round((pass_count / total_checks) * 100)) if total_checks > 0 else 75
    
    if score >= 75:
        overall_status = "QUALIFIED (High Confluence)"
    elif score >= 50:
        overall_status = "WATCHLIST (Partial Confluence)"
    else:
        overall_status = "CAUTION (Low Confluence)"

    return {
        'ticker': ticker,
        'strategy_name': strategy_name,
        'category': category,
        'parameters_used': params,
        'cmp': cmp,
        'status': overall_status,
        'match_score': score,
        'pass_count': pass_count,
        'total_checks': total_checks,
        'criteria_checks': criteria_checks,
        'analysis_summary': summary
    }
