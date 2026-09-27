"""Cycle 3 behaviour (docs/10_CYCLE3_BEHAVIOUR_SPEC.md): state machines, guards, roll-up, diagnosis."""

from datetime import datetime, timedelta, timezone

import pytest

from app import workflow as wf

from .flowkit import H, Flow

SUB_ACTIONS = {  # action -> (endpoint, actor, body)
    "submit": ("submit", "Alice", {}),
    "withdraw": ("withdraw", "Alice", {}),
    "cancel": ("cancel", "Lead", {"reason": "stop this"}),
    "decide": ("decide", "Lead", {}),
    "adjudicate": ("adjudicate", "Dana", {"verdict": "passed", "reason": "judges agreed after discussion"}),
}
VERSION_ACTIONS = {
    "submit_for_review": ("submit-for-review", "Designer", {"comment": "please review"}),
    "publish": ("publish", "Designer", None),
    "approve": ("approve", "Reviewer", {"comment": "ok"}),
    "request_changes": ("request-changes", "Reviewer", {"comment": "fix wording"}),
    "retire": ("retire", "Designer", {"reason": "obsolete"}),
}


@pytest.fixture()
def f(client):
    return Flow(client)


# ---------------------------------------------------------------- transition tables


def test_tables_are_closed_over_declared_states():
    for machine, table in wf.TRANSITIONS.items():
        for (state, _), target in table.items():
            assert state in wf.STATES[machine] and target in wf.STATES[machine]
        for t in wf.TERMINAL[machine]:
            assert wf.actions(machine, t) == [], f"terminal {t} must have no actions"


@pytest.mark.parametrize("state", wf.STATES[wf.SUBMISSION])
def test_submission_state_action_matrix(f, state):
    """Every submission state x every action, through the real API: illegal ones are S001, legal ones are not."""
    v = f.scorecard()
    for action, (endpoint, who, body) in SUB_ACTIONS.items():
        sub = f.to_state(state, v["id"])
        assert sub["status"] == state, sub
        r = f.act(sub["id"], endpoint, who, **body)
        allowed = (state, action) in wf.TRANSITIONS[wf.SUBMISSION]
        code = r.json().get("code") if r.status_code >= 400 else None
        if allowed:
            assert code != "S001", (state, action, r.json())
        else:
            assert r.status_code == 409 and code == "S001", (state, action, r.status_code, r.json())


def _version_in(f, state):
    requires_review = state in ("in_review",)
    v = f.scorecard(publish=False, requires_review=requires_review)
    c = f.c
    if state == "in_review":
        assert c.post(f"/api/versions/{v['id']}/submit-for-review", json={}, headers=H("Designer")).status_code == 200
    elif state in ("published", "retired"):
        assert c.post(f"/api/versions/{v['id']}/publish", headers=H("Designer")).status_code == 200
        if state == "retired":
            c.post(f"/api/versions/{v['id']}/retire", json={"reason": "obsolete"}, headers=H("Designer"))
    return c.get(f"/api/versions/{v['id']}").json()


@pytest.mark.parametrize("state", wf.STATES[wf.VERSION])
def test_version_state_action_matrix(f, state):
    for action, (endpoint, who, body) in VERSION_ACTIONS.items():
        v = _version_in(f, state)
        assert v["status"] == state
        r = f.c.post(f"/api/versions/{v['id']}/{endpoint}", json=body, headers=H(who))
        allowed = (state, action) in wf.TRANSITIONS[wf.VERSION]
        code = r.json().get("code") if r.status_code >= 400 else None
        if action == "publish" and state != "draft":
            assert code in ("E009", "S001"), (state, r.json())  # legacy code kept for direct publish
        elif allowed:
            assert code != "S001", (state, action, r.json())
        else:
            assert r.status_code == 409 and code == "S001", (state, action, r.json())


# ---------------------------------------------------------------- scorecard review


def test_review_workflow_and_separation_of_duties(f):
    v = f.scorecard(publish=False, requires_review=True)
    c = f.c
    r = c.post(f"/api/versions/{v['id']}/publish", headers=H("Designer"))
    assert r.json()["code"] == "S001"
    assert c.post(f"/api/versions/{v['id']}/submit-for-review", json={}, headers=H("Designer")).status_code == 200
    content = c.get(f"/api/versions/{v['id']}/definition").json()["version"]
    assert c.put(f"/api/versions/{v['id']}", json=content).json()["code"] == "E009"  # frozen while in review
    assert c.post(f"/api/versions/{v['id']}/new-draft").json()["code"] == "E014"
    assert c.post(f"/api/versions/{v['id']}/approve", json={}, headers=H("designer")).json()["code"] == "S003"
    r = c.post(f"/api/versions/{v['id']}/request-changes", json={}, headers=H("Reviewer"))
    assert r.status_code == 422
    assert c.post(f"/api/versions/{v['id']}/request-changes", json={"comment": "clarify 4-5"},
                  headers=H("Reviewer")).json()["status"] == "draft"
    c.post(f"/api/versions/{v['id']}/submit-for-review", json={}, headers=H("Designer"))
    assert c.post(f"/api/versions/{v['id']}/approve", json={"comment": "good"},
                  headers=H("Reviewer")).json()["status"] == "published"
    history = [h["action"] for h in c.get(f"/api/versions/{v['id']}/reviews").json()]
    assert history == ["submitted", "changes_requested", "submitted", "published", "approved"]


