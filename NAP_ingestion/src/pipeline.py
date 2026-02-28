# pipeline.py
# Validates and transforms raw FX + transaction data in Python.
# This logic will be translated to SQL once validated here.
#
# Three things we are validating:
#   1. merge_asof join — does every transaction get a rate?
#   2. NaN rates    — are any currency pairs missing FX coverage?
#   3. normalized_amount_usd — is the calculation correct for USD and non-USD?

import logging
import re
import uuid as _uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config import (
    CANONICAL_COLUMN_MAP,
    COMPANY_NAME_TO_UUID,
    CURRENCY_ALIAS_MAP,
    CURRENCY_CODES,
    TIMESTAMP_PARSE_ORDER,
)

logger = logging.getLogger(__name__)

# Excel epoch — days since 1900-01-01 (with Lotus 1-2-3 leap-year bug offset)
_EXCEL_EPOCH = pd.Timestamp("1899-12-30", tz="UTC")

# ============================================================
# STEP 0 — NORMALIZE RECEIPTS
# ============================================================
# Reverses all noise injected by noise.py and brings the DataFrame
# into a canonical, DB-ready state before any joins or transforms.
#
# Sub-steps (each isolated so failures are traceable):
#   0a. Rename columns         — map dirty column names → canonical names
#   0b. Parse timestamps       — multi-format fallback + Excel serial
#   0c. Resolve currencies     — alias map + upper + strip
#   0d. Parse amounts          — strip symbols/commas/parens → float
#   0e. Resolve company IDs    — names → UUIDs; drop unresolvable nulls
#   0f. Parse fees             — percent strings, bundled fees, nulls
#   0g. Final type coercion    — enforce expected dtypes for DB insert
#
# Rows that cannot be normalized are quarantined (returned separately)
# rather than silently dropped, so the caller can log/alert on them.

# ── 0a: Column renaming ───────────────────────────────────────────────────────

def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    pass


# ── 0b: Timestamp parsing ─────────────────────────────────────────────────────

def _parse_single_timestamp(raw) -> pd.Timestamp | None:
    pass

def _parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    pass


# ── 0c: Currency resolution ───────────────────────────────────────────────────

def _resolve_currency(raw) -> str | None:
    pass

def _resolve_currencies(df: pd.DataFrame) -> pd.DataFrame:
    pass


# ── 0d: Amount parsing ────────────────────────────────────────────────────────

def _parse_single_amount(raw) -> float | None:
    pass

def _parse_amounts(df: pd.DataFrame) -> pd.DataFrame:
    pass


# ── 0e: Company ID resolution ─────────────────────────────────────────────────

def _resolve_company_id(raw) -> str | None:
    pass

def _resolve_company_ids(df: pd.DataFrame) -> pd.DataFrame:
    pass


# ── 0f: Fee parsing ───────────────────────────────────────────────────────────

def _parse_fee(row) -> float:
    pass

def _parse_fees(df: pd.DataFrame) -> pd.DataFrame:
    pass


# ── 0g: Final type coercion ───────────────────────────────────────────────────

def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    pass


# ── QUARANTINE LOGIC ──────────────────────────────────────────────────────────

_REQUIRED_FIELDS = ["tx_timestamp", "base_cncy", "amount", "c_id"]

