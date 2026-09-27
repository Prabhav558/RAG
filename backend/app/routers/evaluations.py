from fastapi import APIRouter, Depends, File, Header, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import analytics
from .. import services as svc
from .. import workflow as wf
from ..db import get_session
from ..judge import Judge, JudgeError, get_judge
from ..models import Evaluation, ScorecardVersion
from ..schemas import EvaluationCreate, EvaluationUpdate, MetricValueIn, RatingIn, VoidRequest

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _evaluation(db: Session, evaluation_id: int) -> Evaluation:
    ev = db.get(Evaluation, evaluation_id)
    if not ev:
        raise svc.DomainError("E404", f"Evaluation {evaluation_id} not found", 404)
    return ev


def _check_editor(ev: Evaluation, actor: str | None):
    """Inside a submission, a self-appraisal belongs to the owner and a human judgement to its judge."""
    if ev.submission is None:
        return
    if ev.evaluator_type == "self" and not wf.same_person(actor, ev.submission.owner):
        raise svc.DomainError("S011", f"This self-appraisal is private to {ev.submission.owner}", 403)
    if ev.evaluator_type == "human" and not wf.same_person(actor, ev.evaluator_name):
        raise svc.DomainError("S003", f"Only {ev.evaluator_name} can change their own judgement", 403)


@router.get("/evaluations")
def list_evaluations(
    scorecard_id: int | None = None,
    status: str | None = None,
    include_private: bool = False,
    limit: int = 200,
    db: Session = Depends(get_session),
):
    q = select(Evaluation).join(ScorecardVersion).order_by(Evaluation.id.desc()).limit(min(limit, 1000))
    if scorecard_id:
        q = q.where(ScorecardVersion.scorecard_id == scorecard_id)
    if status:
        q = q.where(Evaluation.status == status)
    if not include_private:
        q = q.where(Evaluation.is_private.is_(False))
    return [svc.evaluation_row(e) for e in db.scalars(q)]


@router.post("/evaluations", status_code=201)
def create_evaluation(body: EvaluationCreate, db: Session = Depends(get_session)):
    return svc.evaluation_view(svc.create_evaluation(db, body))


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: int, x_actor: str | None = Header(default=None), db: Session = Depends(get_session)):
    ev = _evaluation(db, evaluation_id)
    if ev.submission is not None and ev.evaluator_type == "self" and not wf.same_person(x_actor, ev.submission.owner):
        raise svc.DomainError("S011", f"This self-appraisal is private to {ev.submission.owner}", 403)
    return svc.evaluation_view(ev)


@router.put("/evaluations/{evaluation_id}")
def update_evaluation(evaluation_id: int, body: EvaluationUpdate, x_actor: str | None = Header(default=None),
                      db: Session = Depends(get_session)):
    ev = _evaluation(db, evaluation_id)
    _check_editor(ev, x_actor)
    return svc.evaluation_view(svc.apply_update(db, ev, body))


@router.post("/evaluations/{evaluation_id}/documents", status_code=201)
async def upload_document(evaluation_id: int, file: UploadFile = File(...), x_actor: str | None = Header(default=None),
                          db: Session = Depends(get_session)):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise svc.DomainError("E015", "File is larger than 20 MB")
    ev = _evaluation(db, evaluation_id)
    _check_editor(ev, x_actor)
    svc.add_document(db, ev, file.filename or "upload", file.content_type, data)
    return svc.evaluation_view(ev)


@router.post("/evaluations/{evaluation_id}/llm-judge")
def run_llm_judge(evaluation_id: int, db: Session = Depends(get_session), judge: Judge = Depends(get_judge)):
    """LLM first, human second: the judge proposes leaf scores; a human can then adjust before completing."""
    ev = _evaluation(db, evaluation_id)
    if ev.status != "draft":
        raise svc.DomainError("E006", "Only draft evaluations can be judged", 409)
    version = svc.version_view(ev.version)
    parts = [ev.input_text or ""] + [f"--- Document: {d.filename} ---\n{d.content_text}" for d in ev.documents]
    try:
        result = judge.evaluate(version, ev.subject_name, "\n\n".join(p for p in parts if p))
    except JudgeError as e:
        raise svc.DomainError("J001", str(e), e.status) from e

    by_code = {p.code: p for p in ev.version.parameters}
    metric_ids = {f"{p.code}#{m.code}": m.id for p in ev.version.parameters for m in p.metrics}
    existing = {r.parameter_id: r for r in ev.results}
    ratings = [
        RatingIn(
            parameter_id=by_code[r.parameter_code].id,
            judged_score=r.score,
            rationale=r.rationale,
            evidence=r.evidence,
            confidence=r.confidence,
            not_applicable=existing[by_code[r.parameter_code].id].not_applicable,
        )
        for r in result.ratings
    ]
    metrics = [
        MetricValueIn(metric_id=metric_ids[m.metric_code], value=m.value, source="llm", note=m.note)
        for m in result.metric_values
    ]
    ev.judge_model = result.model
    svc.apply_update(db, ev, EvaluationUpdate(ratings=ratings, metric_values=metrics, summary=result.summary))
    view = svc.evaluation_view(ev)
    view["judge_unrated"] = len(view["pending_parameter_ids"])
    return view


@router.post("/evaluations/{evaluation_id}/complete")
def complete(evaluation_id: int, x_actor: str | None = Header(default=None), db: Session = Depends(get_session)):
    ev = _evaluation(db, evaluation_id)
    _check_editor(ev, x_actor)
    return svc.evaluation_view(svc.complete_evaluation(db, ev))


@router.post("/evaluations/{evaluation_id}/void")
def void(evaluation_id: int, body: VoidRequest, db: Session = Depends(get_session)):
    return svc.evaluation_view(svc.void_evaluation(db, _evaluation(db, evaluation_id), body.reason))


# ---------------------------------------------------------------- analytics


@router.get("/analytics/overview")
def analytics_overview(scorecard_id: int | None = None, db: Session = Depends(get_session)):
    data = analytics.overview(db, scorecard_id)
    data["library"] = analytics.library_stats(db)
    return data


@router.get("/analytics/parameters/{version_id}")
def analytics_parameters(version_id: int, db: Session = Depends(get_session)):
    return analytics.parameter_breakdown(db, version_id)


@router.get("/analytics/judge-agreement")
def analytics_agreement(
    scorecard_id: int | None = None, tolerance_pct: float = 10.0, db: Session = Depends(get_session)
):
    return analytics.judge_agreement(db, scorecard_id, tolerance_pct)


@router.get("/analytics/trend")
def analytics_trend(scorecard_id: int | None = None, db: Session = Depends(get_session)):
    return analytics.trend(db, scorecard_id)
