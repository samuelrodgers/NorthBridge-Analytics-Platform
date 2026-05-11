# setup_db.ps1 — Northbridge Analytics Platform database setup (Windows)
# Run from the project root in PowerShell:
#   .\scripts\setup_db.ps1

param(
    [string]$PsqlPath,
    [string]$PgPassword,
    [string]$DbUser = "postgres",
    [string]$DbName = "northbridge",
    [string]$AppUser = "nap_user",
    [string]$AppPassword
)

# ── Locate psql ───────────────────────────────────────────────────────────────

if (-not $PsqlPath) {
    $candidates = @(
        "C:\Program Files\PostgreSQL\18\bin\psql.exe",
        "C:\Program Files\PostgreSQL\17\bin\psql.exe",
        "C:\Program Files\PostgreSQL\16\bin\psql.exe",
        "C:\Program Files\PostgreSQL\15\bin\psql.exe",
        "D:\PostgreSQL\pgAdmin 4\runtime\psql.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $PsqlPath = $c; break }
    }
}

if (-not $PsqlPath -or -not (Test-Path $PsqlPath)) {
    $PsqlPath = Read-Host "psql not found automatically. Enter full path to psql.exe"
}

Write-Host "Using psql: $PsqlPath"

# ── Credentials ───────────────────────────────────────────────────────────────

if (-not $PgPassword) {
    $secure = Read-Host "PostgreSQL superuser ($DbUser) password" -AsSecureString
    $PgPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

if (-not $AppPassword) {
    $secure2 = Read-Host "Password to set for new '$AppUser' DB user" -AsSecureString
    $AppPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure2)
    )
}

$env:PGPASSWORD = $PgPassword

function Invoke-Psql {
    param([string]$Sql, [string]$Database = "postgres")
    & $PsqlPath -U $DbUser -d $Database -c $Sql
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: command failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}

function Invoke-PsqlFile {
    param([string]$File, [string]$Database = $DbName)
    Write-Host "  Applying $([System.IO.Path]::GetFileName($File))..."
    & $PsqlPath -U $DbUser -d $Database -f $File
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: failed on $File (exit $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}

# ── Create database and user ──────────────────────────────────────────────────

Write-Host "`n[1/4] Creating database and user..." -ForegroundColor Cyan

Invoke-Psql "CREATE DATABASE $DbName;"
Invoke-Psql "CREATE USER $AppUser WITH PASSWORD '$AppPassword';"
Invoke-Psql "GRANT ALL PRIVILEGES ON DATABASE $DbName TO $AppUser;"

# ── Apply base schema ─────────────────────────────────────────────────────────

Write-Host "`n[2/4] Applying base schema..." -ForegroundColor Cyan

Invoke-PsqlFile "$PSScriptRoot\SQL\Scripts\analytics_create_tables.sql"
Invoke-PsqlFile "$PSScriptRoot\SQL\Scripts\Create_auth.sql"

# ── Apply migrations ──────────────────────────────────────────────────────────

Write-Host "`n[3/4] Applying migrations..." -ForegroundColor Cyan

Get-ChildItem "$PSScriptRoot\SQL\Migrations\0*.sql" | Sort-Object Name | ForEach-Object {
    Invoke-PsqlFile $_.FullName
}

# ── Grant schema access ───────────────────────────────────────────────────────

Write-Host "`n[4/4] Granting schema access to $AppUser..." -ForegroundColor Cyan

$grants = @"
GRANT USAGE, CREATE ON SCHEMA analytics TO $AppUser;
GRANT ALL ON ALL TABLES IN SCHEMA analytics TO $AppUser;
GRANT ALL ON ALL SEQUENCES IN SCHEMA analytics TO $AppUser;
GRANT USAGE, CREATE ON SCHEMA raw TO $AppUser;
GRANT ALL ON ALL TABLES IN SCHEMA raw TO $AppUser;
GRANT ALL ON ALL SEQUENCES IN SCHEMA raw TO $AppUser;
GRANT USAGE, CREATE ON SCHEMA auth TO $AppUser;
GRANT ALL ON ALL TABLES IN SCHEMA auth TO $AppUser;
GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO $AppUser;
"@

& $PsqlPath -U $DbUser -d $DbName -c $grants
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: grants failed" -ForegroundColor Red; exit 1 }

# ── Write .env files ──────────────────────────────────────────────────────────

Write-Host "`n[5/5] Writing .env files..." -ForegroundColor Cyan

$JwtSecret = [System.Convert]::ToBase64String(
    [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
)

$RootEnvPath     = Join-Path $PSScriptRoot ".." ".env"
$PipelineEnvPath = Join-Path $PSScriptRoot "NAP_ingestion" ".env"

@"
DATABASE_URL=postgresql://${AppUser}:${AppPassword}@localhost:5432/${DbName}
JWT_SECRET_KEY=${JwtSecret}
SUPERSET_URL=http://127.0.0.1:8088
SUPERSET_ADMIN_USER=admin
SUPERSET_ADMIN_PASS=
"@ | Out-File -FilePath $RootEnvPath -Encoding ASCII

@"
DB_HOST=localhost
DB_PORT=5432
DB_NAME=${DbName}
DB_USER=${AppUser}
DB_PASS=${AppPassword}
TWELVE_DATA_API_KEY=
"@ | Out-File -FilePath $PipelineEnvPath -Encoding ASCII

Write-Host "  Written: .env"
Write-Host "  Written: scripts/NAP_ingestion/.env"

Write-Host "`nDone. Database '$DbName' is ready." -ForegroundColor Green
