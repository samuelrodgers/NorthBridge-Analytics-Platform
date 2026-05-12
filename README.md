# Northbridge Analytics Platform

A synthetic financial analytics platform built as a senior capstone project (CPSC 498, Christopher Newport University, Spring 2026). It generates realistic multi-currency transaction data, runs it through a data quality pipeline, and surfaces the results through a custom dashboard backed by Apache Superset.

## What it does

- **Synthetic data pipeline** — generates transactions across 12 fictional companies in 4 industries and 14 currencies, injects realistic data quality issues (malformed timestamps, currency aliases, missing fields), and routes records through a quarantine/resolution workflow
- **Star-schema data warehouse** — PostgreSQL with `raw` (append-only ingestion), `analytics` (transformed fact/dimension tables), and `auth` schemas
- **FastAPI backend** (`bouncer.py`) — proxies Superset embeds, handles authentication (JWT + bcrypt), exposes data quality and governance APIs
- **Dashboard frontend** — HTML/CSS/JS pages for FX rates, transaction volume, data governance, and quarantine resolution
- **ML analysis** (`scripts/NAP_ingestion/src/ml_analysis.py`) — PCA, k-means clustering, and t-SNE on the generated transaction data

## Demo

> **[Watch the demo on YouTube](https://youtu.be/-I-33UQY6hY)**

The demo walks through the dashboard pages and shows the quarantine resolution workflow in action. When this project was active, it ran on AWS (EC2 + RDS) as a fully live, publicly accessible site with real-time data ingestion and forex rate feeds running continuously. What's in this repository is the local version — all the same code, but run on your own machine against a locally seeded database rather than the hosted instance. The demo doesn't cover every technical aspect of the project, but it serves as a record of what the platform looked like when it was live.

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Docker (required for Superset)

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

A setup script handles everything — creating the database and `nap_user` account, applying the schema, and running all 18 migrations. Run it from the **project root** in a separate terminal (no venv needed).

**Windows (PowerShell):**

```powershell
.\scripts\setup_db.ps1
```

The script will auto-detect your PostgreSQL install and prompt for passwords. If it can't find `psql.exe`, enter the full path when prompted (e.g. `D:\PostgreSQL\pgAdmin 4\runtime\psql.exe`).

**Mac/Linux:**

```bash
bash scripts/setup_db.sh
```

Both scripts create a `northbridge` database and a `nap_user` account, then apply the full schema and migrations, and write the `.env` files automatically.

### 3. Configure environment variables

The setup script writes both `.env` files automatically using the credentials you entered. No manual copying needed.

You will need to add your Superset admin password once Superset is running (see Frontend setup below):

- **`.env`** (project root) — add `SUPERSET_ADMIN_PASS` after Superset is set up

### 4. Seed the database

With the venv active, run from the **project root**:

```bash
python scripts/NAP_ingestion/src/transform.py --seed
```

This seeds the dimension tables (companies, industries, currencies) and takes a few seconds.

### 5. Full historical data (20–40 min)

The quick seed populates dimension tables only. For meaningful chart data covering 2021–2026, run the historical seed. Bouncer does not need to be running for this — the seed scripts connect directly to PostgreSQL. This is a good time to start the Frontend setup below in parallel:

```bash
python scripts/NAP_ingestion/src/seed.py --start-date 2021-01-01 --end-date 2026-01-01 --batches 60 -n 38000
python scripts/NAP_ingestion/src/expense_backfill.py
python scripts/NAP_ingestion/src/transform.py --seed
```

Then fix `revenue_growth_rate` nulls by pasting the UPDATE query from `scripts/RESEED.md` Section 6b into psql or pgAdmin.

## Frontend setup

### 1. Start the API

From the **project root** (with venv active):

```bash
python bouncer.py
```

Open `http://localhost:8000` in a browser and register a new account to log in.

Once logged in you can navigate all four pages — FX Rates, Transaction Volume, Data Governance, and Quarantine. The embedded chart panels require Superset to be configured (next step). Everything else — tables, the quarantine resolution workflow, and the governance metrics — works without it.

### 2. Superset

Superset powers the embedded chart panels on every page. Follow these steps to get it running and connected to your local database.

**Install Superset via Docker Compose** — follow the [official quick-start guide](https://superset.apache.org/docs/installation/docker-compose). Once running, Superset is available at `http://127.0.0.1:8088`.

**Import the dashboard snapshot** — in the Superset UI go to **Settings → Import dashboards** and upload `superset_dashboard_backup.zip` from the project root. This restores all charts, datasets, and dashboard layouts.

**Update the database connection** — the imported snapshot contains a connection pointed at the original server. Go to **Settings → Database Connections**, find the Northbridge entry, and update the SQLAlchemy URI to:

```
postgresql://nap_user:<your_password>@localhost:5432/northbridge
```

**Update `.env`** — open `.env` in the project root and add your Superset admin password:

```
SUPERSET_ADMIN_PASS=<your Superset admin password>
```

Restart `bouncer.py` and the chart panels will populate.

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

## Ongoing data ingestion

To keep the project running with live data, two scripts need to run on a schedule.

**Transaction batches** — each call to `main.py` generates one batch of synthetic transactions for a 10-minute window and runs the full pipeline through to the analytics schema. Run this every 10 minutes or so to simulate ongoing activity:

```bash
python scripts/NAP_ingestion/src/main.py -n 100
```

**FX rate feed** — `live_synthetic.py` writes a new synthetic FX rate tick every 5 seconds to the database. This is what drives the live refresh on the FX Rates page. Run it as a persistent background process:

```bash
python scripts/NAP_ingestion/src/live_synthetic.py
```

On Windows you can use Task Scheduler for `main.py` and run `live_synthetic.py` in a dedicated terminal. On Mac/Linux, use `cron` for `main.py` and a background process or `systemd` service for `live_synthetic.py`.

## Author

Samuel Rodgers — CPSC 498 Senior Capstone, Christopher Newport University, Spring 2026
