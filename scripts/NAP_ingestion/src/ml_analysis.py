# ml_analysis.py
# ML analysis pipeline — query, preprocess, PCA.
# Runs independently from ml_main.py and main.py.
#
# Usage:
#   python ml_analysis.py
#
# Stages:
#   1. load_quarantine_features(conn) — SQL query → raw DataFrame
#   2. preprocess(df)                 — feature engineering → (X, y, df_meta)
#   3. run_pca(X, y, df_meta)         — PCA framework (structure only)

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from loader import get_connection


# ============================================================
# STAGE 1 — QUERY
# ============================================================

def load_quarantine_features(conn) -> pd.DataFrame:
    """
    Execute the feature query and return a raw DataFrame.

    One row per quarantine record. No derived features computed here —
    all transformations happen in preprocess().

    Join notes:
      - pipeline_run: LEFT JOIN so records from CRON runs (no pipeline_run
        row) are still included; noise_level etc. will be null for those.
      - d_company: LEFT JOIN because c_id is null for NULL_COMPANY_ID rows.
      - d_industry: dimension table (one row per industry). Joining
        analytics.f_industry here would be wrong — it has one row per
        industry per time period and would fan-out quarantine rows.

    """
    sql = """
        SELECT
            q.quarantine_id,
            q.failure_code,
            q.failure_count,
            q.tx_timestamp,
            q.ingestion_timestamp,
            q.amount,
            q.base_cncy,
            q.c_id,
            p.noise_level,
            p.clean_count,
            p.quarantine_count,
            d.default_cncy,
            d.hq_country,
            di.name                        AS industry_name
        FROM      raw.quarantine_event    q
        LEFT JOIN raw.pipeline_run        p  ON q.batch_id    = p.batch_id
        LEFT JOIN analytics.d_company     d  ON q.c_id        = d.c_id
        LEFT JOIN analytics.d_industry    di ON d.industry_id = di.industry_id
    """
    return pd.read_sql(sql, conn)


# ============================================================
# STAGE 2 — PREPROCESS
# ============================================================

