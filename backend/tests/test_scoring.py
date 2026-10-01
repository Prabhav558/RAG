"""Scoring-engine scenarios. Pure functions, no database."""

import pytest

from app.scoring import BandDef, LeafInput, MetricDef, ParamDef, ScorecardDef, ThresholdDef, band_for, compute

BANDS_0_10 = [
    BandDef("Dark green", 9, "GREEN"),
    BandDef("Light green", 8, "GREEN"),
    BandDef("Grey", 7, "AMBER"),
    BandDef("Amber", 6, "AMBER"),
    BandDef("Dark amber", 5, "RED"),
    BandDef("Red", 4, "RED"),
    BandDef("Dark red", 0, "RED"),
]


def card(params, target=8, aggregation="weighted_mean", qtc=False, lo=0, hi=10, bands=BANDS_0_10):
    return ScorecardDef(lo, hi, bands, target, aggregation, qtc, params)


def P(id, parent=None, weight=1.0, **kw):
    return ParamDef(id=id, code=str(id), name=f"p{id}", parent_id=parent, weight=weight, **kw)


def judged(**scores):
    return {int(k[1:]): LeafInput(judged_score=v) for k, v in scores.items()}


def test_N02_weighted_mean_hierarchy():
    # root1 (w3) -> leaves 2 (w1) & 3 (w3); root4 (w1) leaf
    params = [P(1, weight=3), P(2, 1, 1), P(3, 1, 3), P(4, weight=1)]
    out = compute(card(params), judged(p2=6, p3=10, p4=5), {})
    assert out.params[1].final_score == 9.0  # (6*1 + 10*3)/4
    assert out.final_score == 8.0  # (9*3 + 5)/4
    assert out.band.label == "Light green"
    assert out.quality_met is True
    assert out.params[3].effective_weight == pytest.approx(0.75 * 0.75)
    assert out.params[4].effective_weight == pytest.approx(0.25)


def test_L04_partial_evaluation_is_provisional():
    params = [P(1), P(2)]
    out = compute(card(params), judged(p1=9), {})
    assert out.final_score == 9.0  # provisional, over what is scored
    assert out.complete is False
    assert out.pending_leaf_ids == [2]
    assert out.quality_met is None  # no verdict until complete


def test_B01_all_minimum_and_B02_all_maximum():
    params = [P(1), P(2)]
    assert compute(card(params), judged(p1=0, p2=0), {}).band.label == "Dark red"
    top = compute(card(params), judged(p1=10, p2=10), {})
    assert top.final_score == 10 and top.band.label == "Dark green"


def test_B03_exactly_on_target_meets_it():
    out = compute(card([P(1), P(2)]), judged(p1=7, p2=9), {})
    assert out.final_score == 8.0 and out.quality_met is True


def test_B04_no_rounding_up_below_target():
    # 7.99 must not become 8: green must be really green
    params = [P(1, weight=99), P(2, weight=1)]
    out = compute(card(params), judged(p1=8, p2=7), {})
    assert out.final_score == 7.99
    assert out.band.label == "Grey"
    assert out.quality_met is False


def test_B05_single_parameter():
    out = compute(card([P(1)]), judged(p1=8), {})
    assert out.final_score == 8 and out.quality_met


def test_B07_zero_weight_sibling_contributes_nothing():
    out = compute(card([P(1, weight=1), P(2, weight=0)]), judged(p1=9, p2=0), {})
    assert out.final_score == 9.0
    assert out.params[2].effective_weight == 0


def test_BV03_optional_na_renormalises_weights():
    params = [P(1, weight=50), P(2, weight=50, is_optional=True)]
    out = compute(card(params), {1: LeafInput(8), 2: LeafInput(not_applicable=True)}, {})
    assert out.final_score == 8.0
    assert out.params[1].effective_weight == 1.0
    assert out.params[2].score_source == "not_applicable"
    assert out.complete


def test_BV03_na_ignored_for_required_parameter():
    out = compute(card([P(1), P(2)]), {1: LeafInput(8), 2: LeafInput(not_applicable=True)}, {})
    assert out.complete is False  # required leaf cannot be skipped


def test_B08_all_children_na_makes_parent_na():
    params = [P(1), P(2, 1, is_optional=True), P(3, 1, is_optional=True), P(4)]
    na = LeafInput(not_applicable=True)
    out = compute(card(params), {2: na, 3: na, 4: LeafInput(6)}, {})
    assert out.params[1].not_applicable
    assert out.final_score == 6.0


def test_BV04_minimum_aggregation():
    params = [P(1, aggregation="minimum"), P(2, 1), P(3, 1)]
    out = compute(card(params), judged(p2=10, p3=5), {})
    assert out.params[1].final_score == 5


