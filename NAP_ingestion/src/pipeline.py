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
    """Map any dirty column names → canonical names using CANONICAL_COLUMN_MAP."""
    rename = {col: CANONICAL_COLUMN_MAP[col] for col in df.columns if col in CANONICAL_COLUMN_MAP}
    if rename:
        logger.debug(f"Renaming columns: {rename}")
        df = df.rename(columns=rename)
    return df


# ── 0b: Timestamp parsing ─────────────────────────────────────────────────────

def _parse_single_timestamp(raw) -> pd.Timestamp | None:
    """
    Attempt to parse one raw timestamp value into a UTC pd.Timestamp.

    Handles:
    - Already a Timestamp / datetime → convert to UTC
    - ISO string and known format variants → strptime fallback chain
    - Excel serial float string (e.g. "45327.572") → days-since-epoch math
    - None / NaN → return None (quarantine downstream)
    - Timezone-naive datetime → return None (ambiguous, quarantine downstream)
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None

    # Already a datetime-like
    if isinstance(raw, (pd.Timestamp, datetime)):
        ts = pd.Timestamp(raw)
        if ts.tz is None:
            logger.warning(f"Timestamp has no timezone info, quarantining: {raw!r}")
            return None
        return ts.tz_convert("UTC")

    raw_str = str(raw).strip()

    # Excel serial: purely numeric (may have decimal), no alpha chars
    if re.fullmatch(r"\d{4,6}(\.\d+)?", raw_str):
        try:
            days = float(raw_str)
            return _EXCEL_EPOCH + pd.to_timedelta(days, unit="D")
        except Exception:
            pass

    # Multi-format strptime chain
    for fmt in TIMESTAMP_PARSE_ORDER:
        try:
            dt = datetime.strptime(raw_str, fmt)
            return pd.Timestamp(dt, tz="UTC") if dt.tzinfo is None else pd.Timestamp(dt).tz_convert("UTC")
        except ValueError:
            continue

    # Last resort: pandas infer
    try:
        ts = pd.to_datetime(raw_str, utc=True)
        return ts
    except Exception:
        logger.warning(f"Could not parse timestamp: {raw!r}")
        return None

def _parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Parse tx_timestamp column to UTC pd.Timestamp for every row."""
    df = df.copy()
    df["tx_timestamp"] = df["tx_timestamp"].apply(_parse_single_timestamp)
    return df


# ── 0c: Currency resolution ───────────────────────────────────────────────────

def _resolve_currency(raw) -> str | None:
    """
    Resolve a raw currency value to a canonical ISO code.

    Resolution order:
    1. Strip + upper → already a valid ISO code → return as-is
    2. Strip + lower → check CURRENCY_ALIAS_MAP
    3. Return None if unresolvable (quarantine downstream)
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None

    s = str(raw).strip()

    # Direct ISO match (most rows after strip+upper)
    upper = s.upper()
    if upper in CURRENCY_CODES:
        return upper

    # Alias map lookup (lowercase key)
    lower = s.lower()
    if lower in CURRENCY_ALIAS_MAP:
        return CURRENCY_ALIAS_MAP[lower]

    # Try the original string in alias map
    if s in CURRENCY_ALIAS_MAP:
        return CURRENCY_ALIAS_MAP[s]

    logger.warning(f"Unresolvable currency: {raw!r}")
    return None

def _resolve_currencies(df: pd.DataFrame) -> pd.DataFrame:
    """Apply _resolve_currency to base_cncy (and quote_cncy if present)."""
    df = df.copy()
    df["base_cncy"] = df["base_cncy"].apply(_resolve_currency)
    if "quote_cncy" in df.columns:
        df["quote_cncy"] = df["quote_cncy"].apply(
            lambda x: None if (x is None or (isinstance(x, float) and np.isnan(x))) else _resolve_currency(x)
        )
    return df

# ── 0d: Amount parsing ────────────────────────────────────────────────────────

def _parse_single_amount(raw) -> float | None:
    """
    Parse a raw amount string to float.

    Handles:
    - Already numeric → cast directly
    - Parentheses accounting negative: "(1200.50)" → -1200.50
    - Currency symbol prefix: "$1200.50" → 1200.50
    - Comma thousands: "1,200.50" → 1200.50
    - EU decimal: "1.200,50" → 1200.50
    - EU decimal < 1000: "12,50" → quarantine
    - Space thousands: "1 200.50" → 1200.50
    - Plain negative: "-1200.50" → -1200.50
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    if isinstance(raw, (int, float)):
        if raw < 0:
            return None  # Quarantine negatives
        return float(raw)

    s = str(raw).strip()

    # Strip currency symbols before any other checks
    s = re.sub(r"^[£$€¥₹\s]+", "", s).strip()

    # Accounting negative — quarantine
    if s.startswith("(") and s.endswith(")"):
        return None

    # Plain negative — quarantine
    if s.startswith("-"):
        return None

    # Ambiguous EU sub-1000: "99,00" — quarantine
    if "," in s and "." not in s:
        return None

    # Detect: has at least one comma and at least one period
    elif "," in s and "." in s:
        # Detect: comma comes first (standard format)
        if s.find(",") < s.find("."):
            s = s.replace(",", "").replace(" ", "")
        else:
            # This fixes the Euro format "1.234,56"
            s = s.replace(".", "").replace(",", ".")
    # The only case left is just a period or spaces — strip and parse
    s = s.replace(" ", "")

    try:
        return float(s)
    except ValueError:
        pass
    logger.warning(f"Could not parse amount: {raw!r}")
    return None

