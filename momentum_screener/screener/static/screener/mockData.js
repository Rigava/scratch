/**
 * Aegis Momentum - Mock Data Engine
 * Generates realistic 1-year daily historical candle data for simulated stocks.
 */

const MockDataEngine = (function() {
    // Generate dates for the last 250 trading days
    function generateTradingDates(count = 250) {
        const dates = [];
        let curr = new Date();
        // Go back in time, skipping weekends
        while (dates.length < count) {
            curr.setDate(curr.getDate() - 1);
            const day = curr.getDay();
            if (day !== 0 && day !== 6) { // Skip Sunday (0) and Saturday (6)
                // Format YYYY-MM-DD
                const yyyy = curr.getFullYear();
                const mm = String(curr.getMonth() + 1).padStart(2, '0');
                const dd = String(curr.getDate()).padStart(2, '0');
                dates.unshift(`${yyyy}-${mm}-${dd}`); // Oldest first
            }
        }
        return dates;
    }

    // Helper to generate simulated path with noise and trend
    function generatePath(dates, basePrice, type) {
        let price = basePrice;
        const data = [];
        const n = dates.length;

        for (let i = 0; i < n; i++) {
            let changePercent = 0;
            const noise = (Math.random() - 0.5) * 2; // -1 to 1

            switch (type) {
                case 'steady_growth': // Steady uptrend
                    changePercent = 0.15 + noise * 1.2; // Small positive drift
                    break;
                case 'terminal_decline': // Continuous downtrend
                    changePercent = -0.3 + noise * 1.5; // Negative drift
                    break;
                case 'turnaround': // Drops first, builds base, then starts recovering
                    if (i < 450) {
                        changePercent = -0.15 + noise * 1.5; // Slide
                    } else if (i < 600) {
                        changePercent = 0.0 + noise * 0.8; // Consolidation
                    } else {
                        changePercent = 0.5 + noise * 1.3; // Recovery
                    }
                    break;
                case 'volatile_crash': // Stable, then massive collapse and low base
                    if (i < 540) {
                        changePercent = 0.03 + noise * 1.0;
                    } else if (i >= 540 && i < 555) {
                        changePercent = -5.0 + noise * 3.0; // Fast drop
                    } else {
                        changePercent = -0.1 + noise * 2.0; // Volatile bottom
                    }
                    break;
                case 'healthy_correction': // Uptrend with a recent pullback
                    if (i < 630) {
                        changePercent = 0.08 + noise * 1.1;
                    } else if (i >= 630 && i < 705) {
                        changePercent = -0.4 + noise * 1.0; // Correction
                    } else {
                        changePercent = 0.4 + noise * 1.0; // Stabilizing
                    }
                    break;
                case 'sideways': // Oscillates around baseline
                    const deviation = price - basePrice;
                    const pull = -deviation * 0.05; // Mean reverting force
                    changePercent = pull + noise * 1.4;
                    break;
                case 'speculative_spike': // Flat, massive spike, and total bleedout
                    if (i < 300) {
                        changePercent = 0.0 + noise * 1.5;
                    } else if (i >= 300 && i < 330) {
                        changePercent = 5.0 + noise * 5.0; // Spike
                    } else {
                        changePercent = -1.0 + noise * 2.0; // Slow bleed
                    }
                    break;
            }

            // Apply price change
            price = price * (1 + changePercent / 100);
            if (price < 1) price = 1; // Floor price at 1

            // Simulated OHLC
            const dailyRange = price * (0.01 + Math.random() * 0.03);
            const openNoise = (Math.random() - 0.5) * dailyRange * 0.5;
            
            const close = Math.round(price * 100) / 100;
            const open = Math.round((close + openNoise) * 100) / 100;
            const high = Math.round(Math.max(open, close) + Math.random() * dailyRange * 0.5 * 100) / 100;
            const low = Math.round(Math.min(open, close) - Math.random() * dailyRange * 0.5 * 100) / 100;
            const volume = Math.floor(50000 + Math.random() * 950000);

            data.push({
                date: dates[i],
                open,
                high,
                low,
                close,
                volume
            });
        }
        return data;
    }

    const MOCK_TICKERS = {
        'AEROCORP': { name: 'AeroCorp Technologies', basePrice: 120, type: 'steady_growth' },
        'BIODYNE': { name: 'BioDyne Pharmaceuticals', basePrice: 220, type: 'terminal_decline' },
        'SOLARTECH': { name: 'SolarTech Solutions', basePrice: 150, type: 'turnaround' },
        'NEXUSIND': { name: 'Nexus Industries Ltd.', basePrice: 90, type: 'volatile_crash' },
        'KRONOS': { name: 'Kronos Financial Group', basePrice: 280, type: 'healthy_correction' },
        'TITANMIN': { name: 'Titan Mining Corp.', basePrice: 85, type: 'steady_growth' },
        'GENESIS': { name: 'Genesis Logistics', basePrice: 110, type: 'terminal_decline' },
        'ZEPHYR': { name: 'Zephyr Retail Group', basePrice: 65, type: 'sideways' },
        'OMNIMEDIA': { name: 'OmniMedia Network', basePrice: 140, type: 'volatile_crash' },
        'APEXSECU': { name: 'Apex Security Systems', basePrice: 100, type: 'turnaround' },
        'VORTEX': { name: 'Vortex Energy', basePrice: 180, type: 'terminal_decline' },
        'QUANTUM': { name: 'Quantum Computing Labs', basePrice: 50, type: 'speculative_spike' }
    };

    function getSimulatedData() {
        const dates = generateTradingDates(1250);
        const result = {};

        for (const [ticker, config] of Object.entries(MOCK_TICKERS)) {
            result[ticker] = {
                ticker: ticker,
                name: config.name,
                candles: generatePath(dates, config.basePrice, config.type)
            };
        }

        return result;
    }

    return {
        getSimulatedData
    };
})();
