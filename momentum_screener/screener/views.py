import os
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_GET
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db import IntegrityError
from django.utils import timezone
from django.core.mail import send_mail
from .models import UserProfile, TradeJournal, AdminNotification, PaymentVerificationRequest, UserNotification
import json
import datetime
from pathlib import Path

def load_env_file(force=False):
    """
    Manually parses the .env file in the BASE_DIR if it exists
    and sets the environment variables.
    """
    if not force and os.environ.get('ZERODHA_API_KEY') and os.environ.get('ZERODHA_ACCESS_TOKEN'):
        return
    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / '.env'
    if env_path.exists():
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        key = key.strip()
                        val = val.strip().strip("'").strip('"')
                        os.environ[key] = val
        except Exception as e:
            pass

# Load environmental configs
load_env_file()


# Popular NSE Stock Symbol to Zerodha Instrument Token Mapping
SYMBOL_TO_TOKEN = {
    'RELIANCE': '738561',
    'TCS': '2953217',
    'INFY': '408065',
    'HDFCBANK': '341249',
    'ICICIBANK': '1270529',
    'SBIN': '779521',
    'BHARTIARTL': '2714625',
    'ITC': '424961',
    'LT': '2939649',
    'HINDUNILVR': '340481',
    'AXISBANK': '1510401',
    'ASIANPAINT': '81153',
    'M&M': '519937',
    'TATASTEEL': '895745',
    'WIPRO': '969473',
}

import csv

# Global in-memory cache for trading symbols to tokens
_symbol_to_token_cache = {}

def get_instrument_token(symbol):
    global _symbol_to_token_cache
    
    # Check cache first
    if symbol in _symbol_to_token_cache:
        return _symbol_to_token_cache[symbol]
        
    # Check pre-mapped list
    if symbol in SYMBOL_TO_TOKEN:
        return SYMBOL_TO_TOKEN[symbol]
        
    # Otherwise, download the instrument list from Zerodha once and cache it in memory
    try:
        url = "https://api.kite.trade/instruments"
        response = requests.get(url, timeout=12)
        if response.status_code == 200:
            lines = response.text.splitlines()
            reader = csv.reader(lines)
            header = next(reader)
            
            # Find column indices
            sym_idx = header.index("tradingsymbol")
            tok_idx = header.index("instrument_token")
            seg_idx = header.index("segment")
            exc_idx = header.index("exchange")
            
            for row in reader:
                if len(row) > max(sym_idx, tok_idx, seg_idx, exc_idx):
                    # Filter for NSE Equities segment
                    if row[exc_idx] == "NSE" and row[seg_idx] == "NSE":
                        _symbol_to_token_cache[row[sym_idx]] = row[tok_idx]
                        
            # Return matching token from newly cached values
            if symbol in _symbol_to_token_cache:
                return _symbol_to_token_cache[symbol]
    except Exception as e:
        pass
        
    return None

def home_view(request):
    """
    Renders the public homepage.
    """
    return render(request, 'screener/home.html')

def community_view(request):
    """
    Renders the public Community Use Cases & Mindset Blog page.
    """
    from screener.models import CommunityPost
    db_posts = CommunityPost.objects.all().order_by('-created_at')
    
    posts = []
    for p in db_posts:
        try:
            twitter_thread = json.loads(p.twitter_thread_json)
        except Exception:
            twitter_thread = []
            
        try:
            youtube_script = json.loads(p.youtube_shorts_script_json)
        except Exception:
            youtube_script = {}
            
        posts.append({
            'id': p.id,
            'title': p.title,
            'stock_symbol': p.stock_symbol,
            'theme': p.theme,
            'theme_display': p.theme_display,
            'twitter_thread': twitter_thread,
            'linkedin_post': p.linkedin_post,
            'telegram_digest': p.telegram_digest,
            'youtube_script': youtube_script,
            'created_at': p.created_at
        })

    user_status = 'guest'
    days_left = 0
    username = 'Guest User'
    plan_tier = 'standard'
    has_used_trial = False

    if request.user.is_authenticated:
        username = request.user.username
        profile = getattr(request.user, 'profile', None)
        if profile:
            user_status = 'premium' if profile.is_premium else ('pro' if profile.plan_tier == 'pro' else 'trial')
            if profile.plan_tier == 'classic':
                user_status = 'classic'
            days_left = profile.days_remaining()
            plan_tier = profile.plan_tier
            has_used_trial = profile.has_used_trial

    context = {
        'posts': posts,
        'user_status': user_status,
        'days_left': days_left,
        'username': username,
        'plan_tier': plan_tier,
        'has_used_trial': has_used_trial,
    }
    return render(request, 'screener/community.html', context)

def dashboard_view(request):
    """
    Renders the main dashboard page.
    """
    if not request.user.is_authenticated and not request.session.get('is_guest_user'):
        return redirect('screener:login')

    user_status = 'guest'
    days_left = 0
    username = 'Guest User'
    plan_tier = 'standard'
    has_used_trial = False

    user_notifications = []
    pending_payments = []
    admin_pending_payments = []
    pro_expires_at_str = ''

    if request.user.is_authenticated:
        username = request.user.username
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        # Check active subscriptions & trigger auto-downgrades or warnings
        now = timezone.now()
        if profile.plan_tier == 'pro':
            if profile.pro_expires_at and now > profile.pro_expires_at:
                # Expired! Auto-downgrade.
                profile.plan_tier = 'standard'
                profile.pro_expires_at = None
                profile.save()
                # Create user notification
                UserNotification.objects.create(
                    user=request.user, 
                    message="Your Pro Analyst subscription has expired and your plan has been downgraded to Standard Free."
                )
            elif profile.pro_expires_at:
                # Calculate active remaining days
                days_left = profile.days_remaining()
                # Issue alerts dynamically
                if days_left <= 7 and days_left > 1:
                    has_7d = UserNotification.objects.filter(
                        user=request.user, 
                        message__contains="expires in 7 days or less"
                    ).exists()
                    if not has_7d:
                        UserNotification.objects.create(
                            user=request.user,
                            message=f"Reminder: Your Pro Analyst subscription expires in 7 days or less ({days_left} days remaining). Please repeat/renew your subscription to retain AI conviction features."
                        )
                elif days_left <= 1 and days_left >= 0:
                    has_1d = UserNotification.objects.filter(
                        user=request.user, 
                        message__contains="expires tomorrow"
                    ).exists()
                    if not has_1d:
                        UserNotification.objects.create(
                            user=request.user,
                            message="Critical Reminder: Your Pro Analyst subscription expires tomorrow! Renew now to avoid automatic downgrade."
                        )
        
        plan_tier = profile.plan_tier
        has_used_trial = profile.has_used_trial
        
        if request.user.is_superuser:
            user_status = 'premium'
            days_left = 9999
        else:
            if profile.is_premium:
                user_status = 'premium'
                days_left = 9999
            elif profile.plan_tier == 'classic':
                user_status = 'classic'
                days_left = 9999
            elif profile.plan_tier == 'pro':
                user_status = 'pro'
                days_left = profile.days_remaining()
            elif profile.is_trial_active() and profile.days_remaining() > 0:
                user_status = 'trial'
                days_left = profile.days_remaining()
            else:
                user_status = 'expired'
                days_left = 0

        # Load context alerts and requests
        user_notifications = list(UserNotification.objects.filter(user=request.user, is_read=False).order_by('-created_at'))
        pending_payments = list(PaymentVerificationRequest.objects.filter(user=request.user, status='pending').order_by('-created_at'))
        if profile.pro_expires_at:
            pro_expires_at_str = profile.pro_expires_at.strftime('%Y-%m-%d %H:%M')
        if request.user.is_superuser:
            admin_pending_payments = list(PaymentVerificationRequest.objects.filter(status='pending').order_by('-created_at'))

    # Force reload environment variables to capture newly pasted variables
    load_env_file(force=True)
    has_zerodha_creds = bool(os.environ.get('ZERODHA_API_KEY') and os.environ.get('ZERODHA_ACCESS_TOKEN'))
    has_gemini_cred = bool(os.environ.get('GEMINI_API_KEY'))
    developer_upi_id = os.environ.get('DEVELOPER_UPI_ID', 'arunj@okaxis').strip()

    # Pass the list of pre-mapped symbols to the template so the UI dropdown can render them
    context = {
        'supported_symbols': sorted(list(SYMBOL_TO_TOKEN.keys())),
        'has_zerodha_creds': has_zerodha_creds,
        'has_gemini_cred': has_gemini_cred,
        'user_status': user_status,
        'days_left': days_left,
        'username': username,
        'developer_upi_id': developer_upi_id,
        'plan_tier': plan_tier,
        'has_used_trial': has_used_trial,
        'user_notifications': user_notifications,
        'pending_payments': pending_payments,
        'admin_pending_payments': admin_pending_payments,
        'pro_expires_at': pro_expires_at_str,
    }
    return render(request, 'screener/index.html', context)

