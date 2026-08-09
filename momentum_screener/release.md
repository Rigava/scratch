# Release Notes: Aegis Momentum Platform (v1.0.0)

Aegis Momentum is a premium, quantitative stock momentum screening dashboard, historical strategy backtesting engine, and database-backed trade journaling platform designed to help investors identify momentum shifts and avoid "catching falling knives."

This release notes document compiles all features, architectural designs, user request fulfillments, and critical bug fixes implemented.

---

## 1. Quantitative Core & Market Screener
* **Dual-Mode Data Feeds**:
  * **Simulation Mode**: Generates mock historical stock trajectories, moving averages, and signals dynamically for testing.
  * **Zerodha API Mode**: Connects directly to official NSE ticker feeds via Zerodha Kite Connect developer credentials.
* **Math-Anchored Risk Classification**:
  * **🔴 Falling Knife (High Risk)**: Classifies stocks trading below their 200-day Simple Moving Average (SMA) with high peak-to-trough drawdowns (>30%) or oversold RSI values (<30).
  * **🟢 Safe Momentum (Low Risk)**: Identifies stocks trading above their 200 SMA, consolidating with low drawdown levels (<15%), and exhibiting pullback recovery signals.
* **Interactive Sorting Grid**:
  * Equipped the screener table with ascending and descending sort arrows across all data columns (`Ticker`, `Company`, `Price`, `Drawdown`, `RSI`, `ADX`, and `Status`).
  * Seamlessly toggles sorting orientation on click, with active column headers highlighted in the brand accent color.
* **Gainers & Losers Statistics**:
  * Added 2 new summary cards in the dashboard header indicating "Gainers (Day Up)" and "Losers (Day Down)" count among all scanned stocks.
  * Shows color-coded daily percentage changes (+/-%) adjacent to current stock price cells inside the screener grid.
* **Mini Performance Visual Chart**:
  * Added a dedicated "Perf (1D/7D)" column in the screener grid showing visual micro-progress bar charts for both 1-Day and 7-Day percentage returns.
  * Displays dynamic color gradients (green for positive returns, red for negative returns) with lengths matching performance magnitudes.
* **Performance Filtering Options**:
  * Integrated a "Performance Filter" dropdown inside the config panel allowing users to instantly isolate 1D Winners, 1D Losers, 7D Winners, or 7D Losers.

---

## 2. Interactive Strategy Backtester
* **RSI Crossover Simulator**: Backtests user strategies against historical daily candle data.
* **Variable Lookback Timeframes**: Added lookback duration selection dropdown permitting strategy backtesting over 1 Year (250 candles), 2 Years (500 candles), 3 Years (750 candles), 4 Years (1000 candles), or 5 Years (1250 candles).
* **Buy/Sell Signal Triggers**: Configures custom buy levels (e.g., RSI crossing 30 from below) and sell/exit levels.
* **Performance Metrics**: Computes historical win rates, total trades, average returns, and profitable vs. unprofitable trade allocations.

---

## 3. Persistent Trading Journal
* **Dummy Trade Logging**: Records entry price, exit price, target quantities, stop loss values, and entry/exit reasons from the details panel.
* **Position Longevity (Overnight Fix)**: Corrected the issue where logs deleted daily. Trades now remain active across calendar days until explicitly closed by the user.
* **Journal Metrics Dashboard**: Displays dynamic win rates, total returns, and active trade counts with filters for:
  * **Daily**: Trades closed today.
  * **Monthly**: Trades closed this calendar month.
  * **Yearly**: Trades closed this calendar year.
  * **All Time**: Entire database log.
* **Hybrid Storage Architecture**:
  * **Registered Accounts**: Persists trades permanently inside database tables.
  * **Guest Accounts**: Stores trade logs inside the browser's `localStorage` to allow signup-free dashboard testing.

---

## 4. Authentication, Gating & 7-Day Trials
* **Secure Registration & Login Portal**: Tabbed authentication forms styled with smooth focus outlines and error alerts.
* **7-Day Registered Trial**: Automatically assigns a 7-day trial to new registrants.
* **Ceiling-Based Day Count**: Computes remaining days using seconds-division ceiling limits, ensuring exactly `7` days display immediately on registration day instead of 6.
* **Premium Gating Rules**:
  * Clicks on the **RSI Backtesting** or **Trading Journal** tabs trigger a lockscreen overlay if a trial is expired.
  * Journal dummy trade entry form inside the drawer locks and displays an alert warning.
  * **Market Screener** remains fully open to allow continued platform scanning.
* **Admin Control Center**: Registered profiles in Django admin, allowing administrators to manually check `is_premium` or set `extended_duration_days` to grant additional usage.

---

## 5. Modern Visual Design & Dual Themes
* **Chai Theme Palette**:
  * **Dark Mode**: Warm dark-brownish black background (`#12100e`), card panels (`#1a1714`), cream text (`#eae0d5`), and terracotta orange (`#e9805d`) accents.
  * **Light Mode**: Warm beige background (`#fbf8f3`), white cards (`#ffffff`), and charcoal text (`#181512`).
* **Variable-Driven Style Architecture**: Replaced all hardcoded colors, borders, and modal shadows with CSS variables to ensure consistency across light/dark transitions.
* **Dynamic Theme Switcher**: Persists theme selections to `localStorage`, with a head script tag to check the theme state and prevent unstyled browser flickering.
* **Dynamic Chart.js Repaint**: Automatically recolors price trend lines, Moving Average curves, gridlines, ticks, and legends upon theme toggle.

---

## 6. Marketing & Landing Portal
* **Public Homepage**: Mapped to `/` (redirecting secure views to `/dashboard/`), featuring documentation on how the system works and how it helps investors protect capital.
* **Interactive SVG Stock Visualizer**: Renders an animated mock chart illustrating the "Knife Zone" when stock prices dive beneath the 200 SMA line.
* **Comparison Matrix**: Side-by-side card layouts contrasting falling knives against safe momentum configurations.
