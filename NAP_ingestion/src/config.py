# config.py
# Canonical reference data for synthetic ETL pipeline.
# Structure is designed for direct consumption by noise.py and pipeline.py.
# All lookup tables are dicts (O(1)) rather than lists — important at millions of rows.

import uuid as _uuid

# ============================================================
# COMPANIES
# ============================================================

# Master company registry — canonical short key is for human readability only.
# c_uuid is the actual DB identifier — deterministic uuid5 derived from the key.
# Same key always produces the same UUID across all runs and environments.
# Use this same namespace + key when seeding analytics.d_company.
#
# noise.py will inject: nulls, names instead of IDs, casing variants, whitespace.
# normalize_receipts() must trim + upper + map through COMPANY_NAME_TO_ID.

# Fixed namespace — do not change after first run or all UUIDs will rotate
_COMPANY_NS = _uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

def _company_uuid(key: str) -> str:
    """Deterministic UUID from company short key. Stable across runs."""
    return str(_uuid.uuid5(_COMPANY_NS, key))

COMPANIES = {
    # key   : { c_uuid, name, industry, hq_country, region, default_cncy, weight }
    # c_uuid    = DB identifier written to raw.transaction_event.c_id and analytics.d_company.c_id
    # industry  = required NOT NULL in analytics.d_company
    # hq_country= required NOT NULL in analytics.d_company
    "COMP001": {"c_uuid": _company_uuid("COMP001"), "name": "Orion Systems",        "industry": "Technology", "hq_country": "United States", "region": "US_TECH",        "default_cncy": "USD", "weight": 0.18},
    "COMP002": {"c_uuid": _company_uuid("COMP002"), "name": "BluePeak Analytics",   "industry": "Technology", "hq_country": "United States", "region": "US_TECH",        "default_cncy": "USD", "weight": 0.12},
    "COMP003": {"c_uuid": _company_uuid("COMP003"), "name": "NexaData Corp",        "industry": "Technology", "hq_country": "United States", "region": "US_TECH",        "default_cncy": "USD", "weight": 0.10},
    "COMP004": {"c_uuid": _company_uuid("COMP004"), "name": "AlpenMart GmbH",       "industry": "Retail",     "hq_country": "Germany",       "region": "EU_RETAIL",      "default_cncy": "EUR", "weight": 0.09},
    "COMP005": {"c_uuid": _company_uuid("COMP005"), "name": "Nordic Trade AB",      "industry": "Retail",     "hq_country": "Sweden",        "region": "EU_RETAIL",      "default_cncy": "SEK", "weight": 0.08},
    "COMP006": {"c_uuid": _company_uuid("COMP006"), "name": "Louvre Commerce SARL", "industry": "Retail",     "hq_country": "France",        "region": "EU_RETAIL",      "default_cncy": "EUR", "weight": 0.07},
    "COMP007": {"c_uuid": _company_uuid("COMP007"), "name": "ZenPay Ltd",           "industry": "Fintech",    "hq_country": "Singapore",     "region": "APAC_FINTECH",   "default_cncy": "SGD", "weight": 0.10},
    "COMP008": {"c_uuid": _company_uuid("COMP008"), "name": "Kumo Holdings",        "industry": "Fintech",    "hq_country": "Japan",         "region": "APAC_FINTECH",   "default_cncy": "JPY", "weight": 0.08},
    "COMP009": {"c_uuid": _company_uuid("COMP009"), "name": "Pacific Ledger Co",    "industry": "Fintech",    "hq_country": "Hong Kong",     "region": "APAC_FINTECH",   "default_cncy": "HKD", "weight": 0.06},
    "COMP010": {"c_uuid": _company_uuid("COMP010"), "name": "Andes Logistics",      "industry": "Logistics",  "hq_country": "Mexico",        "region": "LATAM_SERVICES", "default_cncy": "MXN", "weight": 0.05},
    "COMP011": {"c_uuid": _company_uuid("COMP011"), "name": "RioSoft Tecnologia",   "industry": "Technology", "hq_country": "Brazil",        "region": "LATAM_SERVICES", "default_cncy": "BRL", "weight": 0.04},
    "COMP012": {"c_uuid": _company_uuid("COMP012"), "name": "Patagonia Digital",    "industry": "Logistics",  "hq_country": "Argentina",     "region": "LATAM_SERVICES", "default_cncy": "USD", "weight": 0.03},
}