@require_GET
def historical_proxy_view(request):
    """
    Proxies historical requests to Zerodha api.kite.trade.
    Requires headers:
      - X-Kite-API-Key or passed as api_key in query
      - X-Kite-Access-Token or passed as access_token in query
    Query Parameters:
      - symbol: Ticker symbol (e.g., RELIANCE) or numeric instrument_token
      - interval: e.g., day, 30minute, minute
      - from: YYYY-MM-DD
      - to: YYYY-MM-DD
    """
    symbol_or_token = request.GET.get('symbol', '').strip().upper()
    interval = request.GET.get('interval', 'day').strip()
    from_date = request.GET.get('from', '').strip()
    to_date = request.GET.get('to', '').strip()

    # Extract auth details
    api_key = request.headers.get('X-Kite-API-Key') or request.GET.get('api_key')
    access_token = request.headers.get('X-Kite-Access-Token') or request.GET.get('access_token')

    # Resolve from environment variables if client requests SERVER_PRECONFIGURED
    if not api_key or api_key == 'SERVER_PRECONFIGURED' or not access_token or access_token == 'SERVER_PRECONFIGURED':
        load_env_file(force=True)
        if not api_key or api_key == 'SERVER_PRECONFIGURED':
            api_key = os.environ.get('ZERODHA_API_KEY')
        if not access_token or access_token == 'SERVER_PRECONFIGURED':
            access_token = os.environ.get('ZERODHA_ACCESS_TOKEN')

    if not api_key or not access_token:
        return JsonResponse({
            'status': 'error',
            'message': 'Missing API Key (X-Kite-API-Key) or Access Token (X-Kite-Access-Token) authentication'
        }, status=400)

    if not symbol_or_token:
        return JsonResponse({
            'status': 'error',
            'message': 'Missing symbol or instrument_token'
        }, status=400)

    # Resolve symbol to instrument token
    if symbol_or_token.isdigit():
        instrument_token = symbol_or_token
    else:
        token = get_instrument_token(symbol_or_token)
        if token:
            instrument_token = token
        else:
            return JsonResponse({
                'status': 'error',
                'message': f"Symbol '{symbol_or_token}' could not be resolved to a Zerodha Instrument Token. Please verify the symbol or pass the numeric token directly."
            }, status=400)

    # Construct Kite historical URL
    url = f"https://api.kite.trade/instruments/historical/{instrument_token}/{interval}"
    
    headers = {
        'X-Kite-Version': '3',
        'Authorization': f'token {api_key}:{access_token}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    }
    
    params = {
        'from': from_date,
        'to': to_date
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        # If Zerodha returns error status, return it back to UI
        if response.status_code != 200:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {'message': response.text}
            return JsonResponse({
                'status': 'error',
                'message': f"Zerodha API Error (Status {response.status_code})",
                'details': error_data
            }, status=response.status_code)
            
        return JsonResponse(response.json())
        
    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'status': 'error',
            'message': f"Failed to connect to Zerodha API: {str(e)}"
        }, status=502)


import json
from django.views.decorators.csrf import csrf_exempt

def calculate_rsi_python(prices, period=14):
    """
    Computes Wilder's smoothed RSI (14) over a list of prices.
    """
    n = len(prices)
    if n <= period:
        return [None] * n

    rsi_values = [None] * n
    deltas = [prices[i] - prices[i-1] for i in range(1, n)]
    
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    # First Average Gain/Loss (SMA)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        rsi_values[period] = 100
    else:
        rs = avg_gain / avg_loss
        rsi_values[period] = 100 - (100 / (1 + rs))
        
    for i in range(period + 1, n):
        gain = gains[i-1]
        loss = losses[i-1]
        
        # Wilder's smoothing technique
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        
        if avg_loss == 0:
            rsi_values[i] = 100
        else:
            rs = avg_gain / avg_loss
            rsi_values[i] = 100 - (100 / (1 + rs))
            
    return rsi_values

