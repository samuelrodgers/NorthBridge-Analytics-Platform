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
#   3. run_pca(X, y, df_meta)         — PCA analysis

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import matplotlib.pyplot as plt

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
    y       = df["failure_code"]
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
    tx_ts  = pd.to_datetime(df["tx_timestamp"],       utc=True, errors="coerce")
    ingest = pd.to_datetime(df["ingestion_timestamp"], utc=True, errors="coerce")
    df["tx_ingestion_lag"] = (ingest - tx_ts).dt.total_seconds()

    # batch_quarantine_rate: fraction of the batch that was quarantined.
    # Null where both counts are null (CRON runs with no pipeline_run row).
    total_batch = df["clean_count"] + df["quarantine_count"]
    df["batch_quarantine_rate"] = df["quarantine_count"] / total_batch.replace(0, np.nan)

    # hour_of_day and day_of_week: extracted from tx_timestamp.
    # Null where tx_timestamp is missing; fallback applied in Step 5.
    df["hour_of_day"] = tx_ts.dt.hour.astype("Float64")
    df["day_of_week"] = tx_ts.dt.dayofweek.astype("Float64")
    df.loc[df["tx_timestamp_missing"] == 1, ["hour_of_day", "day_of_week"]] = np.nan

    # ── Step 3: One-hot encode industry_name ──────────────────────────────────
    # fill null → "__unknown__" so get_dummies doesn't drop the row silently,
    # then drop the unknown column so nulls become all-zeros rows.
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
    df["tx_ingestion_lag"]      = df["tx_ingestion_lag"].fillna(0)
    df["hour_of_day"]           = df["hour_of_day"].fillna(df["hour_of_day"].median())
    df["day_of_week"]           = df["day_of_week"].fillna(df["day_of_week"].median())
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
    industry_cols = sorted(industry_dummies.columns)
    industry = industry_dummies[industry_cols]

    # -- Country one-hot (10 columns — alphabetical)
    country_cols = sorted(country_dummies.columns)
    country = country_dummies[country_cols]

    # -- Company / currency features
    company = df[["currency_mismatch", "amount", "amount_is_valid", "company_known"]]

    X = pd.concat(
        [temporal, batch, industry, country, company],
        axis=1,
    ).reset_index(drop=True)

    return X, y.reset_index(drop=True), df_meta.reset_index(drop=True)


# ============================================================
# STAGE 3 — PCA SUPPORT FUNCTIONS
# ============================================================

def plot_scree(explained_variance: np.ndarray, cumulative_variance: np.ndarray) -> None:
    """
    Scree plot: individual and cumulative explained variance per component.

    Args:
        explained_variance:  per-component variance ratios from pca.explained_variance_ratio_
        cumulative_variance: cumulative sum of explained_variance
    """
    fig, ax1 = plt.subplots(figsize=(10, 5))

    components = range(1, len(explained_variance) + 1)

    ax1.bar(components, explained_variance, alpha=0.6,
            color='steelblue', label='Individual explained variance')
    ax1.set_xlabel('Principal Component')
    ax1.set_ylabel('Explained Variance Ratio', color='steelblue')
    ax1.set_xticks(components)

    ax2 = ax1.twinx()
    ax2.plot(components, cumulative_variance, color='darkorange',
             marker='o', linewidth=2, label='Cumulative explained variance')
    ax2.set_ylabel('Cumulative Explained Variance', color='darkorange')
    ax2.axhline(y=0.90, color='red', linestyle='--', alpha=0.5, label='90% threshold')

    plt.title('Scree Plot — PCA on Quarantine Records (Analysis 1)')
    fig.legend(loc='center right')
    plt.tight_layout()
    plt.savefig('scree_plot.png', dpi=150)
    plt.show()


