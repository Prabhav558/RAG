"""Pure, deterministic scoring engine. No database access.

Spec: docs/05_SCORING_ENGINE_SPEC.md. Every rule here has a scenario and a test.
"""

from __future__ import annotations

from dataclasses import dataclass, field

EPS = 1e-9


@dataclass
class ThresholdDef:
    min_value: float | None
    max_value: float | None
    score: float

    def contains(self, value: float) -> bool:
        lo_ok = self.min_value is None or value >= self.min_value - EPS
        hi_ok = self.max_value is None or value < self.max_value - EPS
        return lo_ok and hi_ok


@dataclass
class MetricDef:
    id: int
    code: str
    thresholds: list[ThresholdDef] = field(default_factory=list)

    def score_for(self, value: float) -> float | None:
        for t in self.thresholds:
            if t.contains(value):
                return t.score
        return None


@dataclass
class ParamDef:
    id: int
    code: str
    name: str
    parent_id: int | None
    weight: float = 1.0
    sort_order: int = 0
    aggregation: str = "weighted_mean"
    is_critical: bool = False
    min_acceptable_score: float | None = None
    is_optional: bool = False
    metrics: list[MetricDef] = field(default_factory=list)


@dataclass
class BandDef:
    label: str
    lower_bound: float
    rag: str
    color_hex: str = "#cccccc"
    font_hex: str = "#000000"


@dataclass
class ScorecardDef:
    scale_min: float
    scale_max: float
    bands: list[BandDef]
    target_score: float
    aggregation: str
    qtc_enabled: bool
    params: list[ParamDef]


@dataclass
class LeafInput:
    judged_score: float | None = None
    not_applicable: bool = False
    override_reason: str | None = None


@dataclass
class ParamOutcome:
    parameter_id: int
    is_leaf: bool
    judged_score: float | None = None
    computed_score: float | None = None
    final_score: float | None = None
    score_source: str = "pending"  # judged | metric | override | rollup | not_applicable | pending
    not_applicable: bool = False
    effective_weight: float | None = None
    band: BandDef | None = None
    complete: bool = False  # this node and everything under it has a score (or is N/A)


@dataclass
class EvaluationOutcome:
    params: dict[int, ParamOutcome]
    final_score: float | None
    band: BandDef | None
    complete: bool
    pending_leaf_ids: list[int]
    gate_failures: list[dict]
    quality_met: bool | None
    qtc_green: bool | None
    warnings: list[str]


def band_for(score: float | None, bands: list[BandDef]) -> BandDef | None:
    """Highest band whose lower bound <= score. Never rounds up (green must be really green)."""
    if score is None:
        return None
    for b in sorted(bands, key=lambda b: b.lower_bound, reverse=True):
        if score >= b.lower_bound - EPS:
            return b
    return None


