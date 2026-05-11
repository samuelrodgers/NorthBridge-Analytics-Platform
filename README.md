# Northbridge Analytics Platform

A synthetic financial analytics platform built as a senior capstone project (CPSC 498, Christopher Newport University, Spring 2026). It generates realistic multi-currency transaction data, runs it through a data quality pipeline, and surfaces the results through a custom dashboard backed by Apache Superset.

## What it does

- **Synthetic data pipeline** — generates transactions across 12 fictional companies in 4 industries and 14 currencies, injects realistic data quality issues (malformed timestamps, currency aliases, missing fields), and routes records through a quarantine/resolution workflow
- **Star-schema data warehouse** — PostgreSQL with `raw` (append-only ingestion), `analytics` (transformed fact/dimension tables), and `auth` schemas
- **FastAPI backend** (`bouncer.py`) — proxies Superset embeds, handles authentication (JWT + bcrypt), exposes data quality and governance APIs
- **Dashboard frontend** — HTML/CSS/JS pages for FX rates, transaction volume, data governance, and quarantine resolution
- **ML analysis** (`scripts/NAP_ingestion/src/ml_analysis.py`) — PCA, k-means clustering, and t-SNE on the generated transaction data

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Apache Superset (optional — dashboards embed Superset charts; the rest of the app works without it)

## Local setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/samuelrodgers24-web/NorthBridge-Analytics-Platform.git
cd NorthBridge-Analytics-Platform
python -m venv .venv
```

Activate the venv:
- **Windows:** `.venv\Scripts\activate`
- **Mac/Linux:** `source .venv/bin/activate`

```bash
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

Open a separate terminal (outside the venv). All `psql` commands in this section run from the **project root**.

**If you have an existing PostgreSQL install**, use your superuser credentials. On Windows, `psql` may not be on PATH — use the full path to the pgAdmin runtime, e.g.:

```
"C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE DATABASE northbridge;"
```

**First-time install:** use whatever superuser you set up during installation.

Create the database and a user:

```bash
psql -U postgres -c "CREATE DATABASE northbridge;"
psql -U postgres -c "CREATE USER nap_user WITH PASSWORD 'your_password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE northbridge TO nap_user;"
```

Then grant schema-level access (required for PostgreSQL 15+):

```bash
psql -U postgres -d northbridge -c "GRANT USAGE, CREATE ON SCHEMA public TO nap_user;"
```

> **Tip (Windows):** If you prefer a GUI, all of the above can be done in pgAdmin's Query Tool. Connect to your server, open the Query Tool, and paste the SQL statements directly.

### 3. Apply the base schema and migrations

Run all SQL from the **project root** in a terminal where `psql` is available. Apply the base schema first, then migrations in order.

**Mac/Linux:**

```bash
psql -U postgres -d northbridge -f scripts/SQL/Scripts/analytics_create_tables.sql
psql -U postgres -d northbridge -f scripts/SQL/Scripts/Create_auth.sql

for f in scripts/SQL/Migrations/0*.sql; do
    echo "Applying $f..."
    psql -U postgres -d northbridge -f "$f"
done
```

**Windows (PowerShell):**

```powershell
$env:PGPASSWORD = "your_postgres_password"
$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"   # adjust path to match your install

& $psql -U postgres -d northbridge -f "scripts\SQL\Scripts\analytics_create_tables.sql"
& $psql -U postgres -d northbridge -f "scripts\SQL\Scripts\Create_auth.sql"

Get-ChildItem scripts\SQL\Migrations\0*.sql | Sort-Object Name | ForEach-Object {
    Write-Host "Applying $($_.Name)..."
    & $psql -U postgres -d northbridge -f "$($_.FullName)"
}
```

After applying the schema, grant the pipeline user access to the new schemas:

```sql
GRANT USAGE, CREATE ON SCHEMA analytics TO nap_user;
GRANT ALL ON ALL TABLES IN SCHEMA analytics TO nap_user;
GRANT USAGE, CREATE ON SCHEMA raw TO nap_user;
GRANT ALL ON ALL TABLES IN SCHEMA raw TO nap_user;
GRANT USAGE, CREATE ON SCHEMA auth TO nap_user;
GRANT ALL ON ALL TABLES IN SCHEMA auth TO nap_user;
```