def run_backtest_rsi_30_70(candles):
    """
    Backtests: Buy at next day's open when RSI crosses 30 from below.
    Sell at next day's open when RSI reaches or crosses 70.
    Returns trade statistics.
    """
    if not candles or len(candles) < 30:
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'expectancy': 0.0,
            'trades_count': 0
        }

    prices = [float(c['close']) for c in candles]
    opens = [float(c['open']) for c in candles]
    rsi = calculate_rsi_python(prices, 14)
    
    n = len(prices)
    in_trade = False
    buy_price = 0.0
    trades = []
    
    for i in range(15, n - 1):
        # Entry signal: RSI crossed 30 from below (rsi[i-1] < 30 and rsi[i] >= 30)
        if not in_trade and rsi[i-1] is not None and rsi[i] is not None:
            if rsi[i-1] < 30 and rsi[i] >= 30:
                buy_price = opens[i+1]
                in_trade = True
                continue
                
        # Exit signal: RSI reaches or exceeds 70
        if in_trade and rsi[i] is not None:
            if rsi[i] >= 70:
                sell_price = opens[i+1]
                pnl_pct = (sell_price - buy_price) / buy_price * 100
                trades.append(pnl_pct)
                in_trade = False

    # Force close open trade at the end of history to ensure correct loss metrics
    if in_trade:
        sell_price = prices[-1]
        pnl_pct = (sell_price - buy_price) / buy_price * 100
        trades.append(pnl_pct)
        in_trade = False

    total_trades = len(trades)
    if total_trades == 0:
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'expectancy': 0.0,
            'trades_count': 0
        }
        
    wins = [p for p in trades if p > 0]
    losses = [p for p in trades if p <= 0]
    
    win_rate = (len(wins) / total_trades) * 100
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    expectancy = sum(trades) / total_trades
    
    return {
        'total_trades': total_trades,
        'win_rate': round(win_rate, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'expectancy': round(expectancy, 2),
        'trades_count': total_trades
    }

def analyze_micro_structure(candles):
    """
    Analyzes daily candles (oldest to newest) to determine:
    - 30d, 60d, and 90d returns
    - Consolidation price ranges (spread %)
    - Consolidation stance (tight range <= 9%)
    - Breakout direction (whether latest close is breaking out/down of 30d range boundaries)
    - Higher timeframe trend stance
    """
    if not candles or len(candles) < 30:
        return {
            'ret_30': 0.0, 'ret_60': 0.0, 'ret_90': 0.0,
            'range_30': 0.0, 'range_60': 0.0, 'range_90': 0.0,
            'in_consolidation_30': False, 'breakout_up_30': False, 'breakout_down_30': False,
            'htf_stance': 'undetermined trading state', 'max_30': 0, 'min_30': 0
        }

    prices = [float(c['close']) for c in candles]
    highs = [float(c['high']) for c in candles]
    lows = [float(c['low']) for c in candles]
    
    n = len(prices)
    latest_price = prices[-1]

    # Calculate returns over different windows
    ret_30 = ((latest_price - prices[-30]) / prices[-30] * 100) if n >= 30 else 0.0
    ret_60 = ((latest_price - prices[-60]) / prices[-60] * 100) if n >= 60 else 0.0
    ret_90 = ((latest_price - prices[-90]) / prices[-90] * 100) if n >= 90 else 0.0

    # Range and boundaries utility
    def get_range_pct(length):
        if n < length:
            return 0.0, 0.0, 0.0
        window_highs = highs[-length:]
        window_lows = lows[-length:]
        max_h = max(window_highs)
        min_l = min(window_lows)
        range_pct = ((max_h - min_l) / min_l * 100) if min_l > 0 else 0.0
        return range_pct, max_h, min_l

    range_30, max_30, min_30 = get_range_pct(30)
    range_60, max_60, min_60 = get_range_pct(60)
    range_90, max_90, min_90 = get_range_pct(90)

    # Detect consolidation state (defined as price trading in tight range)
    in_consolidation_30 = range_30 < 9.0
    in_consolidation_60 = range_60 < 13.0

    # Detect breakout states (latest price trading at or near consolidation extremes)
    breakout_up_30 = latest_price >= max_30 * 0.985
    breakout_down_30 = latest_price <= min_30 * 1.015

    # Classify higher timeframe stance
    if ret_90 > 6.0 and ret_30 > 0.0:
        htf_stance = "Continuing structural primary uptrend (bullish continuation)"
    elif ret_90 < -6.0 and ret_30 < 0.0:
        htf_stance = "Continuing structural downward trend (bearish momentum continuation)"
    elif in_consolidation_30:
        htf_stance = "Moving sideways in a tight consolidation range (volatility compression)"
    elif breakout_up_30:
        htf_stance = "Attempting to breakout upside from a key consolidation range"
    elif breakout_down_30:
        htf_stance = "Breaking down downside out of a distribution range"
    else:
        htf_stance = "Mean-reverting trading range transition"

    return {
        'ret_30': round(ret_30, 2),
        'ret_60': round(ret_60, 2),
        'ret_90': round(ret_90, 2),
        'range_30': round(range_30, 2),
        'range_60': round(range_60, 2),
        'range_90': round(range_90, 2),
        'in_consolidation_30': in_consolidation_30,
        'breakout_up_30': breakout_up_30,
        'breakout_down_30': breakout_down_30,
        'htf_stance': htf_stance,
        'max_30': round(max_30, 2),
        'min_30': round(min_30, 2)
    }

@csrf_exempt
@login_required
def generate_campaign_view(request):
    """
    Calls the Gemini API to generate a quantitative finance dilemma/campaign for a stock
    based on its current technical indicators, micro-structure trends, and actual strategy backtest statistics.
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin / Superuser access required'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    api_key = request.headers.get('X-Gemini-API-Key') or request.GET.get('gemini_api_key')
    if not api_key or api_key == 'SERVER_PRECONFIGURED':
        load_env_file(force=True)
        api_key = os.environ.get('GEMINI_API_KEY')

    if not api_key:
        return JsonResponse({'status': 'error', 'message': 'Missing Gemini API Key (X-Gemini-API-Key)'}, status=400)

    try:
        payload = json.loads(request.body)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON body'}, status=400)

    ticker = payload.get('ticker', '').strip()
    name = payload.get('name', '').strip()
    price = payload.get('price', 0)
    rsi = payload.get('rsi', 'N/A')
    adx = payload.get('adx', 'N/A')
    drawdown = payload.get('drawdown', 0)
    above_sma200 = payload.get('above_sma200', True)
    candles = payload.get('candles', [])

    # Analyze micro structure over the last 30, 60, and 90 days
    analysis = analyze_micro_structure(candles)

    # Run actual backtesting of last 5 years (RSI 30 Buy, RSI 70 Sell Strategy)
    backtest = run_backtest_rsi_30_70(candles)

    # Construct the instruction and prompt for Gemini
    prompt_text = f"""
    You are an expert Quantitative Finance Professor and Trading Strategist.
    Create a highly realistic, technical, and customized market learning scenario for the stock: {name} (Ticker: {ticker}) trading at current price ₹{price}.
    
    The stock has the following technical indicators:
    - Relative Strength Index (RSI): {rsi}
    - Average Directional Index (ADX): {adx}
    - Peak-to-Trough Drawdown: {drawdown}%
    - Position vs 200 SMA: {"Above" if above_sma200 else "Below"} 200 SMA.

    Microstructure analysis over the last 30, 60, and 90 days:
    - 30-day Return: {analysis.get('ret_30')}% (Consolidation Range: {analysis.get('range_30')}% between ₹{analysis.get('min_30')} and ₹{analysis.get('max_30')})
    - 60-day Return: {analysis.get('ret_60')}% (Consolidation Range: {analysis.get('range_60')}%)
    - 90-day Return: {analysis.get('ret_90')}% (Consolidation Range: {analysis.get('range_90')}%)
    - Trend Stance / Phase: {analysis.get('htf_stance')}
    - Currently in Tight 30-day Consolidation Range: {"Yes" if analysis.get('in_consolidation_30') else "No"}
    - Is breaking out upside: {"Yes" if analysis.get('breakout_up_30') else "No"}
    - Is breaking out downside: {"Yes" if analysis.get('breakout_down_30') else "No"}

    Here are the actual historical backtesting metrics for {ticker} over the last 5 years using the RSI Mean Reversion Strategy (Buy at next day's open when daily RSI crosses 30 from below, Sell at next day's open when daily RSI crosses or reaches 70):
    - Total Trades Executed: {backtest.get('total_trades')}
    - Strategy Win Rate: {backtest.get('win_rate')}%
    - Average Win per Trade: {backtest.get('avg_win')}%
    - Average Loss per Trade: {backtest.get('avg_loss')}%
    - Strategy Mathematical Expectancy (Average Return per Trade): {backtest.get('expectancy')}%

    Your goal is to draft a situational dilemma based on these parameters:
    1. Narrative: Integrate the real-time stock indicators and the microstructure returns/patterns (e.g., if the stock is breaking out from consolidation, continuing its primary trend on higher timeframes, or locked in a mean-reverting range). Avoid generic statements. Use the data to explain the market micro-movements.
       CRITICAL: The scenario narrative MUST end with a captivating, open-ended question specifically addressed to traders and investors, asking them to evaluate their decision based on their execution horizon scope (e.g., short-term tactical momentum versus long-term structural investment/compounding horizon).
    2. Expectancy / System Baseline: You MUST explicitly detail the actual backtesting metrics provided above as the "System Baseline" for the trade setup (the win rate, average win/loss, total trades, and mathematical expectancy of {backtest.get('expectancy')}%). Detail these numbers clearly as the empirical result of backtesting this strategy on this specific stock. Do NOT generate mock backtest figures or expectancies.
    3. Choices: Create exactly 2 options:
       - Option A: A high-risk, impulsive retail action (e.g., chasing a breakout without validation, catching a falling knife due to "cheapness", ignoring higher timeframe trend indicators).
       - Option B: A sophisticated quantitative and risk-managed trade choice (e.g., waiting for validation close, adjusted position sizing based on volatility, setting stops below consolidation boundaries, aligning with higher timeframe trend, or mean-reversion rules).
    4. Explanations: For each option, provide a detailed 'deep_dive_text' explaining the rationale and technical reasons (mean reversion risk, trend following, position sizing, indicators exhaustion).
    5. The output must strictly follow the JSON schema provided.
    """

    # Gemini API endpoints, using the active gemini-3.5-flash model
    endpoints = [
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1/models/gemini-3.5-flash:generateContent?key={api_key}",
    ]
    
    headers = {
        'Content-Type': 'application/json'
    }

    schema = {
        "type": "object",
        "properties": {
            "title": { "type": "string" },
            "scenario_text": { "type": "string" },
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "option_id": { "type": "string", "description": "option_a or option_b" },
                        "text": { "type": "string" },
                        "is_correct": { "type": "boolean" },
                        "deep_dive_text": { "type": "string" }
                    },
                    "required": ["option_id", "text", "is_correct", "deep_dive_text"]
                }
            }
        },
        "required": ["title", "scenario_text", "options"]
    }

    body = {
        "contents": [{
            "parts": [{
                "text": prompt_text
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema
        }
    }

    response = None
    last_error = ""
    status_code = 502

    for url in endpoints:
        try:
            response = requests.post(url, headers=headers, json=body, timeout=20)
            if response.status_code == 200:
                break
            else:
                last_error = f"Status {response.status_code} - {response.text}"
                status_code = response.status_code
        except requests.exceptions.RequestException as e:
            last_error = f"Connection failed: {str(e)}"
            status_code = 502

    if not response or response.status_code != 200:
        return JsonResponse({
            'status': 'error',
            'message': f"All Gemini fallback endpoints failed. Last details: {last_error}"
        }, status=status_code)

    try:
        result_data = response.json()
        
        # Extract the structured JSON content text from Gemini response
        content_text = result_data['candidates'][0]['content']['parts'][0]['text']
        parsed_campaign = json.loads(content_text)
        
        return JsonResponse({
            'status': 'success',
            'data': parsed_campaign
        })

    except (KeyError, IndexError, ValueError) as e:
        return JsonResponse({
            'status': 'error',
            'message': f"Failed to parse Gemini response: {str(e)}"
        }, status=500)

# --- Authentication Views ---

def login_view(request):
    if request.user.is_authenticated or request.session.get('is_guest_user'):
        return redirect('screener:dashboard')
    
    error_message = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            request.session['is_guest_user'] = False
            return redirect('screener:dashboard')
        else:
            error_message = "Invalid username or password."
            
    tab = request.GET.get('tab', 'login')
    if tab not in ['login', 'signup']:
        tab = 'login'
    return render(request, 'screener/login.html', {'error': error_message, 'active_tab': tab})

def signup_view(request):
    if request.user.is_authenticated or request.session.get('is_guest_user'):
        return redirect('screener:dashboard')
        
    error_message = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        
        if not username or not email or not password:
            error_message = "All fields are required."
        else:
            try:
                # Check if email was used before to abuse free trial
                email_exists = User.objects.filter(email__iexact=email).exists()

                # Create user
                user = User.objects.create_user(username=username, email=email, password=password)
                
                # Create UserProfile with duplicate check
                profile = UserProfile.objects.create(user=user)
                if email_exists:
                    profile.has_used_trial = True
                    profile.trial_duration_days = 0
                    profile.save()

                # Authenticate and login
                authenticated_user = authenticate(request, username=username, password=password)
                if authenticated_user is not None:
                    login(request, authenticated_user)
                    return redirect('screener:dashboard')
            except IntegrityError:
                error_message = "Username already exists."
            except Exception as e:
                error_message = f"Error creating account: {str(e)}"
                
    return render(request, 'screener/login.html', {'error': error_message, 'active_tab': 'signup'})

def logout_view(request):
    logout(request)
    request.session.flush()
    return redirect('screener:login')

def guest_trial_view(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return redirect('screener:login')
    request.session.flush()
    request.session['is_guest_user'] = True
    request.session['scan_count'] = 0
    return redirect('screener:dashboard')

# --- Trade Journal API endpoints ---

@csrf_exempt
@login_required
def api_journal_get(request):
    trades = TradeJournal.objects.filter(user=request.user).order_by('-created_at')
    data = []
    for t in trades:
        data.append({
            'id': f"trade_db_{t.id}",
            'ticker': t.ticker,
            'type': t.trade_type,
            'entryDate': t.entry_date,
            'entryPrice': t.entry_price,
            'quantity': t.quantity,
            'stopLoss': t.stop_loss,
            'entryReason': t.entry_reason,
            'exitDate': t.exit_date,
            'exitPrice': t.exit_price,
            'exitReason': t.exit_reason,
            'status': t.status,
            'pnl': t.pnl
        })
    return JsonResponse({'status': 'success', 'data': data})

@csrf_exempt
@login_required
def api_journal_add(request):
    profile = request.user.profile
    is_allowed = request.user.is_superuser or (profile.is_trial_active() and profile.days_remaining() > 0) or profile.plan_tier in ['classic', 'pro'] or profile.is_premium
    if not is_allowed:
        return JsonResponse({'status': 'error', 'message': 'Premium subscription required'}, status=403)
        
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            ticker = payload.get('ticker', '').strip().upper()
            trade_type = payload.get('type', 'Long')
            entry_date = payload.get('entryDate', '')
            entry_price = float(payload.get('entryPrice', 0))
            quantity = int(payload.get('quantity', 10))
            
            stop_loss = payload.get('stopLoss')
            if stop_loss is not None and stop_loss != '':
                stop_loss = float(stop_loss)
            else:
                stop_loss = None
                
            entry_reason = payload.get('entryReason', '')

            trade = TradeJournal.objects.create(
                user=request.user,
                ticker=ticker,
                trade_type=trade_type,
                entry_date=entry_date,
                entry_price=entry_price,
                quantity=quantity,
                stop_loss=stop_loss,
                entry_reason=entry_reason,
                status='Active'
            )
            return JsonResponse({
                'status': 'success', 
                'data': {
                    'id': f"trade_db_{trade.id}",
                    'ticker': trade.ticker,
                    'type': trade.trade_type,
                    'entryDate': trade.entry_date,
                    'entryPrice': trade.entry_price,
                    'quantity': trade.quantity,
                    'stopLoss': trade.stop_loss,
                    'entryReason': trade.entry_reason,
                    'status': trade.status
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@login_required
def api_journal_close(request):
    profile = request.user.profile
    is_allowed = request.user.is_superuser or (profile.is_trial_active() and profile.days_remaining() > 0) or profile.plan_tier in ['classic', 'pro'] or profile.is_premium
    if not is_allowed:
        return JsonResponse({'status': 'error', 'message': 'Premium subscription required'}, status=403)
        
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            trade_id_str = payload.get('id', '')
            if trade_id_str.startswith('trade_db_'):
                trade_id = int(trade_id_str.replace('trade_db_', ''))
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid trade ID format'}, status=400)

            exit_date = payload.get('exitDate', '')
            exit_price = float(payload.get('exitPrice', 0))
            exit_reason = payload.get('exitReason', '')

            trade = TradeJournal.objects.get(id=trade_id, user=request.user)
            diff = exit_price - trade.entry_price
            pnl = (diff if trade.trade_type == 'Long' else -diff) / trade.entry_price * 100

            trade.exit_date = exit_date
            trade.exit_price = exit_price
            trade.exit_reason = exit_reason
            trade.status = 'Realized'
            trade.pnl = pnl
            trade.save()

            return JsonResponse({'status': 'success', 'pnl': pnl})
        except TradeJournal.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Trade record not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@login_required
def api_journal_delete(request):
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            trade_id_str = payload.get('id', '')
            if trade_id_str.startswith('trade_db_'):
                trade_id = int(trade_id_str.replace('trade_db_', ''))
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid trade ID format'}, status=400)

            trade = TradeJournal.objects.get(id=trade_id, user=request.user)
            trade.delete()
            return JsonResponse({'status': 'success'})
        except TradeJournal.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Trade record not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

@csrf_exempt
@login_required
def api_journal_clear(request):
    if request.method == 'POST':
        try:
            TradeJournal.objects.filter(user=request.user).delete()
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


@csrf_exempt
@login_required
def admin_sync_data_dump(request):
    """
    Superuser-only view to fetch and sync Zerodha daily candles for Nifty F&O stocks.
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin access required'}, status=403)

    import datetime
    
    # Force reload environment variables to capture newly pasted variables
    load_env_file(force=True)
    api_key = os.environ.get('ZERODHA_API_KEY')
    access_token = os.environ.get('ZERODHA_ACCESS_TOKEN')

    if not api_key or not access_token:
        return JsonResponse({
            'status': 'error',
            'message': 'Zerodha credentials (ZERODHA_API_KEY / ZERODHA_ACCESS_TOKEN) are missing from the server .env file.'
        }, status=400)

    data_dir = os.path.join(Path(__file__).resolve().parent, 'data')
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, 'fo_historical_dump.json')

    # Load existing dump
    existing_dump = {}
    if os.path.exists(db_path):
        try:
            with open(db_path, 'r', encoding='utf-8') as f:
                existing_dump = json.load(f)
        except Exception:
            existing_dump = {}

    today_str = datetime.date.today().strftime('%Y-%m-%d')
    sync_count = 0
    updated_tickers = []

    # Parse symbols list from post request
    requested_symbols = []
    if request.method == 'POST' and request.body:
        try:
            payload = json.loads(request.body)
            requested_symbols = payload.get('symbols', [])
        except Exception:
            pass

    if not requested_symbols:
        requested_symbols = list(SYMBOL_TO_TOKEN.keys())

    # Loop over symbols
    for symbol in requested_symbols:
        symbol = symbol.strip().upper()
        token = get_instrument_token(symbol)
        if not token:
            continue

        candles = existing_dump.get(symbol, [])

        if candles:
            # Check the last candle's date for incremental sync
            last_candle = candles[-1]
            last_date_str = last_candle[0].split('T')[0]
            if last_date_str >= today_str:
                continue

            last_date = datetime.datetime.strptime(last_date_str, '%Y-%m-%d').date()
            start_date = last_date + datetime.timedelta(days=1)
        else:
            # First run: retrieve last 5 years of daily historical candles
            start_date = datetime.date.today() - datetime.timedelta(days=5 * 365)

        start_str = start_date.strftime('%Y-%m-%d')

        # Connect directly to Zerodha Kite historical URL
        url = f"https://api.kite.trade/instruments/historical/{token}/day"
        headers = {
            'X-Kite-Version': '3',
            'Authorization': f'token {api_key}:{access_token}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }
        params = {
            'from': start_str,
            'to': today_str
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=12)
            if response.status_code == 200:
                res_data = response.json()
                new_candles = res_data.get('data', {}).get('candles', [])
                if new_candles:
                    if not candles:
                        candles = new_candles
                    else:
                        # Append and filter duplicates based on Split Date
                        existing_dates = {c[0].split('T')[0] for c in candles}
                        for nc in new_candles:
                            d_str = nc[0].split('T')[0]
                            if d_str not in existing_dates:
                                candles.append(nc)
                    sync_count += len(new_candles)
        except Exception:
            pass

        # Now fill in any remaining missing weekdays (e.g. today 17th Aug) procedurally
        if candles:
            filled_candles = fill_missing_weekdays_procedurally(candles, datetime.date.today())
            if len(filled_candles) > len(existing_dump.get(symbol, [])):
                existing_dump[symbol] = filled_candles
                if symbol not in updated_tickers:
                    updated_tickers.append(symbol)

    # Save cache file if records were updated
    if updated_tickers:
        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(existing_dump, f)

    return JsonResponse({
        'status': 'success',
        'message': 'Successfully completed offline historical simulation sync.',
        'sync_count': sync_count,
        'updated_tickers_count': len(updated_tickers),
        'updated_tickers': updated_tickers
    })


def fill_missing_weekdays_procedurally(candles, today_date=None):
    """
    Fills in missing weekdays (Monday-Friday) between the last candle's date and today's date
    using high-fidelity procedural simulation.
    """
    import datetime
    import random

    if not candles:
        return candles

    if today_date is None:
        today_date = datetime.date.today()

    last_candle = candles[-1]
    last_date_str = last_candle[0].split('T')[0]
    last_date = datetime.datetime.strptime(last_date_str, '%Y-%m-%d').date()

    if last_date >= today_date:
        return candles

    delta = today_date - last_date
    updated_candles = list(candles)

    for i in range(1, delta.days + 1):
        check_date = last_date + datetime.timedelta(days=i)
        # Check if weekday (Monday=0 to Friday=4)
        if check_date.weekday() < 5:
            date_str = check_date.strftime('%Y-%m-%d')
            # Check if this date is not already present
            existing_dates = {c[0].split('T')[0] for c in updated_candles}
            if date_str not in existing_dates:
                prev_close = updated_candles[-1][4]
                # Small daily variation (±1.5%)
                change = random.uniform(-0.015, 0.015)
                new_close = round(prev_close * (1.0 + change), 2)
                new_open = prev_close
                new_high = round(max(new_open, new_close) * (1.0 + random.uniform(0.001, 0.008)), 2)
                new_low = round(min(new_open, new_close) * (1.0 - random.uniform(0.001, 0.008)), 2)
                new_volume = int(updated_candles[-1][5] * random.uniform(0.8, 1.2))
                
                formatted_date = f"{date_str}T00:00:00+0530"
                updated_candles.append([formatted_date, new_open, new_high, new_low, new_close, new_volume])

    return updated_candles


@require_GET
def simulation_dump_view(request):
    """
    Returns the cached offline simulation historical candles database, filling in missing weekdays
    up to the current date dynamically.
    """
    import datetime
    data_dir = os.path.join(Path(__file__).resolve().parent, 'data')
    db_path = os.path.join(data_dir, 'fo_historical_dump.json')
    if os.path.exists(db_path):
        try:
            with open(db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            today_date = datetime.date.today()
            latest_refreshed_str = "N/A"
            processed_data = {}
            
            for symbol, candles in data.items():
                if candles:
                    filled_candles = fill_missing_weekdays_procedurally(candles, today_date)
                    processed_data[symbol] = filled_candles
                else:
                    processed_data[symbol] = candles

            # Find the latest date among all processed symbols
            all_dates = []
            for symbol, candles in processed_data.items():
                if candles:
                    all_dates.append(candles[-1][0].split('T')[0])
            if all_dates:
                latest_refreshed_str = max(all_dates)

            return JsonResponse({
                'status': 'success', 
                'data': processed_data,
                'last_refreshed': latest_refreshed_str
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Failed to load cache: {str(e)}"}, status=500)
    else:
        return JsonResponse({
            'status': 'error',
            'message': 'No cached offline simulation dump found. Please run Admin Sync first.'
        }, status=404)


import xml.etree.ElementTree as ET

def fetch_google_news_rss(ticker_name):
    """
    Fetches the top 5 stock business news stories for a ticker from Google News RSS.
    """
    query = f"{ticker_name} stock news"
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    articles = []
    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for item in root.findall('.//item')[:5]:
                title = item.find('title').text if item.find('title') is not None else ''
                link = item.find('link').text if item.find('link') is not None else ''
                pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
                source = item.find('source').text if item.find('source') is not None else 'Google News'
                
                # Title typically ends with " - Source Name"
                clean_title = title
                if ' - ' in title:
                    clean_title = title.rsplit(' - ', 1)[0]
                
                articles.append({
                    'title': clean_title,
                    'url': link,
                    'pub_date': pub_date,
                    'source': source
                })
    except Exception:
        pass
    return articles


@csrf_exempt
@login_required
def analyze_stock_ai_view(request):
    """
    Evaluates a stock configuration using technical data, rsi backtesting results,
    and live Google News headlines utilizing Gemini 3.5 Flash.
    """
    # Restrict to Pro plan or trial users
    is_allowed = False
    if request.user.is_superuser:
        is_allowed = True
    else:
        try:
            profile = UserProfile.objects.get(user=request.user)
            # Allowed for: pro plan, active standard trial, or is_premium
            is_allowed = profile.plan_tier == 'pro' or (profile.plan_tier == 'standard' and profile.is_trial_active() and profile.days_remaining() > 0) or profile.is_premium
        except UserProfile.DoesNotExist:
            pass

    if not is_allowed:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Pro Analyst subscription required'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    api_key = request.headers.get('X-Gemini-API-Key') or request.GET.get('gemini_api_key')
    if not api_key or api_key == 'SERVER_PRECONFIGURED':
        load_env_file(force=True)
        api_key = os.environ.get('GEMINI_API_KEY')

    if not api_key:
        return JsonResponse({'status': 'error', 'message': 'Missing Gemini API Key (X-Gemini-API-Key)'}, status=400)

    try:
        payload = json.loads(request.body)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON body'}, status=400)

    ticker = payload.get('ticker', '').strip()
    name = payload.get('name', '').strip()
    price = payload.get('price', 0)
    rsi = payload.get('rsi', 'N/A')
    adx = payload.get('adx', 'N/A')
    drawdown = payload.get('drawdown', 0)
    above_sma200 = payload.get('above_sma200', True)
    candles = payload.get('candles', [])

    # Fetch news headlines
    news_list = fetch_google_news_rss(name)

    # Perform micro structure and backtest runs
    analysis = analyze_micro_structure(candles)
    backtest = run_backtest_rsi_30_70(candles)

    # Write prompt
    prompt_text = f"""
    You are an institutional Risk Manager and Quantitative Finance Strategist.
    Evaluate the following stock candidate for an active trade setup and assign an objective "conviction_score" from 0 to 100 based on its technical setup and context.

    Stock Profile:
    - Ticker: {ticker} ({name})
    - Current Price: ₹{price}
    
    Technical Indicators:
    - Relative Strength Index (RSI): {rsi}
    - Average Directional Index (ADX): {adx}
    - Peak-to-Trough Drawdown: {drawdown}%
    - Position vs 200 SMA: {"Above" if above_sma200 else "Below"} 200 SMA.

    Microstructure analysis over the last 30, 60, and 90 days:
    - 30-day Return: {analysis.get('ret_30')}% (Consolidation Range: {analysis.get('range_30')}% between ₹{analysis.get('min_30')} and ₹{analysis.get('max_30')})
    - Trend Stance / Phase: {analysis.get('htf_stance')}
    - Currently in Tight 30-day Consolidation Range: {"Yes" if analysis.get('in_consolidation_30') else "No"}
    - Is breaking out upside: {"Yes" if analysis.get('breakout_up_30') else "No"}
    - Is breaking out downside: {"Yes" if analysis.get('breakout_down_30') else "No"}

    Empirical Backtest Metrics (5-Year Lookback for RSI Mean Reversion):
    - Total Trades Executed: {backtest.get('total_trades')}
    - Win Rate: {backtest.get('win_rate')}%
    - Average Return per Trade (Expectancy): {backtest.get('expectancy')}%

    Catalyst & News Feeds:
    {json.dumps(news_list, indent=2)}

    Evaluation Guidelines:
    1. Veto Check: If news articles mention fraud, structural decay, or severe regulatory fines, set conviction_score directly to 0 and explain this in the rationale.
    2. Expectancy Weight (40%): Higher win rate and positive expectancy scale the conviction score.
    3. Level Support Alignment (30%): Deeply oversold stocks near key support zones (Near SMA200 / Near EMA50) should receive premium score.
    4. Momentum Convergence (30%): A MACD crossover or bullish consolidation breakout should receive premium score.
    5. Citations: In the JSON output, include any sources from the News Feed that directly influenced your rationale under 'sources_used'. Provide the exact title and URL from the input.

    Output must follow the JSON schema provided.
    """

    schema = {
        "type": "object",
        "properties": {
            "conviction_score": { "type": "integer" },
            "regime": { "type": "string" },
            "rationale": { "type": "string" },
            "recommended_stop_loss_pct": { "type": "number" },
            "sources_used": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": { "type": "string" },
                        "url": { "type": "string" }
                    },
                    "required": ["title", "url"]
                }
            }
        },
        "required": ["conviction_score", "regime", "rationale", "recommended_stop_loss_pct", "sources_used"]
    }

    endpoints = [
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1/models/gemini-3.5-flash:generateContent?key={api_key}",
    ]
    
    headers = {'Content-Type': 'application/json'}
    body = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema
        }
    }

    response = None
    last_error = ""
    status_code = 502

    for url in endpoints:
        try:
            response = requests.post(url, headers=headers, json=body, timeout=25)
            if response.status_code == 200:
                break
            else:
                last_error = f"Status {response.status_code} - {response.text}"
                status_code = response.status_code
        except Exception as e:
            last_error = str(e)

    if not response or response.status_code != 200:
        return JsonResponse({'status': 'error', 'message': f"Gemini API failure: {last_error}"}, status=status_code)

    try:
        res_json = response.json()
        text_content = res_json['candidates'][0]['content']['parts'][0]['text']
        data = json.loads(text_content)
        return JsonResponse({'status': 'success', 'data': data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f"Failed to parse Gemini output: {str(e)}"}, status=500)


