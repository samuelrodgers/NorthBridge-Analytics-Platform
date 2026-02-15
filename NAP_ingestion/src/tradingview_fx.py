import uuid
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd


def ingest_tradingview_fx(filepath, base, quote):
    df = pd.read_csv(filepath)

    # rename columns
    # parse timestamp
    # convert timezone
    # select only required columns

    return cleaned_df
