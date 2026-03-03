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
from synthetic_fx import generate_all_fx_series
from transactions import generate_transactions
from loader import get_connection, load_all
import transform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


def _timer():
    """Return current time in seconds for benchmarking."""
    return time.perf_counter()


def run(n_transactions=10_000, window_minutes=10, batch_size=10_000,
        noise_level="medium", benchmark=False):
    """
    Generate synthetic FX and transaction data, load into raw schema,
    and promote to analytics schema.

    Args:
        n_transactions: number of transaction rows to generate
        window_minutes: length of the synthetic time window
        batch_size:     rows per DB insert batch
        noise_level:    "low", "medium", or "high"
        benchmark:      if True, print timing summary at end
    """
    timings = {}

    start = datetime.now(timezone.utc)
    end   = start + timedelta(minutes=window_minutes)

    logger.info(f"Window: {start.isoformat()} → {end.isoformat()}")
    logger.info(f"Generating {n_transactions:,} transactions over {window_minutes}min window...")

    # ── Generate ───────────────────────────────────────────────────────────────
    t0 = _timer()
    logger.info("Generating FX series...")
    fx = generate_all_fx_series(start, end, CURRENCY_CODES)

    logger.info("Generating transactions...")
    tx = generate_transactions(start, end, n_transactions=n_transactions)
    timings["generate"] = _timer() - t0

    logger.info(f"FX rows: {len(fx):,} | TX rows: {len(tx):,}")

    # ── Noise ──────────────────────────────────────────────────────────────────
    t0 = _timer()
    logger.info(f"Adding noise at {noise_level} level...")
    noisy_tx = apply_noise(tx, noise_level)
    timings["noise"] = _timer() - t0

    logger.info(f"TX rows after noise: {len(noisy_tx):,} | (original: {len(tx):,})")

    # ── Normalize ──────────────────────────────────────────────────────────────
    t0 = _timer()
    logger.info(f"Normalizing {len(noisy_tx):,} rows...")
    cleaned_tx, quarantined, stats = normalize_receipts(noisy_tx, collect_stats=benchmark)
    timings["normalize"] = _timer() - t0

    if stats:
        validate_normalization_report(stats)
    logger.info(f"{len(cleaned_tx):,} clean rows | {len(quarantined):,} quarantined rows")

    # ── Load raw ───────────────────────────────────────────────────────────────
    t0 = _timer()
    logger.info("Connecting to database...")
    conn = get_connection()
    try:
        counts = load_all(conn, fx, cleaned_tx, batch_size=batch_size)
        logger.info(
            f"✅ Load complete — "
            f"fx_rate: {counts['fx_rates']:,} rows, "
            f"transaction_event: {counts['transactions']:,} rows"
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
        transform.run_transform(transform_conn)
    finally:
        transform_conn.close()
    timings["transform"] = _timer() - t0

    # ── Benchmark summary ──────────────────────────────────────────────────────
    if benchmark:
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
        print(f"\n  Rows generated:   {n_transactions:>10,}")
        print(f"  Rows clean:       {len(cleaned_tx):>10,}")
        print(f"  Rows quarantined: {len(quarantined):>10,}")
        print("=" * 60)

    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NAP pipeline runner")
    parser.add_argument(
        "-n", "--transactions",
        type=int,
        default=10_000,
        help="Number of transactions to generate (default: 10000)"
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Print timing summary after run"
    )
    parser.add_argument(
        "--noise",
        choices=["low", "medium", "high"],
        default="medium",
        help="Noise level to apply (default: medium)"
    )
    args = parser.parse_args()

    run(
        n_transactions=args.transactions,
        benchmark=args.benchmark,
        noise_level=args.noise,
    )