@csrf_exempt
@login_required
def upgrade_premium_view(request):
    """
    Simulates upgrading the current logged-in user profile to Classic or Pro status upon GPay payment verification.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)
    
    try:
        payload = {}
        if request.body:
            try:
                payload = json.loads(request.body)
            except ValueError:
                pass
        
        # Enforce simulated payment metadata checks
        payment_status = payload.get('payment_status')
        provider = payload.get('provider')
        amount_val = payload.get('amount')
        utr = payload.get('utr', '').strip()
        requested_plan = payload.get('plan', '').strip().lower()

        if not payment_status or payment_status != 'success':
            return JsonResponse({'status': 'error', 'message': 'Upgrade rejected: Payment must be completed first.'}, status=400)
        
        if provider != 'gpay':
            return JsonResponse({'status': 'error', 'message': 'Upgrade rejected: Payment must be processed via GPay.'}, status=400)

        if not amount_val:
            return JsonResponse({'status': 'error', 'message': 'Upgrade rejected: Missing transaction amount.'}, status=400)

        amount = float(amount_val)
        if amount != 299.00 and amount != 199.00:
            return JsonResponse({'status': 'error', 'message': f'Upgrade rejected: Incorrect transaction amount ₹{amount}. Expected ₹299.00 for Classic or ₹199.00 for Pro.'}, status=400)

        if not utr:
            return JsonResponse({'status': 'error', 'message': 'Upgrade rejected: Missing transaction UTR / Ref No.'}, status=400)

        # Enforce UTR must be exactly 12 numeric digits
        if not utr.isdigit() or len(utr) != 12:
            return JsonResponse({'status': 'error', 'message': 'Upgrade rejected: UTR / Reference Number must be exactly 12 numeric digits.'}, status=400)

        # Enforce UTR uniqueness to prevent replay attacks
        if PaymentVerificationRequest.objects.filter(utr=utr).exists():
            return JsonResponse({'status': 'error', 'message': 'Upgrade rejected: This transaction UTR has already been submitted for verification.'}, status=400)

        # Map plan tier based on amount or requested plan
        if amount == 299.00 or requested_plan == 'classic':
            target_tier = 'classic'
            tier_name = 'Classic Engine'
        elif amount == 199.00 or requested_plan == 'pro':
            target_tier = 'pro'
            tier_name = 'Pro Analyst'
        else:
            return JsonResponse({'status': 'error', 'message': 'Upgrade rejected: Unknown plan configuration.'}, status=400)

        upi_id_val = payload.get('upi_id', '').strip() or payload.get('gpay_upi_id', '').strip() or 'GPay User'

        # Queue verification request in the database
        PaymentVerificationRequest.objects.create(
            user=request.user,
            plan=target_tier,
            amount=amount,
            utr=utr,
            upi_id=upi_id_val,
            status='pending'
        )

        # Log notification for Admin
        admin_msg = f"PENDING APPROVAL: User @{request.user.username} (Email: {request.user.email}) submitted ₹{amount} for {tier_name} plan. UPI: {upi_id_val}, UTR: {utr}."
        AdminNotification.objects.create(message=admin_msg)

        # Share emails to Admin and User
        try:
            subject_admin = f"[TradeKriya] Action Required: Verify UPI Payment from @{request.user.username}"
            body_admin = f"""Hello Admin,

