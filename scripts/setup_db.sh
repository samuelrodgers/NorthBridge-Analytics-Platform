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

export PGPASSWORD="$PG_PASSWORD"

psql_run() {
    psql -U "$DB_SUPERUSER" -d "${2:-postgres}" -c "$1"
}

psql_file() {
    echo "  Applying $(basename "$1")..."
    psql -U "$DB_SUPERUSER" -d "$DB_NAME" -f "$1"
}

# ── Create database and user ──────────────────────────────────────────────────

echo -e "\n[1/4] Creating database and user..."

psql_run "CREATE DATABASE $DB_NAME;"
psql_run "CREATE USER $APP_USER WITH PASSWORD '$APP_PASSWORD';"
psql_run "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $APP_USER;"

# ── Apply base schema ─────────────────────────────────────────────────────────

echo -e "\n[2/4] Applying base schema..."

psql_file "$SCRIPT_DIR/SQL/Scripts/analytics_create_tables.sql"
psql_file "$SCRIPT_DIR/SQL/Scripts/Create_auth.sql"

# ── Apply migrations ──────────────────────────────────────────────────────────

echo -e "\n[3/4] Applying migrations..."

for f in "$SCRIPT_DIR"/SQL/Migrations/0*.sql; do
    psql_file "$f"
done

# ── Grant schema access ───────────────────────────────────────────────────────

echo -e "\n[4/4] Granting schema access to $APP_USER..."

psql -U "$DB_SUPERUSER" -d "$DB_NAME" -c "
GRANT USAGE, CREATE ON SCHEMA analytics TO $APP_USER;
GRANT ALL ON ALL TABLES IN SCHEMA analytics TO $APP_USER;
GRANT ALL ON ALL SEQUENCES IN SCHEMA analytics TO $APP_USER;
GRANT USAGE, CREATE ON SCHEMA raw TO $APP_USER;
GRANT ALL ON ALL TABLES IN SCHEMA raw TO $APP_USER;
GRANT ALL ON ALL SEQUENCES IN SCHEMA raw TO $APP_USER;
GRANT USAGE, CREATE ON SCHEMA auth TO $APP_USER;
GRANT ALL ON ALL TABLES IN SCHEMA auth TO $APP_USER;
GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO $APP_USER;
"

echo -e "\nDone. Database '$DB_NAME' is ready."
echo "Update your .env files with: DB_USER=$APP_USER  DB_PASS=<the password you entered>"
