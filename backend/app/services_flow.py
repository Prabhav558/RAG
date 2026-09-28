"""Cycle 3 services: scorecard review, subjects, submissions (the quality gate), roll-up, red diagnosis.

Behaviour spec: docs/10_CYCLE3_BEHAVIOUR_SPEC.md. Every state change goes through workflow.transition().
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import scoring
from . import services as svc
from . import workflow as wf
from .models import (
    AuditEvent,
    Capability,
    Diagnosis,
    Evaluation,
    ParameterResult,
    Scorecard,
    ScorecardVersion,
    Subject,
    SubjectType,
    Submission,
    VersionReview,
)
from .schemas import INPUT_MAX, NAME_MAX, TEXT_MAX, Contract, EvaluationCreate

RED_THRESHOLD = int(os.environ.get("RED_THRESHOLD", "3"))
RED_WINDOW_DAYS = int(os.environ.get("RED_WINDOW_DAYS", "90"))
MAX_SUBJECT_DEPTH = 6
DomainError = svc.DomainError


# ---------------------------------------------------------------- contracts


class SubjectIn(Contract):
    code: str | None = Field(default=None, max_length=60, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
    name: str = Field(min_length=1, max_length=300)
    subject_type: str
    parent_id: int | None = None
    owner: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    due_at: datetime | None = None
    budget: float | None = Field(default=None, ge=0, le=1e12)
    # ODTQRC task definition: Objective, Deliverable, Time (due_at), Quality, Risk, Cost (budget)
    objective: str | None = Field(default=None, max_length=TEXT_MAX)
    deliverable: str | None = Field(default=None, max_length=TEXT_MAX)
    quality_bar: str | None = Field(default=None, max_length=TEXT_MAX)
    risks: str | None = Field(default=None, max_length=TEXT_MAX)


class SubjectUpdate(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    parent_id: int | None = None
    owner: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=TEXT_MAX)
    due_at: datetime | None = None
    budget: float | None = Field(default=None, ge=0, le=1e12)
    objective: str | None = Field(default=None, max_length=TEXT_MAX)
    deliverable: str | None = Field(default=None, max_length=TEXT_MAX)
    quality_bar: str | None = Field(default=None, max_length=TEXT_MAX)
    risks: str | None = Field(default=None, max_length=TEXT_MAX)


class SubmissionIn(Contract):
    version_id: int
    title: str | None = Field(default=None, max_length=300)
    input_text: str | None = Field(default=None, max_length=INPUT_MAX)


class SubmissionUpdate(Contract):
    title: str | None = Field(default=None, max_length=300)
    input_text: str | None = Field(default=None, max_length=INPUT_MAX)
    actual_cost: float | None = Field(default=None, ge=0, le=1e12)


class SubmissionEvaluationIn(Contract):
    evaluator_type: str = Field(pattern=r"^(self|human|llm)$")
    evaluator_name: str | None = Field(default=None, max_length=120)


class AdjudicationIn(Contract):
    verdict: str = Field(pattern=r"^(passed|redo)$")
    reason: str = Field(min_length=3, max_length=TEXT_MAX)


class ReasonIn(Contract):
    reason: str = Field(min_length=3, max_length=TEXT_MAX)


class CommentIn(Contract):
    comment: str | None = Field(default=None, max_length=TEXT_MAX)


class DiagnosisIn(Contract):
    person: str = Field(min_length=1, max_length=120)
    cause: str = Field(pattern=r"^(skill|aptitude|will|allocation)$")
    action: str = Field(pattern=r"^(train|reassign|discuss|rescope|none)$")
    notes: str | None = Field(default=None, max_length=TEXT_MAX)
    submission_id: int | None = None


LEVEL_LABELS = {1: "Unaware", 2: "Aware", 3: "Developing", 4: "Competent", 5: "Proficient", 6: "Expert"}


class CapabilityIn(Contract):
    person: str = Field(min_length=1, max_length=120)
    scorecard: str  # scorecard.code — the skill domain this level applies to
    level: int = Field(ge=1, le=6)
    notes: str | None = Field(default=None, max_length=TEXT_MAX)


# ---------------------------------------------------------------- scorecard review


def _review(db: Session, version: ScorecardVersion, action: str, actor: str, comment: str | None = None):
    db.add(VersionReview(version_id=version.id, action=action, actor=actor, comment=comment))


def submit_for_review(db: Session, version: ScorecardVersion, actor: str, comment: str | None = None):
    wf.check(wf.VERSION, version.status, "submit_for_review")
    svc._require_valid(version)
    wf.transition(db, wf.VERSION, version, "submit_for_review", actor, details={"comment": comment})
    _review(db, version, "submitted", actor, comment)
    db.commit()


def _submitter(db: Session, version: ScorecardVersion) -> str | None:
    return db.scalar(
        select(VersionReview.actor)
        .where(VersionReview.version_id == version.id, VersionReview.action == "submitted")
        .order_by(VersionReview.id.desc())
    )


def approve(db: Session, version: ScorecardVersion, actor: str, comment: str | None = None):
    wf.check(wf.VERSION, version.status, "approve")
    if wf.same_person(actor, _submitter(db, version)):
        raise DomainError("S003", "A scorecard cannot be approved by the person who submitted it for review", 403)
    svc._require_valid(version)
    svc.go_live(db, version, actor)
    wf.transition(db, wf.VERSION, version, "approve", actor, details={"comment": comment})
    _review(db, version, "approved", actor, comment)
    db.commit()


def request_changes(db: Session, version: ScorecardVersion, actor: str, comment: str | None):
    wf.check(wf.VERSION, version.status, "request_changes")
    if not (comment or "").strip():
        raise DomainError("S001", "Say what needs to change: a comment is required", 422)
    wf.transition(db, wf.VERSION, version, "request_changes", actor, details={"comment": comment})
    _review(db, version, "changes_requested", actor, comment)
    db.commit()


def retire(db: Session, version: ScorecardVersion, actor: str, reason: str):
    wf.transition(db, wf.VERSION, version, "retire", actor, details={"reason": reason})
    version.retired_at = svc.now()
    _review(db, version, "retired", actor, reason)
    db.commit()


def review_history(db: Session, version_id: int) -> list[dict]:
    rows = db.scalars(select(VersionReview).where(VersionReview.version_id == version_id).order_by(VersionReview.id))
    return [{"action": r.action, "actor": r.actor, "comment": r.comment, "at": r.at} for r in rows]


# ---------------------------------------------------------------- subjects


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:40] or "subject"


def _depth(subject: Subject | None) -> int:
    d = 0
    while subject is not None:
        d += 1
        subject = subject.parent
    return d


def _check_parent(db: Session, subject: Subject | None, parent_id: int | None) -> Subject | None:
    if parent_id is None:
        return None
    parent = db.get(Subject, parent_id)
    if not parent:
        raise DomainError("E008", f"Parent subject {parent_id} not found")
    node = parent
    while node is not None:  # cycle check
        if subject is not None and node.id == subject.id:
            raise DomainError("S008", "A subject cannot be placed under itself or one of its descendants")
        node = node.parent
    height = _height(subject) if subject is not None else 1
    if _depth(parent) + height > MAX_SUBJECT_DEPTH:
        raise DomainError("S008", f"Subject hierarchy deeper than {MAX_SUBJECT_DEPTH} levels")
    return parent


def _height(subject: Subject) -> int:
    return 1 + max((_height(c) for c in subject.children), default=0)


def create_subject(db: Session, data: SubjectIn, actor: str) -> Subject:
    st = db.scalar(select(SubjectType).where(SubjectType.code == data.subject_type))
    if not st:
        raise DomainError("E008", f"Unknown subject type '{data.subject_type}'")
    parent = _check_parent(db, None, data.parent_id)
    code = data.code or _slug(data.name)
    base, n = code, 2
    while db.scalar(select(Subject).where(Subject.code == code)):
        if data.code:
            raise DomainError("E011", f"Subject code '{code}' already exists", 409)
        code, n = f"{base}-{n}", n + 1
    s = Subject(code=code, name=data.name, subject_type=st, parent=parent, owner=data.owner.strip(),
                description=data.description, due_at=data.due_at, budget=data.budget,
                objective=data.objective, deliverable=data.deliverable, quality_bar=data.quality_bar,
                risks=data.risks)
    db.add(s)
    db.flush()
    wf.audit(db, "subject", s.id, "create", actor, details={"code": code})
    db.commit()
    return s


def update_subject(db: Session, s: Subject, data: SubjectUpdate, actor: str) -> Subject:
    fields = data.model_fields_set
    if "parent_id" in fields:
        s.parent = _check_parent(db, s, data.parent_id)
    always_nullable = ("description", "due_at", "budget", "objective", "deliverable", "quality_bar", "risks")
    for f in ("name", "owner", *always_nullable):
        if f in fields and (getattr(data, f) is not None or f in always_nullable):
            setattr(s, f, getattr(data, f))
    wf.audit(db, "subject", s.id, "update", actor, details={"fields": sorted(fields)})
    db.commit()
    return s


def _root(subject: Subject) -> Subject:
    while subject.parent is not None:
        subject = subject.parent
    return subject


def _descendants(subject: Subject):
    yield subject
    for c in subject.children:
        yield from _descendants(c)


def _latest_by_scorecard(subject: Subject) -> dict[int, list[Submission]]:
    groups: dict[int, list[Submission]] = defaultdict(list)
    for sub in subject.submissions:
        groups[sub.version.scorecard_id].append(sub)
    return groups


def is_blocked(subject: Subject) -> bool:
    for subs in _latest_by_scorecard(subject).values():
        decided = [x for x in subs if x.status == "decided"]
        if decided and decided[-1].blocks_project:
            return True
    return False


def blockers_in_project(subject: Subject) -> list[Subject]:
    return [s for s in _descendants(_root(subject)) if is_blocked(s)]


# ---------------------------------------------------------------- roll-up

ORDER = ["green", "not_started", "in_progress", "red", "blocked"]  # later = worse


def own_status(subject: Subject) -> str:
    groups = _latest_by_scorecard(subject)
    if not groups:
        return "not_started"
    statuses = []
    for subs in groups.values():
        decided = [x for x in subs if x.status == "decided"]
        live = [x for x in subs if x.status in ("open", "in_review", "adjudication")]
        if not decided:
            statuses.append("in_progress" if live else "not_started")
            continue
        last = decided[-1]
        if last.blocks_project:
            statuses.append("blocked")
        elif last.decision == "passed" and last.qtc_green is not False:
            statuses.append("green")
        else:
            statuses.append("red")
    return max(statuses, key=ORDER.index)


def rollup(subject: Subject) -> dict:
    kids = [rollup(c) for c in subject.children if c.archived_at is None]
    own = own_status(subject)
    candidates = [k["status"] for k in kids]
    if own != "not_started" or not kids:
        candidates.append(own)
    status = max(candidates, key=ORDER.index) if candidates else own
    counts = defaultdict(int)
    for k in kids:
        counts[k["status"]] += 1
        for key, v in k["descendant_counts"].items():
            counts[key] += v
    latest = None
    decided = [x for x in subject.submissions if x.status == "decided"]
    if decided:
        d = decided[-1]
        latest = {"submission_id": d.id, "scorecard": d.version.scorecard.name, "score": d.official_score,
                  "band": d.official_band, "rag": d.official_rag, "decision": d.decision, "qtc_green": d.qtc_green}
    active = [x for x in subject.submissions if x.status in ("open", "in_review", "adjudication")]
    return {
        "id": subject.id, "code": subject.code, "name": subject.name, "subject_type": subject.subject_type.code,
        "subject_type_name": subject.subject_type.name, "owner": subject.owner,
        "due_at": subject.due_at, "budget": subject.budget,
        "own_status": own, "status": status, "latest": latest,
        "active_submission": {"id": active[-1].id, "status": active[-1].status} if active else None,
        "descendant_counts": dict(counts), "children": kids,
    }


def subject_forest(db: Session) -> list[dict]:
    roots = db.scalars(
        select(Subject).where(Subject.parent_id.is_(None), Subject.archived_at.is_(None)).order_by(Subject.name)
        .options(selectinload(Subject.submissions).selectinload(Submission.version).selectinload(ScorecardVersion.scorecard))
    )
    return [rollup(r) for r in roots]


# ---------------------------------------------------------------- submissions

ACTIVE = ("open", "in_review", "adjudication")


def start_submission(db: Session, subject: Subject, data: SubmissionIn, actor: str) -> Submission:
    version = svc.load_version(db, data.version_id)
    if version.status != "published":
        raise DomainError("S010", "Submissions must use a published scorecard version", 409)
    same_card = [x for x in subject.submissions if x.version.scorecard_id == version.scorecard_id]
    if any(x.status in ACTIVE for x in same_card):
        raise DomainError("S001", "This subject already has an active submission for this scorecard; finish it first",
                          409)
    blockers = [b for b in blockers_in_project(subject) if b.id != subject.id]
    if blockers:
        raise DomainError("S007", "The project is stopped by a foundational red: "
                          + ", ".join(f"'{b.name}'" for b in blockers) + ". Fix it before starting other work.", 409)
    if version.qtc_enabled and (subject.due_at is None or subject.budget is None):
        raise DomainError("S006", "This scorecard applies the QTC rule: set the subject's due date and budget first")
    previous = same_card[-1] if same_card else None
    sub = Submission(subject=subject, version=version, owner=subject.owner,
                     attempt_no=max((x.attempt_no for x in same_card), default=0) + 1,
                     previous_id=previous.id if previous else None, title=data.title or subject.name,
                     input_text=data.input_text, status="open")
    db.add(sub)
    db.flush()
    wf.audit(db, wf.SUBMISSION, sub.id, "start", actor, None, "open",
             {"attempt_no": sub.attempt_no, "previous_id": sub.previous_id})
    db.commit()
    return sub


def update_submission(db: Session, sub: Submission, data: SubmissionUpdate, actor: str) -> Submission:
    if sub.status in wf.TERMINAL[wf.SUBMISSION]:
        raise DomainError("S001", f"Submission is {sub.status} and can no longer be changed", 409)
    fields = data.model_fields_set
    if ("title" in fields or "input_text" in fields) and sub.status != "open":
        raise DomainError("S001", "The work can only be changed while the submission is open", 409)
    for f in fields:
        setattr(sub, f, getattr(data, f))
    wf.audit(db, wf.SUBMISSION, sub.id, "update", actor, details={"fields": sorted(fields)})
    db.commit()
    return sub


def add_evaluation(db: Session, sub: Submission, data: SubmissionEvaluationIn, actor: str) -> Evaluation:
    """`actor` is the verified (logged-in) identity performing this call. For `human`, the recorded evaluator
    name is always the actor's own name — a client-supplied `evaluator_name` is never trusted for a person's
    identity (Phase 2 security fix: see docs/14_PHASE2_SECURITY_SPEC.md §4). `llm` has no person to spoof, so a
    caller may still label which judge model/config produced it via `evaluator_name`."""
    if data.evaluator_type == "self":
        if not wf.same_person(actor, sub.owner):
            raise DomainError("S003", f"Only the owner ({sub.owner}) can self-appraise their own work", 403)
        if sub.status != "open":
            raise DomainError("S009", "Self-appraisal happens before submitting (submission must be open)", 409)
        if any(e.evaluator_type == "self" and e.status != "void" for e in sub.evaluations):
            raise DomainError("S009", "There is already a self-appraisal for this submission", 409)
        name = sub.owner
    else:
        if sub.status != "in_review":
            raise DomainError("S009", "Judges can only evaluate a submission that is in review", 409)
        name = actor if data.evaluator_type == "human" else (data.evaluator_name or "LLM judge").strip()
        if data.evaluator_type == "human" and wf.same_person(name, sub.owner):
            raise DomainError("S003", "The owner cannot judge their own work", 403)
    ev = svc.create_evaluation(
        db,
        EvaluationCreate(version_id=sub.version_id, subject_name=sub.title or sub.subject.name,
                         subject_ref=sub.subject.code, input_text=sub.input_text, evaluator_type=data.evaluator_type,
                         evaluator_name=name[:120], attempt_no=sub.attempt_no),
        commit=False, allow_unpublished=True,
    )
    ev.submission, ev.subject_id = sub, sub.subject_id  # via the relationship, so sub.evaluations stays current
    db.flush()
    wf.audit(db, wf.SUBMISSION, sub.id, "add_evaluation", actor,
             details={"evaluation_id": ev.id, "evaluator_type": data.evaluator_type, "evaluator": name})
    db.commit()
    return ev


def submit(db: Session, sub: Submission, actor: str) -> Submission:
    wf.check(wf.SUBMISSION, sub.status, "submit")
    if not wf.same_person(actor, sub.owner):
        raise DomainError("S003", f"Only the owner ({sub.owner}) submits their work", 403)
    if sub.version.require_self_appraisal and not any(
        e.evaluator_type == "self" and e.status == "completed" for e in sub.evaluations
    ):
        raise DomainError("S005", "This scorecard requires a completed self-appraisal before submitting", 409)
    sub.submitted_at = svc.now()
    wf.transition(db, wf.SUBMISSION, sub, "submit", actor)
    db.commit()
    return sub


def withdraw(db: Session, sub: Submission, actor: str) -> Submission:
    wf.check(wf.SUBMISSION, sub.status, "withdraw")
    if not wf.same_person(actor, sub.owner):
        raise DomainError("S003", "Only the owner can withdraw their submission", 403)
    wf.transition(db, wf.SUBMISSION, sub, "withdraw", actor)
    db.commit()
    return sub


def cancel(db: Session, sub: Submission, actor: str, reason: str) -> Submission:
    wf.transition(db, wf.SUBMISSION, sub, "cancel", actor, details={"reason": reason})
    sub.decision_reason = reason
    db.commit()
    return sub


def judge_evaluations(sub: Submission) -> list[Evaluation]:
    return [e for e in sub.evaluations if e.evaluator_type != "self" and e.status == "completed"]


def _as_pct(sub: Submission, score: float) -> float:
    sc = sub.version.rating_scale
    return (score - sc.min_value) / (sc.max_value - sc.min_value) * 100


def _qtc(sub: Submission) -> tuple[bool | None, bool | None]:
    if not sub.version.qtc_enabled:
        return None, None
    subj = sub.subject
    if subj.due_at is None or subj.budget is None or sub.actual_cost is None:
        raise DomainError("S006", "QTC needs the subject's due date and budget and this attempt's actual cost")
    due = subj.due_at if subj.due_at.tzinfo else subj.due_at.replace(tzinfo=timezone.utc)
    submitted = sub.submitted_at if sub.submitted_at.tzinfo else sub.submitted_at.replace(tzinfo=timezone.utc)
    total_cost = sum(x.actual_cost or 0 for x in subj.submissions
                     if x.version.scorecard_id == sub.version.scorecard_id and x.attempt_no <= sub.attempt_no)
    return submitted <= due, total_cost <= subj.budget + 1e-9


def _finalise(sub: Submission, verdict: str, actor: str, reason: str | None):
    time_met, cost_met = _qtc(sub)
    sub.decision, sub.decided_by, sub.decided_at = verdict, actor, svc.now()
    sub.decision_reason = reason
    sub.time_met, sub.cost_met = time_met, cost_met
    sub.qtc_green = (verdict == "passed" and bool(time_met) and bool(cost_met)) if sub.version.qtc_enabled else None
    sub.blocks_project = bool(sub.version.is_foundational and verdict == "redo" and sub.official_rag == "RED")


def decide(db: Session, sub: Submission, actor: str) -> Submission:
    wf.check(wf.SUBMISSION, sub.status, "decide")
    judges = judge_evaluations(sub)
    need = sub.version.required_judges
    if len(judges) < need:
        raise DomainError("S004", f"{len(judges)} of {need} required judge evaluation(s) completed", 409)
    scores = [e.final_score for e in judges]
    sub.official_score = round(mean(scores), 2)
    card = svc.to_scoring_def(sub.version)
    band = scoring.band_for(sub.official_score, card.bands)
    sub.official_band, sub.official_rag = (band.label, band.rag) if band else (None, None)
    sub.judge_spread_pct = round(_as_pct(sub, max(scores)) - _as_pct(sub, min(scores)), 2)
    seen, failures = set(), []
    for e in judges:
        for g in e.gate_failures or []:
            if g["code"] not in seen:
                seen.add(g["code"])
                failures.append(g)
    sub.gate_failures = failures
    verdicts = {bool(e.quality_met) for e in judges}
    disagree = len(verdicts) > 1 or sub.judge_spread_pct > sub.version.judge_tolerance_pct + 1e-9
    details = {"judges": [{"evaluation_id": e.id, "evaluator": e.evaluator_name, "score": e.final_score,
                           "quality_met": e.quality_met} for e in judges],
               "spread_pct": sub.judge_spread_pct, "tolerance_pct": sub.version.judge_tolerance_pct}
    if disagree:
        wf.transition(db, wf.SUBMISSION, sub, "decide", actor, to_state="adjudication", details=details)
    else:
        verdict = "passed" if verdicts == {True} else "redo"
        _finalise(sub, verdict, actor, None)
        wf.transition(db, wf.SUBMISSION, sub, "decide", actor, to_state="decided",
                      details={**details, "decision": verdict, "qtc_green": sub.qtc_green,
                               "blocks_project": sub.blocks_project})
    db.commit()
    return sub


def adjudicate(db: Session, sub: Submission, actor: str, data: AdjudicationIn) -> Submission:
    wf.check(wf.SUBMISSION, sub.status, "adjudicate")
    conflicted = [sub.owner] + [e.evaluator_name for e in sub.evaluations if e.evaluator_type == "human"]
    if any(wf.same_person(actor, c) for c in conflicted):
        raise DomainError("S003", "The adjudicator must be neither the owner nor one of the judges", 403)
    sub.adjudicated = True
    _finalise(sub, data.verdict, actor, data.reason)
    wf.transition(db, wf.SUBMISSION, sub, "adjudicate", actor,
                  details={"decision": data.verdict, "reason": data.reason, "blocks_project": sub.blocks_project})
    db.commit()
    return sub


PRIVATE_FIELDS = ("final_score", "band_label", "rag", "quality_met", "qtc_green")


def _row_for(e: Evaluation, viewer: str | None, owner: str) -> dict:
    row = {**svc.evaluation_row(e), "is_judge": e.evaluator_type != "self", "redacted": False}
    if e.evaluator_type == "self" and not wf.same_person(viewer, owner):
        # framework §11: self-appraisal is private; hiding it also stops judges anchoring on the owner's number
        row.update({f: None for f in PRIVATE_FIELDS}, redacted=True)
    return row


def submission_view(db: Session, sub: Submission, viewer: str | None = None) -> dict:
    events = db.scalars(select(AuditEvent).where(AuditEvent.entity == wf.SUBMISSION, AuditEvent.entity_id == sub.id)
                        .order_by(AuditEvent.id))
    subj = sub.subject
    return {
        "id": sub.id, "status": sub.status, "allowed_actions": wf.actions(wf.SUBMISSION, sub.status),
        "subject": {"id": subj.id, "code": subj.code, "name": subj.name, "owner": subj.owner, "due_at": subj.due_at,
                    "budget": subj.budget, "blocked": is_blocked(subj)},
        "version": {"id": sub.version.id, "scorecard_id": sub.version.scorecard_id,
                    "scorecard_name": sub.version.scorecard.name, "version_no": sub.version.version_no,
                    "required_judges": sub.version.required_judges,
                    "judge_tolerance_pct": sub.version.judge_tolerance_pct,
                    "require_self_appraisal": sub.version.require_self_appraisal,
                    "is_foundational": sub.version.is_foundational, "qtc_enabled": sub.version.qtc_enabled,
                    "target_score": sub.version.target_score, "rating_scale": svc.scale_view(sub.version.rating_scale)},
        "attempt_no": sub.attempt_no, "previous_id": sub.previous_id, "owner": sub.owner, "title": sub.title,
        "input_text": sub.input_text, "actual_cost": sub.actual_cost,
        "created_at": sub.created_at, "submitted_at": sub.submitted_at, "decided_at": sub.decided_at,
        "decision": sub.decision, "official_score": sub.official_score, "official_band": sub.official_band,
        "official_rag": sub.official_rag, "judge_spread_pct": sub.judge_spread_pct, "gate_failures": sub.gate_failures,
        "time_met": sub.time_met, "cost_met": sub.cost_met, "qtc_green": sub.qtc_green,
        "adjudicated": sub.adjudicated, "decided_by": sub.decided_by, "decision_reason": sub.decision_reason,
        "blocks_project": sub.blocks_project,
        "evaluations": [_row_for(e, viewer, sub.owner) for e in sub.evaluations],
        "events": [{"action": e.action, "from": e.from_state, "to": e.to_state, "actor": e.actor, "at": e.at,
                    "details": e.details} for e in events],
    }


def submissions_list(db: Session, subject_id: int | None = None, status: str | None = None,
                     owner: str | None = None) -> list[dict]:
    q = select(Submission).order_by(Submission.id.desc()).options(
        selectinload(Submission.subject), selectinload(Submission.version).selectinload(ScorecardVersion.scorecard))
    if subject_id:
        q = q.where(Submission.subject_id == subject_id)
    if status:
        q = q.where(Submission.status == status)
    if owner:
        q = q.where(Submission.owner.ilike(owner))
    return [{"id": s.id, "subject_id": s.subject_id, "subject_name": s.subject.name, "scorecard": s.version.scorecard.name,
             "version_no": s.version.version_no, "attempt_no": s.attempt_no, "owner": s.owner, "status": s.status,
             "decision": s.decision, "official_score": s.official_score, "official_band": s.official_band,
             "official_rag": s.official_rag, "qtc_green": s.qtc_green, "adjudicated": s.adjudicated,
             "blocks_project": s.blocks_project, "created_at": s.created_at, "decided_at": s.decided_at}
            for s in db.scalars(q.limit(500))]


# ---------------------------------------------------------------- red diagnosis


def attention_list(db: Session, threshold: int = RED_THRESHOLD, window_days: int = RED_WINDOW_DAYS) -> list[dict]:
    since = svc.now() - timedelta(days=window_days)
    reds = db.scalars(select(Submission).where(Submission.decision == "redo").options(selectinload(Submission.subject)))
    by_person: dict[str, list[Submission]] = defaultdict(list)
    for r in reds:
        at = r.decided_at if r.decided_at.tzinfo else r.decided_at.replace(tzinfo=timezone.utc)
        if at >= since:
            by_person[r.owner.strip().casefold()].append(r)
    out = []
    for key, subs in by_person.items():
        subs.sort(key=lambda s: s.decided_at)
        last_red = subs[-1].decided_at
        diag = db.scalars(select(Diagnosis).where(Diagnosis.person.ilike(subs[-1].owner))
                          .order_by(Diagnosis.recorded_at.desc())).first()
        diagnosed_since = diag is not None and _aware(diag.recorded_at) >= _aware(last_red)
        out.append({
            "person": subs[-1].owner, "reds": len(subs), "latest_red_at": last_red,
            "needs_diagnosis": len(subs) >= threshold and not diagnosed_since,
            "last_diagnosis": ({"cause": diag.cause, "action": diag.action, "at": diag.recorded_at,
                                "by": diag.recorded_by} if diag else None),
            "subjects": sorted({s.subject.name for s in subs}),
        })
    out.sort(key=lambda r: (not r["needs_diagnosis"], -r["reds"]))
    return out


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def record_diagnosis(db: Session, data: DiagnosisIn, actor: str) -> Diagnosis:
    if wf.same_person(actor, data.person):
        raise DomainError("S003", "A diagnosis is recorded by a lead, not by the person diagnosed", 403)
    d = Diagnosis(person=data.person.strip(), cause=data.cause, action=data.action, notes=data.notes,
                  submission_id=data.submission_id, recorded_by=actor)
    db.add(d)
    db.flush()
    wf.audit(db, "diagnosis", d.id, "record", actor, details={"person": d.person, "cause": d.cause, "action": d.action})
    db.commit()
    return d


def diagnoses(db: Session, person: str | None = None) -> list[dict]:
    q = select(Diagnosis).order_by(Diagnosis.recorded_at.desc())
    if person:
        q = q.where(Diagnosis.person.ilike(person))
    return [{"id": d.id, "person": d.person, "cause": d.cause, "action": d.action, "notes": d.notes,
             "submission_id": d.submission_id, "recorded_by": d.recorded_by, "recorded_at": d.recorded_at}
            for d in db.scalars(q)]


# ---------------------------------------------------------------- capability & competency (C1-C6)


def record_capability(db: Session, data: CapabilityIn, actor: str) -> Capability:
    if wf.same_person(actor, data.person):
        raise DomainError("S003", "A capability level is recorded by a lead, not by the person themselves", 403)
    sc = db.scalar(select(Scorecard).where(Scorecard.code == data.scorecard))
    if not sc:
        raise DomainError("E008", f"Unknown scorecard '{data.scorecard}'")
    c = Capability(person=data.person.strip(), scorecard_id=sc.id, level=data.level, notes=data.notes, set_by=actor)
    db.add(c)
    db.flush()
    wf.audit(db, "capability", c.id, "record", actor,
             details={"person": c.person, "scorecard": sc.code, "level": c.level})
    db.commit()
    return c


def capabilities(db: Session, person: str | None = None) -> list[dict]:
    """Full assessment history, newest first. The current level for a person and scorecard is the first row
    matching that pair — history is kept, never overwritten (mirrors `diagnoses`)."""
    q = select(Capability).order_by(Capability.set_at.desc()).options(selectinload(Capability.scorecard))
    if person:
        q = q.where(Capability.person.ilike(person))
    return [{"id": c.id, "person": c.person, "scorecard": c.scorecard.code, "scorecard_name": c.scorecard.name,
             "level": c.level, "level_label": LEVEL_LABELS[c.level], "notes": c.notes, "set_by": c.set_by,
             "set_at": c.set_at}
            for c in db.scalars(q)]


def current_capabilities(db: Session, person: str | None = None) -> list[dict]:
    """One row per (person, scorecard): each pair's most recently assessed level."""
    seen: dict[tuple[str, str], dict] = {}
    for row in capabilities(db, person):  # already newest-first, so the first hit per pair is current
        seen.setdefault((row["person"], row["scorecard"]), row)
    return list(seen.values())