def plot_scatter(X_reduced: np.ndarray, y: pd.Series) -> None:
    """
    Side-by-side scatter plots: PC1 vs PC2 (left) and PC2 vs PC3 (right),
    colored by failure_code for Analysis 1 records.

    Args:
        X_reduced: PCA-transformed array, shape (n_samples, n_components)
        y:         failure_code Series aligned to X_reduced rows
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    colors = {
        'INVALID_AMOUNT': 'steelblue',
        'NULL_TIMESTAMP': 'green',
    }

    for failure_code, color in colors.items():
        mask = y == failure_code
        ax1.scatter(
            X_reduced[mask, 0],
            X_reduced[mask, 1],
            c=color,
            label=failure_code,
            alpha=0.3,
            s=5,
        )
        ax2.scatter(
            X_reduced[mask, 1],
            X_reduced[mask, 2],
            c=color,
            label=failure_code,
            alpha=0.3,
            s=5,
        )

    ax1.set_xlabel('Principal Component 1')
    ax1.set_ylabel('Principal Component 2')
    ax1.set_title('PC1 vs PC2 — Failure Code Separation')
    ax1.legend(markerscale=3)

    ax2.set_xlabel('Principal Component 2')
    ax2.set_ylabel('Principal Component 3')
    ax2.set_title('PC2 vs PC3 — Failure Code Separation')
    ax2.legend(markerscale=3)

    plt.suptitle('PCA Feature Space — Analysis 1', fontsize=13)
    plt.tight_layout()
    plt.savefig('pca_scatter_comparison.png', dpi=150)
    plt.show()


def plot_loadings(pca, feature_names: list[str], n_display: int = 5) -> None:
    """
    Loadings heatmap: contribution of each original feature to each component.

    Args:
        pca:           fitted sklearn PCA object
        feature_names: ordered list of feature column names from X
        n_display:     number of components to show (default: 5)
    """
    loadings = pd.DataFrame(
        pca.components_[:n_display].T,
        index=feature_names,
        columns=[f'PC{i + 1}' for i in range(n_display)],
    )

    fig, ax = plt.subplots(figsize=(10, 12))
    im = ax.imshow(loadings.values, cmap='coolwarm', aspect='auto', vmin=-1, vmax=1)

    ax.set_xticks(range(n_display))
    ax.set_xticklabels([f'PC{i + 1}' for i in range(n_display)])
    ax.set_yticks(range(len(feature_names)))
    ax.set_yticklabels(feature_names)

    plt.colorbar(im, ax=ax, label='Loading value')
    ax.set_title(f'PCA Loadings — Top {n_display} Components')
    plt.tight_layout()
    plt.savefig('loadings_heatmap.png', dpi=150)
    plt.show()


def split_analyses(
    X: pd.DataFrame,
    y: pd.Series,
    df_meta: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """
    Split X and y into Analysis 1 (company_known=1) and Analysis 2 (company_known=0).

    Returns:
        X1, y1 — records with a resolvable company ID
        X2, y2 — records where company ID was null (NULL_COMPANY_ID failures)
    """
    known_mask = df_meta["company_known"] == 1

    X1 = X[known_mask].reset_index(drop=True)
    y1 = y[known_mask].reset_index(drop=True)

    X2 = X[~known_mask].reset_index(drop=True)
    y2 = y[~known_mask].reset_index(drop=True)

    print(f"Analysis 1 (company known):   {len(X1):,} records")
    print(f"Analysis 2 (company unknown): {len(X2):,} records")

    return X1, y1, X2, y2


def fit_full_pca(
    X1: pd.DataFrame,
    n_components: int = 25,
) -> tuple[PCA, np.ndarray, np.ndarray]:
    """
    Fit a full PCA on Analysis 1 to inspect explained variance before
    choosing a reduced component count.

    Prints per-component and cumulative variance, and the number of
    components needed to reach 90% explained variance.

    Returns:
        pca_full            — fitted PCA object (all n_components)
        explained_variance  — per-component variance ratio array
        cumulative_variance — cumulative sum of explained_variance
    """
    pca_full = PCA(n_components=n_components)
    pca_full.fit(X1)

    explained_variance  = pca_full.explained_variance_ratio_
    cumulative_variance = np.cumsum(explained_variance)

    print("\nExplained variance per component:")
    for i, (ev, cv) in enumerate(zip(explained_variance, cumulative_variance)):
        print(f"  PC{i + 1}: {ev:.3f} individual  {cv:.3f} cumulative")

    print(f"\nComponents needed for 90% variance: "
          f"{np.argmax(cumulative_variance >= 0.90) + 1}")

    return pca_full, explained_variance, cumulative_variance


def refit_pca(
    X1: pd.DataFrame,
    n_components: int = 11,
) -> tuple[PCA, np.ndarray]:
    """
    Refit PCA with the chosen number of components and transform X1.

    Args:
        X1:           Analysis 1 feature matrix
        n_components: number of components to keep (default: 11)

    Returns:
        pca        — fitted PCA object
        X1_reduced — transformed array, shape (n_samples, n_components)
    """
    pca = PCA(n_components=n_components)
    X1_reduced = pca.fit_transform(X1)
    return pca, X1_reduced


def project_analysis2(
    pca: PCA,
    X2: pd.DataFrame,
    X1_reduced: np.ndarray,
    y1: pd.Series,
) -> np.ndarray:
    """
    Project Analysis 2 records into the PCA space fitted on Analysis 1.
    Produces a single figure: Analysis 1 alone (left) and Analysis 1 +
    Analysis 2 overlay (right), both in PC1/PC2 space.

    Args:
        pca:        PCA object already fitted on Analysis 1
        X2:         Analysis 2 feature matrix (same columns as X1)
        X1_reduced: already-transformed Analysis 1 array (for overlay)
        y1:         Analysis 1 failure_code Series (for overlay colouring)

    Returns:
        X2_reduced — transformed array, shape (n_samples, n_components)
    """
    X2_reduced = pca.transform(X2)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    colors_a1 = {
        'INVALID_AMOUNT': 'steelblue',
        'NULL_TIMESTAMP': 'green',
    }

    # Left — Analysis 1 only
    for failure_code, color in colors_a1.items():
        mask = y1 == failure_code
        ax1.scatter(
            X1_reduced[mask, 0],
            X1_reduced[mask, 1],
            c=color,
            label=failure_code,
            alpha=0.2,
            s=5,
        )
    ax1.set_xlabel('Principal Component 1')
    ax1.set_ylabel('Principal Component 2')
    ax1.set_title('Analysis 1 — Known Company Records')
    ax1.legend(markerscale=3)

    # Right — Analysis 1 + Analysis 2 overlay
    for failure_code, color in colors_a1.items():
        mask = y1 == failure_code
        ax2.scatter(
            X1_reduced[mask, 0],
            X1_reduced[mask, 1],
            c=color,
            label=failure_code,
            alpha=0.2,
            s=5,
        )
    ax2.scatter(
        X2_reduced[:, 0],
        X2_reduced[:, 1],
        c='purple',
        alpha=0.4,
        s=5,
        label='NULL_COMPANY_ID',
    )
    ax2.set_xlabel('Principal Component 1')
    ax2.set_ylabel('Principal Component 2')
    ax2.set_title('Analysis 2 — NULL_COMPANY_ID Projection Overlay')
    ax2.legend(markerscale=3)

    plt.suptitle('NULL_COMPANY_ID Records in PCA Space', fontsize=13)
    plt.tight_layout()
    plt.savefig('analysis2_overlay.png', dpi=150)
    plt.show()

    return X2_reduced


def run_kmeans(X1_reduced: np.ndarray, y1: pd.Series) -> None:
    """
    K-means clustering on PCA-reduced Analysis 1 data.
    Fits k=3, plots clusters vs failure codes, runs targeted clustering
    on PC2+PC3 only, and prints alignment and silhouette scores.

    Args:
        X1_reduced: PCA-transformed array from refit_pca()
        y1:         failure_code Series aligned to X1_reduced rows
    """
    # Elbow method to justify k (commented out — run manually if needed)
    # inertias = []
    # silhouette_scores = []
    # k_range = range(2, 9)
    #
    # for k in k_range:
    #     km = KMeans(n_clusters=k, random_state=42, n_init=10)
    #     labels = km.fit_predict(X1_reduced)
    #     inertias.append(km.inertia_)
    #     silhouette_scores.append(silhouette_score(X1_reduced, labels))
    #     print(f"  k={k} — inertia: {km.inertia_:.1f}, silhouette: {silhouette_scores[-1]:.3f}")
    #
    # fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    # ax1.plot(k_range, inertias, marker='o', color='steelblue')
    # ax1.set_xlabel('Number of Clusters (k)')
    # ax1.set_ylabel('Inertia')
    # ax1.set_title('Elbow Method')
    # ax2.plot(k_range, silhouette_scores, marker='o', color='darkorange')
    # ax2.set_xlabel('Number of Clusters (k)')
    # ax2.set_ylabel('Silhouette Score')
    # ax2.set_title('Silhouette Score by k')
    # plt.tight_layout()
    # plt.savefig('kmeans_selection.png', dpi=150)
    # plt.show()

    # Fit final k-means with k=3
    km_final = KMeans(n_clusters=3, random_state=42, n_init=10)
    cluster_labels = km_final.fit_predict(X1_reduced)

    # Plot clusters vs failure codes side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    colors_cluster = ['steelblue', 'darkorange', 'green']
    for cluster_id, color in enumerate(colors_cluster):
        mask = cluster_labels == cluster_id
        ax1.scatter(
            X1_reduced[mask, 0],
            X1_reduced[mask, 1],
            c=color,
            label=f'Cluster {cluster_id}',
            alpha=0.3,
            s=5,
        )
    ax1.set_xlabel('Principal Component 1')
    ax1.set_ylabel('Principal Component 2')
    ax1.set_title('K-Means Clusters (k=3)')
    ax1.legend(markerscale=3)

    colors_failure = {
        'INVALID_AMOUNT': 'steelblue',
        'NULL_TIMESTAMP': 'green',
    }
    for failure_code, color in colors_failure.items():
        mask = y1 == failure_code
        ax2.scatter(
            X1_reduced[mask, 0],
            X1_reduced[mask, 1],
            c=color,
            label=failure_code,
            alpha=0.3,
            s=5,
        )
    ax2.set_xlabel('Principal Component 1')
    ax2.set_ylabel('Principal Component 2')
    ax2.set_title('Failure Codes (for comparison)')
    ax2.legend(markerscale=3)

    plt.suptitle('K-Means Clusters vs Failure Codes — Analysis 1', fontsize=13)
    plt.tight_layout()
    plt.savefig('kmeans_clusters.png', dpi=150)
    plt.show()

    # Alignment table: clusters vs failure codes
    alignment = pd.crosstab(
        y1,
        cluster_labels,
        rownames=['Failure Code'],
        colnames=['Cluster'],
    )
    print("\nCluster vs Failure Code alignment:")
    print(alignment)
    print("\nNormalized by failure code (row %):")
    print(alignment.div(alignment.sum(axis=1), axis=0).round(3))

    # Targeted clustering on PC2 and PC3 only
    X1_targeted = X1_reduced[:, 1:3]

    km_targeted = KMeans(n_clusters=3, random_state=42, n_init=10)
    cluster_labels_targeted = km_targeted.fit_predict(X1_targeted)

    alignment_targeted = pd.crosstab(
        y1,
        cluster_labels_targeted,
        rownames=['Failure Code'],
        colnames=['Cluster'],
    )
    print("\nTargeted clustering (PC2+PC3) vs Failure Code alignment:")
    print(alignment_targeted)
    print("\nNormalized by failure code (row %):")
    print(alignment_targeted.div(alignment_targeted.sum(axis=1), axis=0).round(3))

    sil_full     = silhouette_score(X1_reduced,  cluster_labels)
    sil_targeted = silhouette_score(X1_targeted, cluster_labels_targeted)
    print(f"\nSilhouette score — full 11 components: {sil_full:.3f}")
    print(f"Silhouette score — PC2+PC3 only:       {sil_targeted:.3f}")

    # Visual comparison: targeted clusters vs failure codes in PC2/PC3 space
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    for cluster_id, color in enumerate(['steelblue', 'darkorange', 'green']):
        mask = cluster_labels_targeted == cluster_id
        ax1.scatter(
            X1_targeted[mask, 0],
            X1_targeted[mask, 1],
            c=color,
            label=f'Cluster {cluster_id}',
            alpha=0.3,
            s=5,
        )
    ax1.set_xlabel('Principal Component 2')
    ax1.set_ylabel('Principal Component 3')
    ax1.set_title('Targeted Clusters — PC2 + PC3 Only')
    ax1.legend(markerscale=3)

    for failure_code, color in colors_failure.items():
        mask = y1 == failure_code
        ax2.scatter(
            X1_targeted[mask, 0],
            X1_targeted[mask, 1],
            c=color,
            label=failure_code,
            alpha=0.3,
            s=5,
        )
    ax2.set_xlabel('Principal Component 2')
    ax2.set_ylabel('Principal Component 3')
    ax2.set_title('Failure Codes — PC2 + PC3')
    ax2.legend(markerscale=3)

    plt.suptitle('Targeted Clustering vs Failure Codes', fontsize=13)
    plt.tight_layout()
    plt.savefig('kmeans_targeted.png', dpi=150)
    plt.show()


# ============================================================
# STAGE 3 — PCA FRAMEWORK
# ============================================================

def run_pca(
    X: pd.DataFrame,
    y: pd.Series,
    df_meta: pd.DataFrame,
) -> None:
    """
    PCA analysis.

    Analysis 1: records where company_known = 1 (can use industry/country features)
    Analysis 2: records where company_known = 0 (those features are all-zero)
    """

    # --- Split into Analysis 1 (company_known=1) and Analysis 2 (company_known=0)
    X1, y1, X2, y2 = split_analyses(X, y, df_meta)

    # --- Fit PCA on Analysis 1 X only
    pca_full, explained_variance, cumulative_variance = fit_full_pca(X1)

    # --- Scree plot: explained variance per component
    plot_scree(explained_variance, cumulative_variance)

    # --- Refit PCA with chosen n_components
    pca, X1_reduced = refit_pca(X1)

    # --- 2D scatter plot: PC1 vs PC2 colored by failure_code
    plot_scatter(X1_reduced, y1)

    # --- Loadings heatmap: original features vs top components
    plot_loadings(pca, feature_names=list(X1.columns))

    # --- Project Analysis 2 records into PCA space
    X2_reduced = project_analysis2(pca, X2, X1_reduced, y1)

    # --- K-means clustering on PCA-reduced Analysis 1 data
    run_kmeans(X1_reduced, y1)


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

    print("\nPreprocessing...")
    X, y, df_meta = preprocess(df)

    print(f"\nFeature matrix shape: {X.shape}")
    print(f"Label distribution:\n{y.value_counts()}")
    print(f"\nFeature columns ({len(X.columns)}):\n{list(X.columns)}")
    print(f"\nFirst 5 rows:\n{X.head()}")

    print("\nRunning PCA...")
    run_pca(X, y, df_meta)


if __name__ == "__main__":
    main()
