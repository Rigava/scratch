import json
import pandas as pd
import numpy as np

def run_test():
    # 1. Load historical F&O dump
    db_path = 'screener/data/fo_historical_dump.json'
    with open(db_path, 'r', encoding='utf-8') as f:
        dump_data = json.load(f)

    print(f"Loaded {len(dump_data)} symbols from historical dump.")

    # 2. Preprocess Data and Create DataFrames
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

    print(f"Parsed {len(dfs)} active DataFrames.")

    # 3. Extract Market Benchmark (Nifty 50) Returns
    nifty_df = dfs.get('NIFTY 50')
    if nifty_df is not None:
        nifty_df['market_return'] = nifty_df['close'].pct_change()
        print("Nifty 50 benchmark returns computed successfully.")
        print(nifty_df[['close', 'market_return']].tail(3))
    else:
        print("NIFTY 50 not found in database! Please check the keys.")
        return

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
        # Handle zero range (flat candles)
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
        df['atr'] = df['spread'].rolling(20).mean()
        
        # Trend indicator (10-day EMA)
        df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()
        
        # Save back
        dfs[symbol] = df

    eval_date = pd.to_datetime('2026-08-28')
    print(f"\nEvaluating scores for target date: {eval_date.date()}")

    absorption_results = []
    bearish_exh_results = []
    bullish_exh_results = []
    vcp_results = []

    # Find the most recent market down day for Institutional Absorption
    down_days = nifty_df[nifty_df['market_return'] < -0.003].index
    if len(down_days) > 0:
        abs_eval_date = down_days[-1]
    else:
        abs_eval_date = nifty_df['market_return'].idxmin()
    
    market_ret_abs = nifty_df.loc[abs_eval_date, 'market_return']
    print(f"\nInstitutional Liquidity Absorption evaluated on most recent market down day: {abs_eval_date.date()} (Nifty 50 return: {market_ret_abs*100:.3f}%)")

    # VCP evaluated on the latest date
    vcp_eval_date = nifty_df.index[-1]
    print(f"Volatility Contraction Pattern evaluated on latest date: {vcp_eval_date.date()}")

    # Behavioral Exhaustion evaluated over the last 5 trading days
    exh_lookback_dates = nifty_df.index[-5:]
    print(f"Behavioral Exhaustion evaluated over the last 5 days: {[d.strftime('%Y-%m-%d') for d in exh_lookback_dates]}")

    absorption_results = []
    bearish_exh_results = []
    bullish_exh_results = []
    vcp_results = []

    # 1. Institutional Liquidity Absorption
    for symbol, df in dfs.items():
        if symbol == 'NIFTY 50' or 'NIFTY' in symbol:
            continue
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

    # 2. Behavioral Exhaustion (over last 5 days)
    for eval_date in exh_lookback_dates:
        for symbol, df in dfs.items():
            if symbol == 'NIFTY 50' or 'NIFTY' in symbol:
                continue
            if eval_date not in df.index:
                continue
            row = df.loc[eval_date]
            if row['vol_z'] > 1.2 and row['spread_z'] > 0.8:
                # Bearish Capitulation
                if row['close'] < row['ema10'] and row['clv'] > 0.2:
                    bear_score = row['vol_z'] * row['spread_z'] * row['clv']
                    bearish_exh_results.append({
                        'Date': eval_date.strftime('%Y-%m-%d'),
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
                        'Date': eval_date.strftime('%Y-%m-%d'),
                        'Symbol': symbol,
                        'Price': row['close'],
                        'Volume Z-Score': round(row['vol_z'], 2),
                        'Spread Z-Score': round(row['spread_z'], 2),
                        'CLV': round(row['clv'], 2),
                        'Bullish Exhaustion Score': round(bull_score, 2)
                    })

    # 3. Volatility Contraction Pattern (latest date)
    for symbol, df in dfs.items():
        if symbol == 'NIFTY 50' or 'NIFTY' in symbol:
            continue
        if vcp_eval_date not in df.index:
            continue
        row = df.loc[vcp_eval_date]
        sub_df = df.loc[:vcp_eval_date].tail(20)
        if len(sub_df) == 20:
            high_20 = sub_df['close'].max()
            dist_from_high = (high_20 - row['close']) / high_20
            
            # Volatility of last 5 days vs 20 days
            vol_5d = sub_df['return'].tail(5).std()
            vol_20d = sub_df['return'].std()
            
            # Volume of last 5 days vs 20 days
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

    abs_df = pd.DataFrame(absorption_results)
    if not abs_df.empty:
        abs_df = abs_df.sort_values(by='Absorption Score', ascending=False)
        print("\n=== TOP 5 STOCKS: INSTITUTIONAL LIQUIDITY ABSORPTION ===")
        print(abs_df.head(5).to_string(index=False))
    else:
        print("\n=== TOP 5 STOCKS: INSTITUTIONAL LIQUIDITY ABSORPTION ===\nNo triggers found.")

    bear_df = pd.DataFrame(bearish_exh_results)
    if not bear_df.empty:
        bear_df = bear_df.sort_values(by='Bearish Exhaustion Score', ascending=False)
        print("\n=== TOP 5 STOCKS: BEARISH CAPITULATION (SELLING EXHAUSTION) ===")
        print(bear_df.head(5).to_string(index=False))
    else:
        print("\n=== TOP 5 STOCKS: BEARISH CAPITULATION (SELLING EXHAUSTION) ===\nNo triggers found.")

    bull_df = pd.DataFrame(bullish_exh_results)
    if not bull_df.empty:
        bull_df = bull_df.sort_values(by='Bullish Exhaustion Score', ascending=False)
        print("\n=== TOP 5 STOCKS: BULLISH CAPITULATION (BUYING EXHAUSTION) ===")
        print(bull_df.head(5).to_string(index=False))
    else:
        print("\n=== TOP 5 STOCKS: BULLISH CAPITULATION (BUYING EXHAUSTION) ===\nNo triggers found.")

    vcp_df = pd.DataFrame(vcp_results)
    if not vcp_df.empty:
        vcp_df = vcp_df.sort_values(by='VCP Score', ascending=False)
        print("\n=== TOP 5 STOCKS: VOLATILITY CONTRACTION (VCP) ===")
        print(vcp_df.head(5).to_string(index=False))
    else:
        print("\n=== TOP 5 STOCKS: VOLATILITY CONTRACTION (VCP) ===\nNo triggers found.")

if __name__ == '__main__':
    run_test()

