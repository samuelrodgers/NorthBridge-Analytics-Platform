# main.py
# Orchestration only — no business logic here.
# Flow: generate FX → generate transactions → load both into raw schema.

import logging
from datetime import datetime, timedelta, timezone

from config import CURRENCIES, CURRENCY_CODES
from synthetic_fx import generate_all_fx_series
from transactions import generate_transactions
from loader import get_connection, load_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


def run(n_transactions=10_000, window_minutes=10, batch_size=10_000):
    """
    Generate synthetic FX and transaction data and load into raw schema.

    Args:
        n_transactions: number of transaction rows to generate
        window_minutes: length of the synthetic time window
        batch_size:     rows per DB insert batch (tune for memory vs. throughput)
    """
    start = datetime.now(timezone.utc)
    end   = start + timedelta(minutes=window_minutes)

    logger.info(f"Window: {start.isoformat()} → {end.isoformat()}")
    logger.info(f"Generating {n_transactions:,} transactions over {window_minutes}min window...")

    # ── Generate ───────────────────────────────────────────────────────────────
    logger.info("Generating FX series...")
    fx = generate_all_fx_series(start, end, CURRENCY_CODES)

    logger.info("Generating transactions...")
    tx = generate_transactions(start, end, n_transactions=n_transactions)

    logger.info(f"FX rows: {len(fx):,} | TX rows: {len(tx):,}")

    # ── Load ───────────────────────────────────────────────────────────────────
    logger.info("Connecting to database...")
    conn = get_connection()

    try:
        counts = load_all(conn, fx, tx, batch_size=batch_size)
        logger.info(
            f"✅ Load complete — "
            f"fx_rate: {counts['fx_rates']:,} rows, "
            f"transaction_event: {counts['transactions']:,} rows"
        )
    finally:
        conn.close()

    return counts


if __name__ == "__main__":
    run()