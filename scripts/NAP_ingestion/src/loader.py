# loader.py
# Inserts generated DataFrames into raw schema tables.
#
# Design principles:
#   - Batch inserts via execute_values() — efficient at millions of rows
#   - ON CONFLICT DO NOTHING on all tables — safe to re-run
#   - Explicit column lists — never rely on column order matching
#   - Connection passed in, not created here — caller controls lifecycle
#   - No transform logic — that belongs in pipeline.py / transform.py
#
# Public API:
#   load_fx_rates(conn, fx_df)
#   load_transactions(conn, tx_df)
#   load_expense_events(conn, expense_df)
#   load_all(conn, fx_df, tx_df, expense_df=None)

import os
import logging
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

load_dotenv()

logger = logging.getLogger(__name__)


# ── Connection ────────────────────────────────────────────────────────────────

def get_connection():
    """Create and return a psycopg2 connection from environment variables."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
    )


# ── FX Rate Loader ────────────────────────────────────────────────────────────

def load_fx_rates(conn, fx_df, batch_size=10_000):
    """
    Insert FX rate rows into raw.fx_rate.

    Expected columns in fx_df:
        fx_timestamp, base_cncy, quote_cncy, rate

    Uses ON CONFLICT DO NOTHING — safe to re-run without duplicates.
    fx_rate_id and ingestion_timestamp are DB-generated defaults.
    source defaults to 'api' at DB level; override by passing a 'source' column.

    Args:
        conn:       psycopg2 connection
        fx_df:      pd.DataFrame
        batch_size: rows per execute_values call

    Returns:
        Total number of rows processed (including conflicts skipped).
    """
    has_source = "source" in fx_df.columns

    if has_source:
        sql = """
            INSERT INTO raw.fx_rate
                (base_cncy, quote_cncy, fx_timestamp, rate, source)
            VALUES %s
            ON CONFLICT ON CONSTRAINT idx_fx_rate_cncy_ts DO NOTHING
        """
        cols = ["base_cncy", "quote_cncy", "fx_timestamp", "rate", "source"]
    else:
        sql = """
            INSERT INTO raw.fx_rate
                (base_cncy, quote_cncy, fx_timestamp, rate)
            VALUES %s
            ON CONFLICT ON CONSTRAINT idx_fx_rate_cncy_ts DO NOTHING
        """
        cols = ["base_cncy", "quote_cncy", "fx_timestamp", "rate"]

    rows_list = list(fx_df[cols].itertuples(index=False, name=None))
    total = len(rows_list)
    inserted = 0

    with conn.cursor() as cur:
        for i in range(0, total, batch_size):
            batch = rows_list[i : i + batch_size]
            execute_values(cur, sql, batch)
            inserted += len(batch)
            logger.info(f"fx_rate: inserted batch {i}–{i + len(batch)} ({inserted}/{total})")

    conn.commit()
    logger.info(f"fx_rate: load complete — {total} rows processed")
    return total


# ── Transaction Loader ────────────────────────────────────────────────────────

def load_transactions(conn, tx_df, batch_size=10_000, batch_id=None):
    """
    Insert transaction rows into raw.transaction_event.

    Expected columns in tx_df:
        tx_id, c_id, base_cncy, quote_cncy, amount, fee_amount, tx_timestamp

    tx_id must be a UUID string — generated in transactions.py.
    ingestion_timestamp is a DB default.

    Args:
        conn:       psycopg2 connection
        tx_df:      pd.DataFrame
        batch_size: rows per execute_values call
        batch_id:   optional UUID string identifying this pipeline run;
                    stamped on every row for Phase 1 ML grouping.
                    If None, the DB column default (NULL) is used.

    Returns:
        Total number of rows processed.
    """
    df = tx_df.copy()
    df["batch_id"] = batch_id  # None -> NULL in DB; consistent across all rows

    sql = """
        INSERT INTO raw.transaction_event
            (tx_id, c_id, base_cncy, quote_cncy, amount, fee_amount,
             tx_timestamp, batch_id)
        VALUES %s
        ON CONFLICT (tx_id) DO NOTHING
    """

    cols = [
        "tx_id", "c_id", "base_cncy", "quote_cncy",
        "amount", "fee_amount", "tx_timestamp", "batch_id"
    ]

    # Validate against original cols minus batch_id (we added that ourselves)
    required = [c for c in cols if c != "batch_id"]
    missing = [c for c in required if c not in tx_df.columns]
    if missing:
        raise ValueError(f"tx_df is missing required columns: {missing}")

    rows_list = list(df[cols].itertuples(index=False, name=None))
    total = len(rows_list)
    inserted = 0

    with conn.cursor() as cur:
        for i in range(0, total, batch_size):
            batch = rows_list[i : i + batch_size]
            execute_values(cur, sql, batch)
            inserted += len(batch)
            logger.info(f"transaction_event: inserted batch {i}–{i + len(batch)} ({inserted}/{total})")

    conn.commit()
    logger.info(f"transaction_event: load complete — {total} rows processed")
    return total


# ── Expense Event Loader ──────────────────────────────────────────────────────

def load_expense_events(conn, expense_df, batch_size=10_000):
    """
    Insert expense event rows into raw.expense_event.

    Expected columns in expense_df:
        expense_id, c_id, cncy, expense_timestamp, amount, category_id

    expense_id must be a UUID string.
    ingestion_timestamp is a DB default.
    cncy is expected to be 'USD' for all rows until multi-currency support
    is implemented (BR-022).

    Args:
        conn:        psycopg2 connection
        expense_df:  pd.DataFrame
        batch_size:  rows per execute_values call

    Returns:
        Total number of rows processed.
    """
    sql = """
        INSERT INTO raw.expense_event
            (expense_id, c_id, cncy, expense_timestamp, amount, category_id)
        VALUES %s
        ON CONFLICT (expense_id) DO NOTHING
    """

    cols = [
        "expense_id", "c_id", "cncy",
        "expense_timestamp", "amount", "category_id"
    ]

    missing = [c for c in cols if c not in expense_df.columns]
    if missing:
        raise ValueError(f"expense_df is missing required columns: {missing}")

    rows_list = list(expense_df[cols].itertuples(index=False, name=None))
    total = len(rows_list)
    inserted = 0

    with conn.cursor() as cur:
        for i in range(0, total, batch_size):
            batch = rows_list[i : i + batch_size]
            execute_values(cur, sql, batch)
            inserted += len(batch)
            logger.info(f"expense_event: inserted batch {i}–{i + len(batch)} ({inserted}/{total})")

    conn.commit()
    logger.info(f"expense_event: load complete — {total} rows processed")
    return total


# ── Convenience: load all raw tables ─────────────────────────────────────────

def load_all(conn, fx_df, tx_df, expense_df=None, batch_size=10_000, batch_id=None):
    """
    Load FX rates, transactions, and optionally expense events in one call.

    Insertion order:
        1. fx_rate          — must exist before transform joins on FX timestamps
        2. transaction_event
        3. expense_event    — optional; skipped if expense_df is None

    expense_df is optional so that callers which do not yet generate expense
    data (e.g. --dry-run, --clean, or test harnesses) do not need to change
    their call signature.

    Args:
        conn:        psycopg2 connection
        fx_df:       pd.DataFrame — FX rate rows
        tx_df:       pd.DataFrame — transaction rows
        expense_df:  pd.DataFrame | None — expense rows (omit to skip)
        batch_size:  rows per execute_values call
        batch_id:    optional UUID string — forwarded to load_transactions()

    Returns:
        dict with row counts:
            {"fx_rates": n, "transactions": n, "expenses": n}
        "expenses" is 0 when expense_df is None.
    """
    logger.info("Starting load_all...")

    fx_count  = load_fx_rates(conn, fx_df, batch_size=batch_size)
    tx_count  = load_transactions(conn, tx_df, batch_size=batch_size, batch_id=batch_id)

    exp_count = 0
    if expense_df is not None:
        exp_count = load_expense_events(conn, expense_df, batch_size=batch_size)

    logger.info(
        f"load_all complete — "
        f"fx: {fx_count}, tx: {tx_count}, expenses: {exp_count}"
    )
    return {"fx_rates": fx_count, "transactions": tx_count, "expenses": exp_count}