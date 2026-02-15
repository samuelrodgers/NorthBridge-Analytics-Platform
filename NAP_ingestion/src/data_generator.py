import uuid
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


# ======= HARDCODED INFO ========= #

companies = [
    {"id": "COMP1", "currency": "USD"},
    {"id": "COMP2", "currency": "AED"}
]
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
# ======= TIME-BASED FUNCTIONS ====== #

# Will replace this with exchangerate.host data
import pandas as pd
import numpy as np

def generate_fx_series(
    start_ts,
    end_ts,
    base_cncy,
    quote_cncy,
    start_rate,
    drift=0.0,
    volatility=0.0005,
    seed=42
):
    np.random.seed(seed)

    timestamps = pd.date_range(start_ts, end_ts, freq="5S")
    n = len(timestamps)

    dt = 1
    shocks = np.random.normal(loc=drift*dt,
                               scale=volatility*np.sqrt(dt),
                               size=n)

    log_returns = shocks
    rates = start_rate * np.exp(np.cumsum(log_returns))

    df = pd.DataFrame({
        "fx_timestamp": timestamps,
        "base_cncy": base_cncy,
        "quote_cncy": quote_cncy,
        "rate": rates
    })

    return df


def generate_transactions(
    start_ts,
    end_ts,
    companies,
    currencies,
    n_transactions=10000,
    seed=42
):
    np.random.seed(seed)

    timestamps = pd.date_range(start_ts, end_ts, freq="S")
    chosen_times = np.random.choice(timestamps, size=n_transactions)

    # heavier weight to business hours
    hours = pd.to_datetime(chosen_times).hour
    weights = np.where((hours >= 9) & (hours <= 17), 3, 1)
    weighted_idx = np.random.choice(
        range(n_transactions),
        size=n_transactions,
        p=weights/weights.sum()
    )

    tx_times = chosen_times[weighted_idx]

    company_ids = np.random.choice(
        companies,
        size=n_transactions,
        p=[0.5, 0.3, 0.2]
    )

    base_currencies = np.random.choice(
        currencies,
        size=n_transactions
    )

    quote_currency = "USD"

    base_amount = np.random.lognormal(
        mean=4,
        sigma=1,
        size=n_transactions
    )

    fee_amount = base_amount * np.random.uniform(0.001, 0.01, size=n_transactions)

    df = pd.DataFrame({
        "tx_timestamp": tx_times,
        "company_id": company_ids,
        "base_cncy": base_currencies,
        "quote_cncy": quote_currency,
        "base_amount": base_amount,
        "fee_amount": fee_amount
    })

    return df

# ====== CREATING NOISE / DATA VOLATILITY ===== #
# TODO - insert noise later
# seed = hash(company_name + batch_date) # For idempotent noise
# def apply_format_noise(df, company_profile):

# ====== CORRECTNESS ENFORCEMENT ===== #
# TODO - account for the noise I made
#def normalize_receipts(raw_df, company_profile)

def match_fx_rates(transactions_df, fx_df):
    transactions_df = transactions_df.sort_values("tx_timestamp")
    fx_df = fx_df.sort_values("fx_timestamp")

    merged = pd.merge_asof(
        transactions_df,
        fx_df,
        left_on="tx_timestamp",
        right_on="fx_timestamp",
        by=["base_cncy", "quote_cncy"],
        direction="backward"
    )

    return merged

# ====== TRANSFORMATIONS ====== #

def transform(transactions_df, fx_df):

    matched = match_fx_rates(transactions_df, fx_df)

    matched["normalized_amount_usd"] = np.where(
        matched["base_cncy"] == "USD",
        matched["base_amount"],
        matched["base_amount"] * matched["rate"]
    )

    f_transaction = matched[[
        "tx_timestamp",
        "company_id",
        "base_cncy",
        "base_amount",
        "normalized_amount_usd"
    ]].copy()

    f_conversion = matched[
        matched["base_cncy"] != "USD"
    ][[
        "tx_timestamp",
        "base_cncy",
        "rate"
    ]].copy()

    return f_transaction, f_conversion


# ====== MAIN ===== #

if __name__ == "__main__":
    s_time = datetime.now()
    e_time = s_time + timedelta(minutes=10)
    base = 'USD'
    quote = 'AED'
    s_rate = 3.67
    fx_frame = generate_fx_series(s_time, e_time, base, quote, s_rate)
    tx_frame = generate_transactions(30, s_time, e_time)
    print(fx_frame.head())
    print(tx_frame.head())
    print(tx_frame["base_cncy"].value_counts())
