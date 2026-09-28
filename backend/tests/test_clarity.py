"""Clarity agent contract tests (docs/12_ARCHITECTURE.md "ODTQRC task definition") — no network, using a fake
agent through FastAPI's dependency_overrides, exactly like the LLM judge tests in test_api.py.
"""

from app.clarity import ClarityIssue, ClarityResult, get_clarity_agent, parse_result
from app.main import app


def make_subject(client, **odtqrc):
    r = client.post("/api/subjects", json={"name": "Test task", "subject_type": "task", "owner": "Alice", **odtqrc})
    assert r.status_code == 201, r.text
    return r.json()


class FakeClarityAgent:
    model = "fake-clarity"

    def __init__(self, result=None):
        self.seen = None
        self._result = result or ClarityResult(
            self.model, is_clear=False,
            issues=[ClarityIssue("quality", "No measurable standard", "Add a checklist")],
            summary="Quality is vague",
        )

    def review(self, task):
        self.seen = task
        return self._result


def test_clarity_check_flags_vague_fields(client):
    s = make_subject(client, objective="Do the thing", quality_bar="make it good")
    fake = FakeClarityAgent()
    app.dependency_overrides[get_clarity_agent] = lambda: fake
    try:
        r = client.post(f"/api/subjects/{s['id']}/clarity-check")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["model"] == "fake-clarity" and body["is_clear"] is False
        assert body["summary"] == "Quality is vague"
        assert body["issues"] == [{"field": "quality", "problem": "No measurable standard",
                                   "suggestion": "Add a checklist"}]
        assert fake.seen["objective"] == "Do the thing" and fake.seen["quality_bar"] == "make it good"
    finally:
        app.dependency_overrides.clear()


def test_clarity_check_passes_a_well_defined_task(client):
    s = make_subject(client, objective="Ship v2 of the report", deliverable="report-v2.pdf",
                     quality_bar="Passes the 12-item review checklist", risks="Reviewer on leave next week")
    fake = FakeClarityAgent(ClarityResult("fake-clarity", True, [], "Looks clear"))
    app.dependency_overrides[get_clarity_agent] = lambda: fake
    try:
        r = client.post(f"/api/subjects/{s['id']}/clarity-check")
        assert r.status_code == 200
        body = r.json()
        assert body["is_clear"] is True and body["issues"] == []
    finally:
        app.dependency_overrides.clear()


def test_clarity_check_never_changes_the_subject(client):
    s = make_subject(client, objective="Original objective")
    fake = FakeClarityAgent()
    app.dependency_overrides[get_clarity_agent] = lambda: fake
    try:
        client.post(f"/api/subjects/{s['id']}/clarity-check")
    finally:
        app.dependency_overrides.clear()
    assert client.get(f"/api/subjects/{s['id']}").json()["objective"] == "Original objective"


def test_clarity_check_unconfigured_returns_503(client, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", "/nonexistent")
    s = make_subject(client)
    r = client.post(f"/api/subjects/{s['id']}/clarity-check")
    assert r.status_code in (502, 503) and r.json()["code"] == "J002"


def test_clarity_check_on_unknown_subject_is_404(client):
    r = client.post("/api/subjects/999999/clarity-check")
    assert r.status_code == 404


def test_clarity_output_is_sanitised():
    data = {
        "is_clear": False,
        "issues": [
            {"field": "quality", "problem": "vague", "suggestion": "be specific"},
            {"field": "not-a-real-field", "problem": "x", "suggestion": "y"},
        ],
        "summary": "s",
    }
    res = parse_result("m", data)
    assert [(i.field, i.problem, i.suggestion) for i in res.issues] == [("quality", "vague", "be specific")]
    assert res.summary == "s" and res.is_clear is False and res.model == "m"


def test_clarity_output_defaults_is_clear_from_issues_when_missing():
    assert parse_result("m", {"issues": [], "summary": ""}).is_clear is True
    assert parse_result("m", {"issues": [{"field": "cost", "problem": "p", "suggestion": "s"}],
                              "summary": ""}).is_clear is False
