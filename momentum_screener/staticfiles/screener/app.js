/**
 * Aegis Momentum - Core Client Application
 * Calculates quantitative indicators (SMA, RSI, ADX, Drawdown) and handles screener UI.
 */

// Custom Chart.js Plugin to draw vertical shaded red blocks during "Falling Knife" periods
const knifeHighlightPlugin = {
    id: 'knifeHighlight',
    beforeDraw(chart) {
        const { ctx, chartArea, scales: { x } } = chart;
        const pluginOptions = chart.options.plugins.knifeHighlight;
        if (!pluginOptions || !pluginOptions.active || !pluginOptions.isKnifeArray) return;
        
        const isKnifeArray = pluginOptions.isKnifeArray;
        const totalPoints = isKnifeArray.length;
        
        ctx.save();
        ctx.fillStyle = 'rgba(239, 68, 68, 0.08)'; // Soft alert red overlay
        
        // Calculate dynamic width of each daily block
        const width = chartArea.width / totalPoints;
        
        for (let i = 0; i < totalPoints; i++) {
            if (isKnifeArray[i]) {
                // Get horizontal pixel location
                const xPos = x.getPixelForValue(i) - (width / 2);
                ctx.fillRect(xPos, chartArea.top, width + 1.2, chartArea.height);
            }
        }
        ctx.restore();
    }
};

// Register the custom plugin globally
Chart.register(knifeHighlightPlugin);

