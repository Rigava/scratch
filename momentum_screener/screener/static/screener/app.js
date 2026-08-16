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

            if (matchesSearch && matchesStatus && matchesPerf) {
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

            tr.innerHTML = `
                <td><strong>${stock.ticker}</strong></td>
                <td>
                    <strong>${stock.ticker}</strong>
                    <span class="symbol-name">${stock.name}</span>
                </td>
                <td>₹${stock.current.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td>${perfVisualHtml}</td>
                <td>${momentumShiftHtml}</td>
                <td>${milestoneHtml}</td>
                <td class="${stock.current.drawdown > state.filters.drawdown.threshold && state.filters.drawdown.enabled ? 'text-red' : ''}">${stock.current.drawdown}%</td>
                <td class="${stock.current.rsi < state.filters.rsi.threshold && state.filters.rsi.enabled ? 'text-red' : ''}">${stock.current.rsi ?? '-'}</td>
                <td>${stock.current.adx ?? '-'}</td>
                <td><span class="badge ${badgeClass}">${icon} ${stock.status}</span></td>
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

        // Open panel
        document.getElementById('detail-drawer').classList.add('active');
    }

    function closeDetailDrawer() {
        state.activeTicker = null;
        document.getElementById('detail-drawer').classList.remove('active');
        document.querySelectorAll('#screener-tbody tr').forEach(row => row.classList.remove('selected'));
    }

    // --- Data Loaders (Simulation vs. Zerodha Proxy) ---

    // Load static high-fidelity simulation pool
    function loadSimulationData() {
        state.stocks = MockDataEngine.getSimulatedData();
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
            alert(`Failed to load historical data for ${symbol}: ${err.message}`);
        }
    }

    // Call the Gemini API via Django backend to generate a quantitative finance campaign
    async function generateAICampaign() {
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
            symbols = MockDataEngine.NIFTY50_LIST;
        } else if (listType === 'fo') {
            symbols = [...new Set([...MockDataEngine.NIFTY50_LIST, ...MockDataEngine.FO_LIST])];
        }

        if (state.dataSource === 'simulation') {
            state.stocks = {};
            renderScreenerGrid();
            closeDetailDrawer();
            
            showScanProgress(true, `Initializing simulated ${listType.toUpperCase()} scan...`, `0 / ${symbols.length}`, 0);
            
            let simulatedPool = listType === 'nifty50' ? MockDataEngine.getSimulatedNifty50() : MockDataEngine.getSimulatedFO();
            
            for (let i = 0; i < symbols.length; i++) {
                const sym = symbols[i];
                state.stocks[sym] = simulatedPool[sym];
                processStockIndicators(state.stocks[sym]);
                renderScreenerGrid();
                
                const pct = Math.round(((i + 1) / symbols.length) * 100);
                showScanProgress(true, `Simulated scan: processing ${sym}...`, `${i + 1} / ${symbols.length}`, pct);
                
                await new Promise(r => setTimeout(r, 45));
            }
            
            showScanProgress(false);
        } else {
            // Zerodha Mode
            const apiKey = sessionStorage.getItem('zerodha_api_key') || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA ? 'SERVER_PRECONFIGURED' : '');
            const accessToken = sessionStorage.getItem('zerodha_access_token') || (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA ? 'SERVER_PRECONFIGURED' : '');
            if (!apiKey || !accessToken) {
                alert("Please configure your Zerodha Kite Credentials first in the top-right header!");
                document.getElementById('credentials-drawer').classList.remove('hidden');
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
        document.getElementById('btn-toggle-credentials').addEventListener('click', () => {
            document.getElementById('credentials-drawer').classList.toggle('hidden');
        });

        // Market batch scan binds
        document.getElementById('btn-scan-nifty50').addEventListener('click', () => executeMarketScan('nifty50'));
        document.getElementById('btn-scan-fo').addEventListener('click', () => executeMarketScan('fo'));

        // Source toggle buttons
        document.getElementById('btn-source-sim').addEventListener('click', (e) => {
            document.getElementById('btn-source-sim').classList.add('active');
            document.getElementById('btn-source-zerodha').classList.remove('active');
            document.getElementById('credentials-drawer').classList.add('hidden');
            document.getElementById('zerodha-add-ticker-section').classList.add('hidden');
            state.dataSource = 'simulation';
            closeDetailDrawer();
            loadSimulationData();
        });

        document.getElementById('btn-source-zerodha').addEventListener('click', (e) => {
            document.getElementById('btn-source-zerodha').classList.add('active');
            document.getElementById('btn-source-sim').classList.remove('active');
            document.getElementById('credentials-drawer').classList.remove('hidden');
            document.getElementById('zerodha-add-ticker-section').classList.remove('hidden');
            state.dataSource = 'zerodha';
            closeDetailDrawer();

            // Clear simulation pool, wait for auth inputs
            state.stocks = {};
            
            // Hydrate credentials inputs if already saved in session storage
            const savedKey = sessionStorage.getItem('zerodha_api_key');
            const savedToken = sessionStorage.getItem('zerodha_access_token');
            const savedGemini = sessionStorage.getItem('gemini_api_key');
            if (savedKey) document.getElementById('zerodha-api-key').value = savedKey;
            if (savedToken) document.getElementById('zerodha-access-token').value = savedToken;
            if (savedGemini) document.getElementById('gemini-api-key').value = savedGemini;

            const isPreconfigZerodha = (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA);
            if (isPreconfigZerodha) {
                document.getElementById('zerodha-api-key').placeholder = "Preconfigured in .env";
                document.getElementById('zerodha-access-token').placeholder = "Preconfigured in .env";
            }
            if (typeof SERVER_HAS_GEMINI !== 'undefined' && SERVER_HAS_GEMINI) {
                document.getElementById('gemini-api-key').placeholder = "Preconfigured in .env";
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

        // Save Configurations Click (Zerodha + Gemini)
        document.getElementById('btn-auth-save').addEventListener('click', () => {
            const key = document.getElementById('zerodha-api-key').value.trim();
            const token = document.getElementById('zerodha-access-token').value.trim();
            const gemini = document.getElementById('gemini-api-key').value.trim();

            if (key) sessionStorage.setItem('zerodha_api_key', key);
            if (token) sessionStorage.setItem('zerodha_access_token', token);
            if (gemini) sessionStorage.setItem('gemini_api_key', gemini);

            alert('API settings saved successfully.');

            // If in Zerodha API mode, trigger load
            if (state.dataSource === 'zerodha' && key && token) {
                state.stocks = {};
                fetchZerodhaData('RELIANCE');
                fetchZerodhaData('TCS');
                fetchZerodhaData('INFY');
                hydrateActiveJournalTickers();
            }
        });

        // Bind generate campaign button
        document.getElementById('btn-generate-campaign').addEventListener('click', generateAICampaign);

        // Add Ticker Click
        document.getElementById('btn-add-ticker').addEventListener('click', () => {
            const selectSym = document.getElementById('sel-add-symbol');
            const customToken = document.getElementById('txt-add-custom-token').value.trim();
            
            const selectedVal = selectSym.value;

            if (customToken) {
                const tickerLabel = `INSTRUMENT-${customToken}`;
                fetchZerodhaData(tickerLabel, customToken);
                document.getElementById('txt-add-custom-token').value = '';
            } else if (selectedVal) {
                fetchZerodhaData(selectedVal);
            } else {
                alert('Please select a stock or input a custom instrument token.');
            }
        });

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

        // Tab switching binds
        const tabScreener = document.getElementById('btn-tab-screener');
        const tabBacktest = document.getElementById('btn-tab-backtest');
        const tabJournal = document.getElementById('btn-tab-journal');
        const screenerStats = document.getElementById('screener-stats-bar');
        const screenerGrid = document.querySelector('.screener-results .screener-grid-card:not(#backtest-view-card):not(#journal-view-card)');
        const backtestViewCard = document.getElementById('backtest-view-card');
        const journalViewCard = document.getElementById('journal-view-card');
        
        function deactivateAllTabs() {
            [tabScreener, tabBacktest, tabJournal].forEach(tab => {
                tab.classList.remove('active');
                tab.style.background = 'transparent';
                tab.style.color = 'var(--text-secondary)';
            });
            screenerStats.classList.add('hidden');
            screenerGrid.classList.add('hidden');
            backtestViewCard.classList.add('hidden');
            journalViewCard.classList.add('hidden');
        }

        tabScreener.addEventListener('click', () => {
            deactivateAllTabs();
            tabScreener.classList.add('active');
            tabScreener.style.background = 'rgba(255,255,255,0.05)';
            tabScreener.style.color = 'var(--text-primary)';
            
            screenerStats.classList.remove('hidden');
            screenerGrid.classList.remove('hidden');
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

    function init() {
        bindEvents();
        
        // Pre-fill fields from sessionStorage if already configured
        const savedKey = sessionStorage.getItem('zerodha_api_key');
        const savedToken = sessionStorage.getItem('zerodha_access_token');
        const savedGemini = sessionStorage.getItem('gemini_api_key');
        if (savedKey) document.getElementById('zerodha-api-key').value = savedKey;
        if (savedToken) document.getElementById('zerodha-access-token').value = savedToken;
        if (savedGemini) document.getElementById('gemini-api-key').value = savedGemini;

        if (typeof SERVER_HAS_ZERODHA !== 'undefined' && SERVER_HAS_ZERODHA) {
            document.getElementById('zerodha-api-key').placeholder = "Preconfigured in .env";
            document.getElementById('zerodha-access-token').placeholder = "Preconfigured in .env";
        }
        if (typeof SERVER_HAS_GEMINI !== 'undefined' && SERVER_HAS_GEMINI) {
            document.getElementById('gemini-api-key').placeholder = "Preconfigured in .env";
        }

        if (USER_STATUS !== 'guest') {
            syncJournalWithBackend();
        }

        // Start in Simulation Mode
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
