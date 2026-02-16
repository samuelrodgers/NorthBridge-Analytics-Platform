# transactions.py
# Generates synthetic transaction records aligned to raw.transaction_event schema.
#
# Column mapping to raw.transaction_event:
#   tx_id          → uuid (generated here, matches DB default gen_random_uuid())
#   c_id           → company uuid (uuid5-derived, matches analytics.d_company.c_id)
#   base_cncy      → customer payment currency (company default in clean data)
#   quote_cncy     → NULL if base_cncy == company default (no conversion needed)
#                    "USD" if base_cncy != company default (conversion required)
#   amount         → raw base currency amount (pre-conversion, pre-fee)
#   fee_amount     → fee in base currency
#   tx_timestamp   → timestamptz, UTC

import uuid
import numpy as np
import pandas as pd

from config import COMPANIES, COMPANY_KEYS, COMPANY_WEIGHTS


def generate_transactions(
    start_ts,
    end_ts,
    n_transactions=10_000,
    seed=42
):
    """
    Generate a DataFrame of synthetic transactions.

    Args:
        start_ts:       datetime — start of the transaction window
        end_ts:         datetime — end of the transaction window
        n_transactions: int — number of rows to generate
        seed:           int — random seed for reproducibility

    Returns:
        pd.DataFrame with columns matching raw.transaction_event
    """
    rng = np.random.default_rng(seed)

    # ── Timestamps ────────────────────────────────────────────────────────────
    # Sample uniformly across the window, then apply business-hours weighting
    timestamps = pd.date_range(start_ts, end_ts, freq="s")
    raw_times = rng.choice(timestamps, size=n_transactions, replace=True)

    hours = pd.DatetimeIndex(raw_times).hour
    weights = np.where((hours >= 9) & (hours <= 17), 3.0, 1.0)
    weights /= weights.sum()
    tx_times = rng.choice(raw_times, size=n_transactions, replace=True, p=weights)

    # Ensure timezone-aware UTC to match timestamptz in DB.
    # date_range inherits tz from start_ts if tz-aware; normalize either way.
    tx_index = pd.DatetimeIndex(tx_times)
    if tx_index.tz is None:
        tx_times = tx_index.tz_localize("UTC")
    else:
        tx_times = tx_index.tz_convert("UTC")

    # ── Companies + default currency ─────────────────────────────────────────
    # Sample short keys, then resolve to c_uuid (DB column) and default_cncy.
    # uuid5 derivation is in config — deterministic, no hardcoding needed.
    sampled_keys = rng.choice(COMPANY_KEYS, size=n_transactions, p=COMPANY_WEIGHTS)

    c_uuids = np.array([COMPANIES[k]["c_uuid"]       for k in sampled_keys])
    base_currencies = np.array([COMPANIES[k]["default_cncy"] for k in sampled_keys])

    # ── Amounts ───────────────────────────────────────────────────────────────
    # Log-normal gives realistic fat-tailed financial amounts.
    # mean=4, sigma=1 → median ~$55, mean ~$90, occasional large transactions
    base_amounts = rng.lognormal(mean=4, sigma=1, size=n_transactions).round(4)

    # Fee as small % of base amount, varies by transaction
    fee_rates = rng.uniform(0.001, 0.01, size=n_transactions)
    fee_amounts = (base_amounts * fee_rates).round(4)

    # ── UUIDs ─────────────────────────────────────────────────────────────────
    # Generate here so tx_id is available in Python for cross-table linking.
    # DB also has gen_random_uuid() as default, but explicit is safer for bulk inserts.
    tx_ids = [str(uuid.uuid4()) for _ in range(n_transactions)]

    # ── Quote currency ────────────────────────────────────────────────────────
    # quote_cncy is NULL when the customer pays in the company's own currency —
    # no conversion event occurs. It is "USD" only when base_cncy differs from
    # the company default, meaning a real currency conversion is needed.
    # In clean generated data base_cncy always equals the company default,
    # so quote_cncy will always be NULL here. Noise injection will later
    # introduce foreign payment currencies to produce conversion events.
    company_defaults = np.array([COMPANIES[k]["default_cncy"] for k in sampled_keys])
    quote_currencies = np.where(base_currencies != company_defaults, "USD", None)

    df = pd.DataFrame({
        "tx_id":        tx_ids,
        "c_id":         c_uuids,
        "base_cncy":    base_currencies,
        "quote_cncy":   quote_currencies,   # NULL = no conversion, "USD" = convert
        "amount":       base_amounts,
        "fee_amount":   fee_amounts,
        "tx_timestamp": tx_times,
    })

    return df