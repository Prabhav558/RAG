"""Tuning (framework §10): measure the real application against the non-functional targets.

Loads volume through the normal services, then times the endpoints people actually hit, over real HTTP.

    python data/tools/perf.py --multiplier 20                 # SQLite
    SCORECARD_DB_URL=postgresql+psycopg://... python data/tools/perf.py --multiplier 20
Targets: p95 < 300 ms for rating updates and page loads at pilot volume;
throughput far above 2,400 evaluations/day (~0.03/s average).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
TARGET_MS = 300


def pct(values, p):
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round(p / 100 * (len(values) - 1)))))
    return values[k]


def timed(client: httpx.Client, method: str, url: str, n: int, **kw) -> dict:
    samples = []
    for _ in range(n):
        t = time.perf_counter()
        r = client.request(method, url, **kw)
        samples.append((time.perf_counter() - t) * 1000)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {url} -> {r.status_code} {r.text[:200]}")
    return {"n": n, "p50": round(statistics.median(samples), 1), "p95": round(pct(samples, 95), 1),
            "max": round(max(samples), 1)}


def leaves(nodes):
    for n in nodes:
        if n["is_leaf"]:
            yield n
        else:
            yield from leaves(n["children"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--multiplier", type=int, default=20)
    ap.add_argument("--skip-load", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "tuning" / "perf_results.json")
    args = ap.parse_args(argv)
    env = dict(os.environ)
    env.setdefault("SCORECARD_DB_URL", f"sqlite:///{ROOT}/backend/perf.db")
    py = sys.executable

    if not args.skip_load:
        t = time.perf_counter()
        subprocess.run([py, str(ROOT / "data/tools/ingest.py"), "--reset"], env=env, check=True, capture_output=True)
        subprocess.run([py, str(ROOT / "data/tools/generate.py"), "--multiplier", str(args.multiplier)], env=env,
                       check=True, capture_output=True)
        subprocess.run([py, str(ROOT / "data/tools/generate_flow.py")], env=env, check=True, capture_output=True)
        load_s = time.perf_counter() - t
    else:
        load_s = None

    server = subprocess.Popen([py, "-m", "uvicorn", "app.main:app", "--port", str(args.port), "--log-level", "warning"],
                              cwd=ROOT / "backend", env=env)
    base = f"http://127.0.0.1:{args.port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base}/api/health").status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.1)
        c = httpx.Client(base_url=base, timeout=60)
        # Every endpoint now requires login (Phase 2). The database was populated via the service layer (no HTTP
        # users exist yet), so this registration becomes the first user and is auto-admin.
        r = c.post("/api/auth/register", json={"username": "perf-bootstrap", "password": "Perf-Bootstrap-1!",
                                                "display_name": "Perf Harness"})
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        cards = c.get("/api/scorecards").json()
        aq = next(x for x in cards if x["code"] == "assessment-quality")
        vid = next(v["id"] for v in aq["versions"] if v["status"] == "published")
        o = c.get("/api/analytics/overview").json()
        n_evals = o["total_completed"] + o["drafts"] + o["voided"]
        ev = c.post("/api/evaluations", json={"version_id": vid, "subject_name": "perf"}).json()
        leaf_ids = [n["id"] for n in leaves(ev["version"]["parameters"])]
        rating = {"ratings": [{"parameter_id": leaf_ids[0], "judged_score": 8}]}
        some_eval = c.get(f"/api/evaluations?scorecard_id={aq['id']}&status=completed&limit=1").json()[0]["id"]
        sub_id = c.get("/api/submissions").json()[0]["id"]
        subject_id = c.get("/api/subjects").json()[0]["id"]

        results = {
            "library: GET /api/scorecards": timed(c, "GET", "/api/scorecards", 30),
            "builder: GET version": timed(c, "GET", f"/api/versions/{vid}", 30),
            "evaluations list (200)": timed(c, "GET", "/api/evaluations", 30),
            "evaluation page: GET evaluation": timed(c, "GET", f"/api/evaluations/{some_eval}", 30),
            "rate one parameter: PUT evaluation": timed(c, "PUT", f"/api/evaluations/{ev['id']}", 50, json=rating),
            "create evaluation: POST": timed(c, "POST", "/api/evaluations", 30,
                                             json={"version_id": vid, "subject_name": "perf create"}),
            "analytics overview": timed(c, "GET", "/api/analytics/overview", 15),
            "analytics parameters": timed(c, "GET", f"/api/analytics/parameters/{vid}", 15),
            "analytics judge agreement": timed(c, "GET", "/api/analytics/judge-agreement", 15),
            "analytics behaviour": timed(c, "GET", "/api/analytics/behaviour", 15),
            "work tree: GET /api/subjects": timed(c, "GET", "/api/subjects", 30),
            "subject page": timed(c, "GET", f"/api/subjects/{subject_id}", 30),
            "submission page": timed(c, "GET", f"/api/submissions/{sub_id}", 30),
        }
        # full evaluation lifecycle throughput
        t = time.perf_counter()
        runs = 20
        for i in range(runs):
            e = c.post("/api/evaluations", json={"version_id": vid, "subject_name": f"tp {i}"}).json()
            c.put(f"/api/evaluations/{e['id']}", json={"ratings": [{"parameter_id": x, "judged_score": 8} for x in leaf_ids]})
            r = c.post(f"/api/evaluations/{e['id']}/complete")
            assert r.status_code == 200, r.text
        per_eval = (time.perf_counter() - t) / runs
    finally:
        server.terminate()
        server.wait(10)

    db = env["SCORECARD_DB_URL"].split("://")[0]
    report = {"database": db, "multiplier": args.multiplier, "evaluations_in_db": n_evals, "load_seconds": load_s,
              "endpoints_ms": results, "full_evaluation_seconds": round(per_eval, 3),
              "evaluations_per_day_capacity_single_worker": int(86400 / per_eval),
              "over_target": [k for k, v in results.items() if v["p95"] > TARGET_MS]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(args.out.read_text()) if args.out.exists() else {}
    existing[f"{db}"] = report
    args.out.write_text(json.dumps(existing, indent=2))
    print(f"{db}: {n_evals} evaluations in DB (+ private self-appraisals)")
    for k, v in results.items():
        flag = "  <-- over target" if v["p95"] > TARGET_MS else ""
        print(f"  {k:<40} p50 {v['p50']:>7} ms  p95 {v['p95']:>7} ms{flag}")
    print(f"  full evaluation (create + rate all + complete): {per_eval * 1000:.0f} ms "
          f"=> ~{report['evaluations_per_day_capacity_single_worker']:,}/day on one worker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