def _parse_amounts(df: pd.DataFrame) -> pd.DataFrame:
    """Parse amount column to float for every row."""
    df = df.copy()
    df["amount"] = df["amount"].apply(_parse_single_amount)
    return df


# ── 0e: Company ID resolution ─────────────────────────────────────────────────

def _resolve_company_id(raw) -> str | None:
    """
    Resolve a raw c_id value to a UUID string.

    Handles:
    - Already a valid UUID string → return as-is
    - Company name (clean, cased, whitespace variants) → UUID via COMPANY_NAME_TO_UUID
    - None / NaN → return None (quarantine downstream)
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None

    s = str(raw).strip()

    # Valid UUID → pass through
    try:
        _uuid.UUID(s)
        return s
    except ValueError:
        pass

    # Name lookup (normalize to upper for map key)
    upper = s.upper()
    if upper in COMPANY_NAME_TO_UUID:
        return COMPANY_NAME_TO_UUID[upper]

    logger.warning(f"Unresolvable company id: {raw!r}")
    return None


def _resolve_company_ids(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["c_id"] = df["c_id"].apply(_resolve_company_id)
    return df


# ── 0f: Fee parsing ───────────────────────────────────────────────────────────

def _parse_fee(row) -> float | None:
    """
    Resolve fee_amount for a single row.

    Handles:
    - None / NaN → 0.0 (missing fee assumed zero)
    - Percent string "2.5%" → compute against row's amount
    - Already numeric → cast to float
    - fee > amount → quarantine (return None)

    Args:
        row: a single DataFrame row (needs both fee_amount and amount)

    Returns:
        float if resolvable, None if fee exceeds amount (quarantine downstream)
    """
    raw = row.get("fee_amount")
    amount = row.get("amount")

    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return 0.0

    if isinstance(raw, str) and raw.strip().endswith("%"):
        try:
            pct = float(raw.strip().rstrip("%")) / 100.0
            base = float(amount) if amount is not None else 0.0
            fee = round(base * pct, 4)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse fee percent: {raw!r}")
            return 0.0
    else:
        try:
            fee = float(raw)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse fee: {raw!r}")
            return 0.0

    if amount is not None and fee > float(amount):
        logger.warning(f"Fee {fee} exceeds amount {amount}, quarantining")
        return None

    return fee

def _parse_fees(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fee_amount"] = df.apply(_parse_fee, axis=1)
    return df

# ── 0g: Final type coercion ───────────────────────────────────────────────────

def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Enforce expected dtypes for DB insert."""
    df = df.copy()
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="raise")
    if "fee_amount" in df.columns:
        df["fee_amount"] = pd.to_numeric(df["fee_amount"], errors="raise").fillna(0.0)
    return df


# ── QUARANTINE LOGIC ──────────────────────────────────────────────────────────

_REQUIRED_FIELDS = ["tx_timestamp", "base_cncy", "amount", "c_id"]

