# noise.py
# Injects realistic data quality issues into clean transaction DataFrames.
# Used to test pipeline robustness and normalization logic.
#
# Usage:
#   from noise import apply_noise
#   clean_frame = generate_transactions(...)
#   noisy_frame = apply_noise(clean_frame, noise_level="medium")

import numpy as np
import pandas as pd
from datetime import datetime, timezone
import random

from config import (
    CURRENCY_ALIAS_MAP,
    COMPANY_NAME_TO_UUID,
    COMPANY_COLUMN_SCHEMAS,
    NOISE_RATES,
    AMOUNT_NOISE_FORMATS,
    AMOUNT_NOISE_WEIGHTS,
    TIMESTAMP_NOISE_FORMATS,
    TIMESTAMP_NOISE_WEIGHTS,
)


# ============================================================
# NOISE INJECTION — TIMESTAMPS
# ============================================================

def inject_timestamp_noise(df, rate=None):
    """
    Replace clean ISO timestamps with format variants.

    Formats injected (from config.TIMESTAMP_NOISE_FORMATS):
    - ISO (clean baseline): "2026-02-14 13:45:00"
    - US format: "02/14/2026 1:45 PM"
    - EU format: "14-02-2026 13:45"
    - Excel serial: "44589.572" (days since 1900-01-01)
    - Null (missing timestamp)

    Args:
        df: DataFrame with 'tx_timestamp' column
        rate: fraction of rows to make noisy (default: NOISE_RATES["timestamp_format"])

    Returns:
        DataFrame with noisy timestamps (still in object dtype, not datetime)
    """
    pass


# ============================================================
# NOISE INJECTION — CURRENCIES
# ============================================================

def inject_currency_noise(df, rate=None):
    """
    Replace clean ISO currency codes with aliases/variants.

    Variants injected (from config.CURRENCY_ALIAS_MAP):
    - Lowercase: "usd" instead of "USD"
    - Full name: "US Dollars" instead of "USD"
    - Symbols: "$" instead of "USD"
    - Misspellings: "U.S.D." instead of "USD"

    Args:
        df: DataFrame with 'base_cncy' column
        rate: fraction of rows to make noisy

    Returns:
        DataFrame with dirty currency codes
    """
    if rate is None:
        rate = NOISE_RATES["timestamp_format"]

    df = df.copy()
    n_noisy = int(len(df) * rate)
    noisy_indices = np.random.choice(df.index, size=n_noisy, replace=False)

    # TODO: Implement timestamp format conversion
    # For each noisy index:
    #   - Sample a format from TIMESTAMP_NOISE_FORMATS with TIMESTAMP_NOISE_WEIGHTS
    #   - Convert the datetime to that format string
    #   - Store back in df.loc[idx, "tx_timestamp"]

    return df

# ============================================================
# NOISE INJECTION — AMOUNTS
# ============================================================

def inject_amount_noise(df, rate=None):
    """
    Format clean float amounts as dirty strings.

    Formats injected:
    - Comma thousands: "1,200.50"
    - EU decimal: "1.200,50"
    - Space thousands: "1 200.50"
    - Negative (refunds): "-1200.50"
    - Parentheses (accounting): "(1200.50)"
    - With symbol: "$1200.50"

    Args:
        df: DataFrame with 'amount' column
        rate: fraction of rows to make noisy

    Returns:
        DataFrame with 'amount' as string (mixed clean/dirty)
    """
    pass

# ============================================================
# NOISE INJECTION — COMPANY IDs
# ============================================================

def inject_company_id_noise(df, rate_null=None, rate_name=None):
    """
    Replace clean UUIDs with nulls or company names.

    Variants:
    - Null: None
    - Name instead of UUID: "Orion Systems" instead of uuid
    - Name with whitespace: " Orion Systems "
    - Name with wrong casing: "orion systems"

    Args:
        df: DataFrame with 'c_id' column (UUIDs)
        rate_null: fraction to set to null
        rate_name: fraction to replace with company name

    Returns:
        DataFrame with dirty c_id column (mixed types)
    """
    pass

# ============================================================
# NOISE INJECTION — FEES
# ============================================================

def inject_fee_noise(df):
    """
    Apply noise to fee_amount column.

    Variants:
    - Missing (null)
    - As percent string: "2%"
    - Negative: -12.50
    - Bundled into base amount (set fee to 0, add fee to amount)

    Returns:
        DataFrame with dirty fee column
    """
    pass

# ============================================================
# NOISE INJECTION — COLUMN NAMES
# ============================================================

def inject_column_name_noise(df):
    """
    Rename columns to company-specific schemas.

    Uses COMPANY_COLUMN_SCHEMAS from config to map canonical names
    to company-specific variants (e.g., "tx_timestamp" → "tx_time").

    Args:
        df: DataFrame with canonical column names

    Returns:
        DataFrame with renamed columns (schema varies by company)
    """
    pass

# ============================================================
# NOISE INJECTION — FOREIGN PAYMENT CURRENCIES
# ============================================================

def inject_foreign_payments(df, rate=0.15):
    """
    Introduce transactions where customer pays in a currency different
    from the company's default — triggering real conversion events.

    For a fraction of rows:
    - Keep base_cncy as-is (company default)
    - Set a different payment_cncy (what customer actually paid)
    - Set quote_cncy = "USD" (conversion needed)

    This creates rows where raw.transaction_event.quote_cncy IS NOT NULL,
    triggering f_conversion inserts and the apply_conversion() trigger.

    Args:
        df: DataFrame with 'base_cncy', 'quote_cncy' columns
        rate: fraction of rows to convert to foreign payments

    Returns:
        DataFrame with quote_cncy set for foreign payments
    """
    pass

# ============================================================
# MAIN NOISE APPLICATION
# ============================================================

def apply_noise(df, noise_level="medium"):
    """
    Apply all noise injection functions to a clean DataFrame.

    Args:
        df: Clean DataFrame from generate_transactions()
        noise_level: "low", "medium", "high" — scales NOISE_RATES

    Returns:
        Noisy DataFrame ready to test pipeline robustness
    """
    pass

# ============================================================
# TESTING HARNESS
# ============================================================

if __name__ == "__main__":

    from datetime import timedelta
    from transactions import generate_transactions

    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=10)

    clean_frame = generate_transactions(start, end, n_transactions=100)
    noisy_frame = apply_noise(clean_frame, noise_level="medium")