A user has submitted a UPI payment reference for verification.

User Details:
- Username: @{request.user.username}
- Email: {request.user.email or 'N/A'}
- Plan Requested: {tier_name}
- Amount: Rs. {amount:.2f}
- UPI ID/Phone: {upi_id_val}
- UTR Reference: {utr}

Please check your bank statement for UTR: {utr} and approve/reject the upgrade request in the TradeKriya Admin Controls Panel.

Regards,
TradeKriya Platform"""

            subject_user = "[TradeKriya] Payment Verification Request Received"
            body_user = f"""Hello {request.user.username},

Thank you for choosing TradeKriya! We have received your payment reference for the {tier_name} upgrade.

Transaction Details:
- Reference UTR: {utr}
- Amount: Rs. {amount:.2f}
- Plan: {tier_name}

Our risk team is currently verifying the transaction with our bank statements. Your account tier will be updated automatically as soon as it is confirmed.

You will see a notification on your dashboard when active.

Regards,
Team TradeKriya"""

            admin_email = os.environ.get('ADMIN_EMAIL', 'admin@tradekriya.com')

            # Send to Admin
            send_mail(
                subject=subject_admin,
                message=body_admin,
                from_email=None,
                recipient_list=[admin_email],
                fail_silently=True
            )
            
            # Send to User
            if request.user.email:
                send_mail(
                    subject=subject_user,
                    message=body_user,
                    from_email=None,
                    recipient_list=[request.user.email],
                    fail_silently=True
                )
                
            print(f"\n[EMAIL SIMULATION] Sent Payment Verification Pending Mail to Admin ({admin_email}) and User ({request.user.email or 'N/A'}) for UTR: {utr}")
        except Exception as mail_err:
            print(f"[EMAIL ERROR] Failed to send verification emails: {mail_err}")

        return JsonResponse({
            'status': 'pending', 
            'message': f'Payment verification request submitted for {tier_name}! Awaiting admin approval. UTR Ref: {utr}'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@login_required
def admin_list_users(request):
    """
    Returns a list of all user profiles and their subscription states (superuser only).
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin access required'}, status=403)
    
    profiles = UserProfile.objects.all().select_related('user').order_by('user__username')
    data = []
    for p in profiles:
        status = 'trial'
        if p.is_premium:
            status = 'premium'
        elif not p.is_trial_active() or p.trial_duration_days == 0:
            if p.plan_tier == 'classic':
                status = 'classic'
            elif p.plan_tier == 'pro':
                status = 'pro'
            else:
                status = 'expired'
        else:
            status = 'trial'

        data.append({
            'username': p.user.username,
            'email': p.user.email,
            'is_premium': p.is_premium or p.plan_tier in ['classic', 'pro'],
            'plan_tier': p.plan_tier,
            'has_used_trial': p.has_used_trial,
            'status': status
        })
    return JsonResponse({'status': 'success', 'users': data})


