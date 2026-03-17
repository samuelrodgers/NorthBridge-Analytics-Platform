# live_fx.py
# Real-time FX rate ingestion — polls frankfurter.app API every 5 seconds
# and inserts rates into raw.fx_rate.
#
# Usage:
#   python live_fx.py
#
# Stop with Ctrl+C (sends SIGINT for graceful shutdown).
#
# API: https://www.frankfurter.app/latest
# Free, no API key required, no explicit rate limits (fair use).
# Maintained by European Central Bank. Returns rates vs. EUR as base.
# We invert the rates to get USD as base before inserting into DB.
#
# FX source switching:
#   This file is one of two FX sources. The other is synthetic_fx.py.
#   fx_source.py provides a unified interface so the dashboard can swap
#   between them at runtime without touching this file or main.py.
#   See fx_source.py for details.

import json
import os
import time
import signal
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
import requests
import psycopg2
from psycopg2.extras import execute_values

from config import CURRENCY_CODES

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

# API endpoint — frankfurter.app returns rates vs. EUR
# We fetch EUR → all currencies, then invert to get USD-based rates
API_URL    = "https://api.frankfurter.app/latest"
API_BASE   = "EUR"   # API's base currency
TARGET_BASE = "USD"  # What we store in the DB

# Polling interval in seconds
POLL_INTERVAL = 5

# All currencies we care about — USD must be in the response so we can
# calculate the EUR→USD cross rate
SYMBOLS = ",".join(CURRENCY_CODES)

# Failure tracking for monitoring
failure_counters = {
    "api_errors":          0,
    "db_errors":           0,
    "rate_limit_hits":     0,
    "malformed_responses": 0,
}

# Latency tracking
LATENCY_THRESHOLD = 2.0  # seconds — warn if a loop iteration exceeds this

latency_stats = {
    "fetch_times":  [],
    "insert_times": [],
    "total_times":  [],
}

# Exponential backoff for API failures
consecutive_failures = 0
MAX_BACKOFF = 60  # seconds — cap backoff at 1 minute

# Output directory for metrics and checkpoint files.
# os.path.join handles cross-platform separators correctly.
_OUT_DIR = os.path.join("NAP_ingestion", "out")

METRICS_FILE    = os.path.join(_OUT_DIR, "live_fx_metrics.jsonl")
CHECKPOINT_FILE = os.path.join(_OUT_DIR, "live_fx_checkpoint.txt")


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
    )


# ============================================================
# RATE VALIDATION
# ============================================================

# Plausible rate ranges — 1 unit of the key currency expressed in USD.
# Used to reject obviously corrupt API responses before they reach the DB.
RATE_BOUNDS = {
    "EUR": (0.5,  2.0),
    "GBP": (0.5,  2.5),
    "JPY": (50,   200),
    "AUD": (0.5,  2.0),
    "CAD": (0.5,  2.0),
    "CHF": (0.5,  2.0),
    "SEK": (5,    15),
    "NOK": (5,    15),
    "MXN": (10,   25),
    "BRL": (2,    10),
    "SGD": (0.8,  2.0),
    "HKD": (5,    10),
    "AED": (2,    5),
}


def validate_rates(rates: dict) -> list[str]:
    """
    Check that each rate falls within its plausible bounds.

    Args:
        rates: dict {currency: rate} — USD-based rates

    Returns:
        List of validation error strings. Empty if all rates are valid.
    """
    errors = []
    for currency, rate in rates.items():
        if currency in RATE_BOUNDS:
            lo, hi = RATE_BOUNDS[currency]
            if not (lo <= rate <= hi):
                errors.append(
                    f"{currency}: {rate:.4f} outside plausible range [{lo}, {hi}]"
                )
    return errors


# ============================================================
# API FETCH
# ============================================================

