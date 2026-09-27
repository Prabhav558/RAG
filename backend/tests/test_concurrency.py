"""Tuning: concurrent workflow actions must serialise (row locks). Meaningful on Postgres; SQLite serialises writes
anyway, so the test also passes there."""

import threading

from fastapi.testclient import TestClient

from app.main import app

from .flowkit import H, Flow


def test_concurrent_decide_happens_exactly_once(client):
    f = Flow(client)
    v = f.scorecard()
    s = f.subject("Race")
    sub = f.start(s["id"], v["id"]).json()
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 9)
    results, barrier = [], threading.Barrier(8)

    def decide():
        with TestClient(app) as c:
            barrier.wait()
            r = c.post(f"/api/submissions/{sub['id']}/decide", headers=H("Lead"))
            results.append((r.status_code, r.json().get("code")))

    threads = [threading.Thread(target=decide) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(code for code, _ in results).count(200) == 1, results
    # losers see S001 (state already moved on) or S012 (optimistic-concurrency conflict)
    assert all(code in ("S001", "S012") for status, code in results if status != 200), results
    audit = client.get(f"/api/audit?entity=submission&entity_id={sub['id']}").json()
    assert [e["action"] for e in audit].count("decide") == 1
