"""State machines for Cycle 3 (docs/10_CYCLE3_BEHAVIOUR_SPEC.md).

Transitions are data, not scattered if-statements: `TRANSITIONS[machine][(state, action)] = next_state`.
Guards that depend on data live in services_flow.py; this module enforces *which* actions exist in *which* state,
and records every transition in the audit log.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AuditEvent
from .services import DomainError

VERSION = "version"
SUBMISSION = "submission"

TRANSITIONS: dict[str, dict[tuple[str, str], str]] = {
    VERSION: {
        ("draft", "submit_for_review"): "in_review",
        ("draft", "publish"): "published",  # only when the scorecard does not require review
        ("in_review", "approve"): "published",
        ("in_review", "request_changes"): "draft",
        ("published", "retire"): "retired",
    },
    SUBMISSION: {
        ("open", "submit"): "in_review",
        ("open", "withdraw"): "withdrawn",
        ("open", "cancel"): "cancelled",
        ("in_review", "decide"): "decided",  # or "adjudication" when judges disagree (decided by the guard)
        ("in_review", "cancel"): "cancelled",
        ("adjudication", "adjudicate"): "decided",
        ("adjudication", "cancel"): "cancelled",
    },
}

STATES = {
    VERSION: ["draft", "in_review", "published", "retired"],
    SUBMISSION: ["open", "in_review", "adjudication", "decided", "withdrawn", "cancelled"],
}
TERMINAL = {SUBMISSION: {"decided", "withdrawn", "cancelled"}, VERSION: {"retired"}}
# alternative outcome of a transition, chosen by its guard
ALTERNATIVE = {(SUBMISSION, "in_review", "decide"): {"decided", "adjudication"}}


def actions(machine: str, state: str) -> list[str]:
    return sorted(a for (s, a) in TRANSITIONS[machine] if s == state)


def require_actor(actor: str | None) -> str:
    actor = (actor or "").strip()
    if not actor:
        raise DomainError("S002", "This action needs an actor: log in first", 422)
    return actor[:120]


def same_person(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a.strip().casefold() == b.strip().casefold()


def check(machine: str, state: str, action: str) -> str:
    target = TRANSITIONS[machine].get((state, action))
    if target is None:
        raise DomainError(
            "S001",
            f"'{action}' is not allowed while the {machine} is {state}",
            409,
            details=[f"allowed: {', '.join(actions(machine, state)) or 'none (terminal state)'}"],
        )
    return target


def transition(db: Session, machine: str, obj, action: str, actor: str, to_state: str | None = None,
               details: dict | None = None) -> str:
    """Move `obj.status` along the table (or to an allowed alternative) and write the audit event."""
    frm = obj.status
    target = check(machine, frm, action)
    if to_state and to_state != target:
        if to_state not in ALTERNATIVE.get((machine, frm, action), set()):
            raise DomainError("S001", f"{machine} cannot go from {frm} to {to_state} via {action}", 409)
        target = to_state
    obj.status = target
    audit(db, machine, obj.id, action, actor, frm, target, details)
    return target


def audit(db: Session, entity: str, entity_id: int, action: str, actor: str, frm: str | None = None,
          to: str | None = None, details: dict | None = None):
    db.add(AuditEvent(entity=entity, entity_id=entity_id, action=action, actor=actor or "system",
                      from_state=frm, to_state=to, details=details or {}))
