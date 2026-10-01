"""AI Assist (app/kpi_assist.py) contract tests: no network, a fake assistant through FastAPI's dependency_overrides,
exactly like tests/test_clarity.py. parse_result is tested directly because it is where the model's output is
repaired or rejected."""

import pytest

from app.kpi_assist import AssistContext, AssistError, AssistResult, get_kpi_assistant, parse_result, required_rows
from app.main import app


def raw_rows(lo=0, hi=10):
    return [{"score_min": s, "score_max": s, "qualitative": f"Level {s}", "quantitative": f"q{s}"} for s in range(lo, hi + 1)]


def raw_param(pid, parent="", name=None, weight=1, **kw):
    return {"id": pid, "parent_id": parent, "name": name or pid, "description": "", "weight": weight,
            "is_critical": False, "min_acceptable_score": None, "criteria": [], "metrics": [], **kw}


def test_required_rows_follow_the_scale_bands():
    assert required_rows(AssistContext()) == [(9, 10), (8, 8), (7, 7), (6, 6), (5, 5), (4, 4), (0, 3)]
    likert = AssistContext(scale_min=1, scale_max=5, band_lower_bounds=[5, 4, 3, 2, 1])
    assert required_rows(likert) == [(5, 5), (4, 4), (3, 3), (2, 2), (1, 1)]


def test_parse_builds_tree_with_codes_and_snaps_matrix_to_required_rows():
    data = {"reply": "ok", "parameters": [
        raw_param("clarity", name="Clarity", weight=40),
        raw_param("c1", "clarity", "Purpose", 50, criteria=raw_rows()),  # one row per score: merged into bands
        raw_param("c2", "clarity", "Ask", 50, criteria=[{"score_min": 0, "score_max": 10, "qualitative": "everything",
                                                         "quantitative": ""}]),
        raw_param("tone", name="Tone", weight=60, criteria=raw_rows()),
    ]}
    res = parse_result("m", data, AssistContext())
    assert [p.code for p in res.parameters] == ["1", "2"]
    clarity, tone = res.parameters
    assert [c.code for c in clarity.children] == ["1.1", "1.2"] and clarity.criteria == []
    ranges = [(c.score_min, c.score_max) for c in tone.criteria]
    assert ranges == required_rows(AssistContext())
    assert tone.criteria[0].qualitative == "Level 10"  # 9-10 takes the model's row covering its top score
    assert clarity.children[1].criteria[3].qualitative == "everything"  # a wide row is spread over every range
    assert clarity.children[1].criteria[3].quantitative is None


def test_parse_skipped_range_stays_blank_so_validation_flags_it():
    rows = [r for r in raw_rows() if r["score_min"] >= 4]  # model forgot 0-3
    res = parse_result("m", {"reply": "", "parameters": [raw_param("a", criteria=rows)]}, AssistContext())
    last = res.parameters[0].criteria[-1]
    assert (last.score_min, last.score_max, last.qualitative) == (0, 3, "")


def test_parse_repairs_bad_values_instead_of_trusting_them():
    metric = {"code": "spell errors", "name": "Spelling errors", "unit": "", "data_type": "bogus",
              "thresholds": [{"min_value": None, "max_value": 1, "score": 99},
                             {"min_value": 1, "max_value": None, "score": 4}]}
    data = {"reply": "", "parameters": [
        raw_param("a", weight=-5, is_critical=True, min_acceptable_score=50, criteria=raw_rows(), metrics=[metric, metric]),
        raw_param("", name=""),  # nameless: dropped
        raw_param("b", parent="does-not-exist", name="Orphan"),  # unknown parent: becomes top level
        raw_param("c", parent="c", name="Self parent"),  # parent is itself: becomes top level
    ]}
    res = parse_result("m", data, AssistContext())
    assert [p.name for p in res.parameters] == ["a", "Orphan", "Self parent"]
    a = res.parameters[0]
    assert a.weight == 0 and a.min_acceptable_score == 10
    assert len(a.metrics) == 1 and a.metrics[0].code == "spell_errors" and a.metrics[0].data_type == "number"
    assert [t.score for t in a.metrics[0].thresholds] == [10, 4]


def test_parse_cycle_in_parents_cannot_loop():
    data = {"reply": "", "parameters": [raw_param("x", parent="y", name="X"), raw_param("y", parent="x", name="Y")]}
    res = parse_result("m", data, AssistContext())
    assert res.parameters == []  # unreachable from the top level, so nothing loops and nothing is invented


