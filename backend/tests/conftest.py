import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["SCORECARD_DB_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import services as svc  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        svc.seed_reference_data(s)
        yield s


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
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
