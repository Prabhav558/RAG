"""Descriptive analytics over completed evaluations (DDD framework §7.5).

Private self-appraisals are excluded from every aggregate.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .models import Evaluation, Parameter, ParameterResult, Scorecard, ScorecardVersion


def _completed(db: Session, scorecard_id: int | None = None, version_id: int | None = None):
    q = (
        select(Evaluation)
        .join(ScorecardVersion)
        .where(Evaluation.status == "completed", Evaluation.is_private.is_(False))
        .options(selectinload(Evaluation.version).selectinload(ScorecardVersion.scorecard))
    )
    if scorecard_id:
        q = q.where(ScorecardVersion.scorecard_id == scorecard_id)
    if version_id:
        q = q.where(Evaluation.version_id == version_id)
    return list(db.scalars(q))


def pct(e: Evaluation, score: float | None = None) -> float:
    """Score as % of its own scale, so scorecards on 0–10, 1–5 and 0–100 scales can be compared."""
    scale = e.version.rating_scale
    s = e.final_score if score is None else score
    return (s - scale.min_value) / (scale.max_value - scale.min_value) * 100


def _rate(items, pred) -> float | None:
    items = list(items)
    return round(sum(1 for i in items if pred(i)) / len(items), 3) if items else None


def overview(db: Session, scorecard_id: int | None = None) -> dict:
    evs = _completed(db, scorecard_id)
    bands: dict[str, int] = defaultdict(int)
    rag: dict[str, int] = defaultdict(int)
    for e in evs:
        bands[e.band_label or "—"] += 1
        rag[e.rag or "—"] += 1

    per_card = defaultdict(list)
    for e in evs:
        per_card[e.version.scorecard_id].append(e)
    cards = []
    for sc_id, items in per_card.items():
        sc = items[0].version.scorecard
        cards.append(
            {
                "scorecard_id": sc_id,
                "name": sc.name,
                "subject_type": sc.subject_type.name,
                "evaluations": len(items),
                "avg_score": round(mean(i.final_score for i in items), 2),
                "avg_score_pct": round(mean(pct(i) for i in items), 1),
                "scale": sc.versions[-1].rating_scale.code,
                "pass_rate": _rate(items, lambda i: i.quality_met),
                "gate_failure_rate": _rate(items, lambda i: bool(i.gate_failures)),
                "rag": {k: sum(1 for i in items if i.rag == k) for k in ("GREEN", "AMBER", "RED")},
            }
        )
    cards.sort(key=lambda c: -c["evaluations"])

    by_evaluator = defaultdict(list)
    for e in evs:
        by_evaluator[e.evaluator_type].append(pct(e))

    first = [e for e in evs if e.attempt_no == 1]
    all_evs = list(db.scalars(select(Evaluation.status)))
    return {
        "total_completed": len(evs),
        "drafts": sum(1 for s in all_evs if s == "draft"),
        "voided": sum(1 for s in all_evs if s == "void"),
        "avg_score_pct": round(mean(pct(e) for e in evs), 1) if evs else None,
        "pass_rate": _rate(evs, lambda e: e.quality_met),
        "first_attempt_pass_rate": _rate(first, lambda e: e.quality_met),
        "qtc_green_rate": _rate([e for e in evs if e.version.qtc_enabled], lambda e: e.qtc_green),
        "band_distribution": dict(bands),
        "rag_distribution": dict(rag),
        "by_evaluator_type": {k: {"count": len(v), "avg_score_pct": round(mean(v), 1)} for k, v in by_evaluator.items()},
        "scorecards": cards,
    }


def parameter_breakdown(db: Session, version_id: int) -> dict:
    version = db.get(ScorecardVersion, version_id)
    evs = _completed(db, version_id=version_id)
    ids = [e.id for e in evs]
    rows = (
        db.execute(
            select(ParameterResult, Parameter)
            .join(Parameter, Parameter.id == ParameterResult.parameter_id)
            .where(ParameterResult.evaluation_id.in_(ids))
        ).all()
        if ids
        else []
    )
    target_by_ev = {e.id: e.target_score for e in evs}
    agg: dict[int, dict] = {}
    for res, p in rows:
        a = agg.setdefault(
            p.id,
            {"parameter_id": p.id, "code": p.code, "name": p.name, "is_leaf": res.is_leaf, "parent_id": p.parent_id,
             "is_critical": p.is_critical, "scores": [], "below_target": 0, "not_applicable": 0,
             "overrides": 0, "metric_scored": 0},
        )
        if res.not_applicable:
            a["not_applicable"] += 1
            continue
        if res.final_score is None:
            continue
        a["scores"].append(res.final_score)
        if res.final_score < target_by_ev[res.evaluation_id]:
            a["below_target"] += 1
        if res.score_source == "override":
            a["overrides"] += 1
        if res.score_source == "metric":
            a["metric_scored"] += 1
    out = []
    for a in agg.values():
        s = a.pop("scores")
        a["n"] = len(s)
        a["avg"] = round(mean(s), 2) if s else None
        a["min"] = min(s) if s else None
        a["max"] = max(s) if s else None
        a["below_target_rate"] = round(a["below_target"] / len(s), 3) if s else None
        out.append(a)
    out.sort(key=lambda a: [int(x) if x.isdigit() else x for x in a["code"].replace("-", ".").split(".")])
    return {
        "version_id": version_id,
        "scorecard_name": version.scorecard.name if version else None,
        "evaluations": len(evs),
        "parameters": out,
        "weakest_leaves": sorted(
            [a for a in out if a["is_leaf"] and a["avg"] is not None], key=lambda a: a["avg"]
        )[:5],
    }


def judge_agreement(db: Session, scorecard_id: int | None = None, tolerance_pct: float = 10.0) -> dict:
    """LLM vs human on the same subject_ref and scorecard version (framework §16 pilot measure).
    Differences are in % of scale (1 point on a 0–10 scale = 10%)."""
    evs = [e for e in _completed(db, scorecard_id) if e.subject_ref]
    groups: dict[tuple, dict[str, list[Evaluation]]] = defaultdict(lambda: defaultdict(list))
    for e in evs:
        groups[(e.version_id, e.subject_ref)][e.evaluator_type].append(e)
    pairs = []
    for (version_id, ref), by_type in groups.items():
        if by_type.get("llm") and by_type.get("human"):
            llm, human = by_type["llm"][-1], by_type["human"][-1]
            pairs.append(
                {
                    "subject_ref": ref,
                    "subject_name": human.subject_name,
                    "scorecard": human.version.scorecard.name,
                    "llm_score": llm.final_score,
                    "human_score": human.final_score,
                    "diff": round(llm.final_score - human.final_score, 2),
                    "diff_pct": round(pct(llm) - pct(human), 1),
                    "same_verdict": llm.quality_met == human.quality_met,
                }
            )
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
    evs = _completed(db, scorecard_id)
    buckets = defaultdict(list)
    for e in evs:
        when = e.completed_at or e.created_at
        buckets[when.strftime("%Y-%m")].append(e)
    return [
        {"period": k, "count": len(v), "avg_score_pct": round(mean(pct(e) for e in v), 1),
         "pass_rate": _rate(v, lambda e: e.quality_met)}
        for k, v in sorted(buckets.items())
    ]


def library_stats(db: Session) -> dict:
    cards = list(db.scalars(select(Scorecard)))
    by_type = defaultdict(int)
    for c in cards:
        by_type[c.subject_type.name] += 1
    return {"scorecards": len(cards), "by_subject_type": dict(by_type)}
