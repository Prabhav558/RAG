"""Cycle 2 · §8.3–8.4 — legacy spreadsheet migration: every injected problem has a defined, tested outcome."""

import pytest
from sqlalchemy import func, select

from app import migration as mig
from app.models import Evaluation, Scorecard, SubjectType

from .conftest import ROOT

LEGACY = ROOT / "data" / "legacy"


def files(*names):
    return [(n, (LEGACY / n).read_bytes()) for n in names]


def row(m, sheet_row, kind="rating"):
    return next(r for r in m.rows if r.row == sheet_row and r.kind == kind)


def test_M00_clean_workbook_imports_and_reconciles(db):
    m = mig.plan(db, files("code-review-quality.xlsx"))
    assert not m.fatal
    d = m.to_dict()
    assert d["status"] == "ok"
    assert m.scale_code == "1-5-likert" and m.definition.version.target_score == 4
    assert [p.code for p in m.definition.version.parameters] == ["1", "2", "3", "4", "5"]
    assert d["reconciliation"] == {"rows_with_legacy_total": 15, "matched": 15, "mismatched": 0,
                                   "mismatched_unexplained": 0, "max_abs_diff": 0.0}
    mig.commit(db, m)
    stored = {e.origin_ref.rsplit(":", 1)[1]: e for e in db.scalars(select(Evaluation))}
    assert len(stored) == 15
    for r in m.ratings:  # the stored score is exactly the legacy total
        assert stored[str(r.row)].final_score == pytest.approx(r.legacy_total, abs=0.01)
        assert stored[str(r.row)].origin == "import" and stored[str(r.row)].status == "completed"


@pytest.fixture()
def messy(db):
    return mig.plan(db, files("training-session-quality.xlsx"))


def test_M01_weights(messy):
    by_name = {k.name: k for k in messy.kpis}
    assert by_name["Accuracy"].weight == 3 and "[M01]" in by_name["Accuracy"].outcome.messages[0]
    assert by_name["Engagement"].weight == 1 and by_name["Engagement"].outcome.status == "warning"


def test_hierarchy_from_numbering_and_summary_rows_skipped(messy):
    tree = messy.definition.version.parameters
    assert [(p.code, [c.code for c in p.children]) for p in tree] == [
        ("1", ["1.1", "1.2"]), ("2", ["2.1", "2.2", "2.3"]), ("3", ["3.1"])]
    assert not any(k.name.lower() == "total" for k in messy.kpis)
    assert not any(r.subject.lower() == "average" for r in messy.ratings)


def test_M02_na_in_history_marks_optional(messy):
    venue = next(k for k in messy.kpis if k.name == "Venue & equipment")
    assert venue.optional
    git = next(r for r in messy.ratings if r.subject == "Workshop: Git")
    assert git.values["3.1"] == "NA" and git.complete


def test_M03_missing_evaluator_and_bad_date(messy):
    assert any("[M03]" in x for x in row(messy, 21).messages)
    assert any("[M302]" in x for x in row(messy, 22).messages)


def test_M04_duplicates_conflicts_and_attempts(messy):
    assert row(messy, 24).status == "rejected"  # exact duplicate
    assert row(messy, 25).status == row(messy, 26).status == "rejected"  # conflicting
    kafka = sorted((r for r in messy.ratings if r.subject == "Workshop: Kafka"), key=lambda r: r.row)
    assert [r.attempt_no for r in kafka] == [1, 2]


def test_M05_text_target_mapped(messy):
    assert messy.definition.version.target_score == 8
    assert any("[M05]" in n and "good" in n for n in messy.notes)


def test_M06_guideline_gaps_get_placeholders_and_merges(messy):
    clarity = next(p for p in messy.definition.version.parameters[1].children if p.code == "2.1")
    assert any(c.qualitative == mig.PLACEHOLDER and (c.score_min, c.score_max) == (4, 5) for c in clarity.criteria)
    relevance = messy.definition.version.parameters[0].children[0]
    assert (relevance.criteria[0].score_min, relevance.criteria[0].score_max) == (9, 10)  # 10 & 9 merged
    assert "needs-guidelines" in messy.definition.tags
    assert not [i for i in messy.issues if i["severity"] == "error"]


def test_cell_level_problems(messy):
    sql = next(r for r in messy.ratings if r.subject == "Workshop: SQL")
    assert sql.values["2.3"] == 7 and any("[M305]" in x for x in sql.outcome.messages)  # 7.5 -> 7, never up
    cloud = next(r for r in messy.ratings if r.subject == "Workshop: Cloud")
    assert cloud.values["2.1"] is None and not cloud.complete  # 12 out of scale -> draft
    testing = next(r for r in messy.ratings if r.subject == "Workshop: Testing")
    assert any("[M303]" in x for x in testing.outcome.messages)
    assert row(messy, 29).status == "rejected" and "[M301]" in row(messy, 29).messages[0]
    assert row(messy, 30).status == "rejected" and "[M306]" in row(messy, 30).messages[0]


def test_every_difference_is_explained(messy):
    rec = messy.to_dict()["reconciliation"]
    assert rec["rows_with_legacy_total"] == 21 and rec["mismatched_unexplained"] == 0


