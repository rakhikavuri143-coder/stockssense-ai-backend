"""
Nifty 50 Indian Stocks Database - NSE/BSE Tickers with Sector Mapping
"""

NIFTY50_STOCKS = [
    {"symbol": "RELIANCE.NS",    "name": "Reliance Industries",          "sector": "Energy"},
    {"symbol": "TCS.NS",         "name": "Tata Consultancy Services",    "sector": "IT"},
    {"symbol": "HDFCBANK.NS",    "name": "HDFC Bank",                    "sector": "Banking"},
    {"symbol": "ICICIBANK.NS",   "name": "ICICI Bank",                   "sector": "Banking"},
    {"symbol": "INFY.NS",        "name": "Infosys",                      "sector": "IT"},
    {"symbol": "HINDUNILVR.NS",  "name": "Hindustan Unilever",           "sector": "FMCG"},
    {"symbol": "ITC.NS",         "name": "ITC Limited",                  "sector": "FMCG"},
    {"symbol": "SBIN.NS",        "name": "State Bank of India",          "sector": "Banking"},
    {"symbol": "BHARTIARTL.NS",  "name": "Bharti Airtel",                "sector": "Telecom"},
    {"symbol": "KOTAKBANK.NS",   "name": "Kotak Mahindra Bank",          "sector": "Banking"},
    {"symbol": "LT.NS",          "name": "Larsen & Toubro",              "sector": "Infrastructure"},
    {"symbol": "HCLTECH.NS",     "name": "HCL Technologies",             "sector": "IT"},
    {"symbol": "MARUTI.NS",      "name": "Maruti Suzuki",                "sector": "Auto"},
    {"symbol": "AXISBANK.NS",    "name": "Axis Bank",                    "sector": "Banking"},
    {"symbol": "SUNPHARMA.NS",   "name": "Sun Pharmaceutical",           "sector": "Pharma"},
    {"symbol": "BAJFINANCE.NS",  "name": "Bajaj Finance",                "sector": "Finance"},
    {"symbol": "ULTRACEMCO.NS",  "name": "UltraTech Cement",             "sector": "Cement"},
    {"symbol": "WIPRO.NS",       "name": "Wipro",                        "sector": "IT"},
    {"symbol": "M&M.NS",         "name": "Mahindra & Mahindra",          "sector": "Auto"},
    {"symbol": "TATAMOTORS.NS",  "name": "Tata Motors",                  "sector": "Auto"},
    {"symbol": "NTPC.NS",        "name": "NTPC",                         "sector": "Power"},
    {"symbol": "TITAN.NS",       "name": "Titan Company",                "sector": "Consumer"},
    {"symbol": "ASIANPAINT.NS",  "name": "Asian Paints",                 "sector": "Consumer"},
    {"symbol": "POWERGRID.NS",   "name": "Power Grid Corporation",       "sector": "Power"},
    {"symbol": "TATASTEEL.NS",   "name": "Tata Steel",                   "sector": "Metal"},
    {"symbol": "ADANIENT.NS",    "name": "Adani Enterprises",            "sector": "Conglomerate"},
    {"symbol": "ADANIPORTS.NS",  "name": "Adani Ports",                  "sector": "Logistics"},
    {"symbol": "COALINDIA.NS",   "name": "Coal India",                   "sector": "Mining"},
    {"symbol": "ONGC.NS",        "name": "Oil & Natural Gas Corporation", "sector": "Energy"},
    {"symbol": "LTIM.NS",        "name": "LTIMindtree",                  "sector": "IT"},
    {"symbol": "TECHM.NS",       "name": "Tech Mahindra",                "sector": "IT"},
    {"symbol": "GRASIM.NS",      "name": "Grasim Industries",            "sector": "Cement"},
    {"symbol": "BRITANNIA.NS",   "name": "Britannia Industries",         "sector": "FMCG"},
    {"symbol": "HDFCLIFE.NS",    "name": "HDFC Life Insurance",          "sector": "Insurance"},
    {"symbol": "CIPLA.NS",       "name": "Cipla",                        "sector": "Pharma"},
    {"symbol": "APOLLOHOSP.NS",  "name": "Apollo Hospitals",             "sector": "Healthcare"},
    {"symbol": "EICHERMOT.NS",   "name": "Eicher Motors",                "sector": "Auto"},
    {"symbol": "BPCL.NS",        "name": "Bharat Petroleum",             "sector": "Energy"},
    {"symbol": "TATACONSUM.NS",  "name": "Tata Consumer Products",       "sector": "FMCG"},
    {"symbol": "JSWSTEEL.NS",    "name": "JSW Steel",                    "sector": "Metal"},
    {"symbol": "DIVISLAB.NS",    "name": "Divi's Laboratories",          "sector": "Pharma"},
    {"symbol": "DRREDDY.NS",     "name": "Dr. Reddy's Laboratories",     "sector": "Pharma"},
    {"symbol": "INDUSINDBK.NS",  "name": "IndusInd Bank",                "sector": "Banking"},
    {"symbol": "HEROMOTOCO.NS",  "name": "Hero MotoCorp",                "sector": "Auto"},
    {"symbol": "HINDALCO.NS",    "name": "Hindalco Industries",          "sector": "Metal"},
    {"symbol": "NESTLEIND.NS",   "name": "Nestle India",                 "sector": "FMCG"},
    {"symbol": "BAJAJ-AUTO.NS",  "name": "Bajaj Auto",                   "sector": "Auto"},
    {"symbol": "SHRIRAMFIN.NS",  "name": "Shriram Finance",              "sector": "Finance"},
    {"symbol": "SBILIFE.NS",     "name": "SBI Life Insurance",           "sector": "Insurance"},
    {"symbol": "BEL.NS",         "name": "Bharat Electronics",           "sector": "Defence"},
]