# Flat list of short keys — used internally for sampling
COMPANY_KEYS = list(COMPANIES.keys())

# Parallel weights — must stay in sync with COMPANY_KEYS
COMPANY_WEIGHTS = [COMPANIES[k]["weight"] for k in COMPANY_KEYS]

# Flat list of UUIDs — what actually gets written to the DB
# transactions.py samples from COMPANY_KEYS then resolves via COMPANIES[key]["c_uuid"]
COMPANY_IDS = [COMPANIES[k]["c_uuid"] for k in COMPANY_KEYS]

# Reverse lookup: normalized name → c_uuid
# Used by normalize_receipts() to recover c_id from injected name noise
COMPANY_NAME_TO_UUID = {
    v["name"].upper(): v["c_uuid"] for v in COMPANIES.values()
}
COMPANY_NAME_TO_UUID.update({
    "ORION SYSTEMS INC":  COMPANIES["COMP001"]["c_uuid"],
    "BLUEPEAK":           COMPANIES["COMP002"]["c_uuid"],
    "NEXADATA":           COMPANIES["COMP003"]["c_uuid"],
    "ALPENMART":          COMPANIES["COMP004"]["c_uuid"],
    "ZENPAY":             COMPANIES["COMP007"]["c_uuid"],
})


# ============================================================
# CURRENCIES
# ============================================================

# Master currency registry.
# noise.py will inject: lowercase, aliases, symbols, flipped base/quote, missing fields.
# normalize_receipts() must resolve through CURRENCY_ALIAS_MAP then validate against this set.

CURRENCIES = {
    "USD": {"name": "US Dollar",           "fx_start_rate": 1.0,    "region": "US"},
    "EUR": {"name": "Euro",                "fx_start_rate": 0.92,   "region": "EU"},
    "GBP": {"name": "British Pound",       "fx_start_rate": 0.79,   "region": "EU"},
    "JPY": {"name": "Japanese Yen",        "fx_start_rate": 149.5,  "region": "APAC"},
    "AUD": {"name": "Australian Dollar",   "fx_start_rate": 1.53,   "region": "APAC"},
    "CAD": {"name": "Canadian Dollar",     "fx_start_rate": 1.36,   "region": "US"},
    "CHF": {"name": "Swiss Franc",         "fx_start_rate": 0.89,   "region": "EU"},
    "SEK": {"name": "Swedish Krona",       "fx_start_rate": 10.4,   "region": "EU"},
    "NOK": {"name": "Norwegian Krone",     "fx_start_rate": 10.6,   "region": "EU"},
    "MXN": {"name": "Mexican Peso",        "fx_start_rate": 17.1,   "region": "LATAM"},
    "BRL": {"name": "Brazilian Real",      "fx_start_rate": 4.97,   "region": "LATAM"},
    "SGD": {"name": "Singapore Dollar",    "fx_start_rate": 1.34,   "region": "APAC"},
    "HKD": {"name": "Hong Kong Dollar",    "fx_start_rate": 7.82,   "region": "APAC"},
    "AED": {"name": "UAE Dirham",          "fx_start_rate": 3.67,   "region": "ME"},
}

# Flat set for O(1) membership checks in validation
CURRENCY_CODES = set(CURRENCIES.keys())

