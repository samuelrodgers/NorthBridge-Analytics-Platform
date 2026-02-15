# pipeline.py

import uuid
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd



# ======= TIME-BASED FUNCTIONS ====== #

# Will replace this with exchangerate.host data
import pandas as pd
import numpy as np




# ====== CORRECTNESS ENFORCEMENT ===== #
# TODO - account for the noise I made
#def normalize_receipts(raw_df, company_profile)

def match_fx_rates(transactions_df, fx_df):
    transactions_df = transactions_df.sort_values("tx_timestamp")
    fx_df = fx_df.sort_values("fx_timestamp")

    merged = pd.merge_asof(
        transactions_df,
        fx_df,
        left_on="tx_timestamp",
        right_on="fx_timestamp",
        by=["base_cncy", "quote_cncy"],
        direction="backward"
    )

    return merged

# ====== TRANSFORMATIONS ====== #

def transform(transactions_df, fx_df):

    matched = match_fx_rates(transactions_df, fx_df)

    matched["normalized_amount_usd"] = np.where(
        matched["base_cncy"] == "USD",
        matched["base_amount"],
        matched["base_amount"] * matched["rate"]
    )

    f_transaction = matched[[
        "tx_timestamp",
        "company_id",
        "base_cncy",
        "base_amount",
        "normalized_amount_usd"
    ]].copy()

    f_conversion = matched[
        matched["base_cncy"] != "USD"
    ][[
        "tx_timestamp",
        "base_cncy",
        "rate"
    ]].copy()

    return f_transaction, f_conversion
