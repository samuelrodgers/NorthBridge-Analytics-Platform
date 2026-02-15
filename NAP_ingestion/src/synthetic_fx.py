# synthetic_fx.py
# Generates synthetic FX rate time series for all currency pairs vs. USD.
# Start rates are read from config.CURRENCIES — single source of truth.

import numpy as np
import pandas as pd

from config import CURRENCIES


def generate_all_fx_series(start_ts, end_ts, currency_codes, quote="USD"):
    """
    Generate a FX rate DataFrame for every currency in currency_codes vs. quote.

    Args:
        start_ts:        datetime (UTC) — start of window
        end_ts:          datetime (UTC) — end of window
        currency_codes:  iterable of ISO currency code strings
        quote:           quote currency (default "USD")

    Returns:
        pd.DataFrame with columns: fx_timestamp, base_cncy, quote_cncy, rate
    """
    frames = []
    for i, ccy in enumerate(currency_codes):
        if ccy == quote:
            continue  # Skip USD↔USD

        start_rate = CURRENCIES[ccy]["fx_start_rate"]

        frames.append(
            generate_fx_series(
                start_ts, end_ts,
                base_cncy=ccy,
                quote_cncy=quote,
                start_rate=start_rate,
                seed=i   # Different seed per pair for independent paths
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
    """
    Generate a single GBM FX rate series at 5-second granularity.

    Args:
        start_ts:    datetime — start of window
        end_ts:      datetime — end of window
        base_cncy:   str — base currency ISO code
        quote_cncy:  str — quote currency ISO code
        start_rate:  float — starting exchange rate
        drift:       float — annualised drift (default 0)
        volatility:  float — per-step vol (default 0.0005)
        seed:        int   — random seed

    Returns:
        pd.DataFrame with columns: fx_timestamp, base_cncy, quote_cncy, rate
    """
    rng = np.random.default_rng(seed)

    timestamps = pd.date_range(start_ts, end_ts, freq="5s")
    n = len(timestamps)

    shocks = rng.normal(loc=drift, scale=volatility, size=n)
    rates = start_rate * np.exp(np.cumsum(shocks))

    return pd.DataFrame({
        "fx_timestamp": timestamps,
        "base_cncy":    base_cncy,
        "quote_cncy":   quote_cncy,
        "rate":         rates.round(7),   # matches raw.fx_rate numeric(14,7)
    })