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

    const NIFTY50_LIST = [
        "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", 
        "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BHARTIARTL", "BPCL", 
        "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY", 
        "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", 
        "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK", 
        "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT", 
        "LTIM", "M&M", "MARUTI", "NESTLEIND", "NTPC", 
        "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", 
        "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS", 
        "TECHM", "TITAN", "ULTRACEMCO", "WIPRO", "TRENT",
        "NIFTY 50", "NIFTY BANK", "NIFTY IT"
    ];

    const FO_LIST = [
        "AUBANK", "AMBUJACEM", "APOLLOTYRE", "ASHOKLEY", "BALRAMCHIN", 
        "BANDHANBNK", "BANKBARODA", "BATAINDIA", "BEL", "BHEL", 
        "BOSCHLTD", "CANBK", "CHOLAFIN", "COFORGE", "CONCOR", 
        "CUMMINSIND", "DABUR", "DEEPAKNTR", "DLF", "ESCORTS", 
        "EXIDEIND", "FEDERALBNK", "GLENMARK", "GMRINFRA", "GNFC", 
        "GODREJPROP", "HAL", "HAVELLS", "IDFCFIRSTB", "IGL", 
        "INDHOTEL", "INDUSTOWER", "IOC", "IRCTC", "JINDALSTEL", 
        "LICHSGFIN", "LUPIN", "METROPOLIS", "MFSL", "MGL", 
        "MPHASIS", "MRF", "MUTHOOTFIN", "NATIONALUM", "NAVINFLUOR", 
        "OBEROIRLTY", "OFSS", "PEL", "PERSISTENT", "PETRONET", 
        "PFC", "PIDILITIND", "PNB", "POLYCAB", "RECLTD", 
        "SAIL", "SHREECEM", "SIEMENS", "SRF", "SYNGENE", 
        "TATACOMM", "TATAPOWER", "TVSMOTOR", "UBL", "VOLTAS", "ZEEL"
    ];

    function getSimulatedData() {
        // Generate and return full universe combining Nifty 50 and F&O list
        return getSimulatedFO();
    }

    function generateSimulatedList(symbols) {
        const dates = generateTradingDates(1250);
        const result = {};
        
        const pathTypes = ['steady_growth', 'terminal_decline', 'volatile_crash', 'healthy_correction', 'sideways', 'speculative_spike'];
        
        symbols.forEach((sym) => {
            let charSum = 0;
            for (let i = 0; i < sym.length; i++) charSum += sym.charCodeAt(i);
            
            const basePrice = 100 + (charSum % 40) * 120;
            const type = pathTypes[charSum % pathTypes.length];
            
            let name = `${sym} Ltd.`;
            if (sym === 'NIFTY 50') name = 'Nifty 50 Index';
            else if (sym === 'NIFTY BANK') name = 'Nifty Bank Index';
            else if (sym === 'NIFTY IT') name = 'Nifty IT Index';
            else if (sym === 'RELIANCE') name = 'Reliance Industries Ltd.';
            else if (sym === 'TCS') name = 'Tata Consultancy Services Ltd.';
            else if (sym === 'INFY') name = 'Infosys Ltd.';
            else if (sym === 'HDFCBANK') name = 'HDFC Bank Ltd.';
            else if (sym === 'ICICIBANK') name = 'ICICI Bank Ltd.';
            else if (sym === 'SBIN') name = 'State Bank of India';
            else if (sym === 'BHARTIARTL') name = 'Bharti Airtel Ltd.';
            else if (sym === 'ITC') name = 'ITC Ltd.';
            else if (sym === 'LT') name = 'Larsen & Toubro Ltd.';
            else if (sym === 'HINDUNILVR') name = 'Hindustan Unilever Ltd.';
            else if (sym === 'AXISBANK') name = 'Axis Bank Ltd.';
            else if (sym === 'ASIANPAINT') name = 'Asian Paints Ltd.';
            else if (sym === 'M&M') name = 'Mahindra & Mahindra Ltd.';
            else if (sym === 'TATASTEEL') name = 'Tata Steel Ltd.';
            else if (sym === 'WIPRO') name = 'Wipro Ltd.';
            else if (sym === 'TATAMOTORS') name = 'Tata Motors Ltd.';
            
            result[sym] = {
                ticker: sym,
                name: name,
                candles: generatePath(dates, basePrice, type)
            };
        });
        
        return result;
    }

    function getSimulatedNifty50() {
        return generateSimulatedList(NIFTY50_LIST);
    }

    function getSimulatedFO() {
        // F&O combines Nifty 50 + extra F&O stocks
        const combined = [...new Set([...NIFTY50_LIST, ...FO_LIST])];
        return generateSimulatedList(combined);
    }

    return {
        getSimulatedData,
        getSimulatedNifty50,
        getSimulatedFO,
        generateSimulatedList,
        NIFTY50_LIST,
        FO_LIST
    };
})();
