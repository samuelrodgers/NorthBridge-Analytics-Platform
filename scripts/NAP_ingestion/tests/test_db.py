# test_db.py
# Run from the tests/ folder:
#   python test_db.py
#
# Assumes project layout:
#   project/
#     src/        ← all Python source files
#     tests/      ← this file
#     out/        ← logs, metrics

import sys
import os

# Add src/ to the path so imports work from the tests/ folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import transform


def main():

    conn = transform.get_connection()
    cur = conn.cursor()

    # ── Test 1: schema tables ─────────────────────────────────────────────────
    print("=" * 40)
    print("TEST 1: Tables in raw + analytics schemas")
    print("=" * 40)
    cur.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('raw', 'analytics')
        ORDER BY table_schema, table_name
    """)
    rows = cur.fetchall()
    for row in rows:
        print(f"  {row[0]}.{row[1]}")
    print(f"  ({len(rows)} tables found)")

    # ── Test 2: seed dimension tables ─────────────────────────────────────────
    print()
    print("=" * 40)
    print("TEST 2: Seed dimension tables")
    print("=" * 40)
    transform.run_seed(conn)

    # ── Test 3: verify seed row counts ────────────────────────────────────────
    print()
    print("=" * 40)
    print("TEST 3: Dimension table row counts")
    print("=" * 40)
    expected = {
        "d_currency":         14,
        "d_industry":          4,
        "d_company":          12,
        "d_expense_category":  6,
    }
    all_ok = True
    for table, exp in expected.items():
        cur.execute(f"SELECT COUNT(*) FROM analytics.{table}")
        actual = cur.fetchone()[0]
        status = "✅" if actual == exp else "❌"
        print(f"  {status} {table}: {actual} rows (expected {exp})")
        if actual != exp:
            all_ok = False
    if all_ok:
        print("  All counts match.")

    # ── Test 7: analytics fact table row counts ───────────────────────────────
    print()
    print("=" * 40)
    print("TEST 7: Analytics fact table row counts")
    print("=" * 40)
    fact_tables = [
        "f_fx_rate",
        "d_time",
        "f_transaction",
        "f_conversion",
        "f_expense",
        "f_industry",
    ]
    for table in fact_tables:
        cur.execute(f"SELECT COUNT(*) FROM analytics.{table}")
        count = cur.fetchone()[0]
        status = "✅" if count > 0 else "⚠️ "
        print(f"  {status} analytics.{table}: {count:,} rows")

    print()
    cur.execute("SELECT COUNT(*) FROM raw.transaction_event")
    print(f"  ℹ️  raw.transaction_event: {cur.fetchone()[0]:,} rows")
    cur.execute("SELECT COUNT(*) FROM raw.expense_event")
    print(f"  ℹ️  raw.expense_event:     {cur.fetchone()[0]:,} rows")
    cur.execute("SELECT COUNT(*) FROM raw.fx_rate")
    print(f"  ℹ️  raw.fx_rate:           {cur.fetchone()[0]:,} rows")

    print()
    print("  Note: f_industry will show 0 rows until transactions span")
    print("  at least one full calendar day boundary.")

    conn.close()


if __name__ == "__main__":
    main()