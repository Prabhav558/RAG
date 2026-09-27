"""API-level scenarios: validation, lifecycle, invalid data, seed ingestion, LLM judge contract."""

import copy
import io
import json
import zipfile

import pytest

from app.judge import JudgeRating, JudgeResult, get_judge, parse_result
from app.main import app

from .conftest import ROOT, definition, leaf, matrix


def create(client, d, publish=True):
    r = client.post(f"/api/scorecards?publish={str(publish).lower()}", json=d)
    assert r.status_code == 201, r.text
    return r.json()


def version_id(card, status="published"):
    return next(v["id"] for v in card["versions"] if v["status"] == status)


def leaves(version):
    out = []

    def walk(nodes):
        for n in nodes:
            out.append(n) if n["is_leaf"] else walk(n["children"])

    walk(version["parameters"])
    return out


def new_eval(client, vid, **kw):
    r = client.post("/api/evaluations", json={"version_id": vid, "subject_name": "Subject", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def rate(client, ev, scores: dict, **extra):
    ids = {n["code"]: n["id"] for n in leaves(ev["version"])}
    ratings = [{"parameter_id": ids[c], "judged_score": s, "rationale": "because"} for c, s in scores.items()]
    return client.put(f"/api/evaluations/{ev['id']}", json={"ratings": ratings, **extra})


def publish_errors(client, d):
    card = create(client, d, publish=False)
    r = client.post(f"/api/versions/{version_id(card, 'draft')}/publish")
    assert r.status_code == 422, r.text
    return {i["code"] for i in r.json()["details"]}


# ---------------------------------------------------------------- normal path


def test_N01_all_seed_scorecards_ingest_and_publish(client):
    files = sorted((ROOT / "data" / "scorecards").glob("*.json"))
    assert len(files) >= 5
    subject_types = set()
    for f in files:
        d = json.loads(f.read_text())
        card = create(client, d)
        issues = client.post(f"/api/versions/{version_id(card)}/validate").json()
        assert not [i for i in issues if i["severity"] == "error"], (f.name, issues)
        subject_types.add(d["subject_type"])
    assert len(subject_types) == len(files)  # every seed scorecard is for a different subject type


def test_N01_assessment_quality_has_four_levels(client):
    card = create(client, json.loads((ROOT / "data/scorecards/assessment-quality.json").read_text()))
    assert card["depth"] == 4 and card["subject_type"] == "assessment"
    v = client.get(f"/api/versions/{version_id(card)}").json()
    total = sum(n["effective_weight"] for n in leaves(v))
    assert total == pytest.approx(1.0)


def test_N02_human_evaluation_end_to_end(client):
    card = create(client, definition())
    ev = new_eval(client, version_id(card), evaluator_type="human")
    ev = rate(client, ev, {"A": 9, "B": 7}).json()
    assert ev["final_score"] == 8.2 and ev["band_label"] == "Light green"
    r = client.post(f"/api/evaluations/{ev['id']}/complete")
    assert r.status_code == 200 and r.json()["quality_met"] is True
    rows = client.get("/api/evaluations").json()
    assert rows[0]["status"] == "completed"


def test_N04_document_upload_txt_and_docx(client):
    card = create(client, definition())
    ev = new_eval(client, version_id(card))
    r = client.post(f"/api/evaluations/{ev['id']}/documents", files={"file": ("a.txt", b"hello world", "text/plain")})
    assert r.status_code == 201 and r.json()["documents"][0]["chars"] == 11
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<w:document><w:body><w:p><w:r><w:t>Q1 &amp; answer</w:t></w:r></w:p>'
                                        "</w:body></w:document>")
    r = client.post(f"/api/evaluations/{ev['id']}/documents", files={"file": ("b.docx", buf.getvalue(), "x")})
    assert r.status_code == 201 and r.json()["documents"][1]["chars"] == len("Q1 & answer")


# ---------------------------------------------------------------- business variants


def test_BV01_one_to_five_scale(client):
    d = definition(scale="1-5-likert", target=4, params=[leaf("A", 1, 1, 5), leaf("B", 1, 1, 5)])
    card = create(client, d)
    ev = rate(client, new_eval(client, version_id(card)), {"A": 5, "B": 4}).json()
    assert ev["final_score"] == 4.5 and ev["band_label"] == "Good"


def test_BV02_percentage_scale_with_ranged_criteria(client):
    rows = [{"score_min": lo, "score_max": hi, "qualitative": f"{lo}-{hi}"} for lo, hi in
            [(0, 24), (25, 49), (50, 74), (75, 89), (90, 94), (95, 100)]]
    d = definition(scale="0-100-pct", target=90, params=[{"code": "A", "name": "A", "criteria": rows}])
    card = create(client, d)
    ev = rate(client, new_eval(client, version_id(card)), {"A": 92}).json()
    assert ev["band_label"] == "Compliant"


def test_BV07_override_recorded_via_api(client):
    p = leaf("A", metrics=[{"code": "m", "name": "M", "data_type": "percent",
                            "thresholds": [{"min_value": 50, "score": 10}, {"max_value": 50, "score": 2}]}])
    card = create(client, definition(params=[p]))
    ev = new_eval(client, version_id(card))
    node = leaves(ev["version"])[0]
    mid = node["metrics"][0]["id"]
    ev = client.put(f"/api/evaluations/{ev['id']}", json={"metric_values": [{"metric_id": mid, "value": 80}]}).json()
    assert ev["final_score"] == 10
    body = {"ratings": [{"parameter_id": node["id"], "judged_score": 6, "override_reason": "Metric miscounted"}]}
    ev = client.put(f"/api/evaluations/{ev['id']}", json=body).json()
    res = leaves(ev["version"])[0]["result"]
    assert ev["final_score"] == 6 and res["score_source"] == "override" and res["computed_score"] == 10


def test_BV08_qtc_via_api_and_I18_missing_time_cost(client):
    card = create(client, definition(qtc_enabled=True))
    ev = rate(client, new_eval(client, version_id(card)), {"A": 9, "B": 9}).json()
    r = client.post(f"/api/evaluations/{ev['id']}/complete")
    assert r.status_code == 422 and r.json()["code"] == "E007"
    ev = client.put(f"/api/evaluations/{ev['id']}", json={"time_met": True, "cost_met": False}).json()
    assert ev["quality_met"] is True and ev["qtc_green"] is False


def test_BV09_evaluation_target_override(client):
    card = create(client, definition())
    ev = rate(client, new_eval(client, version_id(card), target_score=6), {"A": 6, "B": 6}).json()
    assert ev["quality_met"] is True


def test_BV10_clone_as_template(client):
    card = create(client, definition())
    r = client.post(f"/api/scorecards/{card['id']}/clone", json={"code": "copy", "name": "Copy"})
    assert r.status_code == 201
    clone = r.json()
    assert clone["versions"][0]["status"] == "draft" and clone["leaf_count"] == 2


def test_BV11_custom_subject_type_and_scale(client):
    assert client.post("/api/meta/subject-types", json={"code": "vendor", "name": "Vendor"}).status_code == 201
    scale = {"code": "0-4", "name": "0-4", "min_value": 0, "max_value": 4, "bands": [
        {"label": "Top", "lower_bound": 3, "color_hex": "#00B050", "font_hex": "#FFFFFF", "rag": "GREEN"},
        {"label": "Low", "lower_bound": 0, "color_hex": "#C00000", "font_hex": "#FFFFFF", "rag": "RED"}]}
    assert client.post("/api/meta/scales", json=scale).status_code == 201
    d = definition(scale="0-4", target=3, params=[leaf("A", 1, 0, 4)])
    d["subject_type"] = "vendor"
    card = create(client, d)
    ev = rate(client, new_eval(client, version_id(card)), {"A": 3}).json()
    assert ev["band_label"] == "Top" and ev["quality_met"] is True


# ---------------------------------------------------------------- lifecycle


def test_L01_draft_saves_with_issues(client):
    card = create(client, definition(), publish=False)
    vid = version_id(card, "draft")
    content = client.get(f"/api/versions/{vid}/definition").json()["version"]
    content["parameters"][0]["criteria"] = []
    r = client.put(f"/api/versions/{vid}", json=content)
    assert r.status_code == 200
    assert "V005" in {i["code"] for i in r.json()["issues"]}


def test_L02_published_is_immutable(client):
    card = create(client, definition())
    vid = version_id(card)
    content = client.get(f"/api/versions/{vid}/definition").json()["version"]
    r = client.put(f"/api/versions/{vid}", json=content)
    assert r.status_code == 409 and r.json()["code"] == "E009"


def test_L03_new_version_retires_old_and_preserves_history(client):
    card = create(client, definition())
    v1 = version_id(card)
    ev1 = rate(client, new_eval(client, v1), {"A": 10, "B": 5}).json()
    client.post(f"/api/evaluations/{ev1['id']}/complete")
    v2 = client.post(f"/api/versions/{v1}/new-draft?change_note=reweight").json()
    assert v2["version_no"] == 2 and v2["status"] == "draft"
    content = client.get(f"/api/versions/{v2['id']}/definition").json()["version"]
    content["parameters"][0]["weight"], content["parameters"][1]["weight"] = 50, 50
    assert client.put(f"/api/versions/{v2['id']}", json=content).status_code == 200
    assert client.post(f"/api/versions/{v2['id']}/publish").status_code == 200
    statuses = {v["id"]: v["status"] for v in client.get(f"/api/scorecards/{card['id']}").json()["versions"]}
    assert statuses == {v1: "retired", v2["id"]: "published"}
    assert client.get(f"/api/evaluations/{ev1['id']}").json()["final_score"] == 8.0  # v1 weights 60/40
    r = client.post("/api/evaluations", json={"version_id": v1, "subject_name": "x"})
    assert r.status_code == 409 and r.json()["code"] == "E001"
    assert client.post(f"/api/versions/{v2['id']}/new-draft").status_code == 201
    assert client.post(f"/api/versions/{v2['id']}/new-draft").json()["code"] == "E014"


def test_L04_incomplete_cannot_complete(client):
    card = create(client, definition())
    ev = rate(client, new_eval(client, version_id(card)), {"A": 9}).json()
    assert ev["final_score"] == 9 and ev["quality_met"] is None
    r = client.post(f"/api/evaluations/{ev['id']}/complete")
    assert r.status_code == 422 and r.json()["code"] == "E005" and r.json()["details"] == ["B Param B"]


def test_L05_completed_is_immutable_and_L06_void(client):
    card = create(client, definition())
    ev = rate(client, new_eval(client, version_id(card)), {"A": 9, "B": 9}).json()
    client.post(f"/api/evaluations/{ev['id']}/complete")
    r = rate(client, ev, {"A": 1})
    assert r.status_code == 409 and r.json()["code"] == "E006"
    assert client.get("/api/analytics/overview").json()["total_completed"] == 1
    assert client.post(f"/api/evaluations/{ev['id']}/void", json={"reason": "duplicate"}).json()["status"] == "void"
    assert client.get("/api/analytics/overview").json()["total_completed"] == 0


def test_L07_self_appraisal_private_by_default(client):
    card = create(client, definition())
    ev = rate(client, new_eval(client, version_id(card), evaluator_type="self"), {"A": 9, "B": 9}).json()
    assert ev["is_private"] is True
    client.post(f"/api/evaluations/{ev['id']}/complete")
    assert client.get("/api/evaluations").json() == []
    assert len(client.get("/api/evaluations?include_private=true").json()) == 1
    assert client.get("/api/analytics/overview").json()["total_completed"] == 0


def test_L08_resubmission_first_attempt_rate(client):
    card = create(client, definition())
    vid = version_id(card)
    for attempt, scores in [(1, {"A": 5, "B": 5}), (2, {"A": 9, "B": 9})]:
        ev = rate(client, new_eval(client, vid, subject_ref="S1", attempt_no=attempt), scores).json()
        client.post(f"/api/evaluations/{ev['id']}/complete")
    o = client.get("/api/analytics/overview").json()
    assert o["pass_rate"] == 0.5 and o["first_attempt_pass_rate"] == 0.0


# ---------------------------------------------------------------- invalid scenarios (definition)


@pytest.mark.parametrize(
    "scenario,mutate,code",
    [
        ("I01", lambda d: d["version"].update(max_depth=1, parameters=[
            {"code": "P", "name": "P", "children": [leaf("C")]}]), "V002"),
        ("I02", lambda d: d["version"]["parameters"][0].update(criteria=matrix(0, 8)), "V005"),
        ("I03", lambda d: d["version"]["parameters"][0]["criteria"].append(
            {"score_min": 3, "score_max": 5, "qualitative": "dup"}), "V006"),
        ("I04", lambda d: d["version"].update(target_score=11), "V012"),
        ("I05", lambda d: [p.update(weight=0) for p in d["version"]["parameters"]], "V003"),
        ("I06", lambda d: d["version"]["parameters"][0].update(metrics=[{"code": "m", "name": "m", "thresholds": [
            {"min_value": 0, "max_value": 60, "score": 5}, {"min_value": 50, "score": 9}]}]), "V009"),
        ("I07", lambda d: d["version"]["parameters"][0].update(metrics=[{"code": "m", "name": "m"}]), "V011"),
        ("I08", lambda d: d["version"].update(purpose="  ", objective=""), "V016"),
        ("I09", lambda d: d["version"].update(parameters=[{"code": "P", "name": "P", "children": [leaf("C")],
            "metrics": [{"code": "m", "name": "m", "thresholds": [{"score": 5}]}]}]), "V017"),
        ("I00", lambda d: d["version"].update(parameters=[]), "V001"),
    ],
)
def test_invalid_definitions_block_publish(client, scenario, mutate, code):
    d = definition(code=f"inv-{scenario.lower()}")
    mutate(d)
    assert code in publish_errors(client, d), scenario


def test_I20_negative_weight_rejected_by_contract(client):
    d = definition()
    d["version"]["parameters"][0]["weight"] = -1
    assert client.post("/api/scorecards", json=d).status_code == 422


def test_I10_duplicate_parameter_code_rejected_on_save(client):
    d = definition()
    d["version"]["parameters"][1]["code"] = "A"
    r = client.post("/api/scorecards", json=d)
    assert r.status_code == 422 and r.json()["code"] == "V015"


def test_I16_duplicate_scorecard_code(client):
    create(client, definition())
    r = client.post("/api/scorecards", json=definition())
    assert r.status_code == 409 and r.json()["code"] == "E011"


def test_I19_scale_without_band_at_minimum(client):
    scale = {"code": "bad", "name": "bad", "min_value": 0, "max_value": 4, "bands": [
        {"label": "Top", "lower_bound": 3, "color_hex": "#00B050", "font_hex": "#FFFFFF", "rag": "GREEN"}]}
    r = client.post("/api/meta/scales", json=scale)
    assert r.status_code == 422 and r.json()["code"] == "V013"


def test_publish_warnings_do_not_block(client):
    params = [leaf(str(i)) for i in range(9)]
    card = create(client, definition(params=params), publish=False)
    r = client.post(f"/api/versions/{version_id(card, 'draft')}/publish")
    assert r.status_code == 200 and "W101" in {i["code"] for i in r.json()["issues"]}


# ---------------------------------------------------------------- invalid scenarios (evaluation)


def test_I11_evaluation_against_draft(client):
    card = create(client, definition(), publish=False)
    r = client.post("/api/evaluations", json={"version_id": version_id(card, "draft"), "subject_name": "x"})
    assert r.json()["code"] == "E001"


@pytest.mark.parametrize("score,code", [(11, "E002"), (-1, "E002"), (7.5, "E012")])
def test_I12_I15_bad_scores(client, score, code):
    card = create(client, definition())
    r = rate(client, new_eval(client, version_id(card)), {"A": score})
    assert r.status_code == 422 and r.json()["code"] == code


def test_I13_rating_a_parent_and_I14_na_on_required(client):
    params = [{"code": "P", "name": "P", "children": [leaf("C")]}, leaf("D")]
    card = create(client, definition(params=params))
    ev = new_eval(client, version_id(card))
    parent = ev["version"]["parameters"][0]
    r = client.put(f"/api/evaluations/{ev['id']}", json={"ratings": [{"parameter_id": parent["id"], "judged_score": 5}]})
    assert r.json()["code"] == "E003"
    d_id = ev["version"]["parameters"][1]["id"]
    r = client.put(f"/api/evaluations/{ev['id']}", json={"ratings": [{"parameter_id": d_id, "not_applicable": True}]})
    assert r.json()["code"] == "E004"


def test_I17_invalid_metric_values(client):
    p = leaf("A", metrics=[{"code": "m", "name": "M", "data_type": "percent", "thresholds": [{"score": 5}]},
                           {"code": "c", "name": "C", "data_type": "count", "thresholds": [{"score": 5}]}])
    card = create(client, definition(params=[p]))
    ev = new_eval(client, version_id(card))
    pct, cnt = (m["id"] for m in leaves(ev["version"])[0]["metrics"])
    for mid, value in [(pct, 101), (cnt, 1.5), (cnt, -1)]:
        r = client.put(f"/api/evaluations/{ev['id']}", json={"metric_values": [{"metric_id": mid, "value": value}]})
        assert r.json()["code"] == "E013", (mid, value)


def test_parameter_from_other_version_rejected(client):
    a = create(client, definition(code="card-a"))
    b = create(client, definition(code="card-b"))
    ev_a = new_eval(client, version_id(a))
    ev_b = new_eval(client, version_id(b))
    foreign = leaves(ev_b["version"])[0]["id"]
    r = client.put(f"/api/evaluations/{ev_a['id']}", json={"ratings": [{"parameter_id": foreign, "judged_score": 5}]})
    assert r.json()["code"] == "E008"


# ---------------------------------------------------------------- LLM judge (contract, no network)


class FakeJudge:
    model = "fake-judge"

    def __init__(self):
        self.seen = None

    def evaluate(self, version, subject_name, input_text):
        self.seen = input_text
        codes = [n["code"] for n in leaves(version)]
        return JudgeResult(self.model, [JudgeRating(c, 8, "r", "e", 0.9) for c in codes[:-1]], [], "summary")


def test_N03_llm_judge_prefills_then_human_completes(client):
    fake = FakeJudge()
    app.dependency_overrides[get_judge] = lambda: fake
    try:
        card = create(client, definition())
        ev = new_eval(client, version_id(card), input_text="The work")
        client.post(f"/api/evaluations/{ev['id']}/documents", files={"file": ("d.md", b"# Doc", "text/markdown")})
        r = client.post(f"/api/evaluations/{ev['id']}/llm-judge")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "The work" in fake.seen and "# Doc" in fake.seen
        assert body["judge_model"] == "fake-judge" and body["summary"] == "summary"
        assert body["judge_unrated"] == 1  # judge skipped B; a human must finish it
        ev = rate(client, body, {"B": 9}).json()
        assert client.post(f"/api/evaluations/{ev['id']}/complete").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_judge_output_is_sanitised():
    version = {"rating_scale": {"min_value": 0, "max_value": 10}, "parameters": [
        {"code": "A", "is_leaf": True, "metrics": [{"code": "m"}], "children": [], "name": "A"},
        {"code": "P", "is_leaf": False, "metrics": [], "name": "P", "children": [
            {"code": "B", "is_leaf": True, "metrics": [], "children": [], "name": "B"}]}]}
    data = {
        "ratings": [
            {"parameter_code": "A", "score": 7, "rationale": "x", "evidence": "y", "confidence": 3},
            {"parameter_code": "A", "score": 2, "rationale": "dup", "evidence": "", "confidence": 1},
            {"parameter_code": "P", "score": 5, "rationale": "parent", "evidence": "", "confidence": 1},
            {"parameter_code": "B", "score": 42, "rationale": "out of range", "evidence": "", "confidence": 1},
            {"parameter_code": "Z", "score": 5, "rationale": "unknown", "evidence": "", "confidence": 1},
        ],
        "metric_values": [{"metric_code": "A#m", "value": 50, "note": ""}, {"metric_code": "none", "value": 1}],
        "summary": "s",
    }
    res = parse_result("m", version, data)
    assert [(r.parameter_code, r.score, r.confidence) for r in res.ratings] == [("A", 7, 1.0)]
    assert [m.metric_code for m in res.metric_values] == ["A#m"]


def test_judge_prompt_and_schema_cover_every_leaf(client):
    from app.judge import build_prompt, output_schema

    card = create(client, copy.deepcopy(json.loads((ROOT / "data/scorecards/assessment-quality.json").read_text())))
    v = client.get(f"/api/versions/{version_id(card)}").json()
    prompt = build_prompt(v, "Quiz", "content")
    codes = [n["code"] for n in leaves(v)]
    assert all(f"[{c}]" in prompt for c in codes)
    schema = output_schema(v)
    assert schema["properties"]["ratings"]["items"]["properties"]["parameter_code"]["enum"] == codes
    assert "2.2#errors_found" in schema["properties"]["metric_values"]["items"]["properties"]["metric_code"]["enum"]


def test_judge_unconfigured_returns_503(client, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", "/nonexistent")
    card = create(client, definition())
    ev = new_eval(client, version_id(card), input_text="x")
    r = client.post(f"/api/evaluations/{ev['id']}/llm-judge")
    assert r.status_code in (502, 503) and r.json()["code"] == "J001"
