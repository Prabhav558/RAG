"""Phase 2 authentication and RBAC. Spec: docs/14_PHASE2_SECURITY_SPEC.md.

Password hashing and session tokens use only the standard library (no new dependency, no secret-management
surface beyond the database itself). Every workflow actor is now a verified UserAccount.display_name, never a
client-supplied header.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_session
from .models import AuthSession, UserAccount
from .schemas import Contract
from .services import DomainError, now

PBKDF2_ITERATIONS = 260_000
SESSION_TTL_DAYS = int(os.environ.get("SESSION_TTL_DAYS", "14"))
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
ROLES = ("admin", "designer", "reviewer", "lead", "importer")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,59}$")


# ---------------------------------------------------------------- password hashing


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations_s, salt_hex, hash_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


# ---------------------------------------------------------------- tokens


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: UserAccount) -> str:
    token = _new_token()
    db.add(AuthSession(user_id=user.id, token_hash=_token_hash(token),
                       expires_at=now() + timedelta(days=SESSION_TTL_DAYS)))
    return token


def revoke_session(db: Session, token: str) -> None:
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if row and row.revoked_at is None:
        row.revoked_at = now()


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def user_from_token(db: Session, token: str) -> UserAccount | None:
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if not row or row.revoked_at is not None or _aware(row.expires_at) < now():
        return None
    if not row.user.is_active:
        return None
    return row.user


# ---------------------------------------------------------------- registration / login


class RegisterIn(Contract):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=200)


class LoginIn(Contract):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


def register(db: Session, data: RegisterIn) -> UserAccount:
    username = data.username.strip().lower()
    if not USERNAME_RE.match(username):
        raise DomainError("AUTH005", "Username must be 3-60 characters: letters, numbers, '.', '_', '-' only")
    if db.scalar(select(UserAccount).where(UserAccount.username == username)):
        raise DomainError("AUTH001", f"Username '{username}' is already taken", 409)
    display_name = data.display_name.strip()
    if not display_name:
        raise DomainError("AUTH009", "Display name cannot be blank")
    # Bootstrap: the very first account ever created (on a fresh database) is automatically an admin, so there
    # is always someone able to grant roles to everyone else without a side channel into the database.
    is_first = db.scalar(select(func.count()).select_from(UserAccount)) == 0
    user = UserAccount(username=username, email=(data.email or None), display_name=display_name,
                       password_hash=hash_password(data.password), roles=["admin"] if is_first else [])
    db.add(user)
    db.flush()
    return user


def login(db: Session, data: LoginIn) -> tuple[UserAccount, str]:
    user = db.scalar(select(UserAccount).where(UserAccount.username == data.username.strip().lower()))
    if user and user.locked_until and _aware(user.locked_until) > now():
        raise DomainError("AUTH002", "Account locked after too many failed attempts; try again later", 423)
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= LOGIN_MAX_ATTEMPTS:
                user.locked_until = now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
            # The caller's db.commit() never runs on this path since we raise here, so persist now.
            db.commit()
        raise DomainError("AUTH003", "Incorrect username or password", 401)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now()
    token = create_session(db, user)
    return user, token


# ---------------------------------------------------------------- FastAPI dependencies


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip() or None


def get_current_user(authorization: str | None = Header(default=None),
                     db: Session = Depends(get_session)) -> UserAccount:
    token = _extract_bearer(authorization)
    if not token:
        raise DomainError("AUTH004", "Login required: send 'Authorization: Bearer <token>'", 401)
    user = user_from_token(db, token)
    if not user:
        raise DomainError("AUTH004", "Session is invalid, expired or revoked; log in again", 401)
    return user


def get_optional_user(authorization: str | None = Header(default=None),
                      db: Session = Depends(get_session)) -> UserAccount | None:
    token = _extract_bearer(authorization)
    return user_from_token(db, token) if token else None


def actor_name(user: UserAccount = Depends(get_current_user)) -> str:
    """Drop-in replacement for the old X-Actor header: a verified display name."""
    return user.display_name


def optional_actor_name(user: UserAccount | None = Depends(get_optional_user)) -> str | None:
    return user.display_name if user else None


def require_role(*roles: str):
    """Any of `roles`, or admin (which always passes). Guards go on top of, never instead of, identity checks."""

    def dependency(user: UserAccount = Depends(get_current_user)) -> UserAccount:
        if "admin" in user.roles or any(r in user.roles for r in roles):
            return user
        raise DomainError("AUTH006", f"This action needs the '{roles[0]}' role", 403)

    return dependency
