"""Cycle 2 · §8.3 — migrate legacy spreadsheet scorecards (and their historical ratings).

Pipeline: load (xlsx / csv) -> locate metadata, header and columns -> stage KPI rows and rating rows ->
map to the target model (scale, target, hierarchy, rating matrix) -> validate -> reconcile -> commit.

Every source row ends in exactly one state: imported | warning (imported with a note) | rejected (with reason).
`preview` never writes; `commit` writes through app.services, so imported data obeys every normal rule.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import scoring
from . import services as svc
from .models import RatingScale, Scorecard, SubjectType
from .schemas import (
    NAME_MAX,
    WEIGHT_MAX,
    CriterionIn,
    EvaluationCreate,
    EvaluationUpdate,
    ParameterIn,
    RatingIn,
    ScorecardDefinition,
    VersionIn,
)
from .validation import has_errors, structural_errors, validate_version

# ---------------------------------------------------------------- vocabulary

SYN = {
    "code": {"no", "#", "sno", "s no", "sr no", "sl no", "code", "id", "ref", "kpi no", "kpi id", "number"},
    "name": {"kpi", "kpis", "parameter", "parameters", "criteria", "criterion", "kpi name", "parameter name", "area",
             "metric", "dimension", "attribute", "question"},
    "weight": {"weight", "weightage", "weight %", "weight pct", "wt", "weighting", "weight percent"},
    "description": {"description", "definition", "details", "what is measured", "notes on kpi"},
    "critical": {"critical", "mandatory", "gate", "must pass", "knockout"},
}
RATING_SYN = {
    "subject": {"subject", "name", "candidate", "item", "task", "project", "document", "assessment", "vendor", "team",
                "employee", "pr", "pull request", "session", "title"},
    "ref": {"ref", "id", "reference", "subject id", "key"},
    "evaluator": {"evaluator", "assessor", "reviewer", "rated by", "judge", "scored by", "rater"},
    "date": {"date", "rated on", "review date", "evaluated on", "when"},
    "comments": {"comments", "comment", "remarks", "notes", "feedback", "summary"},
    "total": {"total", "overall", "final score", "score", "total score", "weighted score", "result"},
}
META = {
    "name": {"scorecard", "scorecard name", "name", "title"},
    "purpose": {"purpose", "why", "aim"},
    "scope": {"scope"},
    "objective": {"objective", "objectives", "goal", "quality objective"},
    "scale": {"scale", "rating scale", "scoring scale"},
    "target": {"target", "target score", "pass mark", "threshold"},
    "subject_type": {"subject", "subject type", "applies to", "type"},
    "owner": {"owner", "author", "prepared by"},
}
NA_TOKENS = {"na", "n/a", "n.a.", "not applicable", "-", "—", "nil"}
TARGET_WORDS = {"excellent": 0.9, "very good": 0.85, "good": 0.8, "acceptable": 0.7, "satisfactory": 0.7,
                "average": 0.5, "fair": 0.5}
WEIGHT_WORDS = {"high": 3.0, "medium": 2.0, "med": 2.0, "low": 1.0}
SUMMARY_ROW = re.compile(r"^(total|average|avg|mean|overall|sum)\b", re.I)
GUIDE_HDR = re.compile(r"^(?:score|rating|level|grade|points?)?\s*(\d{1,3})(?:\s*(?:-|–|to)\s*(\d{1,3}))?(?:\b|$)", re.I)
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%b %d %Y",
                "%Y/%m/%d"]
PLACEHOLDER = "[Migrated: the source had no guideline for this score. Define one before relying on it.]"


def norm(v: Any) -> str:
    s = str(v if v is not None else "").strip().lower()
    s = re.sub(r"[()\[\]:*_]", " ", s)
    s = s.replace(".", " ") if not re.match(r"^\d+(\.\d+)*$", s) else s
    return re.sub(r"\s+", " ", s).strip()


def blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def slug(s: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50].strip("-")
    return out if len(out) >= 2 else f"imported-{out or 'scorecard'}"


# ---------------------------------------------------------------- source model


@dataclass
class Cell:
    value: Any
    indent: int = 0
    formula_without_value: bool = False


@dataclass
class Sheet:
    name: str
    rows: list[list[Cell]]


def load_sheets(filename: str, data: bytes) -> list[Sheet]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        return _load_xlsx(data)
    if name.endswith((".csv", ".tsv", ".txt")):
        return [_load_csv(filename, data)]
    raise svc.DomainError("M001", f"Unsupported file type '{filename}': use .xlsx or .csv")


def _load_xlsx(data: bytes) -> list[Sheet]:
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover
        raise svc.DomainError("M001", "Excel import needs the 'openpyxl' package") from e
    try:
        wb_v = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        wb_f = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
    except Exception as e:  # noqa: BLE001 - any parser failure means a corrupt workbook
        raise svc.DomainError("M001", "The workbook is corrupt or not an .xlsx file") from e
    sheets = []
    for ws_v in wb_v.worksheets:
        ws_f = wb_f[ws_v.title]
        rows = []
        for r_v, r_f in zip(ws_v.iter_rows(), ws_f.iter_rows()):
            row = []
            for c_v, c_f in zip(r_v, r_f):
                indent = int(getattr(c_v.alignment, "indent", 0) or 0) if c_v.has_style else 0
                is_formula = isinstance(c_f.value, str) and c_f.value.startswith("=")
                row.append(Cell(c_v.value, indent, is_formula and c_v.value is None))
            rows.append(row)
        sheets.append(Sheet(ws_v.title, rows))
    return sheets


def _load_csv(filename: str, data: bytes) -> Sheet:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for raw in csv.reader(io.StringIO(text), dialect):
        row = []
        for v in raw:
            lead = len(v) - len(v.lstrip(" "))
            row.append(Cell(v.strip() if v.strip() else None, lead // 2))
        rows.append(row)
    return Sheet(filename.rsplit("/", 1)[-1], rows)


# ---------------------------------------------------------------- report model


@dataclass
class RowOutcome:
    sheet: str
    row: int
    kind: str  # meta | kpi | rating
    label: str
    status: str = "imported"  # imported | warning | rejected
    messages: list[str] = field(default_factory=list)

    def warn(self, msg: str):
        self.messages.append(msg)
        if self.status == "imported":
            self.status = "warning"

    def reject(self, msg: str):
        self.messages.append(msg)
        self.status = "rejected"


@dataclass
class StagedKPI:
    row: int
    code: str
    name: str
    level: int
    weight: float
    description: str | None
    critical: bool
    criteria: list[tuple[int, int, str]]
    outcome: RowOutcome
    parent: StagedKPI | None = None
    children: list[StagedKPI] = field(default_factory=list)
    optional: bool = False
    placeholders: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class StagedRating:
    row: int
    subject: str
    ref: str | None
    evaluator: str | None
    when: datetime | None
    comments: str | None
    legacy_total: float | None
    values: dict[str, float | str | None]  # kpi code -> score | "NA" | None
    outcome: RowOutcome
    attempt_no: int = 1
    complete: bool = False
    recomputed: float | None = None
    diff: float | None = None
    explanation: str | None = None
    evaluation_id: int | None = None


@dataclass
class MigrationOptions:
    subject_type: str | None = None  # overrides the sheet's metadata
    rescale_to: str | None = None  # rating_scale.code to map legacy scores onto
    fill_missing_guidelines: bool = True
    publish: bool = True
    code: str | None = None


@dataclass
class Migration:
    source: str
    options: MigrationOptions
    fatal: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rows: list[RowOutcome] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    kpis: list[StagedKPI] = field(default_factory=list)
    ratings: list[StagedRating] = field(default_factory=list)
    legacy_scale: tuple[int, int] | None = None
    guide_range: tuple[int, int] | None = None
    new_subject_type: tuple[str, str] | None = None
    scale_code: str | None = None
    definition: ScorecardDefinition | None = None
    issues: list[dict] = field(default_factory=list)
    scorecard_id: int | None = None
    version_id: int | None = None
    committed: bool = False

    # -------- scale mapping (identity unless rescale_to is set)
    target_range: tuple[int, int] | None = None

    def map_score(self, v: float) -> int:
        """Legacy whole score -> target scale: the lower bound of the mapped band (never rounds up)."""
        lo, hi = self.legacy_scale
        tlo, thi = self.target_range
        if (lo, hi) == (tlo, thi):
            return int(v)
        return math.ceil(tlo + (v - lo) * (thi - tlo) / (hi - lo) - 1e-9)

    def map_range(self, a: int, b: int) -> tuple[int, int]:
        lo, hi = self.legacy_scale
        tlo, thi = self.target_range
        if (lo, hi) == (tlo, thi):
            return a, b
        start = self.map_score(a)
        end = thi if b >= hi else self.map_score(b + 1) - 1
        return start, max(start, end)

    def to_dict(self) -> dict:
        from collections import Counter

        by_kind_status = Counter((r.kind, r.status) for r in self.rows)
        rec = [r for r in self.ratings if r.legacy_total is not None and r.recomputed is not None]
        return {
            "source": self.source,
            "status": "failed" if self.fatal else ("ok_with_warnings" if any(r.status != "imported" for r in self.rows)
                                                   or self.issues else "ok"),
            "committed": self.committed,
            "fatal": self.fatal,
            "notes": self.notes,
            "meta": self.meta,
            "legacy_scale": self.legacy_scale,
            "scale": self.scale_code,
            "definition": self.definition.model_dump() if self.definition else None,
            "validation_issues": self.issues,
            "scorecard_id": self.scorecard_id,
            "version_id": self.version_id,
            "counts": {f"{k}_{s}": n for (k, s), n in sorted(by_kind_status.items())},
            "rows": [r.__dict__ for r in self.rows],
            "evaluations": [
                {"row": r.row, "subject": r.subject, "evaluator": r.evaluator, "date": r.when.isoformat() if r.when else None,
                 "attempt_no": r.attempt_no, "status": r.outcome.status,
                 "import_as": "completed" if r.complete else "draft", "values": r.values,
                 "legacy_total": r.legacy_total, "recomputed": r.recomputed, "diff": r.diff,
                 "explanation": r.explanation, "evaluation_id": r.evaluation_id}
                for r in self.ratings
            ],
            "reconciliation": {
                "rows_with_legacy_total": len(rec),
                "matched": sum(1 for r in rec if abs(r.diff) <= 0.01),
                "mismatched": sum(1 for r in rec if abs(r.diff) > 0.01),
                "mismatched_unexplained": sum(1 for r in rec if abs(r.diff) > 0.01 and
                                              (r.explanation or "").startswith("unexplained")),
                "max_abs_diff": round(max((abs(r.diff) for r in rec), default=0), 2),
            },
        }


# ---------------------------------------------------------------- parsing helpers


def _as_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s.endswith("%"):
            s = s[:-1]
        try:
            f = float(s)
            return f if math.isfinite(f) else None
        except ValueError:
            return None
    return None


def _as_date(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, str):
        for f in DATE_FORMATS:
            try:
                return datetime.strptime(v.strip(), f).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _cells(row: list[Cell]) -> list[Any]:
    return [c.value for c in row]


def _find_header(sheet: Sheet, required: dict[str, set[str]], key: str) -> int | None:
    for i, row in enumerate(sheet.rows[:50]):
        if any(norm(v) in required[key] for v in _cells(row)):
            return i
    return None


def _map_columns(header: list[Any], synonyms: dict[str, set[str]]) -> tuple[dict[str, int], list[int]]:
    cols: dict[str, int] = {}
    unknown = []
    for j, h in enumerate(header):
        n = norm(h)
        if not n:
            continue
        hit = next((k for k, syn in synonyms.items() if n in syn and k not in cols), None)
        if hit:
            cols[hit] = j
        else:
            unknown.append(j)
    return cols, unknown


def _meta_pairs(rows: list[list[Cell]]):
    for i, row in enumerate(rows):
        vals = [v for v in _cells(row) if not blank(v)]
        if not vals:
            continue
        first = str(vals[0])
        if ":" in first and len(vals) == 1:
            k, _, v = first.partition(":")
            yield i, norm(k), v.strip()
        elif len(vals) >= 2:
            yield i, norm(first), str(vals[1]).strip()


# ---------------------------------------------------------------- stage 1: definition sheet


def stage_definition(m: Migration, sheet: Sheet):
    h = _find_header(sheet, SYN, "name")
    if h is None:
        m.fatal.append(f"[M002] No KPI header row found in sheet '{sheet.name}' (looked for a column like "
                       f"'KPI', 'Parameter' or 'Criteria')")
        return
    for i, key, value in _meta_pairs(sheet.rows[:h]):
        field_name = next((f for f, syn in META.items() if key in syn), None)
        oc = RowOutcome(sheet.name, i + 1, "meta", key)
        if field_name and value:
            m.meta[field_name] = value
        elif not field_name:
            oc.warn(f"Unrecognised metadata '{key}' ignored")
        m.rows.append(oc)

    header = _cells(sheet.rows[h])
    cols, unknown = _map_columns(header, SYN)
    guide_cols: dict[int, tuple[int, int]] = {}
    for j in unknown:
        g = GUIDE_HDR.match(norm(header[j]))
        if g:
            a, b = int(g.group(1)), int(g.group(2) or g.group(1))
            guide_cols[j] = (min(a, b), max(a, b))
        else:
            m.notes.append(f"[M101] Column '{header[j]}' in '{sheet.name}' was not recognised and is ignored")
    m.guide_range = (min(a for a, _ in guide_cols.values()), max(b for _, b in guide_cols.values())) if guide_cols else None

    stack: list[StagedKPI] = []
    blanks = 0
    for i in range(h + 1, len(sheet.rows)):
        row = sheet.rows[i]
        vals = _cells(row)
        if all(blank(v) for v in vals):
            blanks += 1
            if blanks >= 2 and m.kpis:
                break
            continue
        blanks = 0
        name_cell = row[cols["name"]] if cols["name"] < len(row) else Cell(None)
        name = str(name_cell.value).strip() if not blank(name_cell.value) else ""
        raw_code = vals[cols["code"]] if "code" in cols and cols["code"] < len(vals) else None
        oc = RowOutcome(sheet.name, i + 1, "kpi", name or str(raw_code or ""))
        m.rows.append(oc)
        if SUMMARY_ROW.match(name) or SUMMARY_ROW.match(str(raw_code or "")):
            oc.status, oc.kind = "imported", "meta"
            oc.messages.append("Summary row skipped")
            continue
        if not name:
            oc.reject("[M201] KPI row has no name")
            continue
        if len(name) > NAME_MAX:
            oc.warn(f"Name truncated to {NAME_MAX} characters")
            name = name[:NAME_MAX]
        for c in row:
            if c.formula_without_value:
                oc.warn("A formula cell has no saved value (open and save the file in Excel to compute it)")
                break

        # hierarchy: dotted codes win; otherwise indentation / bullets
        code = norm(raw_code) if not blank(raw_code) else ""
        if isinstance(raw_code, float) and raw_code.is_integer():
            code = str(int(raw_code))
        level = code.count(".") + 1 if re.match(r"^\d+(\.\d+)*$", code) else None
        if level is None:
            bullet = re.match(r"^([-–•*>]+)\s*", name)
            level = 1 + name_cell.indent + (len(bullet.group(1)) if bullet else 0)
            if bullet:
                name = name[bullet.end():].strip()

        # weight
        w_raw = vals[cols["weight"]] if "weight" in cols and cols["weight"] < len(vals) else None
        weight = _as_number(w_raw)
        if blank(w_raw):
            weight = 1.0
            oc.warn("[M01] Blank weight; defaulted to 1")
        elif weight is None:
            word = norm(w_raw)
            if word in WEIGHT_WORDS:
                weight = WEIGHT_WORDS[word]
                oc.warn(f"[M01] Weight '{w_raw}' mapped to {weight:g} (high=3, medium=2, low=1)")
            else:
                weight = 1.0
                oc.warn(f"[M01] Weight '{w_raw}' is not a number; defaulted to 1")
        elif weight < 0 or weight > WEIGHT_MAX:
            oc.warn(f"[M01] Weight {weight:g} out of range; defaulted to 1")
            weight = 1.0

        crit_raw = vals[cols["critical"]] if "critical" in cols and cols["critical"] < len(vals) else None
        critical = norm(crit_raw) in {"y", "yes", "true", "1", "x", "critical", "mandatory"}
        desc = vals[cols["description"]] if "description" in cols and cols["description"] < len(vals) else None

        criteria = []
        for j, (a, b) in guide_cols.items():
            if j < len(vals) and not blank(vals[j]):
                criteria.append((a, b, str(vals[j]).strip()))

        k = StagedKPI(i + 1, code, name, level, weight, None if blank(desc) else str(desc).strip(), critical,
                      criteria, oc)
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            if level > stack[-1].level + 1:
                oc.warn(f"Level jumps from {stack[-1].level} to {level}; attached to '{stack[-1].name}'")
            k.parent = stack[-1]
            stack[-1].children.append(k)
        elif level > 1:
            oc.warn(f"No parent found for level-{level} KPI; placed at the top level")
            k.level = 1
        stack.append(k)
        m.kpis.append(k)

    if not m.kpis:
        m.fatal.append(f"[M003] No KPI rows found under the header in '{sheet.name}'")
        return
    assign_codes(m)


def assign_codes(m: Migration):
    """Give every KPI a unique code before ratings are matched (codes key the rating values)."""
    used: set[str] = set()

    def walk(nodes: list[StagedKPI], prefix: str):
        for n, k in enumerate(nodes, start=1):
            if k.outcome.status == "rejected":
                continue
            generated = f"{prefix}.{n}" if prefix else str(n)
            code = k.code if k.code and len(k.code) <= 30 and re.match(r"^[\w.\-]+$", k.code) else generated
            if code in used:
                new = f"{code}-r{k.row}"
                k.outcome.warn(f"[M202] Duplicate code '{code}' renamed to '{new}'")
                code = new
            used.add(code)
            k.code = code
            walk(k.children, code)

    walk([k for k in m.kpis if k.parent is None], "")


# ---------------------------------------------------------------- stage 2: ratings sheet


def stage_ratings(m: Migration, sheet: Sheet):
    h = _find_header(sheet, RATING_SYN, "subject")
    fallback_subject = None
    if h is None:
        h, fallback_subject = _guess_rating_header(m, sheet)
        if h is None:
            m.fatal.append(f"[M004] No subject column found in ratings sheet '{sheet.name}'")
            return
    header = _cells(sheet.rows[h])
    cols, unknown = _map_columns(header, RATING_SYN)
    if fallback_subject is not None:
        cols["subject"] = fallback_subject
        unknown = [j for j in unknown if j != fallback_subject]
        m.notes.append(f"[M109] Subject column not named as expected; using '{header[fallback_subject]}' "
                       "(the first text column next to the KPI columns)")
    leaves = [k for k in m.kpis if not k.children]
    by_key: dict[str, StagedKPI] = {}
    for k in m.kpis:
        for key in {norm(k.code), norm(k.name)} - {""}:
            by_key.setdefault(key, k)
    kpi_cols: dict[int, StagedKPI] = {}
    for j in unknown:
        n = norm(header[j])
        k = by_key.get(n) or next((x for key, x in by_key.items() if len(n) > 3 and (key.startswith(n) or n.startswith(key))), None)
        if k is None:
            m.notes.append(f"[M102] Ratings column '{header[j]}' matches no KPI and is ignored")
        elif not k.children:
            kpi_cols[j] = k
        else:
            m.notes.append(f"[M103] Ratings column '{header[j]}' is a section; sections are rolled up, not rated — ignored")
    missing_cols = [k for k in leaves if k not in kpi_cols.values()]
    for k in missing_cols:
        m.notes.append(f"[M104] No ratings column for KPI '{k.code} {k.name}'")

    lo, hi = m.legacy_scale or (0, 10)
    for i in range(h + 1, len(sheet.rows)):
        vals = _cells(sheet.rows[i])
        if all(blank(v) for v in vals):
            continue
        get = lambda key: vals[cols[key]] if key in cols and cols[key] < len(vals) else None  # noqa: E731
        subject = str(get("subject")).strip() if not blank(get("subject")) else ""
        oc = RowOutcome(sheet.name, i + 1, "rating", subject)
        m.rows.append(oc)
        if SUMMARY_ROW.match(subject):
            oc.kind, oc.messages = "meta", ["Summary row skipped"]
            continue
        if not subject:
            oc.reject("[M301] Rating row has no subject")
            continue
        evaluator = None if blank(get("evaluator")) else str(get("evaluator")).strip()
        if evaluator is None:
            oc.warn("[M03] No evaluator recorded")
        when = None
        if not blank(get("date")):
            when = _as_date(get("date"))
            if when is None:
                oc.warn(f"[M302] Date '{get('date')}' not understood; import date used")
        values: dict[str, float | str | None] = {}
        for j, k in kpi_cols.items():
            v = vals[j] if j < len(vals) else None
            if blank(v):
                values[k.code] = None
                continue
            if norm(v) in NA_TOKENS:
                values[k.code] = "NA"
                continue
            num = _as_number(v)
            if num is None:
                values[k.code] = None
                oc.warn(f"[M303] '{k.name}': '{v}' is not a score; left unrated")
                continue
            if not lo <= num <= hi:
                values[k.code] = None
                oc.warn(f"[M304] '{k.name}': {num:g} is outside the {lo}–{hi} scale; left unrated")
                continue
            if not float(num).is_integer():
                oc.warn(f"[M305] '{k.name}': {num:g} rounded down to {math.floor(num)} (scores are whole numbers; never rounded up)")
                num = math.floor(num)
            values[k.code] = num
        if values and all(v is None for v in values.values()):
            oc.reject("[M306] Row has no usable scores")
        total = _as_number(get("total"))
        m.ratings.append(StagedRating(i + 1, subject, None if blank(get("ref")) else str(get("ref")), evaluator, when,
                                      None if blank(get("comments")) else str(get("comments")), total, values, oc))

    # [M04] duplicates: same subject + evaluator
    groups: dict[tuple, list[StagedRating]] = {}
    for r in m.ratings:
        if r.outcome.status != "rejected":
            groups.setdefault((norm(r.subject), norm(r.evaluator)), []).append(r)
    for rs in groups.values():
        if len(rs) < 2:
            continue
        by_date: dict[Any, list[StagedRating]] = {}
        for r in rs:
            by_date.setdefault(r.when.date() if r.when else None, []).append(r)
        for same in by_date.values():
            if len(same) < 2:
                continue
            first = same[0]
            for r in same[1:]:
                if r.values == first.values:
                    r.outcome.reject(f"[M04] Exact duplicate of row {first.row}; skipped")
                else:
                    for x in (first, r):
                        if x.outcome.status != "rejected":
                            x.outcome.reject("[M04] Conflicting scores for the same subject, evaluator and date "
                                             f"(rows {first.row} and {r.row}); neither imported — resolve at source")
        alive = sorted([r for r in rs if r.outcome.status != "rejected"],
                       key=lambda r: (r.when or datetime.max.replace(tzinfo=timezone.utc), r.row))
        if len(alive) > 1:
            for n, r in enumerate(alive, start=1):
                r.attempt_no = n
                r.outcome.warn(f"[M04] Repeat rating of the same subject by the same evaluator: imported as attempt {n}")


def _guess_rating_header(m: Migration, sheet: Sheet) -> tuple[int | None, int | None]:
    """Header = first row naming at least two KPIs; subject = first column of mostly text values below it."""
    keys = {norm(k.name) for k in m.kpis} | {norm(k.code) for k in m.kpis}
    for i, row in enumerate(sheet.rows[:50]):
        header = _cells(row)
        if sum(norm(v) in keys for v in header) < 2:
            continue
        body = [_cells(r) for r in sheet.rows[i + 1:i + 30]]
        for j, hv in enumerate(header):
            if norm(hv) in keys or blank(hv):
                continue
            col = [r[j] for r in body if j < len(r) and not blank(r[j])]
            if col and sum(isinstance(v, str) and _as_number(v) is None and _as_date(v) is None for v in col) >= 0.8 * len(col):
                return i, j
        return i, None
    return None, None


# ---------------------------------------------------------------- stage 3: mapping


def resolve_scale(m: Migration, db: Session):
    scales = {(s.min_value, s.max_value): s for s in db.scalars(select(RatingScale))}
    legacy = None
    meta = m.meta.get("scale", "")
    g = re.search(r"(\d+)\s*(?:-|–|to)\s*(\d+)", meta)
    if g:
        legacy = (int(g.group(1)), int(g.group(2)))
    elif "%" in meta or "percent" in meta.lower():
        legacy = (0, 100)
    elif m.guide_range:
        legacy = m.guide_range
        m.notes.append(f"[M105] Scale not stated; inferred {legacy[0]}–{legacy[1]} from the guideline columns")
    if legacy is None:
        m.fatal.append("[M005] Rating scale unknown: add a 'Scale: 0-10' line above the header or score-guideline columns")
        return
    m.legacy_scale = legacy
    if m.options.rescale_to:
        target = db.scalar(select(RatingScale).where(RatingScale.code == m.options.rescale_to))
        if not target:
            m.fatal.append(f"[M006] Unknown target scale '{m.options.rescale_to}'")
            return
        m.notes.append(f"[M106] Legacy {legacy[0]}–{legacy[1]} scores mapped onto {target.name}: each legacy score "
                       f"becomes the lowest score of its mapped band")
        if target.max_value - target.min_value < legacy[1] - legacy[0]:
            m.notes.append("[M110] Warning: the target scale is coarser than the legacy scale; several legacy scores "
                           "collapse into one and pass/fail verdicts near the target may change")
    else:
        target = scales.get(legacy)
        if not target:
            m.fatal.append(f"[M007] No {legacy[0]}–{legacy[1]} rating scale exists. Create it, or migrate with "
                           f"rescale_to (e.g. '0-10-rag')")
            return
    m.scale_code = target.code
    m.target_range = (target.min_value, target.max_value)


def resolve_target(m: Migration) -> float | None:
    tlo, thi = m.target_range
    raw = m.meta.get("target")
    if not raw:
        t = round(tlo + 0.8 * (thi - tlo), 2)
        m.notes.append(f"[M05] No target in source; defaulted to {t:g} (80% of scale)")
        return t
    num = _as_number(raw)
    if num is not None:
        lo, hi = m.legacy_scale
        if not lo <= num <= hi:
            m.fatal.append(f"[M05] Target {num:g} is outside the {lo}–{hi} scale")
            return None
        if (lo, hi) == (tlo, thi):
            return num
        return round(tlo + (num - lo) * (thi - tlo) / (hi - lo), 2)
    word = norm(raw)
    if word in TARGET_WORDS:
        t = round(tlo + TARGET_WORDS[word] * (thi - tlo), 2)
        m.notes.append(f"[M05] Text target '{raw}' mapped to {t:g}")
        return t
    m.fatal.append(f"[M05] Target '{raw}' is neither a number nor a known word ({', '.join(TARGET_WORDS)})")
    return None


def build_definition(m: Migration, db: Session):
    tlo, thi = m.target_range
    target = resolve_target(m)
    if target is None:
        return
    # optional: any KPI rated N/A in the history
    for r in m.ratings:
        for code, v in r.values.items():
            if v == "NA":
                k = next(k for k in m.kpis if k.code == code)
                if not k.optional:
                    k.optional = True
                    k.outcome.warn("[M02] Rated N/A in the history; marked optional")

    def conv(k: StagedKPI) -> ParameterIn:
        code = k.code
        criteria: list[CriterionIn] = []
        if not k.children:
            mapped = sorted(((*m.map_range(a, b), t) for a, b, t in k.criteria), key=lambda x: -x[1])
            merged: list[list] = []
            for a, b, t in mapped:  # merge identical adjacent guidelines into ranges
                if merged and merged[-1][2] == t and merged[-1][0] == b + 1:
                    merged[-1][0] = a
                else:
                    merged.append([a, b, t])
            if len(merged) < len(mapped):
                k.outcome.warn("Identical adjacent guidelines merged into ranges")
            criteria = [CriterionIn(score_min=a, score_max=b, qualitative=t) for a, b, t in merged]
            covered = {s for c in criteria for s in range(c.score_min, c.score_max + 1)}
            gaps = [s for s in range(tlo, thi + 1) if s not in covered]
            if gaps and m.options.fill_missing_guidelines:
                runs, start = [], gaps[0]
                for a, b in zip(gaps, gaps[1:] + [None]):
                    if b != a + 1:
                        runs.append((start, a))
                        start = b
                for a, b in runs:
                    criteria.append(CriterionIn(score_min=a, score_max=b, qualitative=PLACEHOLDER))
                k.placeholders = runs
                k.outcome.warn(f"[M06] No source guideline for scores {', '.join(f'{a}-{b}' if a != b else str(a) for a, b in runs)}; "
                               "placeholder added")
            criteria.sort(key=lambda c: -c.score_max)
        elif k.criteria:
            k.outcome.warn("Guidelines on a section row are ignored (sections are rolled up)")
        return ParameterIn(
            code=code, name=k.name, description=k.description, weight=k.weight, is_critical=k.critical,
            is_optional=k.optional and not k.children, criteria=criteria,
            children=[conv(c) for c in k.children if c.outcome.status != "rejected"],
        )

    roots = [k for k in m.kpis if k.parent is None and k.outcome.status != "rejected"]
    params = [conv(k) for k in roots]
    depth = max((k.level for k in m.kpis), default=1)

    subject = m.options.subject_type or m.meta.get("subject_type")
    if not subject:
        subject = "task"
        m.notes.append("[M107] The source does not say what it scores; subject type defaulted to 'task'")
    st = db.scalar(select(SubjectType).where((SubjectType.code == norm(subject).replace(" ", "_")) |
                                             (SubjectType.name.ilike(subject))))
    st_code = st.code if st else (re.sub(r"[^a-z0-9_]+", "_", subject.lower()).strip("_")[:40] or "task")
    if not st:
        m.new_subject_type = (st_code, subject.strip()[:120])
        m.notes.append(f"[M107] Subject type '{subject}' does not exist; it will be created as '{st_code}'")
    name = (m.meta.get("name") or m.source.rsplit(".", 1)[0]).strip()[:NAME_MAX]
    code = m.options.code or slug(name)
    base, n = code, 2
    while db.scalar(select(Scorecard).where(Scorecard.code == code)):
        code, n = f"{base}-{n}", n + 1
    if code != base:
        m.notes.append(f"[M108] Scorecard code '{base}' exists; using '{code}'")

    purpose = m.meta.get("purpose") or f"Migrated from legacy spreadsheet '{m.source}'. State the purpose before reuse."
    objective = m.meta.get("objective") or f"Reach the target of {target:g}."
    tags = ["legacy-import"] + (["needs-guidelines"] if any(k.placeholders for k in m.kpis) else [])
    version = VersionIn(purpose=purpose, scope=m.meta.get("scope", ""), objective=objective,
                        guidance=f"Imported from {m.source}.", rating_scale=m.scale_code, target_score=target,
                        max_depth=min(6, max(depth, 1)), parameters=params)
    m.definition = ScorecardDefinition(code=code, name=name or "Imported scorecard", subject_type=st_code,
                                       owner=m.meta.get("owner"), tags=tags, version=version)
    scale = db.scalar(select(RatingScale).where(RatingScale.code == m.scale_code))
    issues = structural_errors(version) + validate_version(version, svc.scale_info(scale))
    m.issues = [i.model_dump() for i in issues]


def finalise_ratings(m: Migration, db: Session):
    """Map scores, decide completed vs draft, and reconcile legacy totals using the real scoring engine."""
    if not m.definition:
        return
    scale = db.scalar(select(RatingScale).where(RatingScale.code == m.scale_code))
    flat: list[tuple[ParameterIn, str | None]] = []

    def walk(ps, parent):
        for p in ps:
            flat.append((p, parent))
            walk(p.children, p.code)

    walk(m.definition.version.parameters, None)
    ids = {p.code: n for n, (p, _) in enumerate(flat, start=1)}
    card = scoring.ScorecardDef(
        scale.min_value, scale.max_value,
        [scoring.BandDef(b.label, b.lower_bound, b.rag) for b in scale.bands],
        m.definition.version.target_score, "weighted_mean", False,
        [scoring.ParamDef(id=ids[p.code], code=p.code, name=p.name, parent_id=ids.get(parent), weight=p.weight,
                          sort_order=ids[p.code], is_critical=p.is_critical, is_optional=p.is_optional)
         for p, parent in flat],
    )
    leaf_codes = {p.code for p, _ in flat if not p.children}
    for r in m.ratings:
        if r.outcome.status == "rejected":
            continue
        mapped = {c: (v if v in (None, "NA") else m.map_score(v)) for c, v in r.values.items() if c in leaf_codes}
        r.values = mapped
        inputs = {ids[c]: scoring.LeafInput(judged_score=None if v in (None, "NA") else v, not_applicable=v == "NA")
                  for c, v in mapped.items()}
        out = scoring.compute(card, inputs, {})
        r.complete = out.complete
        r.recomputed = out.final_score
        if not out.complete:
            missing = [p.code for p, _ in flat if ids[p.code] in out.pending_leaf_ids]
            r.outcome.warn(f"Incomplete ({', '.join(missing)} unrated): imported as a draft evaluation")
        if r.legacy_total is not None and r.recomputed is not None:
            legacy_total = r.legacy_total
            lo, hi = m.legacy_scale
            if (lo, hi) != m.target_range and lo <= legacy_total <= hi:
                tlo, thi = m.target_range
                legacy_total = tlo + (legacy_total - lo) * (thi - tlo) / (hi - lo)
            r.diff = round(r.recomputed - legacy_total, 2)
            if abs(r.diff) > 0.01:
                r.explanation = _explain(m, r, flat, ids)


def _legacy_formulas(r: StagedRating, flat) -> dict[str, float]:
    """Candidate formulas spreadsheets typically use, evaluated on the row's (legacy-scale) leaf scores."""
    by_code = {p.code: p for p, _ in flat}
    parent_of = {p.code: parent for p, parent in flat}
    leaves = [p for p, _ in flat if not p.children]
    scored = [(p, r.values.get(p.code)) for p in leaves if isinstance(r.values.get(p.code), (int, float))]
    if not scored:
        return {}

    def path_product(code: str) -> float:
        w, c = 1.0, code
        while c is not None:
            w *= by_code[c].weight / 100
            c = parent_of[c]
        return w

    out = {
        "Σ(score × weight% × parent weight% …), no normalisation": sum(v * path_product(p.code) for p, v in scored),
        "flat weighted mean of leaves (hierarchy ignored)": sum(v * p.weight for p, v in scored) / (sum(p.weight for p, _ in scored) or 1),
        "simple average of leaves": sum(v for _, v in scored) / len(scored),
        "sum of leaf scores": float(sum(v for _, v in scored)),
    }
    return out


