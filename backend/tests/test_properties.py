"""Cycle 2 · §8.1 — property-based tests: the scoring invariants in docs/05_SCORING_ENGINE_SPEC.md §7
must hold for any tree, any weights and any scores, not only the hand-written examples."""

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from app.scoring import BandDef, LeafInput, ParamDef, ScorecardDef, compute

LO, HI = 0, 10
BANDS = [BandDef("G", 8, "GREEN"), BandDef("A", 6, "AMBER"), BandDef("R", 0, "RED")]


@st.composite
def trees(draw, max_nodes=25):
    """Random parameter tree (ids 1..n) with random weights, aggregation, optional/critical flags."""
    n = draw(st.integers(1, max_nodes))
    params = []
    for i in range(1, n + 1):
        parent = draw(st.one_of(st.none(), st.integers(1, i - 1))) if i > 1 else None
        params.append(ParamDef(
            id=i, code=str(i), name=f"p{i}", parent_id=parent,
            weight=draw(st.one_of(st.just(0.0), st.floats(0.01, 1000))),
            sort_order=i,
            aggregation=draw(st.sampled_from(["weighted_mean", "minimum"])),
            is_critical=draw(st.booleans()),
            min_acceptable_score=draw(st.one_of(st.none(), st.integers(LO, HI))),
            is_optional=draw(st.booleans()),
        ))
    return params


def leaves_of(params):
    parents = {p.parent_id for p in params}
    return [p for p in params if p.id not in parents]


@st.composite
def scenario(draw):
    params = draw(trees())
    inputs = {}
    for p in leaves_of(params):
        na = p.is_optional and draw(st.booleans())
        score = draw(st.one_of(st.none(), st.integers(LO, HI)))
        inputs[p.id] = LeafInput(judged_score=score, not_applicable=na)
    card = ScorecardDef(LO, HI, BANDS, draw(st.integers(LO, HI)), draw(st.sampled_from(["weighted_mean", "minimum"])),
                        False, params)
    return card, inputs


@settings(max_examples=400, deadline=None)
@given(scenario())
def test_scores_stay_in_scale(sc):
    card, inputs = sc
    out = compute(card, inputs, {})
    for o in out.params.values():
        if o.final_score is not None:
            assert LO <= o.final_score <= HI
    if out.final_score is not None:
        assert LO <= out.final_score <= HI


@settings(max_examples=400, deadline=None)
@given(scenario())
def test_deterministic(sc):
    card, inputs = sc
    a, b = compute(card, inputs, {}), compute(copy.deepcopy(card), copy.deepcopy(inputs), {})
    assert (a.final_score, a.quality_met, a.gate_failures) == (b.final_score, b.quality_met, b.gate_failures)


@settings(max_examples=400, deadline=None)
@given(scenario())
def test_verdict_only_when_complete(sc):
    card, inputs = sc
    out = compute(card, inputs, {})
    if not out.complete:
        assert out.quality_met is None
    else:
        assert out.pending_leaf_ids == []


@settings(max_examples=400, deadline=None)
@given(scenario())
def test_minimum_parent_never_exceeds_a_child(sc):
    card, inputs = sc
    out = compute(card, inputs, {})
    for p in card.params:
        if p.aggregation != "minimum" or out.params[p.id].final_score is None:
            continue
        kids = [out.params[k.id] for k in card.params if k.parent_id == p.id]
        scored = [k.final_score for k in kids if k.final_score is not None and not k.not_applicable]
        if not kids:  # a leaf: aggregation does not apply
            continue
        assert out.params[p.id].final_score <= min(scored) + 1e-9


@settings(max_examples=400, deadline=None)
@given(scenario())
def test_weighted_mean_between_child_extremes(sc):
    card, inputs = sc
    out = compute(card, inputs, {})
    for p in card.params:
        if p.aggregation != "weighted_mean" or out.params[p.id].final_score is None:
            continue
        kids = [out.params[k.id] for k in card.params if k.parent_id == p.id]
        scored = [k.final_score for k in kids if k.final_score is not None and not k.not_applicable]
        if scored:
            assert min(scored) - 0.01 <= out.params[p.id].final_score <= max(scored) + 0.01


@settings(max_examples=400, deadline=None)
@given(scenario())
def test_effective_weights_of_applicable_leaves_sum_to_one(sc):
    card, inputs = sc
    out = compute(card, inputs, {})
    applicable = [out.params[p.id] for p in leaves_of(card.params) if not out.params[p.id].not_applicable]
    if applicable and any(not out.params[r.id].not_applicable for r in card.params if r.parent_id is None):
        assert abs(sum(o.effective_weight for o in applicable) - 1) < 1e-6


@settings(max_examples=300, deadline=None)
@given(scenario(), st.data())
def test_adding_na_optional_leaf_changes_nothing(sc, data):
    card, inputs = sc
    before = compute(card, inputs, {})
    new_id = max(p.id for p in card.params) + 1
    parent = data.draw(st.one_of(st.none(), st.sampled_from([p.id for p in card.params])))
    if parent is not None and parent in inputs:  # attaching under a leaf would turn it into a parent
        return
    card2 = copy.deepcopy(card)
    card2.params.append(ParamDef(id=new_id, code=str(new_id), name="extra", parent_id=parent,
                                 weight=data.draw(st.floats(0.01, 1000)), is_optional=True))
    inputs2 = {**inputs, new_id: LeafInput(not_applicable=True)}
    after = compute(card2, inputs2, {})
    assert after.final_score == before.final_score
    assert after.quality_met == before.quality_met


@settings(max_examples=300, deadline=None)
@given(scenario(), st.data())
def test_zero_weight_leaf_does_not_move_weighted_mean(sc, data):
    card, inputs = sc
    if card.aggregation != "weighted_mean" or any(p.aggregation == "minimum" for p in card.params):
        return
    before = compute(card, inputs, {})
    if before.final_score is None:
        return
    new_id = max(p.id for p in card.params) + 1
    parent = data.draw(st.one_of(st.none(), st.sampled_from([p.id for p in card.params if p.id not in inputs] or [None])))
    siblings = [p for p in card.params if p.parent_id == parent]
    if not siblings or sum(p.weight for p in siblings) <= 0:
        return  # all-zero siblings fall back to equal weights; a new zero sibling would legitimately count
    card2 = copy.deepcopy(card)
    card2.params.append(ParamDef(id=new_id, code=str(new_id), name="zero", parent_id=parent, weight=0.0))
    after = compute(card2, {**inputs, new_id: LeafInput(judged_score=data.draw(st.integers(LO, HI)))}, {})
    assert after.final_score == before.final_score