def test_approval_retires_previous_version(f):
    v1 = f.scorecard(requires_review=False)
    c = f.c
    c.patch(f"/api/scorecards/{v1['scorecard_id']}", json={"requires_review": True})
    v2 = c.post(f"/api/versions/{v1['id']}/new-draft").json()
    c.post(f"/api/versions/{v2['id']}/submit-for-review", json={}, headers=H("Designer"))
    c.post(f"/api/versions/{v2['id']}/approve", json={}, headers=H("Reviewer"))
    assert c.get(f"/api/versions/{v1['id']}").json()["status"] == "retired"


def test_actor_required(f):
    v = f.scorecard(publish=False)
    r = f.c.post(f"/api/versions/{v['id']}/submit-for-review", json={})
    assert r.status_code == 422 and r.json()["code"] == "S002"
    r = f.c.post("/api/subjects", json={"name": "x", "subject_type": "task", "owner": "A"}, headers=H("  "))
    assert r.json()["code"] == "S002"


# ---------------------------------------------------------------- submissions: the gate


def test_happy_path_single_judge(f):
    v = f.scorecard()
    project = f.subject("Project X", owner="Pat", type_="project")
    task = f.subject("Write spec", owner="Alice", parent=project["id"])
    sub = f.start(task["id"], v["id"], input_text="the spec").json()
    assert sub["status"] == "open" and sub["attempt_no"] == 1
    f.self_appraise(sub["id"], 9)
    assert f.act(sub["id"], "submit", "Bob").json()["code"] == "S003"  # only the owner submits
    assert f.act(sub["id"], "submit", "alice").json()["status"] == "in_review"  # case-insensitive identity
    assert f.evaluation(sub["id"], "human", "Alice", actor="Alice").json()["code"] == "S003"  # no self-judging
    assert f.act(sub["id"], "decide", "Lead").json()["code"] == "S004"
    f.judge(sub["id"], 9)
    d = f.act(sub["id"], "decide", "Lead").json()
    assert d["status"] == "decided" and d["decision"] == "passed" and d["official_score"] == 9
    tree = f.c.get("/api/subjects").json()
    assert tree[0]["status"] == "green" and tree[0]["children"][0]["own_status"] == "green"
    events = [e["action"] for e in d["events"]]
    assert events == ["start", "add_evaluation", "submit", "add_evaluation", "decide"]


def test_project_green_only_when_all_children_green(f):
    v = f.scorecard()
    p = f.subject("P", owner="Pat", type_="project")
    a = f.subject("A", parent=p["id"])
    f.subject("B", parent=p["id"])
    sub = f.start(a["id"], v["id"]).json()
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 9)
    f.act(sub["id"], "decide", "Lead")
    root = f.c.get("/api/subjects").json()[0]
    assert root["status"] == "not_started"  # B not started: project not green
    assert root["descendant_counts"] == {"green": 1, "not_started": 1}


def test_self_appraisal_required(f):
    v = f.scorecard(require_self_appraisal=True)
    s = f.subject("T")
    sub = f.start(s["id"], v["id"]).json()
    assert f.act(sub["id"], "submit").json()["code"] == "S005"
    f.self_appraise(sub["id"], 7)
    assert f.act(sub["id"], "submit").json()["status"] == "in_review"


def test_evaluation_windows(f):
    v = f.scorecard()
    s = f.subject("T")
    sub = f.start(s["id"], v["id"]).json()
    assert f.evaluation(sub["id"], "human", "Bob").json()["code"] == "S009"  # judges wait for submit
    self_ev = f.evaluation(sub["id"], "self", actor="Alice").json()
    assert f.evaluation(sub["id"], "self", actor="Alice").json()["code"] == "S009"  # one self-appraisal
    f.act(sub["id"], "submit")
    assert f.evaluation(sub["id"], "self", actor="Alice").json()["code"] == "S009"
    assert f.rate(self_ev, 8).json()["code"] == "S009"  # self-appraisal after submitting is too late
    j = f.evaluation(sub["id"], "human", "Bob").json()
    f.judge(sub["id"], 9, "Carol")
    f.act(sub["id"], "decide", "Lead")
    assert f.rate(j, 3).json()["code"] == "S009"  # no late judgements after the decision


