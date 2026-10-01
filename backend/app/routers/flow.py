"""Cycle 3 endpoints: scorecard review, subjects, submissions (quality gate), diagnosis, behaviour analytics.

Workflow actions require a logged-in session (Authorization: Bearer <token>); the actor is the authenticated
user's display name, never a client-supplied value.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from .. import services as svc
from .. import services_flow as flow
from .. import workflow as wf
from ..clarity import ClarityAgent, ClarityError, get_clarity_agent
from ..db import get_session
from ..models import AuditEvent, Subject, Submission

router = APIRouter(prefix="/api")

actor = auth.actor_name
require_designer = auth.require_role("designer")
require_reviewer = auth.require_role("reviewer")
require_lead = auth.require_role("lead")


def _subject(db: Session, subject_id: int) -> Subject:
    s = db.get(Subject, subject_id)
    if not s:
        raise svc.DomainError("E404", f"Subject {subject_id} not found", 404)
    return s


def _submission(db: Session, submission_id: int, lock: bool = False) -> Submission:
    """`lock` takes a row lock (SELECT ... FOR UPDATE) so concurrent workflow actions on one submission serialise;
    without it two simultaneous 'decide' calls could both pass the state check. SQLite ignores the hint."""
    s = db.get(Submission, submission_id, with_for_update=lock)
    if not s:
        raise svc.DomainError("E404", f"Submission {submission_id} not found", 404)
    return s


# ---------------------------------------------------------------- scorecard review


@router.post("/versions/{version_id}/submit-for-review")
def submit_for_review(version_id: int, body: flow.CommentIn, who: str = Depends(actor),
                      _: object = Depends(require_designer), db: Session = Depends(get_session)):
    v = svc.load_version(db, version_id, lock=True)
    flow.submit_for_review(db, v, who, body.comment)
    return svc.version_view(v)


@router.post("/versions/{version_id}/approve")
def approve(version_id: int, body: flow.CommentIn, who: str = Depends(actor),
           _: object = Depends(require_reviewer), db: Session = Depends(get_session)):
    v = svc.load_version(db, version_id, lock=True)
    flow.approve(db, v, who, body.comment)
    return svc.version_view(v)


@router.post("/versions/{version_id}/request-changes")
def request_changes(version_id: int, body: flow.CommentIn, who: str = Depends(actor),
                    _: object = Depends(require_reviewer), db: Session = Depends(get_session)):
    v = svc.load_version(db, version_id, lock=True)
    flow.request_changes(db, v, who, body.comment)
    return svc.version_view(v)


@router.post("/versions/{version_id}/retire")
def retire(version_id: int, body: flow.ReasonIn, who: str = Depends(actor),
          _: object = Depends(require_designer), db: Session = Depends(get_session)):
    v = svc.load_version(db, version_id, lock=True)
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
            "objective": s.objective, "deliverable": s.deliverable, "quality_bar": s.quality_bar, "risks": s.risks,
            "blocked_by": [{"id": b.id, "name": b.name} for b in flow.blockers_in_project(s)],
            "submissions": flow.submissions_list(db, subject_id=s.id)}


@router.patch("/subjects/{subject_id}")
def update_subject(subject_id: int, body: flow.SubjectUpdate, who: str = Depends(actor),
                   db: Session = Depends(get_session)):
    return flow.rollup(flow.update_subject(db, _subject(db, subject_id), body, who))


@router.post("/subjects/{subject_id}/clarity-check")
def clarity_check(subject_id: int, db: Session = Depends(get_session),
                  agent: ClarityAgent = Depends(get_clarity_agent)):
    """Advisory only: reviews the subject's ODTQRC task definition for vagueness. Never changes the subject."""
    s = _subject(db, subject_id)
    task = {"name": s.name, "description": s.description, "objective": s.objective, "deliverable": s.deliverable,
            "due_at": s.due_at.isoformat() if s.due_at else None, "quality_bar": s.quality_bar, "risks": s.risks,
            "budget": s.budget}
    try:
        result = agent.review(task)
    except ClarityError as e:
        raise svc.DomainError("J002", str(e), e.status) from e
    return {"model": result.model, "is_clear": result.is_clear, "summary": result.summary,
            "issues": [{"field": i.field, "problem": i.problem, "suggestion": i.suggestion} for i in result.issues]}


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
def get_submission(submission_id: int, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.submission_view(db, _submission(db, submission_id), who)


@router.patch("/submissions/{submission_id}")
def update_submission(submission_id: int, body: flow.SubmissionUpdate, who: str = Depends(actor),
                      db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.update_submission(db, _submission(db, submission_id, lock=True), body, who), who)


@router.post("/submissions/{submission_id}/evaluations", status_code=201)
def add_evaluation(submission_id: int, body: flow.SubmissionEvaluationIn, who: str = Depends(actor),
                   db: Session = Depends(get_session)):
    ev = flow.add_evaluation(db, _submission(db, submission_id, lock=True), body, who)
    return svc.evaluation_view(ev)


@router.post("/submissions/{submission_id}/submit")
def submit(submission_id: int, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.submit(db, _submission(db, submission_id, lock=True), who), who)


@router.post("/submissions/{submission_id}/withdraw")
def withdraw(submission_id: int, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.withdraw(db, _submission(db, submission_id, lock=True), who), who)


@router.post("/submissions/{submission_id}/cancel")
def cancel(submission_id: int, body: flow.ReasonIn, who: str = Depends(actor),
          _: object = Depends(require_lead), db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.cancel(db, _submission(db, submission_id, lock=True), who, body.reason), who)


@router.post("/submissions/{submission_id}/decide")
def decide(submission_id: int, who: str = Depends(actor), db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.decide(db, _submission(db, submission_id, lock=True), who), who)


@router.post("/submissions/{submission_id}/adjudicate")
def adjudicate(submission_id: int, body: flow.AdjudicationIn, who: str = Depends(actor),
               db: Session = Depends(get_session)):
    return flow.submission_view(db, flow.adjudicate(db, _submission(db, submission_id, lock=True), who, body), who)


# ---------------------------------------------------------------- diagnosis & behaviour analytics


@router.get("/attention")
def attention(threshold: int = flow.RED_THRESHOLD, window_days: int = flow.RED_WINDOW_DAYS,
              db: Session = Depends(get_session)):
    return {"threshold": threshold, "window_days": window_days,
            "people": flow.attention_list(db, threshold, window_days)}


@router.post("/diagnoses", status_code=201)
def record_diagnosis(body: flow.DiagnosisIn, who: str = Depends(actor), _: object = Depends(require_lead),
                     db: Session = Depends(get_session)):
    d = flow.record_diagnosis(db, body, who)
    return {"id": d.id, "person": d.person, "cause": d.cause, "action": d.action}


@router.get("/diagnoses")
def diagnoses(person: str | None = None, who: str = Depends(actor), user=Depends(auth.get_current_user),
             db: Session = Depends(get_session)):
    # Diagnosis notes are sensitive personal performance data (spec §5): only lead/admin see everyone's;
    # anyone else sees only their own, whatever `person` they ask for.
    is_lead = "lead" in user.roles or "admin" in user.roles
    return flow.diagnoses(db, person if is_lead else who)


@router.post("/capabilities", status_code=201)
def record_capability(body: flow.CapabilityIn, who: str = Depends(actor), _: object = Depends(require_lead),
                      db: Session = Depends(get_session)):
    c = flow.record_capability(db, body, who)
    return {"id": c.id, "person": c.person, "level": c.level, "level_label": flow.LEVEL_LABELS[c.level]}


@router.get("/capabilities")
def capabilities(person: str | None = None, current: bool = False, who: str = Depends(actor),
                 user=Depends(auth.get_current_user), db: Session = Depends(get_session)):
    # Same privacy rule as diagnoses: a capability assessment is personal performance data.
    is_lead = "lead" in user.roles or "admin" in user.roles
    target = person if is_lead else who
    return flow.current_capabilities(db, target) if current else flow.capabilities(db, target)


@router.get("/analytics/behaviour")
def behaviour(db: Session = Depends(get_session)):
    return {"gates": flow.gate_outcomes(db), "self_appraisal": flow.self_appraisal_gap(db),
            "disputed_parameters": flow.disputed_parameters(db)}


@router.get("/analytics/risk-forecast")
def risk_forecast(who: str = Depends(actor), user=Depends(auth.get_current_user), db: Session = Depends(get_session)):
    """Predictive (risk score + factors) and prescriptive (recommended_action) analytics over open submissions.
    Same privacy rule as diagnoses and capabilities: a person's own risk is theirs to see; everyone's is lead/admin
    only, since the factors include personal track record."""
    rows = flow.risk_forecast(db)
    is_lead = "lead" in user.roles or "admin" in user.roles
    return rows if is_lead else [r for r in rows if wf.same_person(r["owner"], who)]


@router.get("/audit")
def audit(entity: str, entity_id: int, db: Session = Depends(get_session)):
    rows = db.scalars(select(AuditEvent).where(AuditEvent.entity == entity, AuditEvent.entity_id == entity_id)
                      .order_by(AuditEvent.id))
    return [{"action": e.action, "from": e.from_state, "to": e.to_state, "actor": e.actor, "at": e.at,
             "details": e.details} for e in rows]
