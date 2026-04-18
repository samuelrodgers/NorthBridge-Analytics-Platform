# NAP Re-seed Suite

Complete command reference for wiping and re-seeding the EC2 database.
Run each section in order. Verify before proceeding to the next section.

All psql commands use:
```
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres
```
Aliased below as `$PSQL` for brevity.

---

## Section 1 — Stop all services

```bash
# Stop the cron jobs
crontab -e
# Comment out both lines (add # prefix), save and exit

# Stop live FX ingestion
sudo systemctl stop live-fx

# Stop the API (prevents DB connections interfering with truncation)
sudo systemctl stop bouncer
```

---

## Section 2 — Truncate all data tables

```bash
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -c "TRUNCATE raw.fx_rate, raw.transaction_event, raw.quarantine_event, raw.expense_event, raw.quarantine_resolution, raw.batch_log, analytics.f_fx_rate, analytics.f_transaction, analytics.f_conversion, analytics.f_expense, analytics.f_industry, analytics.d_time, analytics.d_company, analytics.d_industry, analytics.d_currency, analytics.d_expense_category CASCADE;"
```

**Verify empty:**
```bash
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -c "SELECT (SELECT COUNT(*) FROM raw.transaction_event) AS tx, (SELECT COUNT(*) FROM analytics.f_transaction) AS f_tx, (SELECT COUNT(*) FROM raw.quarantine_event) AS quarantine, (SELECT COUNT(*) FROM raw.batch_log) AS batch_log;"
```
Expected: all zeros.

---

## Section 3 — Verify migrations are applied

```bash
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -c "\d raw.batch_log"
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -c "\d raw.quarantine_event" | grep dirty_value
```

Both must return results. If either fails, apply the missing migration before proceeding:
```bash
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -f ~/northbridge-analytics-platform/scripts/SQL/Migrations/015_add_batch_log.sql
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -f ~/northbridge-analytics-platform/scripts/SQL/Migrations/016_quarantine_dirty_value.sql
```

---

## Section 4 — Historical seed

Activate the venv and navigate to the src directory first:
```bash
source ~/northbridge-analytics-platform/.venv/bin/activate
cd ~/northbridge-analytics-platform/scripts/NAP_ingestion/src
```

Run the historical seed (60 monthly batches, ~38K rows each ≈ 2.3M total, ~1200 tx/day):
```bash
python seed.py --start-date 2021-01-01 --end-date 2026-04-18 --batches 60 -n 38000
```

This will take 20-40 minutes. Each batch logs its own entry to raw.batch_log with
run_timestamp = batch window end, and quarantine records with historical ingestion_timestamps.
Both are now automatic — no backfill scripts needed for these.

When complete, the script will prompt you to run transform.py.

---

## Section 5 — Expense backfill

The seed only generates 1-5 expenses per company per batch call. With 60 batches that
produces ~2,160 expense rows — far below the 15-30% revenue target. Run the backfill:

```bash
python expense_backfill.py
```

Default settings: 900 events/company/month across 2021-2026 → ~680K rows, ~28% expense ratio.

---

## Section 6 — Analytics transform

```bash
python transform.py --seed
```

Then truncate f_industry and rerun so it calculates net_profit using the backfilled expenses:

```bash
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -c "TRUNCATE analytics.f_industry;"
python transform.py --seed
```

**Verify expense ratio:**
```bash
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -c "SELECT ROUND(AVG(total_expenses/NULLIF(total_revenue,0)*100)::numeric,2) AS avg_expense_pct FROM analytics.f_industry;"
```
Expected: 15–30%.

---

## Section 7 — Quarantine backfill (last 30 days only)

Fill the governance page with 30 days of realistic quarantine data:

```bash
python quarantine_backfill.py --start 2026-03-18 --end 2026-04-18 --per-day 80
```

Note: future re-seeds will not need this script — the ingestion_timestamp fix in loader.py
now stamps quarantine records with the window end time automatically during seed runs.
This script only exists for the current DB state where historical quarantine data was seeded
before that fix was in place.

---

## Section 8 — Restore services

```bash
# Restart the API
sudo systemctl restart bouncer

# Restart live FX ingestion
sudo systemctl start live-fx

# Re-enable cron (uncomment both lines, update -n 100 on main.py line)
crontab -e
```

Cron lines should look like:
```
*/30 * * * * cd /home/ubuntu/northbridge-analytics-platform/scripts/NAP_ingestion && /usr/bin/python3 src/transform.py >> /home/ubuntu/cron.log 2>&1
0 */2 * * * cd /home/ubuntu/northbridge-analytics-platform/scripts/NAP_ingestion && /usr/bin/python3 src/main.py -n 100 >> /home/ubuntu/cron.log 2>&1
```

---

## Section 9 — Final verification

```bash
PGPASSWORD='1a14g2F1!' psql -h localhost -p 5433 -U superset_admin -d postgres -c "
SELECT
    (SELECT COUNT(*) FROM raw.transaction_event)   AS raw_tx,
    (SELECT COUNT(*) FROM analytics.f_transaction) AS f_tx,
    (SELECT COUNT(*) FROM analytics.f_expense)     AS f_expense,
    (SELECT COUNT(*) FROM analytics.f_industry)    AS f_industry,
    (SELECT COUNT(*) FROM raw.quarantine_event)    AS quarantine,
    (SELECT COUNT(*) FROM raw.batch_log)           AS batch_log;
"
```

Expected approximate values:
- raw_tx: ~1.8–2.1M (clean rows from seed)
- f_tx: matches raw_tx
- f_expense: ~680K
- f_industry: ~7,700
- quarantine: ~2,400 (30 days × 80/day)
- batch_log: 60 (one per seed batch)

---

## Known issues fixed in this codebase vs prior seed

| Issue | Fix |
|---|---|
| `raw.batch_log` must exist before seed | Apply migrations (Section 3) before seed (Section 4) |
| Quarantine `ingestion_timestamp` all landed on seed date | loader.py now passes `ingestion_timestamp=end` automatically |
| Expense events too sparse (5 calls for 5-year seed) | expense_backfill.py is a required post-seed step |
| `raw.fx_rate` fills up from live-fx during seed | Stop live-fx (Section 1) before truncate; truncate raw.fx_rate after if needed |
| `f_industry` computed before expense backfill | Always truncate f_industry and rerun transform after expense backfill (Section 6) |
