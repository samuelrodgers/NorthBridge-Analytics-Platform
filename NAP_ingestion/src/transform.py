# transform.py
# Batch transform: raw schema → analytics schema.
#
# Run this after main.py has populated raw.fx_rate and raw.transaction_event.
#
# Execution order (required by FK constraints and trigger logic):
#   SEED  (runs once if tables empty):
#     0. analytics.d_currency    ← FK target for f_fx_rate
#     1. analytics.d_company     ← FK target for f_transaction
#   BATCH (runs every transform):
#     2. analytics.f_fx_rate     ← deduplicated rates; FK target for f_conversion
#     3. analytics.d_time        ← time dimension; FK target for f_transaction
#     4. analytics.f_transaction ← one row per tx, amount=0 placeholder
#     5. analytics.f_conversion  ← fires trg_apply_conversion → sets f_transaction.amount
#                                   fires trg_validate_conversion_currency → guards integrity
#
# Idempotency: every INSERT uses ON CONFLICT DO NOTHING.
# Re-running this script against the same raw data is safe.
#
# Transaction wrapping: steps 2-5 run inside a single BEGIN/COMMIT.
# If any step fails, the entire batch rolls back — no partial analytics state.

import logging
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

from config import COMPANIES, CURRENCIES

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================
# CONNECTION
# ============================================================

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
    )


# ============================================================
# STEP 0 — SEED d_currency
# ============================================================
# d_currency is a FK target for f_fx_rate (base_cncy, quote_cncy).
# Must exist before any FX rates can be promoted to analytics.
# Includes USD even though it never appears as base_cncy in FX pairs —
# it appears as quote_cncy and must satisfy the FK.

SQL_SEED_CURRENCY = """
    INSERT INTO analytics.d_currency (cncy_code, cncy_name)
    VALUES %s
    ON CONFLICT (cncy_code) DO NOTHING
"""

def seed_currencies(cur):
    rows = [
        (code, meta["name"])
        for code, meta in CURRENCIES.items()
    ]
    execute_values(cur, SQL_SEED_CURRENCY, rows)
    logger.info(f"d_currency: seeded {len(rows)} currencies")


# ============================================================
# STEP 1 — SEED d_company
# ============================================================
# d_company is a FK target for f_transaction.c_id.
# c_id here must match the uuid5-derived IDs in config.COMPANIES
# so that raw.transaction_event.c_id joins correctly.

SQL_SEED_COMPANY = """
    INSERT INTO analytics.d_company (c_id, c_name, industry, hq_country, default_cncy)
    VALUES %s
    ON CONFLICT (c_id) DO NOTHING
"""

def seed_companies(cur):
    rows = [
        (
            meta["c_uuid"],
            meta["name"],
            meta["industry"],
            meta["hq_country"],
            meta["default_cncy"],
        )
        for meta in COMPANIES.values()
    ]
    execute_values(cur, SQL_SEED_COMPANY, rows)
    logger.info(f"d_company: seeded {len(rows)} companies")


# ============================================================
# STEP 2 — INSERT f_fx_rate
# ============================================================
# Promotes distinct FX rates from raw into the analytics fact table.
# We deduplicate on (base_cncy, quote_cncy, rate) — the analytics
# f_fx_rate stores unique rate values, not a time series.
# The fx_id generated here is what f_conversion will reference.
#
# Note: raw.fx_rate has many ticks per pair (one per 5s).
# We only promote each unique rate value once.
# The LATERAL join in step 4 will look up the right fx_id by
# matching back to rate value + currency pair.

SQL_INSERT_FX_RATE = """
    INSERT INTO analytics.f_fx_rate (rate, base_cncy, quote_cncy)
    SELECT DISTINCT
        r.rate,
        TRIM(r.base_cncy)  AS base_cncy,
        TRIM(r.quote_cncy) AS quote_cncy
    FROM raw.fx_rate r
    ON CONFLICT DO NOTHING
"""

