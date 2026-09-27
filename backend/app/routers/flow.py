"""Cycle 3 endpoints: scorecard review, subjects, submissions (quality gate), diagnosis, behaviour analytics.

Workflow actions require an actor (header `X-Actor`); see docs/10_CYCLE3_BEHAVIOUR_SPEC.md.
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services as svc
from .. import services_flow as flow
from .. import workflow as wf
from ..db import get_session
from ..models import AuditEvent, Subject, Submission

router = APIRouter(prefix="/api")


def actor(x_actor: str | None = Header(default=None)) -> str:
    return wf.require_actor(x_actor)


def _subject(db: Session, subject_id: int) -> Subject:
    s = db.get(Subject, subject_id)
    if not s:
        raise svc.DomainError("E404", f"Subject {subject_id} not found", 404)
    return s


def _submission(db: Session, submission_id: int) -> Submission:
    s = db.get(Submission, submission_id)
    if not s:
        raise svc.DomainError("E404", f"Submission {submission_id} not found", 404)
    return s


# ---------------------------------------------------------------- scorecard review


@router.post("/versions/{version_id}/submit-for-review")
def submit_for_review(version_id: int, body: flow.CommentIn, who: str = Depends(actor),
                      db: Session = Depends(get_session)):
    v = svc.load_version(db, version_id)
    flow.submit_for_review(db, v, who, body.comment)
    return svc.version_view(v)


@router.post("/versions/{version_id}/approve")
def approve(version_id: int, body: flow.CommentIn, who: str = Depends(actor), db: Session = Depends(get_session)):
    v = svc.load_version(db, version_id)
    flow.approve(db, v, who, body.comment)
    return svc.version_view(v)


@router.post("/versions/{version_id}/request-changes")
def request_changes(version_id: int, body: flow.CommentIn, who: str = Depends(actor),
                    db: Session = Depends(get_session)):
    v = svc.load_version(db, version_id)
    flow.request_changes(db, v, who, body.comment)
    return svc.version_view(v)


@router.post("/versions/{version_id}/retire")
def retire(version_id: int, body: flow.ReasonIn, who: str = Depends(actor), db: Session = Depends(get_session)):
    v = svc.load_version(db, version_id)
    flow.retire(db, v, who, body.reason)
    return svc.version_view(v)


@router.get("/versions/{version_id}/reviews")
def reviews(version_id: int, db: Session = Depends(get_session)):
    return flow.review_history(db, version_id)


# ---------------------------------------------------------------- subjects


@router.get("/subjects")
def subjects(db: Session = Depends(get_session)):
    """The subject forest with roll-up status (a project is green only if everything beneath it is green)."""
    return flow.subject_forest(db)


@router.post("/subjects", status_code=201)
def create_subject(body: flow.SubjectIn, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.rollup(flow.create_subject(db, body, who))


@router.get("/subjects/{subject_id}")
def get_subject(subject_id: int, db: Session = Depends(get_session)):
    s = _subject(db, subject_id)
    path = []
    node = s.parent
    while node is not None:
        path.insert(0, {"id": node.id, "name": node.name, "code": node.code})
        node = node.parent
    return {**flow.rollup(s), "path": path, "description": s.description,
            "blocked_by": [{"id": b.id, "name": b.name} for b in flow.blockers_in_project(s)],
            "submissions": flow.submissions_list(db, subject_id=s.id)}


@router.patch("/subjects/{subject_id}")
def update_subject(subject_id: int, body: flow.SubjectUpdate, who: str = Depends(actor),
                   db: Session = Depends(get_session)):
    return flow.rollup(flow.update_subject(db, _subject(db, subject_id), body, who))


# ---------------------------------------------------------------- submissions


@router.get("/submissions")
def submissions(subject_id: int | None = None, status: str | None = None, owner: str | None = None,
                db: Session = Depends(get_session)):
    return flow.submissions_list(db, subject_id, status, owner)


@router.post("/subjects/{subject_id}/submissions", status_code=201)
def start_submission(subject_id: int, body: flow.SubmissionIn, who: str = Depends(actor),
                     db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.start_submission(db, _subject(db, subject_id), body, who), who)


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: int, x_actor: str | None = Header(default=None), db: Session = Depends(get_session)):
    return flow.submission_view(db, _submission(db, submission_id), x_actor)


@router.patch("/submissions/{submission_id}")
def update_submission(submission_id: int, body: flow.SubmissionUpdate, who: str = Depends(actor),
                      db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.update_submission(db, _submission(db, submission_id), body, who), who)


@router.post("/submissions/{submission_id}/evaluations", status_code=201)
def add_evaluation(submission_id: int, body: flow.SubmissionEvaluationIn, who: str = Depends(actor),
                   db: Session = Depends(get_session)):
    ev = flow.add_evaluation(db, _submission(db, submission_id), body, who)
    return svc.evaluation_view(ev)


@router.post("/submissions/{submission_id}/submit")
def submit(submission_id: int, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.submit(db, _submission(db, submission_id), who), who)


@router.post("/submissions/{submission_id}/withdraw")
def withdraw(submission_id: int, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.withdraw(db, _submission(db, submission_id), who), who)


@router.post("/submissions/{submission_id}/cancel")
def cancel(submission_id: int, body: flow.ReasonIn, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.cancel(db, _submission(db, submission_id), who, body.reason), who)


@router.post("/submissions/{submission_id}/decide")
def decide(submission_id: int, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.decide(db, _submission(db, submission_id), who), who)


@router.post("/submissions/{submission_id}/adjudicate")
def adjudicate(submission_id: int, body: flow.AdjudicationIn, who: str = Depends(actor),
               db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.adjudicate(db, _submission(db, submission_id), who, body), who)


# ---------------------------------------------------------------- diagnosis & behaviour analytics


@router.get("/attention")
def attention(threshold: int = flow.RED_THRESHOLD, window_days: int = flow.RED_WINDOW_DAYS,
              db: Session = Depends(get_session)):
    return {"threshold": threshold, "window_days": window_days,
            "people": flow.attention_list(db, threshold, window_days)}


@router.post("/diagnoses", status_code=201)
def record_diagnosis(body: flow.DiagnosisIn, who: str = Depends(actor), db: Session = Depends(get_session)):
    d = flow.record_diagnosis(db, body, who)
    return {"id": d.id, "person": d.person, "cause": d.cause, "action": d.action}


@router.get("/diagnoses")
def diagnoses(person: str | None = None, db: Session = Depends(get_session)):
    return flow.diagnoses(db, person)


@router.get("/analytics/behaviour")
def behaviour(db: Session = Depends(get_session)):
    return {"gates": flow.gate_outcomes(db), "self_appraisal": flow.self_appraisal_gap(db),
            "disputed_parameters": flow.disputed_parameters(db)}


@router.get("/audit")
def audit(entity: str, entity_id: int, db: Session = Depends(get_session)):
    rows = db.scalars(select(AuditEvent).where(AuditEvent.entity == entity, AuditEvent.entity_id == entity_id)
                      .order_by(AuditEvent.id))
    return [{"action": e.action, "from": e.from_state, "to": e.to_state, "actor": e.actor, "at": e.at,
             "details": e.details} for e in rows]
