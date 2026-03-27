# main.py
# Orchestration only — no business logic here.
# Flow: generate FX → generate transactions → noise → normalize → load raw → transform analytics
#
# Usage:
#   python main.py                  # 10K rows, medium noise
#   python main.py -n 1000          # 1K rows
#   python main.py -n 1000000       # 1M rows
#   python main.py -n 1000 --benchmark  # 1K rows + timing summary

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from config import CURRENCY_CODES
from noise import apply_noise
from pipeline import normalize_receipts, validate_normalization_report
import fx_source
from transactions import generate_transactions
from loader import get_connection, load_all
import transform
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


def _timer():
    """Return current time in seconds for benchmarking."""
    return time.perf_counter()


def _print_benchmark_summary(
    timings: dict,
    n_transactions: int,
    clean_count: int,
    quarantine_count: int,
    transform_counts: dict | None,
):
    """
    Print a formatted timing and row-count summary after a benchmarked run.

    Args:
        timings:          dict of stage name → elapsed seconds
        n_transactions:   number of transactions originally generated
        clean_count:      rows that passed normalization
        quarantine_count: rows quarantined during normalization
        transform_counts: dict returned by transform.run_transform(), or None
                          if the transform step was skipped (dry_run / clean).
    """
    total = sum(timings.values())
    print("\n" + "=" * 60)
    print("BENCHMARK TIMING SUMMARY")
    print("=" * 60)
    print(f"  {'Stage':<20} {'Time (s)':>10}  {'% of total':>10}")
    print(f"  {'-'*20}  {'-'*10}  {'-'*10}")
    for stage, secs in timings.items():
        pct = (secs / total) * 100
        print(f"  {stage:<20} {secs:>10.3f}  {pct:>9.1f}%")
    print(f"  {'':20} {'----------':>10}")
    print(f"  {'TOTAL':<20} {total:>10.3f}")

    print(f"\n  --- Pipeline row counts ---")
    print(f"\n  FX source:        {fx_source.get_source():>10}")
    print(f"  Rows generated:   {n_transactions:>10,}")
    print(f"  Rows clean:       {clean_count:>10,}")
    print(f"  Rows quarantined: {quarantine_count:>10,}")

    if transform_counts:
        print(f"\n  --- Analytics schema counts (this run) ---")
        print(f"  f_fx_rate rows:   {transform_counts.get('fx_rates',      0):>10,}")
        print(f"  d_time rows:      {transform_counts.get('d_time',         0):>10,}")
        print(f"  f_transaction:    {transform_counts.get('transactions',   0):>10,}")
        print(f"  f_conversion:     {transform_counts.get('conversions',    0):>10,}")
        print(f"  raw.expense_event:{transform_counts.get('raw_expenses',   0):>10,}")
        print(f"  f_expense:        {transform_counts.get('expenses',       0):>10,}")
        print(f"  f_industry rows:  {transform_counts.get('industry_rows',  0):>10,}")

    print("=" * 60)


