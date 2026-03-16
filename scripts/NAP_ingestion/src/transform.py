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
#     5. analytics.d_time        ← time dimension; FK target for f_transaction + f_expense
#     6. analytics.f_transaction ← one row per tx; amount = native amount - fee
#     7. analytics.f_conversion  ← additive record of conversion inputs; does not
#                                   modify f_transaction (apply_conversion trigger
#                                   has been removed — f_transaction.amount is final
#                                   on insert and must never be overwritten)
#     8. raw.expense_event       ← synthetic expense rows generated from d_company
#                                   + d_expense_category; loaded into raw before
#                                   promotion so the append-only contract is honoured
#     9. analytics.f_expense     ← promoted from raw.expense_event
#    10. analytics.f_industry    ← daily aggregate refresh per industry;
#                                   computed from f_transaction + f_expense
#
# Idempotency: every INSERT uses ON CONFLICT DO NOTHING.
# Re-running this script against the same raw data is safe.
#
# Transaction wrapping: batch steps 4-10 run inside a single BEGIN/COMMIT.
# If any step fails, the entire batch rolls back — no partial analytics state.
#
# SQL error logging: every caught SQL exception is written to sql_errors.log
# in addition to stdout. Each entry includes the step name, error message,
# and a truncated copy of the SQL that failed. Designed for post-mortem
# debugging when going live.

import logging
import logging.handlers
import os
import uuid
from datetime import datetime, timezone, timedelta

import numpy as np
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

from config import (
    COMPANIES,
    CURRENCIES,
    INDUSTRIES,
    EXPENSE_CATEGORIES,
)

load_dotenv()


# ============================================================
# LOGGING — stdout + SQL error file
# ============================================================
# The root logger handles general INFO output to stdout as before.
# A second dedicated logger writes only SQL errors to sql_errors.log
# so they survive across restarts and are easy to grep post-mortem.
# RotatingFileHandler caps the file at 5 MB and keeps 3 backups —
# enough history without filling disk on a long-running instance.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

_sql_error_logger = logging.getLogger("sql_errors")
_sql_error_logger.setLevel(logging.ERROR)
_sql_error_logger.propagate = False  # Don't double-print to stdout

_sql_error_handler = logging.handlers.RotatingFileHandler(
    filename="sql_errors.log",
    maxBytes=5 * 1024 * 1024,  # 5 MB per file
    backupCount=3,
    encoding="utf-8",
)
_sql_error_handler.setFormatter(logging.Formatter(
    "%(asctime)s\n"
    "STEP:    %(step)s\n"
    "ERROR:   %(message)s\n"
    "SQL:     %(sql)s\n"
    "---\n"
))
_sql_error_logger.addHandler(_sql_error_handler)


def _log_sql_error(step: str, error: Exception, sql: str = "") -> None:
    """
    Write a structured SQL error entry to sql_errors.log.

    Args:
        step:  Human-readable name of the transform step that failed,
               e.g. "insert_transactions" or "refresh_f_industry".
        error: The caught exception.
        sql:   The SQL string that caused the failure. Truncated to 500
               characters to keep log entries scannable.
    """
    _sql_error_logger.error(
        str(error),
        extra={
            "step": step,
            "sql":  (sql[:500] + "...") if len(sql) > 500 else sql,
        }
    )


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
# Reads from the live COMPANIES registry so any companies added at runtime
# via config.register_company() are included on the next seed call.

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
# Must be seeded before f_expense or raw.expense_event rows are generated —
# both have a NOT NULL FK on category_id.
# Categories are managed as data (not a schema enum) so additions to
# config.EXPENSE_CATEGORIES take effect without a migration.

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
# Deduplicates on (base_cncy, quote_cncy, rate) — f_fx_rate stores unique
# rate values, not a full time series.
# The fx_id generated here is what f_conversion references.

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
# One d_time row per unique timestamp across both transaction_event and
# expense_event — both f_transaction and f_expense carry a time_id FK.
# Pulling timestamps from both tables in a single step means the dimension
# is fully populated regardless of which event type arrives first.
#
# fisc_quarter: Q1=months 1-3, Q2=4-6, Q3=7-9, Q4=10-12
# day_of_week:  0=Monday through 6=Sunday (ISODOW - 1)

