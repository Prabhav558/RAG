"""Cycle 3 scenario data: projects -> milestones -> tasks moving through the quality gate.

Every step uses the real workflow services (start, self-appraise, submit, judge, decide, adjudicate, resubmit,
stop rule, diagnosis), so generated behaviour obeys every guard. Timestamps are then spread over the last weeks.

    python data/tools/ingest.py --reset && python data/tools/generate.py && python data/tools/generate_flow.py
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "data" / "tools"))

from sqlalchemy import select  # noqa: E402

from app import services as svc  # noqa: E402
from app import services_flow as flow  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import AuditEvent, Evaluation, Scorecard, ScorecardVersion, Submission  # noqa: E402
from generate import ARCHETYPES, fill_evaluation  # noqa: E402

PEOPLE = {  # person -> archetype name (Eve is the allocation problem the attention list must surface)
    "Alice": "solid", "Bob": "excellent", "Chen": "borderline", "Dev": "solid", "Eve": "weak", "Farah": "excellent",
}
JUDGES = ["Asha (lead)", "Ben (architect)", "Carmen (QA)", "Dan (principal)"]
ADJUDICATOR = "Lou (head of quality)"
PROJECTS = [
    ("Apollo Platform", "Pat", [
        ("M1 Requirements", ["Payments PRD", "Onboarding spec"]),
        ("M2 First build", ["Deploy API v2", "Client status email", "Java trainee quiz"]),
    ]),
    ("Hermes Onboarding", "Quinn", [
        ("M1 Curriculum", ["SQL practical test", "Cloud basics quiz", "Git workflow lab"]),
        ("M2 Rollout", ["Kick-off email", "LMS deployment"]),
    ]),
    ("Zeus Analytics", "Rae", [
        ("M1 Foundations", ["Metrics dictionary spec", "Warehouse deployment"]),
        ("M2 Dashboards", ["Exec summary email", "Analyst assessment"]),
    ]),
]
CARD_FOR = [("PRD", "requirements-document"), ("spec", "requirements-document"), ("email", "client-email"),
            ("Deploy", "cloud-deployment"), ("deployment", "cloud-deployment"), ("quiz", "assessment-quality"),
            ("test", "assessment-quality"), ("lab", "assessment-quality"), ("assessment", "assessment-quality")]


def archetype(name):
    return next(a for a in ARCHETYPES if a[0] == name)


def published(db, code) -> ScorecardVersion:
    return db.scalar(select(ScorecardVersion).join(Scorecard)
                     .where(Scorecard.code == code, ScorecardVersion.status == "published"))


def judge_submission(db, sub, arch, rng, shift, lenient_judge=False):
    for i in range(sub.version.required_judges):
        judge = JUDGES[(sub.id + i) % len(JUDGES)]
        ev = flow.add_evaluation(db, sub, flow.SubmissionEvaluationIn(evaluator_type="human", evaluator_name=judge),
                                 judge)
        fill_evaluation(db, ev, sub.version, arch, "llm" if (lenient_judge and i == 1) else "human", rng, shift,
                        qtc_flags=False)
        svc.complete_evaluation(db, ev)


def run_attempt(db, subject, version, owner, arch, rng, shift=0.0, stop_at=None):
    sub = flow.start_submission(db, subject, flow.SubmissionIn(version_id=version.id,
                                                               input_text=f"[generated] {subject.name}"), owner)
    if version.require_self_appraisal or rng.random() < 0.5:
        ev = flow.add_evaluation(db, sub, flow.SubmissionEvaluationIn(evaluator_type="self"), owner)
        fill_evaluation(db, ev, version, arch, "self", rng, shift, qtc_flags=False)
        svc.complete_evaluation(db, ev)
    if stop_at == "open":
        return sub
    flow.submit(db, sub, owner)
    if version.qtc_enabled:
        flow.update_submission(db, sub, flow.SubmissionUpdate(actual_cost=round(subject.budget * rng.uniform(0.6, 1.15), 2)),
                               owner)
    if stop_at == "in_review":
        return sub
    judge_submission(db, sub, arch, rng, shift, lenient_judge=rng.random() < 0.3)
    flow.decide(db, sub, "PMO bot")
    if sub.status == "adjudication":
        verdict = "passed" if (sub.official_score or 0) >= version.target_score and not sub.gate_failures else "redo"
        flow.adjudicate(db, sub, ADJUDICATOR, flow.AdjudicationIn(
            verdict=verdict, reason="Judges read the guideline differently; settled against the quantitative anchor"))
    return sub


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)
    init_db()
    with SessionLocal() as db:
        now = svc.now()
        milestone_card = published(db, "milestone-delivery")
        people = list(PEOPLE)
        n = 0
        for p_name, p_owner, milestones in PROJECTS:
            project = flow.create_subject(db, flow.SubjectIn(name=p_name, subject_type="project", owner=p_owner), "PMO")
            for m_name, tasks in milestones:
                due = now + timedelta(days=rng.randint(-10, 20))
                milestone = flow.create_subject(db, flow.SubjectIn(
                    name=f"{p_name.split()[0]} {m_name}", subject_type="milestone", owner=p_owner,
                    parent_id=project.id, due_at=due, budget=rng.choice([4000, 6000, 8000])), "PMO")
                milestone_passed = True
                for t_name in tasks:
                    owner = people[n % len(people)]
                    n += 1
                    code = next(c for k, c in CARD_FOR if k.lower() in t_name.lower())
                    version = published(db, code)
                    subject = flow.create_subject(db, flow.SubjectIn(
                        name=f"{p_name.split()[0]}: {t_name}", subject_type="task", owner=owner,
                        parent_id=milestone.id), "PMO")
                    arch = archetype(PEOPLE[owner])
                    if blocked := flow.blockers_in_project(subject):
                        print(f"  skip {subject.name}: project stopped by {blocked[0].name}")
                        milestone_passed = False
                        continue
                    stop_at = rng.choice([None, None, None, None, "open", "in_review"])
                    sub = run_attempt(db, subject, version, owner, arch, rng, stop_at=stop_at)
                    shift = 0.0
                    while sub.status == "decided" and sub.decision == "redo" and sub.attempt_no < 3 and rng.random() < 0.75:
                        shift += 0.12
                        sub = run_attempt(db, subject, version, owner, arch, rng, shift)
                    milestone_passed &= sub.status == "decided" and sub.decision == "passed"
                if milestone_passed and rng.random() < 0.8:  # a milestone is reviewed once its tasks passed
                    run_attempt(db, milestone, milestone_card, p_owner, archetype("solid"), rng)
        # extra history for Eve so the attention list has something real to show
        for i in range(3):
            s = flow.create_subject(db, flow.SubjectIn(name=f"Eve: support ticket write-up {i + 1}", subject_type="task",
                                                       owner="Eve"), "PMO")
            run_attempt(db, s, published(db, "client-email"), "Eve", archetype("weak"), rng)

        # spread timestamps over the last 8 weeks, keeping order within each submission
        subs = list(db.scalars(select(Submission).order_by(Submission.id)))
        for i, sub in enumerate(subs):
            base = now - timedelta(days=56 - int(56 * i / max(1, len(subs))), hours=rng.randint(0, 12))
            sub.created_at = base
            if sub.submitted_at:
                sub.submitted_at = base + timedelta(hours=rng.randint(2, 30))
            if sub.decided_at:
                sub.decided_at = sub.submitted_at + timedelta(hours=rng.randint(4, 72))
            for ev in db.scalars(select(Evaluation).where(Evaluation.submission_id == sub.id)):
                ev.created_at = base + timedelta(hours=1)
                if ev.completed_at:
                    ev.completed_at = (sub.decided_at or sub.submitted_at or base) - timedelta(hours=1)
            for e in db.scalars(select(AuditEvent).where(AuditEvent.entity == "submission", AuditEvent.entity_id == sub.id)):
                e.at = {"start": base, "submit": sub.submitted_at}.get(e.action) or sub.decided_at or base
        db.commit()
        g = flow.gate_outcomes(db)
        print(f"submissions: {len(subs)} · decided {g['decided']} (passed {g['passed']}, redo {g['redo']}, "
              f"adjudicated {g['adjudicated']}, blocked {g['blocked_projects']})")
        print("attention:", [(p["person"], p["reds"], p["needs_diagnosis"]) for p in flow.attention_list(db)])
        print("roll-up:", [(r["name"], r["status"]) for r in flow.subject_forest(db)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