const App = (function() {
    // Core Application State
    const state = {
        dataSource: 'simulation', // 'simulation' or 'zerodha'
        stocks: {},               // Holds all loaded stock records
        activeTicker: null,       // Currently selected stock
        zerodhaAuthErrorAlerted: false, // Flag to prevent alert floods on API auth errors
        universeFilter: 'all',    // 'all', 'nifty50', or 'fo'
        filters: {
            status: 'all',
            sma: { enabled: true },
            rsi: { enabled: true, threshold: 30 },
            adx: { enabled: true, threshold: 25 },
            drawdown: { enabled: true, threshold: 30, years: 1 }
        },
        charts: {
            price: null,
            indicators: null
        },
        journal: JSON.parse(localStorage.getItem('trade_journal') || '[]'),
        journalFilter: 'all',
        sort: {
            field: 'ticker',
            direction: 'asc'
        }
    };

    // --- Mathematical Indicator Calculations ---

    // 1. Simple Moving Average (SMA)
    function calculateSMA(prices, period) {
        const sma = new Array(prices.length).fill(null);
        let sum = 0;
        for (let i = 0; i < prices.length; i++) {
            sum += prices[i];
            if (i >= period) {
                sum -= prices[i - period];
                sma[i] = Math.round((sum / period) * 100) / 100;
            } else if (i === period - 1) {
                sma[i] = Math.round((sum / period) * 100) / 100;
            }
        }
        return sma;
    }

    // 2. Peak-to-Trough Drawdown
    function calculateDrawdown(prices, period = 250) {
        const drawdown = new Array(prices.length).fill(0);
        let maxPrice = -Infinity;
        
        for (let i = 0; i < prices.length; i++) {
            // Sliding window maximum
            let start = Math.max(0, i - period + 1);
            let windowMax = -Infinity;
            for (let j = start; j <= i; j++) {
                if (prices[j] > windowMax) windowMax = prices[j];
            }
            
            const dd = (windowMax - prices[i]) / windowMax;
            drawdown[i] = Math.round(dd * 1000) / 10; // Save as percentage (e.g. 15.4)
        }
        return drawdown;
    }

    // 3. Relative Strength Index (RSI) using Wilder's Smoothing
    function calculateRSI(prices, period = 14) {
        const rsi = new Array(prices.length).fill(null);
        if (prices.length <= period) return rsi;

        let gains = new Array(prices.length).fill(0);
        let losses = new Array(prices.length).fill(0);

        for (let i = 1; i < prices.length; i++) {
            const diff = prices[i] - prices[i - 1];
            gains[i] = diff > 0 ? diff : 0;
            losses[i] = diff < 0 ? -diff : 0;
        }

        // First averages
        let avgGain = gains.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
        let avgLoss = losses.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
        rsi[period] = avgLoss === 0 ? 100 : Math.round((100 - 100 / (1 + avgGain / avgLoss)) * 100) / 100;

        // Wilder's smoothing
        for (let i = period + 1; i < prices.length; i++) {
            avgGain = (avgGain * 13 + gains[i]) / 14;
            avgLoss = (avgLoss * 13 + losses[i]) / 14;
            
            if (avgLoss === 0) {
                rsi[i] = 100;
            } else {
                const rs = avgGain / avgLoss;
                rsi[i] = Math.round((100 - (100 / (1 + rs))) * 100) / 100;
            }
        }
        return rsi;
    }

    // 4. Average Directional Index (ADX)
    function calculateADX(candles, period = 14) {
        const n = candles.length;
        const result = {
            adx: new Array(n).fill(null),
            plusDI: new Array(n).fill(null),
            minusDI: new Array(n).fill(null)
        };

        if (n <= period) return result;

        const tr = new Array(n).fill(0);
        const plusDM = new Array(n).fill(0);
        const minusDM = new Array(n).fill(0);

        // Calculate True Range & Directional Movement
        for (let i = 1; i < n; i++) {
            const h = candles[i].high;
            const l = candles[i].low;
            const prevC = candles[i - 1].close;
            const prevH = candles[i - 1].high;
            const prevL = candles[i - 1].low;

            tr[i] = Math.max(h - l, Math.abs(h - prevC), Math.abs(l - prevC));

            const upMove = h - prevH;
            const downMove = prevL - l;

            plusDM[i] = (upMove > downMove && upMove > 0) ? upMove : 0;
            minusDM[i] = (downMove > upMove && downMove > 0) ? downMove : 0;
        }

        // Initialize sum for first period
        let trSum = tr.slice(1, period + 1).reduce((a, b) => a + b, 0);
        let plusDMSum = plusDM.slice(1, period + 1).reduce((a, b) => a + b, 0);
        let minusDMSum = minusDM.slice(1, period + 1).reduce((a, b) => a + b, 0);

        let trSmoothed = trSum;
        let plusDMSmoothed = plusDMSum;
        let minusDMSmoothed = minusDMSum;

        // DI values
        result.plusDI[period] = Math.round((100 * plusDMSmoothed / trSmoothed) * 100) / 100;
        result.minusDI[period] = Math.round((100 * minusDMSmoothed / trSmoothed) * 100) / 100;
        
        let dx = Math.abs(result.plusDI[period] - result.minusDI[period]) / (result.plusDI[period] + result.minusDI[period]);
        let dxArray = new Array(n).fill(0);
        dxArray[period] = dx * 100;

        // Calculate subsequent values using smoothing
        for (let i = period + 1; i < n; i++) {
            trSmoothed = trSmoothed - (trSmoothed / 14) + tr[i];
            plusDMSmoothed = plusDMSmoothed - (plusDMSmoothed / 14) + plusDM[i];
            minusDMSmoothed = minusDMSmoothed - (minusDMSmoothed / 14) + minusDM[i];

            result.plusDI[i] = Math.round((100 * plusDMSmoothed / trSmoothed) * 100) / 100;
            result.minusDI[i] = Math.round((100 * minusDMSmoothed / trSmoothed) * 100) / 100;

            const sum = result.plusDI[i] + result.minusDI[i];
            dx = sum === 0 ? 0 : Math.abs(result.plusDI[i] - result.minusDI[i]) / sum;
            dxArray[i] = dx * 100;
        }

        // Calculate ADX
        let adxSum = dxArray.slice(period, period * 2).reduce((a, b) => a + b, 0);
        result.adx[period * 2 - 1] = Math.round((adxSum / period) * 100) / 100;

        for (let i = period * 2; i < n; i++) {
            result.adx[i] = Math.round(((result.adx[i - 1] * 13 + dxArray[i]) / 14) * 100) / 100;
        }

        return result;
    }

    // Process a stock's raw candles to compute all historical indicator vectors
    function processStockIndicators(stock) {
        const candles = stock.candles;
        const prices = candles.map(c => c.close);

        // EMA Calculator helper
        function calcEMAArray(vals, period) {
            const ema = new Array(vals.length).fill(null);
            if (vals.length < period) return ema;

            let sum = 0;
            for (let i = 0; i < period; i++) {
                sum += vals[i];
            }
            let currentEma = sum / period;
            ema[period - 1] = currentEma;

            const alpha = 2 / (period + 1);
            for (let i = period; i < vals.length; i++) {
                currentEma = (vals[i] * alpha) + (currentEma * (1 - alpha));
                ema[i] = currentEma;
            }
            return ema;
        }

        // MACD Calculator helper
        function calcMACDArray(vals) {
            const ema12 = calcEMAArray(vals, 12);
            const ema26 = calcEMAArray(vals, 26);
            const macdLine = new Array(vals.length).fill(null);
            
            for (let i = 0; i < vals.length; i++) {
                if (ema12[i] !== null && ema26[i] !== null) {
                    macdLine[i] = ema12[i] - ema26[i];
                }
            }
            
            const signalLine = new Array(vals.length).fill(null);
            const nonNullIndices = [];
            const nonNullValues = [];
            for (let i = 0; i < vals.length; i++) {
                if (macdLine[i] !== null) {
                    nonNullIndices.push(i);
                    nonNullValues.push(macdLine[i]);
                }
            }
            
            if (nonNullValues.length >= 9) {
                const rawSignal = calcEMAArray(nonNullValues, 9);
                for (let i = 0; i < rawSignal.length; i++) {
                    if (rawSignal[i] !== null) {
                        const originalIndex = nonNullIndices[i];
                        signalLine[originalIndex] = rawSignal[i];
                    }
                }
            }
            
            const histogram = new Array(vals.length).fill(null);
            for (let i = 0; i < vals.length; i++) {
                if (macdLine[i] !== null && signalLine[i] !== null) {
                    histogram[i] = macdLine[i] - signalLine[i];
                }
            }
            
            return { macdLine, signalLine, histogram };
        }

        // MACD Crossover Backtester helper
        function runMACDBacktestJS(histCandles) {
            if (!histCandles || histCandles.length < 40) {
                return { totalTrades: 0, winRate: 0, avgPnL: 0 };
            }
            
            const p = histCandles.map(c => c.close);
            const o = histCandles.map(c => c.open);
            const macd = calcMACDArray(p);
            const s200 = calculateSMA(p, 200);
            
            const p3d = new Array(p.length).fill(0);
            for (let i = 3; i < p.length; i++) {
                p3d[i] = ((p[i] - p[i-3]) / p[i-3]) * 100;
            }

            let inTrade = false;
            let buyPrice = 0;
            const trades = [];
            let holdDays = 0;
            
            const n = histCandles.length;
            for (let i = 200; i < n - 1; i++) {
                const currentMacd = macd.macdLine[i];
                const currentSignal = macd.signalLine[i];
                const prevMacd = macd.macdLine[i-1];
                const prevSignal = macd.signalLine[i-1];
                
                if (currentMacd === null || currentSignal === null || prevMacd === null || prevSignal === null) continue;
                
                const isUpwardCrossover = prevMacd <= prevSignal && currentMacd > currentSignal;
                const isDownwardCrossover = prevMacd >= prevSignal && currentMacd < currentSignal;
                
                const priceAboveSma200 = s200[i] ? p[i] >= s200[i] : true;
                const priceBuildingUp = p3d[i] > 0;
                
                if (!inTrade) {
                    if (isUpwardCrossover && priceAboveSma200 && priceBuildingUp) {
                        buyPrice = o[i+1];
                        inTrade = true;
                        holdDays = 0;
                    }
                } else {
                    holdDays++;
                    if (isDownwardCrossover || holdDays >= 20) {
                        const sellPrice = o[i+1];
                        const pnl = ((sellPrice - buyPrice) / buyPrice) * 100;
                        trades.push(pnl);
                        inTrade = false;
                    }
                }
            }
            
            if (inTrade) {
                const sellPrice = p[n-1];
                const pnl = ((sellPrice - buyPrice) / buyPrice) * 100;
                trades.push(pnl);
            }
            
            const totalTrades = trades.length;
            const wins = trades.filter(r => r > 0).length;
            const winRate = totalTrades > 0 ? Math.round((wins / totalTrades) * 100) : 0;
            const avgPnL = totalTrades > 0 ? Math.round((trades.reduce((a, b) => a + b, 0) / totalTrades) * 100) / 100 : 0;
            
            return { totalTrades, winRate, avgPnL };
        }

        const sma50 = calculateSMA(prices, 50);
        const sma200 = calculateSMA(prices, 200);
        const drawdownPeriod = (state.filters.drawdown.years || 1) * 250;
        const drawdown = calculateDrawdown(prices, drawdownPeriod);
        const rsi = calculateRSI(prices, 14);
        const adxData = calculateADX(candles, 14);
        
        const macdData = calcMACDArray(prices);
        const macdBacktest = runMACDBacktestJS(candles);

        stock.indicators = {
            sma50,
            sma200,
            drawdown,
            rsi,
            adx: adxData.adx,
            plusDI: adxData.plusDI,
            minusDI: adxData.minusDI,
            macd: macdData.macdLine,
            signal: macdData.signalLine,
            histogram: macdData.histogram
        };

        // Determine current status based on the latest day's values
        const lastIdx = candles.length - 1;
        const pricePrev = lastIdx > 0 ? prices[lastIdx - 1] : prices[lastIdx];
        const pctChange = pricePrev ? ((prices[lastIdx] - pricePrev) / pricePrev) * 100 : 0;
        const pricePrev7d = lastIdx >= 7 ? prices[lastIdx - 7] : prices[0];
        const pctChange7d = pricePrev7d ? ((prices[lastIdx] - pricePrev7d) / pricePrev7d) * 100 : 0;

        // Momentum Shift calculation today
        const isUpwardCrossoverToday = lastIdx > 0 &&
            macdData.macdLine[lastIdx - 1] !== null &&
            macdData.signalLine[lastIdx - 1] !== null &&
            macdData.macdLine[lastIdx] !== null &&
            macdData.signalLine[lastIdx] !== null &&
            macdData.macdLine[lastIdx - 1] <= macdData.signalLine[lastIdx - 1] &&
            macdData.macdLine[lastIdx] > macdData.signalLine[lastIdx];

        const pricePrev3d = lastIdx >= 3 ? prices[lastIdx - 3] : prices[0];
        const pctChange3d = pricePrev3d ? ((prices[lastIdx] - pricePrev3d) / pricePrev3d) * 100 : 0;
        const priceAboveSma200 = sma200[lastIdx] ? prices[lastIdx] >= sma200[lastIdx] : true;
        const priceBuildingUp = pctChange3d > 0;
        const hasMomentumShift = isUpwardCrossoverToday && priceAboveSma200 && priceBuildingUp;

        // Milestone Key Level evaluation
        const lookbackPeriod = Math.min(250, candles.length);
        const slice52w = prices.slice(-lookbackPeriod);
        const max52w = Math.max(...slice52w);
        const min52w = Math.min(...slice52w);

        const ema50 = calcEMAArray(prices, 50);
        const currentEma50 = ema50[lastIdx];
        const currentSma200 = sma200[lastIdx];
        const currentPrice = prices[lastIdx];

        let milestone = "Stable";
        let milestonePriority = 1;

        if (currentPrice >= 0.98 * max52w) {
            milestone = "52W High";
            milestonePriority = 5;
        } else if (currentPrice <= 1.02 * min52w) {
            milestone = "52W Low";
            milestonePriority = 2;
        } else if (currentEma50 && Math.abs((currentPrice - currentEma50) / currentEma50) <= 0.015) {
            milestone = "Near EMA50";
            milestonePriority = 4;
        } else if (currentSma200 && Math.abs((currentPrice - currentSma200) / currentSma200) <= 0.015) {
            milestone = "Near SMA200";
            milestonePriority = 3;
        }

        stock.current = {
            price: prices[lastIdx],
            drawdown: drawdown[lastIdx],
            rsi: rsi[lastIdx],
            adx: adxData.adx[lastIdx],
            plusDI: adxData.plusDI[lastIdx],
            minusDI: adxData.minusDI[lastIdx],
            aboveSMA200: sma200[lastIdx] ? (prices[lastIdx] >= sma200[lastIdx]) : true,
            pctChange: Math.round(pctChange * 100) / 100,
            pctChange7d: Math.round(pctChange7d * 100) / 100,
            hasMomentumShift,
            macdWinRate: macdBacktest.winRate,
            macdTrades: macdBacktest.totalTrades,
            macdAvgPnL: macdBacktest.avgPnL,
            milestone,
            milestonePriority
        };

        // Compute historical "Knife" flags for chart highlights
        stock.isKnifeArray = candles.map((c, idx) => {
            const pr = c.close;
            const s2 = sma200[idx];
            const dd = drawdown[idx];
            const rs = rsi[idx];
            const ad = adxData.adx[idx];
            const pDI = adxData.plusDI[idx];
            const mDI = adxData.minusDI[idx];

            let failSMA = state.filters.sma.enabled && s2 && pr < s2;
            let failRSI = state.filters.rsi.enabled && rs && rs < state.filters.rsi.threshold;
            let failADX = state.filters.adx.enabled && ad && ad > state.filters.adx.threshold && mDI > pDI;
            let failDD = state.filters.drawdown.enabled && dd > state.filters.drawdown.threshold;

            return failSMA || failRSI || failADX || failDD;
        });

        // Set the consolidated stock status
        stock.status = stock.isKnifeArray[lastIdx] ? 'Knife' : 'Safe';
    }

    // --- UI Rendering & Grid Filtering ---

    // Filter stocks list and update the display table
    function renderScreenerGrid() {
        const query = document.getElementById('grid-search').value.toLowerCase();
        const tbody = document.getElementById('screener-tbody');
        tbody.innerHTML = '';

        let total = 0;
        let knives = 0;
        let safe = 0;
        let gainers = 0;
        let losers = 0;
        let filteredStocks = [];

        for (const stock of Object.values(state.stocks)) {
            // Re-evaluate current status based on updated state filters
            processStockIndicators(stock);

            const matchesSearch = stock.ticker.toLowerCase().includes(query) || 
                                  stock.name.toLowerCase().includes(query);

            const filterStatusSelect = document.getElementById('sel-filter-status');
            const filterStatus = filterStatusSelect ? filterStatusSelect.value : 'all';
            const matchesStatus = filterStatus === 'all' || 
                                  (filterStatus === 'safe' && stock.status === 'Safe') || 
                                  (filterStatus === 'knife' && stock.status === 'Knife');

            const filterPerfSelect = document.getElementById('sel-filter-performance');
            const filterPerf = filterPerfSelect ? filterPerfSelect.value : 'all';
            const matchesPerf = filterPerf === 'all' || 
                                (filterPerf === 'momentum-shift' && stock.current.hasMomentumShift) ||
                                (filterPerf === '1d-winners' && stock.current.pctChange > 0) || 
                                (filterPerf === '1d-losers' && stock.current.pctChange < 0) || 
                                (filterPerf === '7d-winners' && stock.current.pctChange7d > 0) || 
                                (filterPerf === '7d-losers' && stock.current.pctChange7d < 0);

            // Stock Universe Filter (All, Nifty 50, Nifty F&O)
            const universe = state.universeFilter || 'all';
            const isN50 = MockDataEngine.NIFTY50_LIST.includes(stock.ticker);
            const isFoStock = MockDataEngine.FO_LIST.includes(stock.ticker);
            let matchesUniverse = true;
            if (universe === 'nifty50') {
                matchesUniverse = isN50;
            } else if (universe === 'fo') {
                matchesUniverse = isFoStock;
            }

            if (matchesSearch && matchesStatus && matchesPerf && matchesUniverse) {
                total++;
                if (stock.status === 'Knife') {
                    knives++;
                } else {
                    safe++;
                }

                // Track Gainers vs Losers based on day change
                if (stock.current.pctChange > 0) {
                    gainers++;
                } else if (stock.current.pctChange < 0) {
                    losers++;
                }

                filteredStocks.push(stock);
            }
        }

        // Sort filtered stocks list
        const sortField = state.sort.field;
        const sortDirection = state.sort.direction;

        filteredStocks.sort((a, b) => {
            let valA, valB;

            if (sortField === 'ticker') {
                valA = a.ticker.toLowerCase();
                valB = b.ticker.toLowerCase();
            } else if (sortField === 'company') {
                valA = a.name.toLowerCase();
                valB = b.name.toLowerCase();
            } else if (sortField === 'price') {
                valA = a.current.price;
                valB = b.current.price;
            } else if (sortField === 'change1d') {
                valA = a.current.pctChange;
                valB = b.current.pctChange;
            } else if (sortField === 'macd_win') {
                valA = a.current.macdWinRate ?? 0;
                valB = b.current.macdWinRate ?? 0;
            } else if (sortField === 'milestone') {
                valA = a.current.milestonePriority ?? 1;
                valB = b.current.milestonePriority ?? 1;
            } else if (sortField === 'drawdown') {
                valA = a.current.drawdown;
                valB = b.current.drawdown;
            } else if (sortField === 'rsi') {
                valA = a.current.rsi ?? 0;
                valB = b.current.rsi ?? 0;
            } else if (sortField === 'adx') {
                valA = a.current.adx ?? 0;
                valB = b.current.adx ?? 0;
            } else if (sortField === 'status') {
                valA = a.status.toLowerCase();
                valB = b.status.toLowerCase();
            }

            if (valA < valB) return sortDirection === 'asc' ? -1 : 1;
            if (valA > valB) return sortDirection === 'asc' ? 1 : -1;
            return 0;
        });

        // Render rows
        for (const stock of filteredStocks) {
            const tr = document.createElement('tr');
            tr.setAttribute('data-ticker', stock.ticker);
            if (state.activeTicker === stock.ticker) {
                tr.classList.add('selected');
            }

            const badgeClass = stock.status === 'Knife' ? 'badge-red' : 'badge-green';
            const icon = stock.status === 'Knife' ? '<i class="fa-solid fa-skull"></i>' : '<i class="fa-solid fa-circle-check"></i>';

            // Calculate mini progress bars for 1D and 7D returns
            const calcBarWidth = (val) => {
                const abs = Math.abs(val);
                return Math.min(100, Math.round(abs * 10)); // e.g. 5% change -> 50% width
            };

            const width1d = calcBarWidth(stock.current.pctChange);
            const class1d = stock.current.pctChange >= 0 ? 'positive' : 'negative';
            const sign1d = stock.current.pctChange >= 0 ? '+' : '';
            const color1d = stock.current.pctChange >= 0 ? 'text-green' : 'text-red';

            const width7d = calcBarWidth(stock.current.pctChange7d);
            const class7d = stock.current.pctChange7d >= 0 ? 'positive' : 'negative';
            const sign7d = stock.current.pctChange7d >= 0 ? '+' : '';
            const color7d = stock.current.pctChange7d >= 0 ? 'text-green' : 'text-red';

            const perfVisualHtml = `
                <div class="perf-visual">
                    <div class="perf-row">
                        <span class="perf-lbl">1D</span>
                        <div class="perf-bar-bg">
                            <div class="perf-bar ${class1d}" style="width: ${width1d}%;"></div>
                        </div>
                        <span class="perf-val ${color1d}">${sign1d}${stock.current.pctChange}%</span>
                    </div>
                    <div class="perf-row">
                        <span class="perf-lbl">7D</span>
                        <div class="perf-bar-bg">
                            <div class="perf-bar ${class7d}" style="width: ${width7d}%;"></div>
                        </div>
                        <span class="perf-val ${color7d}">${sign7d}${stock.current.pctChange7d}%</span>
                    </div>
                </div>
            `;

            const momentumShiftHtml = stock.current.hasMomentumShift 
                ? `<div class="badge-momentum-shift"><i class="fa-solid fa-rocket"></i> Shift</div>
                   <div class="macd-backtest-info">Win: ${stock.current.macdWinRate}% (${stock.current.macdTrades} tr)</div>`
                : `<div class="macd-backtest-info" style="margin-top: 0;">Win: ${stock.current.macdWinRate}% (${stock.current.macdTrades} tr)</div>`;

            let milestoneClass = 'normal';
            if (stock.current.milestone === '52W High') milestoneClass = 'high';
            else if (stock.current.milestone === '52W Low') milestoneClass = 'low';
            else if (stock.current.milestone === 'Near EMA50') milestoneClass = 'ema50';
            else if (stock.current.milestone === 'Near SMA200') milestoneClass = 'sma200';
            const milestoneHtml = `<span class="badge-milestone ${milestoneClass}">${stock.current.milestone}</span>`;

            const isN50 = MockDataEngine.NIFTY50_LIST.includes(stock.ticker);
            const isFoStock = MockDataEngine.FO_LIST.includes(stock.ticker);
            let universeBadge = '';
            if (isN50) {
                universeBadge = `<span style="font-size: 9px; padding: 2px 6px; border-radius: 4px; background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); font-weight: 600; margin-left: 6px; white-space: nowrap;">NIFTY 50</span>`;
            } else if (isFoStock) {
                universeBadge = `<span style="font-size: 9px; padding: 2px 6px; border-radius: 4px; background: rgba(244, 162, 97, 0.15); color: #f4a261; border: 1px solid rgba(244, 162, 97, 0.3); font-weight: 600; margin-left: 6px; white-space: nowrap;">F&O</span>`;
            }

            tr.innerHTML = `
                <td><strong>${stock.ticker}</strong></td>
                <td>
                    <div style="display: flex; align-items: center;">
                        <strong>${stock.ticker}</strong>
                        ${universeBadge}
                    </div>
                    <span class="symbol-name">${stock.name}</span>
                </td>
                <td>₹${stock.current.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td>${perfVisualHtml}</td>
                <td>${momentumShiftHtml}</td>
                <td>${milestoneHtml}</td>
                <td class="detail-col ${stock.current.drawdown > state.filters.drawdown.threshold && state.filters.drawdown.enabled ? 'text-red' : ''}">${stock.current.drawdown}%</td>
                <td class="detail-col ${stock.current.rsi < state.filters.rsi.threshold && state.filters.rsi.enabled ? 'text-red' : ''}">${stock.current.rsi ?? '-'}</td>
                <td class="detail-col">${stock.current.adx ?? '-'}</td>
                <td class="detail-col"><span class="badge ${badgeClass}">${icon} ${stock.status}</span></td>
            `;

            tr.addEventListener('click', () => {
                openDetailDrawer(stock.ticker);
            });

            tbody.appendChild(tr);
        }

        // Helper to update sorting arrows on table columns
        (function updateScreenerHeaderIcons() {
            document.querySelectorAll('#screener-table th.sortable').forEach(th => {
                const field = th.getAttribute('data-sort');
                const icon = th.querySelector('i');
                if (icon) {
                    if (state.sort.field === field) {
                        th.classList.add('active');
                        icon.className = state.sort.direction === 'asc' ? 'fa-solid fa-sort-up' : 'fa-solid fa-sort-down';
                    } else {
                        th.classList.remove('active');
                        icon.className = 'fa-solid fa-sort';
                    }
                }
            });
        })();

        // Update statistics
        document.getElementById('stat-total').innerText = total;
        document.getElementById('stat-knives').innerText = knives;
        document.getElementById('stat-safe').innerText = safe;
        const statGainers = document.getElementById('stat-gainers');
        if (statGainers) statGainers.innerText = gainers;
        const statLosers = document.getElementById('stat-losers');
        if (statLosers) statLosers.innerText = losers;

        // Sync backtest dashboard if visible
        const backtestView = document.getElementById('backtest-view-card');
        if (backtestView && !backtestView.classList.contains('hidden')) {
            renderBacktestDashboard();
        }
    }

    // --- Interactive Chart Rendering (Chart.js) ---

    function renderCharts(stock) {
        const lookbackDays = (state.filters.drawdown.years || 1) * 250;
        const candlesSlice = stock.candles.slice(-lookbackDays);
        
        const labels = candlesSlice.map(c => c.date);
        const prices = candlesSlice.map(c => c.close);
        const sma50 = stock.indicators.sma50.slice(-lookbackDays);
        const sma200 = stock.indicators.sma200.slice(-lookbackDays);
        const isKnifeArraySlice = stock.isKnifeArray.slice(-lookbackDays);
        
        // Theme variables for Chart.js
        const isLight = document.body.classList.contains('light-theme');
        const textColor = isLight ? '#181512' : '#eae0d5';
        const mutedTextColor = isLight ? '#6e675f' : '#b5ad99';
        const gridColor = isLight ? 'rgba(26, 23, 20, 0.05)' : 'rgba(255, 255, 255, 0.05)';
        const mainLineColor = isLight ? '#181512' : '#eae0d5';
        const sma200Color = '#e9805d';
        
        // 1. Render Price Chart (Top Panel)
        if (state.charts.price) {
            state.charts.price.destroy();
        }

        const ctxPrice = document.getElementById('chart-price').getContext('2d');
        state.charts.price = new Chart(ctxPrice, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Close Price',
                        data: prices,
                        borderColor: mainLineColor,
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.1
                    },
                    {
                        label: '50 SMA',
                        data: sma50,
                        borderColor: '#fbbf24',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        tension: 0.1,
                        borderDash: [4, 4]
                    },
                    {
                        label: '200 SMA',
                        data: sma200,
                        borderColor: sma200Color,
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: mutedTextColor, maxTicksLimit: 8 }
                    },
                    y: {
                        grid: { color: gridColor },
                        ticks: { color: mutedTextColor }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: textColor, boxWidth: 15, font: { family: 'Outfit' } }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    },
                    knifeHighlight: {
                        active: true,
                        isKnifeArray: isKnifeArraySlice
                    }
                }
            }
        });

        // 2. Render Indicator Charts (Bottom Panel)
        if (state.charts.indicators) {
            state.charts.indicators.destroy();
        }

        const ctxInd = document.getElementById('chart-indicators').getContext('2d');
        const showRSI = state.filters.rsi.enabled;

        const datasets = [];
        if (showRSI) {
            datasets.push({
                label: 'RSI (14)',
                data: stock.indicators.rsi.slice(-lookbackDays),
                borderColor: '#ec4899',
                borderWidth: 2,
                pointRadius: 0,
                yAxisID: 'yRsi'
            });
        }
        
        // Add ADX +DI -DI always
        datasets.push({
            label: 'ADX (14)',
            data: stock.indicators.adx.slice(-lookbackDays),
            borderColor: '#3b82f6',
            borderWidth: 2,
            pointRadius: 0,
            yAxisID: 'yAdx'
        });
        datasets.push({
            label: '+DI',
            data: stock.indicators.plusDI.slice(-lookbackDays),
            borderColor: '#10b981',
            borderWidth: 1,
            borderDash: [3, 3],
            pointRadius: 0,
            yAxisID: 'yAdx'
        });
        datasets.push({
            label: '-DI',
            data: stock.indicators.minusDI.slice(-lookbackDays),
            borderColor: '#ef4444',
            borderWidth: 1,
            borderDash: [3, 3],
            pointRadius: 0,
            yAxisID: 'yAdx'
        });

        state.charts.indicators = new Chart(ctxInd, {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: mutedTextColor, maxTicksLimit: 8 }
                    },
                    yRsi: {
                        type: 'linear',
                        position: 'left',
                        min: 0,
                        max: 100,
                        ticks: { color: '#ec4899' },
                        grid: { color: 'rgba(236,72,153,0.05)' }
                    },
                    yAdx: {
                        type: 'linear',
                        position: 'right',
                        min: 0,
                        max: 80,
                        ticks: { color: '#3b82f6' },
                        grid: { display: false }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: textColor, boxWidth: 12, font: { family: 'Outfit' } }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    }
                }
            }
        });
    }

    // --- Side Drawer Controls ---

    function openDetailDrawer(ticker) {
        const stock = state.stocks[ticker];
        if (!stock) return;

        state.activeTicker = ticker;

        // Highlight selected row in table
        document.querySelectorAll('#screener-tbody tr').forEach(row => {
            if (row.getAttribute('data-ticker') === ticker) {
                row.classList.add('selected');
            } else {
                row.classList.remove('selected');
            }
        });

        // Set static properties in drawer UI
        document.getElementById('detail-ticker').innerText = stock.ticker;
        document.getElementById('detail-name').innerText = stock.name;
        document.getElementById('detail-price').innerText = `₹${stock.current.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        
        // Update metric values in stats grids
        const ddYears = state.filters.drawdown.years || 1;
        document.getElementById('detail-metric-dd-label').innerText = `Drawdown (${ddYears}-Yr)`;
        document.getElementById('detail-metric-dd').innerText = `${stock.current.drawdown}%`;
        document.getElementById('detail-metric-rsi').innerText = stock.current.rsi ?? 'N/A';
        document.getElementById('detail-metric-adx').innerText = stock.current.adx ?? 'N/A';
        document.getElementById('detail-metric-sma').innerText = stock.current.aboveSMA200 ? 'Above 200 SMA' : 'Below 200 SMA';
        document.getElementById('detail-metric-sma').className = `value ${stock.current.aboveSMA200 ? 'text-green' : 'text-red'}`;

        const badge = document.getElementById('detail-status-badge');
        badge.innerText = stock.status;
        badge.className = `badge ${stock.status === 'Knife' ? 'badge-red' : 'badge-green'}`;

        // Render visual charts
        renderCharts(stock);

        // Setup journal entry form for this stock
        setupJournalForm(stock);

        const journalFormContainer = document.getElementById('journal-form-container');
        if (journalFormContainer) {
            const elements = journalFormContainer.querySelectorAll('input, select, textarea, button');
            if (USER_STATUS === 'expired') {
                elements.forEach(el => el.disabled = true);
                journalFormContainer.style.opacity = '0.5';
                journalFormContainer.style.pointerEvents = 'none';
                
                let warn = document.getElementById('journal-expired-warning');
                if (!warn) {
                    warn = document.createElement('div');
                    warn.id = 'journal-expired-warning';
                    warn.style.cssText = 'background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); color: #f87171; font-size: 11px; padding: 8px; border-radius: 6px; text-align: center; margin-bottom: 10px; font-weight: 500;';
                    warn.innerHTML = '<i class="fa-solid fa-lock"></i> Trading Journal is locked (Trial Expired)';
                    journalFormContainer.parentNode.insertBefore(warn, journalFormContainer);
                }
            } else {
                elements.forEach(el => el.disabled = false);
                journalFormContainer.style.opacity = '1';
                journalFormContainer.style.pointerEvents = 'auto';
                const warn = document.getElementById('journal-expired-warning');
                if (warn) warn.remove();
            }
        }

        // Reset campaign panel
        document.getElementById('campaign-loading').classList.add('hidden');
        document.getElementById('campaign-content').classList.add('hidden');
        document.getElementById('campaign-feedback').classList.add('hidden');

        // Reset AI Analyst panel
        const aiLoading = document.getElementById('ai-loading');
        const aiContent = document.getElementById('ai-content');
        if (aiLoading) aiLoading.classList.add('hidden');
        if (aiContent) aiContent.classList.add('hidden');

        // Reset PM Brief panel
        const pmLoading = document.getElementById('pm-brief-loading');
        const pmContent = document.getElementById('pm-brief-content-wrapper');
        const btnPublishPm = document.getElementById('btn-publish-pm-brief');
        if (pmLoading) pmLoading.classList.add('hidden');
        if (pmContent) pmContent.classList.add('hidden');
        if (btnPublishPm) btnPublishPm.classList.add('hidden');

        // Apply Premium & Superuser UI Restrictions
        const btnGen = document.getElementById('btn-generate-campaign');
        if (btnGen) {
            if (!IS_SUPERUSER) {
                btnGen.style.display = 'none';
            } else {
                btnGen.style.display = 'block';
            }
        }

        const btnGeneratePm = document.getElementById('btn-generate-pm-brief');
        if (btnGeneratePm) {
            const isProUser = (PLAN_TIER === 'pro' || USER_STATUS === 'premium' || USER_STATUS === 'pro' || IS_SUPERUSER === true);
            if (!isProUser) {
                btnGeneratePm.innerHTML = '<i class="fa-solid fa-lock"></i> Pro Analyst Only';
                btnGeneratePm.style.background = 'rgba(255, 255, 255, 0.05)';
                btnGeneratePm.style.border = '1px solid rgba(255, 255, 255, 0.1)';
                btnGeneratePm.style.color = 'var(--text-secondary)';
                btnGeneratePm.style.cursor = 'not-allowed';
            } else {
                btnGeneratePm.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Generate Brief';
                btnGeneratePm.style.background = 'linear-gradient(135deg, #a855f7, #7c3aed)';
                btnGeneratePm.style.border = 'none';
                btnGeneratePm.style.color = '#fff';
                btnGeneratePm.style.cursor = 'pointer';
            }
        }

        const btnAnalyze = document.getElementById('btn-analyze-conviction');
        if (btnAnalyze) {
            const isAIAllowed = USER_STATUS === 'premium' || USER_STATUS === 'pro' || USER_STATUS === 'trial';
            if (!isAIAllowed) {
                btnAnalyze.innerHTML = '<i class="fa-solid fa-lock"></i> Pro Analyst Only';
                btnAnalyze.style.background = 'rgba(255, 255, 255, 0.05)';
                btnAnalyze.style.border = '1px solid rgba(255, 255, 255, 0.1)';
                btnAnalyze.style.color = 'var(--text-secondary)';
                btnAnalyze.style.cursor = 'not-allowed';
            } else {
                btnAnalyze.innerHTML = '<i class="fa-solid fa-brain"></i> Analyze Conviction';
                btnAnalyze.style.background = 'linear-gradient(135deg, var(--accent-indigo), #5850ec)';
                btnAnalyze.style.border = 'none';
                btnAnalyze.style.color = '#fff';
                btnAnalyze.style.cursor = 'pointer';
            }
        }

        // Open panel
        document.getElementById('detail-drawer').classList.add('active');

        // Ensure charts resize cleanly to container dimensions once drawer animation executes
        setTimeout(() => {
            if (state.charts.price) {
                state.charts.price.resize();
            }
            if (state.charts.indicators) {
                state.charts.indicators.resize();
            }
        }, 350);
    }

    function closeDetailDrawer() {
        state.activeTicker = null;
        document.getElementById('detail-drawer').classList.remove('active');
        document.querySelectorAll('#screener-tbody tr').forEach(row => row.classList.remove('selected'));
    }

    // --- Data Loaders (Simulation vs. Zerodha Proxy) ---

    async function loadSimulationData() {
        try {
            const response = await fetch('/api/simulation/dump/?_t=' + Date.now());
            if (response.ok) {
                const result = await response.json();
                if (result.status === 'success' && result.data && Object.keys(result.data).length > 0) {
                    state.stocks = {};
                    for (const [symbol, candles] of Object.entries(result.data)) {
                        const parsedCandles = candles.map(c => ({
                            date: c[0].split('T')[0],
                            open: c[1],
                            high: c[2],
                            low: c[3],
                            close: c[4],
                            volume: c[5]
                        }));
                        state.stocks[symbol] = {
                            ticker: symbol,
                            name: `${symbol} Equity`,
                            candles: parsedCandles
                        };
                        processStockIndicators(state.stocks[symbol]);
                    }
                    const simRefreshedEl = document.getElementById('sim-last-refreshed');
                    if (simRefreshedEl && result.last_refreshed) {
                        simRefreshedEl.textContent = `Last Refreshed: ${result.last_refreshed}`;
                        simRefreshedEl.style.display = 'block';
                    }
                    showScanProgress(false);
                    hydrateActiveJournalTickers();
                    renderScreenerGrid();
                    console.log("Loaded actual historical F&O data dump from server!");
                    return;
                }
            }
        } catch (e) {
            console.warn("Server offline dump fetch failed, falling back to mock procedural generator.", e);
        }

        // Fallback to procedurally generated full Nifty 50 + F&O universe
        state.stocks = MockDataEngine.getSimulatedData();
        for (const stock of Object.values(state.stocks)) {
            processStockIndicators(stock);
        }
        const simRefreshedEl = document.getElementById('sim-last-refreshed');
        if (simRefreshedEl) {
            simRefreshedEl.textContent = `Last Refreshed: ${new Date().toISOString().split('T')[0]}`;
            simRefreshedEl.style.display = 'block';
        }
        showScanProgress(false);
        hydrateActiveJournalTickers();
        renderScreenerGrid();
    }

    function hydrateActiveJournalTickers() {
        state.journal.forEach(t => {
            if (t.status === 'Active' && !state.stocks[t.ticker]) {
                if (state.dataSource === 'simulation') {
                    // Generate simulated data for this ticker specifically
                    const simulated = MockDataEngine.generateSimulatedList([t.ticker]);
                    if (simulated[t.ticker]) {
                        state.stocks[t.ticker] = simulated[t.ticker];
                        processStockIndicators(state.stocks[t.ticker]);
                    }
                } else if (state.dataSource === 'zerodha') {
                    // Fetch Zerodha data if credentials are saved
                    const apiKey = sessionStorage.getItem('zerodha_api_key') || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA ? 'SERVER_PRECONFIGURED' : '');
                    const accessToken = sessionStorage.getItem('zerodha_access_token') || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA ? 'SERVER_PRECONFIGURED' : '');
                    if (apiKey && accessToken) {
                        fetchZerodhaData(t.ticker).catch(err => console.error(`Failed to hydrate active trade ticker ${t.ticker}:`, err));
                    }
                }
            }
        });
    }

    // Fetch data using the Django CORS-proxy views for Zerodha historical endpoint
    async function fetchZerodhaData(symbol, customToken = null) {
        if (typeof IS_SUPERUSER !== 'undefined' && !IS_SUPERUSER) {
            console.warn('Forbidden: Live Zerodha API mode is restricted to Admin / Superusers only.');
            return;
        }
        const apiKey = sessionStorage.getItem('zerodha_api_key') || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA ? 'SERVER_PRECONFIGURED' : '');
        const accessToken = sessionStorage.getItem('zerodha_access_token') || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA ? 'SERVER_PRECONFIGURED' : '');

        if (!apiKey || !accessToken) {
            alert('Zerodha API Key or Access Token is missing. Please authorize in the Credentials Panel first.');
            return;
        }

        // Set date range for historical candle requests based on drawdown lookback period
        const toDate = new Date();
        const fromDate = new Date();
        const lookupYears = 5; // Fetch 5 years of daily candles to support full RSI backtesting range
        fromDate.setFullYear(toDate.getFullYear() - lookupYears);

        const formatDate = (d) => {
            const yyyy = d.getFullYear();
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const dd = String(d.getDate()).padStart(2, '0');
            return `${yyyy}-${mm}-${dd}`;
        };

        const fromStr = formatDate(fromDate);
        const toStr = formatDate(toDate);

        // Symbol is mapped in django or supplied as numeric token
        const identifier = customToken ? customToken : symbol;
        const url = `/api/historical/?symbol=${identifier}&interval=day&from=${fromStr}&to=${toStr}`;

        try {
            const response = await fetch(url, {
                headers: {
                    'X-Kite-API-Key': apiKey,
                    'X-Kite-Access-Token': accessToken
                }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || `API Error Status ${response.status}`);
            }

            const data = await response.json();
            
            if (data.status === 'error') {
                throw new Error(data.message);
            }

            // Map Zerodha candle array to our internal Candle format
            // Zerodha returns: [ [date, open, high, low, close, volume], ... ]
            const rawCandles = data.data.candles;
            if (!rawCandles || rawCandles.length === 0) {
                throw new Error('Zerodha returned empty candle history.');
            }

            const parsedCandles = rawCandles.map(c => ({
                date: c[0].split('T')[0], // Extract just the date YYYY-MM-DD
                open: c[1],
                high: c[2],
                low: c[3],
                close: c[4],
                volume: c[5]
            }));

            // Save record
            state.stocks[symbol] = {
                ticker: symbol,
                name: customToken ? `Custom Instrument (${customToken})` : `${symbol} Equity`,
                candles: parsedCandles
            };

            // Recalculate indicators and re-render
            renderScreenerGrid();

        } catch (err) {
            console.error(err);
            const isAuthError = err.message.includes("403") || err.message.includes("401") || err.message.toLowerCase().includes("invalid") || err.message.toLowerCase().includes("token") || err.message.toLowerCase().includes("key") || err.message.toLowerCase().includes("credentials");
            if (isAuthError) {
                if (!state.zerodhaAuthErrorAlerted) {
                    state.zerodhaAuthErrorAlerted = true;
                    alert(`Failed to load Zerodha historical data: Your API credentials or Daily Access Token are invalid, missing, or expired (Status 403/401). Please verify and update them in the API Configurations drawer.`);
                }
            } else {
                alert(`Failed to load historical data for ${symbol}: ${err.message}`);
            }
        }
    }

    // Call the Gemini API via Django backend to generate a quantitative finance campaign
    async function generateAICampaign() {
        if (!IS_SUPERUSER) {
            alert('Forbidden: Generate AI Dilemma is restricted to Superusers only.');
            return;
        }

        const geminiKey = sessionStorage.getItem('gemini_api_key') || (typeof SERVER_HAS_GEMINI !== 'undefined' && SERVER_HAS_GEMINI ? 'SERVER_PRECONFIGURED' : '');
        if (!geminiKey) {
            alert('Please enter your Gemini API Key in the "API Setup" drawer first.');
            document.getElementById('credentials-drawer').classList.remove('hidden');
            return;
        }

        const stock = state.stocks[state.activeTicker];
        if (!stock) return;

        const btnGen = document.getElementById('btn-generate-campaign');
        if (btnGen) {
            btnGen.disabled = true;
            btnGen.innerText = 'Generating Scenario...';
        }

        // Show loading spinner, hide previous details
        const loading = document.getElementById('campaign-loading');
        const content = document.getElementById('campaign-content');
        const feedback = document.getElementById('campaign-feedback');
        
        loading.classList.remove('hidden');
        content.classList.add('hidden');
        feedback.classList.add('hidden');

        try {
            // Send the last 1250 candles (5 years) to support actual backtesting calculations
            const candleHistory = stock.candles.slice(-1250);

            const payload = {
                ticker: stock.ticker,
                name: stock.name,
                price: stock.current.price,
                rsi: stock.current.rsi ?? 'N/A',
                adx: stock.current.adx ?? 'N/A',
                drawdown: stock.current.drawdown,
                above_sma200: stock.current.aboveSMA200,
                candles: candleHistory
            };

            const response = await fetch('/api/generate-campaign/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Gemini-API-Key': geminiKey
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.message || `HTTP Error ${response.status}`);
            }

            const resData = await response.json();
            if (resData.status !== 'success') {
                throw new Error(resData.message);
            }

            const data = resData.data;

            // Render Dilemma content
            document.getElementById('campaign-title').innerText = data.title;
            document.getElementById('campaign-scenario').innerText = data.scenario_text;

            const optionsContainer = document.getElementById('campaign-options');
            optionsContainer.innerHTML = '';

            data.options.forEach((opt) => {
                const btn = document.createElement('button');
                btn.className = 'option-btn';
                btn.innerHTML = `
                    <span class="option-marker">Option ${opt.option_id.split('_')[1].toUpperCase()}</span>
                    <span>${opt.text}</span>
                `;
                btn.addEventListener('click', () => {
                    // Highlight selected button
                    document.querySelectorAll('.option-btn').forEach(b => b.classList.remove('selected'));
                    btn.classList.add('selected');

                    // Show the feedback panel with reasons
                    feedback.classList.remove('hidden');
                    if (opt.is_correct) {
                        feedback.className = 'feedback-panel success';
                        document.getElementById('feedback-title').innerHTML = '<i class="fa-solid fa-circle-check"></i> Sophisticated Decision';
                    } else {
                        feedback.className = 'feedback-panel error';
                        document.getElementById('feedback-title').innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> High Risk / Pitfall';
                    }
                    document.getElementById('feedback-text').innerText = opt.deep_dive_text;
                });
                optionsContainer.appendChild(btn);
            });

            loading.classList.add('hidden');
            content.classList.remove('hidden');

        } catch (error) {
            console.error(error);
            alert(`Failed to generate AI scenario: ${error.message}`);
            loading.classList.add('hidden');
        } finally {
            if (btnGen) {
                btnGen.disabled = false;
                btnGen.innerHTML = '<i class="fa-solid fa-brain"></i> Generate Dilemma / Learning Scenario';
            }
        }
    }

    async function runAIConvictionAnalysis() {
        const isAIAllowed = USER_STATUS === 'premium' || USER_STATUS === 'pro' || USER_STATUS === 'trial';
        if (!isAIAllowed) {
            alert('Analyze Conviction is restricted to Pro Analyst plan users only.');
            return;
        }

        const geminiKey = sessionStorage.getItem('gemini_api_key') || 'SERVER_PRECONFIGURED';
        
        const stock = state.stocks[state.activeTicker];
        if (!stock) return;

        const btnAnalyze = document.getElementById('btn-analyze-conviction');
        if (btnAnalyze) {
            btnAnalyze.disabled = true;
            btnAnalyze.innerText = 'Analyzing...';
        }

        // Show loading spinner, hide previous details
        const loading = document.getElementById('ai-loading');
        const content = document.getElementById('ai-content');
        
        loading.classList.remove('hidden');
        content.classList.add('hidden');

        try {
            // Send the last 1250 candles (5 years) to support actual backtesting calculations
            const candleHistory = stock.candles.slice(-1250);

            const payload = {
                ticker: stock.ticker,
                name: stock.name,
                price: stock.current.price,
                rsi: stock.current.rsi ?? 'N/A',
                adx: stock.current.adx ?? 'N/A',
                drawdown: stock.current.drawdown,
                above_sma200: stock.current.aboveSMA200,
                candles: candleHistory
            };

            const response = await fetch('/api/analyze-stock/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Gemini-API-Key': geminiKey
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.message || `HTTP Error ${response.status}`);
            }

            const resData = await response.json();
            if (resData.status !== 'success') {
                throw new Error(resData.message);
            }

            const data = resData.data;

            // Render AI content
            const scoreEl = document.getElementById('ai-score');
            scoreEl.innerText = data.conviction_score;
            
            // Set dynamic background color based on score
            if (data.conviction_score >= 75) {
                scoreEl.style.background = 'var(--color-safe)'; // Green
            } else if (data.conviction_score >= 45) {
                scoreEl.style.background = 'var(--color-warning)'; // Yellow
            } else {
                scoreEl.style.background = 'var(--color-knife)'; // Red
            }

            document.getElementById('ai-regime').innerText = data.regime;
            document.getElementById('ai-stop-loss').innerText = `Recommended Stop Loss: ${data.recommended_stop_loss_pct}%`;
            document.getElementById('ai-rationale').innerText = data.rationale;

            // Render Citations & Sources list
            const sourcesList = document.getElementById('ai-sources-list');
            sourcesList.innerHTML = '';
            if (data.sources_used && data.sources_used.length > 0) {
                data.sources_used.forEach(source => {
                    const link = document.createElement('a');
                    link.href = source.url;
                    link.target = '_blank';
                    link.className = 'citation-link';
                    link.style.display = 'flex';
                    link.style.alignItems = 'center';
                    link.style.gap = '6px';
                    link.style.fontSize = '12px';
                    link.style.color = 'var(--accent-indigo)';
                    link.style.textDecoration = 'none';
                    link.style.padding = '4px 0';
                    link.style.fontWeight = '500';
                    link.innerHTML = `<i class="fa-solid fa-arrow-up-right-from-square" style="font-size:10px;"></i> ${source.title}`;
                    sourcesList.appendChild(link);
                });
                document.getElementById('ai-sources-citations').classList.remove('hidden');
            } else {
                document.getElementById('ai-sources-citations').classList.add('hidden');
            }

            loading.classList.add('hidden');
            content.classList.remove('hidden');
        } catch (err) {
            console.error("AI analysis failed:", err);
            alert(`AI Analysis failed: ${err.message}`);
            loading.classList.add('hidden');
        } finally {
            if (btnAnalyze) {
                btnAnalyze.disabled = false;
                btnAnalyze.innerText = 'Analyze Conviction';
            }
        }
    }

    async function runPMBriefAnalysis() {
        const isProUser = (PLAN_TIER === 'pro' || USER_STATUS === 'premium' || USER_STATUS === 'pro' || IS_SUPERUSER === true);
        if (!isProUser) {
            alert('PM Research Brief is restricted to Pro Analyst plan users only.');
            return;
        }

        const geminiKey = sessionStorage.getItem('gemini_api_key') || 'SERVER_PRECONFIGURED';
        const stock = state.stocks[state.activeTicker];
        if (!stock) return;

        const btnGeneratePm = document.getElementById('btn-generate-pm-brief');
        if (btnGeneratePm) {
            btnGeneratePm.disabled = true;
            btnGeneratePm.innerText = 'Analyzing...';
        }

        const loading = document.getElementById('pm-brief-loading');
        const wrapper = document.getElementById('pm-brief-content-wrapper');
        const bodyEl = document.getElementById('pm-brief-body');
        const titleEl = document.getElementById('pm-brief-title');
        const btnPublishPm = document.getElementById('btn-publish-pm-brief');

        loading.classList.remove('hidden');
        wrapper.classList.add('hidden');
        if (btnPublishPm) btnPublishPm.classList.add('hidden');

        try {
            const windowSelector = document.getElementById('sel-pm-brief-window');
            const lookbackVal = windowSelector ? windowSelector.value : '15';

            const response = await fetch('/api/generate-pm-brief/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Gemini-API-Key': geminiKey
                },
                body: JSON.stringify({
                    ticker: stock.ticker,
                    lookback_window: parseInt(lookbackVal)
                })
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.message || `HTTP Error ${response.status}`);
            }

            const resData = await response.json();
            if (resData.status !== 'success') {
                throw new Error(resData.message);
            }

            const data = resData.data;

            // Render PM Brief
            titleEl.innerText = data.title || `Hedge Fund Research Brief: ${stock.ticker}`;
            bodyEl.innerText = data.brief || '';

            loading.classList.add('hidden');
            wrapper.classList.remove('hidden');

            // Show publish button only for Superusers/Admins
            if (btnPublishPm) {
                if (IS_SUPERUSER) {
                    btnPublishPm.classList.remove('hidden');
                } else {
                    btnPublishPm.classList.add('hidden');
                }
            }

        } catch (e) {
            alert(`Failed to generate brief: ${e.message}`);
            loading.classList.add('hidden');
        } finally {
            if (btnGeneratePm) {
                btnGeneratePm.disabled = false;
                btnGeneratePm.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Generate Brief';
            }
        }
    }

    async function publishPMBrief() {
        if (!IS_SUPERUSER) {
            alert('Only administrators can publish research briefs.');
            return;
        }

        const btnPublishPm = document.getElementById('btn-publish-pm-brief');
        if (btnPublishPm) {
            btnPublishPm.disabled = true;
            btnPublishPm.innerText = 'Publishing...';
        }

        try {
            const response = await fetch('/api/publish-pm-brief/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.message || `HTTP Error ${response.status}`);
            }

            const resData = await response.json();
            if (resData.status !== 'success') {
                throw new Error(resData.message);
            }

            alert('Research brief published successfully to community feed!');
            if (btnPublishPm) btnPublishPm.classList.add('hidden');
            
            // Reload page to show published post in the use-cases feed
            window.location.reload();

        } catch (e) {
            alert(`Publishing failed: ${e.message}`);
        } finally {
            if (btnPublishPm) {
                btnPublishPm.disabled = false;
                btnPublishPm.innerHTML = '<i class="fa-solid fa-share-nodes"></i> Publish to Community Feed';
            }
        }
    }

    // --- Market Batch Scanning ---

    function showScanProgress(visible, label = '', countText = '', percent = 0) {
        const container = document.getElementById('scan-progress-container');
        const labelEl = document.getElementById('scan-progress-label');
        const countEl = document.getElementById('scan-progress-count');
        const barEl = document.getElementById('scan-progress-bar');
        
        if (visible) {
            container.classList.remove('hidden');
            labelEl.innerText = label;
            countEl.innerText = countText;
            barEl.style.width = `${percent}%`;
        } else {
            container.classList.add('hidden');
        }
    }

    async function executeMarketScan(listType) {
        let symbols = [];
        if (listType === 'nifty50') {
            symbols = MockDataEngine.NIFTY50_LIST.filter(s => s !== 'NIFTY 50' && s !== 'NIFTY BANK' && s !== 'NIFTY IT');
        } else if (listType === 'fo') {
            symbols = [...new Set([...MockDataEngine.NIFTY50_LIST, ...MockDataEngine.FO_LIST])].filter(s => s !== 'NIFTY 50' && s !== 'NIFTY BANK' && s !== 'NIFTY IT');
        }

        if (state.dataSource === 'simulation') {
            state.stocks = {};
            renderScreenerGrid();
            closeDetailDrawer();
            
            showScanProgress(true, `Initializing simulated ${listType.toUpperCase()} scan...`, `0 / ${symbols.length}`, 0);

            // Fetch the cached dump from the server to check for actual historical F&O data
            let historicalDump = null;
            try {
                const response = await fetch('/api/simulation/dump/?_t=' + Date.now());
                if (response.ok) {
                    const result = await response.json();
                    if (result.status === 'success' && result.data) {
                        historicalDump = result.data;
                    }
                }
            } catch (e) {
                console.warn("Failed to check server historical dump, using procedural fallback.", e);
            }

            let simulatedPool = {};
            if (historicalDump) {
                for (const [symbol, candles] of Object.entries(historicalDump)) {
                    const parsedCandles = candles.map(c => ({
                        date: c[0].split('T')[0],
                        open: c[1],
                        high: c[2],
                        low: c[3],
                        close: c[4],
                        volume: c[5]
                    }));
                    simulatedPool[symbol] = {
                        ticker: symbol,
                        name: `${symbol} Equity`,
                        candles: parsedCandles
                    };
                }
            } else {
                simulatedPool = listType === 'nifty50' ? MockDataEngine.getSimulatedNifty50() : MockDataEngine.getSimulatedFO();
            }
            
            for (let i = 0; i < symbols.length; i++) {
                const sym = symbols[i];
                if (simulatedPool[sym]) {
                    state.stocks[sym] = simulatedPool[sym];
                } else {
                    const fallbackSim = MockDataEngine.generateSimulatedList([sym]);
                    state.stocks[sym] = fallbackSim[sym];
                }
                processStockIndicators(state.stocks[sym]);
                renderScreenerGrid();
                
                const pct = Math.round(((i + 1) / symbols.length) * 100);
                showScanProgress(true, `Simulated scan: processing ${sym}...`, `${i + 1} / ${symbols.length}`, pct);
                
                await new Promise(r => setTimeout(r, 45));
            }
            
            showScanProgress(false);
        } else {
            // Zerodha Mode
            if (typeof IS_SUPERUSER !== 'undefined' && !IS_SUPERUSER) {
                alert('Forbidden: Live Zerodha API mode is restricted to Admin and Superusers only.');
                return;
            }
            const apiKey = sessionStorage.getItem('zerodha_api_key') || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA ? 'SERVER_PRECONFIGURED' : '');
            const accessToken = sessionStorage.getItem('zerodha_access_token') || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA ? 'SERVER_PRECONFIGURED' : '');
            if (!apiKey || !accessToken) {
                alert("Please configure your Zerodha Kite Credentials first in the top-right header!");
                const credsDrawer = document.getElementById('credentials-drawer');
                if (credsDrawer) credsDrawer.classList.remove('hidden');
                return;
            }
            
            state.stocks = {};
            renderScreenerGrid();
            closeDetailDrawer();
            
            showScanProgress(true, `Initializing Zerodha scan for ${listType.toUpperCase()}...`, `0 / ${symbols.length}`, 0);
            
            const toDate = new Date();
            const fromDate = new Date();
            // Fetch up to 5 years for actual backtesting support
            fromDate.setFullYear(toDate.getFullYear() - 5);
            const fromStr = fromDate.toISOString().split('T')[0];
            const toStr = toDate.toISOString().split('T')[0];
            
            let successCount = 0;
            for (let i = 0; i < symbols.length; i++) {
                const sym = symbols[i];
                showScanProgress(true, `Fetching ${sym} from Zerodha...`, `${i} / ${symbols.length}`, Math.round((i / symbols.length) * 100));
                
                try {
                    const url = `/api/historical/?symbol=${sym}&interval=day&from=${fromStr}&to=${toStr}`;
                    const response = await fetch(url, {
                        headers: {
                            'X-Kite-API-Key': apiKey,
                            'X-Kite-Access-Token': accessToken
                        }
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        if (data.status === 'success' && data.data && data.data.candles) {
                            const parsedCandles = data.data.candles.map(c => ({
                                date: c[0].split('T')[0],
                                open: c[1],
                                high: c[2],
                                low: c[3],
                                close: c[4],
                                volume: c[5]
                            }));
                            
                            state.stocks[sym] = {
                                ticker: sym,
                                name: `${sym} Equity`,
                                candles: parsedCandles
                            };
                            
                            processStockIndicators(state.stocks[sym]);
                            renderScreenerGrid();
                            successCount++;
                        }
                    }
                } catch (err) {
                    console.error(`Failed to load ${sym}:`, err);
                }
                
                // Rate limit respect delay (3 req/sec)
                await new Promise(r => setTimeout(r, 350));
            }
            
            showScanProgress(false);
            alert(`Zerodha scan completed! Successfully loaded ${successCount} out of ${symbols.length} tickers.`);
        }
    }

    // --- Init & UI Binding ---

    function bindEvents() {
        // Toggle API setup drawer
        const btnToggleCreds = document.getElementById('btn-toggle-credentials');
        const credsDrawer = document.getElementById('credentials-drawer');
        const zerodhaAddTicker = document.getElementById('zerodha-add-ticker-section');
        const btnSourceSim = document.getElementById('btn-source-sim');
        const btnSourceZerodha = document.getElementById('btn-source-zerodha');

        if (btnToggleCreds && credsDrawer) {
            btnToggleCreds.addEventListener('click', () => {
                credsDrawer.classList.toggle('hidden');
            });
        }

        // Stock Universe filter bindings (All Stocks, Nifty 50, Nifty F&O)
        const universeButtons = document.querySelectorAll('.universe-btn');
        const selFilterUniverse = document.getElementById('sel-filter-universe');

        function setUniverseFilter(universe) {
            state.universeFilter = universe;
            
            universeButtons.forEach(btn => {
                if (btn.getAttribute('data-universe') === universe) {
                    btn.classList.add('active');
                    btn.style.background = 'rgba(255, 255, 255, 0.12)';
                    btn.style.color = 'var(--text-primary)';
                    btn.style.fontWeight = '600';
                } else {
                    btn.classList.remove('active');
                    btn.style.background = 'transparent';
                    btn.style.color = 'var(--text-secondary)';
                    btn.style.fontWeight = '500';
                }
            });

            if (selFilterUniverse && selFilterUniverse.value !== universe) {
                selFilterUniverse.value = universe;
            }

            renderScreenerGrid();
        }

        universeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                setUniverseFilter(btn.getAttribute('data-universe'));
            });
        });

        if (selFilterUniverse) {
            selFilterUniverse.addEventListener('change', (e) => {
                setUniverseFilter(e.target.value);
            });
        }

        // Zerodha Admin Nifty 50 Scan Button
        const btnScanNiftyZerodha = document.getElementById('btn-scan-nifty-zerodha');
        if (btnScanNiftyZerodha) {
            btnScanNiftyZerodha.addEventListener('click', () => {
                executeMarketScan('nifty50');
            });
        }

        // Source toggle buttons
        if (btnSourceSim) {
            btnSourceSim.addEventListener('click', (e) => {
                btnSourceSim.classList.add('active');
                if (btnSourceZerodha) btnSourceZerodha.classList.remove('active');
                if (credsDrawer) credsDrawer.classList.add('hidden');
                if (zerodhaAddTicker) zerodhaAddTicker.classList.add('hidden');
                state.dataSource = 'simulation';
                closeDetailDrawer();
                loadSimulationData();
            });
        }

        if (btnSourceZerodha) {
            btnSourceZerodha.addEventListener('click', (e) => {
                if (typeof IS_SUPERUSER !== 'undefined' && !IS_SUPERUSER) {
                    alert('Forbidden: Live Zerodha API mode is restricted to Admin and Superusers only.');
                    return;
                }
                state.zerodhaAuthErrorAlerted = false; // Reset auth alert flag
                btnSourceZerodha.classList.add('active');
                if (btnSourceSim) btnSourceSim.classList.remove('active');
                if (credsDrawer) credsDrawer.classList.remove('hidden');
                if (zerodhaAddTicker) zerodhaAddTicker.classList.remove('hidden');
                const simRefreshedEl = document.getElementById('sim-last-refreshed');
                if (simRefreshedEl) simRefreshedEl.style.display = 'none';
                state.dataSource = 'zerodha';
                closeDetailDrawer();

                // Clear simulation pool, wait for auth inputs
                state.stocks = {};
                
                // Hydrate credentials inputs if already saved in session storage
                const savedKey = sessionStorage.getItem('zerodha_api_key');
                const savedToken = sessionStorage.getItem('zerodha_access_token');
                const savedGemini = sessionStorage.getItem('gemini_api_key');
                const keyInput = document.getElementById('zerodha-api-key');
                const tokenInput = document.getElementById('zerodha-access-token');
                const geminiInput = document.getElementById('gemini-api-key');
                if (savedKey && keyInput) keyInput.value = savedKey;
                if (savedToken && tokenInput) tokenInput.value = savedToken;
                if (savedGemini && geminiInput) geminiInput.value = savedGemini;

                const isPreconfigZerodha = (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA);
                if (isPreconfigZerodha) {
                    if (keyInput) keyInput.placeholder = "Preconfigured in .env";
                    if (tokenInput) tokenInput.placeholder = "Preconfigured in .env";
                }
                if (typeof SERVER_HAS_GEMINI !== 'undefined' && SERVER_HAS_GEMINI && geminiInput) {
                    geminiInput.placeholder = "Preconfigured in .env";
                }

                if ((savedKey && savedToken) || isPreconfigZerodha) {
                    // Pre-populate some index tickers
                    fetchZerodhaData('RELIANCE');
                    fetchZerodhaData('TCS');
                    fetchZerodhaData('INFY');
                    hydrateActiveJournalTickers();
                } else {
                    hydrateActiveJournalTickers();
                    renderScreenerGrid();
                }
            });
        }

        // Bind Upgrade Premium Click Triggers (GPay Payment Modal Gate)
        const gpayModal = document.getElementById('gpay-modal');
        const gpayInput = document.getElementById('gpay-state-input');
        const gpayProcessing = document.getElementById('gpay-state-processing');
        const gpaySuccess = document.getElementById('gpay-state-success');

        document.querySelectorAll('.btn-trigger-upgrade').forEach(btn => {
            btn.addEventListener('click', () => {
                if (gpayModal) {
                    // Reset modal states
                    gpayInput.classList.remove('hidden');
                    gpayProcessing.classList.add('hidden');
                    gpaySuccess.classList.add('hidden');
                    document.getElementById('gpay-upi-id').value = '';
                    document.getElementById('gpay-utr-id').value = '';
                    
                    // Render current plan badge and dynamic plan suggestion selector
                    const currentPlanBadge = document.getElementById('gpay-current-plan-badge');
                    const suggestionBox = document.getElementById('gpay-plan-suggestion-box');
                    const planSelector = document.getElementById('gpay-plan-selector');

                    if (currentPlanBadge) {
                        let displayName = 'Standard Free';
                        if (typeof PLAN_TIER !== 'undefined') {
                            if (PLAN_TIER === 'classic') displayName = 'Classic Engine';
                            else if (PLAN_TIER === 'pro') displayName = 'Pro Analyst';
                        }
                        currentPlanBadge.innerText = displayName;
                    }

                    if (suggestionBox && planSelector) {
                        planSelector.innerHTML = '';
                        if (typeof PLAN_TIER !== 'undefined') {
                            if (PLAN_TIER === 'classic') {
                                suggestionBox.innerHTML = '<i class="fa-solid fa-crown" style="color:#fbbf24;"></i> You are a Classic member! Upgrade to Pro Analyst for ₹199/month to unlock advanced indicators and AI conviction analyst.';
                                const opt = document.createElement('option');
                                opt.value = 'pro';
                                opt.setAttribute('data-amount', '199');
                                opt.innerText = 'Pro Analyst (₹199.00 / Month)';
                                planSelector.appendChild(opt);
                            } else if (PLAN_TIER === 'pro') {
                                suggestionBox.innerHTML = '<i class="fa-solid fa-arrows-spin" style="color:#60a5fa;"></i> Repeat subscription for next month. Renew Pro Analyst for ₹199 to keep access to all features.';
                                const opt = document.createElement('option');
                                opt.value = 'pro';
                                opt.setAttribute('data-amount', '199');
                                opt.innerText = 'Pro Analyst Renewal (₹199.00 / Month)';
                                planSelector.appendChild(opt);
                            } else {
                                suggestionBox.innerHTML = '<i class="fa-solid fa-sparkles" style="color:#a78bfa;"></i> Standard Free plan. Upgrade to Classic (₹299 one-time) for technical strategies or Pro (₹199/mo) for everything.';
                                const opt1 = document.createElement('option');
                                opt1.value = 'classic';
                                opt1.setAttribute('data-amount', '299');
                                opt1.innerText = 'Classic Engine (₹299.00 One-time)';
                                const opt2 = document.createElement('option');
                                opt2.value = 'pro';
                                opt2.setAttribute('data-amount', '199');
                                opt2.innerText = 'Pro Analyst (₹199.00 / Month)';
                                planSelector.appendChild(opt1);
                                planSelector.appendChild(opt2);
                            }
                        }
                    }

                    // Helper function to dynamically update payment link and redraw QR code
                    function drawGPayQR() {
                        const selectedOption = planSelector ? planSelector.options[planSelector.selectedIndex] : null;
                        const plan = planSelector ? planSelector.value : 'classic';
                        const amount = selectedOption ? selectedOption.getAttribute('data-amount') : '299';
                        
                        const upiId = (typeof DEVELOPER_UPI_ID !== 'undefined' && DEVELOPER_UPI_ID) ? DEVELOPER_UPI_ID : 'arunj@okaxis';
                        const planLabel = plan === 'classic' ? 'Classic%20Engine%20Upgrade' : 'Pro%20Analyst%20Subscription';
                        const upiUri = `upi://pay?pa=${upiId}&pn=TradeKriya&am=${amount}.00&cu=INR&tn=${planLabel}`;
                        
                        const qrcodeContainer = document.getElementById('gpay-qrcode-container');
                        if (qrcodeContainer && typeof QRCode !== 'undefined') {
                            qrcodeContainer.innerHTML = '';
                            new QRCode(qrcodeContainer, {
                                text: upiUri,
                                width: 120,
                                height: 120,
                                colorDark: "#000000",
                                colorLight: "#ffffff",
                                correctLevel: QRCode.CorrectLevel.M
                            });
                        }
                    }

                    // Bind dynamic changes to plan selection
                    if (planSelector) {
                        planSelector.removeEventListener('change', drawGPayQR);
                        planSelector.addEventListener('change', drawGPayQR);
                    }

                    // Initial draw
                    drawGPayQR();

                    // Show modal
                    gpayModal.classList.remove('hidden');
                }
            });
        });

        // Close GPay Modal
        const btnCloseGPay = document.getElementById('btn-close-gpay');
        if (btnCloseGPay) {
            btnCloseGPay.addEventListener('click', () => {
                gpayModal.classList.add('hidden');
            });
        }

        // Handle GPay Submission
        const btnGPaySubmit = document.getElementById('btn-gpay-submit');
        if (btnGPaySubmit) {
            btnGPaySubmit.addEventListener('click', async () => {
                const upiVal = document.getElementById('gpay-upi-id').value.trim();
                const utrVal = document.getElementById('gpay-utr-id').value.trim();
                const planSelector = document.getElementById('gpay-plan-selector');
                const plan = planSelector ? planSelector.value : 'classic';
                const amount = plan === 'classic' ? 299.00 : 199.00;

                if (!upiVal) {
                    alert('Please enter a valid GPay UPI ID or phone number.');
                    return;
                }
                if (!utrVal) {
                    alert('Please enter the 12-digit payment transaction UTR / Ref No.');
                    return;
                }
                if (!/^\d{12}$/.test(utrVal)) {
                    alert('Invalid transaction reference! The UTR Number must be exactly 12 numeric digits.');
                    return;
                }

                // If user is on a mobile device, open the UPI deep link directly
                const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
                const upiId = (typeof DEVELOPER_UPI_ID !== 'undefined' && DEVELOPER_UPI_ID) ? DEVELOPER_UPI_ID : 'arunj@okaxis';
                const planLabel = plan === 'classic' ? 'Classic%20Engine%20Upgrade' : 'Pro%20Analyst%20Subscription';
                const upiUri = `upi://pay?pa=${upiId}&pn=TradeKriya&am=${amount}.00&cu=INR&tn=${planLabel}`;

                if (isMobile) {
                    window.location.href = upiUri;
                }

                // Show processing spinner
                gpayInput.classList.add('hidden');
                gpayProcessing.classList.remove('hidden');

                // Verify transaction code
                setTimeout(async () => {
                    try {
                        const response = await fetch('/api/upgrade-premium/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                payment_status: 'success',
                                provider: 'gpay',
                                amount: amount,
                                plan: plan,
                                utr: utrVal,
                                upi_id: upiVal
                            })
                        });

                        if (response.ok) {
                            const data = await response.json();
                            
                            // Customize success messages to explain manual UTR verification
                            const title = document.getElementById('gpay-success-title');
                            const desc = document.getElementById('gpay-success-message');
                            
                            if (title) title.innerText = 'Request Submitted!';
                            if (desc) desc.innerText = `Your payment of ₹${amount}.00 (UTR: ${utrVal}) has been sent for verification. Upgrade will activate shortly once approved by Admin.`;
                            
                            gpayProcessing.classList.add('hidden');
                            gpaySuccess.classList.remove('hidden');
                        } else {
                            const err = await response.json();
                            alert(`Verification failed: ${err.message}`);
                            gpayProcessing.classList.add('hidden');
                            gpayInput.classList.remove('hidden');
                        }
                    } catch (e) {
                        alert(`Network error during payment verification: ${e.message}`);
                        gpayProcessing.classList.add('hidden');
                        gpayInput.classList.remove('hidden');
                    }
                }, 3000);
            });
        }

        // Close success and reload dashboard
        const btnGPaySuccessDone = document.getElementById('btn-gpay-success-done');
        if (btnGPaySuccessDone) {
            btnGPaySuccessDone.addEventListener('click', () => {
                gpayModal.classList.add('hidden');
                window.location.reload();
            });
        }

        // Save Configurations Click (Zerodha + Gemini)
        const btnAuthSave = document.getElementById('btn-auth-save');
        if (btnAuthSave) {
            btnAuthSave.addEventListener('click', () => {
                state.zerodhaAuthErrorAlerted = false; // Reset auth alert flag
                const keyInput = document.getElementById('zerodha-api-key');
                const tokenInput = document.getElementById('zerodha-access-token');
                const geminiInput = document.getElementById('gemini-api-key');
                const key = keyInput ? keyInput.value.trim() : '';
                const token = tokenInput ? tokenInput.value.trim() : '';
                const gemini = geminiInput ? geminiInput.value.trim() : '';

            if (key) {
                sessionStorage.setItem('zerodha_api_key', key);
            } else {
                sessionStorage.removeItem('zerodha_api_key');
            }

            if (token) {
                sessionStorage.setItem('zerodha_access_token', token);
            } else {
                sessionStorage.removeItem('zerodha_access_token');
            }

            if (gemini) {
                sessionStorage.setItem('gemini_api_key', gemini);
            } else {
                sessionStorage.removeItem('gemini_api_key');
            }

            alert('API settings saved successfully. Empty values reverted back to preconfigured .env settings.');

            // If in Zerodha API mode, reload data
            if (state.dataSource === 'zerodha') {
                state.stocks = {};
                const activeKey = key || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA);
                const activeToken = token || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA);
                if (activeKey && activeToken) {
                    fetchZerodhaData('RELIANCE');
                    fetchZerodhaData('TCS');
                    fetchZerodhaData('INFY');
                }
                hydrateActiveJournalTickers();
            }
        });
    }

        // Reset to preconfigured .env settings Click
        const btnAuthReset = document.getElementById('btn-auth-reset');
        if (btnAuthReset) {
            btnAuthReset.addEventListener('click', () => {
                state.zerodhaAuthErrorAlerted = false; // Reset auth alert flag
                document.getElementById('zerodha-api-key').value = '';
                document.getElementById('zerodha-access-token').value = '';
                document.getElementById('gemini-api-key').value = '';

                sessionStorage.removeItem('zerodha_api_key');
                sessionStorage.removeItem('zerodha_access_token');
                sessionStorage.removeItem('gemini_api_key');

                alert('API configurations reset successfully. Reverted back to preconfigured .env settings.');

                // If in Zerodha API mode, reload data
                if (state.dataSource === 'zerodha') {
                    state.stocks = {};
                    if (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA) {
                        fetchZerodhaData('RELIANCE');
                        fetchZerodhaData('TCS');
                        fetchZerodhaData('INFY');
                    }
                    hydrateActiveJournalTickers();
                }
            });
        }

        // Bind generate campaign button
        document.getElementById('btn-generate-campaign').addEventListener('click', generateAICampaign);

        // Bind analyze conviction button
        const btnConv = document.getElementById('btn-analyze-conviction');
        if (btnConv) {
            btnConv.addEventListener('click', runAIConvictionAnalysis);
        }

        // Bind PM brief generate and publish buttons
        const btnGeneratePm = document.getElementById('btn-generate-pm-brief');
        if (btnGeneratePm) {
            btnGeneratePm.addEventListener('click', runPMBriefAnalysis);
        }
        const btnPublishPm = document.getElementById('btn-publish-pm-brief');
        if (btnPublishPm) {
            btnPublishPm.addEventListener('click', publishPMBrief);
        }

        // Add Ticker Click
        const btnAddTicker = document.getElementById('btn-add-ticker');
        if (btnAddTicker) {
            btnAddTicker.addEventListener('click', () => {
                const selectSym = document.getElementById('sel-add-symbol');
                const customTokenInput = document.getElementById('txt-add-custom-token');
                const customToken = customTokenInput ? customTokenInput.value.trim() : '';
                
                const selectedVal = selectSym ? selectSym.value : '';

                if (customToken) {
                    const tickerLabel = `INSTRUMENT-${customToken}`;
                    fetchZerodhaData(tickerLabel, customToken);
                    if (customTokenInput) customTokenInput.value = '';
                } else if (selectedVal) {
                    fetchZerodhaData(selectedVal);
                } else {
                    alert('Please select a stock or input a custom instrument token.');
                }
            });
        }

        // Filter Checkboxes & Sliders
        const configureFilterToggle = (chkId, filterKey) => {
            document.getElementById(chkId).addEventListener('change', (e) => {
                state.filters[filterKey].enabled = e.target.checked;
                renderScreenerGrid();
                if (state.activeTicker) {
                    openDetailDrawer(state.activeTicker); // refresh charts highlight
                }
            });
        };

        configureFilterToggle('chk-filter-sma', 'sma');
        configureFilterToggle('chk-filter-rsi', 'rsi');
        configureFilterToggle('chk-filter-adx', 'adx');
        configureFilterToggle('chk-filter-drawdown', 'drawdown');

        // RSI Slider
        const sliderRsi = document.getElementById('rng-filter-rsi');
        sliderRsi.addEventListener('input', (e) => {
            state.filters.rsi.threshold = parseInt(e.target.value);
            document.getElementById('val-filter-rsi').innerText = e.target.value;
            renderScreenerGrid();
            if (state.activeTicker) openDetailDrawer(state.activeTicker);
        });

        // ADX Slider
        const sliderAdx = document.getElementById('rng-filter-adx');
        sliderAdx.addEventListener('input', (e) => {
            state.filters.adx.threshold = parseInt(e.target.value);
            document.getElementById('val-filter-adx').innerText = e.target.value;
            renderScreenerGrid();
            if (state.activeTicker) openDetailDrawer(state.activeTicker);
        });

        // Drawdown Slider
        const sliderDd = document.getElementById('rng-filter-drawdown');
        sliderDd.addEventListener('input', (e) => {
            state.filters.drawdown.threshold = parseInt(e.target.value);
            document.getElementById('val-filter-drawdown').innerText = `${e.target.value}%`;
            renderScreenerGrid();
            if (state.activeTicker) openDetailDrawer(state.activeTicker);
        });

        // Drawdown Lookback Years Selector
        const selectDdYears = document.getElementById('sel-filter-drawdown-years');
        selectDdYears.addEventListener('change', (e) => {
            state.filters.drawdown.years = parseInt(e.target.value);
            
            // If in Zerodha API mode, re-fetch active tickers with new range
            if (state.dataSource === 'zerodha') {
                const activeTickers = Object.keys(state.stocks);
                if (activeTickers.length > 0) {
                    activeTickers.forEach(ticker => {
                        fetchZerodhaData(ticker);
                    });
                }
            } else {
                renderScreenerGrid();
                if (state.activeTicker) openDetailDrawer(state.activeTicker);
            }
        });

        // Search Ticker
        document.getElementById('grid-search').addEventListener('input', () => {
            renderScreenerGrid();
        });

        // Status Filter dropdown change listener
        const selectStatus = document.getElementById('sel-filter-status');
        if (selectStatus) {
            selectStatus.addEventListener('change', () => {
                state.filters.status = selectStatus.value;
                renderScreenerGrid();
            });
        }

        // Performance Filter dropdown change listener
        const selectPerf = document.getElementById('sel-filter-performance');
        if (selectPerf) {
            selectPerf.addEventListener('change', () => {
                renderScreenerGrid();
            });
        }

        // Reset Filters Button
        document.getElementById('btn-reset-filters').addEventListener('click', () => {
            document.getElementById('chk-filter-sma').checked = true;
            document.getElementById('chk-filter-rsi').checked = true;
            document.getElementById('chk-filter-adx').checked = true;
            document.getElementById('chk-filter-drawdown').checked = true;

            sliderRsi.value = 30;
            sliderAdx.value = 25;
            sliderDd.value = 30;
            selectDdYears.value = "1";
            if (selectStatus) selectStatus.value = "all";
            if (selectPerf) selectPerf.value = "all";
            if (selFilterUniverse) selFilterUniverse.value = "all";
            setUniverseFilter("all");

            document.getElementById('val-filter-rsi').innerText = '30';
            document.getElementById('val-filter-adx').innerText = '25';
            document.getElementById('val-filter-drawdown').innerText = '30%';

            state.filters = {
                status: 'all',
                sma: { enabled: true },
                rsi: { enabled: true, threshold: 30 },
                adx: { enabled: true, threshold: 25 },
                drawdown: { enabled: true, threshold: 30, years: 1 }
            };

            renderScreenerGrid();
            if (state.activeTicker) openDetailDrawer(state.activeTicker);
        });

        // Admin Sync Controls
        const btnAdminSync = document.getElementById('btn-admin-sync-dump');
        const syncStatusDiv = document.getElementById('admin-sync-status');
        if (btnAdminSync && syncStatusDiv) {
            btnAdminSync.addEventListener('click', async () => {
                btnAdminSync.disabled = true;
                syncStatusDiv.style.color = 'var(--text-secondary)';
                syncStatusDiv.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Initializing historical F&O dump sync...';

                try {
                    // Extract CSRF token from cookie
                    const getCookie = (name) => {
                        let cookieValue = null;
                        if (document.cookie && document.cookie !== '') {
                            const cookies = document.cookie.split(';');
                            for (let i = 0; i < cookies.length; i++) {
                                const cookie = cookies[i].trim();
                                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                                    break;
                                }
                            }
                        }
                        return cookieValue;
                    };
                    const csrftoken = getCookie('csrftoken');

                    // Compile all symbols to sync
                    const allSymbols = [...new Set([...MockDataEngine.NIFTY50_LIST, ...MockDataEngine.FO_LIST])];
                    const batchSize = 5;
                    const batches = [];
                    for (let i = 0; i < allSymbols.length; i += batchSize) {
                        batches.push(allSymbols.slice(i, i + batchSize));
                    }

                    let totalSyncCount = 0;
                    let totalUpdatedTickers = 0;

                    for (let i = 0; i < batches.length; i++) {
                        const batch = batches[i];
                        const pct = Math.round(((i + 1) / batches.length) * 100);
                        syncStatusDiv.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Syncing batch ${i + 1}/${batches.length} (${pct}%)...<br><span style="font-size:9px; opacity:0.7;">[${batch.join(', ')}]</span>`;

                        const response = await fetch('/api/admin/sync-dump/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': csrftoken
                            },
                            body: JSON.stringify({ symbols: batch })
                        });

                        if (!response.ok) {
                            const err = await response.json();
                            throw new Error(err.message || `HTTP ${response.status}`);
                        }

                        const result = await response.json();
                        if (result.status === 'success') {
                            totalSyncCount += result.sync_count;
                            totalUpdatedTickers += result.updated_tickers_count;
                        }
                    }

                    syncStatusDiv.style.color = 'var(--color-safe)';
                    syncStatusDiv.innerHTML = `<i class="fa-solid fa-circle-check"></i> Sync complete! Synced ${totalSyncCount} candles across ${totalUpdatedTickers} tickers.`;

                    // If current mode is simulation, reload data to reflect the changes
                    if (state.dataSource === 'simulation') {
                        await loadSimulationData();
                    }
                } catch (err) {
                    console.error("Admin sync failed:", err);
                    syncStatusDiv.style.color = 'var(--color-knife)';
                    syncStatusDiv.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Sync aborted: ${err.message}`;
                } finally {
                    btnAdminSync.disabled = false;
                }
            });
        }

        // Admin Marketing Agent controls
        const btnAdminMarketing = document.getElementById('btn-admin-marketing-agent');
        const marketingStatusDiv = document.getElementById('admin-marketing-status');
        if (btnAdminMarketing && marketingStatusDiv) {
            btnAdminMarketing.addEventListener('click', async () => {
                const themeVal = document.getElementById('sel-marketing-theme').value;
                const symbolVal = document.getElementById('txt-marketing-symbol').value.trim();

                btnAdminMarketing.disabled = true;
                marketingStatusDiv.style.color = 'var(--text-secondary)';
                marketingStatusDiv.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Triggering campaign generation...';

                try {
                    const getCookie = (name) => {
                        let cookieValue = null;
                        if (document.cookie && document.cookie !== '') {
                            const cookies = document.cookie.split(';');
                            for (let i = 0; i < cookies.length; i++) {
                                const cookie = cookies[i].trim();
                                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                                    break;
                                }
                            }
                        }
                        return cookieValue;
                    };
                    const csrftoken = getCookie('csrftoken');

                    const response = await fetch('/api/admin/run-marketing-agent/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrftoken
                        },
                        body: JSON.stringify({
                            theme: themeVal || null,
                            symbol: symbolVal || null
                        })
                    });

                    const data = await response.json();
                    if (response.ok && data.status === 'success') {
                        marketingStatusDiv.style.color = '#10b981';
                        marketingStatusDiv.innerHTML = '<i class="fa-solid fa-circle-check"></i> Campaign generated successfully! Draft saved under marketing_campaigns/ directory.';
                        console.log("Marketing Agent logs:", data.logs);
                    } else {
                        throw new Error(data.message || 'Server returned an error');
                    }
                } catch (err) {
                    console.error("Marketing agent trigger failed:", err);
                    marketingStatusDiv.style.color = '#ef4444';
                    marketingStatusDiv.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Failed: ${err.message}`;
                } finally {
                    btnAdminMarketing.disabled = false;
                }
            });
        }

        // Admin User License Management
        // Admin User License Management
        const adminUserListContainer = document.getElementById('admin-user-list');
        const adminNotificationsListContainer = document.getElementById('admin-notifications-list');
        const btnClearNotifications = document.getElementById('btn-clear-notifications');

        if (adminUserListContainer) {
            async function refreshAdminUserList() {
                try {
                    const response = await fetch('/api/admin/list-users/');
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    const result = await response.json();
                    if (result.status === 'success') {
                        adminUserListContainer.innerHTML = '';
                        if (result.users && result.users.length > 0) {
                            result.users.forEach(user => {
                                const row = document.createElement('div');
                                row.style.cssText = 'display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 6px 10px; border-radius: 6px; margin-bottom: 4px;';
                                
                                let displayStatus = user.status;
                                if (user.status === 'premium') displayStatus = 'Premium (All)';
                                else if (user.status === 'classic') displayStatus = 'Classic Engine';
                                else if (user.status === 'pro') displayStatus = 'Pro Analyst';
                                else if (user.status === 'trial') displayStatus = 'Trial';
                                else if (user.status === 'expired') displayStatus = 'Standard (Free)';

                                const info = document.createElement('div');
                                info.innerHTML = `
                                    <span style="font-size: 11px; font-weight: 600; color: var(--text-primary); display: block;">${user.username}</span>
                                    <span style="font-size: 9px; font-weight: 500; text-transform: uppercase; color: ${user.is_premium ? '#34d399' : (user.status === 'trial' ? '#60a5fa' : '#f87171')};">${displayStatus}</span>
                                `;
                                row.appendChild(info);

                                if (user.is_premium) {
                                    const btnDowngrade = document.createElement('button');
                                    btnDowngrade.className = 'primary-btn';
                                    btnDowngrade.style.cssText = 'font-size: 9px; padding: 3px 8px; margin: 0; background: linear-gradient(135deg, #f87171, #ef4444); border: none; cursor: pointer; color: #fff; border-radius: 4px; font-weight: 600;';
                                    btnDowngrade.innerHTML = '<i class="fa-solid fa-arrow-down"></i> Downgrade';
                                    btnDowngrade.addEventListener('click', async () => {
                                        if (confirm(`Are you sure you want to downgrade ${user.username} to Standard Plan?`)) {
                                            btnDowngrade.disabled = true;
                                            btnDowngrade.innerText = 'Updating...';
                                            try {
                                                const res = await fetch('/api/admin/downgrade-user/', {
                                                    method: 'POST',
                                                    headers: {
                                                        'Content-Type': 'application/json'
                                                    },
                                                    body: JSON.stringify({ username: user.username })
                                                });
                                                if (res.ok) {
                                                    alert(`Successfully downgraded ${user.username} to Standard Plan.`);
                                                    refreshAdminUserList();
                                                } else {
                                                    const err = await res.json();
                                                    alert(`Downgrade failed: ${err.message}`);
                                                }
                                            } catch (e) {
                                                alert(`Error downgrading: ${e.message}`);
                                            } finally {
                                                btnDowngrade.disabled = false;
                                            }
                                        }
                                    });
                                    row.appendChild(btnDowngrade);
                                } else {
                                    const btnUpgrade = document.createElement('button');
                                    btnUpgrade.className = 'primary-btn';
                                    btnUpgrade.style.cssText = 'font-size: 9px; padding: 3px 8px; margin: 0; background: linear-gradient(135deg, #10b981, #059669); border: none; cursor: pointer; color: #fff; border-radius: 4px; font-weight: 600;';
                                    btnUpgrade.innerHTML = '<i class="fa-solid fa-arrow-up"></i> Upgrade';
                                    btnUpgrade.addEventListener('click', async () => {
                                        const choice = prompt(`Select target plan for ${user.username}. Enter "classic" or "pro":`, "pro");
                                        if (choice !== null) {
                                            const cleanChoice = choice.trim().toLowerCase();
                                            if (cleanChoice !== 'classic' && cleanChoice !== 'pro') {
                                                alert('Invalid option. Please enter exactly "classic" or "pro".');
                                                return;
                                            }
                                            btnUpgrade.disabled = true;
                                            btnUpgrade.innerText = 'Updating...';
                                            try {
                                                const res = await fetch('/api/admin/upgrade-user/', {
                                                    method: 'POST',
                                                    headers: {
                                                        'Content-Type': 'application/json'
                                                    },
                                                    body: JSON.stringify({ username: user.username, plan: cleanChoice })
                                                });
                                                if (res.ok) {
                                                    alert(`Successfully upgraded ${user.username} to ${cleanChoice === 'classic' ? 'Classic Engine' : 'Pro Analyst'}.`);
                                                    refreshAdminUserList();
                                                } else {
                                                    const err = await res.json();
                                                    alert(`Upgrade failed: ${err.message}`);
                                                }
                                            } catch (e) {
                                                alert(`Error upgrading: ${e.message}`);
                                            } finally {
                                                btnUpgrade.disabled = false;
                                            }
                                        }
                                    });
                                    row.appendChild(btnUpgrade);
                                }
                                adminUserListContainer.appendChild(row);
                            });
                        } else {
                            adminUserListContainer.innerHTML = '<span style="font-size: 11px; color: var(--text-secondary);">No user records found.</span>';
                        }
                    }
                } catch (e) {
                    console.error("Failed to load user licenses:", e);
                    adminUserListContainer.innerHTML = '<span style="font-size: 10px; color: var(--color-knife);"><i class="fa-solid fa-triangle-exclamation"></i> Error loading licenses.</span>';
                }
            }
            refreshAdminUserList();
        }

        if (adminNotificationsListContainer) {
            async function refreshAdminNotifications() {
                try {
                    const response = await fetch('/api/admin/notifications/');
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    const result = await response.json();
                    if (result.status === 'success') {
                        adminNotificationsListContainer.innerHTML = '';
                        if (result.notifications && result.notifications.length > 0) {
                            result.notifications.forEach(notif => {
                                const el = document.createElement('div');
                                el.style.cssText = 'background: rgba(255,255,255,0.02); border: 1px solid rgba(233,128,93,0.1); padding: 8px; border-radius: 6px; font-size: 10px; color: var(--text-secondary); line-height: 1.4; margin-bottom: 4px;';
                                el.innerHTML = `
                                    <div style="font-weight: 600; color: var(--accent-indigo); margin-bottom: 2px;">${notif.created_at}</div>
                                    <div>${notif.message}</div>
                                `;
                                adminNotificationsListContainer.appendChild(el);
                            });
                        } else {
                            adminNotificationsListContainer.innerHTML = '<span style="font-size: 10px; color: var(--text-muted);">No unread notifications.</span>';
                        }
                    }
                } catch (e) {
                    console.error("Failed to load notifications feed:", e);
                    adminNotificationsListContainer.innerHTML = '<span style="font-size: 9px; color: var(--color-knife);">Error loading notifications feed.</span>';
                }
            }

            refreshAdminNotifications();
            setInterval(refreshAdminNotifications, 10000);

            if (btnClearNotifications) {
                btnClearNotifications.addEventListener('click', async () => {
                    try {
                        const res = await fetch('/api/admin/notifications/clear/', { method: 'POST' });
                        if (res.ok) {
                            refreshAdminNotifications();
                        }
                    } catch (e) {
                        console.error("Failed to clear notifications:", e);
                    }
                });
            }
        }

        const adminPendingPaymentsContainer = document.getElementById('admin-pending-payments-list');
        if (adminPendingPaymentsContainer) {
            async function refreshAdminPendingPayments() {
                try {
                    const response = await fetch('/api/admin/payments/pending/');
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    const result = await response.json();
                    if (result.status === 'success') {
                        adminPendingPaymentsContainer.innerHTML = '';
                        if (result.payments && result.payments.length > 0) {
                            result.payments.forEach(pay => {
                                const el = document.createElement('div');
                                el.style.cssText = 'background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 8px; border-radius: 6px; font-size: 10px; color: var(--text-secondary); line-height: 1.4; margin-bottom: 6px;';
                                el.innerHTML = `
                                    <div style="display: flex; justify-content: space-between; font-weight: 600; color: var(--text-primary); margin-bottom: 2px;">
                                        <span>@${pay.username}</span>
                                        <span style="text-transform: uppercase; color: #60a5fa;">${pay.plan}</span>
                                    </div>
                                    <div>Amt: ₹${pay.amount}</div>
                                    <div>UTR: <strong style="color: var(--text-primary);">${pay.utr}</strong></div>
                                    <div>UPI: ${pay.upi_id}</div>
                                    <div style="display: flex; gap: 6px; margin-top: 6px;">
                                        <button class="approve-pay-btn primary-btn" data-id="${pay.id}" style="font-size: 9px; padding: 2px 8px; margin: 0; background: #10b981; border: none; cursor: pointer; color: #fff; border-radius: 4px; font-weight: 600;">Approve</button>
                                        <button class="reject-pay-btn primary-btn" data-id="${pay.id}" style="font-size: 9px; padding: 2px 8px; margin: 0; background: #ef4444; border: none; cursor: pointer; color: #fff; border-radius: 4px; font-weight: 600;">Reject</button>
                                    </div>
                                `;
                                adminPendingPaymentsContainer.appendChild(el);
                            });

                            // Attach click listeners to Approve buttons
                            adminPendingPaymentsContainer.querySelectorAll('.approve-pay-btn').forEach(btn => {
                                btn.addEventListener('click', async () => {
                                    const payId = btn.getAttribute('data-id');
                                    if (confirm('Verify payment and approve upgrade?')) {
                                        btn.disabled = true;
                                        btn.innerText = 'Approving...';
                                        try {
                                            const res = await fetch('/api/admin/payments/verify/', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ payment_id: payId, action: 'approve' })
                                            });
                                            if (res.ok) {
                                                alert('Payment request approved.');
                                                refreshAdminPendingPayments();
                                                if (typeof refreshAdminUserList === 'function') refreshAdminUserList();
                                            } else {
                                                const err = await res.json();
                                                alert('Failed: ' + err.message);
                                            }
                                        } catch (e) {
                                            alert('Error: ' + e.message);
                                        } finally {
                                            btn.disabled = false;
                                            btn.innerText = 'Approve';
                                        }
                                    }
                                });
                            });

                            // Attach click listeners to Reject buttons
                            adminPendingPaymentsContainer.querySelectorAll('.reject-pay-btn').forEach(btn => {
                                btn.addEventListener('click', async () => {
                                    const payId = btn.getAttribute('data-id');
                                    if (confirm('Reject payment request?')) {
                                        btn.disabled = true;
                                        btn.innerText = 'Rejecting...';
                                        try {
                                            const res = await fetch('/api/admin/payments/verify/', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ payment_id: payId, action: 'reject' })
                                            });
                                            if (res.ok) {
                                                alert('Payment request rejected.');
                                                refreshAdminPendingPayments();
                                            } else {
                                                const err = await res.json();
                                                alert('Failed: ' + err.message);
                                            }
                                        } catch (e) {
                                            alert('Error: ' + e.message);
                                        } finally {
                                            btn.disabled = false;
                                            btn.innerText = 'Reject';
                                        }
                                    }
                                });
                            });
                        } else {
                            adminPendingPaymentsContainer.innerHTML = '<span style="font-size: 10px; color: var(--text-muted);">No pending approvals.</span>';
                        }
                    }
                } catch (e) {
                    console.error("Failed to load pending payments:", e);
                    adminPendingPaymentsContainer.innerHTML = '<span style="font-size: 9px; color: var(--color-knife);">Error loading pending approvals.</span>';
                }
            }

            refreshAdminPendingPayments();
            setInterval(refreshAdminPendingPayments, 10000);
        }

        // Close Detail Drawer Bindings
        document.getElementById('btn-close-detail').addEventListener('click', closeDetailDrawer);
        document.getElementById('detail-overlay').addEventListener('click', closeDetailDrawer);

        // Info Guide Modal Bindings
        const guideModal = document.getElementById('guide-modal');
        document.getElementById('btn-open-guide').addEventListener('click', () => {
            guideModal.classList.remove('hidden');
        });
        document.getElementById('btn-close-guide').addEventListener('click', () => {
            guideModal.classList.add('hidden');
        });
        guideModal.addEventListener('click', (e) => {
            if (e.target === guideModal) {
                guideModal.classList.add('hidden');
            }
        });

        // User Notifications Dismiss Bindings
        const clearNotifBtns = document.querySelectorAll('.clear-user-notif-btn');
        clearNotifBtns.forEach(btn => {
            btn.addEventListener('click', async () => {
                const banner = btn.closest('.user-alert-banner');
                try {
                    const res = await fetch('/api/notifications/clear/', { method: 'POST' });
                    if (res.ok) {
                        banner.remove();
                        const container = document.querySelector('.user-alerts-block');
                        if (container && container.querySelectorAll('.user-alert-banner').length === 0) {
                            container.remove();
                        }
                    }
                } catch (e) {
                    console.error("Failed to clear notification:", e);
                }
            });
        });

        // Tab switching binds
        const tabScreener = document.getElementById('btn-tab-screener');
        const tabBacktest = document.getElementById('btn-tab-backtest');
        const tabJournal = document.getElementById('btn-tab-journal');
        const tabAdvanced = document.getElementById('btn-tab-advanced');
        const tabAdminStats = document.getElementById('btn-tab-admin-stats');
        
        const screenerStats = document.getElementById('screener-stats-bar');
        const screenerGrid = document.getElementById('main-screener-grid');
        const backtestViewCard = document.getElementById('backtest-view-card');
        const journalViewCard = document.getElementById('journal-view-card');
        const advancedViewCard = document.getElementById('advanced-strategy-view-card');
        const adminStatsViewCard = document.getElementById('admin-stats-view-card');
        const useCasesSection = document.querySelector('.use-cases-section');
        
        function deactivateAllTabs() {
            document.body.classList.remove('fullscreen-grid-active');
            document.body.classList.remove('fullscreen-advanced-active');
            document.body.classList.remove('fullscreen-stats-active');
            const iconGrid = document.querySelector('#btn-fullscreen-grid i');
            if (iconGrid) iconGrid.className = 'fa-solid fa-expand';
            const btnGrid = document.getElementById('btn-fullscreen-grid');
            if (btnGrid) btnGrid.title = 'Toggle Fullscreen Grid';

            const iconAdv = document.querySelector('#btn-fullscreen-advanced i');
            if (iconAdv) iconAdv.className = 'fa-solid fa-expand';
            const btnAdv = document.getElementById('btn-fullscreen-advanced');
            if (btnAdv) btnAdv.title = 'Toggle Fullscreen Grid';

            const iconStats = document.querySelector('#btn-fullscreen-stats i');
            if (iconStats) iconStats.className = 'fa-solid fa-expand';
            const btnStatsFs = document.getElementById('btn-fullscreen-stats');
            if (btnStatsFs) btnStatsFs.title = 'Toggle Fullscreen Table';

            [tabScreener, tabBacktest, tabJournal, tabAdvanced, tabAdminStats].forEach(tab => {
                if (tab) {
                    tab.classList.remove('active');
                    tab.style.background = 'transparent';
                    tab.style.color = 'var(--text-secondary)';
                }
            });
            screenerStats.classList.add('hidden');
            screenerGrid.classList.add('hidden');
            backtestViewCard.classList.add('hidden');
            journalViewCard.classList.add('hidden');
            if (advancedViewCard) advancedViewCard.classList.add('hidden');
            if (adminStatsViewCard) adminStatsViewCard.classList.add('hidden');
            if (useCasesSection) useCasesSection.classList.add('hidden');
        }

        tabScreener.addEventListener('click', () => {
            deactivateAllTabs();
            tabScreener.classList.add('active');
            tabScreener.style.background = 'rgba(255,255,255,0.05)';
            tabScreener.style.color = 'var(--text-primary)';
            
            screenerStats.classList.remove('hidden');
            screenerGrid.classList.remove('hidden');
            if (useCasesSection) useCasesSection.classList.remove('hidden');
        });
        
        tabBacktest.addEventListener('click', () => {
            if (USER_STATUS === 'expired') {
                document.getElementById('trial-expired-overlay').classList.remove('hidden');
                return;
            }
            deactivateAllTabs();
            tabBacktest.classList.add('active');
            tabBacktest.style.background = 'rgba(255,255,255,0.05)';
            tabBacktest.style.color = 'var(--text-primary)';
            
            backtestViewCard.classList.remove('hidden');
            renderBacktestDashboard();
        });

        tabJournal.addEventListener('click', () => {
            if (USER_STATUS === 'expired') {
                document.getElementById('trial-expired-overlay').classList.remove('hidden');
                return;
            }
            deactivateAllTabs();
            tabJournal.classList.add('active');
            tabJournal.style.background = 'rgba(255,255,255,0.05)';
            tabJournal.style.color = 'var(--text-primary)';
            
            journalViewCard.classList.remove('hidden');
            renderJournalDashboard();
        });

        if (tabAdvanced) {
            tabAdvanced.addEventListener('click', () => {
                console.log("Advanced Strategy Tab Clicked!");
                // Check Pro Analyst permission
                const isProUser = (PLAN_TIER === 'pro' || USER_STATUS === 'premium' || USER_STATUS === 'pro' || IS_SUPERUSER === true);
                console.log("isProUser authorization check:", { PLAN_TIER, USER_STATUS, IS_SUPERUSER, isProUser });
                
                if (!isProUser) {
                    console.log("User is unauthorized. Displaying locking overlay.");
                    document.getElementById('pro-only-overlay').classList.remove('hidden');
                    return;
                }
                
                console.log("User is authorized. Transitioning layout.");
                deactivateAllTabs();
                tabAdvanced.classList.add('active');
                tabAdvanced.style.background = 'rgba(255,255,255,0.05)';
                tabAdvanced.style.color = 'var(--text-primary)';
                
                if (advancedViewCard) {
                    advancedViewCard.classList.remove('hidden');
                }
                renderAdvancedStrategyDashboard();
            });
        }

        if (tabAdminStats) {
            tabAdminStats.addEventListener('click', () => {
                deactivateAllTabs();
                tabAdminStats.classList.add('active');
                tabAdminStats.style.background = 'rgba(255,255,255,0.05)';
                tabAdminStats.style.color = 'var(--text-primary)';
                
                if (adminStatsViewCard) {
                    adminStatsViewCard.classList.remove('hidden');
                }
                renderAdminStatsDashboard();
            });
        }

        const btnSidebarAdminStats = document.getElementById('btn-sidebar-admin-stats');
        if (btnSidebarAdminStats) {
            btnSidebarAdminStats.addEventListener('click', () => {
                if (tabAdminStats) {
                    tabAdminStats.click();
                }
            });
        }

        // Screener Statistics Page Filter & Export Bindings
        const selStatsUniverse = document.getElementById('sel-stats-universe');
        const selStatsStatus = document.getElementById('sel-stats-status');
        const selStatsMomentum = document.getElementById('sel-stats-momentum');
        const txtStatsSearch = document.getElementById('txt-stats-search');
        const btnExportCsv = document.getElementById('btn-export-stats-csv');
        const btnExportJson = document.getElementById('btn-export-stats-json');

        if (selStatsUniverse) selStatsUniverse.addEventListener('change', renderAdminStatsDashboard);
        if (selStatsStatus) selStatsStatus.addEventListener('change', renderAdminStatsDashboard);
        if (selStatsMomentum) selStatsMomentum.addEventListener('change', renderAdminStatsDashboard);
        if (txtStatsSearch) txtStatsSearch.addEventListener('input', renderAdminStatsDashboard);
        if (btnExportCsv) btnExportCsv.addEventListener('click', exportScreenerDataCSV);
        if (btnExportJson) btnExportJson.addEventListener('click', exportScreenerDataJSON);

        const btnStatsScrollLeft = document.getElementById('btn-stats-scroll-left');
        const btnStatsScrollRight = document.getElementById('btn-stats-scroll-right');
        const statsTableContainer = document.getElementById('admin-stats-table-container');

        if (btnStatsScrollLeft && statsTableContainer) {
            btnStatsScrollLeft.addEventListener('click', () => {
                statsTableContainer.scrollBy({ left: -320, behavior: 'smooth' });
            });
        }
        if (btnStatsScrollRight && statsTableContainer) {
            btnStatsScrollRight.addEventListener('click', () => {
                statsTableContainer.scrollBy({ left: 320, behavior: 'smooth' });
            });
        }

        const btnFullscreenStats = document.getElementById('btn-fullscreen-stats');
        if (btnFullscreenStats) {
            btnFullscreenStats.addEventListener('click', () => {
                document.body.classList.toggle('fullscreen-stats-active');
                const icon = btnFullscreenStats.querySelector('i');
                if (document.body.classList.contains('fullscreen-stats-active')) {
                    if (icon) icon.className = 'fa-solid fa-compress';
                    btnFullscreenStats.title = 'Exit Fullscreen';
                } else {
                    if (icon) icon.className = 'fa-solid fa-expand';
                    btnFullscreenStats.title = 'Toggle Fullscreen Table';
                }
            });
        }

        document.querySelectorAll('#admin-stats-table th.stats-th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const field = th.getAttribute('data-sort');
                if (adminStatsSortField === field) {
                    adminStatsSortDirection = adminStatsSortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    adminStatsSortField = field;
                    adminStatsSortDirection = (field === 'price' || field === 'drawdown' || field === 'rsi' || field === 'adx' || field === 'pctChange' || field === 'pctChange7d') ? 'desc' : 'asc';
                }
                renderAdminStatsDashboard();
            });
        });

        const btnFullscreenAdvanced = document.getElementById('btn-fullscreen-advanced');
        if (btnFullscreenAdvanced) {
            btnFullscreenAdvanced.addEventListener('click', () => {
                document.body.classList.toggle('fullscreen-advanced-active');
                const icon = btnFullscreenAdvanced.querySelector('i');
                if (document.body.classList.contains('fullscreen-advanced-active')) {
                    if (icon) icon.className = 'fa-solid fa-compress';
                    btnFullscreenAdvanced.title = 'Exit Fullscreen';
                } else {
                    if (icon) icon.className = 'fa-solid fa-expand';
                    btnFullscreenAdvanced.title = 'Toggle Fullscreen Grid';
                }
            });
        }

        const proOverlayDismiss = document.getElementById('btn-pro-overlay-dismiss');
        if (proOverlayDismiss) {
            proOverlayDismiss.addEventListener('click', () => {
                document.getElementById('pro-only-overlay').classList.add('hidden');
                tabScreener.click(); // Switch back to screener grid
            });
        }

        // Global function for tooltip toggles
        window.toggleAdvancedTooltip = function(id) {
            const block = document.getElementById(id);
            if (block) {
                block.classList.toggle('hidden');
            }
        };

        async function renderAdvancedStrategyDashboard() {
            const absBody = document.getElementById('abs-ranking-table-body');
            const bearBody = document.getElementById('bearish-exh-table-body');
            const bullBody = document.getElementById('bullish-exh-table-body');
            const vcpBody = document.getElementById('vcp-ranking-table-body');

            // Set loading indicators
            [absBody, bearBody, bullBody, vcpBody].forEach(body => {
                if (body) {
                    body.innerHTML = `<tr><td colspan="10" style="padding: 20px; text-align: center; color: var(--text-secondary);"><i class="fa-solid fa-spinner fa-spin"></i> Running quant calculations...</td></tr>`;
                }
            });

            try {
                const response = await fetch('/api/advanced-strategy/');
                if (!response.ok) {
                    throw new Error(await response.text() || 'Failed to fetch advanced strategy rankings');
                }
                const data = await response.json();
                
                // Update dates
                document.getElementById('abs-evaluation-date-label').innerText = `Evaluating on: ${data.evaluation_date} (Benchmark down-day: ${data.absorption_date}, Nifty Return: ${data.market_ret_abs}%)`;
                document.getElementById('vcp-evaluation-date-label').innerText = `Evaluating on: ${data.evaluation_date}`;

                // Render Institutional Absorption
                if (absBody) {
                    if (data.absorption && data.absorption.length > 0) {
                        absBody.innerHTML = data.absorption.map((item, idx) => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03); hover: background: rgba(255,255,255,0.01);">
                                <td style="padding: 10px; font-weight: 600; color: var(--text-primary);">${item.symbol}</td>
                                <td style="padding: 10px; color: var(--text-secondary);">₹${item.price.toFixed(2)}</td>
                                <td style="padding: 10px; text-align: right; color: #10b981; font-weight: 600;">+${item.return}%</td>
                                <td style="padding: 10px; text-align: right; color: var(--text-secondary);">${item.residual > 0 ? '+' : ''}${item.residual}%</td>
                                <td style="padding: 10px; text-align: right; color: var(--text-secondary);">${item.vol_ratio}x</td>
                                <td style="padding: 10px; text-align: right; color: var(--text-secondary);">${item.clv}</td>
                                <td style="padding: 10px; text-align: right; color: #a855f7; font-weight: 700; font-size: 13px;">${item.score.toFixed(4)}</td>
                            </tr>
                        `).join('');
                    } else {
                        absBody.innerHTML = `<tr><td colspan="7" style="padding: 20px; text-align: center; color: var(--text-secondary);">No absorption setups detected.</td></tr>`;
                    }
                }

                // Render Bearish Capitulation
                if (bearBody) {
                    if (data.bearish_exhaustion && data.bearish_exhaustion.length > 0) {
                        bearBody.innerHTML = data.bearish_exhaustion.map(item => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                                <td style="padding: 8px; color: var(--text-secondary); font-size: 11px;">${item.date}</td>
                                <td style="padding: 8px; font-weight: 600; color: var(--text-primary);">${item.symbol}</td>
                                <td style="padding: 8px; text-align: right; color: var(--text-secondary);">₹${item.price.toFixed(2)}</td>
                                <td style="padding: 8px; text-align: right; color: var(--text-secondary);">${item.vol_z}</td>
                                <td style="padding: 8px; text-align: right; color: var(--text-secondary);">${item.spread_z}</td>
                                <td style="padding: 8px; text-align: right; color: #10b981; font-weight: 700;">${item.score.toFixed(2)}</td>
                            </tr>
                        `).join('');
                    } else {
                        bearBody.innerHTML = `<tr><td colspan="6" style="padding: 15px; text-align: center; color: var(--text-secondary);">No Bearish Capitulations found in the last 5 days.</td></tr>`;
                    }
                }

                // Render Bullish Capitulation
                if (bullBody) {
                    if (data.bullish_exhaustion && data.bullish_exhaustion.length > 0) {
                        bullBody.innerHTML = data.bullish_exhaustion.map(item => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                                <td style="padding: 8px; color: var(--text-secondary); font-size: 11px;">${item.date}</td>
                                <td style="padding: 8px; font-weight: 600; color: var(--text-primary);">${item.symbol}</td>
                                <td style="padding: 8px; text-align: right; color: var(--text-secondary);">₹${item.price.toFixed(2)}</td>
                                <td style="padding: 8px; text-align: right; color: var(--text-secondary);">${item.vol_z}</td>
                                <td style="padding: 8px; text-align: right; color: var(--text-secondary);">${item.spread_z}</td>
                                <td style="padding: 8px; text-align: right; color: #f87171; font-weight: 700;">${item.score.toFixed(2)}</td>
                            </tr>
                        `).join('');
                    } else {
                        bullBody.innerHTML = `<tr><td colspan="6" style="padding: 15px; text-align: center; color: var(--text-secondary);">No Bullish Capitulations found in the last 5 days.</td></tr>`;
                    }
                }

                // Render VCP
                if (vcpBody) {
                    if (data.vcp && data.vcp.length > 0) {
                        vcpBody.innerHTML = data.vcp.map(item => `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.03);">
                                <td style="padding: 10px; font-weight: 600; color: var(--text-primary);">${item.symbol}</td>
                                <td style="padding: 10px; color: var(--text-secondary);">₹${item.price.toFixed(2)}</td>
                                <td style="padding: 10px; text-align: right; color: var(--text-secondary);">${item.dist_from_high}%</td>
                                <td style="padding: 10px; text-align: right; color: var(--text-secondary);">${item.vol_comp}%</td>
                                <td style="padding: 10px; text-align: right; color: var(--text-secondary);">${item.volu_cont}%</td>
                                <td style="padding: 10px; text-align: right; color: #6366f1; font-weight: 700; font-size: 13px;">${item.score.toFixed(4)}</td>
                            </tr>
                        `).join('');
                    } else {
                        vcpBody.innerHTML = `<tr><td colspan="6" style="padding: 20px; text-align: center; color: var(--text-secondary);">No Volatility Contractions found near highs.</td></tr>`;
                    }
                }

            } catch (err) {
                console.error(err);
                [absBody, bearBody, bullBody, vcpBody].forEach(body => {
                    if (body) {
                        body.innerHTML = `<tr><td colspan="10" style="padding: 20px; text-align: center; color: #f87171;"><i class="fa-solid fa-circle-exclamation"></i> Error: ${err.message}</td></tr>`;
                    }
                });
            }
        }
        
        // Signal category selector change
        document.getElementById('sel-signal-category').addEventListener('change', () => {
            renderBacktestDashboard();
        });

        // Backtest lookback period selector change
        const backtestPeriodSelect = document.getElementById('sel-backtest-period');
        if (backtestPeriodSelect) {
            backtestPeriodSelect.addEventListener('change', () => {
                renderBacktestDashboard();
            });
        }

        // Trade Log Modal Bindings
        const tradelogModal = document.getElementById('tradelog-modal');
        document.getElementById('btn-close-tradelog').addEventListener('click', () => {
            tradelogModal.classList.add('hidden');
        });
        tradelogModal.addEventListener('click', (e) => {
            if (e.target === tradelogModal) {
                tradelogModal.classList.add('hidden');
            }
        });

        // Journal Entry Form Bindings
        document.getElementById('btn-save-journal-entry').addEventListener('click', () => {
            if (USER_STATUS === 'expired') {
                document.getElementById('trial-expired-overlay').classList.remove('hidden');
                return;
            }
            if (state.activeTicker) {
                saveJournalEntry(state.activeTicker);
            }
        });

        // Journal Clear Bindings
        document.getElementById('btn-clear-journal').addEventListener('click', () => {
            if (USER_STATUS === 'expired') {
                document.getElementById('trial-expired-overlay').classList.remove('hidden');
                return;
            }
            if (confirm('Are you sure you want to clear your trade journal? This will delete all entries permanently.')) {
                if (USER_STATUS === 'guest') {
                    state.journal = [];
                    localStorage.setItem('trade_journal', JSON.stringify([]));
                    renderJournalDashboard();
                } else {
                    fetch('/api/journal/clear/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        }
                    })
                    .then(res => res.json())
                    .then(res => {
                        if (res.status === 'success') {
                            syncJournalWithBackend();
                        } else {
                            alert(`Failed to clear journal: ${res.message}`);
                        }
                    })
                    .catch(err => {
                        console.error('Error clearing journal in DB', err);
                        alert('Error connecting to backend database.');
                    });
                }
            }
        });

        // Trial Expired Overlay Dismiss Bindings
        const expiredOverlay = document.getElementById('trial-expired-overlay');
        const btnExpiredDismiss = document.getElementById('btn-expired-dismiss');
        if (btnExpiredDismiss) {
            btnExpiredDismiss.addEventListener('click', () => {
                expiredOverlay.classList.add('hidden');
                tabScreener.click(); // Switch back to screener tab
            });
        }

        // Table Sorting Header Bindings
        document.querySelectorAll('#screener-table th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const field = th.getAttribute('data-sort');
                if (state.sort.field === field) {
                    // Toggle direction
                    state.sort.direction = state.sort.direction === 'asc' ? 'desc' : 'asc';
                } else {
                    // Set new sort field and default to asc
                    state.sort.field = field;
                    state.sort.direction = 'asc';
                }
                renderScreenerGrid();
            });
        });

        // Theme Toggle Bindings
        const themeToggle = document.getElementById('btn-theme-toggle');
        if (themeToggle) {
            function updateToggleIcon() {
                const isLight = document.body.classList.contains('light-theme');
                themeToggle.innerHTML = isLight ? '<i class="fa-solid fa-moon"></i>' : '<i class="fa-solid fa-sun"></i>';
            }
            // Set initial state
            updateToggleIcon();

            themeToggle.addEventListener('click', () => {
                const activeTheme = document.body.classList.contains('light-theme') ? 'dark' : 'light';
                localStorage.setItem('theme', activeTheme);
                if (activeTheme === 'light') {
                    document.body.classList.add('light-theme');
                } else {
                    document.body.classList.remove('light-theme');
                }
                updateToggleIcon();

                // Redraw active charts to reflect new theme styling gridline/label colors!
                if (state.activeTicker && state.stocks[state.activeTicker]) {
                    renderCharts(state.stocks[state.activeTicker]);
                }
            });
        }

        // Close Trade Modal Bindings
        const closeTradeModal = document.getElementById('close-trade-modal');
        document.getElementById('btn-close-close-trade').addEventListener('click', () => {
            closeTradeModal.classList.add('hidden');
        });
        closeTradeModal.addEventListener('click', (e) => {
            if (e.target === closeTradeModal) {
                closeTradeModal.classList.add('hidden');
            }
        });
        document.getElementById('btn-submit-close-trade').addEventListener('click', submitCloseTrade);

        // Journal Period Filters
        const jBtnAll = document.getElementById('btn-journal-filter-all');
        const jBtnYear = document.getElementById('btn-journal-filter-year');
        const jBtnMonth = document.getElementById('btn-journal-filter-month');
        const jBtnDay = document.getElementById('btn-journal-filter-day');

        function deactivateJournalFilters() {
            [jBtnAll, jBtnYear, jBtnMonth, jBtnDay].forEach(btn => {
                if (btn) {
                    btn.classList.remove('active');
                    btn.style.background = 'transparent';
                    btn.style.color = 'var(--text-secondary)';
                }
            });
        }

        if (jBtnAll) {
            jBtnAll.addEventListener('click', () => {
                deactivateJournalFilters();
                jBtnAll.classList.add('active');
                jBtnAll.style.background = 'rgba(255, 255, 255, 0.08)';
                jBtnAll.style.color = 'var(--text-primary)';
                state.journalFilter = 'all';
                document.getElementById('journal-filter-desc').innerText = 'Showing metrics for all time';
                renderJournalDashboard();
            });
        }

        if (jBtnYear) {
            jBtnYear.addEventListener('click', () => {
                deactivateJournalFilters();
                jBtnYear.classList.add('active');
                jBtnYear.style.background = 'rgba(255, 255, 255, 0.08)';
                jBtnYear.style.color = 'var(--text-primary)';
                state.journalFilter = 'yearly';
                document.getElementById('journal-filter-desc').innerText = 'Showing metrics for past year';
                renderJournalDashboard();
            });
        }

        if (jBtnMonth) {
            jBtnMonth.addEventListener('click', () => {
                deactivateJournalFilters();
                jBtnMonth.classList.add('active');
                jBtnMonth.style.background = 'rgba(255, 255, 255, 0.08)';
                jBtnMonth.style.color = 'var(--text-primary)';
                state.journalFilter = 'monthly';
                document.getElementById('journal-filter-desc').innerText = 'Showing metrics for past month';
                renderJournalDashboard();
            });
        }

        if (jBtnDay) {
            jBtnDay.addEventListener('click', () => {
                deactivateJournalFilters();
                jBtnDay.classList.add('active');
                jBtnDay.style.background = 'rgba(255, 255, 255, 0.08)';
                jBtnDay.style.color = 'var(--text-primary)';
                state.journalFilter = 'daily';
                document.getElementById('journal-filter-desc').innerText = 'Showing metrics for past 24 hours';
                renderJournalDashboard();
            });
        }
    }

    // --- Strategy Backtesting & Signals Engine ---

    function runRSIBacktestJS(candles) {
        if (!candles || candles.length < 30) {
            return { totalTrades: 0, winRate: 0, avgWin: 0, avgLoss: 0, expectancy: 0, signals: [] };
        }
        
        const prices = candles.map(c => c.close);
        const opens = candles.map(c => c.open);
        const rsi = calculateRSI(prices, 14);
        
        let inTrade = false;
        let buyPrice = 0;
        let buyDate = "";
        let trades = [];
        let tradesLog = [];
        let signals = [];
        
        const n = candles.length;
        
        for (let i = 15; i < n - 1; i++) {
            // Entry signal: RSI crossed 30 from below (rsi[i-1] < 30 and rsi[i] >= 30)
            if (!inTrade && rsi[i-1] !== null && rsi[i] !== null) {
                if (rsi[i-1] < 30 && rsi[i] >= 30) {
                    buyPrice = opens[i+1];
                    buyDate = candles[i+1].date;
                    inTrade = true;
                    continue;
                }
            }
            
            // Exit signal: RSI reaches or exceeds 70
            if (inTrade && rsi[i] !== null) {
                if (rsi[i] >= 70) {
                    const sellPrice = opens[i+1];
                    const sellDate = candles[i+1].date;
                    const pnl = ((sellPrice - buyPrice) / buyPrice) * 100;
                    trades.push(pnl);
                    tradesLog.push({
                        direction: 'Long',
                        entryDate: buyDate,
                        entryPrice: buyPrice,
                        exitDate: sellDate,
                        exitPrice: sellPrice,
                        pnl: pnl,
                        isForceClosed: false
                    });
                    inTrade = false;
                }
            }
        }

        // Force close open trade at the end of history to ensure correct loss metrics
        if (inTrade) {
            const sellPrice = prices[n - 1];
            const sellDate = candles[n - 1].date;
            const pnl = ((sellPrice - buyPrice) / buyPrice) * 100;
            trades.push(pnl);
            tradesLog.push({
                direction: 'Long',
                entryDate: buyDate,
                entryPrice: buyPrice,
                exitDate: sellDate,
                exitPrice: sellPrice,
                pnl: pnl,
                isForceClosed: true
            });
            inTrade = false;
        }
        
        // Scan last 14 trading days for active signals (expanded from 5 to find crossovers)
        for (let i = n - 14; i < n; i++) {
            if (i <= 15) continue;
            const prevRsi = rsi[i-1];
            const currRsi = rsi[i];
            
            if (prevRsi !== null && currRsi !== null) {
                // Buy Crossover: crosses above 30 from below
                if (prevRsi < 30 && currRsi >= 30) {
                    signals.push({
                        type: 'Buy',
                        date: candles[i].date,
                        price: candles[i].close,
                        description: `RSI crossed above 30 from below (${prevRsi.toFixed(1)} -> ${currRsi.toFixed(1)})`
                    });
                }
                // Sell Crossovers: reaches/crosses above 70, or crosses back below 70
                if (prevRsi < 70 && currRsi >= 70) {
                    signals.push({
                        type: 'Sell',
                        date: candles[i].date,
                        price: candles[i].close,
                        description: `RSI reached/exceeded 70 (${prevRsi.toFixed(1)} -> ${currRsi.toFixed(1)})`
                    });
                } else if (prevRsi >= 70 && currRsi < 70) {
                    signals.push({
                        type: 'Sell',
                        date: candles[i].date,
                        price: candles[i].close,
                        description: `RSI crossed below 70 showing momentum fade (${prevRsi.toFixed(1)} -> ${currRsi.toFixed(1)})`
                    });
                }
            }
        }
        
        // Fallback: If no crossovers occurred in the last 14 days, check current absolute oversold/overbought states
        if (signals.length === 0 && n > 0) {
            const latestRsi = rsi[n - 1];
            if (latestRsi !== null) {
                if (latestRsi <= 35) {
                    signals.push({
                        type: 'Buy',
                        date: candles[n - 1].date,
                        price: candles[n - 1].close,
                        description: `Oversold zone setup (Current RSI is ${latestRsi.toFixed(1)} <= 35)`
                    });
                } else if (latestRsi >= 65) {
                    signals.push({
                        type: 'Sell',
                        date: candles[n - 1].date,
                        price: candles[n - 1].close,
                        description: `Overbought zone setup (Current RSI is ${latestRsi.toFixed(1)} >= 65)`
                    });
                }
            }
        }
        
        const totalTrades = trades.length;
        if (totalTrades === 0) {
            return { totalTrades: 0, winRate: 0, avgWin: 0, avgLoss: 0, expectancy: 0, signals, tradesLog };
        }
        
        const wins = trades.filter(p => p > 0);
        const losses = trades.filter(p => p <= 0);
        
        const winRate = (wins.length / totalTrades) * 100;
        const avgWin = wins.length > 0 ? (wins.reduce((a, b) => a + b, 0) / wins.length) : 0;
        const avgLoss = losses.length > 0 ? (losses.reduce((a, b) => a + b, 0) / losses.length) : 0;
        const expectancy = trades.reduce((a, b) => a + b, 0) / totalTrades;
        
        return {
            totalTrades,
            winRate: Math.round(winRate * 100) / 100,
            avgWin: Math.round(avgWin * 100) / 100,
            avgLoss: Math.round(avgLoss * 100) / 100,
            expectancy: Math.round(expectancy * 100) / 100,
            signals,
            tradesLog
        };
    }

    function renderBacktestDashboard() {
        const backtestTbody = document.getElementById('backtest-tbody');
        const signalsTbody = document.getElementById('signals-tbody');
        const signalFilter = document.getElementById('sel-signal-category').value;
        
        backtestTbody.innerHTML = '';
        signalsTbody.innerHTML = '';
        
        const query = document.getElementById('grid-search') ? document.getElementById('grid-search').value.toLowerCase() : '';
        const filterStatusSelect = document.getElementById('sel-filter-status');
        const filterStatus = filterStatusSelect ? filterStatusSelect.value : 'all';
        const filterPerfSelect = document.getElementById('sel-filter-performance');
        const filterPerf = filterPerfSelect ? filterPerfSelect.value : 'all';

        const filteredStocksList = Object.values(state.stocks).filter(stock => {
            const matchesSearch = stock.ticker.toLowerCase().includes(query) || 
                                  stock.name.toLowerCase().includes(query);
            const matchesStatus = filterStatus === 'all' || 
                                  (filterStatus === 'safe' && stock.status === 'Safe') || 
                                  (filterStatus === 'knife' && stock.status === 'Knife');
            const matchesPerf = filterPerf === 'all' || 
                                (filterPerf === 'momentum-shift' && stock.current.hasMomentumShift) ||
                                (filterPerf === '1d-winners' && stock.current.pctChange > 0) || 
                                (filterPerf === '1d-losers' && stock.current.pctChange < 0) || 
                                (filterPerf === '7d-winners' && stock.current.pctChange7d > 0) || 
                                (filterPerf === '7d-losers' && stock.current.pctChange7d < 0);
            return matchesSearch && matchesStatus && matchesPerf;
        });

        if (filteredStocksList.length === 0) {
            backtestTbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); font-size: 13px; padding: 20px;">No stocks match active filters. Run Nifty 50 or F&O scan or adjust filters.</td></tr>`;
            signalsTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); font-size: 13px; padding: 20px;">No recent signals matching filters.</td></tr>`;
            return;
        }
        
        const backtestPeriodSelect = document.getElementById('sel-backtest-period');
        const backtestYears = backtestPeriodSelect ? parseInt(backtestPeriodSelect.value) : 1;
        const lookbackDays = backtestYears * 250;

        const backtestResults = [];
        let allSignals = [];
        
        filteredStocksList.forEach(stock => {
            const candlesSlice = stock.candles.slice(-lookbackDays);
            const res = runRSIBacktestJS(candlesSlice);
            backtestResults.push({
                ticker: stock.ticker,
                name: stock.name,
                totalTrades: res.totalTrades,
                winRate: res.winRate,
                avgWin: res.avgWin,
                avgLoss: res.avgLoss,
                expectancy: res.expectancy,
                tradesLog: res.tradesLog
            });
            
            res.signals.forEach(sig => {
                allSignals.push({
                    ticker: stock.ticker,
                    type: sig.type,
                    price: sig.price,
                    date: sig.date,
                    description: sig.description
                });
            });
        });
        
        // Sort backtest results by winRate descending
        backtestResults.sort((a, b) => b.winRate - a.winRate);
        
        // Populate performance table
        backtestResults.forEach(r => {
            const tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            tr.title = 'Click to view detailed trade log';
            tr.innerHTML = `
                <td style="font-weight: 600; color: var(--accent-indigo);">${r.ticker}</td>
                <td>${r.name}</td>
                <td>${r.totalTrades}</td>
                <td style="font-weight: 600; color: ${r.winRate >= 50 ? 'var(--color-safe)' : 'var(--text-secondary)'};">${r.winRate}%</td>
                <td class="text-green">+${r.avgWin.toFixed(2)}%</td>
                <td class="text-red">${r.avgLoss.toFixed(2)}%</td>
                <td style="font-weight: 600; color: ${r.expectancy >= 0 ? 'var(--color-safe)' : 'var(--color-knife)'};">${r.expectancy >= 0 ? '+' : ''}${r.expectancy.toFixed(2)}%</td>
            `;
            tr.addEventListener('click', () => {
                showTradeLogModal(r.ticker, r.name, r.tradesLog);
            });
            backtestTbody.appendChild(tr);
        });
        
        // Filter signals based on shortlist dropdown category
        let filteredSignals = allSignals;
        if (signalFilter === 'buy') {
            filteredSignals = allSignals.filter(s => s.type === 'Buy');
        } else if (signalFilter === 'sell') {
            filteredSignals = allSignals.filter(s => s.type === 'Sell');
        }
        
        if (filteredSignals.length === 0) {
            signalsTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-secondary); font-size: 13px; padding: 20px;">No recent crossovers matching the "${signalFilter}" shortlist category.</td></tr>`;
        } else {
            filteredSignals.forEach(s => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="font-weight: 600; color: var(--accent-indigo); cursor: pointer;" onclick="App.triggerSelect('${s.ticker}')">${s.ticker}</td>
                    <td><span class="badge ${s.type === 'Buy' ? 'badge-green' : 'badge-red'}">${s.type.toUpperCase()}</span></td>
                    <td style="font-weight: 600;">₹${s.price.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
                    <td>${s.date}</td>
                    <td style="font-size: 12px; color: var(--text-secondary);">${s.description}</td>
                `;
                signalsTbody.appendChild(tr);
            });
        }
    }

    function showTradeLogModal(ticker, name, tradesLog) {
        const modal = document.getElementById('tradelog-modal');
        const title = document.getElementById('tradelog-title');
        const tbody = document.getElementById('tradelog-tbody');
        
        title.innerHTML = `<i class="fa-solid fa-list-check" style="color: var(--accent-indigo);"></i> Trade Log: ${ticker} (${name})`;
        tbody.innerHTML = '';
        
        if (!tradesLog || tradesLog.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-secondary); padding: 20px;">No trades executed for this stock.</td></tr>`;
        } else {
            tradesLog.forEach((t, idx) => {
                const tr = document.createElement('tr');
                const exitLabel = t.isForceClosed ? `<span style="color: var(--text-secondary); font-size: 11px;">${t.exitDate} (Force Close)</span>` : t.exitDate;
                tr.innerHTML = `
                    <td style="padding: 10px;">${idx + 1}</td>
                    <td style="padding: 10px;"><span class="badge badge-green">LONG</span></td>
                    <td style="padding: 10px;">${t.entryDate}</td>
                    <td style="padding: 10px; font-weight: 500;">₹${t.entryPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    <td style="padding: 10px;">${exitLabel}</td>
                    <td style="padding: 10px; font-weight: 500;">₹${t.exitPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    <td style="padding: 10px; font-weight: 600; color: ${t.pnl >= 0 ? 'var(--color-safe)' : 'var(--color-knife)'};">${t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}%</td>
                `;
                tbody.appendChild(tr);
            });
        }
        
        modal.classList.remove('hidden');
    }

    let closingTradeId = null;

    function setupJournalForm(stock) {
        const dateSelect = document.getElementById('journal-input-date');
        if (!dateSelect) return;
        
        dateSelect.innerHTML = '';
        
        const recentCandles = stock.candles.slice(-30).reverse();
        recentCandles.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.date;
            opt.text = c.date;
            dateSelect.appendChild(opt);
        });
        
        const latestCandle = stock.candles[stock.candles.length - 1];
        document.getElementById('journal-input-price').value = latestCandle.close.toFixed(2);
        document.getElementById('journal-input-qty').value = '10';
        document.getElementById('journal-input-reason').value = '';
        document.getElementById('journal-input-type').value = 'Long';
        
        // Auto SL Calculator
        function calculateSL() {
            const type = document.getElementById('journal-input-type').value;
            const price = parseFloat(document.getElementById('journal-input-price').value);
            if (!isNaN(price) && price > 0) {
                const sl = type === 'Long' ? (price * 0.95) : (price * 1.05);
                document.getElementById('journal-input-sl').value = sl.toFixed(2);
            }
        }
        
        // Run once initially
        calculateSL();
        
        // Update price and SL on date selection change
        dateSelect.onchange = () => {
            const selectedDate = dateSelect.value;
            const candle = stock.candles.find(c => c.date === selectedDate);
            if (candle) {
                document.getElementById('journal-input-price').value = candle.close.toFixed(2);
                calculateSL();
            }
        };
        
        // Update SL on price or type changes
        document.getElementById('journal-input-price').oninput = calculateSL;
        document.getElementById('journal-input-type').onchange = calculateSL;
    }

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function syncJournalWithBackend() {
        if (USER_STATUS === 'guest') {
            renderJournalDashboard();
            return;
        }
        fetch('/api/journal/')
            .then(res => res.json())
            .then(res => {
                if (res.status === 'success') {
                    state.journal = res.data;
                    hydrateActiveJournalTickers();
                    renderJournalDashboard();
                }
            })
            .catch(err => console.error('Error syncing journal', err));
    }

    function saveJournalEntry(ticker) {
        if (USER_STATUS === 'expired') {
            alert('Your trial has expired. Please contact the administrator to extend your trial.');
            return;
        }

        const type = document.getElementById('journal-input-type').value;
        const entryDate = document.getElementById('journal-input-date').value;
        const entryPrice = parseFloat(document.getElementById('journal-input-price').value);
        const qty = parseInt(document.getElementById('journal-input-qty').value);
        const sl = parseFloat(document.getElementById('journal-input-sl').value);
        const entryReason = document.getElementById('journal-input-reason').value.trim();
        
        if (isNaN(entryPrice) || entryPrice <= 0) {
            alert('Please enter a valid entry price.');
            return;
        }
        
        if (isNaN(qty) || qty <= 0) {
            alert('Please enter a valid quantity.');
            return;
        }
        
        if (isNaN(sl) || sl <= 0) {
            alert('Please enter a valid stop loss price.');
            return;
        }
        
        const entry = {
            ticker: ticker,
            type: type,
            entryDate: entryDate,
            entryPrice: entryPrice,
            quantity: qty,
            stopLoss: sl,
            entryReason: entryReason
        };
        
        if (USER_STATUS === 'guest') {
            entry.id = 'trade_' + Date.now();
            entry.exitDate = null;
            entry.exitPrice = null;
            entry.exitReason = null;
            entry.status = 'Active';
            entry.pnl = null;

            state.journal.push(entry);
            localStorage.setItem('trade_journal', JSON.stringify(state.journal));
            
            alert(`Successfully journaled trade entry for ${ticker}!`);
            document.getElementById('journal-input-reason').value = '';
            renderJournalDashboard();
        } else {
            fetch('/api/journal/add/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(entry)
            })
            .then(res => res.json())
            .then(res => {
                if (res.status === 'success') {
                    alert(`Successfully journaled trade entry for ${ticker}!`);
                    document.getElementById('journal-input-reason').value = '';
                    syncJournalWithBackend();
                } else {
                    alert(`Failed to save trade: ${res.message}`);
                }
            })
            .catch(err => {
                console.error('Error saving trade to DB', err);
                alert('Error connecting to backend database.');
            });
        }
    }

    function renderJournalDashboard() {
        const tbody = document.getElementById('journal-tbody');
        const statTotal = document.getElementById('journal-stat-total');
        const statActive = document.getElementById('journal-stat-active');
        const statWinrate = document.getElementById('journal-stat-winrate');
        const statPnl = document.getElementById('journal-stat-pnl');
        
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        const filter = state.journalFilter || 'all';
        
        // Helper to check if trade date fits filter
        function isTradeInPeriod(t, period) {
            if (period === 'all') return true;
            const dateStr = t.status === 'Realized' ? t.exitDate : t.entryDate;
            if (!dateStr) return false;
            
            const tradeDate = new Date(dateStr);
            const today = new Date();
            
            tradeDate.setHours(0,0,0,0);
            today.setHours(0,0,0,0);
            
            const diffTime = Math.abs(today - tradeDate);
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
            if (period === 'daily') return diffDays <= 1;
            if (period === 'monthly') return diffDays <= 30;
            if (period === 'yearly') return diffDays <= 365;
            return true;
        }

        const journal = state.journal.filter(t => isTradeInPeriod(t, filter));
        statTotal.innerText = journal.length;
        
        const activeTrades = journal.filter(t => t.status === 'Active');
        statActive.innerText = activeTrades.length;
        
        const closedTrades = journal.filter(t => t.status === 'Realized');
        
        let winCount = 0;
        closedTrades.forEach(t => {
            if (t.pnl > 0) winCount++;
        });
        
        const winRate = closedTrades.length > 0 ? Math.round((winCount / closedTrades.length) * 100) : 0;
        statWinrate.innerText = `${winRate}%`;
        
        // Calculate absolute realized PnL based on trade quantity
        let realizedAbsolutePnL = 0;
        closedTrades.forEach(t => {
            const diff = t.exitPrice - t.entryPrice;
            const tradePnL = (t.type === 'Long' ? diff : -diff) * (t.quantity || 10);
            realizedAbsolutePnL += tradePnL;
        });
        
        const formattedAbsolutePnl = realizedAbsolutePnL >= 0 
            ? `₹${realizedAbsolutePnL.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` 
            : `-₹${Math.abs(realizedAbsolutePnL).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
        
        statPnl.innerText = formattedAbsolutePnl;
        statPnl.className = `stat-val ${realizedAbsolutePnL >= 0 ? 'text-green' : 'text-red'}`;
        
        if (journal.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-secondary); font-size: 13px; padding: 20px;">No journal entries match the "${filter}" filter. Select a stock in the Screener Grid and scroll down the details drawer to log a dummy trade!</td></tr>`;
            return;
        }
        
        journal.forEach(t => {
            const tr = document.createElement('tr');
            
            const stock = state.stocks[t.ticker];
            const currentPrice = stock ? stock.current.price : t.entryPrice;
            
            let pnlDisplay = '';
            let pnlClass = '';
            
            const quantity = t.quantity || 10;
            
            if (t.status === 'Active') {
                const diff = currentPrice - t.entryPrice;
                const pct = (t.type === 'Long' ? diff : -diff) / t.entryPrice * 100;
                const absolute = (t.type === 'Long' ? diff : -diff) * quantity;
                pnlDisplay = `Active: ${pct >= 0 ? '+' : ''}${pct.toFixed(2)}% (${absolute >= 0 ? '+' : ''}₹${absolute.toFixed(2)})`;
                pnlClass = pct >= 0 ? 'text-green' : 'text-red';
            } else {
                const diff = t.exitPrice - t.entryPrice;
                const absolute = (t.type === 'Long' ? diff : -diff) * quantity;
                const pnlVal = typeof t.pnl === 'number' ? t.pnl : 0;
                pnlDisplay = `${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)}% (${absolute >= 0 ? '+' : ''}₹${absolute.toFixed(2)})`;
                pnlClass = pnlVal >= 0 ? 'text-green' : 'text-red';
            }
            
            const exitDetails = t.status === 'Active' 
                ? `<span style="color: var(--text-secondary); font-size: 11px;">Active at ₹${currentPrice.toFixed(2)}</span>` 
                : `<div style="font-size: 12px; font-weight: 500;">₹${t.exitPrice.toFixed(2)}</div><div style="font-size: 10px; color: var(--text-secondary);">${t.exitDate}</div>`;
                
            const typeBadge = t.type === 'Long' 
                ? `<span class="badge badge-green" style="font-size: 10px; padding: 2px 6px;">BUY</span>` 
                : `<span class="badge badge-red" style="font-size: 10px; padding: 2px 6px;">SELL</span>`;
                
            const actionBtn = t.status === 'Active'
                ? `<button onclick="App.triggerCloseTrade('${t.id}')" style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #f87171; font-size: 11px; padding: 4px 8px; border-radius: 4px; cursor: pointer; outline: none; transition: all 0.2s;"><i class="fa-solid fa-door-closed"></i> Close</button>`
                : `<button onclick="App.triggerDeleteTrade('${t.id}')" style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); color: var(--text-secondary); font-size: 11px; padding: 4px 8px; border-radius: 4px; cursor: pointer; outline: none; transition: all 0.2s;"><i class="fa-solid fa-trash-can"></i> Delete</button>`;
            
            const slText = t.stopLoss ? `<div style="font-size: 11px; color: #f87171; font-weight: 500;">SL: ₹${t.stopLoss.toFixed(2)}</div>` : '';
            
            let notesText = `<strong>Entry:</strong> ${t.entryReason || 'No reason logged'}`;
            if (t.status === 'Realized' && t.exitReason) {
                notesText += `<br/><strong>Exit:</strong> ${t.exitReason}`;
            }

            tr.innerHTML = `
                <td style="font-weight: 600; color: var(--accent-indigo); cursor: pointer;" onclick="App.triggerSelect('${t.ticker}')">${t.ticker}</td>
                <td>${typeBadge}</td>
                <td>
                    <div style="font-size: 12px; font-weight: 500;">₹${t.entryPrice.toFixed(2)}</div>
                    <div style="font-size: 11px; color: var(--text-secondary);">${quantity} shares</div>
                    ${slText}
                    <div style="font-size: 10px; color: var(--text-secondary); margin-top: 2px;">${t.entryDate}</div>
                </td>
                <td>${exitDetails}</td>
                <td style="font-weight: 600;" class="${pnlClass}">${pnlDisplay}</td>
                <td><span class="badge ${t.status === 'Active' ? 'badge-blue' : 'badge-green'}" style="font-size: 10px; padding: 2px 6px;">${t.status.toUpperCase()}</span></td>
                <td style="font-size: 11px; color: var(--text-secondary); max-width: 250px; white-space: normal; line-height: 1.4;">${notesText}</td>
                <td>${actionBtn}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    function openCloseTradeModal(tradeId) {
        const trade = state.journal.find(t => t.id === tradeId);
        if (!trade) return;
        
        closingTradeId = tradeId;
        
        document.getElementById('close-modal-ticker').innerText = trade.ticker;
        
        const wrapper = document.getElementById('close-modal-date-wrapper');
        const stock = state.stocks[trade.ticker];
        
        if (stock && stock.candles && stock.candles.length > 0) {
            // Render select dropdown
            wrapper.innerHTML = `<select id="close-modal-date" style="width: 100%; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.1); color: var(--text-primary); padding: 6px; border-radius: 4px; outline: none; font-size: 12px; font-family: var(--font-stack);"></select>`;
            const dateSelect = document.getElementById('close-modal-date');
            
            const entryIdx = stock.candles.findIndex(c => c.date === trade.entryDate);
            const startIdx = entryIdx !== -1 ? entryIdx : 0;
            const exitCandles = stock.candles.slice(startIdx);
            
            exitCandles.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.date;
                opt.text = c.date;
                dateSelect.appendChild(opt);
            });
            
            const latestCandle = stock.candles[stock.candles.length - 1];
            document.getElementById('close-modal-price').value = latestCandle.close.toFixed(2);
            document.getElementById('close-modal-reason').value = '';
            
            dateSelect.onchange = () => {
                const selectedDate = dateSelect.value;
                const candle = stock.candles.find(c => c.date === selectedDate);
                if (candle) {
                    document.getElementById('close-modal-price').value = candle.close.toFixed(2);
                }
            };
        } else {
            // Render fallback date picker input since stock is not loaded
            const todayStr = new Date().toISOString().split('T')[0];
            wrapper.innerHTML = `<input type="date" id="close-modal-date" value="${todayStr}" min="${trade.entryDate}" style="width: 100%; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.1); color: var(--text-primary); padding: 6px; border-radius: 4px; outline: none; font-size: 12px; font-family: var(--font-stack);">`;
            
            document.getElementById('close-modal-price').value = trade.entryPrice.toFixed(2);
            document.getElementById('close-modal-reason').value = '';
        }
        
        document.getElementById('close-trade-modal').classList.remove('hidden');
    }

    function submitCloseTrade() {
        if (!closingTradeId) return;
        
        const trade = state.journal.find(t => t.id === closingTradeId);
        if (!trade) return;
        
        const dateInput = document.getElementById('close-modal-date');
        const exitDate = dateInput ? dateInput.value : '';
        const exitPrice = parseFloat(document.getElementById('close-modal-price').value);
        const exitReason = document.getElementById('close-modal-reason').value.trim();
        
        if (!exitDate) {
            alert('Please select or enter a valid exit date.');
            return;
        }
        
        if (isNaN(exitPrice) || exitPrice <= 0) {
            alert('Please enter a valid exit price.');
            return;
        }
        
        if (USER_STATUS === 'guest') {
            const diff = exitPrice - trade.entryPrice;
            const pnl = (trade.type === 'Long' ? diff : -diff) / trade.entryPrice * 100;
            
            trade.exitDate = exitDate;
            trade.exitPrice = exitPrice;
            trade.exitReason = exitReason;
            trade.status = 'Realized';
            trade.pnl = pnl;
            
            localStorage.setItem('trade_journal', JSON.stringify(state.journal));
            document.getElementById('close-trade-modal').classList.add('hidden');
            closingTradeId = null;
            
            renderJournalDashboard();
            alert(`Successfully closed trade for ${trade.ticker}! Realized Return: ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`);
        } else {
            fetch('/api/journal/close/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    id: closingTradeId,
                    exitDate: exitDate,
                    exitPrice: exitPrice,
                    exitReason: exitReason
                })
            })
            .then(res => res.json())
            .then(res => {
                if (res.status === 'success') {
                    document.getElementById('close-trade-modal').classList.add('hidden');
                    closingTradeId = null;
                    syncJournalWithBackend();
                    alert(`Successfully closed trade for ${trade.ticker}! Realized Return: ${res.pnl >= 0 ? '+' : ''}${res.pnl.toFixed(2)}%`);
                } else {
                    alert(`Failed to close trade: ${res.message}`);
                }
            })
            .catch(err => {
                console.error('Error closing trade in DB', err);
                alert('Error connecting to backend database.');
            });
        }
    }

    function deleteJournalEntry(tradeId) {
        if (confirm('Are you sure you want to delete this journal entry?')) {
            if (USER_STATUS === 'guest') {
                state.journal = state.journal.filter(t => t.id !== tradeId);
                localStorage.setItem('trade_journal', JSON.stringify(state.journal));
                renderJournalDashboard();
            } else {
                fetch('/api/journal/delete/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken')
                    },
                    body: JSON.stringify({ id: tradeId })
                })
                .then(res => res.json())
                .then(res => {
                    if (res.status === 'success') {
                        syncJournalWithBackend();
                    } else {
                        alert(`Failed to delete trade: ${res.message}`);
                    }
                })
                .catch(err => {
                    console.error('Error deleting trade from DB', err);
                    alert('Error connecting to backend database.');
                });
            }
        }
    }

    // --- Admin Screener Statistics & Export Engine ---

    let adminStatsSortField = 'ticker';
    let adminStatsSortDirection = 'asc';

    function renderAdminStatsDashboard() {
        const stocks = Object.values(state.stocks);
        if (!stocks || stocks.length === 0) return;

        const selUniverse = document.getElementById('sel-stats-universe')?.value || 'all';
        const selStatus = document.getElementById('sel-stats-status')?.value || 'all';
        const selSignal = document.getElementById('sel-stats-momentum')?.value || 'all';
        const searchQuery = (document.getElementById('txt-stats-search')?.value || '').trim().toUpperCase();

        // 1. Filter Stocks
        const filteredStocks = stocks.filter(stock => {
            const isN50 = MockDataEngine.NIFTY50_LIST.includes(stock.ticker);
            const isFo = MockDataEngine.FO_LIST.includes(stock.ticker);
            
            // Universe filter
            if (selUniverse === 'nifty50' && !isN50) return false;
            if (selUniverse === 'fo' && !isFo) return false;

            // Status filter
            if (selStatus !== 'all' && stock.status !== selStatus) return false;

            // Signal filter
            if (selSignal === 'shift' && !stock.current.hasMomentumShift) return false;
            if (selSignal === 'oversold' && (stock.current.rsi === null || stock.current.rsi >= 30)) return false;
            if (selSignal === 'overbought' && (stock.current.rsi === null || stock.current.rsi <= 70)) return false;
            if (selSignal === 'near50' && stock.current.milestone !== 'Near EMA50') return false;
            if (selSignal === 'near200' && stock.current.milestone !== 'Near SMA200') return false;

            // Search query filter
            if (searchQuery) {
                const tickerMatch = stock.ticker.toUpperCase().includes(searchQuery);
                const nameMatch = (stock.name || '').toUpperCase().includes(searchQuery);
                if (!tickerMatch && !nameMatch) return false;
            }

            return true;
        });

        // 2. Compute Summary Statistics across the active filtered universe
        const total = filteredStocks.length;
        let safeCount = 0;
        let above200Count = 0;
        let above50Count = 0;
        let momentumShiftCount = 0;
        let strongAdxCount = 0;
        let rsiSum = 0;
        let rsiCount = 0;
        let adxSum = 0;
        let adxCount = 0;
        let ddSum = 0;
        let maxDd = 0;

        filteredStocks.forEach(stock => {
            const c = stock.current;
            if (stock.status === 'Safe') safeCount++;
            if (c.aboveSMA200) above200Count++;
            
            const lastIdx = stock.candles.length - 1;
            const s50 = stock.indicators.sma50 ? stock.indicators.sma50[lastIdx] : null;
            if (s50 && c.price >= s50) above50Count++;
            
            if (c.hasMomentumShift) momentumShiftCount++;
            if (c.adx !== null && c.adx !== undefined) {
                adxSum += c.adx;
                adxCount++;
                if (c.adx >= 25) strongAdxCount++;
            }
            if (c.rsi !== null && c.rsi !== undefined) {
                rsiSum += c.rsi;
                rsiCount++;
            }
            if (c.drawdown !== null && c.drawdown !== undefined) {
                ddSum += c.drawdown;
                if (c.drawdown > maxDd) maxDd = c.drawdown;
            }
        });

        const safePct = total ? Math.round((safeCount / total) * 100) : 0;
        const above200Pct = total ? Math.round((above200Count / total) * 100) : 0;
        const above50Pct = total ? Math.round((above50Count / total) * 100) : 0;
        const strongAdxPct = total ? Math.round((strongAdxCount / total) * 100) : 0;
        const avgRsi = rsiCount ? (rsiSum / rsiCount).toFixed(1) : 'N/A';
        const avgAdx = adxCount ? (adxSum / adxCount).toFixed(1) : 'N/A';
        const avgDd = total ? (ddSum / total).toFixed(1) : '0.0';

        // Update KPI Elements
        const elTotal = document.getElementById('stat-admin-total');
        if (elTotal) elTotal.textContent = total.toString();
        const elHealth = document.getElementById('stat-admin-health-sub');
        if (elHealth) elHealth.textContent = `${safePct}% Safe (${safeCount}/${total})`;

        const elAbove200 = document.getElementById('stat-admin-above200');
        if (elAbove200) elAbove200.textContent = `${above200Pct}%`;
        const elCrossSub = document.getElementById('stat-admin-cross-sub');
        if (elCrossSub) elCrossSub.textContent = `${above200Count} Above / ${total - above200Count} Below`;

        const elAbove50 = document.getElementById('stat-admin-above50');
        if (elAbove50) elAbove50.textContent = `${above50Pct}%`;
        const elRsiSub = document.getElementById('stat-admin-rsi-sub');
        if (elRsiSub) elRsiSub.textContent = `Avg RSI: ${avgRsi}`;

        const elStrongAdx = document.getElementById('stat-admin-strong-adx');
        if (elStrongAdx) elStrongAdx.textContent = `${strongAdxPct}%`;
        const elAdxSub = document.getElementById('stat-admin-adx-sub');
        if (elAdxSub) elAdxSub.textContent = `Avg: ${avgAdx} (${strongAdxCount} Trend)`;

        const elAvgDd = document.getElementById('stat-admin-avg-dd');
        if (elAvgDd) elAvgDd.textContent = `${avgDd}%`;
        const elMaxDdSub = document.getElementById('stat-admin-max-dd-sub');
        if (elMaxDdSub) elMaxDdSub.textContent = `Max DD: ${maxDd.toFixed(1)}%`;

        const elCount = document.getElementById('lbl-stats-count');
        if (elCount) elCount.textContent = `${total} of ${stocks.length} stocks`;

        // 3. Sort Filtered Stocks
        const sortedStocks = [...filteredStocks].sort((a, b) => {
            let valA, valB;
            const lastA = a.candles.length - 1;
            const lastB = b.candles.length - 1;
            const s50A = a.indicators.sma50 ? a.indicators.sma50[lastA] : 0;
            const s50B = b.indicators.sma50 ? b.indicators.sma50[lastB] : 0;
            const s200A = a.indicators.sma200 ? a.indicators.sma200[lastA] : 0;
            const s200B = b.indicators.sma200 ? b.indicators.sma200[lastB] : 0;

            switch (adminStatsSortField) {
                case 'ticker': valA = a.ticker; valB = b.ticker; break;
                case 'name': valA = a.name; valB = b.name; break;
                case 'universe':
                    valA = MockDataEngine.NIFTY50_LIST.includes(a.ticker) ? 'NIFTY 50' : 'F&O';
                    valB = MockDataEngine.NIFTY50_LIST.includes(b.ticker) ? 'NIFTY 50' : 'F&O';
                    break;
                case 'price': valA = a.current.price; valB = b.current.price; break;
                case 'status': valA = a.status; valB = b.status; break;
                case 'pctChange': valA = a.current.pctChange; valB = b.current.pctChange; break;
                case 'pctChange7d': valA = a.current.pctChange7d; valB = b.current.pctChange7d; break;
                case 'rsi': valA = a.current.rsi ?? -1; valB = b.current.rsi ?? -1; break;
                case 'adx': valA = a.current.adx ?? -1; valB = b.current.adx ?? -1; break;
                case 'drawdown': valA = a.current.drawdown ?? -1; valB = b.current.drawdown ?? -1; break;
                case 'sma50': valA = s50A; valB = s50B; break;
                case 'sma200': valA = s200A; valB = s200B; break;
                case 'dist50':
                    valA = s50A ? ((a.current.price - s50A) / s50A) : -999;
                    valB = s50B ? ((b.current.price - s50B) / s50B) : -999;
                    break;
                case 'dist200':
                    valA = s200A ? ((a.current.price - s200A) / s200A) : -999;
                    valB = s200B ? ((b.current.price - s200B) / s200B) : -999;
                    break;
                case 'milestone': valA = a.current.milestone; valB = b.current.milestone; break;
                case 'momentumShift': valA = a.current.hasMomentumShift ? 1 : 0; valB = b.current.hasMomentumShift ? 1 : 0; break;
                case 'ret30d': {
                    const p30A = a.candles.length >= 30 ? a.candles[a.candles.length - 30].close : a.candles[0].close;
                    const p30B = b.candles.length >= 30 ? b.candles[b.candles.length - 30].close : b.candles[0].close;
                    valA = p30A ? ((a.current.price - p30A) / p30A) : 0;
                    valB = p30B ? ((b.current.price - p30B) / p30B) : 0;
                    break;
                }
                case 'ret1y': {
                    const p1yA = a.candles.length >= 250 ? a.candles[a.candles.length - 250].close : a.candles[0].close;
                    const p1yB = b.candles.length >= 250 ? b.candles[b.candles.length - 250].close : b.candles[0].close;
                    valA = p1yA ? ((a.current.price - p1yA) / p1yA) : 0;
                    valB = p1yB ? ((b.current.price - p1yB) / p1yB) : 0;
                    break;
                }
                case 'high52w': {
                    const slA = a.candles.slice(-Math.min(250, a.candles.length)).map(x => x.close);
                    const slB = b.candles.slice(-Math.min(250, b.candles.length)).map(x => x.close);
                    valA = Math.max(...slA); valB = Math.max(...slB);
                    break;
                }
                case 'low52w': {
                    const sllA = a.candles.slice(-Math.min(250, a.candles.length)).map(x => x.close);
                    const sllB = b.candles.slice(-Math.min(250, b.candles.length)).map(x => x.close);
                    valA = Math.min(...sllA); valB = Math.min(...sllB);
                    break;
                }
                case 'volume': {
                    const volsA = a.candles.slice(-20).map(x => x.volume || 0);
                    const volsB = b.candles.slice(-20).map(x => x.volume || 0);
                    valA = volsA.length ? (volsA.reduce((x, y) => x + y, 0) / volsA.length) : 0;
                    valB = volsB.length ? (volsB.reduce((x, y) => x + y, 0) / volsB.length) : 0;
                    break;
                }
                default:
                    valA = a.ticker; valB = b.ticker;
            }

            if (valA < valB) return adminStatsSortDirection === 'asc' ? -1 : 1;
            if (valA > valB) return adminStatsSortDirection === 'asc' ? 1 : -1;
            return 0;
        });

        // 4. Populate Table
        const tbody = document.getElementById('admin-stats-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (sortedStocks.length === 0) {
            tbody.innerHTML = `<tr><td colspan="21" style="text-align: center; color: var(--text-secondary); font-size: 13px; padding: 30px;">No stocks match your filter criteria.</td></tr>`;
            return;
        }

        sortedStocks.forEach(stock => {
            const tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            tr.style.borderBottom = '1px solid rgba(255, 255, 255, 0.04)';
            tr.style.transition = 'background 0.2s';
            tr.addEventListener('mouseover', () => tr.style.background = 'rgba(255, 255, 255, 0.04)');
            tr.addEventListener('mouseout', () => tr.style.background = 'transparent');
            tr.addEventListener('click', () => openDetailDrawer(stock.ticker));

            const c = stock.current;
            const ind = stock.indicators;
            const lastIdx = stock.candles.length - 1;
            const prices = stock.candles.map(x => x.close);
            const sma50 = ind.sma50 ? ind.sma50[lastIdx] : null;
            const sma200 = ind.sma200 ? ind.sma200[lastIdx] : null;

            const dist50 = (sma50 && c.price) ? (((c.price - sma50) / sma50) * 100).toFixed(1) : '-';
            const dist200 = (sma200 && c.price) ? (((c.price - sma200) / sma200) * 100).toFixed(1) : '-';

            const lookback = Math.min(250, stock.candles.length);
            const slice52w = prices.slice(-lookback);
            const max52w = slice52w.length ? Math.max(...slice52w) : c.price;
            const min52w = slice52w.length ? Math.min(...slice52w) : c.price;

            const p30d = stock.candles.length >= 30 ? prices[stock.candles.length - 30] : prices[0];
            const ret30d = p30d ? (((c.price - p30d) / p30d) * 100).toFixed(1) : '0.0';

            const p1y = stock.candles.length >= 250 ? prices[stock.candles.length - 250] : prices[0];
            const ret1y = p1y ? (((c.price - p1y) / p1y) * 100).toFixed(1) : '0.0';

            const vols = stock.candles.slice(-20).map(x => x.volume || 0);
            const avgVol = vols.length ? Math.round(vols.reduce((a, b) => a + b, 0) / vols.length) : 0;

            const isN50 = MockDataEngine.NIFTY50_LIST.includes(stock.ticker);
            const universeBadge = isN50
                ? `<span style="font-size: 9px; padding: 2px 6px; border-radius: 4px; background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); font-weight: 600;">NIFTY 50</span>`
                : `<span style="font-size: 9px; padding: 2px 6px; border-radius: 4px; background: rgba(244, 162, 97, 0.15); color: #f4a261; border: 1px solid rgba(244, 162, 97, 0.3); font-weight: 600;">F&O</span>`;

            const statusBadge = stock.status === 'Safe'
                ? `<span class="badge badge-green" style="font-size: 10px; padding: 2px 8px;">Safe</span>`
                : `<span class="badge badge-red" style="font-size: 10px; padding: 2px 8px;">Knife</span>`;

            const shiftBadge = c.hasMomentumShift
                ? `<span style="color: #34d399; font-weight: 700; font-size: 11px;"><i class="fa-solid fa-arrow-trend-up"></i> YES</span>`
                : `<span style="color: var(--text-muted); font-size: 11px;">-</span>`;

            const rsiColor = (c.rsi !== null && c.rsi < 30) ? '#34d399' : (c.rsi !== null && c.rsi > 70) ? '#f87171' : 'var(--text-primary)';
            const rsiVal = (c.rsi !== null && c.rsi !== undefined) ? `<span style="color: ${rsiColor}; font-weight: 600;">${c.rsi.toFixed(1)}</span>` : '-';
            const adxVal = (c.adx !== null && c.adx !== undefined) ? `<span style="font-weight: 600; color: ${c.adx >= 25 ? '#c084fc' : 'var(--text-secondary)'};">${c.adx.toFixed(1)}</span>` : '-';

            const pct1dColor = c.pctChange >= 0 ? '#34d399' : '#f87171';
            const pct7dColor = c.pctChange7d >= 0 ? '#34d399' : '#f87171';
            const ret30dColor = parseFloat(ret30d) >= 0 ? '#34d399' : '#f87171';
            const ret1yColor = parseFloat(ret1y) >= 0 ? '#34d399' : '#f87171';

            tr.innerHTML = `
                <td class="stats-col-ticker" style="padding: 8px 12px; font-weight: 700; color: var(--text-primary); white-space: nowrap;">${stock.ticker}</td>
                <td style="padding: 8px 12px; color: var(--text-secondary); max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${stock.name}</td>
                <td style="padding: 8px 12px; white-space: nowrap;">${universeBadge}</td>
                <td style="padding: 8px 12px; text-align: right; font-weight: 600; color: var(--text-primary); white-space: nowrap;">₹${c.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td style="padding: 8px 12px; text-align: center; white-space: nowrap;">${statusBadge}</td>
                <td style="padding: 8px 12px; text-align: right; color: ${pct1dColor}; font-weight: 600; white-space: nowrap;">${c.pctChange >= 0 ? '+' : ''}${c.pctChange}%</td>
                <td style="padding: 8px 12px; text-align: right; color: ${pct7dColor}; font-weight: 600; white-space: nowrap;">${c.pctChange7d >= 0 ? '+' : ''}${c.pctChange7d}%</td>
                <td style="padding: 8px 12px; text-align: right; white-space: nowrap;">${rsiVal}</td>
                <td style="padding: 8px 12px; text-align: right; white-space: nowrap;">${adxVal}</td>
                <td style="padding: 8px 12px; text-align: right; color: ${c.drawdown > 20 ? '#f87171' : 'var(--text-primary)'}; white-space: nowrap;">${c.drawdown ?? 0}%</td>
                <td style="padding: 8px 12px; text-align: right; color: var(--text-secondary); white-space: nowrap;">${sma50 ? '₹' + sma50.toFixed(1) : '-'}</td>
                <td style="padding: 8px 12px; text-align: right; color: var(--text-secondary); white-space: nowrap;">${sma200 ? '₹' + sma200.toFixed(1) : '-'}</td>
                <td style="padding: 8px 12px; text-align: right; color: ${parseFloat(dist50) >= 0 ? '#34d399' : '#f87171'}; white-space: nowrap;">${dist50 !== '-' && parseFloat(dist50) >= 0 ? '+' : ''}${dist50}%</td>
                <td style="padding: 8px 12px; text-align: right; color: ${parseFloat(dist200) >= 0 ? '#34d399' : '#f87171'}; white-space: nowrap;">${dist200 !== '-' && parseFloat(dist200) >= 0 ? '+' : ''}${dist200}%</td>
                <td style="padding: 8px 12px; white-space: nowrap;"><span class="badge-milestone">${c.milestone || 'Stable'}</span></td>
                <td style="padding: 8px 12px; text-align: center; white-space: nowrap;">${shiftBadge}</td>
                <td style="padding: 8px 12px; text-align: right; color: ${ret30dColor}; white-space: nowrap;">${parseFloat(ret30d) >= 0 ? '+' : ''}${ret30d}%</td>
                <td style="padding: 8px 12px; text-align: right; color: ${ret1yColor}; white-space: nowrap;">${parseFloat(ret1y) >= 0 ? '+' : ''}${ret1y}%</td>
                <td style="padding: 8px 12px; text-align: right; color: var(--text-secondary); white-space: nowrap;">₹${max52w.toLocaleString(undefined, {maximumFractionDigits: 1})}</td>
                <td style="padding: 8px 12px; text-align: right; color: var(--text-secondary); white-space: nowrap;">₹${min52w.toLocaleString(undefined, {maximumFractionDigits: 1})}</td>
                <td style="padding: 8px 12px; text-align: right; color: var(--text-muted); white-space: nowrap;">${avgVol.toLocaleString()}</td>
            `;
            tbody.appendChild(tr);
        });

        // 5. Update header sort indicators
        document.querySelectorAll('#admin-stats-table th.stats-th.sortable').forEach(th => {
            const field = th.getAttribute('data-sort');
            const icon = th.querySelector('i');
            if (icon) {
                if (adminStatsSortField === field) {
                    icon.className = adminStatsSortDirection === 'asc' ? 'fa-solid fa-sort-up' : 'fa-solid fa-sort-down';
                    icon.style.color = 'var(--text-primary)';
                } else {
                    icon.className = 'fa-solid fa-sort';
                    icon.style.color = 'var(--text-muted)';
                }
            }
        });
    }

    function exportScreenerDataCSV() {
        const stocks = Object.values(state.stocks);
        if (!stocks || stocks.length === 0) {
            alert("No screener data loaded yet to export.");
            return;
        }

        const selUniverse = document.getElementById('sel-stats-universe')?.value || 'all';
        const selStatus = document.getElementById('sel-stats-status')?.value || 'all';
        const selSignal = document.getElementById('sel-stats-momentum')?.value || 'all';

        const filtered = stocks.filter(stock => {
            const isN50 = MockDataEngine.NIFTY50_LIST.includes(stock.ticker);
            const isFo = MockDataEngine.FO_LIST.includes(stock.ticker);
            if (selUniverse === 'nifty50' && !isN50) return false;
            if (selUniverse === 'fo' && !isFo) return false;
            if (selStatus !== 'all' && stock.status !== selStatus) return false;
            if (selSignal === 'shift' && !stock.current.hasMomentumShift) return false;
            if (selSignal === 'oversold' && (stock.current.rsi === null || stock.current.rsi >= 30)) return false;
            if (selSignal === 'overbought' && (stock.current.rsi === null || stock.current.rsi <= 70)) return false;
            if (selSignal === 'near50' && stock.current.milestone !== 'Near EMA50') return false;
            if (selSignal === 'near200' && stock.current.milestone !== 'Near SMA200') return false;
            return true;
        });

        const headers = [
            "Ticker",
            "Company Name",
            "Universe",
            "Price (INR)",
            "Status",
            "Milestone",
            "Momentum Shift Today",
            "50 SMA (INR)",
            "200 SMA (INR)",
            "Distance from 50 SMA (%)",
            "Distance from 200 SMA (%)",
            "Position vs 200 SMA",
            "RSI (14)",
            "RSI Classification",
            "ADX (14)",
            "Trend Strength",
            "+DI",
            "-DI",
            "1-Yr Max Drawdown (%)",
            "1-Day Change (%)",
            "7-Day Return (%)",
            "30-Day Return (%)",
            "1-Year Return (%)",
            "52-Week High (INR)",
            "52-Week Low (INR)",
            "Distance from 52W High (%)",
            "20-Day Avg Volume",
            "MACD Win Rate (%)",
            "MACD Total Trades",
            "MACD Avg PnL (%)",
            "Data Source",
            "Export Timestamp"
        ];

        const rows = filtered.map(stock => {
            const c = stock.current;
            const ind = stock.indicators;
            const prices = stock.candles.map(x => x.close);
            const lastIdx = stock.candles.length - 1;
            const sma50 = ind.sma50 ? ind.sma50[lastIdx] : null;
            const sma200 = ind.sma200 ? ind.sma200[lastIdx] : null;
            const dist50 = (sma50 && c.price) ? (((c.price - sma50) / sma50) * 100).toFixed(2) : "N/A";
            const dist200 = (sma200 && c.price) ? (((c.price - sma200) / sma200) * 100).toFixed(2) : "N/A";

            const lookback = Math.min(250, stock.candles.length);
            const slice52w = prices.slice(-lookback);
            const max52w = slice52w.length ? Math.max(...slice52w) : c.price;
            const min52w = slice52w.length ? Math.min(...slice52w) : c.price;
            const dist52wHigh = max52w ? (((c.price - max52w) / max52w) * 100).toFixed(2) : "0.00";

            const p30d = stock.candles.length >= 30 ? prices[stock.candles.length - 30] : prices[0];
            const ret30d = p30d ? (((c.price - p30d) / p30d) * 100).toFixed(2) : "0.00";

            const p1y = stock.candles.length >= 250 ? prices[stock.candles.length - 250] : prices[0];
            const ret1y = p1y ? (((c.price - p1y) / p1y) * 100).toFixed(2) : "0.00";

            const vols = stock.candles.slice(-20).map(x => x.volume || 0);
            const avgVol = vols.length ? Math.round(vols.reduce((a, b) => a + b, 0) / vols.length) : 0;

            const isN50 = MockDataEngine.NIFTY50_LIST.includes(stock.ticker);
            const universe = isN50 ? "NIFTY 50" : "NIFTY F&O";

            const rsiClass = (c.rsi !== null && c.rsi !== undefined) ? (c.rsi < 30 ? "Oversold (<30)" : c.rsi > 70 ? "Overbought (>70)" : "Neutral (30-70)") : "N/A";
            const trendStr = (c.adx !== null && c.adx !== undefined) ? (c.adx >= 25 ? "Strong Trend (ADX>=25)" : "Consolidation (ADX<25)") : "N/A";

            return [
                stock.ticker,
                `"${(stock.name || stock.ticker).replace(/"/g, '""')}"`,
                universe,
                c.price.toFixed(2),
                stock.status,
                c.milestone || "Stable",
                c.hasMomentumShift ? "YES" : "NO",
                sma50 ? sma50.toFixed(2) : "N/A",
                sma200 ? sma200.toFixed(2) : "N/A",
                dist50,
                dist200,
                c.aboveSMA200 ? "Above 200 SMA" : "Below 200 SMA",
                c.rsi !== null && c.rsi !== undefined ? c.rsi.toFixed(1) : "N/A",
                rsiClass,
                c.adx !== null && c.adx !== undefined ? c.adx.toFixed(1) : "N/A",
                trendStr,
                c.plusDI !== null && c.plusDI !== undefined ? c.plusDI.toFixed(1) : "N/A",
                c.minusDI !== null && c.minusDI !== undefined ? c.minusDI.toFixed(1) : "N/A",
                c.drawdown !== null && c.drawdown !== undefined ? c.drawdown.toFixed(2) : "0.00",
                c.pctChange !== null && c.pctChange !== undefined ? c.pctChange.toFixed(2) : "0.00",
                c.pctChange7d !== null && c.pctChange7d !== undefined ? c.pctChange7d.toFixed(2) : "0.00",
                ret30d,
                ret1y,
                max52w.toFixed(2),
                min52w.toFixed(2),
                dist52wHigh,
                avgVol,
                c.macdWinRate !== undefined ? c.macdWinRate + "%" : "N/A",
                c.macdTrades !== undefined ? c.macdTrades : "N/A",
                c.macdAvgPnL !== undefined ? c.macdAvgPnL + "%" : "N/A",
                state.dataSource === "zerodha" ? "Zerodha Kite API" : "Historical Simulation Dump",
                new Date().toISOString()
            ].join(",");
        });

        const csvContent = "\uFEFF" + [headers.join(","), ...rows].join("\r\n");
        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        const today = new Date().toISOString().split("T")[0];
        link.setAttribute("download", `TradeKriya_Screener_Parameters_${selUniverse}_${today}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    function exportScreenerDataJSON() {
        const stocks = Object.values(state.stocks);
        if (!stocks || stocks.length === 0) {
            alert("No screener data loaded yet to export.");
            return;
        }

        const dataDump = stocks.map(stock => {
            const c = stock.current;
            const ind = stock.indicators;
            const lastIdx = stock.candles.length - 1;
            return {
                ticker: stock.ticker,
                name: stock.name,
                universe: MockDataEngine.NIFTY50_LIST.includes(stock.ticker) ? 'NIFTY 50' : 'NIFTY F&O',
                price: c.price,
                status: stock.status,
                milestone: c.milestone,
                momentumShiftToday: c.hasMomentumShift,
                sma50: ind.sma50 ? ind.sma50[lastIdx] : null,
                sma200: ind.sma200 ? ind.sma200[lastIdx] : null,
                aboveSMA200: c.aboveSMA200,
                rsi: c.rsi,
                adx: c.adx,
                plusDI: c.plusDI,
                minusDI: c.minusDI,
                drawdown1Y: c.drawdown,
                change1D: c.pctChange,
                return7D: c.pctChange7d,
                candlesCount: stock.candles.length
            };
        });

        const jsonStr = JSON.stringify(dataDump, null, 2);
        const blob = new Blob([jsonStr], { type: "application/json;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        const today = new Date().toISOString().split("T")[0];
        link.setAttribute("download", `TradeKriya_Screener_Dump_${today}.json`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    function init() {
        bindEvents();
        
        // Pre-fill fields from sessionStorage if already configured
        const savedKey = sessionStorage.getItem('zerodha_api_key');
        const savedToken = sessionStorage.getItem('zerodha_access_token');
        const savedGemini = sessionStorage.getItem('gemini_api_key');
        const zKeyInput = document.getElementById('zerodha-api-key');
        const zTokenInput = document.getElementById('zerodha-access-token');
        const geminiInput = document.getElementById('gemini-api-key');

        if (savedKey && zKeyInput) zKeyInput.value = savedKey;
        if (savedToken && zTokenInput) zTokenInput.value = savedToken;
        if (savedGemini && geminiInput) geminiInput.value = savedGemini;

        if (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA) {
            if (zKeyInput) zKeyInput.placeholder = "Preconfigured in .env";
            if (zTokenInput) zTokenInput.placeholder = "Preconfigured in .env";
        }
        if (typeof SERVER_HAS_GEMINI !== 'undefined' && SERVER_HAS_GEMINI) {
            if (geminiInput) geminiInput.placeholder = "Preconfigured in .env";
        }

        // Always enforce simulation / historical snapshot mode for non-superusers
        if (typeof IS_SUPERUSER !== 'undefined' && !IS_SUPERUSER) {
            state.dataSource = 'simulation';
        }

        if (USER_STATUS !== 'guest') {
            syncJournalWithBackend();
        }

        // Start in Simulation / Historical Snapshot Mode
        loadSimulationData();
    }

    return {
        init,
        triggerSelect: (ticker) => {
            // Switch back to screener tab first
            document.getElementById('btn-tab-screener').click();
            openDetailDrawer(ticker);
        },
        triggerCloseTrade: (tradeId) => {
            openCloseTradeModal(tradeId);
        },
        triggerDeleteTrade: (tradeId) => {
            deleteJournalEntry(tradeId);
        }
    };
})();

// Bootstrap the application on page load
window.addEventListener('DOMContentLoaded', () => {
    App.init();
});