def _explain(m: Migration, r: StagedRating, flat, ids) -> str:
    reasons = []
    legacy_values = r.values  # already mapped; only meaningful when the scale is unchanged
    if m.legacy_scale == m.target_range:
        for label, value in _legacy_formulas(StagedRating(**{**r.__dict__, "values": legacy_values}), flat).items():
            if abs(value - r.legacy_total) <= 0.011:
                reasons.append(f"legacy total matches '{label}'; the system uses normalised weighted means, "
                               "so the legacy totals were not comparable on the scale")
                break
    if any(v == "NA" for v in r.values.values()):
        reasons.append("N/A parameters excluded and weights renormalised")
    if any("[M305]" in msg for msg in r.outcome.messages):
        reasons.append("fractional legacy scores rounded down")
    if any("[M303]" in msg or "[M304]" in msg for msg in r.outcome.messages):
        reasons.append("the legacy total includes a score that was refused on import (not a number or outside "
                       "the scale)")
    if m.legacy_scale != m.target_range:
        reasons.append("scores mapped to a different scale")
    return "; ".join(reasons) or "unexplained: no known legacy formula reproduces the total (check the source)"


# ---------------------------------------------------------------- orchestration


def plan(db: Session, files: list[tuple[str, bytes]], options: MigrationOptions | None = None) -> Migration:
    options = options or MigrationOptions()
    m = Migration(source=files[0][0], options=options)
    sheets: list[Sheet] = []
    for name, data in files:
        try:
            sheets.extend(load_sheets(name, data))
        except svc.DomainError as e:
            m.fatal.append(f"[{e.code}] {e.message}")
    if m.fatal:
        return m
    if not sheets:
        m.fatal.append("[M001] No sheets found")
        return m

    def named(*words):
        return next((s for s in sheets if any(w in s.name.lower() for w in words)), None)

    definition_sheet = named("scorecard", "kpi", "parameter", "definition", "criteria") or sheets[0]
    ratings_sheet = named("rating", "score", "result", "evaluation", "assessment log")
    if ratings_sheet is definition_sheet:
        ratings_sheet = None
    if ratings_sheet is None and len(sheets) > 1:
        ratings_sheet = next(s for s in sheets if s is not definition_sheet)

    stage_definition(m, definition_sheet)
    if m.fatal:
        return m
    resolve_scale(m, db)
    if m.fatal:
        return m
    if ratings_sheet is not None:
        stage_ratings(m, ratings_sheet)
        if m.fatal:
            return m
    try:
        build_definition(m, db)
        finalise_ratings(m, db)
    except ValidationError as e:  # last line of defence: never let a source file crash the migration
        m.definition = None
        problems = "; ".join(".".join(map(str, x["loc"])) + ": " + x["msg"] for x in e.errors()[:5])
        m.fatal.append(f"[M008] The migrated definition violates the data contract: {problems}")
    return m