def test_multi_judge_agreement_uses_mean(f):
    v = f.scorecard(required_judges=2)
    s = f.subject("T")
    sub = f.start(s["id"], v["id"]).json()
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 9, "Bob")
    assert f.act(sub["id"], "decide", "Lead").json()["code"] == "S004"
    f.judge(sub["id"], 8, "Carol")
    d = f.act(sub["id"], "decide", "Lead").json()
    assert d["decision"] == "passed" and d["official_score"] == 8.5 and d["judge_spread_pct"] == 10


def test_disagreement_goes_to_adjudication(f):
    v = f.scorecard(required_judges=2)
    s = f.subject("T")
    sub = f.to_state("adjudication", v["id"])
    assert sub["decision"] is None and sub["allowed_actions"] == ["adjudicate", "cancel"]
    for who in ("Alice", "Bob", "carol"):
        assert f.act(sub["id"], "adjudicate", who, verdict="passed", reason="x" * 5).json()["code"] == "S003"
    d = f.act(sub["id"], "adjudicate", "Dana", verdict="redo", reason="Clarity guideline 4-5 was misread").json()
    assert d["status"] == "decided" and d["decision"] == "redo" and d["adjudicated"]
    assert s  # subject fixture unused otherwise


def test_spread_beyond_tolerance_with_same_verdict_is_a_dispute(f):
    v = f.scorecard(required_judges=2, judge_tolerance_pct=10)
    s = f.subject("T")
    sub = f.start(s["id"], v["id"]).json()
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 10, "Bob")
    f.judge(sub["id"], 8, "Carol")  # both pass, but 20% apart
    assert f.act(sub["id"], "decide", "Lead").json()["status"] == "adjudication"


def test_redo_then_resubmit(f):
    v = f.scorecard()
    s = f.subject("T")
    sub = f.start(s["id"], v["id"]).json()
    assert f.start(s["id"], v["id"]).json()["code"] == "S001"  # one active submission per scorecard
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 5)
    assert f.act(sub["id"], "decide", "Lead").json()["decision"] == "redo"
    assert f.c.get("/api/subjects").json()[0]["status"] == "red"
    sub2 = f.start(s["id"], v["id"]).json()
    assert sub2["attempt_no"] == 2 and sub2["previous_id"] == sub["id"]
    assert f.c.get("/api/subjects").json()[0]["status"] == "red"  # still red until the redo passes
    f.act(sub2["id"], "submit")
    f.judge(sub2["id"], 9)
    f.act(sub2["id"], "decide", "Lead")
    assert f.c.get("/api/subjects").json()[0]["status"] == "green"


def test_qtc_time_and_cost(f):
    v = f.scorecard(qtc_enabled=True)
    s = f.subject("T")
    assert f.start(s["id"], v["id"]).json()["code"] == "S006"
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    f.c.patch(f"/api/subjects/{s['id']}", json={"due_at": past, "budget": 100}, headers=H("Lead"))
    sub = f.start(s["id"], v["id"]).json()
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 9)
    assert f.act(sub["id"], "decide", "Lead").json()["code"] == "S006"  # actual cost missing
    f.c.patch(f"/api/submissions/{sub['id']}", json={"actual_cost": 80}, headers=H("Alice"))
    d = f.act(sub["id"], "decide", "Lead").json()
    assert d["decision"] == "passed" and d["time_met"] is False and d["cost_met"] is True and d["qtc_green"] is False
    assert f.c.get("/api/subjects").json()[0]["status"] == "red"  # quality alone is not green


def test_cost_is_cumulative_across_attempts(f):
    v = f.scorecard(qtc_enabled=True)
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    s = f.subject("T", due_at=future, budget=100)
    first = f.start(s["id"], v["id"]).json()
    f.act(first["id"], "submit")
    f.c.patch(f"/api/submissions/{first['id']}", json={"actual_cost": 70}, headers=H("Alice"))
    f.judge(first["id"], 4)
    f.act(first["id"], "decide", "Lead")
    second = f.start(s["id"], v["id"]).json()
    f.act(second["id"], "submit")
    f.c.patch(f"/api/submissions/{second['id']}", json={"actual_cost": 40}, headers=H("Alice"))
    f.judge(second["id"], 9)
    d = f.act(second["id"], "decide", "Lead").json()
    assert d["decision"] == "passed" and d["time_met"] is True and d["cost_met"] is False  # 110 > 100


