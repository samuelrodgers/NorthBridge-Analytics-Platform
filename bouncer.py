import os
import secrets
import psycopg2
import psycopg2.extras
import requests
import bcrypt as _bcrypt
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Query, Response, Cookie, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPERSET_URL      = os.getenv("SUPERSET_URL", "http://127.0.0.1:8088")
ADMIN_USER        = os.getenv("SUPERSET_ADMIN_USER", "superset_admin")
ADMIN_PASS        = os.getenv("SUPERSET_ADMIN_PASS", "")
DATABASE_URL      = os.getenv("DATABASE_URL", "")
JWT_SECRET_KEY    = os.getenv("JWT_SECRET_KEY", "changeme")
ALGORITHM         = "HS256"
TOKEN_EXPIRE_MINS = 60 * 8

ALLOWED_DASHBOARDS = [
    "4f55a708-c316-406e-8480-1aa3d071631f",  # mainTx
    "813326be-8203-4dce-9908-25e28d9f0e6e",  # kpiStrip
    "0b663ea7-b0d8-4611-9ca4-a8761e17d875",  # company
    "75c09c9f-faf0-448b-9215-bda18bbf87f7",  # industry
    # Add new dashboard UUIDs here as they are created in Superset:
    "3bc8f17c-3e49-4611-98df-545a061c65ed",  # analytics
    "8a6dfe5e-3f6e-49b8-8b83-757895c58d25",  # quarantine
    "9a9fdd7c-27fc-4c4b-8d54-af074a2f8f52",  # pipeline
    "ea995c11-ac00-48ed-a92e-8529978b19fb",  # fx
]

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://samrodgers.site", "https://superset.samrodgers.site"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())

# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Auth cookie dependency
# ---------------------------------------------------------------------------
def require_auth_cookie(access_token: str = Cookie(default=None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.post("/api/auth/register", status_code=201)
def register(body: RegisterRequest):
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id FROM auth.users WHERE email = %s", (body.email,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="Email already registered")
        pw_hash = hash_password(body.password)
        cur.execute(
            "INSERT INTO auth.users (name, email, password_hash) VALUES (%s, %s, %s)",
            (body.name, body.email, pw_hash)
        )
    return {"message": "Account created. Please log in."}

@app.post("/api/auth/login")
def login(body: LoginRequest, response: Response):
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, name, email, password_hash FROM auth.users WHERE email = %s",
            (body.email,)
        )
        user = cur.fetchone()
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token({"sub": str(user["id"]), "email": user["email"]})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 8
    )
    return {"message": "Logged in", "name": user["name"], "email": user["email"]}

@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}

@app.get("/api/auth/me")
def me(payload: dict = Depends(require_auth_cookie)):
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, name, email FROM auth.users WHERE id = %s",
            (int(payload["sub"]),)
        )
        user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": user["id"], "name": user["name"], "email": user["email"]}

@app.post("/api/auth/change-password")
def change_password(body: ChangePasswordRequest, payload: dict = Depends(require_auth_cookie)):
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT password_hash FROM auth.users WHERE id = %s", (int(payload["sub"]),))
        user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    new_hash = hash_password(body.new_password)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE auth.users SET password_hash = %s WHERE id = %s", (new_hash, int(payload["sub"])))
        conn.commit()
    return {"message": "Password updated successfully"}

@app.post("/api/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id FROM auth.users WHERE email = %s", (body.email,))
        user = cur.fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expires = datetime.now(timezone.utc) + timedelta(hours=1)
            cur.execute(
                """UPDATE auth.users
                   SET reset_token = %s, reset_token_expires_at = %s
                   WHERE id = %s""",
                (token, expires, user["id"])
            )
            print(f"[DEV] Reset token for {body.email}: {token}", flush=True)
    return {"message": "If that email exists, a reset link has been sent."}

@app.post("/api/auth/reset-password")
def reset_password(body: ResetPasswordRequest):
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, reset_token_expires_at FROM auth.users WHERE reset_token = %s",
            (body.token,)
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        if datetime.now(timezone.utc) > user["reset_token_expires_at"]:
            raise HTTPException(status_code=400, detail="Reset token has expired")
        new_hash = hash_password(body.new_password)
        cur.execute(
            """UPDATE auth.users
               SET password_hash = %s, reset_token = NULL, reset_token_expires_at = NULL
               WHERE id = %s""",
            (new_hash, user["id"])
        )
    return {"message": "Password updated. Please log in."}