def _normalised(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= EPS:
        return [1.0 / len(weights)] * len(weights) if weights else []
    return [w / total for w in weights]


def _aggregate(method: str, scores: list[float], weights: list[float]) -> float:
    if method == "minimum":
        return min(scores)
    return sum(s * w for s, w in zip(scores, _normalised(weights)))


def compute(
    card: ScorecardDef,
    leaf_inputs: dict[int, LeafInput],
    metric_values: dict[int, float],
    time_met: bool | None = None,
    cost_met: bool | None = None,
    target_score: float | None = None,
) -> EvaluationOutcome:
    target = card.target_score if target_score is None else target_score
    children: dict[int | None, list[ParamDef]] = {}
    for p in card.params:
        children.setdefault(p.parent_id, []).append(p)
    for kids in children.values():
        kids.sort(key=lambda p: (p.sort_order, p.code))

    outcomes: dict[int, ParamOutcome] = {}
    warnings: list[str] = []
    pending: list[int] = []

    def score_leaf(p: ParamDef) -> ParamOutcome:
        inp = leaf_inputs.get(p.id, LeafInput())
        out = ParamOutcome(parameter_id=p.id, is_leaf=True, judged_score=inp.judged_score)
        if inp.not_applicable and p.is_optional:
            out.not_applicable = True
            out.score_source = "not_applicable"
            out.complete = True
            return out
        if p.metrics:
            metric_scores = []
            for m in p.metrics:
                if m.id not in metric_values:
                    metric_scores = None
                    break
                s = m.score_for(metric_values[m.id])
                if s is None:
                    warnings.append(f"Metric '{m.code}' value {metric_values[m.id]} matches no threshold")
                    metric_scores = None
                    break
                metric_scores.append(s)
            if metric_scores:
                out.computed_score = min(metric_scores)
        if inp.override_reason and inp.judged_score is not None:
            out.final_score, out.score_source = inp.judged_score, "override"
        elif out.computed_score is not None:
            out.final_score, out.score_source = out.computed_score, "metric"
        elif inp.judged_score is not None:
            out.final_score, out.score_source = inp.judged_score, "judged"
        out.complete = out.final_score is not None
        if not out.complete:
            pending.append(p.id)
        return out

    def walk(p: ParamDef) -> ParamOutcome:
        kids = children.get(p.id, [])
        if not kids:
            out = score_leaf(p)
            outcomes[p.id] = out
            return out
        kid_outs = [walk(k) for k in kids]
        out = ParamOutcome(parameter_id=p.id, is_leaf=False, score_source="rollup")
        applicable = [(k, o) for k, o in zip(kids, kid_outs) if not o.not_applicable]
        if not applicable:
            out.not_applicable, out.score_source, out.complete = True, "not_applicable", True
        else:
            scored = [(k, o) for k, o in applicable if o.final_score is not None]
            if scored:
                out.final_score = _aggregate(
                    p.aggregation, [o.final_score for _, o in scored], [k.weight for k, _ in scored]
                )
            out.complete = all(o.complete for _, o in applicable)
        outcomes[p.id] = out
        return out

    roots = children.get(None, [])
    root_outs = [walk(r) for r in roots]

    # effective weights: product of normalised sibling weights among applicable siblings
    def assign_weights(nodes: list[ParamDef], parent_share: float):
        applicable = [n for n in nodes if not outcomes[n.id].not_applicable]
        norm = _normalised([n.weight for n in applicable])
        for n, w in zip(applicable, norm):
            outcomes[n.id].effective_weight = parent_share * w
            assign_weights(children.get(n.id, []), parent_share * w)
        for n in nodes:
            if outcomes[n.id].not_applicable:
                outcomes[n.id].effective_weight = 0.0

    assign_weights(roots, 1.0)

    applicable_roots = [(r, o) for r, o in zip(roots, root_outs) if not o.not_applicable]
    scored_roots = [(r, o) for r, o in applicable_roots if o.final_score is not None]
    final = (
        _aggregate(card.aggregation, [o.final_score for _, o in scored_roots], [r.weight for r, _ in scored_roots])
        if scored_roots
        else None
    )
    complete = bool(applicable_roots) and all(o.complete for _, o in applicable_roots)

    for o in outcomes.values():
        if o.final_score is not None:
            o.final_score = round(o.final_score, 2)
        o.band = band_for(o.final_score, card.bands)
    final = round(final, 2) if final is not None else None

    gate_failures = []
    for p in card.params:
        o = outcomes[p.id]
        if p.is_critical and o.final_score is not None and not o.not_applicable:
            floor = p.min_acceptable_score if p.min_acceptable_score is not None else target
            if o.final_score < floor - EPS:
                gate_failures.append(
                    {"parameter_id": p.id, "code": p.code, "name": p.name, "score": o.final_score, "floor": floor}
                )

    quality_met = None
    if complete and final is not None:
        quality_met = final >= target - EPS and not gate_failures
    if card.qtc_enabled:
        qtc_green = None if None in (quality_met, time_met, cost_met) else bool(quality_met and time_met and cost_met)
    else:
        qtc_green = quality_met

    return EvaluationOutcome(
        params=outcomes,
        final_score=final,
        band=band_for(final, card.bands),
        complete=complete,
        pending_leaf_ids=pending,
        gate_failures=gate_failures,
        quality_met=quality_met,
        qtc_green=qtc_green,
        warnings=warnings,
    )
