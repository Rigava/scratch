"""
Sector and Granular Sub-Industry Taxonomy for TradeKriya.
Maps all corporate constituents in Nifty 50 and F&O to standard Indian market sectors and sub-industries.
"""

SECTOR_TAXONOMY = {
    # --- Automobile & Auto Components ---
    "MARUTI": {"sector": "Automobile & Auto Components", "industry": "Passenger Vehicles (4-Wheelers)"},
    "TATAMOTORS": {"sector": "Automobile & Auto Components", "industry": "Commercial & Passenger Vehicles"},
    "M&M": {"sector": "Automobile & Auto Components", "industry": "Utility Vehicles & Farm Equipment"},
    "BAJAJ-AUTO": {"sector": "Automobile & Auto Components", "industry": "2 & 3 Wheelers"},
    "HEROMOTOCO": {"sector": "Automobile & Auto Components", "industry": "2 Wheelers"},
    "TVSMOTOR": {"sector": "Automobile & Auto Components", "industry": "2 & 3 Wheelers"},
    "EICHERMOT": {"sector": "Automobile & Auto Components", "industry": "Premium Motorcycles & Commercial"},
    "ASHOKLEY": {"sector": "Automobile & Auto Components", "industry": "Commercial Vehicles & Buses"},
    "ESCORTS": {"sector": "Automobile & Auto Components", "industry": "Agri Machinery & Construction"},
    "BOSCHLTD": {"sector": "Automobile & Auto Components", "industry": "Auto Ancillaries & Electronic Systems"},
    "APOLLOTYRE": {"sector": "Automobile & Auto Components", "industry": "Tyres & Rubber Products"},
    "MRF": {"sector": "Automobile & Auto Components", "industry": "Tyres & Rubber Products"},
    "EXIDEIND": {"sector": "Automobile & Auto Components", "industry": "Auto Storage Batteries"},

    # --- Banking & Financial Services (BFSI) ---
    "HDFCBANK": {"sector": "Banking & Financial Services", "industry": "Private Sector Bank"},
    "ICICIBANK": {"sector": "Banking & Financial Services", "industry": "Private Sector Bank"},
    "AXISBANK": {"sector": "Banking & Financial Services", "industry": "Private Sector Bank"},
    "KOTAKBANK": {"sector": "Banking & Financial Services", "industry": "Private Sector Bank"},
    "INDUSINDBK": {"sector": "Banking & Financial Services", "industry": "Private Sector Bank"},
    "BANDHANBNK": {"sector": "Banking & Financial Services", "industry": "Private Sector Bank - Microfinance"},
    "FEDERALBNK": {"sector": "Banking & Financial Services", "industry": "Private Sector Bank"},
    "IDFCFIRSTB": {"sector": "Banking & Financial Services", "industry": "Private Sector Bank"},
    "AUBANK": {"sector": "Banking & Financial Services", "industry": "Small Finance Bank"},
    "SBIN": {"sector": "Banking & Financial Services", "industry": "Public Sector Bank (PSU)"},
    "BANKBARODA": {"sector": "Banking & Financial Services", "industry": "Public Sector Bank (PSU)"},
    "PNB": {"sector": "Banking & Financial Services", "industry": "Public Sector Bank (PSU)"},
    "CANBK": {"sector": "Banking & Financial Services", "industry": "Public Sector Bank (PSU)"},
    "BAJFINANCE": {"sector": "Banking & Financial Services", "industry": "NBFC - Consumer & Retail Lending"},
    "BAJAJFINSV": {"sector": "Banking & Financial Services", "industry": "Financial Holding & Wealth Services"},
    "CHOLAFIN": {"sector": "Banking & Financial Services", "industry": "NBFC - Vehicle & Home Finance"},
    "MUTHOOTFIN": {"sector": "Banking & Financial Services", "industry": "NBFC - Gold Loans"},
    "LICHSGFIN": {"sector": "Banking & Financial Services", "industry": "Housing Finance"},
    "HDFCLIFE": {"sector": "Banking & Financial Services", "industry": "Life Insurance"},
    "SBILIFE": {"sector": "Banking & Financial Services", "industry": "Life Insurance"},
    "MFSL": {"sector": "Banking & Financial Services", "industry": "Life Insurance & Financial Services"},
    "PEL": {"sector": "Banking & Financial Services", "industry": "Diversified Financial Services"},
    "PFC": {"sector": "Banking & Financial Services", "industry": "Power Infrastructure Financing"},
    "RECLTD": {"sector": "Banking & Financial Services", "industry": "Power Infrastructure Financing"},

    # --- Information Technology ---
    "TCS": {"sector": "Information Technology", "industry": "IT Consulting & Enterprise Software"},
    "INFY": {"sector": "Information Technology", "industry": "IT Consulting & Digital Services"},
    "HCLTECH": {"sector": "Information Technology", "industry": "IT Services & Engineering R&D"},
    "WIPRO": {"sector": "Information Technology", "industry": "IT Services & Cloud Solutions"},
    "TECHM": {"sector": "Information Technology", "industry": "IT Services - Telecom & Enterprise"},
    "LTIM": {"sector": "Information Technology", "industry": "IT Consulting & Enterprise Solutions"},
    "PERSISTENT": {"sector": "Information Technology", "industry": "Software Product Engineering"},
    "COFORGE": {"sector": "Information Technology", "industry": "Digital Services - BFS & Travel"},
    "MPHASIS": {"sector": "Information Technology", "industry": "Cloud & Cognitive IT Solutions"},
    "OFSS": {"sector": "Information Technology", "industry": "Banking Financial Software Products"},

    # --- Pharmaceuticals & Healthcare ---
    "SUNPHARMA": {"sector": "Pharmaceuticals & Healthcare", "industry": "Specialty & Generic Pharmaceuticals"},
    "CIPLA": {"sector": "Pharmaceuticals & Healthcare", "industry": "Formulations & Respiratory Care"},
    "DRREDDY": {"sector": "Pharmaceuticals & Healthcare", "industry": "Generic APIs & Biosimilars"},
    "DIVISLAB": {"sector": "Pharmaceuticals & Healthcare", "industry": "Active Pharmaceutical Ingredients (API)"},
    "APOLLOHOSP": {"sector": "Pharmaceuticals & Healthcare", "industry": "Hospitals & Healthcare Services"},
    "LUPIN": {"sector": "Pharmaceuticals & Healthcare", "industry": "Generic Formulations & Biotech"},
    "GLENMARK": {"sector": "Pharmaceuticals & Healthcare", "industry": "Dermatology & Oncology Pharma"},
    "SYNGENE": {"sector": "Pharmaceuticals & Healthcare", "industry": "Contract Research (CRMO/CRAMS)"},
    "METROPOLIS": {"sector": "Pharmaceuticals & Healthcare", "industry": "Diagnostic Centers & Pathology"},

    # --- Oil, Gas & Consumable Fuels ---
    "RELIANCE": {"sector": "Oil, Gas & Energy", "industry": "Refining, Petrochemicals & Conglomerate"},
    "ONGC": {"sector": "Oil, Gas & Energy", "industry": "Oil & Gas Exploration & Production"},
    "BPCL": {"sector": "Oil, Gas & Energy", "industry": "Refining & Petroleum Marketing"},
    "IOC": {"sector": "Oil, Gas & Energy", "industry": "Refining & Petroleum Marketing"},
    "COALINDIA": {"sector": "Oil, Gas & Energy", "industry": "Coal Mining & Solid Fuels"},
    "IGL": {"sector": "Oil, Gas & Energy", "industry": "City Gas Distribution (CNG/PNG)"},
    "MGL": {"sector": "Oil, Gas & Energy", "industry": "City Gas Distribution (CNG/PNG)"},
    "PETRONET": {"sector": "Oil, Gas & Energy", "industry": "LNG Terminals & Regasification"},

    # --- Fast-Moving Consumer Goods (FMCG) ---
    "HINDUNILVR": {"sector": "Fast-Moving Consumer Goods (FMCG)", "industry": "Personal Care & Packaged Foods"},
    "ITC": {"sector": "Fast-Moving Consumer Goods (FMCG)", "industry": "Cigarettes, Foods & Agribusiness"},
    "NESTLEIND": {"sector": "Fast-Moving Consumer Goods (FMCG)", "industry": "Packaged Foods & Dairy Products"},
    "BRITANNIA": {"sector": "Fast-Moving Consumer Goods (FMCG)", "industry": "Bakery & Dairy Products"},
    "TATACONSUM": {"sector": "Fast-Moving Consumer Goods (FMCG)", "industry": "Tea, Coffee & Branded Foods"},
    "DABUR": {"sector": "Fast-Moving Consumer Goods (FMCG)", "industry": "Ayurvedic Healthcare & Personal Care"},
    "BALRAMCHIN": {"sector": "Fast-Moving Consumer Goods (FMCG)", "industry": "Sugar & Ethanol Biofuels"},
    "UBL": {"sector": "Fast-Moving Consumer Goods (FMCG)", "industry": "Breweries & Alcoholic Beverages"},

    # --- Metals & Mining ---
    "TATASTEEL": {"sector": "Metals & Mining", "industry": "Integrated Steel Production"},
    "JSWSTEEL": {"sector": "Metals & Mining", "industry": "Flat & Long Steel Products"},
    "HINDALCO": {"sector": "Metals & Mining", "industry": "Aluminium & Copper Products"},
    "JINDALSTEL": {"sector": "Metals & Mining", "industry": "Steel & Power Infrastructure"},
    "SAIL": {"sector": "Metals & Mining", "industry": "Public Sector Steel Production"},
    "NATIONALUM": {"sector": "Metals & Mining", "industry": "Bauxite, Alumina & Aluminium"},

    # --- Capital Goods & Engineering ---
    "LT": {"sector": "Capital Goods & Engineering", "industry": "Infrastructure EPC & Construction"},
    "SIEMENS": {"sector": "Capital Goods & Engineering", "industry": "Industrial Automation & Energy Systems"},
    "CUMMINSIND": {"sector": "Capital Goods & Engineering", "industry": "Diesel Engines & Power Gen"},
    "BHEL": {"sector": "Capital Goods & Engineering", "industry": "Heavy Electrical Equipment & Turbines"},
    "BEL": {"sector": "Capital Goods & Engineering", "industry": "Defense Electronics & Radars"},
    "HAL": {"sector": "Capital Goods & Engineering", "industry": "Aerospace & Defense Aircraft"},
    "HAVELLS": {"sector": "Capital Goods & Engineering", "industry": "Consumer Electricals & Lighting"},
    "VOLTAS": {"sector": "Capital Goods & Engineering", "industry": "Air Conditioning & Cooling Products"},
    "POLYCAB": {"sector": "Capital Goods & Engineering", "industry": "Wires, Cables & Fast Moving Electricals"},

    # --- Chemicals & Materials ---
    "PIDILITIND": {"sector": "Chemicals & Materials", "industry": "Adhesives, Sealants & Construction Chemicals"},
    "SRF": {"sector": "Chemicals & Materials", "industry": "Fluorochemicals & Specialty Packaging"},
    "DEEPAKNTR": {"sector": "Chemicals & Materials", "industry": "Phenolics & Basic Chemicals"},
    "NAVINFLUOR": {"sector": "Chemicals & Materials", "industry": "Specialty Fluorochemicals"},
    "GNFC": {"sector": "Chemicals & Materials", "industry": "Fertilizers & Industrial Chemicals"},
    "ASIANPAINT": {"sector": "Chemicals & Materials", "industry": "Decorative Paints & Home Coatings"},

    # --- Cement & Construction Materials ---
    "ULTRACEMCO": {"sector": "Cement & Construction Materials", "industry": "Grey Cement & Ready Mix Concrete"},
    "GRASIM": {"sector": "Cement & Construction Materials", "industry": "Viscose Staple Fibre, Chemicals & Cement"},
    "AMBUJACEM": {"sector": "Cement & Construction Materials", "industry": "Portland Cement & Building Solutions"},
    "SHREECEM": {"sector": "Cement & Construction Materials", "industry": "Cement & Clinker"},

    # --- Power & Utilities ---
    "NTPC": {"sector": "Power & Utilities", "industry": "Thermal & Renewable Power Generation"},
    "POWERGRID": {"sector": "Power & Utilities", "industry": "Electric Power Transmission Utility"},
    "TATAPOWER": {"sector": "Power & Utilities", "industry": "Integrated Power Generation & Solar EPC"},

    # --- Consumer Services, Retail & Media ---
    "TITAN": {"sector": "Consumer Services & Retail", "industry": "Jewellery, Watches & Eyewear"},
    "TRENT": {"sector": "Consumer Services & Retail", "industry": "Apparel & Lifestyle Retail (Westside/Zudio)"},
    "INDHOTEL": {"sector": "Consumer Services & Retail", "industry": "Luxury Hotels & Hospitality (Taj)"},
    "BATAINDIA": {"sector": "Consumer Services & Retail", "industry": "Footwear & Leather Goods"},
    "IRCTC": {"sector": "Consumer Services & Retail", "industry": "Railway Ticketing, Catering & Tourism"},
    "ZEEL": {"sector": "Consumer Services & Retail", "industry": "Media, Broadcasting & Entertainment"},

    # --- Telecommunication & Digital ---
    "BHARTIARTL": {"sector": "Telecommunication & Digital", "industry": "Wireless Telecom & Broadband Services"},
    "INDUSTOWER": {"sector": "Telecommunication & Digital", "industry": "Telecom Tower Infrastructure"},
    "TATACOMM": {"sector": "Telecommunication & Digital", "industry": "Global Network & Data Connectivity"},

    # --- Realty & Infrastructure Logistics ---
    "DLF": {"sector": "Realty & Infrastructure Logistics", "industry": "Commercial & Residential Real Estate"},
    "GODREJPROP": {"sector": "Realty & Infrastructure Logistics", "industry": "Residential Real Estate Development"},
    "OBEROIRLTY": {"sector": "Realty & Infrastructure Logistics", "industry": "Premium Real Estate & Mixed-Use"},
    "ADANIPORTS": {"sector": "Realty & Infrastructure Logistics", "industry": "Ports, SEZ & Marine Logistics"},
    "ADANIENT": {"sector": "Realty & Infrastructure Logistics", "industry": "Diversified Incubator & Infrastructure"},
    "CONCOR": {"sector": "Realty & Infrastructure Logistics", "industry": "Container Freight & Multi-Modal Rail"},
    "GMRINFRA": {"sector": "Realty & Infrastructure Logistics", "industry": "Airport Development & Transportation"}
}