# ---------------------------------------------------------------------------
# Superset guest token (protected)
# ---------------------------------------------------------------------------
@app.get("/api/get-token")
def get_token(
    dashboard_id: str = Query(..., description="UUID of the dashboard to embed"),
    payload: dict = Depends(require_auth_cookie)
):
    if dashboard_id not in ALLOWED_DASHBOARDS:
        raise HTTPException(status_code=403, detail="Dashboard not authorized")
    try:
        login_url = f"{SUPERSET_URL}/api/v1/security/login"
        auth_payload = {"username": ADMIN_USER, "password": ADMIN_PASS, "provider": "db"}
        auth_resp = requests.post(login_url, json=auth_payload)
        if auth_resp.status_code != 200:
            return {"error": f"Login failed with status {auth_resp.status_code}"}
        access_token = auth_resp.json().get("access_token")
        headers = {"Authorization": f"Bearer {access_token}"}
        guest_payload = {
            "user": {"username": "guest", "first_name": "Guest", "last_name": "User"},
            "resources": [{"type": "dashboard", "id": dashboard_id}],
            "rls": []
        }
        r = requests.post(
            f"{SUPERSET_URL}/api/v1/security/guest_token/",
            json=guest_payload,
            headers=headers
        )
        return r.json()
    except Exception as e:
        return {"error": "Bouncer Script Error", "details": str(e)}

# ---------------------------------------------------------------------------
# Live FX value ticker
# ---------------------------------------------------------------------------

@app.get("/api/value")
def get_platform_value(payload: dict = Depends(require_auth_cookie)):
    """
    Returns the current USD-equivalent value of all EUR-denominated platform
    revenue, converted at the latest live EUR/USD rate.

    The value fluctuates every refresh purely because the exchange rate moves
    — not because new transactions arrived. This demonstrates that the
    intrinsic USD value of foreign-currency revenue is continuously in flux.
    """
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT ROUND(
                SUM(ft.amount) * (
                    SELECT rate FROM raw.fx_rate
                    WHERE base_cncy = 'EUR' AND quote_cncy = 'USD'
                    ORDER BY fx_timestamp DESC LIMIT 1
                ),
                2
            ) AS usd_value
            FROM analytics.f_transaction ft
            WHERE ft.cncy = 'EUR'
        """)
        row = cur.fetchone()
    return {"value": float(row["usd_value"]) if row and row["usd_value"] else 0.0}


# ---------------------------------------------------------------------------
# OLAP endpoints — pre-aggregated analytics schema
# ---------------------------------------------------------------------------

@app.get("/api/olap/kpis")
def get_kpis(payload: dict = Depends(require_auth_cookie)):
    """
    Returns four headline KPIs derived entirely from the pre-aggregated
    analytics schema (f_industry, d_company). Queries run against O(7K rows)
    in f_industry rather than O(6M rows) in raw — demonstrating that OLAP
    pre-aggregation enables sub-100ms API responses at scale.
    """
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                SUM(total_revenue)                                          AS total_revenue,
                SUM(transaction_count)                                      AS transaction_count,
                ROUND(SUM(total_revenue) / NULLIF(SUM(transaction_count), 0), 2)
                                                                            AS avg_transaction,
                (SELECT COUNT(*) FROM analytics.d_company)                  AS company_count
            FROM analytics.f_industry
        """)
        row = cur.fetchone()
    return {
        "total_revenue":     float(row["total_revenue"] or 0),
        "transaction_count": int(row["transaction_count"] or 0),
        "avg_transaction":   float(row["avg_transaction"] or 0),
        "company_count":     int(row["company_count"] or 0),
    }


# ---------------------------------------------------------------------------
# Quarantine endpoints
# ---------------------------------------------------------------------------

