"""Cycle 3 · §9.5 — business-readable acceptance suite.

Scenarios live in /acceptance/*.feature (plain Given/When/Then that stakeholders sign off). This file is a
deliberately small runner: it parses the features and binds each step to the real API through regex step
definitions. `acceptance/ACCEPTANCE_RESULTS.md` is regenerated on every run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app import migration as mig

from .conftest import ROOT
from .flowkit import H, Flow, definition, leaf

FEATURES = ROOT / "acceptance"
RESULTS: list[dict] = []


# ---------------------------------------------------------------- parser


@dataclass
class Scenario:
    feature: str
    name: str
    steps: list[str]
    file: str


def parse(path: Path) -> list[Scenario]:
    feature, background, out, current = "", [], [], None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("Feature:"):
            feature = line.split(":", 1)[1].strip()
        elif line.startswith("Background:"):
            current = background
        elif line.startswith("Scenario:"):
            current = []
            out.append(Scenario(feature, line.split(":", 1)[1].strip(), current, path.name))
        elif re.match(r"^(Given|When|Then|And|But)\b", line) and current is not None:
            current.append(line)
    for s in out:
        s.steps[:0] = background
    return out


SCENARIOS = [s for f in sorted(FEATURES.glob("*.feature")) for s in parse(f)]


# ---------------------------------------------------------------- step registry

STEPS: list[tuple[re.Pattern, callable]] = []


def step(pattern: str):
    def deco(fn):
        STEPS.append((re.compile(f"^{pattern}$"), fn))
        return fn
    return deco


@dataclass
class World:
    f: Flow
    last: object = None  # last HTTP response
    version: dict | None = None
    cards: dict = field(default_factory=dict)  # name -> version view
    draft: dict | None = None  # definition being designed
    draft_card: dict | None = None
    evaluation: dict | None = None
    subjects: dict = field(default_factory=dict)  # name -> subject
    submission: dict | None = None
    migration: dict | None = None

    @property
    def c(self):
        return self.f.c

    def refresh_eval(self):
        self.evaluation = self.c.get(f"/api/evaluations/{self.evaluation['id']}").json()
        return self.evaluation

    def leaf(self, name):
        def walk(ns):
            for n in ns:
                if n["name"] == name:
                    return n
                hit = walk(n["children"])
                if hit:
                    return hit
        return walk(self.refresh_eval()["version"]["parameters"])

    def leaves(self):
        out = []

        def walk(ns):
            for n in ns:
                out.append(n) if n["is_leaf"] else walk(n["children"])

        walk(self.evaluation["version"]["parameters"])
        return out

    def expect_ok(self, r):
        assert r.status_code < 300, r.text
        return r.json()


def run(world: World, text: str):
    body = re.sub(r"^(Given|When|Then|And|But)\s+", "", text)
    for pattern, fn in STEPS:
        m = pattern.match(body)
        if m:
            return fn(world, *m.groups())
    raise AssertionError(f"No step definition for: {text}")


# ---------------------------------------------------------------- designing scorecards


@step(r'a draft scorecard "(.+)" with one fully defined KPI "(.+)"')
def _(w, name, kpi):
    w.draft = definition(code=re.sub(r"\W+", "-", name.lower()), params=[{**leaf("K1"), "name": kpi}])
    w.draft["name"] = name


@step(r"its purpose is empty")
def _(w):
    w.draft["version"]["purpose"] = ""


@step(r'the rating matrix of "(.+)" has no guideline for scores (\d+) to (\d+)')
def _(w, kpi, a, b):
    p = next(p for p in w.draft["version"]["parameters"] if p["name"] == kpi)
    p["criteria"] = [c for c in p["criteria"] if not int(a) <= c["score_min"] <= int(b)]


@step(r"the scorecard requires review")
def _(w):
    w.draft["requires_review"] = True


def _create_draft(w):
    if w.draft_card is None:
        w.draft_card = w.expect_ok(w.c.post("/api/scorecards", json=w.draft))
    return w.draft_card["versions"][0]["id"]


@step(r"the designer publishes it")
def _(w):
    w.last = w.c.post(f"/api/versions/{_create_draft(w)}/publish", headers=H("Designer"))


@step(r'"(.+)" submits it for review')
def _(w, who):
    w.last = w.c.post(f"/api/versions/{_create_draft(w)}/submit-for-review", json={}, headers=H(who))


@step(r'"(.+)" approves it')
def _(w, who):
    w.last = w.c.post(f"/api/versions/{_create_draft(w)}/approve", json={}, headers=H(who))


@step(r'the scorecard version is "(.+)"')
def _(w, status):
    assert w.c.get(f"/api/versions/{_create_draft(w)}").json()["status"] == status


@step(r'the reference scorecard "(.+)"')
def _(w, name):
    for f in (ROOT / "data" / "scorecards").glob("*.json"):
        d = json.loads(f.read_text())
        if d["name"] == name:
            card = w.expect_ok(w.c.post("/api/scorecards?publish=true", json=d))
            w.version = w.c.get(f"/api/versions/{card['versions'][0]['id']}").json()
            w.cards[name] = w.version
            return
    raise AssertionError(f"no reference scorecard {name}")


@step(r"it has (\d+) levels of parameters")
def _(w, n):
    assert w.c.get(f"/api/scorecards/{w.version['scorecard_id']}").json()["depth"] == int(n)


@step(r"its rated parameters carry 100% of the weight")
def _(w):
    total = []

    def walk(ns):
        for n in ns:
            total.append(n["effective_weight"]) if n["is_leaf"] else walk(n["children"])

    walk(w.version["parameters"])
    assert abs(sum(total) - 1) < 1e-9


@step(r"the designer edits the published version")
def _(w):
    content = w.c.get(f"/api/versions/{w.version['id']}/definition").json()["version"]
    w.last = w.c.put(f"/api/versions/{w.version['id']}", json=content)


@step(r"the designer creates a new version")
def _(w):
    w.last = w.c.post(f"/api/versions/{w.version['id']}/new-draft")


@step(r"version (\d+) is a draft")
def _(w, n):
    body = w.expect_ok(w.last)
    assert body["version_no"] == int(n) and body["status"] == "draft"


@step(r'it is rejected with "(.+)"')
def _(w, code):
    body = w.last.json()
    codes = {body.get("code")} | {d.get("code") for d in body.get("details") or [] if isinstance(d, dict)}
    assert w.last.status_code >= 400 and code in codes, (w.last.status_code, body)


# ---------------------------------------------------------------- scoring


@step(r'a scorecard with KPIs "(.+)" weighted (\d+) and "(.+)" weighted (\d+) and target (\d+)')
def _(w, a, wa, b, wb, target):
    d = definition(code="rounding", target=int(target),
                   params=[{**leaf("A", int(wa)), "name": a}, {**leaf("B", int(wb)), "name": b}])
    card = w.expect_ok(w.c.post("/api/scorecards?publish=true", json=d))
    w.version = w.c.get(f"/api/versions/{card['versions'][0]['id']}").json()


def _ensure_eval(w):
    if w.evaluation is None:
        w.evaluation = w.expect_ok(w.c.post("/api/evaluations", json={"version_id": w.version["id"],
                                                                      "subject_name": "Acceptance subject"}))


@step(r"a judge rates every parameter (\d+)")
def _(w, score):
    _ensure_eval(w)
    ratings = [{"parameter_id": n["id"], "judged_score": int(score)} for n in w.leaves()]
    w.evaluation = w.expect_ok(w.c.put(f"/api/evaluations/{w.evaluation['id']}", json={"ratings": ratings}))


@step(r'a judge rates "(.+)" (\d+) and "(.+)" (\d+)')
def _(w, a, sa, b, sb):
    _ensure_eval(w)
    ids = {n["name"]: n["id"] for n in w.leaves()}
    body = {"ratings": [{"parameter_id": ids[a], "judged_score": int(sa)},
                        {"parameter_id": ids[b], "judged_score": int(sb)}]}
    w.evaluation = w.expect_ok(w.c.put(f"/api/evaluations/{w.evaluation['id']}", json=body))


@step(r'records (\d+) for the metric "(.+)"')
def _(w, value, metric):
    mid = next(m["id"] for n in w.leaves() for m in n["metrics"] if m["name"] == metric)
    w.evaluation = w.expect_ok(w.c.put(f"/api/evaluations/{w.evaluation['id']}",
                                       json={"metric_values": [{"metric_id": mid, "value": float(value)}]}))


@step(r'marks "(.+)" as not applicable')
def _(w, name):
    n = w.leaf(name)
    w.evaluation = w.expect_ok(w.c.put(f"/api/evaluations/{w.evaluation['id']}",
                                       json={"ratings": [{"parameter_id": n["id"], "not_applicable": True}]}))


@step(r"records that time was met but cost was not")
def _(w):
    w.evaluation = w.expect_ok(w.c.put(f"/api/evaluations/{w.evaluation['id']}",
                                       json={"time_met": True, "cost_met": False}))


@step(r'the judge overrides "(.+)" with (\d+) because "(.+)"')
def _(w, name, score, reason):
    n = w.leaf(name)
    body = {"ratings": [{"parameter_id": n["id"], "judged_score": int(score), "override_reason": reason}]}
    w.evaluation = w.expect_ok(w.c.put(f"/api/evaluations/{w.evaluation['id']}", json=body))


@step(r'"(.+)" scores (\d+) (from metrics|as an override)')
def _(w, name, score, how):
    r = w.leaf(name)["result"]
    assert r["final_score"] == int(score), r
    assert r["score_source"] == ("metric" if how == "from metrics" else "override")


@step(r"the final score is ([\d.]+)")
def _(w, score):
    assert w.refresh_eval()["final_score"] == float(score)


@step(r'the band is "(.+)"')
def _(w, band):
    assert w.evaluation["band_label"] == band


@step(r"the evaluation is below target")
def _(w):
    assert w.refresh_eval()["quality_met"] is False


@step(r"the evaluation meets target")
def _(w):
    assert w.refresh_eval()["quality_met"] is True


@step(r"QTC is not green")
def _(w):
    assert w.refresh_eval()["qtc_green"] is False


@step(r'the gate "(.+)" fails')
def _(w, name):
    assert name in [g["name"] for g in w.refresh_eval()["gate_failures"]]


# ---------------------------------------------------------------- quality gate


@step(r'a published( foundational)? scorecard "(.+)"(?: requiring (\d+) judges within (\d+)% and a self-appraisal)?')
def _(w, foundational, name, judges, tol):
    kw = {"is_foundational": bool(foundational)}
    if judges:
        kw.update(required_judges=int(judges), judge_tolerance_pct=float(tol), require_self_appraisal=True)
    w.cards[name] = w.f.scorecard(code=re.sub(r"\W+", "-", name.lower()), **kw)
    w.version = w.cards[name]


@step(r'a project "(.+)" owned by "(.+)" with a task "(.+)" owned by "(.+)"')
def _(w, project, powner, task, towner):
    w.subjects[project] = w.f.subject(project, owner=powner, type_="project")
    w.subjects[task] = w.f.subject(task, owner=towner, parent=w.subjects[project]["id"])


@step(r'the project "(.+)" also has a task "(.+)" owned by "(.+)"')
def _(w, project, task, owner):
    w.subjects[task] = w.f.subject(task, owner=owner, parent=w.subjects[project]["id"])


def _start(w, who, subject, version):
    w.last = w.f.start(w.subjects[subject]["id"], version["id"], actor=who)
    if w.last.status_code == 201:
        w.submission = w.last.json()


@step(r'"(.+)" starts a submission for "(.+)"')
def _(w, who, subject):
    _start(w, who, subject, w.version)


@step(r'"(.+)" submits it')
def _(w, who):
    w.last = w.f.act(w.submission["id"], "submit", who)


@step(r'"(.+)" self-appraises it at (\d+)')
def _(w, who, score):
    w.f.self_appraise(w.submission["id"], int(score), owner=who)


@step(r'"(.+)" has submitted "(.+)"')
def _(w, who, subject):
    _start(w, who, subject, w.version)
    w.f.self_appraise(w.submission["id"], 8, owner=who)
    w.expect_ok(w.f.act(w.submission["id"], "submit", who))


@step(r'"(.+)" judges it at (\d+)')
def _(w, who, score):
    r = w.f.evaluation(w.submission["id"], "human", who, actor=who)
    w.last = r
    if r.status_code == 201:
        w.f.rate(r.json(), int(score))


@step(r'"(.+)" decides')
def _(w, who):
    w.last = w.f.act(w.submission["id"], "decide", who)
    if w.last.status_code == 200:
        w.submission = w.last.json()


@step(r'"(.+)" adjudicates it as "(.+)" because "(.+)"')
def _(w, who, verdict, reason):
    w.last = w.f.act(w.submission["id"], "adjudicate", who, verdict=verdict, reason=reason)
    if w.last.status_code == 200:
        w.submission = w.last.json()


@step(r'the submission is "(.+)"')
def _(w, status):
    assert w.c.get(f"/api/submissions/{w.submission['id']}").json()["status"] == status


@step(r'the decision is "(.+)"(?: with an official score of ([\d.]+))?')
def _(w, decision, score):
    s = w.c.get(f"/api/submissions/{w.submission['id']}").json()
    assert s["decision"] == decision, s
    if score:
        assert s["official_score"] == float(score)


@step(r"it is attempt (\d+)")
def _(w, n):
    assert w.submission["attempt_no"] == int(n)


def _find(tree, name):
    for n in tree:
        if n["name"] == name:
            return n
        hit = _find(n["children"], name)
        if hit:
            return hit


@step(r'"(.+)" is "(.+)"')
def _(w, name, status):
    node = _find(w.c.get("/api/subjects").json(), name)
    assert node["status"] == status, node


# ---------------------------------------------------------------- stop rule & diagnosis


@step(r'"(.+)" submits "(.+)" against "(.+)" and it is judged (\d+)')
def _(w, who, subject, card, score):
    _start(w, who, subject, w.cards[card])
    w.expect_ok(w.f.act(w.submission["id"], "submit", who))
    w.f.judge(w.submission["id"], int(score), "Judge Jo")
    w.expect_ok(w.f.act(w.submission["id"], "decide", "Lead"))


@step(r'"(.+)" starts "(.+)" against "(.+)"')
def _(w, who, subject, card):
    _start(w, who, subject, w.cards[card])


@step(r'"(.+)" has had (\d+) pieces of work judged red against "(.+)"')
def _(w, who, n, card):
    for i in range(int(n)):
        s = w.f.subject(f"{who} task {i}", owner=who)
        sub = w.f.start(s["id"], w.cards[card]["id"], actor=who).json()
        w.f.act(sub["id"], "submit", who)
        w.f.judge(sub["id"], 3, "Judge Jo")
        w.f.act(sub["id"], "decide", "Lead")


def _attention(w, who):
    return next(p for p in w.c.get("/api/attention").json()["people"] if p["person"] == who)


@step(r'"(.+)" needs a diagnosis')
def _(w, who):
    assert _attention(w, who)["needs_diagnosis"]


@step(r'"(.+)" no longer needs a diagnosis')
def _(w, who):
    assert not _attention(w, who)["needs_diagnosis"]


@step(r'"(.+)" records a diagnosis of "(.+)" with action "(.+)" for "(.+)"')
def _(w, who, cause, action, person):
    w.last = w.c.post("/api/diagnoses", json={"person": person, "cause": cause, "action": action}, headers=H(who))


# ---------------------------------------------------------------- migration


@step(r'the legacy file "(.+)" is previewed')
def _(w, name):
    data = (ROOT / "data" / "legacy" / name).read_bytes()
    w.last = w.c.post("/api/migrations/preview", files=[("files", (name, data, "application/octet-stream"))])
    w.migration = w.expect_ok(w.last)


@step(r"(\d+) rating rows would be imported")
def _(w, n):
    c = w.migration["counts"]
    assert c.get("rating_imported", 0) + c.get("rating_warning", 0) == int(n), c


@step(r"(\d+) of (\d+) legacy totals are reproduced")
def _(w, a, b):
    rec = w.migration["reconciliation"]
    assert (rec["matched"], rec["rows_with_legacy_total"]) == (int(a), int(b))


@step(r'rating rows (\d+) and (\d+) are rejected with "(.+)"')
def _(w, a, b, code):
    for n in (int(a), int(b)):
        r = next(r for r in w.migration["rows"] if r["row"] == n and r["kind"] == "rating")
        assert r["status"] == "rejected" and any(f"[{code}]" in m for m in r["messages"]), r


@step(r"no difference from the legacy totals is unexplained")
def _(w):
    assert w.migration["reconciliation"]["mismatched_unexplained"] == 0


@step(r'the migration fails with "(.+)"')
def _(w, code):
    assert w.migration["status"] == "failed" and w.migration["fatal"][0].startswith(f"[{code}]")


# ---------------------------------------------------------------- run


@pytest.fixture(scope="module", autouse=True)
def report():
    yield
    out = ROOT / "acceptance" / "ACCEPTANCE_RESULTS.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Acceptance results", "", "Generated by `pytest tests/test_acceptance.py` from `/acceptance/*.feature`. "
             "Sign-off: a stakeholder reviews each scenario's wording; the suite proves the system does exactly that.",
             "", "| Feature | Scenario | Steps | Result | Signed off by |", "|---|---|---|---|---|"]
    for r in RESULTS:
        lines.append(f"| {r['feature']} | {r['scenario']} | {r['steps']} | {'✅ pass' if r['ok'] else '❌ ' + r['error']} | |")
    passed = sum(r["ok"] for r in RESULTS)
    lines += ["", f"**{passed} / {len(RESULTS)} scenarios pass.**"]
    out.write_text("\n".join(lines) + "\n")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[f"{s.file}::{s.name}" for s in SCENARIOS])
def test_acceptance(client, scenario):
    world = World(Flow(client))
    try:
        for text in scenario.steps:
            run(world, text)
    except Exception as e:
        RESULTS.append({"feature": scenario.feature, "scenario": scenario.name, "steps": len(scenario.steps),
                        "ok": False, "error": f"{type(e).__name__}: {str(e)[:80]}".replace("|", "/")})
        raise
    RESULTS.append({"feature": scenario.feature, "scenario": scenario.name, "steps": len(scenario.steps), "ok": True})


def test_every_step_is_bound():
    unbound = []
    for s in SCENARIOS:
        for text in s.steps:
            body = re.sub(r"^(Given|When|Then|And|But)\s+", "", text)
            if not any(p.match(body) for p, _ in STEPS):
                unbound.append(text)
    assert not unbound, unbound
    assert len(SCENARIOS) >= 18


assert mig  # the migration module is exercised through the API
