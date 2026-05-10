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
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

```bash
psql -U postgres -c "CREATE DATABASE northbridge;"
psql -U postgres -c "CREATE USER nap_user WITH PASSWORD 'your_password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE northbridge TO nap_user;"
```

### 3. Apply the base schema and migrations

Run the base schema scripts first (order matters — `analytics_create_tables.sql` before `Create_auth.sql`):

```bash
psql -U nap_user -d northbridge -f scripts/SQL/Scripts/analytics_create_tables.sql
psql -U nap_user -d northbridge -f scripts/SQL/Scripts/Create_auth.sql
```

Then apply all migrations in order:

```bash
for f in scripts/SQL/Migrations/0*.sql; do
    echo "Applying $f..."
    psql -U nap_user -d northbridge -f "$f"
done
```

On Windows (PowerShell):

```powershell
Get-ChildItem scripts\SQL\Migrations\0*.sql | Sort-Object Name | ForEach-Object {
    Write-Host "Applying $($_.Name)..."
    psql -U nap_user -d northbridge -f $_.FullName
}
```

### 4. Configure environment variables

Copy the example files and fill in your values:

```bash
cp .env.example .env
cp scripts/NAP_ingestion/.env.example scripts/NAP_ingestion/.env
```

Edit `.env` (for `bouncer.py`):

```
DATABASE_URL=postgresql://nap_user:your_password@localhost:5432/northbridge
JWT_SECRET_KEY=<output of: openssl rand -hex 32>
SUPERSET_URL=http://127.0.0.1:8088    # omit if not running Superset
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
TWELVE_DATA_API_KEY=          # optional — only needed for live FX ingestion
```

### 5. Seed the database

Navigate to the ingestion source directory:

```bash
cd scripts/NAP_ingestion/src
```

Seed dimension tables (industries, companies, currencies, expense categories):

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

Fix `revenue_growth_rate` nulls (a single-pass UPDATE — see `scripts/RESEED.md` for the full SQL):

```bash
python -c "
import os; from dotenv import load_dotenv; load_dotenv(); import psycopg2
conn = psycopg2.connect(host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT'), dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASS'))
cur = conn.cursor()
cur.execute(open('../SQL/Scripts/Workbook3.sql').read())
conn.commit(); conn.close()
"
```

Or just paste the UPDATE query from `scripts/RESEED.md` Section 6b directly into psql.

### 6. Start the API

From the project root:

```bash
python bouncer.py
```

The API runs at `http://localhost:8000`. Open `frontend/index.html` in a browser to use the dashboard.

## Project structure

```
.
├── bouncer.py                          # FastAPI backend
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

To keep data flowing after the seed, run `main.py` on a schedule. Each call generates one batch of transactions for a 10-minute synthetic window:

```bash
python scripts/NAP_ingestion/src/main.py -n 100
```

## Apache Superset (optional)

The dashboard embeds Superset charts. To use them you need Superset running locally via Docker:

```bash
# Clone the Superset repo and start it
git clone https://github.com/apache/superset.git
cd superset
docker compose up -d
```

Then import the dashboard backup from `superset_dashboard_backup.zip` via the Superset UI (Settings → Import dashboards). Update `SUPERSET_URL` and credentials in `.env` to match.

## Author

Samuel Rodgers — CPSC 498 Senior Capstone, Christopher Newport University, Spring 2026
