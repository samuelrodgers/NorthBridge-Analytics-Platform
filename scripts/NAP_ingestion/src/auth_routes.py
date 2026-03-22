# auth_routes.py
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Response, HTTPException, Depends, Cookie
from pydantic import BaseModel, EmailStr
import asyncpg

from auth_config import (
    hash_password, verify_password,
    create_access_token, decode_access_token
)

router = APIRouter(prefix="/api/auth")

# --- Pydantic models ---
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

# --- DB dependency (reuse your existing pool pattern) ---
# Replace this with however your Bouncer currently gets a DB connection.
# If you use a global asyncpg pool, import it here instead.
async def get_db(request: Request) -> asyncpg.Connection:
    async with request.app.state.db_pool.acquire() as conn:
        yield conn

# ------------------------------------------------------------------ #
#  REGISTER                                                            #
# ------------------------------------------------------------------ #
@router.post("/register", status_code=201)
async def register(body: RegisterRequest, db=Depends(get_db)):
    existing = await db.fetchrow(
        "SELECT id FROM users WHERE email = $1", body.email
    )
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    pw_hash = hash_password(body.password)
    await db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES ($1, $2, $3)",
        body.name, body.email, pw_hash
    )
    return {"message": "Account created. Please log in."}

# ------------------------------------------------------------------ #
#  LOGIN                                                               #
# ------------------------------------------------------------------ #
@router.post("/login")
async def login(body: LoginRequest, response: Response, db=Depends(get_db)):
    user = await db.fetchrow(
        "SELECT id, name, email, password_hash FROM users WHERE email = $1",
        body.email
    )
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": str(user["id"]), "email": user["email"]})

    # HttpOnly cookie — JS cannot read this, which is the point
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,        # requires HTTPS — fine since you're on 443
        samesite="lax",
        max_age=60 * 60 * 8
    )
    return {"message": "Logged in", "name": user["name"], "email": user["email"]}

# ------------------------------------------------------------------ #
#  LOGOUT                                                              #
# ------------------------------------------------------------------ #
@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}

# ------------------------------------------------------------------ #
#  ME — used by frontend to check session on page load                #
# ------------------------------------------------------------------ #
@router.get("/me")
async def me(access_token: str | None = Cookie(default=None), db=Depends(get_db)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await db.fetchrow(
        "SELECT id, name, email FROM users WHERE id = $1",
        int(payload["sub"])
    )
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {"id": user["id"], "name": user["name"], "email": user["email"]}

# ------------------------------------------------------------------ #
#  FORGOT PASSWORD                                                     #
# ------------------------------------------------------------------ #
@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db=Depends(get_db)):
    user = await db.fetchrow("SELECT id FROM users WHERE email = $1", body.email)

    # Always return 200 — never reveal whether an email exists
    if user:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.execute(
            """UPDATE users
               SET reset_token = $1, reset_token_expires_at = $2
               WHERE id = $3""",
            token, expires, user["id"]
        )
        # In a real system: send email here.
        # For demo: return the token directly so you can test the flow.
        print(f"[DEV ONLY] Password reset token for {body.email}: {token}")

    return {"message": "If that email exists, a reset link has been sent."}

# ------------------------------------------------------------------ #
#  RESET PASSWORD                                                      #
# ------------------------------------------------------------------ #
@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db=Depends(get_db)):
    user = await db.fetchrow(
        """SELECT id, reset_token_expires_at FROM users
           WHERE reset_token = $1""",
        body.token
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if datetime.now(timezone.utc) > user["reset_token_expires_at"]:
        raise HTTPException(status_code=400, detail="Reset token has expired")

    new_hash = hash_password(body.new_password)
    await db.execute(
        """UPDATE users
           SET password_hash = $1, reset_token = NULL, reset_token_expires_at = NULL
           WHERE id = $2""",
        new_hash, user["id"]
    )
    return {"message": "Password updated. Please log in."}