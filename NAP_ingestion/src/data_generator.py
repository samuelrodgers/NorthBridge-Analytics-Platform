import uuid
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# Makes transformations idempotent
random.seed(42)
np.random.seed(42)


def generate_fx_series(
    start_time,
    end_time,
    base_cncy,
    quote_cncy,
    start_rate=1.10,
    interval_seconds=5
):
    timestamps = []
    rates = []

    current_rate = start_rate
    current_time = start_time

    while current_time <= end_time:
        shock = np.random.normal(0, 0.0002)
        current_rate *= (1 + shock)

        timestamps.append(current_time)
        rates.append(round(current_rate, 7))

        current_time += timedelta(seconds=interval_seconds)

    return pd.DataFrame({
        "event_timestamp": timestamps,
        "base_cncy": base_cncy,
        "quote_cncy": quote_cncy,
        "rate": rates
    })

if __name__ == "__main__":
    s_time = datetime.now()
    e_time = s_time + timedelta(seconds=10)
    base = 'USD'
    quote = 'AED'
    s_rate = 3.67
    frame = generate_fx_series(s_time, e_time, base, quote, s_rate)
    print(frame)