def test_BV05_critical_gate_fails_despite_high_average():
    params = [P(1, weight=9), P(2, weight=1, is_critical=True, min_acceptable_score=7)]
    out = compute(card(params), judged(p1=10, p2=6), {})
    assert out.final_score == 9.6
    assert out.quality_met is False
    assert out.gate_failures[0]["code"] == "2"


def test_BV05_critical_defaults_to_target_floor():
    out = compute(card([P(1), P(2, is_critical=True)]), judged(p1=10, p2=7), {})
    assert out.final_score == 8.5 and out.quality_met is False  # 7 < target 8


def test_BV05_critical_parent_gate():
    params = [P(1, is_critical=True, min_acceptable_score=7), P(2, 1), P(3, 1), P(4)]
    out = compute(card(params), judged(p2=6, p3=7, p4=10), {})
    assert [g["code"] for g in out.gate_failures] == ["1"]


def _metric(id, *bands):
    return MetricDef(id, f"m{id}", [ThresholdDef(lo, hi, s) for lo, hi, s in bands])


def test_BV06_metric_scored_leaf_and_B09_boundary():
    m = _metric(100, (90, None, 10), (70, 90, 7), (None, 70, 3))
    params = [P(1, metrics=[m])]
    assert compute(card(params), {}, {100: 90}).final_score == 10  # boundary goes to upper band
    assert compute(card(params), {}, {100: 89.9}).final_score == 7
    out = compute(card(params), {}, {100: 10})
    assert out.final_score == 3 and out.params[1].score_source == "metric"


def test_BV06_multiple_metrics_take_minimum():
    m1 = _metric(1, (90, None, 10), (None, 90, 5))
    m2 = _metric(2, (None, 1, 10), (1, None, 4))
    out = compute(card([P(1, metrics=[m1, m2])]), {}, {1: 95, 2: 2})
    assert out.final_score == 4


def test_BV06_metric_leaf_falls_back_to_judgement_without_values():
    m = _metric(1, (None, None, 10))
    out = compute(card([P(1, metrics=[m])]), judged(p1=6), {})
    assert out.final_score == 6 and out.params[1].score_source == "judged"


def test_BV07_override_requires_reason():
    m = _metric(1, (None, None, 10))
    params = [P(1, metrics=[m])]
    no_reason = compute(card(params), {1: LeafInput(judged_score=5)}, {1: 3})
    assert no_reason.final_score == 10  # metric wins, judgement kept only for the record
    with_reason = compute(card(params), {1: LeafInput(judged_score=5, override_reason="Key has errors")}, {1: 3})
    assert with_reason.final_score == 5 and with_reason.params[1].score_source == "override"


def test_metric_value_matching_no_threshold_warns():
    m = _metric(1, (0, 50, 5))
    out = compute(card([P(1, metrics=[m])]), {}, {1: 80})
    assert out.final_score is None and out.warnings


def test_BV08_qtc_is_logical_and():
    params = [P(1)]
    c = card(params, qtc=True)
    assert compute(c, judged(p1=9), {}, time_met=True, cost_met=False).qtc_green is False
    assert compute(c, judged(p1=9), {}, time_met=True, cost_met=True).qtc_green is True
    assert compute(c, judged(p1=9), {}, time_met=True, cost_met=None).qtc_green is None
    assert compute(c, judged(p1=7), {}, time_met=True, cost_met=True).qtc_green is False


def test_BV09_context_target_override():
    out = compute(card([P(1)]), judged(p1=6), {}, target_score=6)
    assert out.quality_met is True


def test_BV01_other_scale_uses_its_bands():
    bands = [BandDef("Excellent", 5, "GREEN"), BandDef("Good", 4, "GREEN"), BandDef("Adequate", 3, "AMBER"),
             BandDef("Weak", 2, "RED"), BandDef("Poor", 1, "RED")]
    out = compute(card([P(1), P(2)], target=4, lo=1, hi=5, bands=bands), judged(p1=4, p2=3), {})
    assert out.final_score == 3.5 and out.band.label == "Adequate" and out.quality_met is False


def test_root_minimum_aggregation():
    out = compute(card([P(1), P(2)], aggregation="minimum"), judged(p1=10, p2=7), {})
    assert out.final_score == 7


def test_band_for_none():
    assert band_for(None, BANDS_0_10) is None


def test_zero_weight_only_scored_gives_no_provisional_score():
    """Found by the property tests in Cycle 3: a scored zero-weight leaf must not stand in for its weighted siblings."""
    params = [P(1, weight=0), P(2, weight=0), P(3, weight=1)]
    out = compute(card(params), judged(p2=1), {})
    assert out.final_score is None and out.complete is False
    all_zero = compute(card([P(1, weight=0), P(2, weight=0)]), judged(p1=4, p2=8), {})
    assert all_zero.final_score == 6.0  # equal-weight fallback only when every applicable sibling is zero-weight
