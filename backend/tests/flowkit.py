"""Helpers to drive the Cycle 3 workflows through the API (shared by workflow and acceptance tests).

Phase 2 made every workflow action require a real login. `H(actor)` keeps the
old call shape used throughout these tests: it transparently registers/logs in a user for that display name (once
per test, cached) and returns a real `Authorization: Bearer <token>` header.

Newly-registered test actors are granted every role, because these tests exercise workflow and
separation-of-duties rules, not role-based authorisation (RBAC itself has dedicated tests in test_auth.py). The
grant goes through the ordinary admin API (`PATCH /api/users/{id}`), using the client's own default identity —
the `client` fixture in conftest.py registers as the very first user of a fresh database, which `auth.register`
always makes an admin — never a direct database side channel. This is also why it works unchanged against a
live remote server, not just the in-process TestClient.
"""

from __future__ import annotations

import re
import threading

from app import auth

from .conftest import definition, leaf

TEST_PASSWORD = "Test-Password-123!"
_DEFAULT_CLIENT = None
_TOKENS: dict[tuple[int, str], str] = {}
_LOCK = threading.Lock()


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if len(s) < 3:
        s = (s + "-user")[:10]
    return s[:60]


def _login_as(client, display_name: str) -> str:
    username = _slug(display_name)
    r = client.post("/api/auth/register",
                    json={"username": username, "password": TEST_PASSWORD, "display_name": display_name.strip()})
    if r.status_code == 201:
        user = r.json()["user"]
        if "admin" not in user["roles"]:
            grant = client.patch(f"/api/users/{user['id']}", json={"roles": list(auth.ROLES)})
            assert grant.status_code == 200, grant.text
        return r.json()["token"]
    r = client.post("/api/auth/login", json={"username": username, "password": TEST_PASSWORD})
    if r.status_code != 200:
        raise RuntimeError(f"flowkit could not authenticate test actor {display_name!r}: {r.status_code} {r.text}")
    return r.json()["token"]


def H(actor: str) -> dict:
    if _DEFAULT_CLIENT is None:
        raise RuntimeError("H() needs a Flow(client) constructed first in this test")
    key = (id(_DEFAULT_CLIENT), actor.strip().lower())
    with _LOCK:
        token = _TOKENS.get(key)
        if token is None:
            token = _login_as(_DEFAULT_CLIENT, actor)
            _TOKENS[key] = token
    return {"Authorization": f"Bearer {token}"}


class Flow:
    def __init__(self, client):
        global _DEFAULT_CLIENT
        self.c = client
        self.n = 0
        _DEFAULT_CLIENT = client
        # Each test wipes and recreates the database (see conftest.py's `db` fixture), so tokens cached against a
        # previous test's client are worthless here even if `id(client)` happens to collide with a garbage-
        # collected earlier client (Python reuses ids). One Flow is built per test, so this is the right place to
        # drop anything left over.
        _TOKENS.clear()

    # ---- scorecards
    def scorecard(self, code=None, target=8, publish=True, **version_kw) -> dict:
        self.n += 1
        d = definition(code=code or f"flow-card-{self.n}", target=target, **version_kw)
        requires_review = version_kw.pop("requires_review", None)
        if requires_review is not None:
            d["requires_review"] = requires_review
            d["version"].pop("requires_review", None)
        r = self.c.post(f"/api/scorecards?publish={str(publish).lower()}", json=d, headers=H("Designer"))
        assert r.status_code == 201, r.text
        card = r.json()
        vid = card["versions"][0]["id"]
        return self.c.get(f"/api/versions/{vid}", headers=H("Designer")).json()

    # ---- subjects
    def subject(self, name, owner="Alice", parent=None, type_="task", **kw) -> dict:
        body = {"name": name, "subject_type": type_, "owner": owner, "parent_id": parent, **kw}
        r = self.c.post("/api/subjects", json=body, headers=H("Lead"))
        assert r.status_code == 201, r.text
        return r.json()

    # ---- submissions
    def start(self, subject_id, version_id, actor="Alice", **kw):
        return self.c.post(f"/api/subjects/{subject_id}/submissions", json={"version_id": version_id, **kw},
                           headers=H(actor))

    def act(self, sub_id, action, actor="Alice", **body):
        return self.c.post(f"/api/submissions/{sub_id}/{action}", json=body or None, headers=H(actor))

    def evaluation(self, sub_id, evaluator_type="human", name=None, actor="Judge"):
        body = {"evaluator_type": evaluator_type}
        if name:
            body["evaluator_name"] = name
        return self.c.post(f"/api/submissions/{sub_id}/evaluations", json=body, headers=H(actor))

    def rate(self, ev: dict, score: int, complete=True, actor=None):
        actor = actor or ev.get("evaluator_name") or ""
        hdr = H(actor)
        ids = []

        def walk(ns):
            for n in ns:
                ids.append(n["id"]) if n["is_leaf"] else walk(n["children"])

        walk(ev["version"]["parameters"])
        r = self.c.put(f"/api/evaluations/{ev['id']}",
                       json={"ratings": [{"parameter_id": i, "judged_score": score} for i in ids]}, headers=hdr)
        if r.status_code != 200:
            return r
        if complete:
            return self.c.post(f"/api/evaluations/{ev['id']}/complete", headers=hdr)
        return r

    def judge(self, sub_id, score, name="Bob", evaluator_type="human"):
        r = self.evaluation(sub_id, evaluator_type, name, actor=name)
        assert r.status_code == 201, r.text
        r2 = self.rate(r.json(), score)
        assert r2.status_code == 200, r2.text
        return r2.json()

    def self_appraise(self, sub_id, score, owner="Alice"):
        r = self.evaluation(sub_id, "self", actor=owner)
        assert r.status_code == 201, r.text
        return self.rate(r.json(), score)

    def to_state(self, state, version_id, subject_name=None, **subject_kw) -> dict:
        """A fresh submission driven into `state` (for the transition matrix)."""
        s = self.subject(subject_name or f"{state} subject {self.n}", **subject_kw)
        self.n += 1
        sub = self.start(s["id"], version_id).json()
        sid = sub["id"]
        if state == "open":
            return sub
        if state == "withdrawn":
            return self.act(sid, "withdraw").json()
        if state == "cancelled":
            return self.act(sid, "cancel", "Lead", reason="no longer needed").json()
        self.act(sid, "submit")
        if state == "in_review":
            return self.c.get(f"/api/submissions/{sid}", headers=H("Alice")).json()
        if state == "decided":
            self.judge(sid, 9)
            return self.act(sid, "decide", "Lead").json()
        if state == "adjudication":
            self.judge(sid, 10, "Bob")
            self.judge(sid, 2, "Carol")
            return self.act(sid, "decide", "Lead").json()
        raise ValueError(state)


__all__ = ["Flow", "H", "leaf", "definition"]
