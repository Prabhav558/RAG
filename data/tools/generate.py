"""Scenario-based evaluation data generator (DDD framework §7.4).

Scenario richness first, volume second: every generated subject is drawn from a named archetype
(see docs/04_SCENARIO_CATALOGUE.md), and --multiplier scales volume only after the archetypes exist.
All writes go through app.services, so generated data obeys exactly the same rules as user data.

    python data/tools/ingest.py --reset && python data/tools/generate.py --multiplier 1
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app import services as svc  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.models import Scorecard, ScorecardVersion  # noqa: E402
from app.schemas import EvaluationCreate, EvaluationUpdate, MetricValueIn, RatingIn  # noqa: E402

# Archetype: (name, share, mean quality on a 0..1 scale, spread, weak_critical)
ARCHETYPES = [
    ("excellent", 0.15, 0.93, 0.05, False),
    ("solid", 0.30, 0.82, 0.07, False),
    ("borderline", 0.20, 0.74, 0.07, False),
    ("weak", 0.15, 0.50, 0.12, False),
    ("uneven-critical-miss", 0.10, 0.85, 0.05, True),  # strong average, one critical parameter fails
    ("sparse", 0.10, 0.78, 0.15, False),  # many optional parameters N/A
]

EVALUATORS = {
    # evaluator type: (bias in scale points on 0..10, noise sd on 0..10)
    "human": (0.0, 0.6),
    "llm": (0.3, 0.8),  # slightly lenient: the bias analytics must detect
    "self": (1.0, 0.8),  # optimistic self-appraisal (framework §11)
}
HUMANS = ["A. Rao", "S. Iyer", "M. Chen", "P. Keshwar", "L. Gomez"]
SUBJECT_NOUNS = {
    "assessment": ["Java Fundamentals Quiz", "SQL Practical", "Cloud Basics Test", "Python Assignment",
                   "System Design Case", "Git Workflow Lab", "REST API Exercise", "Data Structures Test"],
    "document": ["Payments PRD", "Onboarding Spec", "Search Requirements", "Billing FRS", "Audit Log PRD"],
    "milestone": ["M1 Data Model", "M2 First Build", "M3 Migration", "M4 UAT", "M5 Go-Live"],
    "team": ["Platform Team", "Data Team", "Mobile Squad", "QA Guild", "Interns Batch A"],
    "communication": ["Status update to client", "Scope change email", "Incident summary", "Proposal follow-up"],
    "deployment": ["API v2 rollout", "DB migration 42", "CDN switch", "Auth service upgrade"],
}


def pick_archetype(rng: random.Random):
    r, acc = rng.random(), 0.0
    for a in ARCHETYPES:
        acc += a[1]
        if r <= acc:
            return a
    return ARCHETYPES[-1]


def closest_value(metric, target_score: float, rng: random.Random) -> float:
    """Invert thresholds: choose a value inside a band bracketing the latent score. The upper band is
    picked with probability proportional to proximity, so coarse thresholds keep the expected score."""
    scores = sorted({t.score for t in metric.thresholds})
    above = [s for s in scores if s >= target_score]
    below = [s for s in scores if s <= target_score]
    if above and below and min(above) != max(below):
        hi_s, lo_s = min(above), max(below)
        chosen = hi_s if rng.random() < (target_score - lo_s) / (hi_s - lo_s) else lo_s
    else:
        chosen = min(scores, key=lambda s: abs(s - target_score))
    best = next(t for t in metric.thresholds if t.score == chosen)
    lo = best.min_value if best.min_value is not None else (best.max_value - 20 if best.max_value else 0)
    hi = best.max_value if best.max_value is not None else lo + (1 if metric.data_type == "count" else 5)
    lo = max(lo, 0)
    if metric.data_type == "count":
        return float(rng.randint(int(lo), max(int(lo), int(hi) - 1)))
    if metric.data_type == "percent":
        hi = min(hi, 100.0)
        if best.max_value is None:
            return 100.0 if lo >= 100 else round(rng.uniform(lo, hi), 1)
    v = rng.uniform(lo, hi - 1e-6 if best.max_value is not None else hi)
    return round(min(v, 100.0) if metric.data_type == "percent" else v, 1)


def criterion_for(param, score: int):
    for c in param.criteria:
        if c.score_min <= score <= c.score_max:
            return c
    return None


def generate_evaluation(db, version: ScorecardVersion, subject: str, ref: str, archetype, evaluator: str,
                        rng: random.Random, when, attempt: int = 1, quality_shift: float = 0.0,
                        complete: bool = True):
    scale = version.rating_scale
    span = scale.max_value - scale.min_value
    kids = {p.parent_id for p in version.parameters}
    leaves = [p for p in version.parameters if p.id not in kids]
    _, _, mean_q, spread, weak_critical = archetype
    bias, noise = EVALUATORS[evaluator]

    critical_leaves = [p for p in leaves if p.is_critical] or [
        p for p in leaves if p.parent and p.parent.is_critical
    ]
    sabotage = rng.choice(critical_leaves) if weak_critical and critical_leaves else None

    ev = svc.create_evaluation(
        db,
        EvaluationCreate(
            version_id=version.id,
            subject_name=subject,
            subject_ref=ref,
            evaluator_type=evaluator,
            evaluator_name="claude-opus-5" if evaluator == "llm" else rng.choice(HUMANS),
            attempt_no=attempt,
            input_text=f"[generated] {subject} — archetype '{archetype[0]}'",
        ),
        commit=False,
    )
    if evaluator == "llm":
        ev.judge_model = "claude-opus-5"

    ratings, metric_values = [], []
    for p in leaves:
        if p.is_optional and (archetype[0] == "sparse" or rng.random() < 0.25):
            ratings.append(RatingIn(parameter_id=p.id, not_applicable=True, rationale="Not applicable to this subject"))
            continue
        q = min(1.0, max(0.0, rng.gauss(mean_q + quality_shift, spread)))
        if p is sabotage:
            q = rng.uniform(0.25, 0.55)
        true_score = scale.min_value + q * span
        judged = true_score + (bias + rng.gauss(0, noise)) * span / 10
        judged = int(round(min(scale.max_value, max(scale.min_value, judged))))
        if p.metrics:
            for m in p.metrics:
                metric_values.append(MetricValueIn(metric_id=m.id, value=closest_value(m, true_score, rng),
                                                   source="llm" if evaluator == "llm" else "manual"))
        crit = criterion_for(p, judged)
        ratings.append(RatingIn(
            parameter_id=p.id,
            judged_score=judged,
            rationale=f"Matches {crit.score_min}–{crit.score_max}: {crit.qualitative}" if crit else None,
            evidence=crit.quantitative if crit else None,
            confidence=round(rng.uniform(0.55, 0.95), 2) if evaluator == "llm" else None,
        ))

    upd = EvaluationUpdate(ratings=ratings, metric_values=metric_values)
    if version.qtc_enabled:
        upd.time_met = rng.random() < 0.8
        upd.cost_met = rng.random() < 0.9
    svc.apply_update(db, ev, upd, commit=False)
    ev.created_at = when
    if complete:
        svc.complete_evaluation(db, ev, commit=False)
        ev.completed_at = when + timedelta(hours=rng.randint(1, 48))
    return ev


def published(db):
    q = select(ScorecardVersion).where(ScorecardVersion.status == "published").join(Scorecard)
    return list(db.scalars(q))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--multiplier", type=int, default=1, help="volume multiplier (subjects per scorecard x 12)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--days", type=int, default=180, help="spread evaluations over the last N days")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    init_db()
    counts = {"completed": 0, "draft": 0, "void": 0, "self": 0}
    with SessionLocal() as db:
        now = svc.now()
        for version in published(db):
            sc = version.scorecard
            nouns = SUBJECT_NOUNS.get(sc.subject_type.code, [sc.subject_type.name])
            for i in range(12 * args.multiplier):
                archetype = pick_archetype(rng)
                subject = f"{rng.choice(nouns)} #{i + 1:03d}"
                ref = f"{sc.code}-{i + 1:04d}"
                when = now - timedelta(days=rng.randint(1, args.days), hours=rng.randint(0, 23))

                # scenario: private self-appraisal before the real judgement
                if rng.random() < 0.3:
                    generate_evaluation(db, version, subject, ref, archetype, "self", rng, when - timedelta(hours=6))
                    counts["self"] += 1

                ev = generate_evaluation(db, version, subject, ref, archetype, "human", rng, when)
                counts["completed"] += 1

                # scenario: LLM judge on the same subject (judge-agreement analytics)
                if rng.random() < 0.5:
                    generate_evaluation(db, version, subject, ref, archetype, "llm", rng, when + timedelta(hours=1))
                    counts["completed"] += 1

                # scenario: failed gate -> redo -> resubmission (framework §10.1)
                if ev.quality_met is False and rng.random() < 0.6:
                    generate_evaluation(db, version, subject, ref, archetype, "human", rng,
                                        when + timedelta(days=rng.randint(2, 7)), attempt=2, quality_shift=0.12)
                    counts["completed"] += 1

            # lifecycle scenarios: one in-progress draft and one voided evaluation per scorecard
            archetype = pick_archetype(rng)
            generate_evaluation(db, version, f"{rng.choice(nouns)} (in progress)", f"{sc.code}-draft",
                                archetype, "human", rng, now - timedelta(hours=3), complete=False)
            counts["draft"] += 1
            voided = generate_evaluation(db, version, f"{rng.choice(nouns)} (duplicate)", f"{sc.code}-dup",
                                         archetype, "human", rng, now - timedelta(days=2))
            db.flush()
            svc.void_evaluation(db, voided, "Duplicate submission of the same subject")
            counts["void"] += 1
            db.commit()
            print(f"generated for '{sc.name}' v{version.version_no}")
        db.commit()
    print(f"done: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
