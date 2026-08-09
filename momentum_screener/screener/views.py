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
from .models import UserProfile, TradeJournal
import json
from pathlib import Path

def load_env_file():
    """
    Manually parses the .env file in the BASE_DIR if it exists
    and sets the environment variables.
    """
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

def dashboard_view(request):
    """
    Renders the main dashboard page.
    """
    if not request.user.is_authenticated and not request.session.get('is_guest_user'):
        return redirect('screener:login')

    user_status = 'guest'
    days_left = 0
    username = 'Guest User'

    if request.user.is_authenticated:
        username = request.user.username
        if request.user.is_superuser:
            user_status = 'premium'
            days_left = 9999
        else:
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            if profile.is_premium:
                user_status = 'premium'
                days_left = 9999
            elif profile.is_trial_active():
                user_status = 'trial'
                days_left = profile.days_remaining()
            else:
                user_status = 'expired'
                days_left = 0

    has_zerodha_creds = bool(os.environ.get('ZERODHA_API_KEY') and os.environ.get('ZERODHA_ACCESS_TOKEN'))
    has_gemini_cred = bool(os.environ.get('GEMINI_API_KEY'))

    # Pass the list of pre-mapped symbols to the template so the UI dropdown can render them
    context = {
        'supported_symbols': sorted(list(SYMBOL_TO_TOKEN.keys())),
        'has_zerodha_creds': has_zerodha_creds,
        'has_gemini_cred': has_gemini_cred,
        'user_status': user_status,
        'days_left': days_left,
        'username': username,
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
def generate_campaign_view(request):
    """
    Calls the Gemini API to generate a quantitative finance dilemma/campaign for a stock
    based on its current technical indicators, micro-structure trends, and actual strategy backtest statistics.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    api_key = request.headers.get('X-Gemini-API-Key') or request.GET.get('gemini_api_key')
    if not api_key or api_key == 'SERVER_PRECONFIGURED':
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

    # Gemini API fallback endpoints, prioritizing stable 1.5 models for free quota reliability
    endpoints = [
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={api_key}",
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
                # Create user
                user = User.objects.create_user(username=username, email=email, password=password)
                # Create UserProfile
                UserProfile.objects.create(user=user)
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
    if not request.user.is_superuser and not request.user.profile.is_trial_active():
        return JsonResponse({'status': 'error', 'message': 'Trial Expired'}, status=403)
        
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
    if not request.user.is_superuser and not request.user.profile.is_trial_active():
        return JsonResponse({'status': 'error', 'message': 'Trial Expired'}, status=403)
        
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

