# transform.py
# Batch transform: raw schema → analytics schema.
#
# Run this after main.py has populated raw.fx_rate and raw.transaction_event.
#
# Execution order (required by FK constraints):
#   SEED  (runs once per table if empty):
#     0. analytics.d_currency          ← FK target for d_industry, f_fx_rate
#     1. analytics.d_industry          ← FK target for d_company
#     2. analytics.d_company           ← FK target for f_transaction, f_expense
#     3. analytics.d_expense_category  ← FK target for f_expense, raw.expense_event
#   BATCH (runs every transform):
#     4. analytics.f_fx_rate     ← deduplicated rates; FK target for f_conversion
#     5. analytics.d_time        ← time dimension; FK target for f_transaction
#     6. analytics.f_transaction ← one row per tx; amount = native amount - fee
#     7. analytics.f_conversion  ← additive record of conversion inputs; does not
#                                   modify f_transaction (apply_conversion trigger
#                                   has been removed — f_transaction.amount is final
#                                   on insert and must never be overwritten)
#
# Idempotency: every INSERT uses ON CONFLICT DO NOTHING.
# Re-running this script against the same raw data is safe.
#
# Transaction wrapping: batch steps 4-7 run inside a single BEGIN/COMMIT.
# If any step fails, the entire batch rolls back — no partial analytics state.

import logging
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

from config import COMPANIES, CURRENCIES, INDUSTRIES, EXPENSE_CATEGORIES

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
# SEED STEP 0 — d_currency
# ============================================================
# d_currency is a FK target for d_industry (display_cncy) and f_fx_rate.
# Must be seeded first — nothing else can be inserted until currencies exist.
# USD is included even though it never appears as base_cncy in FX pairs;
# it is required as quote_cncy and as a valid display_cncy value.

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
# SEED STEP 1 — d_industry
# ============================================================
# d_industry must be seeded before d_company — d_company.industry_id is a
# FK to d_industry.industry_id.
# display_cncy is also a FK to d_currency, so d_currency must exist first.

SQL_SEED_INDUSTRY = """
    INSERT INTO analytics.d_industry (industry_id, name, display_cncy)
    VALUES %s
    ON CONFLICT (industry_id) DO NOTHING
"""

def seed_industries(cur):
    rows = [
        (
            meta["industry_id"],
            name,
            meta["display_cncy"],
        )
        for name, meta in INDUSTRIES.items()
    ]
    execute_values(cur, SQL_SEED_INDUSTRY, rows)
    logger.info(f"d_industry: seeded {len(rows)} industries")


# ============================================================
# SEED STEP 2 — d_company
# ============================================================
# d_company is a FK target for f_transaction.c_id and f_expense.c_id.
# c_id must match the uuid5-derived IDs in config.COMPANIES so that
# raw.transaction_event.c_id joins correctly.
# industry_id is a UUID FK to d_industry — the old plain industry string
# column no longer exists in the schema.
#
# This function reads from the live COMPANIES registry, so any companies
# added at runtime via config.register_company() are included automatically
# on the next seed call without restarting the process.

SQL_SEED_COMPANY = """
    INSERT INTO analytics.d_company (c_id, c_name, industry_id, hq_country, default_cncy)
    VALUES %s
    ON CONFLICT (c_id) DO NOTHING
"""

def seed_companies(cur):
    rows = [
        (
            meta["c_uuid"],
            meta["name"],
            meta["industry_id"],
            meta["hq_country"],
            meta["default_cncy"],
        )
        for meta in COMPANIES.values()
    ]
    execute_values(cur, SQL_SEED_COMPANY, rows)
    logger.info(f"d_company: seeded {len(rows)} companies")


# ============================================================
# SEED STEP 3 — d_expense_category
# ============================================================
# d_expense_category must be seeded before f_expense or raw.expense_event
# rows are generated — both have a NOT NULL FK on category_id.
# Categories are managed as data (not as a schema enum) so new categories
# can be added to config.EXPENSE_CATEGORIES without a migration.

SQL_SEED_EXPENSE_CATEGORY = """
    INSERT INTO analytics.d_expense_category (category_id, category_name)
    VALUES %s
    ON CONFLICT (category_id) DO NOTHING
"""

def seed_expense_categories(cur):
    rows = [
        (category_id, category_name)
        for category_name, category_id in EXPENSE_CATEGORIES.items()
    ]
    execute_values(cur, SQL_SEED_EXPENSE_CATEGORY, rows)
    logger.info(f"d_expense_category: seeded {len(rows)} categories")


