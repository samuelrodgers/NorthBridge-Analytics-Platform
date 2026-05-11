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

### 2. Set up the database

A setup script handles everything — creating the database, applying the schema, running all 18 migrations, and granting the right permissions. Run it from the **project root** in a separate terminal (no venv needed).

**Windows (PowerShell):**

```powershell
.\scripts\setup_db.ps1
```

The script will auto-detect your PostgreSQL install and prompt for passwords. If it can't find `psql.exe`, enter the full path when prompted (e.g. `D:\PostgreSQL\pgAdmin 4\runtime\psql.exe`).

**Mac/Linux:**

```bash
bash scripts/setup_db.sh
```

Both scripts create a `northbridge` database and a `nap_user` account, then apply the full schema and migrations. Take note of the `nap_user` password you enter — you'll need it in the next step.

### 3. Configure environment variables

Copy the example files:
- **Windows:** `copy .env.example .env` and `copy scripts\NAP_ingestion\.env.example scripts\NAP_ingestion\.env`
- **Mac/Linux:** `cp .env.example .env` and `cp scripts/NAP_ingestion/.env.example scripts/NAP_ingestion/.env`

Open each file in a text editor and fill in your values.

**`.env`** (for `bouncer.py`, in the project root):

```
DATABASE_URL=postgresql://nap_user:your_password@localhost:5432/northbridge
JWT_SECRET_KEY=any_long_random_string
SUPERSET_URL=http://127.0.0.1:8088
SUPERSET_ADMIN_USER=admin
SUPERSET_ADMIN_PASS=
```

**`scripts/NAP_ingestion/.env`** (for the pipeline):

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=northbridge
DB_USER=nap_user
DB_PASS=your_password
TWELVE_DATA_API_KEY=
```

### 4. Seed the database

With the venv active, run these from the **project root**:

```bash
python scripts/NAP_ingestion/src/transform.py --seed
```

This seeds the dimension tables (companies, industries, currencies) and takes a few seconds. That's enough to run the app. To populate it with full historical transaction data (takes 20–40 min):

```bash
python scripts/NAP_ingestion/src/seed.py --start-date 2021-01-01 --end-date 2026-01-01 --batches 60 -n 38000
python scripts/NAP_ingestion/src/expense_backfill.py
python scripts/NAP_ingestion/src/transform.py --seed
```

Then fix `revenue_growth_rate` nulls by pasting the UPDATE query from `scripts/RESEED.md` Section 6b into psql or pgAdmin.

### 5. Start the API

From the **project root** (with venv active):

```bash
python bouncer.py
```

Open `http://localhost:8000` in a browser. Register a new account to log in.

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
│   ├── setup_db.ps1                    # Windows database setup script
│   ├── setup_db.sh                     # Mac/Linux database setup script
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