def _split_quarantine(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split DataFrame into clean and quarantined rows.

    A row is quarantined if ANY required field is null after normalization.
    Quarantined rows are tagged with a 'quarantine_reason' column describing
    which fields failed, so the caller can log or review them.

    Returns:
        (clean_df, quarantine_df)
    """
    reasons = []
    for _, row in df.iterrows():
        row_reasons = []
        for field in _REQUIRED_FIELDS:
            val = row.get(field)
            if val is None or pd.isna(val):
                row_reasons.append(f"null_{field}")
        reasons.append(", ".join(row_reasons) if row_reasons else "")

    df = df.copy()
    df["_quarantine_reason"] = reasons

    clean = df[df["_quarantine_reason"] == ""].drop(columns=["_quarantine_reason"])
    quarantine = df[df["_quarantine_reason"] != ""].rename(columns={"_quarantine_reason": "quarantine_reason"})

    return clean, quarantine


# ── PUBLIC ENTRY POINT ────────────────────────────────────────────────────────

def normalize_receipts(df: pd.DataFrame, collect_stats: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, dict | None]:
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
    logger.info(f"normalize_receipts: starting with {len(df):,} rows")
    df = df.copy()

    # Snapshot only taken when stats are requested
    original = df[["tx_timestamp", "base_cncy", "amount", "c_id"]].copy() if collect_stats else None

    df = _rename_columns(df)
    df = _parse_timestamps(df)
    df = _resolve_currencies(df)
    df = _parse_amounts(df)
    df = _resolve_company_ids(df)
    df = _parse_fees(df)
    df = _coerce_types(df)

    clean, quarantine = _split_quarantine(df)
    stats = _collect_stats(original, clean, quarantine) if collect_stats else None

    logger.info(
        f"normalize_receipts: {len(clean):,} clean rows, "
        f"{len(quarantine):,} quarantined rows"
    )

    return clean, quarantine, stats

# ── Stat tracking helpers for normalize_receipts() ────────────────────────────────────────────────────────

def validate_normalization_report(stats: dict) -> None:
    """
    Print a structured normalization quality report from stats returned
    by normalize_receipts().

    Sections:
        1 — Volume summary
        2 — Quarantine breakdown by reason
        3 — Field-level statistics on clean rows
        4 — Noise absorption summary
    """
    input_rows      = stats["input_rows"]
    clean_rows      = stats["clean_rows"]
    quarantine_rows = stats["quarantine_rows"]
    quarantine_rate = round(quarantine_rows / input_rows * 100, 2) if input_rows > 0 else 0.0

    print("\n" + "=" * 60)
    print("NORMALIZATION QUALITY REPORT")
    print("=" * 60)

    # ── Section 1 — Volume ────────────────────────────────────────────────
    print("\n--- Section 1: Volume Summary ---")
    print(f"  Input rows:       {input_rows:>8,}")
    print(f"  Clean rows:       {clean_rows:>8,}")
    print(f"  Quarantined rows: {quarantine_rows:>8,}")
    print(f"  Quarantine rate:  {quarantine_rate:>7.2f}%")

    # ── Section 2 — Quarantine breakdown ─────────────────────────────────
    print("\n--- Section 2: Quarantine Breakdown ---")
    reasons = stats.get("quarantine_reasons", {})
    if reasons:
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            pct = round(count / input_rows * 100, 2)
            print(f"  {reason:<25} {count:>6,}  ({pct:.2f}%)")
    else:
        print("  No quarantined rows.")

    # ── Section 3 — Field-level statistics ───────────────────────────────
    print("\n--- Section 3: Field-Level Statistics (clean rows) ---")

    amount_stats = stats.get("amount_stats", {})
    if amount_stats:
        print(f"  Amount (USD):")
        print(f"    Min:    {amount_stats['min']:>12,.2f}")
        print(f"    Median: {amount_stats['median']:>12,.2f}")
        print(f"    Mean:   {amount_stats['mean']:>12,.2f}")
        print(f"    Max:    {amount_stats['max']:>12,.2f}")

    fee_stats = stats.get("fee_stats", {})
    if fee_stats:
        print(f"  Fees:")
        print(f"    Rows with fee > 0: {fee_stats['rows_with_fee']:>6,}")
        print(f"    Mean fee (USD):    {fee_stats['mean_fee']:>10,.4f}")
        print(f"    Mean fee % of amt: {fee_stats['mean_fee_pct']:>9,.4f}%")

    cncy_dist = stats.get("cncy_distribution", {})
    if cncy_dist:
        print(f"  Currency distribution:")
        for cncy, count in sorted(cncy_dist.items(), key=lambda x: -x[1]):
            pct = round(count / clean_rows * 100, 2)
            print(f"    {cncy:<6} {count:>6,}  ({pct:.2f}%)")

    conversion_count = stats.get("conversion_count", 0)
    conversion_pct   = round(conversion_count / clean_rows * 100, 2) if clean_rows > 0 else 0.0
    print(f"  Conversion events: {conversion_count:>6,}  ({conversion_pct:.2f}% of clean rows)")

    # ── Section 4 — Noise absorption ─────────────────────────────────────
    print("\n--- Section 4: Noise Absorption (successfully parsed) ---")
    fields = [
        ("Timestamp variants", "timestamp_noise_absorbed"),
        ("Currency aliases",   "currency_noise_absorbed"),
        ("Amount formats",     "amount_noise_absorbed"),
        ("Company names",      "company_noise_absorbed"),
    ]
    for label, key in fields:
        count = stats.get(key, 0)
        pct   = round(count / input_rows * 100, 2) if input_rows > 0 else 0.0
        print(f"  {label:<22} {count:>6,}  ({pct:.2f}%)")

    print("\n" + "=" * 60)


def _collect_stats(original: pd.DataFrame, clean: pd.DataFrame, quarantine: pd.DataFrame) -> dict:
    """
    Compute normalization statistics from pre/post DataFrames.
    Called by normalize_receipts() after _split_quarantine().
    """
    # This function was generated by Claude and lightly reviewed
    # ── Section 2 — quarantine breakdown ─────────────────────────────────
    quarantine_reasons = {}
    if len(quarantine) > 0:
        for reason_str in quarantine["quarantine_reason"]:
            for reason in reason_str.split(", "):
                reason = reason.strip()
                if reason:
                    quarantine_reasons[reason] = quarantine_reasons.get(reason, 0) + 1

    # ── Section 3 — field-level statistics on clean rows ─────────────────
    amount_stats = {}
    fee_stats    = {}
    cncy_dist    = {}
    conversion_count = 0

    if len(clean) > 0:
        amounts = clean["amount"].dropna()
        amount_stats = {
            "min":    round(float(amounts.min()),    2),
            "median": round(float(amounts.median()), 2),
            "mean":   round(float(amounts.mean()),   2),
            "max":    round(float(amounts.max()),    2),
        }

        fees = clean["fee_amount"].dropna()
        fees_nonzero = fees[fees > 0]
        mean_fee     = round(float(fees_nonzero.mean()), 4) if len(fees_nonzero) > 0 else 0.0
        mean_fee_pct = round(float(
            (fees_nonzero / clean.loc[fees_nonzero.index, "amount"]).mean() * 100
        ), 4) if len(fees_nonzero) > 0 else 0.0
        fee_stats = {
            "rows_with_fee": int(len(fees_nonzero)),
            "mean_fee":      mean_fee,
            "mean_fee_pct":  mean_fee_pct,
        }

        cncy_dist        = clean["base_cncy"].value_counts().to_dict()
        conversion_count = int(clean["quote_cncy"].notna().sum()) if "quote_cncy" in clean.columns else 0

    # ── Section 4 — noise absorption ─────────────────────────────────────
    def _absorbed(orig_col, parsed_col):
        parsed = parsed_col.reindex(orig_col.index)
        return int(((parsed != orig_col) & parsed.notna()).sum())

    return {
        "input_rows":               len(original),
        "clean_rows":               len(clean),
        "quarantine_rows":          len(quarantine),
        "quarantine_reasons":       quarantine_reasons,
        "amount_stats":             amount_stats,
        "fee_stats":                fee_stats,
        "cncy_distribution":        cncy_dist,
        "conversion_count":         conversion_count,
        "timestamp_noise_absorbed": _absorbed(original["tx_timestamp"], clean["tx_timestamp"].reindex(original.index) if "tx_timestamp" in clean.columns else pd.Series(dtype=object)),
        "currency_noise_absorbed":  _absorbed(original["base_cncy"],    clean["base_cncy"].reindex(original.index)    if "base_cncy"    in clean.columns else pd.Series(dtype=object)),
        "amount_noise_absorbed":    _absorbed(original["amount"],       clean["amount"].reindex(original.index)       if "amount"       in clean.columns else pd.Series(dtype=object)),
        "company_noise_absorbed":   _absorbed(original["c_id"],         clean["c_id"].reindex(original.index)         if "c_id"         in clean.columns else pd.Series(dtype=object)),
    }

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
# This is just for validating the logic
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

    # Step 0: normalize
    clean_tx, quarantine, _ = normalize_receipts(tx_df)

    # Step 1: FX join
    matched = match_fx_rates(clean_tx, fx_df)
    if validate:
        validate_join(matched)

    # Step 2: amount normalization
    normalized = normalize_amounts(matched)
    if validate:
        validate_normalization(normalized)

    # Step 3: split
    f_transaction, f_conversion = split_to_analytics(normalized)
    if validate:
        validate_split(f_transaction, f_conversion)

    print(f"\n✅ Transform complete. ({len(quarantine):,} rows quarantined)")
    return f_transaction, f_conversion, quarantine