# ============================================================
# BATCH STEP 4 — f_fx_rate
# ============================================================
# Promotes distinct FX rates from raw into the analytics fact table.
# We deduplicate on (base_cncy, quote_cncy, rate) — analytics.f_fx_rate
# stores unique rate values, not a full time series.
# The fx_id generated here is what f_conversion references.
#
# Note: raw.fx_rate has many ticks per pair (one per 5s from live_fx.py,
# or denser from synthetic_fx.py). We only promote each unique rate value
# once. The LATERAL join in step 6 matches back to the right fx_id by
# rate value + currency pair.

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
# BATCH STEP 5 — d_time
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
# BATCH STEP 6 — f_transaction
# ============================================================
# One row per raw transaction.
# amount = t.amount - COALESCE(t.fee_amount, 0) for every row regardless of
# whether a currency conversion is involved. f_transaction.amount stores the
# native recorded currency amount after fee deduction and must never be
# overwritten (the apply_conversion trigger has been removed).
#
# f_conversion (step 7) records the conversion inputs as an additive audit
# row but does not touch f_transaction.amount.
#
# cncy    = the base currency of the raw transaction (company's payment currency).
# c_id    = uuid5 company ID — must match analytics.d_company.c_id.
# time_id = FK to d_time, matched on exact timestamp.

SQL_INSERT_FTRANSACTION = """
    INSERT INTO analytics.f_transaction (tx_id, amount, c_id, time_id, cncy)
    SELECT
        t.tx_id,

        t.amount - COALESCE(t.fee_amount, 0)    AS amount,

        t.c_id,

        d.time_id,

        TRIM(t.base_cncy)                        AS cncy

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
# BATCH STEP 7 — f_conversion
# ============================================================
# One row per transaction that involved a currency conversion
# (i.e. raw.transaction_event.quote_cncy IS NOT NULL).
#
# f_conversion is a purely additive audit table — it records the conversion
# inputs (base_amount, fee_amount, fx_id) alongside the original transaction
# for reference and downstream reporting. It does NOT modify f_transaction.
#
# The only trigger that still fires on this table is:
#   trg_validate_conversion_currency (BEFORE INSERT)
#     Checks that f_transaction.cncy matches f_fx_rate.base_cncy.
#     Raises an exception on mismatch — protects against a wrong FX rate
#     being linked to a transaction.
#
# The LATERAL join is the SQL equivalent of merge_asof: for each transaction
# find the most recent FX tick at or before the transaction timestamp.
# The composite index on raw.fx_rate(base_cncy, quote_cncy, fx_timestamp)
# keeps this efficient at scale.

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
    logger.info(f"f_conversion: inserted {count} conversion audit rows")
    return count


# ============================================================
# MAIN — orchestrates seed + batch transform
# ============================================================

def run_seed(conn):
    """
    Seed all dimension tables that are required before batch transforms can run.
    Safe to call on every run — each table is checked individually and skipped
    if it already has rows, so partial seeds from a previous interrupted run
    are completed rather than skipped entirely.

    Insertion order is fixed by FK constraints:
        d_currency → d_industry → d_company → d_expense_category
    """
    with conn.cursor() as cur:
        # Check each table independently so a partial previous seed is resumed.
        cur.execute("SELECT COUNT(*) FROM analytics.d_currency")
        if cur.fetchone()[0] == 0:
            logger.info("Seeding d_currency...")
            seed_currencies(cur)
        else:
            logger.info("d_currency already seeded — skipping.")

        cur.execute("SELECT COUNT(*) FROM analytics.d_industry")
        if cur.fetchone()[0] == 0:
            logger.info("Seeding d_industry...")
            seed_industries(cur)
        else:
            logger.info("d_industry already seeded — skipping.")

        cur.execute("SELECT COUNT(*) FROM analytics.d_company")
        if cur.fetchone()[0] == 0:
            logger.info("Seeding d_company...")
            seed_companies(cur)
        else:
            logger.info("d_company already seeded — skipping.")

        cur.execute("SELECT COUNT(*) FROM analytics.d_expense_category")
        if cur.fetchone()[0] == 0:
            logger.info("Seeding d_expense_category...")
            seed_expense_categories(cur)
        else:
            logger.info("d_expense_category already seeded — skipping.")

        conn.commit()
        logger.info("Seed complete.")


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
                f"f_fx_rate: {fx_count}, "
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