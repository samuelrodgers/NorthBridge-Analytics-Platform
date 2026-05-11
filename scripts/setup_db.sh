#!/usr/bin/env bash
# setup_db.sh — Northbridge Analytics Platform database setup (Mac/Linux)
# Run from the project root:
#   bash scripts/setup_db.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_NAME="northbridge"
DB_SUPERUSER="postgres"
APP_USER="nap_user"

# ── Credentials ───────────────────────────────────────────────────────────────

read -rsp "PostgreSQL superuser ($DB_SUPERUSER) password: " PG_PASSWORD; echo
read -rsp "Password to set for new '$APP_USER' DB user: " APP_PASSWORD; echo

# Helper: run SQL as the postgres superuser
psql_super() {
    PGPASSWORD="$PG_PASSWORD" psql -U "$DB_SUPERUSER" -d "${2:-postgres}" -c "$1"
}

# Helper: run a SQL file as the app user (nap_user owns all created objects)
psql_file() {
    echo "  Applying $(basename "$1")..."
    PGPASSWORD="$APP_PASSWORD" psql -U "$APP_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$1"
}

# ── Create database and user ──────────────────────────────────────────────────

echo -e "\n[1/3] Creating database and user..."

psql_super "CREATE DATABASE $DB_NAME;"
psql_super "CREATE USER $APP_USER WITH PASSWORD '$APP_PASSWORD';"
psql_super "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $APP_USER;"

# ── Apply base schema and migrations (as app user) ────────────────────────────
# Running as nap_user means it owns all schemas, tables, and functions.
# No separate GRANT step is needed — owners have full access automatically.

echo -e "\n[2/3] Applying schema and migrations..."

psql_file "$SCRIPT_DIR/SQL/Scripts/analytics_create_tables.sql"
psql_file "$SCRIPT_DIR/SQL/Scripts/Create_auth.sql"

for f in "$SCRIPT_DIR"/SQL/Migrations/0*.sql; do
    psql_file "$f"
done

# ── Write .env files ──────────────────────────────────────────────────────────

echo -e "\n[3/3] Writing .env files..."

JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null \
    || openssl rand -base64 32)

cat > "$SCRIPT_DIR/../.env" <<EOF
DATABASE_URL=postgresql://${APP_USER}:${APP_PASSWORD}@localhost:5432/${DB_NAME}
JWT_SECRET_KEY=${JWT_SECRET}
SUPERSET_URL=http://127.0.0.1:8088
SUPERSET_ADMIN_USER=admin
SUPERSET_ADMIN_PASS=
EOF

cat > "$SCRIPT_DIR/NAP_ingestion/.env" <<EOF
DB_HOST=localhost
DB_PORT=5432
DB_NAME=${DB_NAME}
DB_USER=${APP_USER}
DB_PASS=${APP_PASSWORD}
TWELVE_DATA_API_KEY=
EOF

echo "  Written: .env"
echo "  Written: scripts/NAP_ingestion/.env"

echo -e "\nDone. Database '$DB_NAME' is ready."
