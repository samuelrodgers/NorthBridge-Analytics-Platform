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

import os
import sys
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
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

# API endpoint — frankfurter.app returns rates vs. EUR
# We'll fetch EUR → USD and all other currencies, then invert to get USD-based rates
API_URL = "https://api.frankfurter.app/latest"
API_BASE = "EUR"  # API's base currency
TARGET_BASE = "USD"  # What we want as base in our DB

# Polling interval in seconds
POLL_INTERVAL = 5

# Build symbols list (all currencies we care about)
# We need USD in the response so we can calculate the EUR→USD rate
SYMBOLS = ",".join(CURRENCY_CODES)

# Failure tracking for monitoring
failure_counters = {
    "api_errors": 0,
    "db_errors": 0,
    "rate_limit_hits": 0,
    "malformed_responses": 0,
}

# Latency tracking
LATENCY_THRESHOLD = 2.0  # seconds — warn if loop exceeds this

latency_stats = {
    "fetch_times": [],
    "insert_times": [],
    "total_times": [],
}

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
# API FETCH
# ============================================================

def fetch_rates():
    """
    Fetch current FX rates from frankfurter.app.

    API returns rates with EUR as base. We convert to USD-based rates
    by inverting: if API gives EUR→USD = 1.08, then USD→EUR = 1/1.08 = 0.926.

    Returns:
        dict with keys:
            "timestamp": datetime (UTC) — when the rate was valid
            "rates": dict {currency: rate} — USD-based rates

        Returns None on failure (API down, timeout, malformed response).
    """
    try:

        fetch_start = time.time() # For latency tracking

        # Build request URL
        params = {
            "from": API_BASE,
            "to": SYMBOLS,
        }

        response = requests.get(API_URL, params=params, timeout=10)

        # Specifically check for rate limiting
        if response.status_code == 429:
            failure_counters["rate_limit_hits"] += 1
            logger.error("API rate limit hit (HTTP 429) — too many requests")
            return None

        response.raise_for_status()

        data = response.json()

        # API response structure:
        # {
        #   "amount": 1.0,
        #   "base": "EUR",
        #   "date": "2026-02-18",
        #   "rates": {
        #     "USD": 1.0876,
        #     "GBP": 0.8598,
        #     "JPY": 162.94,
        #     ...
        #   }
        # }

        rates_eur_based = data.get("rates", {})

        if not rates_eur_based:
            failure_counters["malformed_responses"] += 1
            logger.error("API response missing rates")
            return None

            # Extract EUR→USD rate (we need this to convert everything to USD-based)
        eur_to_usd = rates_eur_based.get("USD")
        if not eur_to_usd:
            failure_counters["malformed_responses"] += 1
            logger.error("API response missing USD rate")
            return None

        # Convert all rates to USD-based by inverting through USD
        rates_usd_based = {}

        for currency, rate_from_eur in rates_eur_based.items():
            if currency == "USD":
                # USD→EUR is just the inverse of EUR→USD
                rates_usd_based["EUR"] = round(1.0 / eur_to_usd, 7)
            else:
                # Cross rate: USD→X = (EUR→X) / (EUR→USD)
                rates_usd_based[currency] = round(rate_from_eur / eur_to_usd, 7)

        # Timestamp: API returns date string, convert to datetime
        date_str = data.get("date")
        if date_str:
            # frankfurter returns YYYY-MM-DD, treat as EOD UTC
            ts = datetime.strptime(date_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        else:
            ts = datetime.now(timezone.utc)
            logger.warning("API response missing date, using current time")

        # Log success with sample rates for verification
        sample_rates = {k: rates_usd_based[k] for k in list(rates_usd_based.keys())[:3]}
        fetch_time = time.time() - fetch_start
        latency_stats["fetch_times"].append(fetch_time)

        logger.info(
            f"Fetched {len(rates_usd_based)} USD-based rates at {ts.isoformat()} "
            f"(sample: {sample_rates}) [fetch: {fetch_time:.3f}s]"
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

def insert_rates(conn, timestamp, rates):
    """
    Insert FX rates into raw.fx_rate.

    Args:
        conn:      psycopg2 connection
        timestamp: datetime (UTC) — fx_timestamp
        rates:     dict {currency: rate} — USD-based rates e.g. {"EUR": 0.92, ...}

    Returns:
        int — number of rows inserted (may be 0 if all conflict)
    """

    insert_start = time.time() # For latency tracking

    # Build rows: (base_cncy, quote_cncy, fx_timestamp, rate)
    # All our rates are vs. USD, so quote_cncy is always USD
    rows = [
        (currency, TARGET_BASE, timestamp, rate)
        for currency, rate in rates.items()
    ]

    sql = """
        INSERT INTO raw.fx_rate (base_cncy, quote_cncy, fx_timestamp, rate)
        VALUES %s
        ON CONFLICT ON CONSTRAINT fx_unique DO NOTHING
    """

    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
        inserted = cur.rowcount

    conn.commit()
    insert_time = time.time() - insert_start
    latency_stats["insert_times"].append(insert_time)

    if inserted > 0:
        logger.info(f"Inserted {inserted} rates into raw.fx_rate [insert: {insert_time:.3f}s]")
    else:
        logger.debug("All rates already exist (conflict)")

    return inserted


# ============================================================
# MAIN LOOP
# ============================================================

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    global shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_requested = True


# Register signal handlers for Ctrl+C and kill
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run():
    """
    Main polling loop — fetch rates every POLL_INTERVAL seconds.
    Runs until SIGINT/SIGTERM received.
    """
    logger.info(f"Starting live FX ingestion (polling every {POLL_INTERVAL}s)")
    logger.info(f"Fetching {len(SYMBOLS.split(','))} currencies, converting to {TARGET_BASE}-based rates")
    logger.info(f"API endpoint: {API_URL} (base: {API_BASE})")
    logger.info("Press Ctrl+C to stop")

    conn = get_connection()

    try:
        while not shutdown_requested:
            loop_start = time.time()

            # Fetch rates from API
            result = fetch_rates()

            if result:
                # Insert into DB with error handling
                try:
                    insert_rates(conn, result["timestamp"], result["rates"])
                except psycopg2.Error as e:
                    failure_counters["db_errors"] += 1
                    logger.error(f"Database insert failed: {e}")
                    # Try to reconnect on next loop
                    try:
                        conn.close()
                        conn = get_connection()
                        logger.info("Reconnected to database")
                    except Exception as reconnect_err:
                        logger.error(f"Failed to reconnect: {reconnect_err}")
            else:
                logger.warning("Skipping insert due to fetch failure")

                # Track total loop latency (runs every loop, success or failure)
            total_time = time.time() - loop_start
            latency_stats["total_times"].append(total_time)

            if total_time > LATENCY_THRESHOLD:
                logger.warning(
                    f"⚠️  High latency: loop took {total_time:.3f}s "
                    f"(threshold: {LATENCY_THRESHOLD}s)"
                )

            # Sleep for remaining interval time
            elapsed = total_time

            # Sleep for remaining interval time
            elapsed = time.time() - loop_start
            sleep_time = max(0, POLL_INTERVAL - elapsed)

            if sleep_time > 0 and not shutdown_requested:
                time.sleep(sleep_time)

        logger.info("Shutdown complete")
        logger.info(f"Failure counters: {failure_counters}")

        # Log latency statistics
        if latency_stats["total_times"]:
            avg_total = sum(latency_stats["total_times"]) / len(latency_stats["total_times"])
            max_total = max(latency_stats["total_times"])
            logger.info(
                f"Latency summary: avg={avg_total:.3f}s, max={max_total:.3f}s, "
                f"loops={len(latency_stats['total_times'])}"
            )


    finally:
        conn.close()


if __name__ == "__main__":
    run()