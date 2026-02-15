# transactions.py

import uuid
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

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