def _split_quarantine(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    pass


# ── PUBLIC ENTRY POINT ────────────────────────────────────────────────────────

def normalize_receipts(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Normalize a noisy transaction DataFrame into DB-ready canonical form.

    Applies all cleaning sub-steps in order:
      0a  rename_columns      — map dirty column names → canonical
      0b  parse_timestamps    — multi-format + Excel serial → UTC Timestamp
      0c  resolve_currencies  — aliases/symbols → ISO codes
      0d  parse_amounts       — formatted strings → float
      0e  resolve_company_ids — names → UUIDs
      0f  parse_fees          — percent strings / nulls → float
      0g  coerce_types        — enforce dtypes for DB insert

    Args:
        df: pd.DataFrame — noisy input (from apply_noise() or raw DB read)

    Returns:
        (clean_df, quarantine_df) — rows that passed all checks, rows that failed
    """
    pass



# ============================================================
# STEP 1 — FX JOIN
# ============================================================
# merge_asof is an ordered join. For each transaction timestamp,
# it finds the most recent FX rate that is <= that timestamp.
# This is the "backward" direction — we never use a future rate.
#
# The "by" parameter means: only match rows where base_cncy AND
# quote_cncy are identical in both DataFrames. A EUR transaction
# will only match a EUR/USD FX row, never a JPY/USD row.
#
# If no FX row exists before a transaction's timestamp, the rate
# will be NaN — this is what we check for in validate_join().

def match_fx_rates(tx_df, fx_df):
    """
    Join each transaction to the closest preceding FX rate.

    Args:
        tx_df:  pd.DataFrame — transactions (must have tx_timestamp, base_cncy, quote_cncy)
        fx_df:  pd.DataFrame — FX rates (must have fx_timestamp, base_cncy, quote_cncy, rate)

    Returns:
        pd.DataFrame — transactions with rate and fx_timestamp columns added
    """
    tx_df  = tx_df.sort_values("tx_timestamp").reset_index(drop=True)
    fx_df  = fx_df.sort_values("fx_timestamp").reset_index(drop=True)

    merged = pd.merge_asof(
        tx_df,
        fx_df[["fx_timestamp", "base_cncy", "quote_cncy", "rate"]],
        left_on="tx_timestamp",
        right_on="fx_timestamp",
        by=["base_cncy", "quote_cncy"],
        direction="backward"
    )

    return merged


def validate_join(matched_df):
    """
    VALIDATION 1 — inspect the join result row by row.
    Prints a report showing:
      - Total rows
      - How many got a rate vs. how many are NaN
      - Which currency pairs are missing rates (and why)
      - A sample of matched rows to verify the rate looks right
    """
    print("\n" + "="*60)
    print("VALIDATION 1: FX JOIN RESULTS")
    print("="*60)

    total       = len(matched_df)
    has_rate    = matched_df["rate"].notna().sum()
    missing     = matched_df["rate"].isna().sum()
    usd_rows    = (matched_df["base_cncy"].str.strip() == "USD").sum()
    non_usd     = total - usd_rows

    print(f"\nTotal rows:          {total:>8,}")
    print(f"USD transactions:    {usd_rows:>8,}  (no FX lookup needed)")
    print(f"Non-USD rows:        {non_usd:>8,}  (need FX rate)")
    print(f"Rows with rate:      {has_rate:>8,}")
    print(f"Rows missing rate:   {missing:>8,}")

    if missing > 0:
        print("\n⚠️  MISSING RATES — breakdown by currency pair:")
        missing_df = matched_df[matched_df["rate"].isna()]
        print(missing_df.groupby(["base_cncy", "quote_cncy"]).size()
                        .reset_index(name="missing_count")
                        .to_string(index=False))
        print("\n  Likely cause: transaction timestamp precedes first FX tick.")
        print("  In production SQL this becomes a LEFT JOIN gap — rows need")
        print("  to be quarantined or filled with a fallback rate.")
    else:
        print("\n✅ All non-USD rows matched to an FX rate.")

    print("\n--- Sample matched rows (non-USD) ---")
    sample = (matched_df[matched_df["base_cncy"].str.strip() != "USD"]
              [["tx_timestamp", "base_cncy", "quote_cncy", "amount", "rate", "fx_timestamp"]]
              .head(5))
    print(sample.to_string(index=False))

    # Show how close the FX timestamp is to the transaction timestamp
    non_usd_df = matched_df[
        (matched_df["base_cncy"].str.strip() != "USD") &
        matched_df["rate"].notna()
    ].copy()

    if len(non_usd_df) > 0:
        non_usd_df["lag_seconds"] = (
            non_usd_df["tx_timestamp"] - non_usd_df["fx_timestamp"]
        ).dt.total_seconds()

        print(f"\n--- FX rate lag (seconds between tx and matched FX tick) ---")
        print(f"  Mean:    {non_usd_df['lag_seconds'].mean():.1f}s")
        print(f"  Median:  {non_usd_df['lag_seconds'].median():.1f}s")
        print(f"  Max:     {non_usd_df['lag_seconds'].max():.1f}s")
        print(f"  (FX ticks every 5s — expect median ~2-3s)")


# ============================================================
# STEP 2 — NORMALIZATION
# ============================================================
# For USD transactions: normalized_amount = amount (no conversion needed)
# For non-USD:          normalized_amount = amount * rate
#
# rate is always expressed as: 1 unit of base_cncy = rate USD
# e.g. rate = 0.92 for EUR means 1 EUR = 0.92 USD
#
# The fee is NOT deducted here — that happens in the analytics DB
# via the apply_conversion() trigger when f_conversion is inserted.

def normalize_amounts(matched_df):
    """
    Add normalized_amount_usd column to matched DataFrame.

    For USD rows: pass amount through unchanged.
    For non-USD:  multiply amount by FX rate.
    Rows with NaN rate are flagged but kept — quarantine logic goes here later.
    """
    df = matched_df.copy()

    is_usd      = df["base_cncy"].str.strip() == "USD"
    has_rate    = df["rate"].notna()
    needs_conv  = ~is_usd & has_rate
    no_rate     = ~is_usd & ~has_rate

    df["normalized_amount_usd"] = np.where(
        is_usd,
        df["amount"],                       # USD: pass through
        np.where(
            has_rate,
            (df["amount"] * df["rate"]).round(4),  # non-USD: convert
            np.nan                          # no rate: flag for quarantine
        )
    )

    df["conversion_flag"] = np.select(
        [is_usd, needs_conv, no_rate],
        ["usd_passthrough", "converted", "missing_rate"],
        default="unknown"
    )

    return df


def validate_normalization(df):
    """
    VALIDATION 2 — verify the normalized_amount_usd calculation.
    Prints:
      - Breakdown by conversion_flag
      - Spot-check: manually verify 3 non-USD rows
      - Sanity check: USD rows should have identical amount and normalized_amount
    """
    print("\n" + "="*60)
    print("VALIDATION 2: NORMALIZATION RESULTS")
    print("="*60)

    print("\n--- Rows by conversion type ---")
    print(df["conversion_flag"].value_counts().to_string())

    # Spot-check: show calculation detail for a few non-USD rows
    print("\n--- Spot-check: non-USD conversion (verify: amount × rate = normalized) ---")
    sample = (df[df["conversion_flag"] == "converted"]
              [["base_cncy", "amount", "rate", "normalized_amount_usd"]]
              .head(5))
    print(sample.to_string(index=False))

    # Manual verification column
    sample = sample.copy()
    sample["manual_check"] = (sample["amount"] * sample["rate"]).round(4)
    sample["match"] = sample["manual_check"] == sample["normalized_amount_usd"]
    print("\n--- Manual verification (manual_check should equal normalized_amount_usd) ---")
    print(sample[["base_cncy", "normalized_amount_usd", "manual_check", "match"]].to_string(index=False))

    # USD passthrough check
    usd_rows = df[df["conversion_flag"] == "usd_passthrough"]
    usd_ok   = (usd_rows["amount"] == usd_rows["normalized_amount_usd"]).all()
    print(f"\n--- USD passthrough check ---")
    print(f"  All USD rows: amount == normalized_amount_usd → {'✅ PASS' if usd_ok else '❌ FAIL'}")

    # Distribution sanity
    print(f"\n--- normalized_amount_usd distribution (converted rows only) ---")
    conv = df[df["conversion_flag"] == "converted"]["normalized_amount_usd"]
    print(f"  Min:    {conv.min():>12.4f}")
    print(f"  Median: {conv.median():>12.4f}")
    print(f"  Mean:   {conv.mean():>12.4f}")
    print(f"  Max:    {conv.max():>12.4f}")


# ============================================================
# STEP 3 — SPLIT INTO ANALYTICS TABLES
# ============================================================
# This mirrors what the SQL batch transform will INSERT into:
#   f_transaction : one row per tx — tx_id, c_id, cncy, amount (post-conversion)
#   f_conversion  : one row per non-USD tx — links tx to fx rate used
#
# Note: f_transaction.amount in the DB is set by the apply_conversion()
# trigger AFTER f_conversion is inserted. Here in Python we compute it
# directly so we can validate the math before writing SQL.

def split_to_analytics(df):
    """
    Split matched+normalized DataFrame into analytics fact table shapes.

    Returns:
        f_transaction: pd.DataFrame
        f_conversion:  pd.DataFrame (non-USD rows only)
    """
    f_transaction = df[[
        "tx_id",
        "c_id",
        "base_cncy",
        "amount",
        "normalized_amount_usd",
        "tx_timestamp",
        "conversion_flag"
    ]].copy()

    f_conversion = df[df["conversion_flag"] == "converted"][[
        "tx_id",
        "amount",
        "fee_amount",
        "rate",
        "fx_timestamp",
        "base_cncy",
    ]].copy()
    f_conversion.rename(columns={"amount": "base_amount"}, inplace=True)

    return f_transaction, f_conversion


def validate_split(f_transaction, f_conversion):
    """
    VALIDATION 3 — verify the split looks right before SQL translation.
    """
    print("\n" + "="*60)
    print("VALIDATION 3: ANALYTICS TABLE SHAPES")
    print("="*60)

    print(f"\nf_transaction rows:  {len(f_transaction):,}")
    print(f"f_conversion rows:   {len(f_conversion):,}")
    print(f"\n  Every f_conversion row should have a matching f_transaction row.")

    tx_ids       = set(f_transaction["tx_id"])
    conv_tx_ids  = set(f_conversion["tx_id"])
    orphaned     = conv_tx_ids - tx_ids
    print(f"  Orphaned f_conversion rows (no parent tx): {len(orphaned)}")
    print(f"  → {'✅ PASS' if len(orphaned) == 0 else '❌ FAIL — investigate'}")

    print("\n--- f_transaction sample ---")
    print(f_transaction.head(3).to_string(index=False))

    print("\n--- f_conversion sample ---")
    print(f_conversion.head(3).to_string(index=False))


# ============================================================
# MAIN TRANSFORM — runs all three steps with validation
# ============================================================

def transform(tx_df, fx_df, validate=True):
    """
    Full pipeline: join → normalize → split.

    Args:
        tx_df:    pd.DataFrame — from generate_transactions()
        fx_df:    pd.DataFrame — from generate_all_fx_series()
        validate: bool — if True, print validation report at each step

    Returns:
        f_transaction: pd.DataFrame
        f_conversion:  pd.DataFrame
    """
    print("\n🔄 Starting pipeline transform...")
    print(f"   Input: {len(tx_df):,} transactions, {len(fx_df):,} FX rows")

    # Step 1: join
    matched = match_fx_rates(tx_df, fx_df)
    if validate:
        validate_join(matched)

    # Step 2: normalize
    normalized = normalize_amounts(matched)
    if validate:
        validate_normalization(normalized)

    # Step 3: split
    f_transaction, f_conversion = split_to_analytics(normalized)
    if validate:
        validate_split(f_transaction, f_conversion)

    print("\n✅ Transform complete.")
    return f_transaction, f_conversion