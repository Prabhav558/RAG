"""Cycle 2 · §8.2 — buggy and invalid scenario datasets.

Every case takes valid seed data, injects exactly ONE defect, sends it through the real API and classifies the
outcome. Each case is traceable: case id -> scenario -> defect type -> expected rejection code.

Outcomes
  PASS        rejected with an expected code (or accepted, for positive controls)
  WRONG_CODE  rejected, but with a different code than documented
  ACCEPTED    the defect got in (a hole in validation)
  CRASH       HTTP 5xx / unhandled exception (the worst outcome)

    python data/tools/corrupt.py                      # prints summary, writes docs/cycle2/corruption_report.md
"""

from __future__ import annotations

import copy
import io
import json
import os
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

CONTRACT = "CONTRACT"  # request rejected by the schema contract (HTTP 422 from pydantic)
ACCEPT = "ACCEPT"  # positive control: must be accepted


@dataclass
class Case:
    id: str
    area: str  # definition | publish | scale | evaluation | upload | request
    defect: str  # defect type
    description: str
    expected: set[str]
    run: Callable[["Ctx"], "Response"]
    scenario: str = ""


@dataclass
class Response:
    status: int
    codes: set[str]
    body: object = None


@dataclass
class Ctx:
    client: object
    seeds: dict = field(default_factory=dict)  # code -> definition json
    published: dict = field(default_factory=dict)  # code -> version view

    def req(self, method: str, url: str, **kw) -> Response:
        r = self.client.request(method, url, **kw)
        try:
            body = r.json()
        except Exception:  # noqa: BLE001 - non-JSON body (e.g. plain 500)
            body = r.text
        codes: set[str] = set()
        if isinstance(body, dict):
            if "code" in body:
                codes.add(body["code"])
                for d in body.get("details") or []:
                    if isinstance(d, dict) and "code" in d:
                        codes.add(d["code"])
            elif r.status_code == 422 and "detail" in body:
                codes.add(CONTRACT)
        return Response(r.status_code, codes, body)

    # ---- helpers
    counter: int = 0

    def seed(self, code="assessment-quality") -> dict:
        self.counter += 1
        d = copy.deepcopy(self.seeds[code])
        d["code"] = f"{code}-c{self.counter}"
        return d

    def create_and_publish(self, d: dict) -> Response:
        r = self.req("POST", "/api/scorecards", json=d)
        if r.status >= 300:
            return r
        vid = r.body["versions"][0]["id"]
        return self.req("POST", f"/api/versions/{vid}/publish")

    def version(self, code="assessment-quality") -> dict:
        return self.published[code]

    def new_eval(self, code="assessment-quality", **kw) -> dict:
        body = {"version_id": self.version(code)["id"], "subject_name": "Corruption target", **kw}
        r = self.req("POST", "/api/evaluations", json=body)
        assert r.status == 201, r.body
        return r.body

    def leaves(self, code="assessment-quality") -> list[dict]:
        out = []

        def walk(ns):
            for n in ns:
                out.append(n) if n["is_leaf"] else walk(n["children"])

        walk(self.version(code)["parameters"])
        return out

    def leaf(self, code="assessment-quality", with_metrics=None, optional=None) -> dict:
        for n in self.leaves(code):
            if with_metrics is not None and bool(n["metrics"]) != with_metrics:
                continue
            if optional is not None and n["is_optional"] != optional:
                continue
            return n
        raise LookupError("no such leaf")

    def put(self, ev: dict, body: dict) -> Response:
        return self.req("PUT", f"/api/evaluations/{ev['id']}", json=body)

    def raw(self, method: str, url: str, text: str) -> Response:
        return self.req(method, url, content=text, headers={"Content-Type": "application/json"})


# ---------------------------------------------------------------- mutation helpers


def first_leaf(params: list[dict]) -> dict:
    p = params[0]
    while p.get("children"):
        p = p["children"][0]
    return p


def first_metric_leaf(params: list[dict]) -> dict:
    stack = list(params)
    while stack:
        p = stack.pop(0)
        if p.get("metrics"):
            return p
        stack = p.get("children", []) + stack
    raise LookupError


def mut(ctx: Ctx, fn, code="assessment-quality", publish=True) -> Response:
    d = ctx.seed(code)
    fn(d)
    return ctx.create_and_publish(d) if publish else ctx.req("POST", "/api/scorecards", json=d)


