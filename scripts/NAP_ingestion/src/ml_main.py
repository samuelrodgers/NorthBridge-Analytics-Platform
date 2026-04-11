# ml_main.py
# ML-specific pipeline entry point.
#
# Purpose: runs one or more pipeline batches with explicit noise/scale control
# and writes a raw.pipeline_run record after each batch so that ML analysis
# can join transaction and quarantine data back to the conditions that produced
# them (noise level, row count, timing).
#
# This file is intentionally separate from main.py so that the production
# CRON entry point is never touched during ML prep work.
#
# Usage:
#   python ml_main.py                              # 1 batch, 500 rows, medium noise
#   python ml_main.py -n 2000 --noise-level high   # 2000 rows, high noise
#   python ml_main.py --batches 3 -n 1000          # 3 sequential batches, 1000 rows each
#   python ml_main.py --batches 5 --noise-level low --notes "baseline sweep"

import argparse
import logging
import time
from datetime import datetime, timezone

import fx_source as _fx_source
from loader import get_connection, load_pipeline_run
from main import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


# ── Single-batch runner ───────────────────────────────────────────────────────

def run_batch(
    n_transactions: int,
    noise_level: str,
    fx_source_name: str,
    notes: str | None,
    batch_number: int,
    total_batches: int,
) -> dict:
    """
    Execute one pipeline batch and write a raw.pipeline_run record.

    Args:
        n_transactions:  rows to generate
        noise_level:     'low' | 'medium' | 'high'
        fx_source_name:  'synthetic' | 'live'
        notes:           optional annotation stored in pipeline_run.notes
        batch_number:    1-based index for log messages
        total_batches:   total count for log messages

    Returns:
        dict with keys:
            batch_id, noise_level, n_transactions, fx_source,
            clean_count, quarantine_count, duration_seconds
        Returns an error-flagged dict if run() returns None.
    """
    logger.info(
        f"[{batch_number}/{total_batches}] Starting batch — "
        f"{n_transactions:,} rows, {noise_level} noise, fx={fx_source_name}"
    )

    run_timestamp = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    result = run(
        n_transactions=n_transactions,
        noise_level=noise_level,
    )

    duration = round(time.perf_counter() - t0, 2)

    if result is None:
        logger.error(
            f"[{batch_number}/{total_batches}] run() returned None — "
            "FX source may have produced no rows, or dry_run was active. "
            "Skipping pipeline_run record."
        )
        return {
            "batch_id":         None,
            "noise_level":      noise_level,
            "n_transactions":   n_transactions,
            "fx_source":        fx_source_name,
            "clean_count":      None,
            "quarantine_count": None,
            "duration_seconds": duration,
            "error":            True,
        }

    batch_id         = result["batch_id"]
    clean_count      = result.get("transactions", 0)
    quarantine_count = result.get("quarantine",   0)

    meta_conn = get_connection()
    try:
        load_pipeline_run(meta_conn, {
            "batch_id":         batch_id,
            "noise_level":      noise_level,
            "n_transactions":   n_transactions,
            "fx_source":        fx_source_name,
            "run_timestamp":    run_timestamp,
            "duration_seconds": duration,
            "clean_count":      clean_count,
            "quarantine_count": quarantine_count,
            "notes":            notes,
        })
    finally:
        meta_conn.close()

    logger.info(
        f"[{batch_number}/{total_batches}] Batch complete — "
        f"batch_id={batch_id}, "
        f"clean={clean_count:,}, quarantined={quarantine_count:,}, "
        f"duration={duration}s"
    )

    return {
        "batch_id":         batch_id,
        "noise_level":      noise_level,
        "n_transactions":   n_transactions,
        "fx_source":        fx_source_name,
        "clean_count":      clean_count,
        "quarantine_count": quarantine_count,
        "duration_seconds": duration,
        "error":            False,
    }


# ── Summary printer ───────────────────────────────────────────────────────────

def _print_summary(results: list[dict]) -> None:
    """Print a per-batch summary table after all batches complete."""
    print("\n" + "=" * 78)
    print("ML PIPELINE RUN SUMMARY")
    print("=" * 78)
    print(
        f"  {'#':<4} {'batch_id':<38} {'noise':<8} "
        f"{'clean':>8} {'quarantined':>12} {'secs':>7}"
    )
    print(f"  {'-'*4}  {'-'*36}  {'-'*6}  {'-'*8}  {'-'*10}  {'-'*7}")

    total_clean      = 0
    total_quarantine = 0
    total_duration   = 0.0

    for i, r in enumerate(results, start=1):
        bid = r["batch_id"] or "(failed)"
        err = " !" if r.get("error") else ""
        clean = r["clean_count"]      if r["clean_count"]      is not None else "-"
        quar  = r["quarantine_count"] if r["quarantine_count"] is not None else "-"
        dur   = r["duration_seconds"] if r["duration_seconds"] is not None else 0.0

        print(
            f"  {i:<4} {bid:<38} {r['noise_level']:<8} "
            f"{str(clean):>8} {str(quar):>12} {dur:>6.1f}s{err}"
        )

        if isinstance(clean, int):
            total_clean += clean
        if isinstance(quar, int):
            total_quarantine += quar
        total_duration += dur

    print(f"  {'-'*4}  {'-'*36}  {'-'*6}  {'-'*8}  {'-'*10}  {'-'*7}")
    print(
        f"  {'TOTAL':<44} "
        f"{total_clean:>8,} {total_quarantine:>12,} {total_duration:>6.1f}s"
    )

    total_rows = total_clean + total_quarantine
    if total_rows > 0:
        qrate = total_quarantine / total_rows * 100
        print(f"\n  Overall quarantine rate: {qrate:.2f}%")

    errors = sum(1 for r in results if r.get("error"))
    if errors:
        print(f"\n  WARNING: {errors} batch(es) failed — marked with '!' above.")

    print("=" * 78)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "NAP ML pipeline — generates labelled batches and writes "
            "raw.pipeline_run metadata for each run."
        )
    )
    parser.add_argument(
        "-n", "--transactions",
        type=int,
        default=500,
        help="Rows to generate per batch (default: 500)",
    )
    parser.add_argument(
        "--noise-level",
        choices=["low", "medium", "high"],
        default="medium",
        help="Noise injection scale: low=0.5x, medium=1.0x, high=2.0x (default: medium)",
    )
    parser.add_argument(
        "--fx-source",
        choices=["synthetic", "live"],
        default="synthetic",
        help="FX rate source (default: synthetic)",
    )
    parser.add_argument(
        "--batches",
        type=int,
        default=1,
        help="Number of sequential batches to run (default: 1)",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default=None,
        help="Optional annotation stored in pipeline_run.notes for every batch",
    )
    args = parser.parse_args()

    # Set the FX source module-level flag before any calls to run()
    _fx_source.set_source(args.fx_source)

    all_results: list[dict] = []

    for batch_num in range(1, args.batches + 1):
        batch_result = run_batch(
            n_transactions=args.transactions,
            noise_level=args.noise_level,
            fx_source_name=args.fx_source,
            notes=args.notes,
            batch_number=batch_num,
            total_batches=args.batches,
        )
        all_results.append(batch_result)

    _print_summary(all_results)
