# Scoring Engine Specification

Implementation: `backend/app/scoring.py` (pure functions). Tests: `backend/tests/test_scoring.py`.
The LLM judge **never** computes roll-ups, bands or verdicts: it only proposes leaf scores. Everything below is
deterministic.

## Inputs
- Scorecard version: scale `[min, max]`, bands, target, root aggregation, QTC flag, parameter tree.
- Per leaf: `judged_score` (whole number in scale), `not_applicable`, `override_reason`.
- Per metric: `value`.
- Per evaluation: `target_score` (defaults to the version's), `time_met`, `cost_met`.

## 1. Leaf score
```
if leaf.not_applicable and leaf.is_optional:     source = not_applicable (excluded)
computed = min(threshold_score(m, value[m]) for m in leaf.metrics)   # only if every metric has a value
                                                                      # that falls inside a threshold
if override_reason and judged is not None:        final = judged,   source = override
elif computed is not None:                        final = computed, source = metric
elif judged is not None:                          final = judged,   source = judged
else:                                             final = None,     source = pending
```
`threshold_score`: the threshold with `min ≤ value < max` (open bounds when null).
Rationale for *min across metrics*: quantitative guidelines read as conjunctions ("≥ 90% with acceptance criteria
**and** ≤ 2 undefined terms"), so the weakest measure bounds the score.

## 2. Roll-up (parents and root)
Let `A` = children that are not N/A, `S` = those in `A` with a score.
- `weighted_mean`: Σ(score·w) / Σw over `S`. If Σw = 0, equal weights.
- `minimum`: min over `S`.
- If `A` is empty the parent is N/A. If `S` is empty the parent has no score yet.
- A node is *complete* when every node in `A` is complete.

Partial evaluations therefore show a **provisional** score over what has been rated, with no verdict.

## 3. Effective weight
`effective_weight(node) = Π normalised sibling weight` along the path, computed over non-N/A siblings. It is shown
as "x% of total" and stored per result for analytics. It is informational for `minimum` parents.

## 4. Rounding and bands
- Every score is rounded to 2 decimals **after** aggregation.
- Band = the band with the highest `lower_bound ≤ score`. There is no rounding up: 7.99 is Grey, not Light green.

## 5. Verdict
```
gate_failures = [p for p in critical params (leaf or parent) with a score
                 if p.final < (p.min_acceptable_score ?? target)]
quality_met   = complete and final ≥ target and not gate_failures      (None while incomplete)
qtc_green     = quality_met AND time_met AND cost_met   if qtc_enabled  (None if any input missing)
              = quality_met                              otherwise
```

## 6. Worked example (Assessment Quality)
Rating every judged leaf 8 and entering *1 technical error* (2.2 metric → 7):

| Node | Score | How |
|---|---|---|
| 2.2 Technical correctness | 7 | metric: 1 error → 7 (judged 8 is kept for the record) |
| 2 Item Quality | 0.3·8 + 0.4·7 + 0.3·8 = 7.6 | weighted mean |
| Final | 7.86 | weighted mean of the five KPIs |
| Band | Grey | 7 ≤ 7.86 < 8 |
| Verdict | Below target; gate failed on 2.2 (7 < 8) | |

## 7. Invariants (tested)
1. Scores never leave the scale.
2. Adding an N/A optional leaf never changes the final score.
3. A zero-weight leaf never changes a weighted-mean score.
4. `minimum` parent ≤ every applicable child.
5. `quality_met` is `None` until every required leaf is scored.
6. Same inputs → same outputs (no randomness, no clock).