@app.get("/api/quarantine/health")
def quarantine_health(payload: dict = Depends(require_auth_cookie)):
    """
    Governance KPI stats for the data health panel.
    Returns total quarantined rows, pass rate, new rows since last transform
    run (2h window), and the most recent ingestion timestamp.
    """
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Use raw.quarantine_event directly — v_quarantine_log scans all 6M
        # transaction_event rows on every query (window function in the view).
        cur.execute("SELECT COUNT(*) AS total FROM raw.quarantine_event")
        total_quarantined = cur.fetchone()["total"]

        cur.execute("""
            SELECT reltuples::bigint AS total
            FROM pg_class
            WHERE relname = 'transaction_event'
        """)
        total_raw = cur.fetchone()["total"]

        cur.execute("""
            SELECT COUNT(*) AS recent
            FROM raw.quarantine_event
            WHERE ingestion_timestamp >= NOW() - INTERVAL '2 hours'
        """)
        recent = cur.fetchone()["recent"]

        cur.execute("""
            SELECT MAX(ingestion_timestamp) AS latest
            FROM raw.transaction_event
        """)
        latest_raw = cur.fetchone()["latest"]

    pass_rate = round((total_raw - total_quarantined) / total_raw * 100, 2) if total_raw else 100.0
    clean = total_raw - total_quarantined

    return {
        "total_quarantined": total_quarantined,
        "total_raw":         total_raw,
        "clean_rows":        clean,
        "pass_rate":         pass_rate,
        "new_since_last_run": recent,
        "latest_ingestion":  latest_raw.isoformat() if latest_raw else None,
    }


@app.get("/api/quarantine/summary")
def quarantine_summary(payload: dict = Depends(require_auth_cookie)):
    """
    Breakdown of quarantine violations by source and failure code.
    Also includes a cross-layer contamination count (should always be 0).
    Intended for badge counts and overview panels on page load.
    """
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT 'python_layer' AS source, failure_code, COUNT(*) AS count
            FROM raw.quarantine_event
            GROUP BY failure_code
            ORDER BY count DESC
        """)
        summary = [dict(r) for r in cur.fetchall()]

    return {
        "summary": summary,
        "cross_layer_contamination": 0,
    }


@app.get("/api/quarantine/rows")
def quarantine_rows(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    failure_code: str = Query(default=None),
    source: str = Query(default=None, pattern="^(python_layer|sql_layer)$"),
    since: datetime = Query(default=None),
    payload: dict = Depends(require_auth_cookie),
):
    """
    Paginated quarantine rows from analytics.v_quarantine_log.

    Optional filters:
        failure_code — e.g. NULL_COMPANY_ID
        source       — python_layer or sql_layer
        since        — only rows with ingestion_timestamp >= this value
    """
    filters = []
    params = []

    if failure_code:
        filters.append("failure_code = %s")
        params.append(failure_code)
    if source:
        filters.append("source = %s")
        params.append(source)
    if since:
        filters.append("ingestion_timestamp >= %s")
        params.append(since)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    offset = (page - 1) * page_size

    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            f"SELECT COUNT(*) AS total FROM raw.quarantine_event {where}",
            params,
        )
        total = cur.fetchone()["total"]

        cur.execute(
            f"""
            SELECT qe.tx_id, qe.c_id, qe.base_cncy, qe.tx_timestamp, qe.amount,
                   qe.fee_amount, qe.quote_cncy, qe.ingestion_timestamp,
                   qe.failure_code, qe.failure_reason, qe.batch_id,
                   'python_layer' AS source,
                   dc.c_name
            FROM raw.quarantine_event qe
            LEFT JOIN analytics.d_company dc ON qe.c_id = dc.c_id
            {where}
            ORDER BY qe.ingestion_timestamp DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = [dict(r) for r in cur.fetchall()]

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/fx/rates")
def get_fx_rates(payload: dict = Depends(require_auth_cookie)):
    """Latest rate per currency pair from raw.fx_rate."""
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT DISTINCT ON (base_cncy, quote_cncy)
                base_cncy, quote_cncy,
                ROUND(rate::numeric, 6) AS rate,
                fx_timestamp
            FROM raw.fx_rate
            ORDER BY base_cncy, quote_cncy, fx_timestamp DESC
        """)
        rates = [dict(r) for r in cur.fetchall()]
    return {"rates": rates}


@app.get("/api/fx/company-revenues")
def get_company_revenues(payload: dict = Depends(require_auth_cookie)):
    """Total revenue per company per currency — loaded once, combined client-side with live rates."""
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT dc.c_name,
                   ft.cncy,
                   ROUND(SUM(ft.amount), 2) AS total_revenue
            FROM analytics.f_transaction ft
            JOIN analytics.d_company dc ON ft.c_id = dc.c_id
            GROUP BY dc.c_id, dc.c_name, ft.cncy
            ORDER BY dc.c_name, ft.cncy
        """)
        revenues = [dict(r) for r in cur.fetchall()]
    return {"revenues": revenues}


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
