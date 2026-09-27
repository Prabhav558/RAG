"""Cycle 2 · §8.2 — every injected defect is rejected with its documented code; nothing crashes."""

import sys

import pytest
from fastapi.testclient import TestClient

from app.main import app

from .conftest import ROOT

sys.path.insert(0, str(ROOT / "data" / "tools"))
import corrupt  # noqa: E402

ROWS: list[dict] = []


@pytest.fixture(scope="module")
def results():
    return ROWS


def test_corruption_catalogue(db):
    with TestClient(app, raise_server_exceptions=False) as client:
        rows = corrupt.run_all(client)
    failures = [r for r in rows if r["outcome"] != "PASS"]
    assert not failures, "\n".join(
        f"{r['id']} {r['outcome']}: {r['description']} expected {r['expected']} got {r['got']}" for r in failures
    )
    assert not [r for r in rows if r["outcome"] == "CRASH"]
    assert len(rows) >= 70
