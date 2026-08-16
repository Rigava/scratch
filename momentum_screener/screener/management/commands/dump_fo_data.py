import os
import json
import requests
import datetime
from django.core.management.base import BaseCommand
from pathlib import Path
from screener.views import SYMBOL_TO_TOKEN

class Command(BaseCommand):
    help = 'Fetches or updates the offline simulation Nifty F&O candle database'

    def handle(self, *args, **options):
        api_key = os.environ.get('ZERODHA_API_KEY')
        access_token = os.environ.get('ZERODHA_ACCESS_TOKEN')

        if not api_key or not access_token:
            self.stdout.write(self.style.ERROR('Zerodha credentials missing from .env'))
            return

        data_dir = os.path.join(Path(__file__).resolve().parent.parent.parent, 'data')
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, 'fo_historical_dump.json')

        existing_dump = {}
        if os.path.exists(db_path):
            with open(db_path, 'r', encoding='utf-8') as f:
                existing_dump = json.load(f)

        today_str = datetime.date.today().strftime('%Y-%m-%d')
        sync_count = 0
        updated = []

        for symbol, token in SYMBOL_TO_TOKEN.items():
            candles = existing_dump.get(symbol, [])
            if candles:
                last_candle = candles[-1]
                last_date_str = last_candle[0].split('T')[0]
                if last_date_str >= today_str:
                    continue
                last_date = datetime.datetime.strptime(last_date_str, '%Y-%m-%d').date()
                start_date = last_date + datetime.timedelta(days=1)
            else:
                start_date = datetime.date.today() - datetime.timedelta(days=5 * 365)

            start_str = start_date.strftime('%Y-%m-%d')
            self.stdout.write(f"Syncing {symbol} from {start_str}...")

            url = f"https://api.kite.trade/instruments/historical/{token}/day"
            headers = {
                'X-Kite-Version': '3',
                'Authorization': f'token {api_key}:{access_token}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }
            params = {'from': start_str, 'to': today_str}

            try:
                response = requests.get(url, headers=headers, params=params, timeout=12)
                if response.status_code == 200:
                    new_candles = response.json().get('data', {}).get('candles', [])
                    if new_candles:
                        if not candles:
                            candles = new_candles
                        else:
                            existing_dates = {c[0].split('T')[0] for c in candles}
                            for nc in new_candles:
                                d_str = nc[0].split('T')[0]
                                if d_str not in existing_dates:
                                    candles.append(nc)
                        existing_dump[symbol] = candles
                        sync_count += len(new_candles)
                        updated.append(symbol)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error syncing {symbol}: {str(e)}"))

        if updated:
            with open(db_path, 'w', encoding='utf-8') as f:
                json.dump(existing_dump, f)
            self.stdout.write(self.style.SUCCESS(f"Successfully synced {len(updated)} stocks, {sync_count} candles."))
        else:
            self.stdout.write(self.style.SUCCESS("All stocks are already up to date."))