# ---------------------------------------------------------------- behaviour analytics


def self_appraisal_gap(db: Session) -> dict:
    """Framework §11: can people honestly score their own work? Self score vs judges' official score."""
    subs = db.scalars(select(Submission).where(Submission.status == "decided")
                      .options(selectinload(Submission.evaluations), selectinload(Submission.version)))
    rows = []
    for s in subs:
        selfs = [e for e in s.evaluations if e.evaluator_type == "self" and e.status == "completed"]
        if selfs and s.official_score is not None:
            rows.append({"person": s.owner, "gap_pct": _as_pct(s, selfs[-1].final_score) - _as_pct(s, s.official_score),
                         "same_verdict": bool(selfs[-1].quality_met) == (s.decision == "passed")})
    by_person = defaultdict(list)
    for r in rows:
        by_person[r["person"]].append(r)
    return {
        "pairs": len(rows),
        "mean_gap_pct": round(mean(r["gap_pct"] for r in rows), 1) if rows else None,
        "verdict_match_rate": round(sum(r["same_verdict"] for r in rows) / len(rows), 3) if rows else None,
        "people": sorted(
            [{"person": p, "n": len(v), "mean_gap_pct": round(mean(x["gap_pct"] for x in v), 1),
              "verdict_match_rate": round(sum(x["same_verdict"] for x in v) / len(v), 3)} for p, v in by_person.items()],
            key=lambda x: -abs(x["mean_gap_pct"])),
    }


