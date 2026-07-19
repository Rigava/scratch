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
            sma: { enabled: true },
            rsi: { enabled: true, threshold: 30 },
            adx: { enabled: true, threshold: 25 },
            drawdown: { enabled: true, threshold: 30, years: 1 }
        },
        charts: {
            price: null,
            indicators: null
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

        const sma50 = calculateSMA(prices, 50);
        const sma200 = calculateSMA(prices, 200);
        const drawdownPeriod = (state.filters.drawdown.years || 1) * 250;
        const drawdown = calculateDrawdown(prices, drawdownPeriod);
        const rsi = calculateRSI(prices, 14);
        const adxData = calculateADX(candles, 14);

        stock.indicators = {
            sma50,
            sma200,
            drawdown,
            rsi,
            adx: adxData.adx,
            plusDI: adxData.plusDI,
            minusDI: adxData.minusDI
        };

        // Determine current status based on the latest day's values
        const lastIdx = candles.length - 1;
        stock.current = {
            price: prices[lastIdx],
            drawdown: drawdown[lastIdx],
            rsi: rsi[lastIdx],
            adx: adxData.adx[lastIdx],
            plusDI: adxData.plusDI[lastIdx],
            minusDI: adxData.minusDI[lastIdx],
            aboveSMA200: sma200[lastIdx] ? (prices[lastIdx] >= sma200[lastIdx]) : true
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

        for (const stock of Object.values(state.stocks)) {
            // Re-evaluate current status based on updated state filters
            processStockIndicators(stock);

            const matchesSearch = stock.ticker.toLowerCase().includes(query) || 
                                  stock.name.toLowerCase().includes(query);

            if (matchesSearch) {
                total++;
                if (stock.status === 'Knife') {
                    knives++;
                } else {
                    safe++;
                }

                // Render row
                const tr = document.createElement('tr');
                tr.setAttribute('data-ticker', stock.ticker);
                if (state.activeTicker === stock.ticker) {
                    tr.classList.add('selected');
                }

                const badgeClass = stock.status === 'Knife' ? 'badge-red' : 'badge-green';
                const icon = stock.status === 'Knife' ? '<i class="fa-solid fa-skull"></i>' : '<i class="fa-solid fa-circle-check"></i>';

                tr.innerHTML = `
                    <td><strong>${stock.ticker}</strong></td>
                    <td>
                        <strong>${stock.ticker}</strong>
                        <span class="symbol-name">${stock.name}</span>
                    </td>
                    <td>₹${stock.current.price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    <td class="${stock.current.drawdown > state.filters.drawdown.threshold && state.filters.drawdown.enabled ? 'text-red' : ''}">${stock.current.drawdown}%</td>
                    <td class="${stock.current.rsi < state.filters.rsi.threshold && state.filters.rsi.enabled ? 'text-red' : ''}">${stock.current.rsi ?? '-'}</td>
                    <td>${stock.current.adx ?? '-'}</td>
                    <td><span class="badge ${badgeClass}">${icon} ${stock.status}</span></td>
                `;

                // Set click handler
                tr.addEventListener('click', () => {
                    openDetailDrawer(stock.ticker);
                });

                tbody.appendChild(tr);
            }
        }

        // Update statistics
        document.getElementById('stat-total').innerText = total;
        document.getElementById('stat-knives').innerText = knives;
        document.getElementById('stat-safe').innerText = safe;
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
                        borderColor: '#f9fafb',
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
                        borderColor: '#6366f1',
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
                        ticks: { color: '#6b7280', maxTicksLimit: 8 }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#6b7280' }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: '#f9fafb', boxWidth: 15, font: { family: 'Outfit' } }
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
                        ticks: { color: '#6b7280', maxTicksLimit: 8 }
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
                        labels: { color: '#f9fafb', boxWidth: 12, font: { family: 'Outfit' } }
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
        renderScreenerGrid();
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
        const lookupYears = state.filters.drawdown.years || 1;
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

            if (savedKey && savedToken) {
                // Pre-populate some index tickers
                fetchZerodhaData('RELIANCE');
                fetchZerodhaData('TCS');
                fetchZerodhaData('INFY');
            } else {
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

            document.getElementById('val-filter-rsi').innerText = '30';
            document.getElementById('val-filter-adx').innerText = '25';
            document.getElementById('val-filter-drawdown').innerText = '30%';

            state.filters = {
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

        // Start in Simulation Mode
        loadSimulationData();
    }

    return {
        init
    };
})();

// Bootstrap the application on page load
window.addEventListener('DOMContentLoaded', () => {
    App.init();
});
