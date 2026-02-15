# synthetic_fx.py
import uuid
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

def generate_all_fx_series(start_ts, end_ts, currencies, quote="USD"):
    """Generate a FX series for every currency pair against the quote currency."""

    # Approximate starting rates vs USD
    START_RATES = {
        "EUR": 0.92, "GBP": 0.79, "JPY": 149.5, "AUD": 1.53,
        "CAD": 1.36, "CHF": 0.89, "SEK": 10.4, "NOK": 10.6,
        "MXN": 17.1, "BRL": 4.97, "SGD": 1.34, "HKD": 7.82,
        "AED": 3.67,
    }

    frames = []
    for i, ccy in enumerate(currencies):
        if ccy == quote:
            continue  # Skip USD↔USD
        frames.append(
            generate_fx_series(
                start_ts, end_ts,
                base_cncy=ccy,
                quote_cncy=quote,
                start_rate=START_RATES[ccy],
                seed=i  # Different seed per pair for independent paths
            )
        )

    return pd.concat(frames, ignore_index=True)

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

    timestamps = pd.date_range(start_ts, end_ts, freq="5s")
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

