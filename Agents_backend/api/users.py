"""Email + password accounts for the web UI.

Complements `api/auth.py`, which is a single shared secret for the whole API.
This is per-user: signup, login, and a `GET /api/auth/me` the frontend calls on
boot to decide between the dashboard and the login screen.

Deliberately dependency-free:
  * passwords are hashed with `hashlib.scrypt` (stdlib) — no bcrypt/passlib,
  * sessions are stateless HMAC-signed tokens — no JWT library, no session
    table to create or vacuum.

`AUTH_SECRET` in `.env` signs the tokens. It falls back to `API_KEY`, then to a
fixed development string — set it in any deployment, or every restart with a
different value silently logs everyone out (and the fixed fallback means anyone
who reads this file can mint a token).

ponytail: stateless tokens, so sign-out is client-side only and a stolen token
stays valid until it expires. Add a `sessions` table if revocation matters.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from db import get_db, _format_sql

logger = logging.getLogger("api.users")
router = APIRouter(tags=["auth"])

TOKEN_TTL_SECONDS = 7 * 24 * 3600
MIN_PASSWORD_LENGTH = 8
# Good enough to catch typos and reject junk; real validation is "can they
# receive mail", which this app never tests.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT,
    password_hash TEXT NOT NULL,
    created_at    TEXT
);
"""


def init_users():
    with get_db() as conn:
        conn.execute(_format_sql(_CREATE_USERS))
        conn.commit()


# ============================================================================
# PASSWORDS
# ============================================================================

def hash_password(password: str) -> str:
    """`scrypt$<salt hex>$<derived key hex>`. n=2**14 keeps memory at ~16 MB."""
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, dk_hex = (stored or "").split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), dk_hex)


# ============================================================================
# TOKENS
# ============================================================================

def _secret() -> bytes:
    return (
        os.getenv("AUTH_SECRET")
        or os.getenv("API_KEY")
        or "dev-insecure-secret-set-AUTH_SECRET"
    ).strip().encode()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(user_id: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": user_id, "exp": int(time.time()) + ttl}).encode()
    ).decode().rstrip("=")
    return f"{payload}.{_sign(payload)}"


def user_id_from_token(token: str | None) -> str | None:
    """The user id a valid, unexpired token names — otherwise None."""
    if not token or "." not in token:
        return None
    payload, _, signature = token.rpartition(".")
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    if data.get("exp", 0) <= time.time():
        return None
    return data.get("sub")


def current_user(request: Request) -> dict | None:
    """Resolve the caller from `Authorization: Bearer ...`, or None."""
    header = request.headers.get("Authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    user_id = user_id_from_token(token)
    return get_user_by_id(user_id) if user_id else None


# ============================================================================
# CRUD
# ============================================================================

def _public(row) -> dict:
    """The user fields safe to hand back to the browser — never the hash."""
    d = dict(row)
    return {
        "id": d["id"],
        "email": d["email"],
        "name": d.get("name") or "",
        "created_at": d.get("created_at"),
    }


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        cursor = conn.execute(
            _format_sql("SELECT * FROM users WHERE email = ?"), (email.strip().lower(),)
        )
        row = cursor.fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    with get_db() as conn:
        cursor = conn.execute(_format_sql("SELECT * FROM users WHERE id = ?"), (user_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


def create_user(email: str, password: str, name: str = "") -> dict:
    user = {
        "id": str(uuid.uuid4()),
        "email": email.strip().lower(),
        "name": name.strip(),
        "password_hash": hash_password(password),
        "created_at": datetime.now(UTC).isoformat(),
    }
    with get_db() as conn:
        conn.execute(
            _format_sql(
                "INSERT INTO users (id, email, name, password_hash, created_at)"
                " VALUES (?,?,?,?,?)"
            ),
            (user["id"], user["email"], user["name"],
             user["password_hash"], user["created_at"]),
        )
        conn.commit()
    return _public(user)


# ============================================================================
# ROUTES
# ============================================================================

class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


def _validate(email: str, password: str) -> None:
    if not _EMAIL_RE.match(email.strip()):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )


@router.post("/api/auth/signup", status_code=status.HTTP_201_CREATED)
async def signup(req: SignupRequest):
    _validate(req.email, req.password)
    if get_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="That email is already registered.")
    user = create_user(req.email, req.password, req.name)
    logger.info(f"New account: {user['email']}")
    return {"token": make_token(user["id"]), "user": user}


@router.post("/api/auth/login")
async def login(req: LoginRequest):
    user = get_user_by_email(req.email)
    # Same message either way: a distinct "no such account" would tell an
    # attacker which emails are registered.
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return {"token": make_token(user["id"]), "user": _public(user)}


@router.get("/api/auth/me")
async def me(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return _public(user)


init_users()
