"""Domain services: reference data, scorecard definition <-> ORM, evaluation lifecycle.

Everything that writes data goes through here — the API, the ingestion tool and the generator —
so every path enforces the same rules.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import scoring
from .models import (
    Evaluation,
    EvaluationDocument,
    Metric,
    MetricThreshold,
    MetricValue,
    Parameter,
    ParameterResult,
    RatingBand,
    RatingCriterion,
    RatingScale,
    Scorecard,
    ScorecardVersion,
    SubjectType,
)
from .schemas import (
    CriterionIn,
    EvaluationCreate,
    EvaluationUpdate,
    MetricIn,
    ParameterIn,
    ScaleIn,
    ScorecardDefinition,
    ThresholdIn,
    VersionIn,
)
from .validation import ScaleInfo, has_errors, structural_errors, validate_scale, validate_version


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, details=None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- reference data

DEFAULT_SCALES = [
    ScaleIn(
        code="0-10-rag",
        name="0–10 Quality Scale (RAG)",
        min_value=0,
        max_value=10,
        description="Quality Scorecard Framework v1.1 §6: 11-point scale with fixed colour bands.",
        bands=[
            {"label": "Dark green", "lower_bound": 9, "color_hex": "#00B050", "font_hex": "#FFFFFF", "rag": "GREEN",
             "meaning": "Excellent. Target for foundational artefacts."},
            {"label": "Light green", "lower_bound": 8, "color_hex": "#92D050", "font_hex": "#000000", "rag": "GREEN",
             "meaning": "Good. Default target for most work."},
            {"label": "Grey", "lower_bound": 7, "color_hex": "#D9D9D9", "font_hex": "#000000", "rag": "AMBER",
             "meaning": "Acceptable. Minimum floor for day-to-day work."},
            {"label": "Amber", "lower_bound": 6, "color_hex": "#FFC000", "font_hex": "#000000", "rag": "AMBER",
             "meaning": "Below standard; acceptable only where a POC target of 6 is set."},
            {"label": "Dark amber", "lower_bound": 5, "color_hex": "#ED7D31", "font_hex": "#FFFFFF", "rag": "RED",
             "meaning": "Average; not acceptable, even for a POC."},
            {"label": "Red", "lower_bound": 4, "color_hex": "#FF0000", "font_hex": "#FFFFFF", "rag": "RED",
             "meaning": "Poor."},
            {"label": "Dark red", "lower_bound": 0, "color_hex": "#C00000", "font_hex": "#FFFFFF", "rag": "RED",
             "meaning": "Unacceptable (0–3 are treated the same)."},
        ],
    ),
    ScaleIn(
        code="1-5-likert",
        name="1–5 Rating Scale",
        min_value=1,
        max_value=5,
        description="Common 5-point scale for people, team and survey-style scorecards.",
        bands=[
            {"label": "Excellent", "lower_bound": 5, "color_hex": "#00B050", "font_hex": "#FFFFFF", "rag": "GREEN"},
            {"label": "Good", "lower_bound": 4, "color_hex": "#92D050", "font_hex": "#000000", "rag": "GREEN"},
            {"label": "Adequate", "lower_bound": 3, "color_hex": "#FFC000", "font_hex": "#000000", "rag": "AMBER"},
            {"label": "Weak", "lower_bound": 2, "color_hex": "#ED7D31", "font_hex": "#FFFFFF", "rag": "RED"},
            {"label": "Poor", "lower_bound": 1, "color_hex": "#C00000", "font_hex": "#FFFFFF", "rag": "RED"},
        ],
    ),
    ScaleIn(
        code="0-100-pct",
        name="0–100 Percentage Scale",
        min_value=0,
        max_value=100,
        description="Percentage scale for audit/compliance style scorecards.",
        bands=[
            {"label": "Compliant", "lower_bound": 90, "color_hex": "#00B050", "font_hex": "#FFFFFF", "rag": "GREEN"},
            {"label": "Minor gaps", "lower_bound": 75, "color_hex": "#FFC000", "font_hex": "#000000", "rag": "AMBER"},
            {"label": "Major gaps", "lower_bound": 50, "color_hex": "#ED7D31", "font_hex": "#FFFFFF", "rag": "RED"},
            {"label": "Non-compliant", "lower_bound": 0, "color_hex": "#C00000", "font_hex": "#FFFFFF", "rag": "RED"},
        ],
    ),
]

DEFAULT_SUBJECT_TYPES = [
    ("task", "Task", "A single unit of work"),
    ("activity", "Activity", "A group of tasks"),
    ("milestone", "Milestone", "A set of tasks achieving a higher-order business objective"),
    ("project", "Project", "A project made of milestones"),
    ("document", "Document", "A written artefact: spec, report, proposal"),
    ("assessment", "Assessment", "A test, quiz, assignment or other assessment instrument"),
    ("team", "Team", "A group of people"),
    ("individual", "Individual", "A person"),
    ("product", "Product", "A product or release"),
    ("meeting", "Meeting", "A meeting, call or session"),
    ("communication", "Communication", "Email, message or other communication"),
    ("deployment", "Deployment", "A technical deployment or operational change"),
]


def seed_reference_data(db: Session) -> None:
    for s in DEFAULT_SCALES:
        if not db.scalar(select(RatingScale).where(RatingScale.code == s.code)):
            create_scale(db, s, commit=False)
    for code, name, desc in DEFAULT_SUBJECT_TYPES:
        if not db.scalar(select(SubjectType).where(SubjectType.code == code)):
            db.add(SubjectType(code=code, name=name, description=desc))
    db.commit()


def create_scale(db: Session, s: ScaleIn, commit: bool = True) -> RatingScale:
    issues = validate_scale(ScaleInfo(s.min_value, s.max_value, [b.lower_bound for b in s.bands]))
    if has_errors(issues):
        raise DomainError("V013", "Invalid rating scale", details=[i.model_dump() for i in issues])
    if db.scalar(select(RatingScale).where(RatingScale.code == s.code)):
        raise DomainError("E011", f"Rating scale '{s.code}' already exists", 409)
    scale = RatingScale(
        code=s.code, name=s.name, min_value=s.min_value, max_value=s.max_value, description=s.description
    )
    scale.bands = [RatingBand(**b.model_dump()) for b in s.bands]
    db.add(scale)
    if commit:
        db.commit()
    return scale


def scale_by_code(db: Session, code: str) -> RatingScale:
    scale = db.scalar(select(RatingScale).where(RatingScale.code == code))
    if not scale:
        raise DomainError("E008", f"Unknown rating scale '{code}'")
    return scale


def subject_type_by_code(db: Session, code: str) -> SubjectType:
    st = db.scalar(select(SubjectType).where(SubjectType.code == code))
    if not st:
        raise DomainError("E008", f"Unknown subject type '{code}'")
    return st


def scale_info(scale: RatingScale) -> ScaleInfo:
    return ScaleInfo(scale.min_value, scale.max_value, [b.lower_bound for b in scale.bands])


# ---------------------------------------------------------------- definition -> ORM


def _build_parameters(version: ScorecardVersion, params: list[ParameterIn], parent: Parameter | None):
    for i, p in enumerate(params):
        node = Parameter(
            code=p.code,
            name=p.name,
            description=p.description,
            weight=p.weight,
            sort_order=i,
            aggregation=p.aggregation,
            is_critical=p.is_critical,
            min_acceptable_score=p.min_acceptable_score,
            is_optional=p.is_optional,
            parent=parent,
        )
        node.criteria = [RatingCriterion(**c.model_dump()) for c in p.criteria]
        node.metrics = [
            Metric(
                code=m.code,
                name=m.name,
                unit=m.unit,
                data_type=m.data_type,
                description=m.description,
                sort_order=j,
                thresholds=[MetricThreshold(**t.model_dump()) for t in m.thresholds],
            )
            for j, m in enumerate(p.metrics)
        ]
        version.parameters.append(node)
        _build_parameters(version, p.children, node)


def _apply_version_content(db: Session, version: ScorecardVersion, v: VersionIn):
    blocking = structural_errors(v)
    if blocking:  # even a draft cannot hold these
        raise DomainError(blocking[0].code, blocking[0].message, details=[i.model_dump() for i in blocking])
    scale = scale_by_code(db, v.rating_scale)
    version.purpose, version.scope, version.objective = v.purpose, v.scope, v.objective
    version.guidance, version.change_note = v.guidance, v.change_note
    version.rating_scale = scale
    version.target_score, version.aggregation = v.target_score, v.aggregation
    version.max_depth, version.qtc_enabled = v.max_depth, v.qtc_enabled
    version.required_judges, version.judge_tolerance_pct = v.required_judges, v.judge_tolerance_pct
    version.require_self_appraisal, version.is_foundational = v.require_self_appraisal, v.is_foundational
    version.parameters.clear()
    db.flush()
    _build_parameters(version, v.parameters, None)


def create_scorecard(db: Session, d: ScorecardDefinition, publish: bool = False) -> Scorecard:
    if db.scalar(select(Scorecard).where(Scorecard.code == d.code)):
        raise DomainError("E011", f"Scorecard code '{d.code}' already exists", 409)
    sc = Scorecard(
        code=d.code,
        name=d.name,
        subject_type=subject_type_by_code(db, d.subject_type),
        owner=d.owner,
        tags=d.tags,
        is_template=d.is_template,
        requires_review=d.requires_review,
    )
    version = ScorecardVersion(version_no=1, status="draft", target_score=d.version.target_score)
    sc.versions.append(version)
    db.add(sc)
    _apply_version_content(db, version, d.version)
    db.flush()
    if publish:
        publish_version(db, version, commit=False)
    db.commit()
    return sc


def update_draft(db: Session, version: ScorecardVersion, v: VersionIn) -> ScorecardVersion:
    if version.status != "draft":
        raise DomainError("E009", "Published and retired versions are immutable; create a new draft version", 409)
    _apply_version_content(db, version, v)
    db.commit()
    db.refresh(version)
    return version


def validate_stored_version(version: ScorecardVersion):
    return validate_version(version_to_definition(version), scale_info(version.rating_scale))


def _require_valid(version: ScorecardVersion):
    issues = validate_stored_version(version)
    if has_errors(issues):
        raise DomainError(
            "V000", "Scorecard has validation errors", details=[i.model_dump() for i in issues if i.severity == "error"]
        )
    return issues


def go_live(db: Session, version: ScorecardVersion, actor: str):
    """Shared by direct publish and reviewer approval: retire the previous published version."""
    from . import workflow as wf
    from .models import VersionReview

    for other in version.scorecard.versions:
        if other.status == "published" and other.id != version.id:
            wf.transition(db, wf.VERSION, other, "retire", actor, details={"reason": f"superseded by v{version.version_no}"})
            other.retired_at = now()
    version.published_at = now()
    db.add(VersionReview(version_id=version.id, action="published", actor=actor))


def publish_version(db: Session, version: ScorecardVersion, commit: bool = True, actor: str = "system"):
    """Direct publish (draft -> published), only for scorecards that do not require review."""
    from . import workflow as wf

    if version.status != "draft":
        raise DomainError("E009", "Only draft versions can be published", 409)
    if version.scorecard.requires_review:
        raise DomainError("S001", "This scorecard requires reviewer approval: submit it for review instead", 409,
                          details=["allowed: submit_for_review"])
    issues = _require_valid(version)
    go_live(db, version, actor)
    wf.transition(db, wf.VERSION, version, "publish", actor)
    if commit:
        db.commit()
    return issues


def new_draft_from(db: Session, source: ScorecardVersion, change_note: str | None = None) -> ScorecardVersion:
    sc = source.scorecard
    if any(v.status in ("draft", "in_review") for v in sc.versions):
        raise DomainError("E014", "This scorecard already has a draft or a version in review", 409)
    content = version_to_definition(source)
    content.change_note = change_note
    version = ScorecardVersion(
        version_no=max(v.version_no for v in sc.versions) + 1,
        status="draft",
        target_score=content.target_score,
        based_on_version_id=source.id,
    )
    sc.versions.append(version)
    _apply_version_content(db, version, content)
    db.commit()
    return version


def clone_scorecard(db: Session, source: ScorecardVersion, code: str, name: str) -> Scorecard:
    d = ScorecardDefinition(
        code=code,
        name=name,
        subject_type=source.scorecard.subject_type.code,
        owner=source.scorecard.owner,
        tags=list(source.scorecard.tags or []),
        version=version_to_definition(source),
    )
    return create_scorecard(db, d)


def delete_draft(db: Session, version: ScorecardVersion):
    if version.status != "draft":
        raise DomainError("E009", "Only draft versions can be deleted", 409)
    sc = version.scorecard
    if len(sc.versions) == 1:
        db.delete(sc)
    else:
        db.delete(version)
    db.commit()


# ---------------------------------------------------------------- ORM -> definition / views


def _children_map(version: ScorecardVersion) -> dict[int | None, list[Parameter]]:
    m: dict[int | None, list[Parameter]] = {}
    for p in version.parameters:
        m.setdefault(p.parent_id, []).append(p)
    for kids in m.values():
        kids.sort(key=lambda p: (p.sort_order, p.id))
    return m


def version_to_definition(version: ScorecardVersion) -> VersionIn:
    kids = _children_map(version)

    def conv(p: Parameter) -> ParameterIn:
        return ParameterIn(
            code=p.code,
            name=p.name,
            description=p.description,
            weight=p.weight,
            aggregation=p.aggregation,
            is_critical=p.is_critical,
            min_acceptable_score=p.min_acceptable_score,
            is_optional=p.is_optional,
            criteria=[
                CriterionIn(
                    score_min=c.score_min, score_max=c.score_max, qualitative=c.qualitative, quantitative=c.quantitative
                )
                for c in sorted(p.criteria, key=lambda c: -c.score_max)
            ],
            metrics=[
                MetricIn(
                    code=m.code,
                    name=m.name,
                    unit=m.unit,
                    data_type=m.data_type,
                    description=m.description,
                    thresholds=[
                        ThresholdIn(min_value=t.min_value, max_value=t.max_value, score=t.score) for t in m.thresholds
                    ],
                )
                for m in p.metrics
            ],
            children=[conv(c) for c in kids.get(p.id, [])],
        )

    return VersionIn(
        purpose=version.purpose,
        scope=version.scope,
        objective=version.objective,
        guidance=version.guidance,
        rating_scale=version.rating_scale.code,
        target_score=version.target_score,
        aggregation=version.aggregation,
        max_depth=version.max_depth,
        qtc_enabled=version.qtc_enabled,
        required_judges=version.required_judges,
        judge_tolerance_pct=version.judge_tolerance_pct,
        require_self_appraisal=version.require_self_appraisal,
        is_foundational=version.is_foundational,
        change_note=version.change_note,
        parameters=[conv(p) for p in kids.get(None, [])],
    )


def export_definition(version: ScorecardVersion) -> ScorecardDefinition:
    sc = version.scorecard
    return ScorecardDefinition(
        code=sc.code,
        name=sc.name,
        subject_type=sc.subject_type.code,
        owner=sc.owner,
        tags=list(sc.tags or []),
        is_template=sc.is_template,
        requires_review=sc.requires_review,
        version=version_to_definition(version),
    )


def scale_view(scale: RatingScale) -> dict:
    return {
        "id": scale.id,
        "code": scale.code,
        "name": scale.name,
        "min_value": scale.min_value,
        "max_value": scale.max_value,
        "description": scale.description,
        "bands": [
            {
                "label": b.label,
                "lower_bound": b.lower_bound,
                "color_hex": b.color_hex,
                "font_hex": b.font_hex,
                "rag": b.rag,
                "meaning": b.meaning,
            }
            for b in sorted(scale.bands, key=lambda b: -b.lower_bound)
        ],
    }


def version_view(version: ScorecardVersion) -> dict:
    """Full tree with database ids — used by the evaluation UI and judge."""
    kids = _children_map(version)
    card = to_scoring_def(version)
    shares = scoring.compute(card, {}, {}).params  # effective weights with nothing N/A

    def conv(p: Parameter, level: int) -> dict:
        return {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "description": p.description,
            "level": level,
            "weight": p.weight,
            "effective_weight": shares[p.id].effective_weight,
            "aggregation": p.aggregation,
            "is_critical": p.is_critical,
            "min_acceptable_score": p.min_acceptable_score,
            "is_optional": p.is_optional,
            "is_leaf": not kids.get(p.id),
            "criteria": [
                {"score_min": c.score_min, "score_max": c.score_max, "qualitative": c.qualitative,
                 "quantitative": c.quantitative}
                for c in sorted(p.criteria, key=lambda c: -c.score_max)
            ],
            "metrics": [
                {
                    "id": m.id,
                    "code": m.code,
                    "name": m.name,
                    "unit": m.unit,
                    "data_type": m.data_type,
                    "description": m.description,
                    "thresholds": [
                        {"min_value": t.min_value, "max_value": t.max_value, "score": t.score} for t in m.thresholds
                    ],
                }
                for m in p.metrics
            ],
            "children": [conv(c, level + 1) for c in kids.get(p.id, [])],
        }

    sc = version.scorecard
    return {
        "id": version.id,
        "scorecard_id": sc.id,
        "scorecard_code": sc.code,
        "scorecard_name": sc.name,
        "subject_type": sc.subject_type.code,
        "subject_type_name": sc.subject_type.name,
        "version_no": version.version_no,
        "status": version.status,
        "purpose": version.purpose,
        "scope": version.scope,
        "objective": version.objective,
        "guidance": version.guidance,
        "target_score": version.target_score,
        "aggregation": version.aggregation,
        "max_depth": version.max_depth,
        "qtc_enabled": version.qtc_enabled,
        "required_judges": version.required_judges,
        "judge_tolerance_pct": version.judge_tolerance_pct,
        "require_self_appraisal": version.require_self_appraisal,
        "is_foundational": version.is_foundational,
        "requires_review": sc.requires_review,
        "change_note": version.change_note,
        "published_at": version.published_at,
        "rating_scale": scale_view(version.rating_scale),
        "parameters": [conv(p, 1) for p in kids.get(None, [])],
    }


def tree_stats(version: ScorecardVersion) -> tuple[int, int, int]:
    kids = _children_map(version)
    depth = 0

    def d(p: Parameter, lvl: int):
        nonlocal depth
        depth = max(depth, lvl)
        for c in kids.get(p.id, []):
            d(c, lvl + 1)

    for r in kids.get(None, []):
        d(r, 1)
    leaves = sum(1 for p in version.parameters if not kids.get(p.id))
    return len(version.parameters), leaves, depth


def scorecard_summary(db: Session, sc: Scorecard) -> dict:
    current = next((v for v in reversed(sc.versions) if v.status == "published"), sc.versions[-1])
    n, leaves, depth = tree_stats(current)
    evals = db.scalar(
        select(func.count(Evaluation.id))
        .join(ScorecardVersion)
        .where(ScorecardVersion.scorecard_id == sc.id, Evaluation.status != "void")
    )
    return {
        "id": sc.id,
        "code": sc.code,
        "name": sc.name,
        "subject_type": sc.subject_type.code,
        "subject_type_name": sc.subject_type.name,
        "owner": sc.owner,
        "tags": list(sc.tags or []),
        "is_template": sc.is_template,
        "requires_review": sc.requires_review,
        "purpose": current.purpose,
        "parameter_count": n,
        "leaf_count": leaves,
        "depth": depth,
        "evaluation_count": evals or 0,
        "versions": [
            {"id": v.id, "version_no": v.version_no, "status": v.status, "published_at": v.published_at,
             "created_at": v.created_at}
            for v in sc.versions
        ],
    }


def to_scoring_def(version: ScorecardVersion) -> scoring.ScorecardDef:
    scale = version.rating_scale
    return scoring.ScorecardDef(
        scale_min=scale.min_value,
        scale_max=scale.max_value,
        bands=[scoring.BandDef(b.label, b.lower_bound, b.rag, b.color_hex, b.font_hex) for b in scale.bands],
        target_score=version.target_score,
        aggregation=version.aggregation,
        qtc_enabled=version.qtc_enabled,
        params=[
            scoring.ParamDef(
                id=p.id,
                code=p.code,
                name=p.name,
                parent_id=p.parent_id,
                weight=p.weight,
                sort_order=p.sort_order,
                aggregation=p.aggregation,
                is_critical=p.is_critical,
                min_acceptable_score=p.min_acceptable_score,
                is_optional=p.is_optional,
                metrics=[
                    scoring.MetricDef(
                        id=m.id,
                        code=m.code,
                        thresholds=[scoring.ThresholdDef(t.min_value, t.max_value, t.score) for t in m.thresholds],
                    )
                    for m in p.metrics
                ],
            )
            for p in version.parameters
        ],
    )


# ---------------------------------------------------------------- evaluations


def load_version(db: Session, version_id: int) -> ScorecardVersion:
    v = db.scalar(
        select(ScorecardVersion)
        .where(ScorecardVersion.id == version_id)
        .options(
            selectinload(ScorecardVersion.parameters).selectinload(Parameter.metrics).selectinload(Metric.thresholds),
            selectinload(ScorecardVersion.parameters).selectinload(Parameter.criteria),
        )
    )
    if not v:
        raise DomainError("E404", f"Version {version_id} not found", 404)
    return v


def create_evaluation(db: Session, data: EvaluationCreate, commit: bool = True,
                      allow_unpublished: bool = False) -> Evaluation:
    """`allow_unpublished` is only for evaluations inside a submission, which pins the version it started on."""
    version = load_version(db, data.version_id)
    if version.status != "published" and not allow_unpublished:
        raise DomainError("E001", "Evaluations can only be created against a published scorecard version", 409)
    scale = version.rating_scale
    target = version.target_score if data.target_score is None else data.target_score
    if not (scale.min_value <= target <= scale.max_value):
        raise DomainError("V012", "Target is outside the rating scale")
    ev = Evaluation(
        version=version,
        subject_name=data.subject_name,
        subject_ref=data.subject_ref,
        input_text=data.input_text,
        evaluator_type=data.evaluator_type,
        evaluator_name=data.evaluator_name,
        is_private=data.evaluator_type == "self" if data.is_private is None else data.is_private,
        target_score=target,
        attempt_no=data.attempt_no,
        notes=data.notes,
        status="draft",
    )
    kids = _children_map(version)
    ev.results = [ParameterResult(parameter_id=p.id, is_leaf=not kids.get(p.id)) for p in version.parameters]
    db.add(ev)
    db.flush()
    recompute(ev)
    if commit:
        db.commit()
    return ev


def _require_draft(ev: Evaluation):
    if ev.status != "draft":
        raise DomainError("E006", f"Evaluation is {ev.status} and can no longer be changed", 409)


def apply_update(db: Session, ev: Evaluation, upd: EvaluationUpdate, commit: bool = True) -> Evaluation:
    _require_draft(ev)
    version = ev.version
    scale = version.rating_scale
    results = {r.parameter_id: r for r in ev.results}
    params = {p.id: p for p in version.parameters}
    metrics = {m.id: m for p in version.parameters for m in p.metrics}

    rated = [r.parameter_id for r in upd.ratings]
    if len(rated) != len(set(rated)):
        raise DomainError("E016", "The same parameter is rated more than once in one request")
    metric_ids = [mv.metric_id for mv in upd.metric_values]
    if len(metric_ids) != len(set(metric_ids)):
        raise DomainError("E016", "The same metric is given more than once in one request")

    for r in upd.ratings:
        res = results.get(r.parameter_id)
        if res is None:
            raise DomainError("E008", f"Parameter {r.parameter_id} is not part of this scorecard version")
        if not res.is_leaf:
            raise DomainError("E003", f"'{params[r.parameter_id].name}' is a parent; parents are rolled up, not rated")
        if r.not_applicable and not params[r.parameter_id].is_optional:
            raise DomainError("E004", f"'{params[r.parameter_id].name}' is required and cannot be marked N/A")
        if r.judged_score is not None:
            if r.judged_score != int(r.judged_score):
                raise DomainError("E012", "Judged scores must be whole numbers on the rating scale")
            if not (scale.min_value <= r.judged_score <= scale.max_value):
                raise DomainError(
                    "E002", f"Score {r.judged_score} is outside the scale {scale.min_value}–{scale.max_value}"
                )
        if r.override_reason and r.judged_score is None:
            raise DomainError("E010", "An override reason needs a judged score to override with")
        res.judged_score = r.judged_score
        res.not_applicable = r.not_applicable
        res.rationale, res.evidence = r.rationale, r.evidence
        res.confidence, res.override_reason = r.confidence, (r.override_reason or None)

    existing = {mv.metric_id: mv for mv in ev.metric_values}
    for mv in upd.metric_values:
        m = metrics.get(mv.metric_id)
        if m is None:
            raise DomainError("E008", f"Metric {mv.metric_id} is not part of this scorecard version")
        if mv.value is None:
            if mv.metric_id in existing:
                ev.metric_values.remove(existing[mv.metric_id])
            continue
        if (m.data_type == "boolean" and mv.value not in (0, 1)) or (
            m.data_type == "percent" and not 0 <= mv.value <= 100
        ) or (m.data_type == "count" and (mv.value < 0 or mv.value != int(mv.value))):
            raise DomainError("E013", f"Value {mv.value} is invalid for {m.data_type} metric '{m.code}'")
        if mv.metric_id in existing:
            row = existing[mv.metric_id]
            row.value, row.source, row.note = mv.value, mv.source, mv.note
        else:
            ev.metric_values.append(MetricValue(metric_id=mv.metric_id, value=mv.value, source=mv.source, note=mv.note))

    fields = upd.model_fields_set
    for f in ("subject_name", "input_text", "summary", "notes"):
        if f in fields and getattr(upd, f) is not None:
            setattr(ev, f, getattr(upd, f))
    if "time_met" in fields:
        ev.time_met = upd.time_met
    if "cost_met" in fields:
        ev.cost_met = upd.cost_met
    if upd.target_score is not None:
        if not (scale.min_value <= upd.target_score <= scale.max_value):
            raise DomainError("V012", "Target is outside the rating scale")
        ev.target_score = upd.target_score

    db.flush()
    recompute(ev)
    if commit:
        db.commit()
    return ev


def recompute(ev: Evaluation) -> scoring.EvaluationOutcome:
    card = to_scoring_def(ev.version)
    leaf_inputs = {
        r.parameter_id: scoring.LeafInput(r.judged_score, r.not_applicable, r.override_reason)
        for r in ev.results
        if r.is_leaf
    }
    values = {mv.metric_id: mv.value for mv in ev.metric_values}
    out = scoring.compute(card, leaf_inputs, values, ev.time_met, ev.cost_met, ev.target_score)
    for r in ev.results:
        o = out.params[r.parameter_id]
        r.computed_score, r.final_score = o.computed_score, o.final_score
        r.score_source, r.effective_weight = o.score_source, o.effective_weight
        r.band_label = o.band.label if o.band else None
    ev.final_score = out.final_score
    ev.band_label = out.band.label if out.band else None
    ev.rag = out.band.rag if out.band else None
    ev.quality_met, ev.qtc_green = out.quality_met, out.qtc_green
    ev.gate_failures = out.gate_failures
    return out


def complete_evaluation(db: Session, ev: Evaluation, commit: bool = True) -> Evaluation:
    _require_draft(ev)
    if ev.submission is not None:
        allowed = ("open",) if ev.evaluator_type == "self" else ("in_review",)
        if ev.submission.status not in allowed:
            raise DomainError("S009", f"The submission is {ev.submission.status}; this "
                              f"{'self-appraisal' if ev.evaluator_type == 'self' else 'judge evaluation'} "
                              "can no longer be completed", 409)
    out = recompute(ev)
    if not out.complete:
        names = {p.id: f"{p.code} {p.name}" for p in ev.version.parameters}
        raise DomainError(
            "E005",
            "Every required leaf parameter needs a score (or metric values) before completion",
            details=[names[i] for i in out.pending_leaf_ids],
        )
    # inside a submission, time and cost are facts of the submission (due date, budget, actual cost), not of a judge
    if ev.version.qtc_enabled and ev.submission is None and (ev.time_met is None or ev.cost_met is None):
        raise DomainError("E007", "This scorecard applies the QTC rule: record whether time and cost were met")
    ev.status, ev.completed_at = "completed", now()
    if commit:
        db.commit()
    return ev


def void_evaluation(db: Session, ev: Evaluation, reason: str) -> Evaluation:
    if ev.status == "void":
        raise DomainError("E006", "Evaluation is already void", 409)
    ev.status, ev.voided_reason = "void", reason
    db.commit()
    return ev


def evaluation_view(ev: Evaluation) -> dict:
    results = {r.parameter_id: r for r in ev.results}
    values = {mv.metric_id: mv for mv in ev.metric_values}
    version = version_view(ev.version)

    def attach(nodes: list[dict]):
        for n in nodes:
            r = results.get(n["id"])
            n["result"] = (
                {
                    "judged_score": r.judged_score,
                    "computed_score": r.computed_score,
                    "final_score": r.final_score,
                    "score_source": r.score_source,
                    "not_applicable": r.not_applicable,
                    "rationale": r.rationale,
                    "evidence": r.evidence,
                    "confidence": r.confidence,
                    "override_reason": r.override_reason,
                    "effective_weight": r.effective_weight,
                    "band_label": r.band_label,
                }
                if r
                else None
            )
            for m in n["metrics"]:
                mv = values.get(m["id"])
                m["value"] = mv.value if mv else None
                m["value_source"] = mv.source if mv else None
                m["value_note"] = mv.note if mv else None
            attach(n["children"])

    attach(version["parameters"])
    pending = [r.parameter_id for r in ev.results if r.is_leaf and r.score_source == "pending"]
    return {
        "id": ev.id,
        "status": ev.status,
        "subject_name": ev.subject_name,
        "subject_ref": ev.subject_ref,
        "input_text": ev.input_text,
        "evaluator_type": ev.evaluator_type,
        "evaluator_name": ev.evaluator_name,
        "judge_model": ev.judge_model,
        "is_private": ev.is_private,
        "target_score": ev.target_score,
        "time_met": ev.time_met,
        "cost_met": ev.cost_met,
        "attempt_no": ev.attempt_no,
        "origin": ev.origin,
        "origin_ref": ev.origin_ref,
        "submission_id": ev.submission_id,
        "final_score": ev.final_score,
        "band_label": ev.band_label,
        "rag": ev.rag,
        "quality_met": ev.quality_met,
        "qtc_green": ev.qtc_green,
        "gate_failures": ev.gate_failures or [],
        "pending_parameter_ids": pending,
        "summary": ev.summary,
        "notes": ev.notes,
        "created_at": ev.created_at,
        "completed_at": ev.completed_at,
        "voided_reason": ev.voided_reason,
        "documents": [
            {"id": d.id, "filename": d.filename, "media_type": d.media_type, "chars": len(d.content_text)}
            for d in ev.documents
        ],
        "version": version,
    }


def evaluation_row(ev: Evaluation) -> dict:
    sc = ev.version.scorecard
    return {
        "id": ev.id,
        "scorecard_id": sc.id,
        "scorecard_name": sc.name,
        "version_id": ev.version_id,
        "version_no": ev.version.version_no,
        "subject_name": ev.subject_name,
        "subject_ref": ev.subject_ref,
        "evaluator_type": ev.evaluator_type,
        "evaluator_name": ev.evaluator_name,
        "status": ev.status,
        "final_score": ev.final_score,
        "target_score": ev.target_score,
        "band_label": ev.band_label,
        "rag": ev.rag,
        "quality_met": ev.quality_met,
        "qtc_green": ev.qtc_green,
        "is_private": ev.is_private,
        "origin": ev.origin,
        "submission_id": ev.submission_id,
        "created_at": ev.created_at,
        "completed_at": ev.completed_at,
    }


# ---------------------------------------------------------------- documents

MAX_DOC_CHARS = 400_000


def extract_text(filename: str, data: bytes) -> str:
    try:
        return _extract_text(filename, data)
    except DomainError:
        raise
    except Exception as e:  # corrupt or truncated DOCX/PDF: any parser error is a bad file, not a server error
        raise DomainError("E015", f"Could not read '{filename}': the file is corrupt or not a valid document") from e


def _extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".docx"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
        text = "\n".join("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in paras)
        return _unescape(text)
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as e:  # pragma: no cover - optional dependency
            raise DomainError("E015", "PDF support needs the 'pypdf' package") from e
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DomainError("E015", "Unsupported file: upload text, markdown, CSV, JSON, DOCX or PDF") from e


def _unescape(s: str) -> str:
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")


def add_document(db: Session, ev: Evaluation, filename: str, media_type: str | None, data: bytes) -> EvaluationDocument:
    _require_draft(ev)
    text = extract_text(filename, data).strip()
    if not text:
        raise DomainError("E015", "No text could be extracted from the document")
    if len(text) > MAX_DOC_CHARS:
        raise DomainError("E015", f"Document is too large ({len(text)} chars; limit {MAX_DOC_CHARS})")
    doc = EvaluationDocument(filename=filename, media_type=media_type, content_text=text)
    ev.documents.append(doc)
    db.commit()
    return doc