def fetch_rates() -> dict | None:
    """
    Fetch current FX rates from frankfurter.app.

    The API returns rates with EUR as base. We convert to USD-based rates:
        EUR→USD rate from API = eur_to_usd
        USD→EUR = 1 / eur_to_usd
        USD→X   = (EUR→X) / eur_to_usd

    Returns:
        dict with keys:
            "timestamp": datetime (UTC) — when the rate was valid
            "rates":     dict {currency: rate} — USD-based rates
        Returns None on any failure so the caller can apply backoff.
    """
    try:
        fetch_start = time.time()

        response = requests.get(
            API_URL,
            params={"from": API_BASE, "to": SYMBOLS},
            timeout=10,
        )

        if response.status_code == 429:
            failure_counters["rate_limit_hits"] += 1
            logger.error("API rate limit hit (HTTP 429) — too many requests")
            return None

        response.raise_for_status()
        data = response.json()

        rates_eur_based = data.get("rates", {})
        if not rates_eur_based:
            failure_counters["malformed_responses"] += 1
            logger.error("API response missing rates")
            return None

        eur_to_usd = rates_eur_based.get("USD")
        if not eur_to_usd:
            failure_counters["malformed_responses"] += 1
            logger.error("API response missing USD rate")
            return None

        rates_usd_based = {}
        for currency, rate_from_eur in rates_eur_based.items():
            if currency == "USD":
                rates_usd_based["EUR"] = round(1.0 / eur_to_usd, 7)
            else:
                rates_usd_based[currency] = round(rate_from_eur / eur_to_usd, 7)

        # API returns YYYY-MM-DD; treat as end-of-day UTC
        date_str = data.get("date")
        if date_str:
            ts = datetime.strptime(date_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        else:
            ts = datetime.now(timezone.utc)
            logger.warning("API response missing date, using current time")

        # Clock skew guard — reject timestamps more than 24h in the future
        now = datetime.now(timezone.utc)
        if (ts - now).total_seconds() > 86400:
            failure_counters["malformed_responses"] += 1
            logger.error(
                f"API timestamp too far in future: {ts.isoformat()} "
                f"(now: {now.isoformat()})"
            )
            return None

        validation_errors = validate_rates(rates_usd_based)
        if validation_errors:
            failure_counters["malformed_responses"] += 1
            logger.error(f"Rate validation failed: {'; '.join(validation_errors)}")
            return None

        fetch_time = time.time() - fetch_start
        latency_stats["fetch_times"].append(fetch_time)

        sample = {k: rates_usd_based[k] for k in list(rates_usd_based.keys())[:3]}
        logger.info(
            f"Fetched {len(rates_usd_based)} USD-based rates at {ts.isoformat()} "
            f"(sample: {sample}) [fetch: {fetch_time:.3f}s]"
        )
        return {"timestamp": ts, "rates": rates_usd_based}

    except requests.exceptions.Timeout:
        failure_counters["api_errors"] += 1
        logger.error("API request timed out")
        return None
    except requests.exceptions.RequestException as e:
        failure_counters["api_errors"] += 1
        logger.error(f"API request failed: {e}")
        return None
    except (KeyError, ValueError, ZeroDivisionError) as e:
        failure_counters["malformed_responses"] += 1
        logger.error(f"Malformed API response or rate conversion error: {e}")
        return None


# ============================================================
# DATABASE INSERT
# ============================================================

def insert_rates(conn, timestamp: datetime, rates: dict) -> int:
    """
    Insert FX rates into raw.fx_rate.

    Args:
        conn:      psycopg2 connection
        timestamp: datetime (UTC) — fx_timestamp
        rates:     dict {currency: rate} — USD-based rates

    Returns:
        Number of rows inserted (0 if all already existed).
    """
    insert_start = time.time()

    rows = [
        (currency, TARGET_BASE, timestamp, rate)
        for currency, rate in rates.items()
    ]

    sql = """
        INSERT INTO raw.fx_rate (base_cncy, quote_cncy, fx_timestamp, rate)
        VALUES %s
        ON CONFLICT ON CONSTRAINT idx_fx_rate_cncy_ts DO NOTHING
    """

    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
        inserted = cur.rowcount

    conn.commit()
    insert_time = time.time() - insert_start
    latency_stats["insert_times"].append(insert_time)

    if inserted > 0:
        logger.info(
            f"Inserted {inserted} rates into raw.fx_rate "
            f"[insert: {insert_time:.3f}s]"
        )
    else:
        logger.debug("All rates already exist (conflict)")

    return inserted


# ============================================================
# MAIN LOOP
# ============================================================

shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_requested = True


signal.signal(signal.SIGINT,  signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run():
    """
    Main polling loop — fetch rates every POLL_INTERVAL seconds.
    Runs until SIGINT/SIGTERM is received.
    """
    global consecutive_failures

    logger.info(f"Starting live FX ingestion (polling every {POLL_INTERVAL}s)")
    logger.info(f"Currencies: {len(SYMBOLS.split(','))} pairs vs {TARGET_BASE}")
    logger.info(f"API endpoint: {API_URL} (base: {API_BASE})")
    logger.info("Press Ctrl+C to stop")

    # Ensure output directory exists before trying to write files
    os.makedirs(_OUT_DIR, exist_ok=True)

    conn = get_connection()

    last_checkpoint = None
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            checkpoint_str = f.read().strip()
            if checkpoint_str:
                last_checkpoint = datetime.fromisoformat(checkpoint_str)
                logger.info(f"Resuming from checkpoint: {last_checkpoint.isoformat()}")
    except FileNotFoundError:
        logger.info("No checkpoint found, starting fresh")
    except Exception as e:
        logger.warning(f"Failed to read checkpoint: {e}")

    try:
        while not shutdown_requested:
            loop_start = time.time()

            result = fetch_rates()

            skipped_duplicate = False
            if result and last_checkpoint and result["timestamp"] <= last_checkpoint:
                logger.debug(
                    f"Skipping already-processed timestamp: "
                    f"{result['timestamp'].isoformat()}"
                )
                skipped_duplicate = True
                result = None

            if result:
                try:
                    insert_rates(conn, result["timestamp"], result["rates"])
                except psycopg2.Error as e:
                    failure_counters["db_errors"] += 1
                    logger.error(f"Database insert failed: {e}")
                    try:
                        conn.close()
                        conn = get_connection()
                        logger.info("Reconnected to database")
                    except Exception as reconnect_err:
                        logger.error(f"Failed to reconnect: {reconnect_err}")

                consecutive_failures = 0

                try:
                    with open(CHECKPOINT_FILE, "w") as f:
                        f.write(result["timestamp"].isoformat())
                    last_checkpoint = result["timestamp"]
                except Exception as e:
                    logger.warning(f"Failed to write checkpoint: {e}")

            else:
                if not skipped_duplicate:
                    consecutive_failures += 1
                    backoff_delay = min(2 ** (consecutive_failures - 1), MAX_BACKOFF)
                    logger.warning(
                        f"Skipping insert due to fetch failure "
                        f"(consecutive: {consecutive_failures}, "
                        f"backoff: {backoff_delay}s)"
                    )
                    for _ in range(int(backoff_delay)):
                        if shutdown_requested:
                            break
                        time.sleep(1)

            total_time = time.time() - loop_start
            latency_stats["total_times"].append(total_time)

            if total_time > LATENCY_THRESHOLD:
                logger.warning(
                    f"⚠️  High latency: loop took {total_time:.3f}s "
                    f"(threshold: {LATENCY_THRESHOLD}s)"
                )

            try:
                metric_entry = {
                    "timestamp":           datetime.now(timezone.utc).isoformat(),
                    "fetch_time":          latency_stats["fetch_times"][-1]  if latency_stats["fetch_times"]  else None,
                    "insert_time":         latency_stats["insert_times"][-1] if latency_stats["insert_times"] else None,
                    "total_time":          total_time,
                    "success":             result is not None,
                    "consecutive_failures": consecutive_failures,
                    "failure_counters":    failure_counters.copy(),
                }
                with open(METRICS_FILE, "a") as f:
                    f.write(json.dumps(metric_entry) + "\n")
            except Exception as e:
                logger.warning(f"Failed to write metrics: {e}")

            elapsed    = time.time() - loop_start
            sleep_time = max(0, POLL_INTERVAL - elapsed)
            if sleep_time > 0 and not shutdown_requested:
                time.sleep(sleep_time)

        logger.info("Shutdown complete")
        logger.info(f"Failure counters: {failure_counters}")

        if latency_stats["total_times"]:
            avg = sum(latency_stats["total_times"]) / len(latency_stats["total_times"])
            mx  = max(latency_stats["total_times"])
            logger.info(
                f"Latency summary: avg={avg:.3f}s, max={mx:.3f}s, "
                f"loops={len(latency_stats['total_times'])}"
            )

    finally:
        conn.close()


if __name__ == "__main__":
    run()