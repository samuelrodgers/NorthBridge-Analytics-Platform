import uuid
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# Makes transformations idempotent
random.seed(42)
np.random.seed(42)

# ======= HARDCODED INFO ========= #

companies = [
    {"id": "COMP1", "currency": "USD"},
    {"id": "COMP2", "currency": "AED"}
]

# ======= TIME-BASED FUNCTIONS ====== #

def generate_fx_series(
    start_time,
    end_time,
    base_cncy,
    quote_cncy,
    start_rate=1.10,
    interval_seconds=5
):
    timestamps = []
    rates = []

    current_rate = start_rate
    current_time = start_time

    while current_time <= end_time:
        shock = np.random.normal(0, 0.0002)
        current_rate *= (1 + shock)

        timestamps.append(current_time)
        rates.append(round(current_rate, 7))

        current_time += timedelta(seconds=interval_seconds)

    return pd.DataFrame({
        "event_timestamp": timestamps,
        "base_cncy": base_cncy,
        "quote_cncy": quote_cncy,
        "rate": rates
    })

def generate_transactions(n, start_time, end_time):
    rows = []

    for _ in range(n):
        company = random.choice(companies)

        event_time = start_time + timedelta(
            seconds=random.randint(0, int((end_time - start_time).total_seconds()))
        )

        base_cncy = random.choice(["USD", "EUR", "AED"])
        quote_cncy = company["currency"]

        base_amount = round(random.uniform(10, 500), 2)

        fee = round(base_amount * 0.01, 2)

        rows.append({
            "event_timestamp": event_time,
            "company_id": company["id"],
            "base_cncy": base_cncy,
            "quote_cncy": quote_cncy,
            "base_amount": base_amount,
            "fee_amount": fee
        })

    return pd.DataFrame(rows)

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
