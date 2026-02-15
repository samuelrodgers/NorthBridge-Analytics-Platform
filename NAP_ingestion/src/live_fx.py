import requests
import time
from datetime import datetime, timezone
import psycopg2

API_URL = "https://api.exchangerate.host/latest?base=EUR&symbols=USD"

def fetch_rate():
    response = requests.get(API_URL)
    data = response.json()
    return data["rates"]["USD"]

def insert_rate(rate):
    # insert into raw.fx_rate
    pass

while True:
    rate = fetch_rate()
    timestamp = datetime.now(timezone.utc)
    insert_rate(rate)
    time.sleep(5)
