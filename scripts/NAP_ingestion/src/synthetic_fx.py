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


def _auto_freq(window_seconds: float) -> str:
    """
    Pick a date_range frequency that keeps row count reasonable for any window.

    Target: ~10K–20K rows per currency pair regardless of window length.
        ≤ 1 day    →  5s    (~17K rows)
        ≤ 7 days   →  1min  (~10K rows)
        ≤ 30 days  →  15min (~2.9K rows)
        ≤ 365 days →  1h    (~730 rows/day is ~8.8K for a year)
        > 365 days →  4h    (keeps multi-year runs under ~5K rows/pair)
    """
    if window_seconds <= 86_400:
        return "5s"
    elif window_seconds <= 7 * 86_400:
        return "1min"
    elif window_seconds <= 30 * 86_400:
        return "15min"
    elif window_seconds <= 365 * 86_400:
        return "1h"
    else:
        return "4h"


def generate_fx_series(
    start_ts,
    end_ts,
    base_cncy,
    quote_cncy,
    start_rate,
    drift=0.0,
    volatility=0.0005,
    seed=42,
    freq=None,
):
    """
    Generate a single GBM FX rate series.

    Granularity is chosen automatically based on window length unless freq
    is passed explicitly. See _auto_freq() for the thresholds.

    Args:
        start_ts:    datetime — start of window
        end_ts:      datetime — end of window
        base_cncy:   str — base currency ISO code
        quote_cncy:  str — quote currency ISO code
        start_rate:  float — starting exchange rate
        drift:       float — annualised drift (default 0)
        volatility:  float — per-step vol (default 0.0005)
        seed:        int   — random seed
        freq:        str | None — pandas offset alias (e.g. "5s", "1h");
                     if None the frequency is chosen automatically

    Returns:
        pd.DataFrame with columns: fx_timestamp, base_cncy, quote_cncy, rate
    """
    rng = np.random.default_rng(seed)

    if freq is None:
        window_seconds = (pd.Timestamp(end_ts) - pd.Timestamp(start_ts)).total_seconds()
        freq = _auto_freq(window_seconds)

    timestamps = pd.date_range(start_ts, end_ts, freq=freq)
    n = len(timestamps)

    shocks = rng.normal(loc=drift, scale=volatility, size=n)
    rates = start_rate * np.exp(np.cumsum(shocks))

    return pd.DataFrame({
        "fx_timestamp": timestamps,
        "base_cncy":    base_cncy,
        "quote_cncy":   quote_cncy,
        "rate":         rates.round(7),   # matches raw.fx_rate numeric(14,7)
    })