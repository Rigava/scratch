import os
import json
import datetime
from pathlib import Path
import pandas as pd
import numpy as np
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Computes second-order quantitative scores (Absorption, Exhaustion, VCP) and ranks stocks.'

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, default='2026-08-28', help='Evaluation date in YYYY-MM-DD format')
        parser.add_argument('--out-dir', type=str, default=None, help='Directory path to write markdown report to')

    def handle(self, *args, **options):
        self.stdout.write("====================================================")
        self.stdout.write("    Quant Insights: Second-Order Screener & Ranking ")
        self.stdout.write("====================================================\n")

        # 1. Path to historical data dump
        base_dir = Path(__file__).resolve().parent.parent.parent
        db_path = base_dir / 'data' / 'fo_historical_dump.json'

        if not db_path.exists():
            self.stdout.write(self.style.ERROR(f"[ERROR] Database dump file not found at {db_path}"))
            self.stdout.write("[INFO] Please run 'python manage.py dump_fo_data' first to fetch stock data.")
            return

        # 2. Read the dump
        with open(db_path, 'r', encoding='utf-8') as f:
            dump_data = json.load(f)

        if not dump_data:
            self.stdout.write(self.style.ERROR("[ERROR] The historical dump database is empty."))
            return

        self.stdout.write(f"[INFO] Loaded historical data for {len(dump_data)} symbols.")

        # 3. Preprocess Data and Create DataFrames
        dfs = {}
        for symbol, candles in dump_data.items():
            if not candles:
                continue
            df = pd.DataFrame(candles, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
            df['date'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            df.set_index('date', inplace=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.sort_index(inplace=True)
            dfs[symbol] = df

        nifty_df = dfs.get('NIFTY 50')
        if nifty_df is None:
            self.stdout.write(self.style.ERROR("[ERROR] NIFTY 50 benchmark not found in historical dump."))
            return

        nifty_df['market_return'] = nifty_df['close'].pct_change()

        # 4. Calculate Rolling Indicators and Beta for Stocks
        for symbol, df in dfs.items():
            if symbol == 'NIFTY 50' or 'NIFTY' in symbol:
                continue
            
            # Daily return
            df['return'] = df['close'].pct_change()
            
            # Align with market returns
            df = df.join(nifty_df['market_return'], how='left')
            
            # Rolling Beta (60-day window)
            covariance = df['return'].rolling(60).cov(df['market_return'])
            market_variance = df['market_return'].rolling(60).var()
            df['beta'] = covariance / market_variance
            df['beta'] = df['beta'].fillna(1.0) # Fallback to beta = 1
            
            # Residual return
            df['residual_return'] = df['return'] - df['beta'] * df['market_return']
            
            # Close Location Value (CLV)
            hl_range = df['high'] - df['low']
            df['clv'] = ((df['close'] - df['low']) - (df['high'] - df['close'])) / hl_range
            df['clv'] = df['clv'].fillna(0.0)
            
            # Volume Indicators
            vol_mean = df['volume'].rolling(20).mean()
            vol_std = df['volume'].rolling(20).std().replace(0, 1e-6)
            df['vol_ratio'] = df['volume'] / vol_mean.replace(0, 1e-6)
            df['vol_z'] = (df['volume'] - vol_mean) / vol_std
            
            # Spread Indicators
            df['spread'] = df['high'] - df['low']
            spread_mean = df['spread'].rolling(20).mean()
            spread_std = df['spread'].rolling(20).std().replace(0, 1e-6)
            df['spread_z'] = (df['spread'] - spread_mean) / spread_std
            
            # Trend indicator (10-day EMA)
            df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
            
            dfs[symbol] = df

        # Parse evaluation date
        target_date_str = options['date']
        try:
            eval_date = pd.to_datetime(target_date_str)
        except Exception:
            self.stdout.write(self.style.ERROR(f"[ERROR] Invalid date format: {target_date_str}"))
            return

        if eval_date not in nifty_df.index:
            self.stdout.write(self.style.ERROR(f"[ERROR] Evaluation date {target_date_str} not found in Nifty index dates."))
            return

        # 5. Evaluate and Rank Outcomes

        # A. Institutional Liquidity Absorption
        # Find the most recent market down day (return < -0.003) relative to the eval_date
        past_dates = nifty_df.loc[:eval_date].index
        down_days = nifty_df.loc[past_dates][nifty_df.loc[past_dates, 'market_return'] < -0.003].index
        if len(down_days) > 0:
            abs_eval_date = down_days[-1]
        else:
            abs_eval_date = nifty_df.loc[past_dates, 'market_return'].idxmin()

        market_ret_abs = nifty_df.loc[abs_eval_date, 'market_return']
        self.stdout.write(f"[INFO] Institutional Absorption evaluated on: {abs_eval_date.date()} (Nifty 50 Return: {market_ret_abs*100:.2f}%)")

        # B. Volatility Contraction Pattern (VCP)
        vcp_eval_date = eval_date
        self.stdout.write(f"[INFO] Volatility Contraction Pattern evaluated on: {vcp_eval_date.date()}")

        # C. Behavioral Exhaustion
        # Look back 5 trading days up to eval_date
        idx_pos = nifty_df.index.get_loc(eval_date)
        start_idx = max(0, idx_pos - 4)
        exh_lookback_dates = nifty_df.index[start_idx:idx_pos + 1]
        self.stdout.write(f"[INFO] Behavioral Exhaustion evaluated over 5 days: {[d.strftime('%Y-%m-%d') for d in exh_lookback_dates]}")

        absorption_results = []
        bearish_exh_results = []
        bullish_exh_results = []
        vcp_results = []

        # Calculate scores
        for symbol, df in dfs.items():
            if symbol == 'NIFTY 50' or 'NIFTY' in symbol:
                continue

            # 1. Institutional Absorption
            if abs_eval_date in df.index:
                row = df.loc[abs_eval_date]
                if row['return'] >= 0:
                    abs_score = row['residual_return'] * row['vol_ratio'] * (1 + row['clv'])
                    absorption_results.append({
                        'Symbol': symbol,
                        'Price': row['close'],
                        'Stock Return (%)': round(row['return'] * 100, 2),
                        'Residual Return (%)': round(row['residual_return'] * 100, 2),
                        'Volume Ratio': round(row['vol_ratio'], 2),
                        'CLV': round(row['clv'], 2),
                        'Absorption Score': round(abs_score, 4)
                    })

            # 2. Behavioral Exhaustion (Lookback)
            for d in exh_lookback_dates:
                if d in df.index:
                    row = df.loc[d]
                    if row['vol_z'] > 1.2 and row['spread_z'] > 0.8:
                        # Bearish Capitulation
                        if row['close'] < row['ema10'] and row['clv'] > 0.2:
                            bear_score = row['vol_z'] * row['spread_z'] * row['clv']
                            bearish_exh_results.append({
                                'Date': d.strftime('%Y-%m-%d'),
                                'Symbol': symbol,
                                'Price': row['close'],
                                'Volume Z-Score': round(row['vol_z'], 2),
                                'Spread Z-Score': round(row['spread_z'], 2),
                                'CLV': round(row['clv'], 2),
                                'Bearish Exhaustion Score': round(bear_score, 2)
                            })
                        # Bullish Capitulation
                        elif row['close'] > row['ema10'] and row['clv'] < -0.2:
                            bull_score = row['vol_z'] * row['spread_z'] * (-row['clv'])
                            bullish_exh_results.append({
                                'Date': d.strftime('%Y-%m-%d'),
                                'Symbol': symbol,
                                'Price': row['close'],
                                'Volume Z-Score': round(row['vol_z'], 2),
                                'Spread Z-Score': round(row['spread_z'], 2),
                                'CLV': round(row['clv'], 2),
                                'Bullish Exhaustion Score': round(bull_score, 2)
                            })

            # 3. Volatility Contraction Pattern (VCP)
            if vcp_eval_date in df.index:
                row = df.loc[vcp_eval_date]
                sub_df = df.loc[:vcp_eval_date].tail(20)
                if len(sub_df) == 20:
                    high_20 = sub_df['close'].max()
                    dist_from_high = (high_20 - row['close']) / high_20
                    
                    vol_5d = sub_df['return'].tail(5).std()
                    vol_20d = sub_df['return'].std()
                    
                    avg_vol_5d = sub_df['volume'].tail(5).mean()
                    avg_vol_20d = sub_df['volume'].mean()
                    
                    if vol_20d > 0 and avg_vol_20d > 0:
                        vol_comp = (vol_20d - vol_5d) / vol_20d
                        volu_cont = 1.0 - (avg_vol_5d / avg_vol_20d)
                        
                        if vol_comp > 0 and volu_cont > 0 and dist_from_high < 0.05:
                            vcp_score = vol_comp * volu_cont * (1.0 - dist_from_high)
                            vcp_results.append({
                                'Symbol': symbol,
                                'Price': row['close'],
                                'Dist from High (%)': round(dist_from_high * 100, 2),
                                'Vol Comp (%)': round(vol_comp * 100, 2),
                                'Volume Contraction (%)': round(volu_cont * 100, 2),
                                'VCP Score': round(vcp_score, 4)
                            })

        # DataFrames and Sorting
        abs_df = pd.DataFrame(absorption_results)
        if not abs_df.empty:
            abs_df = abs_df.sort_values(by='Absorption Score', ascending=False)

        bear_df = pd.DataFrame(bearish_exh_results)
        if not bear_df.empty:
            bear_df = bear_df.sort_values(by='Bearish Exhaustion Score', ascending=False)

        bull_df = pd.DataFrame(bullish_exh_results)
        if not bull_df.empty:
            bull_df = bull_df.sort_values(by='Bullish Exhaustion Score', ascending=False)

        vcp_df = pd.DataFrame(vcp_results)
        if not vcp_df.empty:
            vcp_df = vcp_df.sort_values(by='VCP Score', ascending=False)

        # Print output to CLI
        self.stdout.write(self.style.SUCCESS("\n=== TOP 5 STOCKS: INSTITUTIONAL LIQUIDITY ABSORPTION ==="))
        if not abs_df.empty:
            self.stdout.write(abs_df.head(5).to_string(index=False))
        else:
            self.stdout.write("No setups found.")

        self.stdout.write(self.style.SUCCESS("\n=== TOP 5 STOCKS: BEARISH CAPITULATION (SELLING EXHAUSTION) ==="))
        if not bear_df.empty:
            self.stdout.write(bear_df.head(5).to_string(index=False))
        else:
            self.stdout.write("No setups found.")

        self.stdout.write(self.style.SUCCESS("\n=== TOP 5 STOCKS: BULLISH CAPITULATION (BUYING EXHAUSTION) ==="))
        if not bull_df.empty:
            self.stdout.write(bull_df.head(5).to_string(index=False))
        else:
            self.stdout.write("No setups found.")

        self.stdout.write(self.style.SUCCESS("\n=== TOP 5 STOCKS: VOLATILITY CONTRACTION (VCP) ==="))
        if not vcp_df.empty:
            self.stdout.write(vcp_df.head(5).to_string(index=False))
        else:
            self.stdout.write("No setups found.")

        # Create markdown report content
        report_md = f"""# Quant Insights: Second-Order Market Observations
Report date: **{eval_date.strftime('%Y-%m-%d')}**

This report ranks stocks based on second-order market structures, behavior, and microstructure rather than retail charts.

## 1. Institutional Liquidity Absorption
*Calculated on the most recent market down day:* **{abs_eval_date.strftime('%Y-%m-%d')}** *when Nifty 50 returned* **{market_ret_abs*100:.2f}%**.
*Logic:* Detects stocks that close green on high relative volume and high CLV when the market drops, signifying strong institutional absorption.

{abs_df.head(10).to_markdown(index=False) if not abs_df.empty else "*No setups found.*"}

## 2. Behavioral Exhaustion
*Calculated over the last 5 trading days ending:* **{eval_date.strftime('%Y-%m-%d')}**
*Logic:* Identifies extreme volume expansions on wide daily ranges that close near their highs (Selling Climax) or lows (Buying Climax), representing transfer of ownership.

### Bearish Capitulation (Selling Climax Reversals)
{bear_df.head(10).to_markdown(index=False) if not bear_df.empty else "*No setups found.*"}

### Bullish Capitulation (Buying Climax Reversals / Blow-off Tops)
{bull_df.head(10).to_markdown(index=False) if not bull_df.empty else "*No setups found.*"}

## 3. Volatility Contraction Pattern (VCP)
*Calculated on:* **{vcp_eval_date.strftime('%Y-%m-%d')}**
*Logic:* Measures volatility compression (ATR reduction) and volume drying up near 20-day highs, signaling supply absorption before breakouts.

{vcp_df.head(10).to_markdown(index=False) if not vcp_df.empty else "*No setups found.*"}
"""

        # Write Report to file if out-dir is specified
        out_dir = options['out_dir']
        if out_dir:
            out_path = Path(out_dir) / f"second_order_rankings.md"
            os.makedirs(out_dir, exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(report_md)
            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Markdown report written to: {out_path}"))