SQL_INSERT_DTIME = """
    INSERT INTO analytics.d_time (t_stamp, fisc_quarter, day_of_week)
    SELECT DISTINCT
        ts                                                        AS t_stamp,
        CEIL(EXTRACT(MONTH FROM ts) / 3.0)::smallint             AS fisc_quarter,
        (EXTRACT(ISODOW FROM ts) - 1)::smallint                  AS day_of_week
    FROM (
        SELECT tx_timestamp      AS ts FROM raw.transaction_event
        UNION
        SELECT expense_timestamp AS ts FROM raw.expense_event
    ) combined
    WHERE NOT EXISTS (
        SELECT 1
        FROM analytics.d_time d
        WHERE d.t_stamp = ts
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
# amount = t.amount - COALESCE(t.fee_amount, 0) for every row, regardless
# of whether a currency conversion is involved.
# f_transaction.amount stores the native recorded currency amount after fee
# deduction and must never be overwritten — the apply_conversion trigger has
# been removed.
#
# f_conversion (step 7) records conversion inputs as an additive audit row
# but does not touch f_transaction.amount.

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
# (raw.transaction_event.quote_cncy IS NOT NULL).
#
# f_conversion is a purely additive audit table — records the conversion
# inputs (base_amount, fee_amount, fx_id) for reference and reporting.
# Does NOT modify f_transaction.
#
# trg_validate_conversion_currency (BEFORE INSERT) still fires and raises
# an exception if f_transaction.cncy does not match f_fx_rate.base_cncy —
# protecting against a wrong FX rate being linked to a transaction.

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
# BATCH STEP 8 — generate and load raw.expense_event
# ============================================================
# Generates synthetic expense rows for every company in the live registry
# and inserts them into raw.expense_event. Raw is the correct landing zone
# even for generated data — it preserves the append-only contract and means
# the promotion in step 9 always has the same source regardless of whether
# expenses came from a real feed or were generated here.
#
# Generation strategy:
#   - Each company gets between 1 and 5 expense events per run.
#   - Timestamps are spread randomly across the past 24 hours relative to
#     the current wall clock, so each run produces a fresh time window.
#   - Amounts are drawn from a log-normal distribution shaped to produce
#     realistic operating expense values (median ~$500, occasional peaks).
#   - Categories are sampled uniformly from the live EXPENSE_CATEGORIES
#     registry — all categories appear with roughly equal frequency.
#   - Currency is USD only (BR-022). Multi-currency support is deferred.
#
# expense_id is generated in Python (uuid4) so it is available for the
# ON CONFLICT guard — same pattern as tx_id in transactions.py.

def generate_expense_events(
    window_hours: int = 24,
    seed: int = None,
) -> list[tuple]:
    """
    Generate synthetic expense event rows ready for bulk insert into
    raw.expense_event.

    Args:
        window_hours: How many hours back from now the expense timestamps
                      should be distributed across. Default 24 hours.
        seed:         Optional random seed for reproducibility in tests.
                      Production runs should leave this as None.

    Returns:
        List of tuples:
            (expense_id, c_id, cncy, expense_timestamp, amount, category_id)
        Column order matches SQL_INSERT_EXPENSE_EVENT.
    """
    rng = np.random.default_rng(seed)

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=window_hours)

    category_ids = list(EXPENSE_CATEGORIES.values())

    rows = []
    for meta in COMPANIES.values():
        # Between 1 and 5 expense events per company per run
        n_expenses = int(rng.integers(1, 6))

        for _ in range(n_expenses):
            offset_seconds = rng.uniform(0, window_hours * 3600)
            expense_ts = window_start + timedelta(seconds=float(offset_seconds))

            # Log-normal: median ~$500, sigma=0.8 gives a realistic spread
            amount = round(float(rng.lognormal(mean=6.2, sigma=0.8)), 4)

            category_id = str(rng.choice(category_ids))

            rows.append((
                str(uuid.uuid4()),  # expense_id
                meta["c_uuid"],     # c_id
                "USD",              # cncy — USD only (BR-022)
                expense_ts,         # expense_timestamp
                amount,             # amount
                category_id,        # category_id
            ))

    return rows


SQL_INSERT_EXPENSE_EVENT = """
    INSERT INTO raw.expense_event
        (expense_id, c_id, cncy, expense_timestamp, amount, category_id)
    VALUES %s
    ON CONFLICT (expense_id) DO NOTHING
