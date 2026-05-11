# Code Development Agent Briefing
# Northbridge Analytics Platform — Lessons Learned

This file captures hard-won lessons from building and debugging this project.
Read it before making changes to setup scripts, environment config, or the
PostgreSQL schema pipeline.

---

## Project overview

Full-stack local analytics platform:
- **PostgreSQL** star schema (`analytics`, `raw`, `auth` schemas)
- **Python pipeline** (`scripts/NAP_ingestion/src/`) — generates synthetic data, runs ETL
- **FastAPI backend** (`bouncer.py`) — serves the frontend and APIs
- **Frontend** (`frontend/`) — plain HTML/CSS/JS, served as static files via bouncer.py

The app is entirely local. There is no cloud deployment.

---

## PostgreSQL setup — the most important lesson

**Always create schema objects as the app user, not postgres.**

If you create tables as the postgres superuser and then try to GRANT access to
the app user, FK constraint enforcement will fail in subtle ways even after all
grants appear to succeed. Specifically, PostgreSQL's internal FK check query
(`SELECT 1 FROM ONLY table x WHERE ... FOR KEY SHARE`) will raise
"permission denied for schema" even when `has_schema_privilege` and
`has_table_privilege` both return true.

The fix: in the setup script, after creating the database and user as postgres,
switch to the app user (`nap_user`) for all `CREATE SCHEMA`, `CREATE TABLE`,
`CREATE FUNCTION`, and migration scripts. The app user then owns all objects
and no separate GRANT step is needed.

See `scripts/setup_db.ps1` steps [1/3] vs [2/3] for the pattern:
- Step 1: connect as postgres — CREATE DATABASE, CREATE USER, GRANT ALL PRIVILEGES ON DATABASE
- Step 2: connect as nap_user — apply all SQL scripts and migrations

**Do not add `OWNER TO <user>` lines to SQL scripts.** Owner assignment in SQL
files is tied to a specific username and breaks on any other install. Let
ownership come from which user runs the scripts.

---

## load_dotenv — two required patterns for Python scripts

### 1. Always use a script-relative path

`load_dotenv()` with no arguments searches upward from CWD. When scripts are
run from the project root (e.g. `python scripts/NAP_ingestion/src/transform.py`),
CWD is the project root and it finds the root `.env`, not the pipeline `.env`.

Correct pattern in every pipeline script:
```python
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'), override=True)
```

### 2. Always pass `override=True`

On Windows, users may have stale environment variables set at the system level
(e.g. from a previous install with a different username/password). Without
`override=True`, those stale values silently win over the `.env` file.

Both patterns are required. Either one alone is insufficient.

---

## requirements.txt — use >= not ==

Pinned exact versions (`package==X.Y.Z`) fail when:
- The exact version is yanked from PyPI
- The version doesn't exist for the user's Python version
- Platform-specific wheels differ

Use minimum version constraints (`package>=X.Y.Z`). This project previously had
`uvicorn==0.34.0` (didn't exist) which blocked the entire `pip install`.

Also: always test `pip install -r requirements.txt` on Python 3.11+ specifically.
Some packages (e.g. numpy) have different minimum version requirements per
Python version.

---

## Windows-specific caveats

### PowerShell syntax
- No backslash line continuations — use backtick (`` ` ``) or just keep commands on one line
- `&&` pipeline chaining is not available in PowerShell 5.1 — use `;` or `if ($?) { ... }`
- Default file encoding is UTF-16 LE with BOM — use `-Encoding ASCII` or `-Encoding UTF8` explicitly when writing files that Python will read
- Here-strings (`@"..."@`) start with a newline after `@"` — be careful passing them to native executables via `-c`; prefer separate calls over one multiline `-c` string

### psql on Windows
- psql is not on PATH by default; users must either add it or use the full path
- Common locations: `C:\Program Files\PostgreSQL\<version>\bin\psql.exe` or `D:\PostgreSQL\pgAdmin 4\runtime\psql.exe`
- The setup script auto-detects common locations

### Environment variables
- Windows users often have stale env vars from previous installs that override `.env` files
- Always use `override=True` in `load_dotenv()`

---

## .env file management

The project has two `.env` files:
- `.env` (project root) — for `bouncer.py`: DATABASE_URL, JWT_SECRET_KEY, Superset creds
- `scripts/NAP_ingestion/.env` — for the pipeline: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS, TWELVE_DATA_API_KEY

Both are gitignored. The setup script (`setup_db.ps1` / `setup_db.sh`) writes
them automatically during setup. `.env.example` files exist as reference only.

**Never instruct users to copy `.env.example` and fill it in manually.** They
will edit `.env.example` directly instead of creating `.env`, and then wonder
why nothing works. Auto-generation in the setup script eliminates this entirely.

---

## Frontend serving

The frontend is served by FastAPI via `StaticFiles`. Users must access the app
at `http://localhost:8000`, not by opening HTML files directly. Opening files
with `file://` breaks all API calls because `/api/` paths don't resolve.

The root `GET /` route returns `index.html`. All API routes must be registered
before the `StaticFiles` mount, or FastAPI will serve the static file instead
of routing to the API handler.

---

## Database re-setup

If a user needs to re-run `setup_db.ps1` (e.g. after a failed install), they
must first drop the existing database and user in pgAdmin or psql:

```sql
DROP DATABASE northbridge;
DROP USER nap_user;
```

The setup script does not handle "already exists" gracefully — `CREATE DATABASE`
will fail and exit the script before any grants or schema work happens. A future
improvement would be to add `IF NOT EXISTS` / `IF EXISTS` guards, but for now
the README should document the drop-and-recreate procedure.

---

## Schema migration pattern

18 numbered migrations (`001` through `018`) live in `scripts/SQL/Migrations/`.
The base schema is in `scripts/SQL/Scripts/analytics_create_tables.sql` and
`scripts/SQL/Scripts/Create_auth.sql`. Always apply base schema first, then
migrations in order. The setup script handles this automatically.

Migrations are incremental and not idempotent by default — running them twice
will fail. This is intentional (append-only history). If a migration needs to
be re-run, the database must be dropped and recreated.

---

## Seed vs full historical data

`transform.py --seed` seeds dimension tables only (currencies, industries,
companies, expense categories). Takes ~5 seconds. Enough to run the app.

For full historical data (required for meaningful charts):
```
python scripts/NAP_ingestion/src/seed.py --start-date 2021-01-01 --end-date 2026-01-01 --batches 60 -n 38000
python scripts/NAP_ingestion/src/expense_backfill.py
python scripts/NAP_ingestion/src/transform.py --seed
```
Takes 20–40 minutes. After this, run the `revenue_growth_rate` fix in
`scripts/RESEED.md` Section 6b.