def test_foundational_red_stops_the_project(f):
    spec_card = f.scorecard(is_foundational=True)
    other = f.scorecard()
    p = f.subject("P", owner="Pat", type_="project")
    spec = f.subject("Spec", parent=p["id"])
    build = f.subject("Build", owner="Bob", parent=p["id"])
    sub = f.start(spec["id"], spec_card["id"]).json()
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 2, "Carol")  # dark red
    d = f.act(sub["id"], "decide", "Lead").json()
    assert d["blocks_project"] is True
    root = f.c.get("/api/subjects").json()[0]
    assert root["status"] == "blocked"
    r = f.start(build["id"], other["id"], actor="Bob")
    assert r.status_code == 409 and r.json()["code"] == "S007"
    redo = f.start(spec["id"], spec_card["id"]).json()  # the blocked work itself can be redone
    f.act(redo["id"], "submit")
    f.judge(redo["id"], 9, "Carol")
    f.act(redo["id"], "decide", "Lead")
    assert f.start(build["id"], other["id"], actor="Bob").status_code == 201


def test_amber_redo_on_foundational_does_not_block(f):
    card = f.scorecard(is_foundational=True)
    s = f.subject("Spec")
    sub = f.start(s["id"], card["id"]).json()
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 7)  # below target 8, but Grey (AMBER), not RED
    assert f.act(sub["id"], "decide", "Lead").json()["blocks_project"] is False


def test_withdraw_and_cancel_rules(f):
    v = f.scorecard()
    s = f.subject("T")
    sub = f.start(s["id"], v["id"]).json()
    assert f.act(sub["id"], "withdraw", "Bob").json()["code"] == "S003"
    assert f.act(sub["id"], "cancel", "Lead").status_code == 422  # reason required
    assert f.act(sub["id"], "withdraw").json()["status"] == "withdrawn"
    assert f.start(s["id"], v["id"]).status_code == 201  # can start again later


def test_retired_version_keeps_open_submission(f):
    v = f.scorecard()
    s = f.subject("T")
    sub = f.start(s["id"], v["id"]).json()
    f.c.post(f"/api/versions/{v['id']}/retire", json={"reason": "replaced"}, headers=H("Designer"))
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 9)
    assert f.act(sub["id"], "decide", "Lead").json()["decision"] == "passed"
    assert f.start(f.subject("U")["id"], v["id"]).json()["code"] == "S010"


def test_subject_hierarchy_guards(f):
    a = f.subject("A")
    b = f.subject("B", parent=a["id"])
    r = f.c.patch(f"/api/subjects/{a['id']}", json={"parent_id": b["id"]}, headers=H("Lead"))
    assert r.json()["code"] == "S008"
    parent = b["id"]
    for i in range(4):
        parent = f.subject(f"L{i}", parent=parent)["id"]  # depth 6
    r = f.c.post("/api/subjects", json={"name": "too deep", "subject_type": "task", "owner": "A", "parent_id": parent},
                 headers=H("Lead"))
    assert r.json()["code"] == "S008"


# ---------------------------------------------------------------- red diagnosis & behaviour analytics


def test_attention_list_and_diagnosis(f):
    v = f.scorecard()
    for i in range(3):
        s = f.subject(f"T{i}", owner="Eve")
        sub = f.start(s["id"], v["id"], actor="Eve").json()
        f.act(sub["id"], "submit", "Eve")
        f.judge(sub["id"], 4)
        f.act(sub["id"], "decide", "Lead")
    people = f.c.get("/api/attention").json()["people"]
    assert people[0]["person"] == "Eve" and people[0]["reds"] == 3 and people[0]["needs_diagnosis"]
    body = {"person": "Eve", "cause": "skill", "action": "train", "notes": "C to Java gap; 1-week module"}
    assert f.c.post("/api/diagnoses", json=body, headers=H("Eve")).json()["code"] == "S003"
    assert f.c.post("/api/diagnoses", json=body, headers=H("Lead")).status_code == 201
    assert not f.c.get("/api/attention").json()["people"][0]["needs_diagnosis"]
    bad = {**body, "cause": "laziness"}
    assert f.c.post("/api/diagnoses", json=bad, headers=H("Lead")).status_code == 422


def test_behaviour_analytics(f):
    v = f.scorecard(required_judges=2, judge_tolerance_pct=50)
    s = f.subject("T")
    sub = f.start(s["id"], v["id"]).json()
    f.self_appraise(sub["id"], 10)
    f.act(sub["id"], "submit")
    f.judge(sub["id"], 8, "Bob")
    f.judge(sub["id"], 9, "Carol")
    f.act(sub["id"], "decide", "Lead")
    b = f.c.get("/api/analytics/behaviour").json()
    assert b["gates"]["passed"] == 1 and b["gates"]["first_attempt_pass_rate"] == 1.0
    assert b["self_appraisal"]["pairs"] == 1 and b["self_appraisal"]["mean_gap_pct"] == 15.0  # 10 vs 8.5
    assert b["disputed_parameters"][0]["mean_spread"] == 1.0
    audit = f.c.get(f"/api/audit?entity=submission&entity_id={sub['id']}").json()
    assert [e["action"] for e in audit][-1] == "decide"
