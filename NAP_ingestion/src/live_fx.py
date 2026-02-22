# live_fx.py - basic structure, no API yet

import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POLL_INTERVAL = 5


def run():
    logger.info(f"Starting live FX ingestion (polling every {POLL_INTERVAL}s)")

    while True:
        loop_start = time.time()

        logger.info("Fetching rates...")  # placeholder

        # Sleep for remaining interval
        elapsed = time.time() - loop_start
        sleep_time = max(0, POLL_INTERVAL - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)


if __name__ == "__main__":
    run()