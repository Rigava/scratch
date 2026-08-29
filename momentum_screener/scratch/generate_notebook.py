import json
import os

notebook = {
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# Quant Insights: Second and Third-Order Market Observations\n",
    "\n",
    "This notebook tests the deterministic scoring and ranking of stocks based on market microstructure, behavioral panic/exhaustion, and institutional supply digestion, rather than retail indicators.\n",
    "\n",
    "## 1. Import Libraries and Load Data"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "import json\n",
    "import pandas as pd\n",
    "import numpy as np\n",
    "\n",
    "# Load historical F&O dump\n",
    "db_path = 'screener/data/fo_historical_dump.json'\n",
    "with open(db_path, 'r', encoding='utf-8') as f:\n",
    "    dump_data = json.load(f)\n",
    "\n",
    "print(f\"Loaded {len(dump_data)} symbols from historical dump.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 2. Preprocess Data and Create DataFrames\n",
    "\n",
    "We will convert the raw candle arrays into Pandas DataFrames. Each candle contains: `[date, open, high, low, close, volume]`."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "dfs = {}\n",
    "for symbol, candles in dump_data.items():\n",
    "    if not candles:\n",
    "        continue\n",
    "    df = pd.DataFrame(candles, columns=['date', 'open', 'high', 'low', 'close', 'volume'])\n",
    "    df['date'] = pd.to_datetime(df['date'])\n",
    "    df.set_index('date', inplace=True)\n",
    "    # Convert columns to numeric\n",
    "    for col in ['open', 'high', 'low', 'close', 'volume']:\n",
    "        df[col] = pd.to_numeric(df[col], errors='coerce')\n",
    "    df.sort_index(inplace=True)\n",
    "    dfs[symbol] = df\n",
    "\n",
    "print(f\"Parsed {len(dfs)} active DataFrames.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 3. Extract Market Benchmark (Nifty 50) Returns\n",
    "\n",
    "We will use `'NIFTY 50'` as the benchmark for market returns and beta calculations."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "nifty_df = dfs.get('NIFTY 50')\n",
    "if nifty_df is not None:\n",
    "    nifty_df['market_return'] = nifty_df['close'].pct_change()\n",
    "    print(\"Nifty 50 benchmark returns computed successfully.\")\n",
    "    print(nifty_df[['close', 'market_return']].tail(3))\n",
    "else:\n",
    "    print(\"NIFTY 50 not found in database! Please check the keys.\")"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 4. Calculate Rolling Indicators and Beta for Stocks\n",
    "\n",
    "We calculate:\n",
    "- Daily stock return ($R_s$)\n",
    "- 60-day rolling beta ($\\beta$) against Nifty 50\n",
    "- Residual return ($e_s = R_s - \\beta \\cdot R_m$)\n",
    "- Close Location Value ($CLV = \\frac{(Close-Low) - (High-Close)}{High-Low}$)\n",
    "- 20-day Volume SMA and standard deviation\n",
    "- Volume Z-score\n",
    "- Spread (High - Low) and its 20-day SMA and standard deviation\n",
    "- Spread Z-score\n",
    "- 10-day Close EMA to determine short-term trend"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "for symbol, df in dfs.items():\n",
    "    if symbol == 'NIFTY 50' or 'NIFTY' in symbol:\n",
    "        continue\n",
    "    \n",
    "    # Daily return\n",
    "    df['return'] = df['close'].pct_change()\n",
    "    \n",
    "    # Align with market returns\n",
    "    df = df.join(nifty_df['market_return'], how='left')\n",
    "    \n",
    "    # Rolling Beta (60-day window)\n",
    "    covariance = df['return'].rolling(60).cov(df['market_return'])\n",
    "    market_variance = df['market_return'].rolling(60).var()\n",
    "    df['beta'] = covariance / market_variance\n",
    "    df['beta'] = df['beta'].fillna(1.0) # Fallback to beta = 1\n",
    "    \n",
    "    # Residual return\n",
    "    df['residual_return'] = df['return'] - df['beta'] * df['market_return']\n",
    "    \n",
    "    # Close Location Value (CLV)\n",
    "    hl_range = df['high'] - df['low']\n",
    "    df['clv'] = ((df['close'] - df['low']) - (df['high'] - df['close'])) / hl_range\n",
    "    # Handle zero range (flat candles)\n",
    "    df['clv'] = df['clv'].fillna(0.0)\n",
    "    \n",
    "    # Volume Indicators\n",
    "    vol_mean = df['volume'].rolling(20).mean()\n",
    "    vol_std = df['volume'].rolling(20).std().replace(0, 1e-6)\n",
    "    df['vol_ratio'] = df['volume'] / vol_mean.replace(0, 1e-6)\n",
    "    df['vol_z'] = (df['volume'] - vol_mean) / vol_std\n",
    "    \n",
    "    # Spread Indicators\n",
    "    df['spread'] = df['high'] - df['low']\n",
    "    spread_mean = df['spread'].rolling(20).mean()\n",
    "    spread_std = df['spread'].rolling(20).std().replace(0, 1e-6)\n",
    "    df['spread_z'] = (df['spread'] - spread_mean) / spread_std\n",
    "    df['atr'] = df['spread'].rolling(20).mean()\n",
    "    \n",
    "    # Trend indicator (10-day EMA)\n",
    "    df['ema10'] = df['close'].ewm(span=10, adjust=False).mean()\n",
    "    \n",
    "    # Save back\n",
    "    dfs[symbol] = df"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 5. Define Scoring Metrics\n",
    "\n",
    "We implement three scores:\n",
    "\n",
    "1. **Institutional Liquidity Absorption Score**:\n",
    "   - Triggered on market down days (Nifty 50 return < -0.0075) where the stock return is $\\ge 0$.\n",
    "   - Formula: $Score = e_s \\cdot VolRatio \\cdot (1 + CLV)$\n",
    "\n",
    "2. **Behavioral Exhaustion Score (Capitulation)**:\n",
    "   - **Bearish Capitulation (Selling Climax)**:\n",
    "     - Triggered when stock is below EMA10, Volume Z-score > 2.0, Spread Z-score > 1.5, and CLV > 0.4.\n",
    "     - Formula: $Score = VolZ \\cdot SpreadZ \\cdot CLV$\n",
    "   - **Bullish Capitulation (Blow-off Top)**:\n",
    "     - Triggered when stock is above EMA10, Volume Z-score > 2.0, Spread Z-score > 1.5, and CLV < -0.4.\n",
    "     - Formula: $Score = VolZ \\cdot SpreadZ \\cdot (-CLV)$\n",
    "\n",
    "3. **Volatility Contraction Score (VCP)**:\n",
    "   - Triggered when price is near 20-day high (within 4%), 5-day return volatility is less than 20-day volatility, and 5-day average volume is less than 20-day volume.\n",
    "   - Formula: $Score = VolComp \\cdot VoluCont \\cdot (1 - DistFromHigh)$\n",
    "     - $VolComp = \\frac{\\sigma_{Ret}(20) - \\sigma_{Ret}(5)}{\\sigma_{Ret}(20)}$\n",
    "     - $VoluCont = 1 - \\frac{MA(V, 5)}{MA(V, 20)}$\n",
    "     - $DistFromHigh = \\frac{\\max(C_{t-20:t}) - C_t}{\\max(C_{t-20:t})}$"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "eval_date = pd.to_datetime('2026-08-28')\n",
    "print(f\"Evaluating scores for target date: {eval_date.date()}\")"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "absorption_results = []\n",
    "bearish_exh_results = []\n",
    "bullish_exh_results = []\n",
    "vcp_results = []\n",
    "\n",
    "nifty_row = nifty_df.loc[eval_date]\n",
    "market_ret = nifty_row['market_return']\n",
    "print(f\"Nifty 50 return on eval date: {market_ret*100:.3f}%\")\n",
    "\n",
    "for symbol, df in dfs.items():\n",
    "    if symbol == 'NIFTY 50' or 'NIFTY' in symbol:\n",
    "        continue\n",
    "        \n",
    "    if eval_date not in df.index:\n",
    "        continue\n",
    "        \n",
    "    row = df.loc[eval_date]\n",
    "    prev_row = df.shift(1).loc[eval_date]\n",
    "    \n",
    "    # 1. Institutional Liquidity Absorption\n",
    "    # Nifty drops significantly, stock is green/flat, showing relative strength and absorption\n",
    "    # We trigger if Nifty is down < -0.5% (to make sure we get triggers if market was weak) and stock return >= 0\n",
    "    if market_ret < -0.005 and row['return'] >= 0:\n",
    "        abs_score = row['residual_return'] * row['vol_ratio'] * (1 + row['clv'])\n",
    "        absorption_results.append({\n",
    "            'Symbol': symbol,\n",
    "            'Price': row['close'],\n",
    "            'Stock Return (%)': round(row['return'] * 100, 2),\n",
    "            'Residual Return (%)': round(row['residual_return'] * 100, 2),\n",
    "            'Volume Ratio': round(row['vol_ratio'], 2),\n",
    "            'CLV': round(row['clv'], 2),\n",
    "            'Absorption Score': round(abs_score, 4)\n",
    "        })\n",
    "        \n",
    "    # 2. Behavioral Exhaustion\n",
    "    # Bearish Capitulation: downtrend, huge volume, wide spread, closing near high (reversal lower tail)\n",
    "    # Bullish Capitulation: uptrend, huge volume, wide spread, closing near low (reversal upper tail)\n",
    "    if row['vol_z'] > 1.5 and row['spread_z'] > 1.0:\n",
    "        # Bearish Capitulation\n",
    "        if row['close'] < row['ema10'] and row['clv'] > 0.3:\n",
    "            bear_score = row['vol_z'] * row['spread_z'] * row['clv']\n",
    "            bearish_exh_results.append({\n",
    "                'Symbol': symbol,\n",
    "                'Price': row['close'],\n",
    "                'Volume Z-Score': round(row['vol_z'], 2),\n",
    "                'Spread Z-Score': round(row['spread_z'], 2),\n",
    "                'CLV': round(row['clv'], 2),\n",
    "                'Bearish Exhaustion Score': round(bear_score, 2)\n",
    "            })\n",
    "        # Bullish Capitulation\n",
    "        elif row['close'] > row['ema10'] and row['clv'] < -0.3:\n",
    "            bull_score = row['vol_z'] * row['spread_z'] * (-row['clv'])\n",
    "            bullish_exh_results.append({\n",
    "                'Symbol': symbol,\n",
    "                'Price': row['close'],\n",
    "                'Volume Z-Score': round(row['vol_z'], 2),\n",
    "                'Spread Z-Score': round(row['spread_z'], 2),\n",
    "                'CLV': round(row['clv'], 2),\n",
    "                'Bullish Exhaustion Score': round(bull_score, 2)\n",
    "            })\n",
    "\n",
    "    # 3. Volatility Contraction Pattern (VCP)\n",
    "    # Near highs, vol and range shrinking\n",
    "    # We look at historical 20-day window up to eval_date\n",
    "    sub_df = df.loc[:eval_date].tail(20)\n",
    "    if len(sub_df) == 20:\n",
    "        high_20 = sub_df['close'].max()\n",
    "        dist_from_high = (high_20 - row['close']) / high_20\n",
    "        \n",
    "        # Volatility of last 5 days vs 20 days\n",
    "        vol_5d = sub_df['return'].tail(5).std()\n",
    "        vol_20d = sub_df['return'].std()\n",
    "        \n",
    "        # Volume of last 5 days vs 20 days\n",
    "        avg_vol_5d = sub_df['volume'].tail(5).mean()\n",
    "        avg_vol_20d = sub_df['volume'].mean()\n",
    "        \n",
    "        if vol_20d > 0 and avg_vol_20d > 0:\n",
    "            vol_comp = (vol_20d - vol_5d) / vol_20d\n",
    "            volu_cont = 1.0 - (avg_vol_5d / avg_vol_20d)\n",
    "            \n",
    "            # Only trigger if there is actual contraction and we are near the high\n",
    "            if vol_comp > 0 and volu_cont > 0 and dist_from_high < 0.05:\n",
    "                vcp_score = vol_comp * volu_cont * (1.0 - dist_from_high)\n",
    "                vcp_results.append({\n",
    "                    'Symbol': symbol,\n",
    "                    'Price': row['close'],\n",
    "                    'Dist from High (%)': round(dist_from_high * 100, 2),\n",
    "                    'Vol Comp (%)': round(vol_comp * 100, 2),\n",
    "                    'Volume Contraction (%)': round(volu_cont * 100, 2),\n",
    "                    'VCP Score': round(vcp_score, 4)\n",
    "                })\n"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 6. Display Rankings\n",
    "\n",
    "We sort and display the top stocks for each outcome."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "abs_df = pd.DataFrame(absorption_results).sort_values(by='Absorption Score', ascending=False)\n",
    "bear_df = pd.DataFrame(bearish_exh_results).sort_values(by='Bearish Exhaustion Score', ascending=False)\n",
    "bull_df = pd.DataFrame(bullish_exh_results).sort_values(by='Bullish Exhaustion Score', ascending=False)\n",
    "vcp_df = pd.DataFrame(vcp_results).sort_values(by='VCP Score', ascending=False)\n",
    "\n",
    "print(\"=== TOP 5 STOCKS: INSTITUTIONAL LIQUIDITY ABSORPTION ===\")\n",
    "print(abs_df.head(5).to_string(index=False))\n",
    "\n",
    "print(\"\\n=== TOP 5 STOCKS: BEARISH CAPITULATION (SELLING EXHAUSTION) ===\")\n",
    "print(bear_df.head(5).to_string(index=False))\n",
    "\n",
    "print(\"\\n=== TOP 5 STOCKS: BULLISH CAPITULATION (BUYING EXHAUSTION) ===\")\n",
    "print(bull_df.head(5).to_string(index=False))\n",
    "\n",
    "print(\"\\n=== TOP 5 STOCKS: VOLATILITY CONTRACTION (VCP) ===\")\n",
    "print(vcp_df.head(5).to_string(index=False))"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "name": "python"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}

os.makedirs('scratch', exist_ok=True)
with open('test_second_order.ipynb', 'w', encoding='utf-8') as f:
    json.dump(notebook, f, indent=1)
print("Notebook generated successfully at test_second_order.ipynb")
