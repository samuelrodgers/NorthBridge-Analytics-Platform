# live_synthetic.py
# Continuously writes synthetic FX rates to raw.fx_rate every 5 seconds.
#
# Uses the same GBM model as synthetic_fx.py but runs as a persistent service
# rather than a batch generator — one new tick per currency pair per loop,
# written to the DB so the frontend 5s refresh always has fresh data.
#
# Starting rates are read from config.CURRENCIES (fx_start_rate) so they
# stay in sync with the batch pipeline's starting point.
#
# Usage:
#   python live_synthetic.py
#
# Stop with Ctrl+C or SIGTERM (graceful shutdown).

import os
import time
import math
import signal
import logging
from datetime import datetime, timezone

import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

from config import CURRENCIES

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'), override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

POLL_INTERVAL = 5       # seconds between ticks
VOLATILITY    = 0.0003  # per-step GBM vol — small realistic movements at 5s
QUOTE_CCY     = "USD"

# Build per-currency state: starting rate + independent RNG (same seeds as
# synthetic_fx.py so historical and live data are statistically consistent)
_pairs = {
    ccy: {
        "rate": meta["fx_start_rate"],
        "rng":  np.random.default_rng(seed=i),
    }
    for i, (ccy, meta) in enumerate(CURRENCIES.items())
    if ccy != QUOTE_CCY
}

logger.info(f"Tracking {len(_pairs)} currency pairs vs {QUOTE_CCY}")


# ── GBM tick ──────────────────────────────────────────────────────────────────

def next_tick() -> dict:
    """Apply one GBM step to every currency and return {ccy: new_rate}."""
    result = {}
    for ccy, state in _pairs.items():
        shock = state["rng"].normal(loc=0.0, scale=VOLATILITY)
        state["rate"] = round(state["rate"] * math.exp(shock), 7)
        result[ccy] = state["rate"]
    return result


# ── Database ──────────────────────────────────────────────────────────────────

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5433)),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "superset_admin"),
        password=os.getenv("DB_PASS", ""),
    )


def insert_tick(conn, rates: dict, ts: datetime) -> int:
    rows = [(base, QUOTE_CCY, ts, rate) for base, rate in rates.items()]
    sql = """
        INSERT INTO raw.fx_rate (base_cncy, quote_cncy, fx_timestamp, rate)
        VALUES %s
        ON CONFLICT ON CONSTRAINT idx_fx_rate_cncy_ts DO NOTHING
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
        inserted = cur.rowcount
    conn.commit()
    return inserted


# ── Main loop ─────────────────────────────────────────────────────────────────

shutdown_requested = False


def _handle_signal(signum, frame):
    global shutdown_requested
    logger.info(f"Received signal {signum} — shutting down gracefully")
    shutdown_requested = True


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def run():
    logger.info(f"Starting live synthetic FX ingestion (every {POLL_INTERVAL}s)")

    conn = get_connection()
    logger.info("Connected to database")

    try:
        while not shutdown_requested:
            loop_start = time.time()

            ts    = datetime.now(timezone.utc)
            rates = next_tick()

            try:
                inserted = insert_tick(conn, rates, ts)
                sample = {k: rates[k] for k in list(rates)[:3]}
                logger.info(f"Tick at {ts.isoformat()} | inserted={inserted} | {sample}")
            except psycopg2.Error as e:
                logger.error(f"DB insert failed: {e}")
                try:
                    conn.close()
                    conn = get_connection()
                    logger.info("Reconnected to database")
                except Exception as re:
                    logger.error(f"Reconnect failed: {re}")

            elapsed = time.time() - loop_start
            sleep_time = max(0, POLL_INTERVAL - elapsed)
            if sleep_time > 0 and not shutdown_requested:
                time.sleep(sleep_time)

    finally:
        conn.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    run()