def commit(db: Session, m: Migration) -> Migration:
    if m.fatal or not m.definition:
        raise svc.DomainError("M900", "Migration has fatal problems; fix the source and preview again",
                              details=m.fatal)
    if any(i["severity"] == "error" and i["code"] in {"V015", "V020", "V002"} for i in m.issues):
        raise svc.DomainError("M901", "The migrated definition cannot be stored", details=m.issues)
    if m.new_subject_type and not db.scalar(select(SubjectType).where(SubjectType.code == m.new_subject_type[0])):
        db.add(SubjectType(code=m.new_subject_type[0], name=m.new_subject_type[1],
                           description=f"Created by migration of {m.source}"))
        db.flush()
    sc = svc.create_scorecard(db, m.definition)
    version = sc.versions[0]
    m.scorecard_id, m.version_id = sc.id, version.id
    blocking = has_errors(svc.validate_stored_version(version))
    if blocking or not m.options.publish:
        for r in m.ratings:
            if r.outcome.status != "rejected":
                r.outcome.reject("[M902] Scorecard kept as a draft (validation errors or publish=false); "
                                 "ratings can only be imported against a published version")
        m.notes.append("[M902] Scorecard saved as a draft; fix the validation issues, publish, then re-run the "
                       "ratings import")
        m.committed = True
        return m
    svc.publish_version(db, version)
    by_code = {p.code: p for p in version.parameters}
    now = svc.now()
    for r in m.ratings:
        if r.outcome.status == "rejected":
            continue
        ev = svc.create_evaluation(db, EvaluationCreate(
            version_id=version.id, subject_name=r.subject[:300], subject_ref=r.ref, evaluator_type="human",
            evaluator_name=(r.evaluator or "legacy import")[:120], attempt_no=r.attempt_no,
            notes=f"Imported from {m.source} row {r.row}"), commit=False)
        ev.origin, ev.origin_ref = "import", f"{m.source}!{r.outcome.sheet}:{r.row}"[:300]
        ratings = [RatingIn(parameter_id=by_code[c].id, judged_score=None if v in (None, "NA") else v,
                            not_applicable=v == "NA") for c, v in r.values.items() if c in by_code]
        svc.apply_update(db, ev, EvaluationUpdate(ratings=ratings, summary=r.comments), commit=False)
        ev.created_at = r.when or now
        if r.complete:
            svc.complete_evaluation(db, ev, commit=False)
            ev.completed_at = r.when or now
        db.flush()
        r.evaluation_id = ev.id
        if ev.final_score is not None and r.recomputed is not None and abs(ev.final_score - r.recomputed) > 1e-6:
            r.outcome.warn(f"Stored score {ev.final_score} differs from the preview {r.recomputed}")  # should never happen
    db.commit()
    m.committed = True
    return m