Verify both `analytics` and `raw` schemas exist before continuing — if they're missing, the base schema script didn't run successfully.

### 4. Configure environment variables

Copy the example files and fill in your values in a text editor:

```bash
cp .env.example .env
cp scripts/NAP_ingestion/.env.example scripts/NAP_ingestion/.env
```

Edit `.env` (for `bouncer.py`):

```
DATABASE_URL=postgresql://nap_user:your_password@localhost:5432/northbridge
JWT_SECRET_KEY=any_long_random_string
SUPERSET_URL=http://127.0.0.1:8088
SUPERSET_ADMIN_USER=admin
SUPERSET_ADMIN_PASS=
```

Edit `scripts/NAP_ingestion/.env` (for the pipeline):

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=northbridge
DB_USER=nap_user
DB_PASS=your_password
TWELVE_DATA_API_KEY=
```

### 5. Seed the database

Navigate to the ingestion source directory from the **project root** (with venv active):

```bash
cd scripts/NAP_ingestion/src
```

Seed dimension tables (industries, companies, currencies, expense categories — takes a few seconds):

```bash
python transform.py --seed
```

Run the historical transaction seed (~2.3M rows, 60 monthly batches from 2021–2026, takes 20–40 min):

```bash
python seed.py --start-date 2021-01-01 --end-date 2026-01-01 --batches 60 -n 38000
```

Backfill expense events (required — the seed alone generates too few):

```bash
python expense_backfill.py
```

Re-run the analytics transform now that expenses are populated:

```bash
python transform.py --seed
```

Fix `revenue_growth_rate` nulls (paste the UPDATE query from `scripts/RESEED.md` Section 6b into psql or pgAdmin).

### 6. Start the API

From the project root (with venv active):

```bash
python bouncer.py
```

Open `http://localhost:8000` in a browser. Register a new account to log in — the demo button requires a pre-seeded guest account which is not created by default.

## Project structure

```
.
├── bouncer.py                          # FastAPI backend + static file server
├── frontend/                           # Dashboard HTML/CSS/JS
│   ├── index.html
│   ├── fx.html
│   ├── governance.html
│   ├── quarantine-resolve.html
│   └── shared.css
├── scripts/
│   ├── NAP_ingestion/
│   │   └── src/
│   │       ├── main.py                 # Continuous ingestion entry point
│   │       ├── seed.py                 # Historical bulk seed
│   │       ├── transform.py            # Analytics layer ETL
│   │       ├── pipeline.py             # Normalization and quarantine logic
│   │       ├── noise.py                # Data quality issue injection
│   │       ├── transactions.py         # Synthetic transaction generation
│   │       ├── loader.py               # Raw schema loaders
│   │       ├── config.py               # Company / industry / currency reference data
│   │       ├── ml_analysis.py          # PCA, k-means, t-SNE
│   │       └── ml_main.py              # ML pipeline entry point
│   └── SQL/
│       ├── Migrations/                 # 001–018 incremental schema changes
│       └── Scripts/                    # Base schema creation and utility queries
└── requirements.txt
```

## Ongoing ingestion (optional)

To keep data flowing after the seed, run `main.py` on a schedule from the project root. Each call generates one batch of transactions for a 10-minute synthetic window:

```bash
python scripts/NAP_ingestion/src/main.py -n 100
```

## Apache Superset (optional)

The dashboard embeds Superset charts. To use them you need Superset running locally via Docker:

```bash
git clone https://github.com/apache/superset.git
cd superset
docker compose up -d
```

Then import the dashboard backup from `superset_dashboard_backup.zip` via the Superset UI (Settings → Import dashboards). Update `SUPERSET_URL` and credentials in `.env` to match.

## Author

Samuel Rodgers — CPSC 498 Senior Capstone, Christopher Newport University, Spring 2026
