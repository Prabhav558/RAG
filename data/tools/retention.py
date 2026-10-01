"""Data governance — retention purge for audit events and voided evaluations.

Completed evaluations, submissions and diagnoses are never touched here: they are the record a red diagnosis and
a scorecard's history depend on. Only two things are ever purged, and only once they are old enough to no longer
serve any purpose:
  - audit events older than --audit-days (default 400 / AUDIT_RETENTION_DAYS)
  - void evaluations (already excluded from every read model) older than --void-days (default 90 / VOID_RETENTION_DAYS)

Always prints a dry-run report first. Nothing is deleted unless --apply is given.

    python data/tools/retention.py                 # dry run against SCORECARD_DB_URL
    python data/tools/retention.py --apply          # actually purge
    python data/tools/retention.py --audit-days 180 --void-days 30 --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models import AuditEvent, Evaluation  # noqa: E402
from app.services import now  # noqa: E402

AUDIT_RETENTION_DAYS = int(os.environ.get("AUDIT_RETENTION_DAYS", "400"))
VOID_RETENTION_DAYS = int(os.environ.get("VOID_RETENTION_DAYS", "90"))


def plan(db, audit_days: int, void_days: int) -> dict:
    audit_cutoff = now() - timedelta(days=audit_days)
    void_cutoff = now() - timedelta(days=void_days)
    stale_audit = db.query(AuditEvent).filter(AuditEvent.at < audit_cutoff).all()
    stale_void = db.query(Evaluation).filter(Evaluation.status == "void",
                                             Evaluation.voided_at.isnot(None),
                                             Evaluation.voided_at < void_cutoff).all()
    return {"audit_cutoff": audit_cutoff, "void_cutoff": void_cutoff,
            "audit_events": stale_audit, "void_evaluations": stale_void}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-days", type=int, default=AUDIT_RETENTION_DAYS)
    ap.add_argument("--void-days", type=int, default=VOID_RETENTION_DAYS)
    ap.add_argument("--apply", action="store_true", help="actually delete; default is a dry-run report only")
    args = ap.parse_args(argv)

    init_db()
    db = SessionLocal()
    try:
        p = plan(db, args.audit_days, args.void_days)
        print(f"audit events older than {args.audit_days}d (before {p['audit_cutoff'].date()}): "
              f"{len(p['audit_events'])}")
        print(f"void evaluations older than {args.void_days}d (before {p['void_cutoff'].date()}): "
              f"{len(p['void_evaluations'])}")
        if not args.apply:
            print("dry run only; pass --apply to delete")
            return 0
        for row in p["audit_events"]:
            db.delete(row)
        for row in p["void_evaluations"]:
            db.delete(row)
        db.commit()
        print(f"deleted {len(p['audit_events'])} audit event(s) and {len(p['void_evaluations'])} "
              f"void evaluation(s)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
