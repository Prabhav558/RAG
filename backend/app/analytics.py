"""Descriptive analytics over completed evaluations (DDD framework §7.5).

Private self-appraisals are excluded from every aggregate.

Tuning (framework §10): aggregates read lean column projections or SQL GROUP BYs, never full ORM graphs, so cost
grows with the number of rows scanned rather than with objects materialised. See docs/tuning/TUNING_REPORT.md.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import Evaluation, Parameter, ParameterResult, RatingScale, Scorecard, ScorecardVersion, SubjectType

def pct(row, score: float | None = None) -> float:
    """Score as % of its own scale, so scorecards on 0–10, 1–5 and 0–100 scales can be compared."""
    s = row.final_score if score is None else score
    return (s - row.min_value) / (row.max_value - row.min_value) * 100


def _rate(items, pred) -> float | None:
    items = list(items)
    return round(sum(1 for i in items if pred(i)) / len(items), 3) if items else None


def _pct_expr():
    return (Evaluation.final_score - RatingScale.min_value) * 100.0 / (RatingScale.max_value - RatingScale.min_value)


def _scoped(q, scorecard_id: int | None):
    q = (q.join(ScorecardVersion, ScorecardVersion.id == Evaluation.version_id)
         .join(RatingScale, RatingScale.id == ScorecardVersion.rating_scale_id)
         .where(Evaluation.status == "completed", Evaluation.is_private.is_(False)))
    return q.where(ScorecardVersion.scorecard_id == scorecard_id) if scorecard_id else q


def _ratio(num, den, digits=3):
    return round(num / den, digits) if den else None


def overview(db: Session, scorecard_id: int | None = None) -> dict:
    """All aggregation happens in SQL: cost is one scan per GROUP BY, independent of Python object counts."""
    yes = lambda cond: func.sum(case((cond, 1), else_=0))  # noqa: E731
    per_card = db.execute(_scoped(select(
        ScorecardVersion.scorecard_id, func.count().label("n"), func.avg(Evaluation.final_score).label("avg"),
        func.avg(_pct_expr()).label("avg_pct"), yes(Evaluation.quality_met.is_(True)).label("passed"),
        yes(Evaluation.gate_failure_count > 0).label("gated"),
        yes(Evaluation.rag == "GREEN").label("green"), yes(Evaluation.rag == "AMBER").label("amber"),
        yes(Evaluation.rag == "RED").label("red"),
    ), scorecard_id).group_by(ScorecardVersion.scorecard_id)).all()
    meta = {
        sc_id: (name, st_name, code)
        for sc_id, name, st_name, code in db.execute(
            select(Scorecard.id, Scorecard.name, SubjectType.name, RatingScale.code)
            .join(SubjectType, SubjectType.id == Scorecard.subject_type_id)
            .join(ScorecardVersion, ScorecardVersion.scorecard_id == Scorecard.id)
            .join(RatingScale, RatingScale.id == ScorecardVersion.rating_scale_id)
            .where(Scorecard.id.in_([r.scorecard_id for r in per_card]))
        )
    }
    cards = sorted(({
        "scorecard_id": r.scorecard_id, "name": meta[r.scorecard_id][0], "subject_type": meta[r.scorecard_id][1],
        "evaluations": r.n, "avg_score": round(float(r.avg), 2), "avg_score_pct": round(float(r.avg_pct), 1),
        "scale": meta[r.scorecard_id][2], "pass_rate": _ratio(r.passed, r.n), "gate_failure_rate": _ratio(r.gated, r.n),
        "rag": {"GREEN": int(r.green), "AMBER": int(r.amber), "RED": int(r.red)},
    } for r in per_card), key=lambda c: -c["evaluations"])

    totals = db.execute(_scoped(select(
        func.count().label("n"), func.avg(_pct_expr()).label("avg_pct"),
        yes(Evaluation.quality_met.is_(True)).label("passed"),
        yes(Evaluation.attempt_no == 1).label("first"),
        yes((Evaluation.attempt_no == 1) & Evaluation.quality_met.is_(True)).label("first_passed"),
        yes(ScorecardVersion.qtc_enabled.is_(True)).label("qtc"),
        yes(ScorecardVersion.qtc_enabled.is_(True) & Evaluation.qtc_green.is_(True)).label("qtc_green"),
    ), scorecard_id)).one()
    bands = db.execute(_scoped(select(Evaluation.band_label, func.count()), scorecard_id).group_by(Evaluation.band_label)).all()
    rags = db.execute(_scoped(select(Evaluation.rag, func.count()), scorecard_id).group_by(Evaluation.rag)).all()
    by_eval = db.execute(_scoped(select(Evaluation.evaluator_type, func.count(), func.avg(_pct_expr())), scorecard_id)
                         .group_by(Evaluation.evaluator_type)).all()
    status_counts = dict(db.execute(select(Evaluation.status, func.count()).group_by(Evaluation.status)).all())
    return {
        "total_completed": totals.n,
        "drafts": status_counts.get("draft", 0),
        "voided": status_counts.get("void", 0),
        "avg_score_pct": round(float(totals.avg_pct), 1) if totals.n else None,
        "pass_rate": _ratio(totals.passed, totals.n),
        "first_attempt_pass_rate": _ratio(totals.first_passed, totals.first),
        "qtc_green_rate": _ratio(totals.qtc_green, totals.qtc),
        "band_distribution": {(b or "—"): n for b, n in bands},
        "rag_distribution": {(r or "—"): n for r, n in rags},
        "by_evaluator_type": {t: {"count": n, "avg_score_pct": round(float(a), 1)} for t, n, a in by_eval},
        "scorecards": cards,
    }


def parameter_breakdown(db: Session, version_id: int) -> dict:
    version = db.get(ScorecardVersion, version_id)
    completed = (Evaluation.version_id == version_id, Evaluation.status == "completed", Evaluation.is_private.is_(False))
    n_evals = db.scalar(select(func.count()).select_from(Evaluation).where(*completed)) or 0
    scored = ParameterResult.final_score.is_not(None) & ParameterResult.not_applicable.is_(False)
    one = lambda cond: func.sum(case((cond, 1), else_=0))  # noqa: E731
    stats = {
        r.parameter_id: r
        for r in db.execute(
            select(
                ParameterResult.parameter_id,
                func.count(ParameterResult.final_score).label("n"),
                func.avg(ParameterResult.final_score).label("avg"),
                func.min(ParameterResult.final_score).label("min"),
                func.max(ParameterResult.final_score).label("max"),
                one(scored & (ParameterResult.final_score < Evaluation.target_score)).label("below_target"),
                one(ParameterResult.not_applicable.is_(True)).label("not_applicable"),
                one(ParameterResult.score_source == "override").label("overrides"),
                one(ParameterResult.score_source == "metric").label("metric_scored"),
            )
            .join(Evaluation, Evaluation.id == ParameterResult.evaluation_id)
            .where(*completed)
            .group_by(ParameterResult.parameter_id)
        )
    }
    params = list(db.scalars(select(Parameter).where(Parameter.version_id == version_id)))
    parents = {p.parent_id for p in params}
    out = []
    for p in params:
        s = stats.get(p.id)
        if s is None:
            continue
        n = s.n or 0
        out.append({
            "parameter_id": p.id, "code": p.code, "name": p.name, "is_leaf": p.id not in parents,
            "parent_id": p.parent_id, "is_critical": p.is_critical, "below_target": int(s.below_target or 0),
            "not_applicable": int(s.not_applicable or 0), "overrides": int(s.overrides or 0),
            "metric_scored": int(s.metric_scored or 0), "n": n,
            "avg": round(float(s.avg), 2) if n else None, "min": s.min, "max": s.max,
            "below_target_rate": round(int(s.below_target or 0) / n, 3) if n else None,
        })
    out.sort(key=lambda a: [int(x) if x.isdigit() else x for x in a["code"].replace("-", ".").split(".")])
    return {
        "version_id": version_id,
        "scorecard_name": version.scorecard.name if version else None,
        "evaluations": n_evals,
        "parameters": out,
        "weakest_leaves": sorted([a for a in out if a["is_leaf"] and a["avg"] is not None], key=lambda a: a["avg"])[:5],
    }


def judge_agreement(db: Session, scorecard_id: int | None = None, tolerance_pct: float = 10.0) -> dict:
    """LLM vs human on the same subject_ref and scorecard version (framework §16 pilot measure).
    Differences are in % of scale (1 point on a 0–10 scale = 10%)."""
    base = (Evaluation.status == "completed", Evaluation.is_private.is_(False), Evaluation.subject_ref.is_not(None))
    llm_refs = select(Evaluation.subject_ref).where(*base, Evaluation.evaluator_type == "llm")
    q = _scoped(select(
        Evaluation.version_id, ScorecardVersion.scorecard_id, Evaluation.subject_ref, Evaluation.subject_name,
        Evaluation.evaluator_type, Evaluation.final_score, Evaluation.quality_met, RatingScale.min_value,
        RatingScale.max_value,
    ), scorecard_id).where(*base, Evaluation.evaluator_type.in_(("llm", "human")),
                           Evaluation.subject_ref.in_(llm_refs)).order_by(Evaluation.id)
    groups: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in db.execute(q):
        groups[(r.version_id, r.subject_ref)][r.evaluator_type].append(r)
    names = dict(db.execute(select(Scorecard.id, Scorecard.name)).all())
    pairs = []
    for (_, ref), by_type in groups.items():
        if by_type.get("llm") and by_type.get("human"):
            llm, human = by_type["llm"][-1], by_type["human"][-1]
            pairs.append({
                "subject_ref": ref,
                "subject_name": human.subject_name,
                "scorecard": names.get(human.scorecard_id),
                "llm_score": llm.final_score,
                "human_score": human.final_score,
                "diff": round(llm.final_score - human.final_score, 2),
                "diff_pct": round(pct(llm) - pct(human), 1),
                "same_verdict": llm.quality_met == human.quality_met,
            })
    diffs = [abs(p["diff_pct"]) for p in pairs]
    return {
        "pairs": len(pairs),
        "mean_abs_diff_pct": round(mean(diffs), 1) if diffs else None,
        "within_tolerance_rate": round(sum(d <= tolerance_pct + 1e-9 for d in diffs) / len(diffs), 3) if diffs else None,
        "verdict_agreement_rate": _rate(pairs, lambda p: p["same_verdict"]),
        "mean_bias_pct_llm_minus_human": round(mean(p["diff_pct"] for p in pairs), 1) if pairs else None,
        "tolerance_pct": tolerance_pct,
        "details": sorted(pairs, key=lambda p: -abs(p["diff_pct"]))[:50],
    }


def trend(db: Session, scorecard_id: int | None = None) -> list[dict]:
    buckets = defaultdict(list)
    q = _scoped(select(Evaluation.completed_at, Evaluation.created_at, Evaluation.final_score, Evaluation.quality_met,
                       RatingScale.min_value, RatingScale.max_value), scorecard_id)
    for r in db.execute(q):
        when = r.completed_at or r.created_at
        buckets[when.strftime("%Y-%m")].append(r)
    return [
        {"period": k, "count": len(v), "avg_score_pct": round(mean(pct(e) for e in v), 1),
         "pass_rate": _rate(v, lambda e: e.quality_met)}
        for k, v in sorted(buckets.items())
    ]


def library_stats(db: Session) -> dict:
    rows = db.execute(select(SubjectType.name, func.count(Scorecard.id))
                      .join(Scorecard, Scorecard.subject_type_id == SubjectType.id).group_by(SubjectType.name)).all()
    return {"scorecards": sum(n for _, n in rows), "by_subject_type": dict(rows)}
