# config.py

# ======= HARDCODED INFO ========= #


COMPANIES = {
    "US_TECH": ["Orion Systems", "BluePeak Analytics", "NexaData Corp"],
    "EU_RETAIL": ["AlpenMart GmbH", "Nordic Trade AB", "Louvre Commerce SARL"],
    "APAC_FINTECH": ["ZenPay Ltd", "Kumo Holdings", "Pacific Ledger Co"],
    "LATAM_SERVICES": ["Andes Logistics", "RioSoft Tecnologia", "Patagonia Digital"],
}
COMPANY_ID_MAP = {
    "ORION SYSTEMS": 101,
    "BLUEPEAK ANALYTICS": 102,
    "NEXADATA CORP": 103,
}
CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "AUD",
    "CAD", "CHF", "SEK", "NOK", "MXN",
    "BRL", "SGD", "HKD"
]
CURRENCY_ALIASES = {
    "usd": "USD",
    "US Dollars": "USD",
    "$": "USD",
    "eur": "EUR",
    "€": "EUR",
    "yen": "JPY",
}
PRODUCTS = {
    "SAAS_BASIC": {"mean_price": 50, "volatility": 10},
    "SAAS_PRO": {"mean_price": 200, "volatility": 40},
    "ENTERPRISE_LICENSE": {"mean_price": 5000, "volatility": 500},
    "API_USAGE": {"mean_price": 0.05, "volatility": 0.02},
    "CONSULTING_HOUR": {"mean_price": 150, "volatility": 30},
}