ALL_SECTORS = sorted(list(set(item["sector"] for item in SECTOR_TAXONOMY.values())))

SECTOR_TO_INDUSTRIES = {}
for _sec in ALL_SECTORS:
    SECTOR_TO_INDUSTRIES[_sec] = sorted(list(set(item["industry"] for item in SECTOR_TAXONOMY.values() if item["sector"] == _sec)))

def get_stock_taxonomy(ticker):
    """
    Returns dict with 'sector' and 'industry' for a given ticker.
    Falls back to 'Diversified' if ticker is unknown.
    """
    if not ticker:
        return {"sector": "General", "industry": "General"}
    clean_ticker = ticker.strip().upper()
    return SECTOR_TAXONOMY.get(clean_ticker, {
        "sector": "Diversified",
        "industry": "Diversified Commercial"
    })

def get_all_sectors():
    """Returns sorted list of all unique sectors."""
    return ALL_SECTORS

def get_all_industries(sector=None):
    """Returns sorted list of all unique industries, optionally filtered by sector."""
    if sector and sector in SECTOR_TO_INDUSTRIES:
        return SECTOR_TO_INDUSTRIES[sector]
    if sector:
        return sorted(list(set(item["industry"] for item in SECTOR_TAXONOMY.values() if item["sector"] == sector)))
    return sorted(list(set(item["industry"] for item in SECTOR_TAXONOMY.values())))
