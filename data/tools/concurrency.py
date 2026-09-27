"""Concurrent writers: N threads each run full evaluations (create, rate all, complete) against a live server.

    python data/tools/concurrency.py --url http://127.0.0.1:8000 --threads 16 --each 10
"""

from __future__ import annotations

import argparse
import threading
import time

import httpx


def leaves(nodes):
    for n in nodes:
        if n["is_leaf"]:
            yield n
        else:
            yield from leaves(n["children"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--each", type=int, default=10)
    a = ap.parse_args(argv)
    c = httpx.Client(base_url=a.url, timeout=60)
    card = next(x for x in c.get("/api/scorecards").json() if x["code"] == "assessment-quality")
    vid = next(v["id"] for v in card["versions"] if v["status"] == "published")
    errors: list[str] = []
    done = [0]
    lock = threading.Lock()

    def worker(t):
        cl = httpx.Client(base_url=a.url, timeout=60)
        for i in range(a.each):
            try:
                ev = cl.post("/api/evaluations", json={"version_id": vid, "subject_name": f"c{t}-{i}"})
                ev.raise_for_status()
                ev = ev.json()
                ids = [n["id"] for n in leaves(ev["version"]["parameters"])]
                cl.put(f"/api/evaluations/{ev['id']}",
                       json={"ratings": [{"parameter_id": x, "judged_score": 8} for x in ids]}).raise_for_status()
                cl.post(f"/api/evaluations/{ev['id']}/complete").raise_for_status()
                with lock:
                    done[0] += 1
            except Exception as e:  # noqa: BLE001 - count every failure
                with lock:
                    errors.append(f"{type(e).__name__}: {str(e)[:120]}")

    t0 = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(t,)) for t in range(a.threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    secs = time.perf_counter() - t0
    print(f"{done[0]} evaluations completed, {len(errors)} errors, {secs:.1f}s "
          f"({done[0] / secs:.1f}/s with {a.threads} concurrent writers)")
    for e in sorted(set(errors))[:5]:
        print("  ", e)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