def preprocess(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Transform the raw query DataFrame into model-ready (X, y, df_meta).

    Args:
        df: raw DataFrame from load_quarantine_features()

    Returns:
        X       -- normalized feature matrix, 25 columns
        y       -- failure_code Series (label)
        df_meta -- quarantine_id and company_known, for Analysis 2 splits
    """
    df = df.copy()

    # ── Labels and identifiers (not features) ────────────────────────────────
    y      = df["failure_code"]
    df_meta = df[["quarantine_id"]].copy()   # company_known added below

    # ── Step 1: Binary flags ──────────────────────────────────────────────────

    df["tx_timestamp_missing"] = df["tx_timestamp"].isna().astype(int)

    df["amount_is_valid"] = (
        df["amount"].notna() & (df["amount"] > 0)
    ).astype(int)

    df["company_known"] = df["c_id"].notna().astype(int)

    df["currency_mismatch"] = (
        df["base_cncy"].notna()
        & df["default_cncy"].notna()
        & (df["base_cncy"] != df["default_cncy"])
    ).astype(int)

    # Carry company_known into df_meta for PCA splits
    df_meta["company_known"] = df["company_known"]

    # ── Step 2: Continuous derived features ───────────────────────────────────

    # tx_ingestion_lag: seconds between transaction time and ingest time.
    # Only meaningful where tx_timestamp is present; null otherwise.
    # Null fallback (fill with 0) applied in Step 5.
    tx_ts   = pd.to_datetime(df["tx_timestamp"],    utc=True, errors="coerce")
    ingest  = pd.to_datetime(df["ingestion_timestamp"], utc=True, errors="coerce")
    df["tx_ingestion_lag"] = (ingest - tx_ts).dt.total_seconds()

    # batch_quarantine_rate: fraction of the batch that was quarantined.
    # Null where both counts are null (CRON runs with no pipeline_run row).
    total_batch = df["clean_count"] + df["quarantine_count"]
    df["batch_quarantine_rate"] = df["quarantine_count"] / total_batch.replace(0, np.nan)

    # hour_of_day and day_of_week: extracted from tx_timestamp.
    # Null where tx_timestamp is missing; fallback applied in Step 5.
    df["hour_of_day"]  = tx_ts.dt.hour.astype("Float64")
    df["day_of_week"]  = tx_ts.dt.dayofweek.astype("Float64")
    df.loc[df["tx_timestamp_missing"] == 1, ["hour_of_day", "day_of_week"]] = np.nan

    # ── Step 3: One-hot encode industry_name ──────────────────────────────────
    # fill null → "Unknown" so get_dummies doesn't drop the row silently,
    # then drop the Unknown column so nulls become all-zeros rows.
    industry_dummies = pd.get_dummies(
        df["industry_name"].fillna("__unknown__"),
        prefix="industry",
    )
    industry_dummies.columns = (
        industry_dummies.columns.str.lower().str.replace(" ", "_", regex=False)
    )
    if "industry___unknown__" in industry_dummies.columns:
        industry_dummies = industry_dummies.drop(columns=["industry___unknown__"])

    # ── Step 4: One-hot encode hq_country ────────────────────────────────────
    country_dummies = pd.get_dummies(
        df["hq_country"].fillna("__unknown__"),
        prefix="country",
    )
    country_dummies.columns = (
        country_dummies.columns.str.lower().str.replace(" ", "_", regex=False)
    )
    if "country___unknown__" in country_dummies.columns:
        country_dummies = country_dummies.drop(columns=["country___unknown__"])

    # ── Step 5: Null fallbacks before scaling ─────────────────────────────────
    df["tx_ingestion_lag"]    = df["tx_ingestion_lag"].fillna(0)
    df["hour_of_day"]         = df["hour_of_day"].fillna(df["hour_of_day"].median())
    df["day_of_week"]         = df["day_of_week"].fillna(df["day_of_week"].median())
    df["batch_quarantine_rate"] = df["batch_quarantine_rate"].fillna(
        df["batch_quarantine_rate"].mean()
    )
    industry_dummies = industry_dummies.fillna(0)
    country_dummies  = country_dummies.fillna(0)

    # Null amount means the value itself was the failure — semantically
    # equivalent to no valid amount present. Fill with 0. The amount_is_valid
    # flag already carries all the signal about whether the amount was bad.
    df["amount"] = df["amount"].fillna(0)

    # ── Step 6: Encode noise_level and scale continuous features ──────────────
    noise_map = {"low": 0, "medium": 1, "high": 2}
    df["noise_level"] = df["noise_level"].map(noise_map)
    # Null noise_level arises only for rows from CRON runs that have no
    # pipeline_run record. In this dataset all records were generated via
    # ml_main.py so this case does not occur — handled defensively with median.
    df["noise_level"] = df["noise_level"].fillna(df["noise_level"].median())

    features_to_scale = [
        "failure_count",
        "tx_ingestion_lag",
        "hour_of_day",
        "day_of_week",
        "noise_level",
        "batch_quarantine_rate",
        "amount",
    ]

    scaler = MinMaxScaler()
    df[features_to_scale] = scaler.fit_transform(df[features_to_scale])

    # ── Step 7: Assemble X — 25 features in canonical order ──────────────────

    # -- Temporal / count features
    temporal = df[["failure_count", "tx_ingestion_lag",
                   "tx_timestamp_missing", "hour_of_day", "day_of_week"]]

    # -- Batch metadata features
    batch = df[["noise_level", "batch_quarantine_rate"]]

    # -- Industry one-hot (4 columns — alphabetical)
    industry_cols = sorted([c for c in industry_dummies.columns])
    industry = industry_dummies[industry_cols]

    # -- Country one-hot (10 columns — alphabetical)
    country_cols = sorted([c for c in country_dummies.columns])
    country = country_dummies[country_cols]

    # -- Company / currency features
    company = df[["currency_mismatch", "amount", "amount_is_valid", "company_known"]]

    X = pd.concat(
        [temporal, batch, industry, country, company],
        axis=1,
    ).reset_index(drop=True)

    return X, y.reset_index(drop=True), df_meta.reset_index(drop=True)


# ============================================================
# STAGE 3 — PCA FRAMEWORK
# ============================================================

def run_pca(
    X: pd.DataFrame,
    y: pd.Series,
    df_meta: pd.DataFrame,
) -> None:
    """
    PCA analysis — structure only. Fill in each section below.

    Analysis 1: records where company_known = 1 (can use industry/country features)
    Analysis 2: records where company_known = 0 (those features are all-zero)
    """

    # --- Split into Analysis 1 (company_known=1) and Analysis 2 (company_known=0)

    # --- Fit PCA on Analysis 1 X only

    # --- Scree plot: explained variance per component

    # --- 2D scatter plot: PC1 vs PC2 colored by failure_code

    # --- Loadings heatmap: original features vs top components

    # --- Project Analysis 2 records into PCA space

    # --- K-means clustering on PCA-reduced Analysis 1 data

    pass


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    conn = get_connection()
    try:
        print("Loading quarantine features...")
        df = load_quarantine_features(conn)
        print(f"Raw query: {df.shape[0]:,} rows x {df.shape[1]} columns")
    finally:
        conn.close()

    print("Preprocessing...")
    X, y, df_meta = preprocess(df)

    print(f"\nFeature matrix shape: {X.shape}")
    print(f"Label distribution:\n{y.value_counts()}")
    print(f"\nFeature columns ({len(X.columns)}):\n{list(X.columns)}")
    print(f"\nFirst 5 rows:\n{X.head()}")


if __name__ == "__main__":
    main()
