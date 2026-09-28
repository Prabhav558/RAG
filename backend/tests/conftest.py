import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
# SCORECARD_TEST_DB_URL runs the whole suite on another database, e.g. postgresql+psycopg://...
os.environ["SCORECARD_DB_URL"] = os.environ.get("SCORECARD_TEST_DB_URL", f"sqlite:///{_tmp}/test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import services as svc  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

BOOTSTRAP_PASSWORD = "Test-Password-123!"


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        svc.seed_reference_data(s)
        yield s


@pytest.fixture()
def client(db):
    """Phase 2 made every API endpoint require login (docs/14_PHASE2_SECURITY_SPEC.md). Most existing tests
    predate identity and don't care who is acting, so this fixture registers as the very first user of the fresh
    database — `auth.register` always makes that user an admin — and sets it as the client's default identity.
    Cycle 3 workflow/acceptance tests that DO care about a specific actor override this per call with an explicit
    `headers=` (see tests/flowkit.py's `H()`) — per-call headers replace the client's default `Authorization`
    header, they don't merge with it."""
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"username": "test-bootstrap", "password": BOOTSTRAP_PASSWORD,
                                                "display_name": "Test Bootstrap"})
        assert r.status_code == 201, r.text
        assert "admin" in r.json()["user"]["roles"], "the first user registered on a fresh database must be admin"
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c


def matrix(lo=0, hi=10):
    """A complete one-row-per-score rating matrix."""
    return [{"score_min": s, "score_max": s, "qualitative": f"Level {s}", "quantitative": f"q{s}"} for s in range(lo, hi + 1)]


def leaf(code, weight=1.0, lo=0, hi=10, **kw):
    return {"code": code, "name": f"Param {code}", "weight": weight, "criteria": matrix(lo, hi), **kw}


def definition(code="test-card", params=None, scale="0-10-rag", target=8, lo=0, hi=10, **version_kw):
    return {
        "code": code,
        "name": f"Card {code}",
        "subject_type": "task",
        "version": {
            "purpose": "Test purpose",
            "scope": "Test scope",
            "objective": "Test objective",
            "rating_scale": scale,
            "target_score": target,
            "parameters": params if params is not None else [leaf("A", 60, lo, hi), leaf("B", 40, lo, hi)],
            **version_kw,
        },
    }