def test_parse_too_many_parameters_is_refused():
    data = {"reply": "", "parameters": [raw_param(f"p{i}") for i in range(61)]}
    with pytest.raises(AssistError):
        parse_result("m", data, AssistContext())


def test_parse_question_only_has_no_parameters():
    res = parse_result("m", {"reply": "Which KPIs do you want?", "parameters": []}, AssistContext())
    assert res.parameters == [] and res.reply == "Which KPIs do you want?"


# ---------------------------------------------------------------- endpoint


class FakeAssistant:
    model = "fake-assist"

    def __init__(self, result=None, error=None):
        self.seen = None
        self.error = error
        self._result = result

    def propose(self, messages, ctx):
        self.seen = (messages, ctx)
        if self.error:
            raise self.error
        return self._result or AssistResult("fake-assist", "Drafted two KPIs", parse_result(
            "fake", {"reply": "", "parameters": [raw_param("a", name="Clarity", weight=60, criteria=raw_rows()),
                                                 raw_param("b", name="Tone", weight=40, criteria=raw_rows())]},
            AssistContext()).parameters)


def body(**kw):
    return {"messages": [{"role": "user", "content": "I want clarity and tone"}], "name": "Email", "purpose": "p",
            "objective": "o", "rating_scale": "0-10-rag", "target_score": 7, "max_depth": 2, **kw}


def test_endpoint_returns_a_proposal_and_context_reaches_the_assistant(client):
    fake = FakeAssistant()
    app.dependency_overrides[get_kpi_assistant] = lambda: fake
    try:
        r = client.post("/api/ai-assist/parameters", json=body(existing=["Safety"]))
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["model"] == "fake-assist" and out["reply"] == "Drafted two KPIs"
        assert [p["name"] for p in out["parameters"]] == ["Clarity", "Tone"]
        assert [p["code"] for p in out["parameters"]] == ["1", "2"]
        assert out["issues"] == []  # complete matrix: nothing to fix
        messages, ctx = fake.seen
        assert messages == [{"role": "user", "content": "I want clarity and tone"}]
        assert (ctx.scale_min, ctx.scale_max, ctx.max_depth, ctx.existing) == (0, 10, 2, ["Safety"])
        assert ctx.band_lower_bounds == [9, 8, 7, 6, 5, 4, 0]
    finally:
        app.dependency_overrides.clear()


def test_endpoint_reports_validation_issues_in_the_proposal(client):
    incomplete = parse_result("f", {"reply": "", "parameters": [raw_param("a", criteria=[])]}, AssistContext()).parameters
    app.dependency_overrides[get_kpi_assistant] = lambda: FakeAssistant(AssistResult("f", "x", incomplete))
    try:
        out = client.post("/api/ai-assist/parameters", json=body()).json()
        assert {i["code"] for i in out["issues"]} == {"V019"}  # blank guidelines: flagged, not hidden
        assert all(i["path"] for i in out["issues"])  # parameter-level only; purpose etc. are the form's job
    finally:
        app.dependency_overrides.clear()


def test_endpoint_maps_assistant_errors(client):
    app.dependency_overrides[get_kpi_assistant] = lambda: FakeAssistant(error=AssistError("not configured", 503))
    try:
        r = client.post("/api/ai-assist/parameters", json=body())
        assert r.status_code == 503 and r.json()["code"] == "J003"
    finally:
        app.dependency_overrides.clear()


def test_endpoint_rejects_bad_requests(client):
    app.dependency_overrides[get_kpi_assistant] = lambda: FakeAssistant()
    try:
        assert client.post("/api/ai-assist/parameters", json=body(messages=[])).status_code == 422
        assert client.post("/api/ai-assist/parameters", json=body(rating_scale="nope")).status_code in (400, 404, 422)
        assert client.post("/api/ai-assist/parameters", json=body(max_depth=9)).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_endpoint_needs_login_and_designer_role(client):
    app.dependency_overrides[get_kpi_assistant] = lambda: FakeAssistant()
    try:
        assert client.post("/api/ai-assist/parameters", json=body(), headers={"Authorization": ""}).status_code == 401
        r = client.post("/api/auth/register", json={"username": "plain-user", "password": "Another-Pass-123!",
                                                    "display_name": "Plain User"})
        assert r.status_code == 201, r.text
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        assert "designer" not in r.json()["user"]["roles"]
        assert client.post("/api/ai-assist/parameters", json=body(), headers=h).status_code == 403
    finally:
        app.dependency_overrides.clear()
