"""AI-assisted spreadsheet import (app/ai_import.py) contract tests: no network. A fake drafter goes through FastAPI's
dependency_overrides, like tests/test_clarity.py and tests/test_kpi_assist.py. parse_draft and sheet_to_text are
tested directly because that is where the model's output and the messy spreadsheet are handled."""

import io

import pytest
from openpyxl import Workbook

from app.ai_import import (
    DraftContext, SheetDraft, build_prompt, get_sheet_drafter, parse_draft, sheet_to_text, slugify, MAX_ROWS_PER_SHEET,
)
from app.kpi_assist import AssistError
from app.main import app
from app.migration import load_sheets

from .test_kpi_assist import raw_param, raw_rows

TYPES = ["task", "assessment", "communication"]


def xlsx(rows, extra=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet one"
    for r in rows:
        ws.append(r)
    if extra:
        ws2 = wb.create_sheet("Scores")
        for r in extra:
            ws2.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ctx(**kw):
    return DraftContext(filename="Vendors.xlsx", sheet_text="x", subject_types=TYPES, **kw)


def draft_data(**kw):
    return {"summary": "A sheet", "assumptions": ["a1", "", "a2"], "name": "Vendor review", "subject_type": "assessment",
            "purpose": "p", "scope": "s", "objective": "o", "guidance": "g", "target_score": 7,
            "parameters": [raw_param("q", name="Quality", weight=60), raw_param("q1", "q", "Specs", 100, criteria=raw_rows()),
                           raw_param("p", name="Price", weight=40, criteria=raw_rows())], **kw}


# ---------------------------------------------------------------- reading the sheet


def test_sheet_to_text_lists_every_sheet_row_by_row_and_skips_blank_rows():
    sheets = load_sheets("v.xlsx", xlsx([["Vendor review"], [], ["KPI", "Weight"], ["Quality", "high"]], [["Vendor", "Quality"], ["A", 4]]))
    text, truncated = sheet_to_text(sheets)
    assert not truncated
    assert "## Sheet: Sheet one" in text and "## Sheet: Scores" in text
    assert "r3: KPI | Weight" in text and "r4: Quality | high" in text and "r1: Vendor review" in text
    assert "r2:" not in text.split("## Sheet: Scores")[0]  # the blank row is skipped, numbering is the sheet's own


def test_sheet_to_text_truncates_long_sheets_and_says_so():
    sheets = load_sheets("v.xlsx", xlsx([[f"KPI {i}", i] for i in range(MAX_ROWS_PER_SHEET + 50)]))
    text, truncated = sheet_to_text(sheets)
    assert truncated and "more rows not shown" in text and f"KPI {MAX_ROWS_PER_SHEET + 40}" not in text


def test_prompt_carries_scale_rows_depth_types_hint_and_sheet():
    p = build_prompt(DraftContext(filename="v.xlsx", sheet_text="r1: Quality | high", subject_types=TYPES,
                                  max_depth=3, hint="quarterly vendor reviews", subject_type="assessment"))
    assert "9-10, 8, 7, 6, 5, 4, 0-3" in p and "3 level(s)" in p and "task, assessment, communication" in p
    assert "chosen the subject type: assessment" in p and "quarterly vendor reviews" in p and "r1: Quality | high" in p


# ---------------------------------------------------------------- parsing the draft


def test_parse_draft_builds_scorecard_fields_and_tree():
    d = parse_draft("m", draft_data(), ctx())
    assert (d.name, d.subject_type, d.target_score, d.summary) == ("Vendor review", "assessment", 7.0, "A sheet")
    assert d.assumptions == ["a1", "a2"]  # blanks dropped
    assert [p.code for p in d.parameters] == ["1", "2"] and d.parameters[0].children[0].code == "1.1"
    assert len(d.parameters[1].criteria) == 7


def test_parse_draft_repairs_target_subject_type_and_blank_summary():
    d = parse_draft("m", draft_data(target_score=99, subject_type="spaceship", summary=""), ctx())
    assert d.target_score == 8.0  # outside the scale: falls back to 80% of the scale
    assert d.subject_type == "task"  # not a known code: falls back
    assert "2 KPIs with 2 rated parameters" in d.summary and "Vendors.xlsx" in d.summary
    assert parse_draft("m", draft_data(), ctx(subject_type="communication")).subject_type == "communication"  # user's choice wins


def test_parse_draft_without_kpis_is_refused_with_a_useful_message():
    with pytest.raises(AssistError) as e:
        parse_draft("m", {**draft_data(), "parameters": []}, ctx())
    assert e.value.status == 422 and "could not find any KPIs" in str(e.value)


def test_slugify():
    assert slugify("Vendor Review: Q3 (2026)!") == "vendor-review-q3-2026"
    assert slugify("!!") == "imported-scorecard"


# ---------------------------------------------------------------- endpoint


class FakeDrafter:
    model = "fake-import"

    def __init__(self, error=None, **kw):
        self.error, self.seen, self.kw = error, None, kw

    def draft(self, c):
        self.seen = c
        if self.error:
            raise self.error
        return parse_draft("fake-import", draft_data(**self.kw), c)


def post(client, content=None, fname="v.xlsx", **data):
    content = content or xlsx([["KPI", "Weight"], ["Quality", "high"], ["Price", "low"]])
    return client.post("/api/migrations/ai-draft", files=[("files", (fname, content, "application/octet-stream"))],
                       data={"max_depth": "2", **data})


def test_endpoint_returns_a_reviewable_definition_without_saving_anything(client):
    fake = FakeDrafter()
    app.dependency_overrides[get_sheet_drafter] = lambda: fake
    try:
        r = post(client, hint="vendor reviews", rating_scale="0-10-rag")
        assert r.status_code == 200, r.text
        out = r.json()
        d = out["definition"]
        assert d["name"] == "Vendor review" and d["code"] == "vendor-review" and d["owner"] == "Test Bootstrap"
        assert d["tags"] == ["ai-drafted", "imported"] and d["version"]["rating_scale"] == "0-10-rag"
        assert [p["name"] for p in d["version"]["parameters"]] == ["Quality", "Price"]
        assert out["assumptions"] == ["a1", "a2"] and out["issues"] == [] and out["truncated"] is False
        assert out["sheets"] == [{"name": "Sheet one", "rows": 3}]
        assert "Quality | high" in fake.seen.sheet_text and fake.seen.hint == "vendor reviews"
        assert (fake.seen.scale_min, fake.seen.scale_max, fake.seen.max_depth) == (0, 10, 2)
        assert "communication" in fake.seen.subject_types
        assert client.get("/api/scorecards").json() == []  # a preview: nothing was written
        # ...and the definition is accepted as-is by the normal create endpoint, as a draft
        made = client.post("/api/scorecards?publish=false", json=d)
        assert made.status_code == 201, made.text
        assert made.json()["versions"][0]["status"] == "draft"
    finally:
        app.dependency_overrides.clear()


def test_endpoint_makes_the_code_unique(client):
    app.dependency_overrides[get_sheet_drafter] = lambda: FakeDrafter()
    try:
        first = post(client).json()["definition"]
        assert client.post("/api/scorecards?publish=false", json=first).status_code == 201
        assert post(client).json()["definition"]["code"] == "vendor-review-2"
    finally:
        app.dependency_overrides.clear()


def test_endpoint_flags_problems_in_the_draft(client):
    # a leaf the model left without any matrix rows, and no purpose: both are reported, not hidden
    bad = {"parameters": [raw_param("a", name="Only", criteria=[])], "purpose": ""}
    app.dependency_overrides[get_sheet_drafter] = lambda: FakeDrafter(**bad)
    try:
        out = post(client).json()
        codes = {i["code"] for i in out["issues"]}
        assert {"V016", "V019"} <= codes
    finally:
        app.dependency_overrides.clear()


def test_endpoint_maps_drafter_errors_and_rejects_bad_input(client):
    app.dependency_overrides[get_sheet_drafter] = lambda: FakeDrafter(error=AssistError("AI import is not configured", 503))
    try:
        r = post(client)
        assert r.status_code == 503 and r.json()["code"] == "J004"
        assert post(client, max_depth="9").status_code == 422 or post(client, max_depth="9").json()["code"] == "M001"
        assert post(client, rating_scale="nope").status_code in (400, 404, 422)
        assert post(client, subject_type="nope").status_code in (400, 404, 422)
        assert post(client, hint="x" * 1001).json()["code"] == "M001"
        assert post(client, b"not a workbook").json()["code"] == "M001"
        assert post(client, xlsx([[None]])).json()["code"] == "M002"
        assert post(client, b"a,b", fname="v.pdf").json()["code"] == "M001"
    finally:
        app.dependency_overrides.clear()


def test_endpoint_needs_login_and_designer_role(client):
    app.dependency_overrides[get_sheet_drafter] = lambda: FakeDrafter()
    try:
        assert post(client).status_code == 200
        r = client.post("/api/auth/register", json={"username": "plain-user", "password": "Another-Pass-123!",
                                                    "display_name": "Plain User"})
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        files = [("files", ("v.xlsx", xlsx([["KPI"], ["Quality"]]), "application/octet-stream"))]
        assert client.post("/api/migrations/ai-draft", files=files, headers=h).status_code == 403
        assert client.post("/api/migrations/ai-draft", files=files, headers={"Authorization": ""}).status_code == 401
    finally:
        app.dependency_overrides.clear()
