# seed.py
# Local development entry point for the NAP pipeline.
# Exposes all run() options as CLI flags for building and testing
# different database states.
#
# Usage:
#   python seed.py                          # 10K rows, medium noise
#   python seed.py -n 500 --noise high      # 500 rows, heavy noise
#   python seed.py -n 1000 --clean          # 1K clean rows, no noise
#   python seed.py -n 500 --dry-run         # normalize only, skip DB
#   python seed.py -n 1000 --benchmark      # run with timing summary
#   python seed.py --fx-source live         # use live FX rates from DB
#
# Production CRON uses main.py directly — do not use this file on the server.

import argparse
import fx_source
from main import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NAP pipeline — local dev / seeding")
    parser.add_argument(
        "-n", "--transactions",
        type=int,
        default=10_000,
        help="Number of transactions to generate (default: 10000)"
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
        help="Print timing and row-count summary after run"
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

    run(
        n_transactions=args.transactions,
        noise_level=args.noise,
        clean=args.clean,
        dry_run=args.dry_run,
        benchmark=args.benchmark,
    )
