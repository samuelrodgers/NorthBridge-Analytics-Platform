# noise.py
# Injects realistic data quality issues into clean transaction DataFrames.
# Used to test pipeline robustness and normalization logic.
#
# Usage:
#   from noise import apply_noise
#   clean_frame = generate_transactions(...)
#   noisy_frame = apply_noise(clean_frame, noise_level="medium")
from traceback import format_tb

import numpy as np
import pandas as pd
from datetime import datetime, timezone
import random
import logging
logger = logging.getLogger(__name__)

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
    if rate is None:
        rate = NOISE_RATES["timestamp_format"]

    df = df.copy()
    n_noisy = int(len(df) * rate)
    if n_noisy == 0:
        return df
    # Select random rows to apply noise
    noisy_indices = np.random.choice(df.index, size=n_noisy, replace=False)

    for idx in noisy_indices:
        # Sample a format
        format_idx = random.choices(range(len(TIMESTAMP_NOISE_WEIGHTS)), weights=TIMESTAMP_NOISE_WEIGHTS, k=1)[0]
        # We don't actually use the written formats for this part
        # format = TIMESTAMP_NOISE_FORMATS[format_idx]

        # Convert DataFrame datetime to selected format
        clean_time = df.loc[idx, "tx_timestamp"]
        match format_idx:
            case 0:
                dirty_time = clean_time.strftime("%m/%d/%Y %I:%M %p")
            case 1:
                dirty_time = clean_time.strftime("%d-%m-%Y %H:%M")
            case 2:
                excel_epoch = pd.Timestamp("1900-01-01", tz="UTC")
                days_since = (clean_time - excel_epoch).total_seconds() / 86400
                dirty_time = f"{days_since:.3f}"
            case 3:
                dirty_time = None
            case _:  # The default case (wildcard)
                dirty_time = clean_time
                logger.debug(f"Unknown format index {format_idx} for row {idx}, keeping clean")

        # Store back in df.loc[idx, "tx_timestamp"]
        df.loc[idx, "tx_timestamp"] = dirty_time

    return df


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
        rate = NOISE_RATES["currency_dirty"]

    df = df.copy()
    # Determine how many rows to make noisy
    n_noisy = int(len(df) * rate)
    if n_noisy == 0:
        return df

    # Select random rows to apply noise
    noisy_indices = np.random.choice(df.index, size=n_noisy, replace=False)

    # Build reverse lookup: ISO code -> list of dirty aliases
    # CURRENCY_ALIAS_MAP maps dirty -> clean, we need clean -> dirty
    iso_to_aliases = {}
    for dirty, clean in CURRENCY_ALIAS_MAP.items():
        if clean not in iso_to_aliases:
            iso_to_aliases[clean] = []
        iso_to_aliases[clean].append(dirty)

    # For each noisy row, replace the clean ISO code with a random alias
    for idx in noisy_indices:
        clean_code = df.loc[idx, "base_cncy"]

        # If this currency has aliases defined, pick one randomly
        if clean_code in iso_to_aliases:
            dirty_variant = random.choice(iso_to_aliases[clean_code])
            df.loc[idx, "base_cncy"] = dirty_variant

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
    if rate is None:
        rate = NOISE_RATES["amount_dirty"]

    df = df.copy()
    df["amount"] = df["amount"].astype(str)  # Convert all to string first
    # TODO: Implement amount formatting
    return df

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
    if rate_null is None:
        rate_null = NOISE_RATES["company_id_null"]
    if rate_name is None:
        rate_name = NOISE_RATES["company_id_name"]

    df = df.copy()
    # TODO: Implement company ID variants
    return df

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
    df = df.copy()
    # TODO: Implement fee variants
    return df

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
    df = df.copy()
    # TODO: For each unique c_id, apply that company's schema
    # This is complex — might need to group by company and rename separately
    return df

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
    df = df.copy()
    # TODO: Sample a different currency for base_cncy, set quote_cncy = "USD"
    return df

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
    scale = {"low": 0.5, "medium": 1.0, "high": 2.0}.get(noise_level, 1.0)

    # Apply noise in order
    df = inject_foreign_payments(df, rate=0.15 * scale)
    df = inject_timestamp_noise(df, rate=NOISE_RATES["timestamp_format"] * scale)
    df = inject_currency_noise(df, rate=NOISE_RATES["currency_dirty"] * scale)
    df = inject_amount_noise(df, rate=NOISE_RATES["amount_dirty"] * scale)
    df = inject_company_id_noise(df)
    df = inject_fee_noise(df)
    # df = inject_column_name_noise(df)  # TODO: This one is complex, defer

    return df

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