def run(n_transactions=10_000, window_minutes=10, batch_size=10_000,
        noise_level="medium", benchmark=False, dry_run=False, clean=False):
    """
    Generate synthetic FX and transaction data, load into raw schema,
    and promote to analytics schema.

    Args:
        n_transactions: number of transaction rows to generate
        window_minutes: length of the synthetic time window
        batch_size:     rows per DB insert batch
        noise_level:    "low", "medium", or "high"
        benchmark:      if True, print timing and row-count summary at end
        dry_run:        if True, skip DB load and transform entirely
        clean:          if True, skip noise injection and normalization

    Returns:
        dict with raw load counts and transform counts, or None on dry_run.
    """
    timings = {}
    transform_counts = None

    start = datetime.now(timezone.utc)
    end   = start + timedelta(minutes=window_minutes)

    logger.info(f"Window: {start.isoformat()} → {end.isoformat()}")

    # Unique identifier for this pipeline run — stamped on every raw row
    # so Phase 1 analysis can group failures and clean rows by ingestion batch.
    import uuid as _uuid
    batch_id = str(_uuid.uuid4())
    logger.info(f"Batch ID: {batch_id}")

    logger.info(f"Generating {n_transactions:,} transactions over {window_minutes}min window...")

    # ── Generate ───────────────────────────────────────────────────────────────
    t0 = _timer()
    logger.info(f"FX source: {fx_source.get_source()!r}")
    logger.info("Generating FX series...")

    # In live mode get_fx_rates() reads the latest ticks from raw.fx_rate,
    # so a DB connection is needed at this point. In synthetic mode the
    # connection argument is ignored and can be None.
    _fx_conn = get_connection() if fx_source.get_source() == "live" else None
    try:
        fx = fx_source.get_fx_rates(start_ts=start, end_ts=end, conn=_fx_conn)
    finally:
        if _fx_conn is not None:
            _fx_conn.close()

    if len(fx) == 0:
        logger.error(
            "FX source returned no rows. "
            "If source is 'live', confirm live_fx.py is running and has "
            "inserted rows into raw.fx_rate before starting a pipeline run."
        )
        return None

    logger.info("Generating transactions...")
    tx = generate_transactions(start, end, n_transactions=n_transactions)
    timings["generate"] = _timer() - t0

    logger.info(f"FX rows: {len(fx):,} | TX rows: {len(tx):,}")

    # ── Noise + Normalize ─────────────────────────────────────────────────────
    if clean:
        logger.info("Clean mode — skipping noise and normalization...")
        cleaned_tx = tx
        quarantined = []
        stats = None
    else:
        t0 = _timer()
        logger.info(f"Adding noise at {noise_level} level...")
        noisy_tx = apply_noise(tx, noise_level)
        timings["noise"] = _timer() - t0
        logger.info(f"TX rows after noise: {len(noisy_tx):,} | (original: {len(tx):,})")

        t0 = _timer()
        logger.info(f"Normalizing {len(noisy_tx):,} rows...")
        cleaned_tx, quarantined, stats = normalize_receipts(noisy_tx, collect_stats=benchmark)
        timings["normalize"] = _timer() - t0

        if stats:
            validate_normalization_report(stats)
        logger.info(f"{len(cleaned_tx):,} clean rows | {len(quarantined):,} quarantined rows")

    # ── Dry run stops here ─────────────────────────────────────────────────────
    if dry_run:
        logger.info("Dry run complete — skipping DB load and transform.")
        if benchmark:
            _print_benchmark_summary(
                timings, n_transactions, len(cleaned_tx), len(quarantined),
                transform_counts=None,
            )
        return None

    # ── Load raw ───────────────────────────────────────────────────────────────
    # Expense generation happens inside transform.run_transform() so that it
    # runs within the analytics batch transaction. load_all handles FX rates,
    # transactions, and quarantine rows; expense_df is omitted here.
    t0 = _timer()
    logger.info("Connecting to database...")
    conn = get_connection()
    try:
        raw_counts = load_all(
            conn, fx, cleaned_tx,
            quarantine_df=quarantined if not clean else None,
            batch_size=batch_size,
            batch_id=batch_id,
        )
        logger.info(
            f"✅ Load complete — "
            f"fx_rate: {raw_counts['fx_rates']:,} rows, "
            f"transaction_event: {raw_counts['transactions']:,} rows, "
            f"quarantine_event: {raw_counts['quarantine']:,} rows"
        )
    finally:
        conn.close()
    timings["load_raw"] = _timer() - t0

    # ── Transform ──────────────────────────────────────────────────────────────
    t0 = _timer()
    logger.info("Starting analytics transform...")
    transform_conn = transform.get_connection()
    try:
        transform.run_seed(transform_conn)
        transform_counts = transform.run_transform(transform_conn)
    finally:
        transform_conn.close()
    timings["transform"] = _timer() - t0

    # ── Summary ────────────────────────────────────────────────────────────────
    if benchmark:
        _print_benchmark_summary(
            timings, n_transactions, len(cleaned_tx), len(quarantined),
            transform_counts=transform_counts,
        )

    # Merge raw load counts and transform counts for the return value so
    # callers (e.g. the dashboard API) have a single dict to work with.
    return {**raw_counts, **(transform_counts or {})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NAP pipeline — production CRON entry point")
    parser.add_argument(
        "-n", "--transactions",
        type=int,
        default=10_000,
        help="Number of transactions to generate (default: 10000)"
    )
    parser.add_argument(
        "--fx-source",
        choices=["synthetic", "live"],
        default=None,
        help=(
            "FX rate source: 'synthetic' (default) generates rates locally; "
            "'live' reads from raw.fx_rate populated by live_fx.py"
        )
    )
    args = parser.parse_args()

    if args.fx_source:
        fx_source.set_source(args.fx_source)

    run(n_transactions=args.transactions)