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
        parser.add_argument('--theme', type=str, default=None, choices=['patience', 'discipline', 'fomo', 'loss_aversion'], help='Focus trading psychology theme')

    def handle(self, *args, **options):
        self.stdout.write("====================================================")
        self.stdout.write("       TradeKriya Marketing & Insights Agent        ")
        self.stdout.write("====================================================\n")

        # 1. Force reload env to capture API keys
        load_env_file(force=True)
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            self.stdout.write(self.style.ERROR("[ERROR] GEMINI_API_KEY is not defined in the server's .env file."))
            return

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
        theme = options['theme']

        if target_symbol:
            for item in scanned_results:
                if item['symbol'] == target_symbol:
                    selected_stock = item
                    break
            if not selected_stock:
                self.stdout.write(self.style.WARNING(f"[WARNING] Target symbol '{target_symbol}' was not found or lacks sufficient candles in the database."))
                return
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

        theme_descriptions = {
            'patience': 'Patience: Waiting for trend validation rather than jumping in early on a "cheap" asset (avoiding falling knives).',
            'discipline': 'Discipline: Sticking to rule-based setups (such as validated MACD crossovers) and utilizing strict exit stop losses rather than trading on emotions.',
            'fomo': 'FOMO (Fear Of Missing Out): Chasing breakouts blindly without volume/micro-structure confirmation.',
            'loss_aversion': 'Loss Aversion: The psychological bias that causes traders to hold losing trades, hoping to break even, instead of cutting losses cleanly.'
        }

        selected_theme_desc = theme_descriptions.get(theme, theme_descriptions['patience'])

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
        - Address the psychological values of trading (Patience, Discipline, or emotional biases like Loss Aversion and FOMO).
        - DO NOT make a boring data dump. The post must focus on the mindset, using the stock's indicators only to illustrate the lesson.
        - Create EXACTLY 4 drafts:
          1. Twitter/X Thread (3-4 tweets. Start with an emotional or psychological hook, explain the setup as a lesson, and call to action to scan with TradeKriya).
          2. LinkedIn Post (A detailed professional, storytelling post discussing the mindset required for trading, risk management, and quantitative systems).
          3. Telegram Alert (A concise bulleted digest with a clear takeaway on discipline).
          4. YouTube Shorts / Reels Script (A 60-second video script with visual instructions, spoken narration, and text overlays that illustrate the psychological lesson using the stock's chart behavior).
        
        Return the result in JSON format conforming strictly to this JSON schema:
        {{
            "title": "Title of the Campaign",
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

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
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
                    "required": ["title", "twitter_thread", "linkedin_post", "telegram_digest", "youtube_shorts_script"]
                }
            }
        }

        self.stdout.write("[INFO] Submitting payload to Gemini API...")
        try:
            response = requests.post(url, headers=headers, json=body, timeout=20)
            if response.status_code == 200:
                result_json = response.json()
                content = result_json['candidates'][0]['content']['parts'][0]['text']
                campaign = json.loads(content)

                self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Successfully generated campaign: {campaign['title']}"))
                
                # Create marketing_campaigns at project root (parent of screener app)
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

                # Auto-Publish to Community Use Cases DB
                try:
                    from screener.models import CommunityPost
                    CommunityPost.objects.create(
                        title=campaign['title'],
                        stock_symbol=selected_stock['symbol'],
                        theme=theme,
                        theme_display=selected_theme_desc,
                        twitter_thread_json=json.dumps(campaign['twitter_thread']),
                        linkedin_post=campaign['linkedin_post'],
                        telegram_digest=campaign['telegram_digest'],
                        youtube_shorts_script_json=json.dumps(campaign['youtube_shorts_script'])
                    )
                    self.stdout.write(self.style.SUCCESS("[SUCCESS] Campaign successfully published to public Community section database."))
                except Exception as db_err:
                    self.stdout.write(self.style.ERROR(f"[ERROR] Failed to auto-publish campaign to database: {str(db_err)}"))

                self.stdout.write(self.style.SUCCESS(f"[SUCCESS] Draft archived successfully at: {draft_path}"))
                self.stdout.write("====================================================\n")
                ascii_preview = md_content[:1500].encode('ascii', 'ignore').decode('ascii')
                self.stdout.write(ascii_preview + "\n... (remaining content saved to file) ...")
            else:
                self.stdout.write(self.style.ERROR(f"[ERROR] Gemini API failed (HTTP {response.status_code}): {response.text}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[ERROR] Error communicating with Gemini API: {str(e)}"))

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
