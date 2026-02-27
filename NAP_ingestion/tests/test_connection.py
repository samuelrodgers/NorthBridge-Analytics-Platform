import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()  # loads .env

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASS
)

cur = conn.cursor()
cur.execute("SELECT 1;")
result = cur.fetchone()
print("Result of SELECT 1:", result)

cur.close()
conn.close()