def gate_outcomes(db: Session) -> dict:
    """Quality, time and cost misses tracked separately (framework §16 pilot measure)."""
    subs = list(db.scalars(select(Submission).where(Submission.status == "decided")
                           .options(selectinload(Submission.version))))
    qtc = [s for s in subs if s.version.qtc_enabled]
    disputes = defaultdict(int)
    for s in subs:
        if s.adjudicated:
            disputes[s.version.scorecard_id] += 1
    return {
        "decided": len(subs),
        "passed": sum(s.decision == "passed" for s in subs),
        "redo": sum(s.decision == "redo" for s in subs),
        "adjudicated": sum(s.adjudicated for s in subs),
        "blocked_projects": sum(s.blocks_project for s in subs),
        "first_attempt_pass_rate": _rate([s for s in subs if s.attempt_no == 1], lambda s: s.decision == "passed"),
        "qtc": {"n": len(qtc), "quality_missed": sum(s.decision != "passed" for s in qtc),
                "time_missed": sum(s.time_met is False for s in qtc),
                "cost_missed": sum(s.cost_met is False for s in qtc), "green": sum(bool(s.qtc_green) for s in qtc)},
    }


def _rate(items, pred):
    items = list(items)
    return round(sum(1 for i in items if pred(i)) / len(items), 3) if items else None


