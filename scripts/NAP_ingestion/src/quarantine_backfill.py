# quarantine_backfill.py
# Synthetic historical quarantine backfill.
# Generates plausible quarantine records spread across a historical date range
# with ingestion_timestamp matching the synthetic tx window, so the governance
# ingestion timeline and quarantine-by-day charts look populated.
#
# Records are synthetic — tx_ids are random UUIDs not tied to real transactions.
# Failure code distribution matches the observed seed rate (~8.6% quarantine):
#   INVALID_AMOUNT   ~62%  (negatives, parentheses, ambiguous EU decimal)
#   NULL_TIMESTAMP   ~26%  (null timestamps)
#   NULL_COMPANY_ID  ~12%  (null company IDs)
#
# Usage:
#   python quarantine_backfill.py
#   python quarantine_backfill.py --start 2021-01-01 --end 2026-04-18 --per-day 80

import argparse
import uuid
import logging
import random
from datetime import datetime, timedelta, timezone

from psycopg2.extras import execute_values

from config import COMPANIES
from loader import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SQL_INSERT = """
    INSERT INTO raw.quarantine_event
        (quarantine_id, tx_id, c_id, base_cncy, quote_cncy, amount,
         fee_amount, tx_timestamp, failure_code, failure_reason,
         batch_id, dirty_value, ingestion_timestamp)
    VALUES %s
    ON CONFLICT (quarantine_id) DO NOTHING
"""

FAILURE_CODES = [
    # (failure_code, failure_reason, weight, dirty_value_fn)
    (
        "INVALID_AMOUNT",
        "amount is null or non-positive after normalization",
        0.62,
        lambda rng: random.choice([
            f"-{round(rng.uniform(100, 9999), 2)}",
            f"({round(rng.uniform(100, 9999), 2)})",
            f"{round(rng.uniform(10, 999), 2)}".replace(".", ","),
        ]),
    ),
    (
        "NULL_TIMESTAMP",
        "tx_timestamp is null after normalization",
        0.26,
        lambda rng: None,
    ),
    (
        "NULL_COMPANY_ID",
        "c_id is null after normalization",
        0.12,
        lambda rng: None,
    ),
]

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "SGD"]
COMPANY_LIST = list(COMPANIES.values())


def _pick_failure(rng):
    codes, reasons, weights, dirty_fns = zip(*[
        (f[0], f[1], f[2], f[3]) for f in FAILURE_CODES
    ])
    idx = random.choices(range(len(codes)), weights=weights, k=1)[0]
    dirty = dirty_fns[idx](rng)
    return codes[idx], reasons[idx], dirty


def run_backfill(start: datetime, end: datetime, per_day: int, seed: int = 42):
    import numpy as np
    rng_np = np.random.default_rng(seed)
    conn = get_connection()
    total = 0
    synthetic_batch_id = str(uuid.uuid4())

    current = start
    while current < end:
        next_day = min(current + timedelta(days=1), end)
        window_seconds = (next_day - current).total_seconds()

        rows = []
        for _ in range(per_day):
            failure_code, failure_reason, dirty_value = _pick_failure(rng_np)

            offset = rng_np.uniform(0, window_seconds)
            tx_ts = current + timedelta(seconds=float(offset))
            ingestion_ts = tx_ts + timedelta(seconds=float(rng_np.uniform(1, 60)))

            company = random.choice(COMPANY_LIST)
            base_cncy = company["default_cncy"]
            c_id = company["c_uuid"] if failure_code != "NULL_COMPANY_ID" else None
            # INVALID_AMOUNT means normalization produced NULL — store NULL to match
            # what the real pipeline puts in quarantine_event.amount.
            # Other failure types have a valid amount (the transaction amount was fine).
            amount = None if failure_code == "INVALID_AMOUNT" else round(float(rng_np.lognormal(mean=8, sigma=1.2)), 4)

            quarantine_id = str(uuid.uuid5(
                uuid.UUID("a7c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"),
                f"{synthetic_batch_id}:{tx_ts.isoformat()}:{failure_code}:{_}"
            ))

            rows.append((
                quarantine_id,
                str(uuid.uuid4()),   # tx_id
                c_id,
                base_cncy,
                None,                # quote_cncy
                amount,
                None,                # fee_amount
                tx_ts,
                failure_code,
                failure_reason,
                synthetic_batch_id,
                dirty_value,
                ingestion_ts,        # override ingestion_timestamp
            ))

        with conn.cursor() as cur:
            execute_values(cur, SQL_INSERT, rows)
        conn.commit()
        total += len(rows)

        if current.day == 1:
            logger.info(f"{current.date()}: {total:,} quarantine records inserted so far")

        current = next_day

    conn.close()
    logger.info(f"Backfill complete — {total:,} quarantine records inserted")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Historical quarantine backfill")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end",   default="2026-04-18")
    parser.add_argument("--per-day", type=int, default=80,
                        help="Quarantine records per day (default: 80, ~30 days = ~2400 recent records)")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end   = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    logger.info(f"Backfilling quarantine: {start.date()} → {end.date()}, {args.per_day}/day")
    run_backfill(start, end, args.per_day)
