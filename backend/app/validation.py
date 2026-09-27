"""Scorecard definition validation. Pure functions returning coded issues.

Errors block publishing; warnings are advisory. Codes are referenced by the scenario catalogue
(docs/04_SCENARIO_CATALOGUE.md) and the tests, so keep them stable.
"""

from __future__ import annotations

from .schemas import Issue, ParameterIn, VersionIn

MAX_TOP_LEVEL_ADVISED = 8
MIN_CRITERIA_ROWS_ADVISED = 6


class ScaleInfo:
    def __init__(self, min_value: int, max_value: int, band_lower_bounds: list[float]):
        self.min_value = min_value
        self.max_value = max_value
        self.band_lower_bounds = band_lower_bounds


def _err(code, msg, path=None):
    return Issue(code=code, severity="error", message=msg, path=path)


def _warn(code, msg, path=None):
    return Issue(code=code, severity="warning", message=msg, path=path)


def validate_scale(scale: ScaleInfo) -> list[Issue]:
    issues = []
    if scale.max_value <= scale.min_value:
        issues.append(_err("V013", "Rating scale max must be greater than min"))
    lbs = scale.band_lower_bounds
    if not lbs:
        issues.append(_err("V013", "Rating scale has no bands"))
    else:
        if min(lbs) > scale.min_value:
            issues.append(_err("V013", f"No band covers the scale minimum {scale.min_value}"))
        if any(lb < scale.min_value or lb > scale.max_value for lb in lbs):
            issues.append(_err("V013", "A band lower bound lies outside the scale"))
        if len(set(lbs)) != len(lbs):
            issues.append(_err("V013", "Two bands share the same lower bound"))
    return issues


def validate_version(v: VersionIn, scale: ScaleInfo) -> list[Issue]:
    issues: list[Issue] = []
    lo, hi = scale.min_value, scale.max_value

    if not v.purpose.strip():
        issues.append(_err("V016", "Purpose is required: every scorecard must state why it exists", "purpose"))
    if not v.objective.strip():
        issues.append(_err("V016", "Assessment/quality objective is required", "objective"))
    if not (lo <= v.target_score <= hi):
        issues.append(_err("V012", f"Target {v.target_score} is outside the scale {lo}–{hi}", "target_score"))
    if not v.parameters:
        issues.append(_err("V001", "A scorecard needs at least one parameter", "parameters"))
    if len(v.parameters) > MAX_TOP_LEVEL_ADVISED:
        issues.append(
            _warn("W101", f"{len(v.parameters)} top-level KPIs; the framework advises 5–6 so each earns its place")
        )

    seen_codes: set[str] = set()

    def check_siblings(nodes: list[ParameterIn], path: str):
        if nodes and sum(n.weight for n in nodes) <= 0:
            issues.append(_err("V003", "Sibling parameters must have at least one positive weight", path))

    def walk(p: ParameterIn, depth: int, path: str):
        here = f"{path}/{p.code}"
        if p.code in seen_codes:
            issues.append(_err("V015", f"Duplicate parameter code '{p.code}'", here))
        seen_codes.add(p.code)
        if depth > v.max_depth:
            issues.append(_err("V002", f"'{p.name}' is at level {depth}; max depth is {v.max_depth}", here))
        if p.weight < 0:
            issues.append(_err("V004", "Weight cannot be negative", here))
        if p.min_acceptable_score is not None and not (lo <= p.min_acceptable_score <= hi):
            issues.append(_err("V014", "Minimum acceptable score is outside the scale", here))
        if p.is_critical and p.is_optional:
            issues.append(_warn("W105", "Parameter is both critical and optional; marking it N/A bypasses the gate", here))

        if p.children:
            check_siblings(p.children, here)
            if p.criteria:
                issues.append(_warn("W104", "Rating criteria on a parent are ignored; parents are rolled up", here))
            if p.metrics:
                issues.append(_err("V017", "Metrics can only be attached to leaf parameters", here))
            for c in p.children:
                walk(c, depth + 1, here)
            return

        # leaf: rating matrix must cover every integer score exactly once
        covered: dict[int, int] = {}
        for c in p.criteria:
            if c.score_min < lo or c.score_max > hi:
                issues.append(_err("V007", f"Criterion {c.score_min}–{c.score_max} is outside the scale", here))
            if c.score_max < c.score_min:
                issues.append(_err("V007", f"Criterion range {c.score_min}–{c.score_max} is inverted", here))
            for s in range(max(c.score_min, lo), min(c.score_max, hi) + 1):
                covered[s] = covered.get(s, 0) + 1
        blank = [f"{c.score_min}–{c.score_max}" if c.score_min != c.score_max else str(c.score_min)
                 for c in p.criteria if not c.qualitative.strip()]
        if blank:
            issues.append(_err("V019", f"Rating-matrix rows without a qualitative guideline: {', '.join(blank)}", here))
        missing = [s for s in range(lo, hi + 1) if s not in covered]
        overlap = [s for s, n in covered.items() if n > 1]
        if missing:
            issues.append(_err("V005", f"Rating matrix does not cover scores {missing}", here))
        if overlap:
            issues.append(_err("V006", f"Rating matrix defines scores {sorted(overlap)} more than once", here))
        if p.criteria and len(p.criteria) < min(MIN_CRITERIA_ROWS_ADVISED, hi - lo + 1):
            issues.append(
                _warn("W102", f"Only {len(p.criteria)} rating-matrix rows; coarse anchors reduce consistency", here)
            )

        metric_codes: set[str] = set()
        for m in p.metrics:
            mp = f"{here}#{m.code}"
            if m.code in metric_codes:
                issues.append(_err("V015", f"Duplicate metric code '{m.code}'", mp))
            metric_codes.add(m.code)
            if not m.thresholds:
                issues.append(_err("V011", "Metric has no thresholds, so it cannot produce a score", mp))
                continue
            for t in m.thresholds:
                if not (lo <= t.score <= hi):
                    issues.append(_err("V010", f"Threshold score {t.score} is outside the scale", mp))
                if t.min_value is not None and t.max_value is not None and t.max_value <= t.min_value:
                    issues.append(_err("V009", f"Threshold [{t.min_value}, {t.max_value}) is empty", mp))
            ordered = sorted(m.thresholds, key=lambda t: float("-inf") if t.min_value is None else t.min_value)
            for a, b in zip(ordered, ordered[1:]):
                a_hi = float("inf") if a.max_value is None else a.max_value
                b_lo = float("-inf") if b.min_value is None else b.min_value
                if b_lo < a_hi:
                    issues.append(_err("V009", "Metric thresholds overlap", mp))
                elif b_lo > a_hi:
                    issues.append(_warn("W103", f"Metric thresholds leave a gap between {a_hi} and {b_lo}", mp))

    check_siblings(v.parameters, "")
    for p in v.parameters:
        walk(p, 1, "")
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