def disputed_parameters(db: Session, limit: int = 10) -> list[dict]:
    """Parameters where judges of the same submission differ most: candidates for guideline refinement (§8.7)."""
    subs = db.scalars(select(Submission).where(Submission.status.in_(("decided", "adjudication")))
                      .options(selectinload(Submission.evaluations).selectinload(Evaluation.results)
                               .selectinload(ParameterResult.parameter)))
    spread: dict[int, list[float]] = defaultdict(list)
    names: dict[int, tuple[str, str]] = {}
    for s in subs:
        judges = judge_evaluations(s)
        if len(judges) < 2:
            continue
        per_param: dict[int, list[float]] = defaultdict(list)
        for e in judges:
            for r in e.results:
                if r.is_leaf and r.final_score is not None:
                    per_param[r.parameter_id].append(r.final_score)
                    names[r.parameter_id] = (r.parameter.code, r.parameter.name)
        for pid, vals in per_param.items():
            if len(vals) >= 2:
                spread[pid].append(max(vals) - min(vals))
    rows = [{"parameter_id": pid, "code": names[pid][0], "name": names[pid][1], "n": len(v),
             "mean_spread": round(mean(v), 2), "max_spread": max(v)} for pid, v in spread.items()]
    return sorted(rows, key=lambda r: -r["mean_spread"])[:limit]