# Alias map — every dirty variant resolves to a canonical ISO code.
# noise.py draws from the keys; normalize_receipts() resolves them.
CURRENCY_ALIAS_MAP = {
    # USD variants
    "usd":         "USD",
    "us dollars":  "USD",
    "us dollar":   "USD",
    "$":           "USD",
    "u.s.d.":      "USD",
    "dollar":      "USD",
    # EUR variants
    "eur":         "EUR",
    "euro":        "EUR",
    "euros":       "EUR",
    "€":           "EUR",
    # GBP variants
    "gbp":         "GBP",
    "pound":       "GBP",
    "pounds":      "GBP",
    "£":           "GBP",
    "sterling":    "GBP",
    # JPY variants
    "jpy":         "JPY",
    "yen":         "JPY",
    "¥":           "JPY",
    # AUD variants
    "aud":         "AUD",
    "a$":          "AUD",
    "australian":  "AUD",
    # CAD variants
    "cad":         "CAD",
    "c$":          "CAD",
    "canadian":    "CAD",
    # CHF variants
    "chf":         "CHF",
    "franc":       "CHF",
    "francs":      "CHF",
    # SEK variants
    "sek":         "SEK",
    "krona":       "SEK",
    # NOK variants
    "nok":         "NOK",
    "krone":       "NOK",
    # MXN variants
    "mxn":         "MXN",
    "peso":        "MXN",
    # BRL variants
    "brl":         "BRL",
    "real":        "BRL",
    "reais":       "BRL",
    "r$":          "BRL",
    # SGD variants
    "sgd":         "SGD",
    "s$":          "SGD",
    # HKD variants
    "hkd":         "HKD",
    "hk$":         "HKD",
    # AED variants
    "aed":         "AED",
    "dirham":      "AED",
    "dirhams":     "AED",
}


# ============================================================
# PRODUCTS
# ============================================================

# Used for generating realistic base_amount distributions per product type.
# noise.py will inject: fee inside base_amount, percent-string fees, missing fees.

PRODUCTS = {
    "SAAS_BASIC":         {"mean_price": 50,   "volatility": 10,  "fee_rate": 0.005},
    "SAAS_PRO":           {"mean_price": 200,  "volatility": 40,  "fee_rate": 0.005},
    "ENTERPRISE_LICENSE": {"mean_price": 5000, "volatility": 500, "fee_rate": 0.003},
    "API_USAGE":          {"mean_price": 0.05, "volatility": 0.02,"fee_rate": 0.010},
    "CONSULTING_HOUR":    {"mean_price": 150,  "volatility": 30,  "fee_rate": 0.008},
}

PRODUCT_CODES = list(PRODUCTS.keys())


# ============================================================
# TIMESTAMP NOISE FORMATS
# ============================================================
# noise.py draws from TIMESTAMP_NOISE_FORMATS to replace clean ISO timestamps.
# normalize_receipts() must attempt each parser in TIMESTAMP_PARSE_ORDER.

TIMESTAMP_NOISE_FORMATS = [
    "{iso}",                  # clean baseline: "2026-02-14 13:45:00"
    "{mm}/{dd}/{yyyy} {h}:{mm_t} {ampm}",  # "02/14/2026 1:45 PM"
    "{dd}-{mm}-{yyyy} {HH}:{MM}",          # "14-02-2026 13:45"
    "{excel_serial}",                       # "44589.572"  (Excel float)
    None,                                   # null (small %)
]

# Weights for how often each format is injected (must sum to 1.0)
# Order matches TIMESTAMP_NOISE_FORMATS
TIMESTAMP_NOISE_WEIGHTS = [0.80, 0.07, 0.05, 0.03, 0.05]

# Ordered list of strptime format strings for multi-format parsing fallback
TIMESTAMP_PARSE_ORDER = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y %H:%M",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
]


# ============================================================
# AMOUNT NOISE FORMATS
# ============================================================
# noise.py uses these templates to format clean float amounts as dirty strings.
# normalize_receipts() must strip and parse back to float.

AMOUNT_NOISE_FORMATS = [
    "standard",         # 1200.50
    "comma_thousands",  # 1,200.50
    "eu_decimal",       # 1.200,50  (European locale)
    "space_thousands",  # 1 200.50
    "negative",         # -1200.50  (refund)
    "parentheses",      # (1200.50) (accounting negative)
    "with_symbol",      # $1200.50
]

