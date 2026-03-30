# seed.py
# Local development entry point for the NAP pipeline.
# Exposes all run() options as CLI flags for building and testing
# different database states, including historical date-range seeding.
#
# Usage:
#   python seed.py                                    # 10K rows, medium noise, recent window
#   python seed.py -n 500 --noise high                # 500 rows, heavy noise
#   python seed.py -n 1000 --clean                    # 1K clean rows, no noise
#   python seed.py -n 500 --dry-run                   # normalize only, skip DB
#   python seed.py -n 1000 --benchmark                # run with timing summary
#   python seed.py --fx-source live                   # use live FX rates from DB
#
#   # Historical seeding — spoof tx_timestamps over a past date range:
#   python seed.py --years 2 -n 50000                 # 2-year range, 50K rows, 1 batch
#   python seed.py --years 3 -n 20000 --batches 36    # 3 years, 36 monthly batches of 20K
#   python seed.py --start-date 2022-01-01 --end-date 2024-12-31 --batches 12 -n 10000
#
# --batches splits the date range into equal slices and calls run() once per slice.
# More batches → more realistic spread of ingestion_timestamps, but slower overall.
#
# Production CRON uses main.py directly — do not use this file on the server.

import argparse
from datetime import datetime, timedelta, timezone

import fx_source
from main import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NAP pipeline — local dev / seeding")
    parser.add_argument(
        "-n", "--transactions",
        type=int,
        default=10_000,
        help="Number of transactions to generate per batch (default: 10000)"
    )
    parser.add_argument(
        "--noise",
        choices=["low", "medium", "high"],
        default="medium",
        help="Noise level to apply (default: medium)"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Skip noise and normalization, load clean data directly"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run Python pipeline only, skip DB load and transform"
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Print timing and row-count summary after each batch"
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
    parser.add_argument(
        "--skip-transform",
        action="store_true",
        default=False,
        help=(
            "Load raw data only; skip the analytics transform. "
            "Automatically enabled for historical range runs. "
            "Run `python transform.py` once after all batches complete."
        )
    )

    # ── Historical date range ────────────────────────────────────────────────
    date_group = parser.add_argument_group(
        "historical seeding",
        "Override the default recent-window with an explicit date range. "
        "Use --years as a shortcut, or --start-date + --end-date for full control."
    )
    date_group.add_argument(
        "--years",
        type=int,
        default=None,
        metavar="N",
        help="Seed N years of history ending today (e.g. --years 3)"
    )
    date_group.add_argument(
        "--start-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Explicit range start date (UTC). Requires --end-date."
    )
    date_group.add_argument(
        "--end-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Explicit range end date (UTC). Requires --start-date."
    )
    date_group.add_argument(
        "--batches",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Split the date range into N equal slices and run the pipeline "
            "once per slice (default: 1). Each batch loads --transactions rows."
        )
    )

    args = parser.parse_args()

    # Validate date args
    if args.start_date and not args.end_date:
        parser.error("--start-date requires --end-date")
    if args.end_date and not args.start_date:
        parser.error("--end-date requires --start-date")

    if args.fx_source:
        fx_source.set_source(args.fx_source)

    # ── Determine date range ─────────────────────────────────────────────────
    if args.years or (args.start_date and args.end_date):
        if args.start_date and args.end_date:
            # Explicit range takes priority over --years
            range_end   = datetime.fromisoformat(args.end_date).replace(tzinfo=timezone.utc)
            range_start = datetime.fromisoformat(args.start_date).replace(tzinfo=timezone.utc)
        else:
            range_end   = datetime.now(timezone.utc).replace(
                              hour=0, minute=0, second=0, microsecond=0)
            range_start = range_end - timedelta(days=365 * args.years)

        n_batches     = max(1, args.batches)
        total_seconds = (range_end - range_start).total_seconds()
        slice_seconds = total_seconds / n_batches

        # Historical runs always skip per-batch transform — run transform.py once at the end.
        skip_tx = True
        if not args.dry_run:
            print(f"  Transform will be skipped per batch. Run `python transform.py` after this completes.")

        print(f"Historical seed: {range_start.date()} to {range_end.date()} "
              f"| {n_batches} batch(es) x {args.transactions:,} rows each")

        for i in range(n_batches):
            batch_start = range_start + timedelta(seconds=i * slice_seconds)
            batch_end   = range_start + timedelta(seconds=(i + 1) * slice_seconds)
            print(f"\n[{i + 1}/{n_batches}] {batch_start.date()} to {batch_end.date()}")
            run(
                n_transactions=args.transactions,
                noise_level=args.noise,
                clean=args.clean,
                dry_run=args.dry_run,
                benchmark=args.benchmark,
                start_ts=batch_start,
                end_ts=batch_end,
                skip_transform=skip_tx,
            )

        if not args.dry_run:
            print(f"\nAll {n_batches} batches loaded. Run `python transform.py --seed` to promote to analytics schema."  )

    else:
        # Default: recent-window mode (same as before)
        run(
            n_transactions=args.transactions,
            noise_level=args.noise,
            clean=args.clean,
            dry_run=args.dry_run,
            benchmark=args.benchmark,
            skip_transform=args.skip_transform,
        )
