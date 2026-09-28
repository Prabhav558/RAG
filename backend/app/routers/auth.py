"""Registration, login/logout, current-user info, and admin user management (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from .. import services as svc
from ..db import get_session
from ..models import UserAccount
from ..schemas import Contract

router = APIRouter(prefix="/api")


def _view(u: UserAccount) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "email": u.email,
            "roles": u.roles, "is_active": u.is_active, "created_at": u.created_at, "last_login_at": u.last_login_at}


@router.post("/auth/register", status_code=201)
def register(body: auth.RegisterIn, db: Session = Depends(get_session)):
    user = auth.register(db, body)
    token = auth.create_session(db, user)
    db.commit()
    return {"token": token, "user": _view(user)}


@router.post("/auth/login")
def do_login(body: auth.LoginIn, db: Session = Depends(get_session)):
    user, token = auth.login(db, body)
    db.commit()
    return {"token": token, "user": _view(user)}


@router.post("/auth/logout", status_code=204)
def do_logout(authorization: str | None = Header(default=None), db: Session = Depends(get_session)):
    token = auth._extract_bearer(authorization)
    if token:
        auth.revoke_session(db, token)
        db.commit()


@router.get("/auth/me")
def me(user: UserAccount = Depends(auth.get_current_user)):
    return _view(user)


class RoleUpdate(Contract):
    roles: list[str] | None = None
    is_active: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


@router.get("/users")
def list_users(_: UserAccount = Depends(auth.require_role("admin")), db: Session = Depends(get_session)):
    return [_view(u) for u in db.scalars(select(UserAccount).order_by(UserAccount.username))]


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: RoleUpdate, admin: UserAccount = Depends(auth.require_role("admin")),
                db: Session = Depends(get_session)):
    u = db.get(UserAccount, user_id)
    if not u:
        raise svc.DomainError("E404", f"User {user_id} not found", 404)
    if body.roles is not None:
        bad = set(body.roles) - set(auth.ROLES)
        if bad:
            raise svc.DomainError("AUTH007", f"Unknown role(s): {', '.join(sorted(bad))}. Valid: {', '.join(auth.ROLES)}")
        u.roles = sorted(set(body.roles))
    if body.is_active is not None:
        if u.id == admin.id and not body.is_active:
            raise svc.DomainError("AUTH008", "You cannot deactivate your own account", 409)
        u.is_active = body.is_active
    if body.display_name is not None:
        u.display_name = body.display_name.strip()
    db.commit()
    return _view(u)
