import os
import json
import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from screener.views import SYMBOL_TO_TOKEN, load_env_file
import requests

class Command(BaseCommand):
    help = 'Scans historical dumps to find technical setups and drafts marketing content focusing on trading psychology using Gemini'

    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, default=None, help='Target stock symbol to write about')
        parser.add_argument('--theme', type=str, default=None, choices=['patience', 'discipline', 'fomo', 'loss_aversion', 'failed_breakout', 'failed_breakdown', 'sudden_reversal'], help='Focus trading psychology theme')

    def handle(self, *args, **options):
        self.stdout.write("====================================================")
        self.stdout.write("       TradeKriya Marketing & Insights Agent        ")
        self.stdout.write("====================================================\n")

        # 1. Force reload env to capture API keys
        load_env_file(force=True)
        api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('Gemini_API_KEY') or os.environ.get('gemini_api_key')
        if not api_key:
            self.stdout.write(self.style.WARNING("[WARNING] GEMINI_API_KEY is not defined in the server's .env file. The agent will use quantitative algorithmic copywriting."))

        # 2. Path to historical data dump
        # Path(__file__).resolve().parent.parent.parent is the 'screener' app directory
        base_dir = Path(__file__).resolve().parent.parent.parent
        db_path = base_dir / 'data' / 'fo_historical_dump.json'

        if not db_path.exists():
            self.stdout.write(self.style.ERROR(f"[ERROR] Database dump file not found at {db_path}"))
            self.stdout.write("[INFO] Please run 'python manage.py dump_fo_data' first to fetch stock data.")
            return

        # 3. Read the dump
        with open(db_path, 'r', encoding='utf-8') as f:
            dump_data = json.load(f)

        if not dump_data:
            self.stdout.write(self.style.ERROR("[ERROR] The historical dump database is empty."))
            return

        self.stdout.write(f"[INFO] Loaded historical data for {len(dump_data)} stocks.")

        # 4. Scan stocks & compute indicators locally
        scanned_results = []
        target_symbol = options['symbol'].strip().upper() if options['symbol'] else None

        for symbol, candles in dump_data.items():
            if target_symbol and symbol != target_symbol:
                continue

            if not candles or len(candles) < 200:
                continue

            closes = [float(c[4]) for c in candles]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]

            sma200 = self.calculate_sma(closes, 200)
            sma50 = self.calculate_sma(closes, 50)
            rsi = self.calculate_rsi(closes, 14)
            adx, plus_di, minus_di = self.calculate_adx(highs, lows, closes, 14)
            macd, signal = self.calculate_macd(closes)

            price = closes[-1]
            last_sma200 = sma200[-1]
            last_sma50 = sma50[-1]
            last_rsi = rsi[-1]
            last_adx = adx[-1]
            last_plus_di = plus_di[-1]
            last_minus_di = minus_di[-1]
            last_macd = macd[-1]
            last_signal = signal[-1]

            window_250_highs = highs[-250:] if len(highs) >= 250 else highs
            peak_250 = max(window_250_highs) if window_250_highs else price
            drawdown = round(((peak_250 - price) / peak_250 * 100), 2) if peak_250 > 0 else 0.0

            stance = 'Stable'
            max_52w = max(closes[-250:]) if len(closes) >= 250 else max(closes)
            min_52w = min(closes[-250:]) if len(closes) >= 250 else min(closes)
            if price >= max_52w * 0.98:
                stance = '52W High'
            elif price <= min_52w * 1.02:
                stance = '52W Low'
            elif last_sma200 and abs(price - last_sma200) / last_sma200 <= 0.015:
                stance = 'Near SMA 200'
            elif last_sma50 and abs(price - last_sma50) / last_sma50 <= 0.015:
                stance = 'Near EMA 50'

            is_falling_knife = (
                last_sma200 and price < last_sma200 and 
                drawdown >= 30.0 and 
                last_rsi and last_rsi < 35.0 and 
                last_adx and last_adx > 22.0 and 
                last_minus_di and last_plus_di and last_minus_di > last_plus_di
            )

            macd_crossover_shift = False
            if len(macd) >= 3 and macd[-1] is not None and signal[-1] is not None:
                crossover_today = macd[-1] > signal[-1] and macd[-2] <= signal[-2]
                crossover_yesterday = macd[-2] > signal[-2] and macd[-3] <= signal[-3]
                if (crossover_today or crossover_yesterday) and price > last_sma200:
                    macd_crossover_shift = True

            scanned_results.append({
                'symbol': symbol,
                'price': price,
                'sma200': last_sma200,
                'rsi': last_rsi,
                'adx': last_adx,
                'drawdown': drawdown,
                'stance': stance,
                'is_falling_knife': is_falling_knife,
                'macd_crossover_shift': macd_crossover_shift,
            })

        # 5. Selection strategy based on flags
        selected_stock = None
        theme = options.get('theme')
        if theme:
            theme = theme.strip().lower()

        if target_symbol:
            for item in scanned_results:
                if item['symbol'] == target_symbol:
                    selected_stock = item
                    break
            if not selected_stock:
                # Dynamically fetch candles for ticker via get_candles_for_ticker
                from screener.fundamental_service import get_candles_for_ticker
                fallback_candles = get_candles_for_ticker(target_symbol)
                if fallback_candles and len(fallback_candles) >= 30:
                    closes = [float(c[4]) for c in fallback_candles]
                    highs = [float(c[2]) for c in fallback_candles]
                    lows = [float(c[3]) for c in fallback_candles]
                    sma200 = self.calculate_sma(closes, 200)
                    sma50 = self.calculate_sma(closes, 50)
                    rsi = self.calculate_rsi(closes, 14)
                    adx, plus_di, minus_di = self.calculate_adx(highs, lows, closes, 14)
                    macd, signal = self.calculate_macd(closes)
                    price = closes[-1]
                    last_sma200 = sma200[-1] if (sma200 and sma200[-1] is not None) else price
                    last_sma50 = sma50[-1] if (sma50 and sma50[-1] is not None) else price
                    last_rsi = rsi[-1] if (rsi and rsi[-1] is not None) else 50.0
                    last_adx = adx[-1] if (adx and adx[-1] is not None) else 20.0
                    peak_250 = max(highs[-250:]) if len(highs) >= 250 else max(highs)
                    drawdown = round(((peak_250 - price) / peak_250 * 100), 2) if peak_250 > 0 else 0.0
                    
                    stance = 'Key Support/Resistance'
                    max_52w = max(closes[-250:]) if len(closes) >= 250 else max(closes)
                    min_52w = min(closes[-250:]) if len(closes) >= 250 else min(closes)
                    if price >= max_52w * 0.98:
                        stance = '52W High'
                    elif price <= min_52w * 1.02:
                        stance = '52W Low'
                    elif last_sma200 and abs(price - last_sma200) / last_sma200 <= 0.015:
                        stance = 'Near SMA 200'
                    elif last_sma50 and abs(price - last_sma50) / last_sma50 <= 0.015:
                        stance = 'Near EMA 50'

                    selected_stock = {
                        'symbol': target_symbol,
                        'price': price,
                        'sma200': last_sma200,
                        'rsi': last_rsi,
                        'adx': last_adx,
                        'drawdown': drawdown,
                        'stance': stance,
                        'is_falling_knife': (drawdown >= 30.0 and last_rsi < 35.0),
                        'macd_crossover_shift': (macd[-1] > signal[-1]) if (macd and signal and macd[-1] is not None and signal[-1] is not None) else False,
                    }
                else:
                    self.stdout.write(self.style.ERROR(f"[ERROR] Target symbol '{target_symbol}' was not found on NSE or lacks trading history."))
                    return

            # Auto-detect psychological theme for target stock if theme was not provided
            if not theme:
                if selected_stock.get('macd_crossover_shift'):
                    theme = 'discipline'
                elif selected_stock.get('is_falling_knife'):
                    theme = 'patience'
                elif selected_stock.get('stance') == '52W High':
                    theme = 'fomo'
                elif selected_stock.get('drawdown', 0) >= 15.0:
                    theme = 'loss_aversion'
                else:
                    theme = 'discipline'
        else:
            shifts = [s for s in scanned_results if s['macd_crossover_shift']]
            knives = [k for k in scanned_results if k['is_falling_knife']]
            
            if shifts:
                shifts.sort(key=lambda x: x['rsi'] if x['rsi'] is not None else 100)
                selected_stock = shifts[0]
                if not theme:
                    theme = 'discipline'
            elif knives:
                knives.sort(key=lambda x: x['drawdown'], reverse=True)
                selected_stock = knives[0]
                if not theme:
                    theme = 'patience'
            else:
                scanned_results.sort(key=lambda x: x['drawdown'], reverse=True)
                selected_stock = scanned_results[0]
                if not theme:
                    theme = 'loss_aversion'

        if not theme:
            theme = 'discipline'

        theme_descriptions = {
            'patience': 'Patience: Waiting for trend validation rather than jumping in early on a "cheap" asset (avoiding falling knives).',
            'discipline': 'Discipline: Sticking to rule-based setups (such as validated MACD crossovers) and utilizing strict exit stop losses rather than trading on emotions.',
            'fomo': 'FOMO (Fear Of Missing Out): Chasing breakouts blindly without volume/micro-structure confirmation.',
            'loss_aversion': 'Loss Aversion: The psychological bias that causes traders to hold losing trades, hoping to break even, instead of cutting losses cleanly.',
            'failed_breakout': 'Failed Breakouts / Bull Traps: Showing trapped buyer emotions, stop-loss clusters just below the breakout level, and why chasing FOMO makes buyers emotionally vulnerable.',
            'failed_breakdown': 'Failed Breakdowns / Bear Traps: Showing trapped seller emotions, stop-loss clusters just above the breakdown levels, and why panic selling makes bears emotionally vulnerable.',
            'sudden_reversal': 'Sudden Trend Reversals: Illustrating stop-loss cascades, emotional shock/denial, and the capitulation of trapped trend-followers.'
        }

        selected_theme_desc = theme_descriptions.get(theme, theme_descriptions['discipline'])

        self.stdout.write(f"\n[INFO] Selected Stock: {selected_stock['symbol']}")
        self.stdout.write(f"[INFO] Current Price: Rs {selected_stock['price']}")
        self.stdout.write(f"[INFO] Indicators - RSI: {round(selected_stock['rsi'], 1) if selected_stock['rsi'] else 'N/A'}, ADX: {round(selected_stock['adx'], 1) if selected_stock['adx'] else 'N/A'}, Drawdown: {selected_stock['drawdown']}%")
        self.stdout.write(f"[INFO] Stance: {selected_stock['stance']}")
        self.stdout.write(f"[INFO] Target Psychology Theme: {theme.upper()} ({selected_theme_desc})")

        # 6. Construct Gemini prompt payload
        prompt_text = f"""
        You are an expert Quantitative Finance Copywriter, Trading Psychologist, and Marketing Strategist for the TradeKriya platform.
        
        Write a psychology-centered marketing campaign using a real quantitative stock setup as a teachable moment.
        
        Stock Details:
        - Ticker: {selected_stock['symbol']}
        - Current Price: Rs {selected_stock['price']}
        - Relative Strength Index (RSI): {round(selected_stock['rsi'], 1) if selected_stock['rsi'] else 'N/A'}
        - Average Directional Index (ADX): {round(selected_stock['adx'], 1) if selected_stock['adx'] else 'N/A'}
        - Peak-to-Trough Drawdown: {selected_stock['drawdown']}%
        - Technical Stance: {selected_stock['stance']}
        - Falling Knife Status: {"Yes (severe downtrend)" if selected_stock['is_falling_knife'] else "No"}
        - Recent MACD Crossover: {"Yes (bullish shift confirmed)" if selected_stock['macd_crossover_shift'] else "No"}

        Core Psychological Theme:
        - Theme: {selected_theme_desc}

        INSTRUCTIONS:
        - Address the psychological values of trading (Patience, Discipline, or emotional biases like Loss Aversion, FOMO, Trapped Traders, Stop-loss Clusters, and Emotional Vulnerability).
        - Explicitly analyze:
          1. Where stop-losses are likely clustered for bulls and bears.
          2. Which side of the market is emotionally vulnerable and why.
          3. How the trapped traders' emotions (shock, denial, panic) play out.
        - DO NOT make a boring data dump. The post must focus on the mindset, using the stock's indicators only to illustrate the lesson.
        - Generate EXACTLY 3 interesting, distinct questions related to this stock setup. Each question must ask the user whether they would be Bullish, Bearish, or Wait in this scenario.
        - Create EXACTLY 4 drafts:
          1. Twitter/X Thread (3-4 tweets. Start with an emotional or psychological hook, explain the setup as a lesson, and call to action to vote at [VOTING_LINK]).
          2. LinkedIn Post (A detailed professional storytelling post discussing the mindset required for trading, risk management, and quantitative systems. End with a call to action to vote at [VOTING_LINK]).
          3. Telegram Alert (A concise bulleted digest with a takeaway on discipline and the link [VOTING_LINK]).
          4. YouTube Shorts / Reels Script (A 60-second video script with visual instructions, spoken narration, and text overlays that illustrate the psychological lesson using the stock's chart behavior).
        
        Return the result in JSON format conforming strictly to this JSON schema:
        {{
            "title": "Title of the Campaign",
            "question_1": "Mindset question 1 related to this stock setup?",
            "question_2": "Mindset question 2 related to this stock setup?",
            "question_3": "Mindset question 3 related to this stock setup?",
            "twitter_thread": ["Tweet 1 text", "Tweet 2 text", "Tweet 3 text", "Tweet 4 text"],
            "linkedin_post": "Full text of the LinkedIn post",
            "telegram_digest": "Full text of the Telegram alert",
            "youtube_shorts_script": {{
                "visuals_description": "General description of what should be shown on screen",
                "voiceover_script": "Voiceover narrative script",
                "on_screen_text": "Important text/captions to display on screen"
            }}
        }}
        """

        campaign = None
        if api_key:
            candidate_models = [
                'gemini-2.5-flash',
                'gemini-flash-latest',
                'gemini-3.5-flash',
                'gemini-3.8-flash',
            ]
            headers = {
                'Content-Type': 'application/json'
            }
            body = {
                "contents": [{
                    "parts": [{
                        "text": prompt_text
                    }]
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "object",
                        "properties": {
                            "title": { "type": "string" },
                            "question_1": { "type": "string" },
                            "question_2": { "type": "string" },
                            "question_3": { "type": "string" },
                            "twitter_thread": {
                                "type": "array",
                                "items": { "type": "string" }
                            },
                            "linkedin_post": { "type": "string" },
                            "telegram_digest": { "type": "string" },
                            "youtube_shorts_script": {
                                "type": "object",
                                "properties": {
                                    "visuals_description": { "type": "string" },
                                    "voiceover_script": { "type": "string" },
                                    "on_screen_text": { "type": "string" }
                                },
                                "required": ["visuals_description", "voiceover_script", "on_screen_text"]
                            }
                        },
                        "required": ["title", "question_1", "question_2", "question_3", "twitter_thread", "linkedin_post", "telegram_digest", "youtube_shorts_script"]
                    }
                }
            }

            self.stdout.write("[INFO] Submitting payload to Gemini API...")
            for model_name in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                try:
                    response = requests.post(url, headers=headers, json=body, timeout=30)
                    if response.status_code == 200:
                        result_json = response.json()
                        candidates = result_json.get('candidates', [])
                        if candidates and 'content' in candidates[0] and 'parts' in candidates[0]['content']:
                            content = candidates[0]['content']['parts'][0]['text']
                            campaign = json.loads(content)
                            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Model '{model_name}' successfully generated campaign: {campaign.get('title', 'Campaign')}"))
                            break
                    else:
                        self.stdout.write(self.style.WARNING(f"[WARNING] Model '{model_name}' returned HTTP {response.status_code}. Retrying with next model..."))
                except Exception as req_err:
                    self.stdout.write(self.style.WARNING(f"[WARNING] Model '{model_name}' request failed: {str(req_err)}. Retrying with next model..."))

        if not campaign:
            self.stdout.write(self.style.WARNING("[INFO] Generating campaign using deterministic quantitative copywriting engine..."))
            campaign = self.generate_deterministic_campaign(selected_stock, theme, selected_theme_desc)
            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Successfully generated campaign via quantitative engine: {campaign['title']}"))

        # 1. Auto-Publish to Community Use Cases DB to get post ID
        post_id = None
        try:
            from screener.models import CommunityPost
            post = CommunityPost.objects.create(
                title=campaign['title'],
                stock_symbol=selected_stock['symbol'],
                theme=theme,
                theme_display=selected_theme_desc,
                twitter_thread_json=json.dumps(campaign['twitter_thread']),
                linkedin_post=campaign['linkedin_post'],
                telegram_digest=campaign['telegram_digest'],
                youtube_shorts_script_json=json.dumps(campaign['youtube_shorts_script']),
                question_1=campaign['question_1'],
                question_2=campaign['question_2'],
                question_3=campaign['question_3']
            )
            post_id = post.id
            
            # Generate dynamic voting/mindset poll URL
            voting_link = f"https://www.tradekriya.com/community/post/{post.id}/"
            
            # Replace [VOTING_LINK] in text fields
            campaign['linkedin_post'] = campaign['linkedin_post'].replace('[VOTING_LINK]', voting_link)
            campaign['telegram_digest'] = campaign['telegram_digest'].replace('[VOTING_LINK]', voting_link)
            campaign['twitter_thread'] = [t.replace('[VOTING_LINK]', voting_link) for t in campaign['twitter_thread']]
            
            # Update database post with replaced contents
            post.linkedin_post = campaign['linkedin_post']
            post.telegram_digest = campaign['telegram_digest']
            post.twitter_thread_json = json.dumps(campaign['twitter_thread'])
            post.save()
            
            self.stdout.write(self.style.SUCCESS(f"[SUCCESS] Campaign successfully published to DB (ID: {post.id}) with Voting Link: {voting_link}"))
        except Exception as db_err:
            self.stdout.write(self.style.WARNING(f"[WARNING] Failed to auto-publish campaign to database: {str(db_err)}"))
            voting_link = "https://www.tradekriya.com/community/"

        # 2. Archive draft to markdown file
        try:
            project_root = base_dir.parent
            marketing_dir = project_root / 'marketing_campaigns'
            marketing_dir.mkdir(exist_ok=True)
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            draft_path = marketing_dir / f"campaign_{timestamp}.md"

            md_content = f"""# TradeKriya Marketing Campaign: {campaign['title']}
**Date:** {datetime.date.today().strftime('%B %d, %Y')}  
**Stock Anchor:** {selected_stock['symbol']} (Price: Rs {selected_stock['price']})  
**Core Theme:** {theme.upper()} - {selected_theme_desc}  

---

## 🗳️ Interactive Mindset Poll Questions
1. **Q1:** {campaign['question_1']}
2. **Q2:** {campaign['question_2']}
3. **Q3:** {campaign['question_3']}

---

## 🐦 Draft 1: X (Twitter) Thread
"""
            for idx, tweet in enumerate(campaign['twitter_thread']):
                md_content += f"### Tweet {idx + 1}\n{tweet}\n\n"

            md_content += f"""---

## 💼 Draft 2: LinkedIn Post
{campaign['linkedin_post']}

---

## 📢 Draft 3: Telegram Digest
{campaign['telegram_digest']}

---

## 🎥 Draft 4: YouTube Shorts / Reels Script (60-Seconds)
* **Visual Setup:** {campaign['youtube_shorts_script']['visuals_description']}  
* **Text Overlay:** {campaign['youtube_shorts_script']['on_screen_text']}  

### Narration Script
{campaign['youtube_shorts_script']['voiceover_script']}
"""

            with open(draft_path, 'w', encoding='utf-8') as f_out:
                f_out.write(md_content)

            self.stdout.write(self.style.SUCCESS(f"[SUCCESS] Draft archived successfully at: {draft_path}"))
            self.stdout.write("====================================================\n")
            ascii_preview = md_content[:1500].encode('ascii', 'ignore').decode('ascii')
            self.stdout.write(ascii_preview + "\n... (remaining content saved to file) ...")
        except Exception as file_err:
            self.stdout.write(self.style.WARNING(f"[WARNING] Failed to archive campaign draft to file: {str(file_err)}"))

    def calculate_sma(self, prices, period):
        if len(prices) < period:
            return [None] * len(prices)
        sma = [None] * (period - 1)
        current_sum = sum(prices[:period])
        sma.append(current_sum / period)
        for i in range(period, len(prices)):
            current_sum += prices[i] - prices[i - period]
            sma.append(current_sum / period)
        return sma

    def calculate_ema(self, prices, period):
        n = len(prices)
        if n < period:
            return [None] * n
        ema = [None] * n
        initial_sma = sum(prices[:period]) / period
        ema[period - 1] = initial_sma
        multiplier = 2.0 / (period + 1)
        for i in range(period, n):
            ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
        return ema

    def calculate_rsi(self, prices, period=14):
        n = len(prices)
        if n <= period:
            return [None] * n
        rsi_values = [None] * n
        deltas = [prices[i] - prices[i-1] for i in range(1, n)]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
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
            
            avg_gain = (avg_gain * (period - 1) + gain) / period
            avg_loss = (avg_loss * (period - 1) + loss) / period
            
            if avg_loss == 0:
                rsi_values[i] = 100
            else:
                rs = avg_gain / avg_loss
                rsi_values[i] = 100 - (100 / (1 + rs))
        return rsi_values

    def calculate_adx(self, highs, lows, closes, period=14):
        n = len(closes)
        if n <= period:
            return [None] * n, [None] * n, [None] * n
            
        tr = [0.0] * n
        plus_dm = [0.0] * n
        minus_dm = [0.0] * n
        
        for i in range(1, n):
            h_diff = highs[i] - highs[i-1]
            l_diff = lows[i-1] - lows[i]
            
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            
            if h_diff > l_diff and h_diff > 0:
                plus_dm[i] = h_diff
            else:
                plus_dm[i] = 0.0
                
            if l_diff > h_diff and l_diff > 0:
                minus_dm[i] = l_diff
            else:
                minus_dm[i] = 0.0
                
        smoothed_tr = [0.0] * n
        smoothed_plus_dm = [0.0] * n
        smoothed_minus_dm = [0.0] * n
        
        smoothed_tr[period] = sum(tr[1:period+1])
        smoothed_plus_dm[period] = sum(plus_dm[1:period+1])
        smoothed_minus_dm[period] = sum(minus_dm[1:period+1])
        
        for i in range(period + 1, n):
            smoothed_tr[i] = smoothed_tr[i-1] - (smoothed_tr[i-1] / period) + tr[i]
            smoothed_plus_dm[i] = smoothed_plus_dm[i-1] - (smoothed_plus_dm[i-1] / period) + plus_dm[i]
            smoothed_minus_dm[i] = smoothed_minus_dm[i-1] - (smoothed_minus_dm[i-1] / period) + minus_dm[i]
            
        plus_di = [None] * n
        minus_di = [None] * n
        dx = [None] * n
        
        for i in range(period, n):
            tr_val = smoothed_tr[i]
            if tr_val == 0:
                plus_di[i] = 0.0
                minus_di[i] = 0.0
            else:
                plus_di[i] = 100 * (smoothed_plus_dm[i] / tr_val)
                minus_di[i] = 100 * (smoothed_minus_dm[i] / tr_val)
                
            sum_di = plus_di[i] + minus_di[i]
            if sum_di == 0:
                dx[i] = 0.0
            else:
                dx[i] = 100 * (abs(plus_di[i] - minus_di[i]) / sum_di)
                
        adx = [None] * n
        dx_start = period
        valid_dxs = [d for d in dx[dx_start : dx_start + period] if d is not None]
        if len(valid_dxs) < period:
            return [None] * n, plus_di, minus_di
            
        adx[dx_start + period - 1] = sum(valid_dxs) / period
        
        for i in range(dx_start + period, n):
            if dx[i] is not None and adx[i-1] is not None:
                adx[i] = (adx[i-1] * (period - 1) + dx[i]) / period
                
        return adx, plus_di, minus_di

    def calculate_macd(self, prices):
        n = len(prices)
        ema12 = self.calculate_ema(prices, 12)
        ema26 = self.calculate_ema(prices, 26)
        
        macd_line = [None] * n
        for i in range(n):
            if ema12[i] is not None and ema26[i] is not None:
                macd_line[i] = ema12[i] - ema26[i]
                
        first_valid = 0
        while first_valid < n and macd_line[first_valid] is None:
            first_valid += 1
            
        signal_line = [None] * n
        if first_valid + 9 <= n:
            macd_valid_sub = macd_line[first_valid:]
            sub_signal = self.calculate_ema(macd_valid_sub, 9)
            for i in range(len(sub_signal)):
                signal_line[first_valid + i] = sub_signal[i]
                
        return macd_line, signal_line

    def generate_deterministic_campaign(self, stock, theme, theme_desc):
        sym = stock['symbol']
        px = stock['price']
        rsi = round(stock['rsi'], 1) if stock.get('rsi') is not None else 50.0
        adx = round(stock.get('adx', 20.0), 1) if stock.get('adx') is not None else 20.0
        dd = stock.get('drawdown', 0.0)
        stance = stock.get('stance', 'Key Support/Resistance')

        if theme == 'patience':
            title = f"The Patience Edge: Why Catching {sym} at Rs {px} Demands Rules, Not Hope"
            q1 = f"With {sym} at Rs {px} down {dd}% from its peak and RSI at {rsi}, do you enter now or wait for base confirmation?"
            q2 = f"If {sym} tests fresh swing lows, would you average down or let stops protect your account?"
            q3 = f"What validates a reversal for you in {sym}: an oversold bounce or price reclaiming its EMA 50?"
            twitter = [
                f"1/4 The most expensive mistake in trading isn't taking a stop loss—it's jumping into an unconfirmed trend out of impatience. Let's analyze {sym} at Rs {px}.\\n\\n#TradeKriya #TradingPsychology #NSE",
                f"2/4 With RSI at {rsi} and a {dd}% peak drawdown, retail traders are tempted to 'bottom fish'. But with ADX at {adx}, trend momentum still carries downside risk.",
                f"3/4 Trapped trader psychology: Impatient bulls cluster stop losses right below key swing lows. Smart systematic money waits for weak hands to get flushed before entering.",
                f"4/4 Patience is your true edge. Don't catch falling knives; let the setup come to you.\\n\\nCast your vote on how you would trade {sym} today: [VOTING_LINK]"
            ]
            linkedin = f"""Trading isn't about being first—it's about having high probability confirmation.

Looking at {sym} currently trading at Rs {px} ({stance}), we see a classic psychological test for market participants. The stock is down {dd}% from recent highs, with an RSI of {rsi} and ADX of {adx}.

Here is what happens under the surface:
• Retail traders feel the psychological itch to buy "at a discount", confusing low price with high value.
• Stop-loss clusters are tightly bunched just under recent lows, leaving late buyers highly vulnerable to liquidity flushes.
• Quantitative discipline dictates that we wait for price micro-structure to confirm higher lows before committing capital.

At TradeKriya, our systems eliminate guesswork by replacing hope with quantitative edges. 

How would you approach {sym} today? Would you be Bullish, Bearish, or Wait for confirmation?
Cast your vote and join the discussion: [VOTING_LINK]

#TradingMindset #QuantitativeTrading #IndianEquities #RiskManagement"""
            telegram = f"""📢 **TradeKriya Market Mindset Alert: {sym}**

🔹 **Ticker:** {sym} | **CMP:** Rs {px}
🔹 **Technical Stance:** {stance} | **RSI:** {rsi} | **Drawdown:** {dd}%
🔹 **Core Theme:** Patience vs Catching Falling Knives

💡 **Psychological Breakdown:**
When stocks undergo prolonged pullbacks, impatience leads to premature entries. Stop losses cluster right below support zones. The disciplined trader waits for volume absorption and trend structure rather than guessing the bottom.

🗳️ **Vote on the Mindset Poll:**
Are you Bullish, Bearish, or Waiting?
👉 Cast your vote here: [VOTING_LINK]"""
            youtube = {
                "visuals_description": f"Dynamic candlestick chart of {sym} on daily timeframe showing recent drop, highlighting Rs {px} level and RSI indicator at {rsi}.",
                "voiceover_script": f"Are you rushing to buy {sym} at Rs {px} just because it looks cheap? With a {dd}% drawdown, impatient traders are piling in. But look at the RSI and ADX: momentum hasn't confirmed a bottom yet. If you buy on hope instead of confirmation, you become liquidity for smart money. Trade the system, not your impatience. Cast your vote on TradeKriya right now!",
                "on_screen_text": f"{sym} at Rs {px}: Bargain or Trap? | Drawdown: {dd}% | Trade Discipline Over Hope"
            }

        elif theme == 'fomo':
            title = f"The FOMO Trap: Why Chasing {sym} at Rs {px} Destroys Risk-Reward"
            q1 = f"With {sym} trading near Rs {px} ({stance}), would you chase the breakout today or wait for a retest?"
            q2 = f"If {sym} gaps up another 2%, does your fear of missing out tempt you to market-buy without a defined stop?"
            q3 = f"Where would you place your stop loss in {sym} to avoid getting trapped by institutional profit-taking?"
            twitter = [
                f"1/4 Chasing green candles is where retail capital goes to vanish. Let's break down the psychological setup on {sym} at Rs {px}.\\n\\n#TradeKriya #FOMO #StockMarketIndia",
                f"2/4 {sym} is currently {stance} with RSI at {rsi}. When a stock rallies hard, traders suffer from Fear Of Missing Out (FOMO), buying right where early smart money looks to take profit.",
                f"3/4 Vulnerability: Late breakout buyers cluster their stops right beneath the breakout bar. If momentum pauses, a quick shakeout triggers their stops instantly.",
                f"4/4 Quantitative rule: Never chase extensions. Wait for base pullbacks with favorable risk-to-reward ratios.\\n\\nAre you chasing, shorting, or waiting? Vote here: [VOTING_LINK]"
            ]
            linkedin = f"""The emotion of FOMO (Fear Of Missing Out) is the single biggest contributor to poor risk-reward trades.

Take {sym}, currently trading at Rs {px} ({stance}, RSI {rsi}). When momentum surges, emotional traders convince themselves that "this stock will never pull back."

Systematic analysis tells a different story:
1. Late buyers are emotionally over-leveraged, entering at the tail end of an impulse wave.
2. Stop-loss clusters sit just below recent pivot levels, creating easy liquidity targets for institutional re-accumulation or profit booking.
3. High-probability systems never buy extended moves—they enter at defined inflection points where risk is strictly capped.

Discipline means being comfortable sitting on your hands when a trade does not meet your entry criteria.

What is your stance on {sym}? 
Vote in our interactive community poll: [VOTING_LINK]

#TradingPsychology #RiskReward #TradeKriya #Discipline"""
            telegram = f"""📢 **TradeKriya Mindset Alert: The FOMO Check on {sym}**

🔹 **Ticker:** {sym} | **CMP:** Rs {px}
🔹 **Technical Stance:** {stance} | **RSI:** {rsi}
🔹 **Theme:** FOMO vs Defined Risk/Reward

💡 **Key Takeaway:**
Buying extended moves near key resistance without confirmation leaves you vulnerable to fast mean reversions. Professional trading is about executing rules, not satisfying the fear of missing out.

🗳️ **Vote on the Setup:**
Bullish, Bearish, or Waiting?
👉 [VOTING_LINK]"""
            youtube = {
                "visuals_description": f"Candlestick chart of {sym} showing extended upward price action to Rs {px}, highlighted resistance bands, and RSI {rsi}.",
                "voiceover_script": f"Did you feel the urge to jump into {sym} today at Rs {px}? That feeling is FOMO, and market makers thrive on it. When retail rushes to buy extended highs, smart money is preparing to lock in gains. Without a strict stop loss and favorable risk-reward, chasing breakouts is a gamble. What's your call on {sym}? Vote on TradeKriya right now!",
                "on_screen_text": f"Don't Chase {sym} at Rs {px}! | Avoid FOMO Traps | Rule-Based Trading"
            }

        elif theme == 'loss_aversion':
            title = f"The Loss Aversion Trap: Why Holding Losing Trades in {sym} Erodes Capital"
            q1 = f"If you entered {sym} higher and are now down {dd}%, would you take the loss cleanly or hold hoping to break even?"
            q2 = f"At Rs {px} (RSI {rsi}), does {sym} offer a genuine mathematical edge or an emotional rationalization to avoid a loss?"
            q3 = f"Would you re-enter {sym} today with fresh capital if you had zero prior positions in it?"
            twitter = [
                f"1/4 Loss aversion: The cognitive bias where the pain of losing is twice as intense as the joy of winning. Look at {sym} at Rs {px}.\\n\\n#TradeKriya #Mindset #TradingPsychology",
                f"2/4 Down {dd}% from its highs with RSI at {rsi}, trapped investors in {sym} often refuse to cut losses. They turn short-term swing trades into unwanted 'long-term investments'.",
                f"3/4 The hidden cost: Not just capital erosion, but opportunity cost. Money trapped in a declining asset is money that cannot compound in high-momentum leaders.",
                f"4/4 Rule: Cut losses fast and let winners run. Your capital is your inventory.\\n\\nHow would you manage {sym} right now? Vote in the TradeKriya poll: [VOTING_LINK]"
            ]
            linkedin = f"""Daniel Kahneman and Amos Tversky proved that human beings feel the emotional pain of a loss twice as intensely as the pleasure of an equivalent gain.

In trading, this bias—Loss Aversion—is lethal.

Consider {sym}, now trading at Rs {px}, reflecting a peak drawdown of {dd}% with RSI {rsi}. 
When a position moves against a trader, the rational response is to honor the predefined stop loss. But loss aversion whispers: "Wait until it gets back to breakeven."

Systematic trading removes this cognitive trap:
• Losses are budgeted business expenses, not personal failures.
• Capital preserved today is ammunition for tomorrow's verified edge.
• Every bar requires asking: "If I held cash today, would I buy this setup right now?"

Are you Bullish, Bearish, or Waiting on {sym}?
Share your perspective in our community poll: [VOTING_LINK]

#TradingPsychology #BehavioralFinance #RiskManagement #TradeKriya"""
            telegram = f"""📢 **TradeKriya Mindset Alert: Loss Aversion in {sym}**

🔹 **Ticker:** {sym} | **Price:** Rs {px}
🔹 **Drawdown:** {dd}% | **RSI:** {rsi} | **Stance:** {stance}
🔹 **Theme:** Loss Aversion & Capital Preservation

💡 **Insight:**
Holding losing positions hoping for a bounce ties up mental energy and trading capital. Professional traders cut losers decisively and redeploy into relative strength.

🗳️ **Participate in the Community Poll:**
👉 Vote on {sym} here: [VOTING_LINK]"""
            youtube = {
                "visuals_description": f"Chart of {sym} highlighting the drawdown from highs down to Rs {px}, with visual stop-loss line crossed and warning indicators.",
                "voiceover_script": f"Are you holding {sym} at Rs {px} just hoping to get your money back? That's loss aversion talking. Waiting for breakeven on a stock down {dd}% traps your capital while leaders make new highs. The first loss is always the cheapest loss. Cut it, reset, and follow the math. Cast your vote on TradeKriya right now!",
                "on_screen_text": f"Stop Hoping for Breakeven! | {sym} at Rs {px} | Cut Losses decisively"
            }

        elif theme == 'failed_breakout':
            title = f"The Anatomy of a Bull Trap: Dissecting the Failed Breakout in {sym}"
            q1 = f"If {sym} breaks resistance at Rs {px} and immediately slips back into range, do you exit or give it 'room to breathe'?"
            q2 = f"Where are the stop-loss clusters located for breakout buyers currently trapped in {sym}?"
            q3 = f"How many confirmation closes above the breakout level does your trading ruleset require before sizing up?"
            twitter = [
                f"1/4 Bull traps don't just cost money—they shake your psychological confidence. Case study on {sym} at Rs {px}.\\n\\n#TradeKriya #BullTrap #PriceAction",
                f"2/4 When {sym} pushed near resistance, buyers piled in aggressively. But lack of volume expansion turned the move into a false breakout.",
                f"3/4 Who is emotionally trapped? Breakout buyers who entered late are now sitting on paper losses with stops clustered right under key swing pivots.",
                f"4/4 In trading, rule #1 on false breakouts is quick defense. How would you handle {sym} right now? Vote on TradeKriya: [VOTING_LINK]"
            ]
            linkedin = f"""A failed breakout is one of the most psychologically punishing events for trend followers.

When {sym} tested key resistance levels near Rs {px} ({stance}), optimism surged. But markets move on liquidity, not optimism. 

When a breakout fails to attract follow-through buying:
1. Eager buyers get trapped at the absolute top of the range.
2. Stop-loss clusters form just below the breakout zone, creating a magnet for institutional sellers.
3. Denial turns into panic as price slips back inside the trading range.

Systematic traders recognize bull traps early, cut risk instantly, and often flip to defensive posture.

Are you Bullish, Bearish, or Waiting on {sym}? 
Vote in our community poll: [VOTING_LINK]

#MarketPsychology #PriceAction #BullTraps #RiskFirst"""
            telegram = f"""📢 **TradeKriya Alert: Anatomy of a Bull Trap in {sym}**

🔹 **Ticker:** {sym} | **Price:** Rs {px}
🔹 **Stance:** {stance} | **RSI:** {rsi}
🔹 **Theme:** Failed Breakouts & Trapped Buyers

💡 **Key Takeaway:**
When a breakout stalls without institutional volume, trapped buyers become future sellers. Protect capital before the stop cascade begins.

🗳️ **Vote on {sym}:**
👉 [VOTING_LINK]"""
            youtube = {
                "visuals_description": f"Candlestick chart of {sym} showing a breakout candle poking above resistance at Rs {px} followed by immediate rejection back into range.",
                "voiceover_script": f"Did {sym} lure you into a bull trap at Rs {px}? When breakouts fail, amateur traders freeze in shock, while systematic traders exit immediately. The stops beneath the range are about to trigger. Don't let hope replace risk management. What is your move on {sym}? Vote on TradeKriya now!",
                "on_screen_text": f"Bull Trap Warning in {sym} | Don't Get Trapped at Resistance | TradeKriya"
            }

        elif theme == 'failed_breakdown':
            title = f"The Bear Trap: How Smart Money Punishes Panic Sellers in {sym}"
            q1 = f"When {sym} pierced support at Rs {px} only to recover sharply, did you panic sell or look for a bear trap reclaim?"
            q2 = f"Where are short sellers' stop losses clustered now as {sym} pushes back above key levels?"
            q3 = f"Does your playbook allow buying a failed breakdown with tight risk under the reclaim candle?"
            twitter = [
                f"1/4 Panic is the ultimate liquidity provider for smart money. Let's look at the bear trap dynamics in {sym} (CMP: Rs {px}).\\n\\n#TradeKriya #BearTrap #TradingMindset",
                f"2/4 When {sym} dipped below support, emotional bears rushed to short, while fearful holders capitulated right into institutional bids.",
                f"3/4 The reversal: Trapped short sellers now face rising prices with stops clustered right above the range highs. A short squeeze looms.",
                f"4/4 Recognize where emotion drives retail action. What would you do in {sym} today? Cast your vote on TradeKriya: [VOTING_LINK]"
            ]
            linkedin = f"""Bear traps are a masterclass in market psychology and liquidity hunting.

In {sym} at Rs {px} ({stance}, RSI {rsi}), the test of support triggered classical emotional responses:
• Fearful long positions capitulated at the worst possible price.
• Late breakdown short-sellers jumped in aggressively without waiting for candle close validation.
• Once sell stops were harvested, aggressive institutional bids pushed the price straight back into the value zone.

Now the tables have turned: the bears are trapped, and their buy-stops sit clustered above recent highs.

Are you Bullish, Bearish, or Waiting on {sym}?
Cast your vote on TradeKriya: [VOTING_LINK]

#BearTraps #InstitutionalLiquidity #TradingPsychology #TradeKriya"""
            telegram = f"""📢 **TradeKriya Alert: Bear Trap Dynamics in {sym}**

🔹 **Ticker:** {sym} | **CMP:** Rs {px}
🔹 **Stance:** {stance} | **RSI:** {rsi}
🔹 **Theme:** Failed Breakdown & Trapped Bears

💡 **Insight:**
Selling in panic often delivers cheap shares directly into smart money hands. Watch for the reclaim of support as trapped shorts scramble to cover.

🗳️ **Mindset Poll:**
👉 [VOTING_LINK]"""
            youtube = {
                "visuals_description": f"Candlestick chart of {sym} showing a breakdown wick below support followed by an engulfing green candle back into range.",
                "voiceover_script": f"Did {sym} trick you into panic selling at Rs {px}? When support breaks and immediately snaps back, that is a classic bear trap. Weak hands gave up their shares, and now trapped shorts are forced to cover. Trade the liquidity, not the fear. Vote your stance on TradeKriya now!",
                "on_screen_text": f"Bear Trap in {sym}? | Smart Money vs Panic Sellers | TradeKriya"
            }

        elif theme == 'sudden_reversal':
            title = f"The Shock of Trend Reversals: Navigating Volatility in {sym}"
            q1 = f"When {sym} experiences a sudden reversal at Rs {px}, do you adjust your position size immediately or freeze in shock?"
            q2 = f"Are your stops trailing mechanically, or does a sudden market shift catch you unprepared?"
            q3 = f"How do you distinguish a genuine regime change in {sym} from a temporary volatility spike?"
            twitter = [
                f"1/4 Nothing tests trader psychology like a violent reversal. Analyzing {sym} at Rs {px}.\\n\\n#TradeKriya #Volatility #TradingRules",
                f"2/4 When an established trend suddenly turns, traders experience the classic grief cycle: denial, anger, bargaining, and finally capitulation.",
                f"3/4 Having pre-set trailing stops and volatility-adjusted sizing turns chaos into a managed business event.",
                f"4/4 Sticking to rules in volatile moments is what preserves long-term edge. What is your view on {sym}? Vote here: [VOTING_LINK]"
            ]
            linkedin = f"""Sudden trend reversals are the ultimate stress tests for any trading system.

Looking at {sym} at Rs {px} ({stance}), rapid shifts in momentum create emotional shockwaves:
1. Denial: "It's just a temporary dip."
2. Rationalization: Seeking bullish news to justify holding through adverse moves.
3. Capitulation: Selling at the exact point of maximum despair.

Systematic traders don't rely on emotional composure alone—they rely on automated risk parameters, predetermined trailing exits, and hard stop losses.

How do you view {sym} today? 
Cast your vote on TradeKriya: [VOTING_LINK]

#RiskManagement #TrendReversals #TradingSystem #TradeKriya"""
            telegram = f"""📢 **TradeKriya Alert: Reversal Mindset in {sym}**

🔹 **Ticker:** {sym} | **Price:** Rs {px}
🔹 **Stance:** {stance} | **RSI:** {rsi}
🔹 **Theme:** Sudden Trend Reversals & Risk Control

💡 **Takeaway:**
When momentum flips abruptly, rule-based trailing stops protect months of accumulated profit. Don't debate the tape—respect the price action.

🗳️ **Vote on {sym}:**
👉 [VOTING_LINK]"""
            youtube = {
                "visuals_description": f"Chart of {sym} illustrating an abrupt momentum shift at Rs {px} with trailing stop levels highlighted.",
                "voiceover_script": f"When {sym} reverses suddenly at Rs {px}, will your rules protect you or will shock paralyze you? Sharp market reversals punish complacency. If you don't have hard trailing stops, the market will decide your risk for you. Protect your capital first. Cast your vote on TradeKriya right now!",
                "on_screen_text": f"Sudden Reversal in {sym}! | Protect Your Gains | Systematic Risk Rules"
            }

        else: # discipline (default)
            title = f"The Discipline Blueprint: How Sticking to Rules in {sym} Builds Long-Term Edge"
            q1 = f"With {sym} trading at Rs {px} ({stance}, RSI {rsi}), does your system give a validated trigger or are you trading on intuition?"
            q2 = f"If {sym} hits your stop loss tomorrow, will you execute without hesitation or negotiate with the market?"
            q3 = f"What matters more in your trading of {sym}: win rate or strictly respecting your risk-reward ratio?"
            twitter = [
                f"1/4 Consistency in trading doesn't come from market predictions. It comes from disciplined execution. Here is a case study on {sym} (CMP: Rs {px}).\\n\\n#TradeKriya #Discipline #SystematicTrading",
                f"2/4 Trading at Rs {px} ({stance}), {sym} tests the patience and discipline of both bulls and bears. RSI stands at {rsi} and ADX at {adx}.",
                f"3/4 Emotional traders look for excitement. Systematic traders look for rule confirmation: defined entries, position sizing, and non-negotiable exit stops.",
                f"4/4 Sticking to your rules protects your capital in bad regimes and lets profits run in favorable trends.\\n\\nWhat is your stance on {sym}? Vote in the TradeKriya poll: [VOTING_LINK]"
            ]
            linkedin = f"""The difference between amateur trading and professional portfolio management is a single word: Discipline.

Looking at {sym} at Rs {px} ({stance}, RSI {rsi}, ADX {adx}), every trader sees a different narrative. The amateur looks for confirmation of their personal bias. The systematic trader asks: "Does this setup satisfy my validated rules?"

Key pillars of disciplined execution:
1. Strict Entry Criteria: No trade without validated technical edge and volume confirmation.
2. Invariable Stop Losses: Defined before entering, executed without debate.
3. Process Over Outcome: Evaluating trades by whether rules were followed, not just immediate P&L.

How would you trade {sym} today? 
Cast your vote on TradeKriya's community poll: [VOTING_LINK]

#SystematicTrading #TradingDiscipline #EquityMarkets #RiskControl"""
            telegram = f"""📢 **TradeKriya Market Mindset Alert: Discipline in {sym}**

🔹 **Ticker:** {sym} | **CMP:** Rs {px}
🔹 **Stance:** {stance} | **RSI:** {rsi} | **ADX:** {adx}
🔹 **Theme:** Systematic Discipline & Risk Rules

💡 **Takeaway:**
Great traders don't predict the future; they execute rules with machine-like consistency. Protect your downside, respect your stops, and let mathematics work in your favor.

🗳️ **Vote on {sym}:**
Bullish, Bearish, or Wait?
👉 [VOTING_LINK]"""
            youtube = {
                "visuals_description": f"Clean technical chart of {sym} at Rs {px} showing moving averages and disciplined risk-reward trade setup brackets.",
                "voiceover_script": f"In trading, you don't rise to the level of your hopes; you fall to the level of your discipline. At Rs {px}, {sym} presents an interesting setup. But before placing an order, do you have your exact stop loss and profit target defined? Sticking to your system is what separates traders from gamblers. Cast your vote on TradeKriya right now!",
                "on_screen_text": f"Trade the Plan, Not the Emotion | {sym} at Rs {px} | Rules First"
            }

        return {
            "title": title,
            "question_1": q1,
            "question_2": q2,
            "question_3": q3,
            "twitter_thread": twitter,
            "linkedin_post": linkedin,
            "telegram_digest": telegram,
            "youtube_shorts_script": youtube
        }
