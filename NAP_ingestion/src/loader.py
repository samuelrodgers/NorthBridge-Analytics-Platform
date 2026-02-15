# loader.py
# Inserts generated DataFrames into raw.fx_rate and raw.transaction_event.
#
# Design principles:
#   - Batch inserts via execute_values() — efficient at millions of rows
#   - ON CONFLICT DO NOTHING on fx_rate (unique constraint on timestamp+pair)
#   - Explicit column lists — never rely on column order matching
#   - Connection passed in, not created here — caller controls lifecycle
#   - No transform logic — that belongs in pipeline.py

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
    """
    has_source = "source" in fx_df.columns

    if has_source:
        sql = """
            INSERT INTO raw.fx_rate
                (base_cncy, quote_cncy, fx_timestamp, rate, source)
            VALUES %s
            ON CONFLICT ON CONSTRAINT fx_unique DO NOTHING
        """
        cols = ["base_cncy", "quote_cncy", "fx_timestamp", "rate", "source"]
    else:
        sql = """
            INSERT INTO raw.fx_rate
                (base_cncy, quote_cncy, fx_timestamp, rate)
            VALUES %s
            ON CONFLICT ON CONSTRAINT fx_unique DO NOTHING
        """
        cols = ["base_cncy", "quote_cncy", "fx_timestamp", "rate"]

    rows = fx_df[cols].itertuples(index=False, name=None)
    rows_list = list(rows)
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

def load_transactions(conn, tx_df, batch_size=10_000):
    """
    Insert transaction rows into raw.transaction_event.

    Expected columns in tx_df:
        tx_id, c_id, base_cncy, quote_cncy, amount, fee_amount,
        tx_timestamp, source

    tx_id must be a UUID string — generated in transactions.py.
    ingestion_timestamp is a DB default.

    Args:
        conn:       psycopg2 connection
        tx_df:      pd.DataFrame
        batch_size: rows per execute_values call
    """
    sql = """
        INSERT INTO raw.transaction_event
            (tx_id, c_id, base_cncy, quote_cncy, amount, fee_amount,
             tx_timestamp)
        VALUES %s
        ON CONFLICT (tx_id) DO NOTHING
    """

    cols = [
        "tx_id", "c_id", "base_cncy", "quote_cncy",
        "amount", "fee_amount", "tx_timestamp"
    ]

    # Validate required columns are present
    missing = [c for c in cols if c not in tx_df.columns]
    if missing:
        raise ValueError(f"tx_df is missing required columns: {missing}")

    rows_list = list(tx_df[cols].itertuples(index=False, name=None))
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


# ── Convenience: load both ────────────────────────────────────────────────────

def load_all(conn, fx_df, tx_df, batch_size=10_000):
    """
    Load FX rates then transactions in a single call.
    FX must be loaded first — pipeline.py joins on fx rates by timestamp.

    Returns:
        dict with row counts: {"fx_rates": n, "transactions": n}
    """
    logger.info("Starting load_all...")

    fx_count = load_fx_rates(conn, fx_df, batch_size=batch_size)
    tx_count = load_transactions(conn, tx_df, batch_size=batch_size)

    logger.info(f"load_all complete — fx: {fx_count}, tx: {tx_count}")
    return {"fx_rates": fx_count, "transactions": tx_count}