AMOUNT_NOISE_WEIGHTS = [0.70, 0.10, 0.05, 0.03, 0.05, 0.03, 0.04]


# ============================================================
# COLUMN NAME SCHEMAS (per company profile)
# ============================================================
# Each company sends data with different column names.
# noise.py selects a schema per company_id and renames columns accordingly.
# normalize_receipts() maps back to canonical schema using CANONICAL_COLUMN_MAP.

COMPANY_COLUMN_SCHEMAS = {
    "COMP001": {
        "tx_timestamp": "tx_time",
        "company_id":   "company",
        "base_cncy":    "currency",
        "base_amount":  "amount",
        "fee_amount":   "fee",
    },
    "COMP004": {
        "tx_timestamp": "timestamp",
        "company_id":   "firm_id",
        "base_cncy":    "base_cncy",
        "base_amount":  "base_amount",
        "fee_amount":   "service_fee",
    },
    "COMP007": {
        "tx_timestamp": "date",
        "company_id":   "seller",
        "base_cncy":    "curr",
        "base_amount":  "gross_value",
        "fee_amount":   "charges",
    },
    # All other companies use canonical names by default
    "_default": {
        "tx_timestamp": "tx_timestamp",
        "company_id":   "company_id",
        "base_cncy":    "base_cncy",
        "base_amount":  "base_amount",
        "fee_amount":   "fee_amount",
    },
}

# Inverted: all known dirty column names → canonical name
# Auto-built from COMPANY_COLUMN_SCHEMAS so there's one place to update
CANONICAL_COLUMN_MAP = {}
for _schema in COMPANY_COLUMN_SCHEMAS.values():
    for canonical, dirty in _schema.items():
        CANONICAL_COLUMN_MAP[dirty] = canonical


# ============================================================
# NOISE INJECTION RATES
# ============================================================
# Top-level dials — adjust these to stress-test your pipeline harder or softer.
# noise.py reads these rather than hardcoding percentages inline.

NOISE_RATES = {
    "timestamp_format":  0.20,   # 20% of rows get a non-ISO timestamp
    "timestamp_null":    0.02,   # 2%  of rows get a null timestamp
    "currency_dirty":    0.10,   # 10% of rows get a currency alias/variant
    "amount_dirty":      0.15,   # 15% of rows get a formatted amount string
    "company_id_null":   0.03,   # 3%  of rows get null company_id
    "company_id_name":   0.04,   # 4%  of rows get company name instead of ID
    "fee_missing":       0.05,   # 5%  of rows have no fee
    "fee_as_percent":    0.03,   # 3%  of rows express fee as "2%"
    "fee_in_base":       0.02,   # 2%  of rows have fee bundled into base_amount
    "malformed_row":     0.05,   # 5%  of rows are structurally broken
    "missing_fields":    0.03,   # 3%  of rows have one or more fields dropped
    "source_dirty":      0.08,   # 8%  of rows get a dirty source variant
}


# ============================================================
# SOURCE VALUES
# ============================================================
# Clean source system names — used by transactions.py for generation.
# Weights control how often each source appears in clean data.
# noise.py injects dirty variants from SOURCE_NOISE_VARIANTS.

SOURCE_VALUES = {
    "api":           0.60,
    "manual_upload": 0.15,
    "batch_csv":     0.12,
    "sftp_feed":     0.08,
    "webhook":       0.05,
}

# Dirty variants noise.py can inject per canonical source value
SOURCE_NOISE_VARIANTS = {
    "api":           ["API", "Api", "api ", " api", None],
    "manual_upload": ["Manual Upload", "manual upload", "MANUAL_UPLOAD", "manual-upload"],
    "batch_csv":     ["Batch CSV", "batch_CSV", "batchcsv", "BATCH_CSV"],
    "sftp_feed":     ["SFTP", "sftp feed", "sftp-feed", "SFTPFeed"],
    "webhook":       ["Webhook", "WEBHOOK", "web_hook", "Web Hook"],
}