# f_fx_rate has no unique constraint defined yet — we rely on
# the PK (fx_id) being distinct per insert. To make this truly
# idempotent we need to not re-insert rates already promoted.
# We guard by checking if the (rate, base_cncy, quote_cncy) combo exists.
SQL_INSERT_FX_RATE_SAFE = """
    INSERT INTO analytics.f_fx_rate (rate, base_cncy, quote_cncy)
    SELECT DISTINCT
        r.rate,
        TRIM(r.base_cncy)  AS base_cncy,
        TRIM(r.quote_cncy) AS quote_cncy
    FROM raw.fx_rate r
    WHERE NOT EXISTS (
        SELECT 1
        FROM analytics.f_fx_rate f
        WHERE f.rate       = r.rate
          AND f.base_cncy  = TRIM(r.base_cncy)
          AND f.quote_cncy = TRIM(r.quote_cncy)
    )
"""

def insert_fx_rates(cur):
    cur.execute(SQL_INSERT_FX_RATE_SAFE)
    count = cur.rowcount
    logger.info(f"f_fx_rate: inserted {count} new rate rows")
    return count


# ============================================================
# STEP 3 — INSERT d_time
# ============================================================
# One d_time row per unique transaction timestamp.
# fisc_quarter: derived from month (Q1=months 1-3, etc.)
# day_of_week:  0=Monday through 6=Sunday (PostgreSQL ISODOW - 1)
#
# ISODOW returns 1(Mon)–7(Sun); we subtract 1 to get 0-indexed.

SQL_INSERT_DTIME = """
    INSERT INTO analytics.d_time (t_stamp, fisc_quarter, day_of_week)
    SELECT DISTINCT
        t.tx_timestamp                                    AS t_stamp,
        CEIL(EXTRACT(MONTH FROM t.tx_timestamp) / 3.0)::smallint
                                                          AS fisc_quarter,
        (EXTRACT(ISODOW FROM t.tx_timestamp) - 1)::smallint
                                                          AS day_of_week
    FROM raw.transaction_event t
    WHERE NOT EXISTS (
        SELECT 1
        FROM analytics.d_time d
        WHERE d.t_stamp = t.tx_timestamp
    )
"""

def insert_time_dimension(cur):
    cur.execute(SQL_INSERT_DTIME)
    count = cur.rowcount
    logger.info(f"d_time: inserted {count} new time rows")
    return count


# ============================================================
# STEP 4 — INSERT f_transaction
# ============================================================
# One row per raw transaction.
# amount is set to 0 here — it is a required NOT NULL field,
# but the real value is written by the apply_conversion() trigger
# when f_conversion is inserted in step 5.
#
# For USD transactions (no conversion needed), amount is set
# directly here as: amount - fee_amount (no FX multiplication).
#
# cncy = the company's default currency (base_cncy on the raw tx).
# c_id = the uuid5 company ID — must match analytics.d_company.c_id.
# time_id = FK to d_time, looked up by matching t_stamp to tx_timestamp.

SQL_INSERT_FTRANSACTION = """
    INSERT INTO analytics.f_transaction (tx_id, amount, c_id, time_id, cncy)
    SELECT
        t.tx_id,

        -- No conversion (quote_cncy IS NULL): amount is already in company currency.
        -- Set final amount directly as amount - fee.
        -- Conversion needed (quote_cncy IS NOT NULL): placeholder 0.
        -- apply_conversion() trigger will overwrite this after f_conversion insert.
        CASE
            WHEN t.quote_cncy IS NULL
            THEN t.amount - COALESCE(t.fee_amount, 0)
            ELSE 0
        END                             AS amount,

        t.c_id,

        d.time_id,

        TRIM(t.base_cncy)               AS cncy

    FROM raw.transaction_event t

    JOIN analytics.d_time d
      ON d.t_stamp = t.tx_timestamp

    WHERE NOT EXISTS (
        SELECT 1
        FROM analytics.f_transaction f
        WHERE f.tx_id = t.tx_id
    )
"""

