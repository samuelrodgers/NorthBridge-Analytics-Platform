# main.py

from datetime import datetime, timedelta
from config import CURRENCIES, COMPANIES
from synthetic_fx import generate_all_fx_series
from transactions import generate_transactions
from pipeline import transform

def run(n_transactions=10_000, window_minutes=10):
    start = datetime.now()
    end = start + timedelta(minutes=window_minutes)

    print("Generating FX series...")
    fx = generate_all_fx_series(start, end, CURRENCIES)

    print("Generating transactions...")
    company_ids = [c["id"] for c in COMPANIES]
    tx = generate_transactions(start, end, company_ids, CURRENCIES, n_transactions)

    print("Transforming...")
    f_transaction, f_conversion = transform(tx, fx)

    print(f"✅ {len(f_transaction)} transactions, "
          f"{f_conversion['base_cncy'].nunique()} currencies converted")
    return f_transaction, f_conversion

if __name__ == "__main__":
    run()