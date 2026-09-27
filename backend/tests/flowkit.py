"""Helpers to drive the Cycle 3 workflows through the API (shared by workflow and acceptance tests)."""

from __future__ import annotations

from .conftest import definition, leaf


def H(actor: str) -> dict:
    return {"X-Actor": actor}


class Flow:
    def __init__(self, client):
        self.c = client
        self.n = 0

    # ---- scorecards
    def scorecard(self, code=None, target=8, publish=True, **version_kw) -> dict:
        self.n += 1
        d = definition(code=code or f"flow-card-{self.n}", target=target, **version_kw)
        requires_review = version_kw.pop("requires_review", None)
        if requires_review is not None:
            d["requires_review"] = requires_review
            d["version"].pop("requires_review", None)
        r = self.c.post(f"/api/scorecards?publish={str(publish).lower()}", json=d)
        assert r.status_code == 201, r.text
        card = r.json()
        vid = card["versions"][0]["id"]
        return self.c.get(f"/api/versions/{vid}").json()

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
            return self.c.get(f"/api/submissions/{sid}").json()
        if state == "decided":
            self.judge(sid, 9)
            return self.act(sid, "decide", "Lead").json()
        if state == "adjudication":
            self.judge(sid, 10, "Bob")
            self.judge(sid, 2, "Carol")
            return self.act(sid, "decide", "Lead").json()
        raise ValueError(state)


__all__ = ["Flow", "H", "leaf", "definition"]