def insert_transactions(cur):
    cur.execute(SQL_INSERT_FTRANSACTION)
    count = cur.rowcount
    logger.info(f"f_transaction: inserted {count} rows")
    return count


# ============================================================
# STEP 5 — INSERT f_conversion
# ============================================================
# One row per non-USD transaction.
# Inserting here fires two triggers in order:
#
#   1. trg_validate_conversion_currency (BEFORE INSERT)
#      Checks that f_transaction.cncy matches f_fx_rate.quote_cncy.
#      Raises exception if mismatch — protects against wrong FX rate.
#
#   2. trg_apply_conversion (AFTER INSERT)
#      Reads base_amount and fee_amount from the new f_conversion row,
#      reads rate from f_fx_rate via fx_id,
#      then UPDATEs f_transaction.amount = (base_amount * rate) - fee_amount.
#
# The LATERAL join here is the SQL equivalent of merge_asof —
# for each transaction, find the most recent FX tick before it.
# The composite index on raw.fx_rate(base_cncy, quote_cncy, fx_timestamp)
# makes this efficient at scale.

SQL_INSERT_FCONVERSION = """
    INSERT INTO analytics.f_conversion (base_amount, fee_amount, fx_id, tx_id)
    SELECT
        t.amount                        AS base_amount,
        COALESCE(t.fee_amount, 0)       AS fee_amount,
        matched_fx.fx_id                AS fx_id,
        t.tx_id                         AS tx_id

    FROM raw.transaction_event t

    JOIN LATERAL (
        SELECT
            f_analytics.fx_id,
            f_raw.fx_timestamp
        FROM raw.fx_rate f_raw
        JOIN analytics.f_fx_rate f_analytics
          ON  f_analytics.rate       = f_raw.rate
          AND f_analytics.base_cncy  = f_raw.base_cncy
          AND f_analytics.quote_cncy = f_raw.quote_cncy
        WHERE f_raw.base_cncy   = t.base_cncy
          AND f_raw.quote_cncy  = t.quote_cncy
          AND f_raw.fx_timestamp <= t.tx_timestamp
        ORDER BY f_raw.fx_timestamp DESC
        LIMIT 1
    ) matched_fx ON true

    WHERE t.quote_cncy IS NOT NULL

    AND NOT EXISTS (
        SELECT 1
        FROM analytics.f_conversion fc
        WHERE fc.tx_id = t.tx_id
    )
"""

def insert_conversions(cur):
    cur.execute(SQL_INSERT_FCONVERSION)
    count = cur.rowcount
    logger.info(f"f_conversion: inserted {count} rows (trigger fired for each)")
    return count


# ============================================================
# MAIN — orchestrates seed + batch transform
# ============================================================

def run_seed(conn):
    """
    Seed dimension tables if empty. Safe to call on every run.
    Checks row count first — skips if already populated.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM analytics.d_currency")
        if cur.fetchone()[0] == 0:
            logger.info("Seeding dimension tables...")
            seed_currencies(cur)
            seed_companies(cur)
            conn.commit()
            logger.info("Seed complete.")
        else:
            logger.info("Dimension tables already seeded — skipping.")


def run_transform(conn):
    """
    Batch transform: raw → analytics.
    Wrapped in a single transaction — all steps succeed or all roll back.
    """
    logger.info("Starting batch transform...")

    with conn.cursor() as cur:
        try:
            fx_count   = insert_fx_rates(cur)
            time_count = insert_time_dimension(cur)
            tx_count   = insert_transactions(cur)
            conv_count = insert_conversions(cur)

            conn.commit()

            logger.info(
                f"✅ Transform complete — "
                f"fx_rate: {fx_count}, "
                f"d_time: {time_count}, "
                f"f_transaction: {tx_count}, "
                f"f_conversion: {conv_count}"
            )

        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Transform failed — rolled back. Error: {e}")
            raise


def run(seed=False):
    conn = get_connection()
    try:
        if seed:
            run_seed(conn)
        run_transform(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    # Pass --seed flag on first run: python transform.py --seed
    seed = "--seed" in sys.argv
    run(seed=seed)