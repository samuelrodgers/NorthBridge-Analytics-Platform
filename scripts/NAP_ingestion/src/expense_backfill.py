# expense_backfill.py
# One-time historical expense backfill.
# Generates synthetic expense events across a historical date range at a
# density that produces expenses at roughly 15% of total seeded revenue.
#
# Usage:
#   python expense_backfill.py
#   python expense_backfill.py --start 2021-01-01 --end 2026-04-18 --per-company-month 900
#
# After this completes, run:
#   python transform.py --seed
# to promote raw.expense_event rows into analytics.f_expense and rebuild f_industry.

import argparse
import uuid
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from psycopg2.extras import execute_values

from config import COMPANIES, EXPENSE_CATEGORIES
from transform import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SQL_INSERT = """
    INSERT INTO raw.expense_event
        (expense_id, c_id, cncy, expense_timestamp, amount, category_id)
    VALUES %s
    ON CONFLICT (expense_id) DO NOTHING
"""

def run_backfill(start: datetime, end: datetime, per_company_month: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    category_ids = list(EXPENSE_CATEGORIES.values())
    conn = get_connection()
    total = 0

    current = start
    while current < end:
        next_month = min(current + timedelta(days=30), end)
        window_seconds = (next_month - current).total_seconds()

        rows = []
        for meta in COMPANIES.values():
            for _ in range(per_company_month):
                offset = rng.uniform(0, window_seconds)
                expense_ts = current + timedelta(seconds=float(offset))
                amount = round(float(rng.lognormal(mean=7.6, sigma=0.8)), 4)
                category_id = str(rng.choice(category_ids))
                rows.append((
                    str(uuid.uuid4()),
                    meta["c_uuid"],
                    "USD",
                    expense_ts,
                    amount,
                    category_id,
                ))

        with conn.cursor() as cur:
            execute_values(cur, SQL_INSERT, rows)
        conn.commit()
        total += len(rows)
        logger.info(f"{current.date()} → {next_month.date()}: {len(rows)} rows inserted (total: {total:,})")
        current = next_month

    conn.close()
    logger.info(f"Backfill complete — {total:,} expense events inserted into raw.expense_event")
    logger.info("Run `python transform.py --seed` to promote to analytics.f_expense and rebuild f_industry.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Historical expense backfill")
    parser.add_argument("--start", default="2021-01-01", help="Start date YYYY-MM-DD (default: 2021-01-01)")
    parser.add_argument("--end",   default="2026-04-18", help="End date YYYY-MM-DD (default: 2026-04-18)")
    parser.add_argument("--per-company-month", type=int, default=900,
                        help="Expense events per company per 30-day window (default: 900 → ~15%% of revenue)")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end   = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    logger.info(f"Backfilling expenses: {start.date()} → {end.date()}, {args.per_company_month} events/company/month")
    run_backfill(start, end, args.per_company_month)