def test_every_source_row_has_exactly_one_state(messy):
    assert all(r.status in {"imported", "warning", "rejected"} for r in messy.rows)
    rating_rows = [r for r in messy.rows if r.kind == "rating"]
    assert len(rating_rows) == 29  # 29 data rows in the feedback log (summary row excluded)


def test_commit_messy_imports_drafts_and_completed(db, messy):
    mig.commit(db, messy)
    evs = list(db.scalars(select(Evaluation)))
    assert len(evs) == 24
    assert {e.status for e in evs} == {"completed", "draft"}
    assert sum(e.status == "draft" for e in evs) == 3


def test_csv_pair_generates_codes_and_creates_subject_type(db):
    m = mig.plan(db, files("vendor-assessment.csv", "vendor-assessment-ratings.csv"))
    assert not m.fatal and m.scale_code == "0-100-pct"
    codes = [(p.code, [c.code for c in p.children]) for p in m.definition.version.parameters]
    assert codes == [("1", ["1.1", "1.2"]), ("2", ["2.1", "2.2"]), ("3", ["3.1", "3.2"])]
    assert [c.is_critical for c in m.definition.version.parameters[1].children] == [True, True]
    assert all(r.complete for r in m.ratings) and len(m.ratings) == 6
    mig.commit(db, m)
    assert db.scalar(select(SubjectType).where(SubjectType.code == "vendor"))


def test_unknown_scale_needs_rescale(db):
    m = mig.plan(db, files("meeting-effectiveness-7pt.xlsx"))
    assert m.fatal and "[M007]" in m.fatal[0]


def test_rescale_is_contiguous_and_preserves_verdicts(db):
    m = mig.plan(db, files("meeting-effectiveness-7pt.xlsx"), mig.MigrationOptions(rescale_to="0-10-rag"))
    assert not m.fatal
    for p in m.definition.version.parameters:
        covered = sorted(s for c in p.criteria for s in range(c.score_min, c.score_max + 1))
        assert covered == list(range(0, 11))
    legacy_target, target = 5, m.definition.version.target_score
    for v in range(1, 8):
        assert (v >= legacy_target) == (m.map_score(v) >= target)
    assert m.ratings and all(r.subject.startswith("Weekly sync") for r in m.ratings)  # subject column inferred


@pytest.mark.parametrize("name,code", [("broken-no-header.xlsx", "[M002]"), ("corrupt.xlsx", "[M001]")])
def test_unusable_files_fail_fast(db, name, code):
    m = mig.plan(db, files(name))
    assert m.fatal and m.fatal[0].startswith(code)
    with pytest.raises(Exception) as e:
        mig.commit(db, m)
    assert getattr(e.value, "code", None) == "M900"


def test_preview_writes_nothing_and_recommit_gets_new_code(db):
    before = db.scalar(select(func.count(Scorecard.id)))
    m = mig.plan(db, files("code-review-quality.xlsx"))
    assert db.scalar(select(func.count(Scorecard.id))) == before
    mig.commit(db, m)
    m2 = mig.plan(db, files("code-review-quality.xlsx"))
    assert m2.definition.code == "code-review-quality-2"


def test_api_preview_and_commit(client):
    up = [("files", ("vendor-assessment.csv", (LEGACY / "vendor-assessment.csv").read_bytes(), "text/csv")),
          ("files", ("r.csv", (LEGACY / "vendor-assessment-ratings.csv").read_bytes(), "text/csv"))]
    r = client.post("/api/migrations/preview", files=up)
    assert r.status_code == 200 and r.json()["status"] == "ok_with_warnings" and not r.json()["committed"]
    assert client.get("/api/scorecards").json() == []
    r = client.post("/api/migrations/commit", files=up, data={"subject_type": "vendor"})
    assert r.status_code == 200 and r.json()["committed"]
    sid = r.json()["scorecard_id"]
    assert client.get(f"/api/scorecards/{sid}").json()["evaluation_count"] == 6
    bad = client.post("/api/migrations/commit", files=[("files", ("x.xlsx", b"junk", "application/octet-stream"))])
    assert bad.status_code == 422 and bad.json()["code"] == "M900"


from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

_CSV_CELLS = st.one_of(st.text(max_size=12), st.sampled_from(["KPI", "Weight", "Scale: 0-10", "Target: 8", "N/A", "10",
                                                              "1.1", "-", "x", "Subject", "Total", "", "1e309", "nan"]))


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(st.lists(_CSV_CELLS, max_size=8), max_size=25))
def test_arbitrary_csv_never_crashes(db, rows):
    import csv as _csv
    import io as _io

    buf = _io.StringIO()
    _csv.writer(buf).writerows(rows)
    m = mig.plan(db, [("fuzz.csv", buf.getvalue().encode())])
    d = m.to_dict()  # the report must always be producible
    assert d["status"] in {"ok", "ok_with_warnings", "failed"}


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.integers(0, 6000))
def test_truncated_workbook_fails_cleanly(db, cut):
    data = (LEGACY / "training-session-quality.xlsx").read_bytes()[:cut]
    m = mig.plan(db, [("t.xlsx", data)])
    assert m.fatal and m.fatal[0].startswith("[M001]")