def raw_definition(ctx: Ctx, fn) -> Response:
    """Mutate at the JSON-text level (NaN / Infinity cannot be produced by json.dumps(allow_nan=False))."""
    d = ctx.seed()
    text = fn(json.dumps(d))
    r = ctx.raw("POST", "/api/scorecards", text)
    if r.status >= 300:
        return r
    return ctx.req("POST", f"/api/versions/{r.body['versions'][0]['id']}/publish")


def docx_bytes(xml: str | None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if xml is not None:
            z.writestr("word/document.xml", xml)
        else:
            z.writestr("other.txt", "x")
    return buf.getvalue()


def upload(ctx: Ctx, name: str, data: bytes, ev: dict | None = None) -> Response:
    ev = ev or ctx.new_eval()
    return ctx.req("POST", f"/api/evaluations/{ev['id']}/documents", files={"file": (name, data, "application/octet-stream")})


def completed_eval(ctx: Ctx) -> dict:
    ev = ctx.new_eval("client-email")
    ratings = [{"parameter_id": n["id"], "judged_score": 9} for n in ctx.leaves("client-email")]
    ctx.put(ev, {"ratings": ratings})
    ctx.req("POST", f"/api/evaluations/{ev['id']}/complete")
    return ev


def rating(ctx: Ctx, leaf: dict, **kw) -> dict:
    return {"ratings": [{"parameter_id": leaf["id"], **kw}]}


def metric_value(ctx: Ctx, data_type: str, value) -> Response:
    for n in ctx.leaves():
        for m in n["metrics"]:
            if m["data_type"] == data_type:
                return ctx.put(ctx.new_eval(), {"metric_values": [{"metric_id": m["id"], "value": value}]})
    raise LookupError(data_type)


def scale(ctx: Ctx, **over) -> Response:
    body = {
        "code": f"scale-{len(ctx.published)}-{abs(hash(json.dumps(over, sort_keys=True))) % 10**8}",
        "name": "Corrupt scale",
        "min_value": 0,
        "max_value": 4,
        "bands": [
            {"label": "Top", "lower_bound": 3, "color_hex": "#00B050", "font_hex": "#FFFFFF", "rag": "GREEN"},
            {"label": "Low", "lower_bound": 0, "color_hex": "#C00000", "font_hex": "#FFFFFF", "rag": "RED"},
        ],
    }
    for k, v in over.items():
        if k.startswith("band0_"):
            body["bands"][0][k[6:]] = v
        else:
            body[k] = v
    return ctx.req("POST", "/api/meta/scales", json=body)


# ---------------------------------------------------------------- the catalogue

def cases() -> list[Case]:
    C = Case
    L = lambda d: first_leaf(d["version"]["parameters"])  # noqa: E731
    ML = lambda d: first_metric_leaf(d["version"]["parameters"])  # noqa: E731
    P = lambda d: d["version"]["parameters"]  # noqa: E731
    return [
        # ---------------- definitions: missing references
        C("D01", "definition", "missing reference", "Unknown rating scale code", {"E008"},
          lambda c: mut(c, lambda d: d["version"].update(rating_scale="0-7-unknown"), publish=False)),
        C("D02", "definition", "missing reference", "Unknown subject type", {"E008"},
          lambda c: mut(c, lambda d: d.update(subject_type="spaceship"), publish=False)),
        # ---------------- definitions: invalid values
        C("D03", "publish", "inverted range", "Criterion score_min > score_max", {"V007", CONTRACT},
          lambda c: mut(c, lambda d: L(d)["criteria"][0].update(score_min=10, score_max=8))),
        C("D04", "publish", "out of range", "Criterion beyond scale max", {"V007"},
          lambda c: mut(c, lambda d: L(d)["criteria"][0].update(score_max=11))),
        C("D05", "publish", "overlap", "Metric thresholds overlap", {"V009"},
          lambda c: mut(c, lambda d: ML(d)["metrics"][0]["thresholds"][1].update(max_value=1e6))),
        C("D06", "publish", "empty interval", "Threshold with min == max", {"V009"},
          lambda c: mut(c, lambda d: ML(d)["metrics"][0]["thresholds"].append({"min_value": 5, "max_value": 5, "score": 5}))),
        C("D07", "publish", "out of range", "Threshold score outside scale", {"V010"},
          lambda c: mut(c, lambda d: ML(d)["metrics"][0]["thresholds"][0].update(score=42))),
        C("D08", "definition", "duplicate identity", "Nested parameter reuses a root code", {"V015"},
          lambda c: mut(c, lambda d: L(d).update(code="2"), publish=False)),
        C("D09", "publish", "duplicate identity", "Two metrics with the same code on one leaf", {"V015"},
          lambda c: mut(c, lambda d: ML(d)["metrics"].append(copy.deepcopy(ML(d)["metrics"][0])))),
        C("D10", "publish", "structure", "Tree deeper than max_depth", {"V002"},
          lambda c: mut(c, lambda d: d["version"].update(max_depth=2))),
        C("D11", "definition", "non-finite number", "Target score NaN", {CONTRACT},
          lambda c: raw_definition(c, lambda t: t.replace('"target_score": 8', '"target_score": NaN'))),
        C("D12", "definition", "non-finite number", "Weight Infinity", {CONTRACT},
          lambda c: raw_definition(c, lambda t: t.replace('"weight": 20', '"weight": Infinity', 1))),
        C("D13", "definition", "overflow", "Sibling weights of 1e308 (sum overflows to inf)", {CONTRACT},
          lambda c: mut(c, lambda d: [p.update(weight=1e308) for p in P(d)], publish=False)),
        C("D14", "definition", "missing value", "Empty scorecard name", {CONTRACT},
          lambda c: mut(c, lambda d: d.update(name=""), publish=False)),
        C("D15", "definition", "oversized", "10,000-char parameter name", {CONTRACT},
          lambda c: mut(c, lambda d: L(d).update(name="x" * 10_000), publish=False)),
        C("D16", "definition", "oversized", "2 MB purpose text", {CONTRACT},
          lambda c: mut(c, lambda d: d["version"].update(purpose="p" * 2_000_000), publish=False)),
        C("D17", "definition", "wrong type", "Weight given as text", {CONTRACT},
          lambda c: mut(c, lambda d: P(d)[0].update(weight="heavy"), publish=False)),
        C("D18", "definition", "wrong type", "parameters is an object, not a list", {CONTRACT},
          lambda c: mut(c, lambda d: d["version"].update(parameters={"a": 1}), publish=False)),
        C("D19", "definition", "missing field", "No version block", {CONTRACT},
          lambda c: mut(c, lambda d: d.pop("version"), publish=False)),
        C("D20", "definition", "malformed identity", "Scorecard code with spaces and capitals", {CONTRACT},
          lambda c: mut(c, lambda d: d.update(code="Assessment Quality"), publish=False)),
        C("D21", "publish", "structure", "Metric attached to a parent parameter", {"V017"},
          lambda c: mut(c, lambda d: P(d)[0].update(metrics=[{"code": "m", "name": "m", "thresholds": [{"score": 5}]}]))),
        C("D22", "publish", "invalid value", "All top-level weights zero", {"V003"},
          lambda c: mut(c, lambda d: [p.update(weight=0) for p in P(d)])),
        C("D23", "publish", "missing value", "Whitespace-only qualitative guideline", {"V019"},
          lambda c: mut(c, lambda d: L(d)["criteria"][0].update(qualitative="   "))),
        C("D24", "publish", "out of range", "Gate floor outside scale", {"V014"},
          lambda c: mut(c, lambda d: L(d).update(is_critical=True, min_acceptable_score=12))),
        C("D25", "definition", "volume abuse", "5,000 leaf parameters", {"V020", CONTRACT},
          lambda c: mut(c, lambda d: d["version"].update(parameters=[
              {"code": f"p{i}", "name": f"p{i}", "criteria": [{"score_min": 0, "score_max": 10, "qualitative": "q"}]}
              for i in range(5000)]), publish=False)),
        C("D26", "definition", "out of range", "max_depth 0", {CONTRACT},
          lambda c: mut(c, lambda d: d["version"].update(max_depth=0), publish=False)),
        C("D27", "publish", "overlap", "Unbounded threshold overlapping all others", {"V009"},
          lambda c: mut(c, lambda d: ML(d)["metrics"][0]["thresholds"].append({"min_value": None, "max_value": None, "score": 5}))),
        C("D28", "publish", "invalid value", "Target outside scale", {"V012"},
          lambda c: mut(c, lambda d: d["version"].update(target_score=-1))),
        C("D29", "request", "malformed payload", "Truncated JSON body", {CONTRACT},
          lambda c: c.raw("POST", "/api/scorecards", '{"code": "x", "name": ')),
        # ---------------- rating scales
        C("D40", "scale", "duplicate identity", "Two bands with the same lower bound", {"V013"},
          lambda c: scale(c, band0_lower_bound=0)),
        C("D41", "scale", "inverted range", "Scale min > max", {"V013", CONTRACT},
          lambda c: scale(c, min_value=10, max_value=0)),
        C("D42", "scale", "malformed value", "Band colour 'red' is not a hex colour", {CONTRACT},
          lambda c: scale(c, band0_color_hex="red")),
        C("D43", "scale", "malformed value", "Band RAG status 'BLUE'", {CONTRACT},
          lambda c: scale(c, band0_rag="BLUE")),
        C("D44", "scale", "out of range", "Band lower bound above scale max", {"V013"},
          lambda c: scale(c, band0_lower_bound=99)),
        # ---------------- evaluations
        C("D50", "evaluation", "missing reference", "Evaluation on non-existent version", {"E404"},
          lambda c: c.req("POST", "/api/evaluations", json={"version_id": 999999, "subject_name": "x"})),
        C("D51", "evaluation", "lifecycle", "Evaluation on a draft version", {"E001"},
          lambda c: c.req("POST", "/api/evaluations", json={
              "version_id": mut(c, lambda d: None, publish=False).body["versions"][0]["id"], "subject_name": "x"})),
        C("D52", "evaluation", "non-finite number", "Judged score NaN", {CONTRACT},
          lambda c: c.raw("PUT", f"/api/evaluations/{c.new_eval()['id']}",
                          '{"ratings": [{"parameter_id": %d, "judged_score": NaN}]}' % c.leaf()["id"])),
        C("D53", "evaluation", "non-finite number", "Judged score Infinity", {CONTRACT},
          lambda c: c.raw("PUT", f"/api/evaluations/{c.new_eval()['id']}",
                          '{"ratings": [{"parameter_id": %d, "judged_score": Infinity}]}' % c.leaf()["id"])),
        C("D54", "evaluation", "out of range", "Judged score 11 on 0–10", {"E002"},
          lambda c: c.put(c.new_eval(), rating(c, c.leaf(), judged_score=11))),
        C("D55", "evaluation", "out of range", "Negative judged score", {"E002"},
          lambda c: c.put(c.new_eval(), rating(c, c.leaf(), judged_score=-3))),
        C("D56", "evaluation", "wrong precision", "Judged score 7.5", {"E012"},
          lambda c: c.put(c.new_eval(), rating(c, c.leaf(), judged_score=7.5))),
        C("D57", "evaluation", "referential", "Rating a parameter of another scorecard", {"E008"},
          lambda c: c.put(c.new_eval(), rating(c, c.leaf("client-email"), judged_score=5))),
        C("D58", "evaluation", "missing reference", "Rating a non-existent parameter", {"E008"},
          lambda c: c.put(c.new_eval(), {"ratings": [{"parameter_id": 999999, "judged_score": 5}]})),
        C("D59", "evaluation", "structure", "Rating a parent parameter", {"E003"},
          lambda c: c.put(c.new_eval(), {"ratings": [{"parameter_id": c.version()["parameters"][0]["id"], "judged_score": 5}]})),
        C("D60", "evaluation", "rule", "N/A on a required parameter", {"E004"},
          lambda c: c.put(c.new_eval(), rating(c, c.leaf(optional=False), not_applicable=True))),
        C("D61", "evaluation", "rule", "Override reason without a score", {"E010"},
          lambda c: c.put(c.new_eval(), rating(c, c.leaf(), override_reason="because"))),
        C("D62", "evaluation", "duplicate identity", "Same parameter rated twice in one request", {"E016"},
          lambda c: c.put(c.new_eval(), {"ratings": [{"parameter_id": c.leaf()["id"], "judged_score": 3},
                                                     {"parameter_id": c.leaf()["id"], "judged_score": 9}]})),
        C("D63", "evaluation", "out of range", "Percent metric value 150", {"E013"},
          lambda c: metric_value(c, "percent", 150)),
        C("D64", "evaluation", "wrong precision", "Count metric value 2.5", {"E013"},
          lambda c: metric_value(c, "count", 2.5)),
        C("D65", "evaluation", "out of range", "Negative count", {"E013"},
          lambda c: metric_value(c, "count", -1)),
        C("D66", "evaluation", "referential", "Metric of another scorecard", {"E008"},
          lambda c: c.put(c.new_eval("client-email"), {"metric_values": [{"metric_id": c.leaf(with_metrics=True)["metrics"][0]["id"], "value": 1}]})),
        C("D67", "evaluation", "non-finite number", "Metric value NaN", {CONTRACT},
          lambda c: c.raw("PUT", f"/api/evaluations/{c.new_eval()['id']}",
                          '{"metric_values": [{"metric_id": %d, "value": NaN}]}' % c.leaf(with_metrics=True)["metrics"][0]["id"])),
        C("D68", "evaluation", "lifecycle", "Completing with unrated parameters", {"E005"},
          lambda c: c.req("POST", f"/api/evaluations/{c.new_eval()['id']}/complete")),
        C("D69", "evaluation", "lifecycle", "Completing a QTC evaluation without time/cost", {"E007"},
          lambda c: (lambda ev: (c.put(ev, {"ratings": [{"parameter_id": n["id"], "judged_score": 9} for n in c.leaves("milestone-delivery")]}),
                                 c.req("POST", f"/api/evaluations/{ev['id']}/complete"))[1])(c.new_eval("milestone-delivery"))),
        C("D70", "evaluation", "lifecycle", "Editing a completed evaluation", {"E006"},
          lambda c: c.put(completed_eval(c), rating(c, c.leaf("client-email"), judged_score=1))),
        C("D71", "evaluation", "lifecycle", "Voiding twice", {"E006"},
          lambda c: (lambda ev: (c.req("POST", f"/api/evaluations/{ev['id']}/void", json={"reason": "dup"}),
                                 c.req("POST", f"/api/evaluations/{ev['id']}/void", json={"reason": "dup"}))[1])(c.new_eval())),
        C("D72", "evaluation", "out of range", "Context target outside scale", {"V012"},
          lambda c: c.req("POST", "/api/evaluations", json={"version_id": c.version()["id"], "subject_name": "x", "target_score": 50})),
        C("D73", "evaluation", "missing value", "Empty subject name", {CONTRACT},
          lambda c: c.req("POST", "/api/evaluations", json={"version_id": c.version()["id"], "subject_name": ""})),
        C("D74", "evaluation", "oversized", "5 MB rationale", {CONTRACT},
          lambda c: c.put(c.new_eval(), rating(c, c.leaf(), judged_score=5, rationale="r" * 5_000_000))),
        C("D75", "evaluation", "invalid enum", "Evaluator type 'robot'", {CONTRACT},
          lambda c: c.req("POST", "/api/evaluations", json={"version_id": c.version()["id"], "subject_name": "x", "evaluator_type": "robot"})),
        C("D76", "evaluation", "out of range", "Confidence 1.5", {CONTRACT},
          lambda c: c.put(c.new_eval(), rating(c, c.leaf(), judged_score=5, confidence=1.5))),
        C("D77", "evaluation", "out of range", "Attempt number 0", {CONTRACT},
          lambda c: c.req("POST", "/api/evaluations", json={"version_id": c.version()["id"], "subject_name": "x", "attempt_no": 0})),
        C("D78", "evaluation", "missing reference", "Update a non-existent evaluation", {"E404"},
          lambda c: c.req("PUT", "/api/evaluations/999999", json={})),
        C("D79", "evaluation", "oversized", "5 MB pasted input text", {CONTRACT},
          lambda c: c.req("POST", "/api/evaluations", json={"version_id": c.version()["id"], "subject_name": "x", "input_text": "i" * 5_000_000})),
        # ---------------- documents
        C("D80", "upload", "corrupt file", "Random bytes named .docx", {"E015"},
          lambda c: upload(c, "a.docx", os.urandom(2048))),
        C("D81", "upload", "corrupt file", "DOCX zip without word/document.xml", {"E015"},
          lambda c: upload(c, "a.docx", docx_bytes(None))),
        C("D82", "upload", "corrupt file", "Random bytes named .pdf", {"E015"},
          lambda c: upload(c, "a.pdf", b"%PDF-1.4\n" + os.urandom(2048))),
        C("D83", "upload", "wrong format", "Binary file", {"E015"},
          lambda c: upload(c, "a.bin", bytes(range(256)) * 8)),
        C("D84", "upload", "missing value", "Empty file", {"E015"},
          lambda c: upload(c, "a.txt", b"")),
        C("D85", "upload", "oversized", "Text over the 400k-char limit", {"E015"},
          lambda c: upload(c, "a.txt", b"x" * 400_001)),
        C("D86", "upload", "lifecycle", "Upload to a completed evaluation", {"E006"},
          lambda c: upload(c, "a.txt", b"hello", completed_eval(c))),
        C("D87", "upload", "truncated file", "DOCX with malformed XML", {"E015", ACCEPT},
          lambda c: upload(c, "a.docx", docx_bytes("<w:document><w:p><w:t>unclosed"))),
        # ---------------- positive controls (must be accepted)
        C("P01", "definition", "positive control", "Unicode, emoji and RTL text in names", {ACCEPT},
          lambda c: mut(c, lambda d: (d.update(name="Qualité 評価 ✅ تقييم"), L(d).update(name="Clarté ✨ وضوح")))),
        C("P02", "definition", "positive control", "Fractional weights (0.001)", {ACCEPT},
          lambda c: mut(c, lambda d: [p.update(weight=0.001) for p in P(d)])),
        C("P03", "evaluation", "positive control", "Clearing a metric value with null", {ACCEPT},
          lambda c: c.put(c.new_eval(), {"metric_values": [{"metric_id": c.leaf(with_metrics=True)["metrics"][0]["id"], "value": None}]})),
        C("P04", "upload", "positive control", "UTF-8 markdown with non-Latin text", {ACCEPT},
          lambda c: upload(c, "a.md", "# Évaluation\n質問 1".encode())),
    ]


def classify(case: Case, r: Response) -> str:
    if r.status >= 500:
        return "CRASH"
    if ACCEPT in case.expected and r.status < 300:
        return "PASS"
    if r.status < 300:
        return "ACCEPTED"
    return "PASS" if r.codes & case.expected else "WRONG_CODE"


def run_all(client=None) -> list[dict]:
    """Run every case against a fresh database. Returns one row per case."""
    own = client is None
    if own:
        tmp = tempfile.mkdtemp()
        os.environ["SCORECARD_DB_URL"] = f"sqlite:///{tmp}/corrupt.db"
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
    ctx = Ctx(client)
    for f in sorted((ROOT / "data" / "scorecards").glob("*.json")):
        d = json.loads(f.read_text())
        ctx.seeds[d["code"]] = d
        r = ctx.req("POST", "/api/scorecards?publish=true", json=d)
        if r.status == 409:  # already there (shared test database)
            r = ctx.req("GET", "/api/scorecards")
            card = next(x for x in r.body if x["code"] == d["code"])
        else:
            card = r.body
        vid = next(v["id"] for v in card["versions"] if v["status"] == "published")
        ctx.published[d["code"]] = ctx.req("GET", f"/api/versions/{vid}").body

    rows = []
    for case in cases():
        try:
            r = case.run(ctx)
            outcome = classify(case, r)
            got = sorted(r.codes) or [str(r.status)]
        except Exception as e:  # noqa: BLE001 - a crash in the harness path is itself a finding
            outcome, got, r = "CRASH", [type(e).__name__], None
        rows.append({"id": case.id, "area": case.area, "defect": case.defect, "description": case.description,
                     "expected": sorted(case.expected), "got": got, "status": r.status if r else None,
                     "outcome": outcome})
    if own:
        client.__exit__(None, None, None)
    return rows


def report(rows: list[dict]) -> str:
    from collections import Counter

    counts = Counter(r["outcome"] for r in rows)
    lines = [
        "# Corruption Report (Cycle 2 · §8.2)",
        "",
        "Generated by `python data/tools/corrupt.py`. Each case injects one defect into valid seed data and sends it "
        "through the real API.",
        "",
        "| Outcome | Cases |",
        "|---|---|",
        *[f"| {k} | {counts.get(k, 0)} |" for k in ("PASS", "WRONG_CODE", "ACCEPTED", "CRASH")],
        "",
        "| Case | Area | Defect type | Injected defect | Expected | Got | Outcome |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['id']} | {r['area']} | {r['defect']} | {r['description']} | {', '.join(r['expected'])} | "
                     f"{', '.join(r['got'])} | {'✅' if r['outcome'] == 'PASS' else '❌ ' + r['outcome']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = run_all()
    for r in rows:
        if r["outcome"] != "PASS":
            print(f"{r['outcome']:<10} {r['id']} {r['description']} — expected {r['expected']} got {r['got']} ({r['status']})")
    out = ROOT / "docs" / "cycle2" / "corruption_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(rows))
    bad = sum(r["outcome"] != "PASS" for r in rows)
    print(f"{len(rows)} cases, {len(rows) - bad} pass, {bad} fail -> {out.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