# High-Volume Liquid Budget Stocks (under ₹200 on NSE)
# Scanned using the EXACT SAME 10 Capital Protection Guards!
BUDGET_LOW_PRICED_STOCKS = [
    {"symbol": "SUZLON.NS",     "name": "Suzlon Energy",                "sector": "Power"},
    {"symbol": "IDFCFIRSTB.NS", "name": "IDFC First Bank",              "sector": "Banking"},
    {"symbol": "PNB.NS",        "name": "Punjab National Bank",         "sector": "Banking"},
    {"symbol": "YESBANK.NS",    "name": "Yes Bank",                     "sector": "Banking"},
    {"symbol": "IRFC.NS",       "name": "Indian Railway Finance",       "sector": "Finance"},
    {"symbol": "NHPC.NS",       "name": "NHPC Limited",                 "sector": "Power"},
    {"symbol": "SAIL.NS",       "name": "Steel Authority of India",     "sector": "Metal"},
    {"symbol": "IOC.NS",        "name": "Indian Oil Corporation",       "sector": "Energy"},
    {"symbol": "GMRAIRPORT.NS", "name": "GMR Airports Infrastructure",  "sector": "Infrastructure"},
    {"symbol": "IDBI.NS",       "name": "IDBI Bank",                    "sector": "Banking"},
    {"symbol": "UCOBANK.NS",    "name": "UCO Bank",                     "sector": "Banking"},
    {"symbol": "UNIONBANK.NS",  "name": "Union Bank of India",          "sector": "Banking"},
    {"symbol": "HFCL.NS",       "name": "HFCL Limited",                 "sector": "Telecom"},
    {"symbol": "NBCC.NS",       "name": "NBCC India",                   "sector": "Infrastructure"},
    {"symbol": "SJVN.NS",       "name": "SJVN Limited",                 "sector": "Power"},
    {"symbol": "RCF.NS",        "name": "Rashtriya Chemicals",          "sector": "Chemicals"},
    {"symbol": "FEDERALBNK.NS", "name": "Federal Bank",                 "sector": "Banking"},
    {"symbol": "ETERNAL.NS",    "name": "Eternal (Zomato Limited)",     "sector": "Consumer"},
]

ALL_STOCKS = NIFTY50_STOCKS + BUDGET_LOW_PRICED_STOCKS
SECTORS = list(set(s["sector"] for s in ALL_STOCKS))

def get_all_symbols(include_budget: bool = True):
    stocks = ALL_STOCKS if include_budget else NIFTY50_STOCKS
    return [s["symbol"] for s in stocks]

def get_stock_by_symbol(symbol: str):
    for s in ALL_STOCKS:
        if s["symbol"].upper() == symbol.upper():
            return s
    return None

def get_stocks_by_sector(sector: str):
    return [s for s in ALL_STOCKS if s["sector"].lower() == sector.lower()]

# Nifty 50 Index ticker for market trend guard
NIFTY_INDEX_SYMBOL = "^NSEI"