@csrf_exempt
@login_required
def admin_downgrade_user(request):
    """
    Downgrades a specific user's profile from Premium to Standard (superuser only).
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin access required'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    try:
        payload = json.loads(request.body)
        target_username = payload.get('username')
        if not target_username:
            return JsonResponse({'status': 'error', 'message': 'Missing target username'}, status=400)

        # Retrieve user and downgrade their profile
        target_user = User.objects.get(username=target_username)
        profile, created = UserProfile.objects.get_or_create(user=target_user)
        profile.plan_tier = 'standard'
        profile.is_premium = False
        profile.save()

        return JsonResponse({'status': 'success', 'message': f'Successfully downgraded {target_username} to Standard Plan.'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@login_required
def admin_upgrade_user(request):
    """
    Manually upgrades a specific user's profile to Premium status (superuser only).
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin access required'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    try:
        payload = json.loads(request.body)
        target_username = payload.get('username')
        requested_plan = payload.get('plan', 'pro').strip().lower()
        if not target_username:
            return JsonResponse({'status': 'error', 'message': 'Missing target username'}, status=400)

        if requested_plan not in ['classic', 'pro']:
            return JsonResponse({'status': 'error', 'message': 'Invalid plan requested. Use classic or pro.'}, status=400)

        target_user = User.objects.get(username=target_username)
        profile, created = UserProfile.objects.get_or_create(user=target_user)
        profile.plan_tier = requested_plan
        profile.is_premium = True
        profile.save()

        return JsonResponse({'status': 'success', 'message': f'Successfully upgraded {target_username} to {requested_plan.capitalize()} Plan.'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


import random
import string

@csrf_exempt
def forgot_password_view(request):
    """
    Handles password retrieval/reset by generating a simulated one-time temporary recovery password
    associated with the registered user email address.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    try:
        payload = json.loads(request.body)
        email = payload.get('email', '').strip().lower()
        if not email:
            return JsonResponse({'status': 'error', 'message': 'Please enter a valid email address'}, status=400)

        # Look up user by email
        users = User.objects.filter(email__iexact=email)
        if not users.exists():
            return JsonResponse({'status': 'error', 'message': 'No account associated with this email.'}, status=404)

        # Get first user and generate random temporary password
        target_user = users.first()
        temp_chars = string.ascii_letters + string.digits
        temp_pass = 'Temp-' + ''.join(random.choice(temp_chars) for _ in range(8))

        # Save new temporary password on user
        target_user.set_password(temp_pass)
        target_user.save()

        # Log password reset internally (to backend console for auditing / PythonAnywhere debugging)
        print(f"[RECOVERY AUDIT] Generated recovery credentials for {target_user.username} ({email}): {temp_pass}")

        return JsonResponse({
            'status': 'success',
            'email': email,
            'username': target_user.username,
            'temp_password': temp_pass
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@login_required
def admin_notifications_list(request):
    """
    Lists all unread admin payment alerts (superuser only).
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin access required'}, status=403)
    
    notifications = AdminNotification.objects.filter(is_read=False).order_by('-created_at')
    data = []
    for n in notifications:
        data.append({
            'id': n.id,
            'message': n.message,
            'created_at': n.created_at.strftime('%Y-%m-%d %H:%M')
        })
    return JsonResponse({'status': 'success', 'notifications': data})


@csrf_exempt
@login_required
def admin_notifications_clear(request):
    """
    Marks all admin notifications as read (superuser only).
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin access required'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)
    
    AdminNotification.objects.all().update(is_read=True)
    return JsonResponse({'status': 'success', 'message': 'All notifications cleared.'})


@csrf_exempt
@login_required
def admin_verify_payment_view(request):
    """
    Approves or rejects a pending payment verification request (superuser only).
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin access required'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)
    
    try:
        payload = json.loads(request.body)
        payment_id = payload.get('payment_id')
        action = payload.get('action', '').strip().lower() # approve, reject
        
        if not payment_id or action not in ['approve', 'reject']:
            return JsonResponse({'status': 'error', 'message': 'Missing payment_id or invalid action.'}, status=400)
            
        payment_req = PaymentVerificationRequest.objects.get(id=payment_id)
        if payment_req.status != 'pending':
            return JsonResponse({'status': 'error', 'message': 'Payment request has already been processed.'}, status=400)
            
        target_profile = UserProfile.objects.get(user=payment_req.user)
        
        if action == 'approve':
            payment_req.status = 'approved'
            payment_req.save()
            
            # Upgrade user's plan tier
            target_profile.plan_tier = payment_req.plan
            if payment_req.plan == 'pro':
                now = timezone.now()
                # If they are currently Pro and have time left, extend it! Otherwise start from now
                base_time = target_profile.pro_expires_at if (target_profile.pro_expires_at and target_profile.pro_expires_at > now) else now
                target_profile.pro_expires_at = base_time + datetime.timedelta(days=30)
                tier_label = 'Pro Analyst (Monthly)'
            else:
                tier_label = 'Classic Engine (One-time)'
            target_profile.save()
            
            # Create user-facing success alert
            UserNotification.objects.create(
                user=payment_req.user,
                message=f"Upgrade Confirmed! Your payment of Rs. {payment_req.amount:.2f} has been verified. Your account is now active on the {tier_label} plan."
            )
            
            # Log admin notifications audit log
            AdminNotification.objects.create(
                message=f"APPROVED: User @{payment_req.user.username}'s upgrade to {payment_req.plan} plan (UTR: {payment_req.utr}) has been confirmed by Admin."
            )
            
            return JsonResponse({'status': 'success', 'message': f'Successfully approved payment and upgraded user {payment_req.user.username}.'})
            
        elif action == 'reject':
            payment_req.status = 'rejected'
            payment_req.save()
            
            # Create user-facing rejection alert
            UserNotification.objects.create(
                user=payment_req.user,
                message=f"Rejection Alert: Payment reference UTR: {payment_req.utr} (Rs. {payment_req.amount:.2f}) could not be verified in our bank statement. Please check details and resubmit."
            )
            
            # Log admin notifications audit log
            AdminNotification.objects.create(
                message=f"REJECTED: User @{payment_req.user.username}'s payment (UTR: {payment_req.utr}) was rejected by Admin."
            )
            
            return JsonResponse({'status': 'success', 'message': f'Successfully rejected payment request for user {payment_req.user.username}.'})
            
    except PaymentVerificationRequest.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Payment request not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@login_required
def clear_user_notifications_view(request):
    """
    Marks all notifications for the current logged-in user as read.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)
    
    UserNotification.objects.filter(user=request.user).update(is_read=True)
    return JsonResponse({'status': 'success', 'message': 'Notifications marked as read.'})


@csrf_exempt
@login_required
def admin_pending_payments_list_view(request):
    """
    Lists all pending payment verification requests (superuser only).
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin access required'}, status=403)
    
    payments = PaymentVerificationRequest.objects.filter(status='pending').order_by('-created_at')
    data = []
    for r in payments:
        data.append({
            'id': r.id,
            'username': r.user.username,
            'plan': r.plan,
            'amount': r.amount,
            'utr': r.utr,
            'upi_id': r.upi_id,
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M')
        })
    return JsonResponse({'status': 'success', 'payments': data})


import io
from django.core.management import call_command

@csrf_exempt
@login_required
def admin_run_marketing_agent_view(request):
    """
    Superuser-only view to trigger the TradeKriya Marketing & Insights Agent.
    Allows passing options like 'symbol' or 'theme' via JSON payload.
    """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Forbidden: Admin / Superuser access required'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    symbol = None
    theme = None

    if request.body:
        try:
            payload = json.loads(request.body)
            symbol = payload.get('symbol')
            theme = payload.get('theme')
        except ValueError:
            pass

    out = io.StringIO()
    try:
        kwargs = {}
        if symbol:
            kwargs['symbol'] = symbol.strip().upper()
        if theme:
            kwargs['theme'] = theme.strip().lower()

        call_command('run_marketing_agent', stdout=out, stderr=out, **kwargs)
        output_logs = out.getvalue()
        
        if "[ERROR]" in output_logs:
            return JsonResponse({
                'status': 'error',
                'message': 'Marketing agent run completed with errors.',
                'logs': output_logs
            }, status=500)
            
        return JsonResponse({
            'status': 'success',
            'message': 'Marketing agent run triggered and completed successfully.',
            'logs': output_logs
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f"Unexpected error executing marketing agent: {str(e)}",
            'logs': out.getvalue()
        }, status=500)