"""

def load_expense_events(cur, rows: list[tuple]) -> int:
    """
    Bulk insert generated expense rows into raw.expense_event.

    Args:
        cur:  psycopg2 cursor (within the caller's transaction).
        rows: List of tuples from generate_expense_events().

    Returns:
        Number of rows inserted.
    """
    if not rows:
        logger.info("raw.expense_event: no rows to insert")
        return 0

    execute_values(cur, SQL_INSERT_EXPENSE_EVENT, rows)
    count = cur.rowcount
    logger.info(f"raw.expense_event: inserted {count} rows")
    return count


# ============================================================
# BATCH STEP 9 — f_expense
# ============================================================
# Promotes rows from raw.expense_event into analytics.f_expense.
# Joins on d_time to resolve expense_timestamp → time_id — the same
# dimension used by f_transaction, so expense and transaction timestamps
# are directly comparable in the analytics schema.
# cncy is passed through directly (USD only for now, BR-022).

SQL_INSERT_FEXPENSE = """
    INSERT INTO analytics.f_expense
        (expense_id, amount, cncy, c_id, time_id, category_id)
    SELECT
        e.expense_id,
        e.amount,
        e.cncy,
        e.c_id,
        d.time_id,
        e.category_id
    FROM raw.expense_event e
    JOIN analytics.d_time d
      ON d.t_stamp = e.expense_timestamp
    WHERE NOT EXISTS (
        SELECT 1
        FROM analytics.f_expense f
        WHERE f.expense_id = e.expense_id
    )
"""

def insert_expenses(cur) -> int:
    cur.execute(SQL_INSERT_FEXPENSE)
    count = cur.rowcount
    logger.info(f"f_expense: inserted {count} rows")
    return count


# ============================================================
# BATCH STEP 10 — f_industry (daily aggregate refresh)
# ============================================================
# Computes and inserts one row per industry per calendar day from the
# current state of f_transaction and f_expense.
#
# Grain: (industry_id, time_id) composite PK, where time_id points to
# a d_time row whose t_stamp is midnight on the day being aggregated.
# Because d_time stores individual event timestamps (not calendar days),
# SQL_ENSURE_MIDNIGHT_DTIME inserts a synthetic midnight row for each
# distinct day before the aggregation runs, giving the JOIN a target.
#
# revenue_growth_rate:
#   Computed via LAG() partitioned by industry_id, ordered by day.
#   NULL on the first row for any industry (no prior period, BR-026).
#   NULL if prior period revenue was zero (avoids divide-by-zero).
#   Formula: (current - prior) / prior * 100, stored as numeric(7,4).
#
# Idempotency: ON CONFLICT (industry_id, time_id) DO NOTHING.
# Already-written rows for a given (industry, day) are left untouched.
# Full recalculation requires deleting and re-inserting those rows, which
# is intentionally out of scope here (BR-024: never updated in place).

SQL_ENSURE_MIDNIGHT_DTIME = """
    INSERT INTO analytics.d_time (t_stamp, fisc_quarter, day_of_week)
    SELECT DISTINCT
        DATE_TRUNC('day', d.t_stamp)                                          AS t_stamp,
        CEIL(EXTRACT(MONTH FROM DATE_TRUNC('day', d.t_stamp)) / 3.0)::smallint
                                                                              AS fisc_quarter,
        (EXTRACT(ISODOW FROM DATE_TRUNC('day', d.t_stamp)) - 1)::smallint    AS day_of_week
    FROM analytics.d_time d
    WHERE NOT EXISTS (
        SELECT 1
        FROM analytics.d_time existing
        WHERE existing.t_stamp = DATE_TRUNC('day', d.t_stamp)
    )
"""

SQL_REFRESH_FINDUSTRY = """
    INSERT INTO analytics.f_industry
        (industry_id, time_id, total_revenue, total_expenses, net_profit,
         transaction_count, avg_revenue_per_co, revenue_growth_rate, company_count)

    WITH

    -- Aggregate transaction revenue and counts per industry per day
    daily_revenue AS (
        SELECT
            dc.industry_id,
            DATE_TRUNC('day', dt.t_stamp)   AS day,
            SUM(ft.amount)                  AS total_revenue,
            COUNT(ft.tx_id)                 AS transaction_count,
            COUNT(DISTINCT ft.c_id)         AS company_count
        FROM analytics.f_transaction ft
        JOIN analytics.d_time dt
          ON dt.time_id = ft.time_id
        JOIN analytics.d_company dc
          ON dc.c_id = ft.c_id
        GROUP BY dc.industry_id, DATE_TRUNC('day', dt.t_stamp)
    ),

    -- Aggregate expense totals per industry per day
    daily_expenses AS (
        SELECT
            dc.industry_id,
            DATE_TRUNC('day', dt.t_stamp)   AS day,
            SUM(fe.amount)                  AS total_expenses
        FROM analytics.f_expense fe
        JOIN analytics.d_time dt
          ON dt.time_id = fe.time_id
        JOIN analytics.d_company dc
          ON dc.c_id = fe.c_id
        GROUP BY dc.industry_id, DATE_TRUNC('day', dt.t_stamp)
    ),

    -- Join revenue and expenses; default expenses to 0 if no expense rows
    -- exist yet for a given industry-day (possible early in a run)
    combined AS (
        SELECT
            dr.industry_id,
            dr.day,
            dr.total_revenue,
            COALESCE(de.total_expenses, 0)              AS total_expenses,
            dr.total_revenue
                - COALESCE(de.total_expenses, 0)        AS net_profit,
            dr.transaction_count,
            dr.company_count,
            dr.total_revenue / NULLIF(dr.company_count, 0)
                                                        AS avg_revenue_per_co
        FROM daily_revenue dr
        LEFT JOIN daily_expenses de
          ON de.industry_id = dr.industry_id
         AND de.day          = dr.day
    ),

    -- Period-over-period revenue growth via LAG.
    -- NULL on first row per industry (BR-026).
    -- NULL if prior period revenue was zero (avoid divide-by-zero).
    with_growth AS (
        SELECT
            c.*,
            CASE
                WHEN LAG(c.total_revenue) OVER (
                         PARTITION BY c.industry_id ORDER BY c.day
                     ) IS NULL
                    THEN NULL
                WHEN LAG(c.total_revenue) OVER (
                         PARTITION BY c.industry_id ORDER BY c.day
                     ) = 0
                    THEN NULL
                ELSE ROUND(
                    (
                        c.total_revenue
                        - LAG(c.total_revenue) OVER (
                              PARTITION BY c.industry_id ORDER BY c.day
                          )
                    )
                    / LAG(c.total_revenue) OVER (
                          PARTITION BY c.industry_id ORDER BY c.day
                      ) * 100,
                    4
                )
            END AS revenue_growth_rate
        FROM combined c
    )

    -- Resolve calendar day → time_id via the midnight d_time rows inserted above
    SELECT
        wg.industry_id,
        dt.time_id,
        wg.total_revenue,
        wg.total_expenses,
        wg.net_profit,
        wg.transaction_count,
        wg.avg_revenue_per_co,
        wg.revenue_growth_rate,
        wg.company_count::smallint
    FROM with_growth wg
    JOIN analytics.d_time dt
      ON dt.t_stamp = wg.day

    ON CONFLICT (industry_id, time_id) DO NOTHING
"""

def refresh_f_industry(cur) -> int:
    """
    Compute and insert daily industry aggregate rows into f_industry.

    Runs SQL_ENSURE_MIDNIGHT_DTIME first to guarantee that a d_time row
    exists for each calendar day before the aggregation tries to join on it.

    Returns:
        Number of new f_industry rows inserted.
    """
    cur.execute(SQL_ENSURE_MIDNIGHT_DTIME)
    midnight_count = cur.rowcount
    if midnight_count > 0:
        logger.info(
            f"d_time: inserted {midnight_count} synthetic midnight rows "
            f"for f_industry day-grain join"
        )

    cur.execute(SQL_REFRESH_FINDUSTRY)
    count = cur.rowcount
    logger.info(f"f_industry: inserted {count} aggregate rows")
    return count


# ============================================================
# MAIN — orchestrates seed + batch transform
# ============================================================

def run_seed(conn):
    """
    Seed all dimension tables required before batch transforms can run.
    Safe to call on every run — each table is checked individually and
    skipped if already populated, so a previously interrupted seed is
    completed rather than re-skipped entirely.

    Insertion order is fixed by FK constraints:
        d_currency → d_industry → d_company → d_expense_category
    """
    with conn.cursor() as cur:
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
    All batch steps run inside a single transaction — all succeed or all
    roll back so the analytics schema is never left in a partial state.

    SQL errors are written to sql_errors.log in addition to stderr so
    they are preserved across restarts for post-mortem debugging.
    """
    logger.info("Starting batch transform...")

    with conn.cursor() as cur:
        try:
            fx_count       = insert_fx_rates(cur)
            time_count     = insert_time_dimension(cur)
            tx_count       = insert_transactions(cur)
            conv_count     = insert_conversions(cur)

            expense_rows   = generate_expense_events()
            raw_exp_count  = load_expense_events(cur, expense_rows)
            exp_count      = insert_expenses(cur)

            industry_count = refresh_f_industry(cur)

            conn.commit()

            logger.info(
                f"✅ Transform complete — "
                f"f_fx_rate: {fx_count}, "
                f"d_time: {time_count}, "
                f"f_transaction: {tx_count}, "
                f"f_conversion: {conv_count}, "
                f"raw.expense_event: {raw_exp_count}, "
                f"f_expense: {exp_count}, "
                f"f_industry: {industry_count}"
            )

            return {
                "fx_rates":      fx_count,
                "d_time":        time_count,
                "transactions":  tx_count,
                "conversions":   conv_count,
                "raw_expenses":  raw_exp_count,
                "expenses":      exp_count,
                "industry_rows": industry_count,
            }

        except Exception as e:
            conn.rollback()
            _log_sql_error(
                step="run_transform",
                error=e,
                sql=getattr(e, "pgerror", "") or "",
            )
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