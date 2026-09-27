# Scenario Catalogue (Cycle 1 · §7.3)

*Scenario richness first, volume second.* Each scenario is a business situation the system must store, process,
display or reject. Every one maps to an automated test (`backend/tests/`) and, where it is a data pattern, to the
generator (`data/tools/generate.py`).

## Seed scorecards (proof the system is generic)

| Scorecard | Subject type | Scale | Target | Depth | What it exercises |
|---|---|---|---|---|---|
| **Assessment Quality** (pilot) | assessment | 0–10 | 8 | 4 | Full 4-level hierarchy, metric leaves, critical gates, MIN roll-up, optional leaf |
| Requirements Document Quality | document | 0–10 | **10** | 1 | Foundational target; two metrics on one leaf (min wins) |
| Milestone Delivery Health | milestone | 0–10 | 8 | 2 | **QTC rule**, MIN roll-up on a critical parent |
| Team Collaboration Health | team | **1–5** | 4 | 1 | Different scale and bands |
| Client Email Quality | communication | 0–10 | **7** | 1 | Organisational floor; smallest useful scorecard |
| Cloud Deployment Readiness | deployment | **0–100** | 90 | 1 | Percentage scale, ranged criteria, metric-scored KPI |

## Normal / happy path
| ID | Scenario | Test |
|---|---|---|
| N01 | All seed scorecards ingest, validate and publish; each is a different subject type; assessment has 4 levels and leaf weights sum to 100% | `test_N01_*` |
| N02 | Human rates all leaves → weighted roll-up, band, verdict; completes | `test_N02_*` (engine + API) |
| N03 | LLM judge pre-fills scores/rationale/evidence from text + document; human finishes unrated leaf; completes | `test_N03_*` |
| N04 | Document upload (txt, docx) extracted to text | `test_N04_*` |

## Business variants
| ID | Scenario | Test |
|---|---|---|
| BV01 | 1–5 scale scorecard uses its own bands | `test_BV01_*` |
| BV02 | 0–100 scale with ranged criteria | `test_BV02_*` |
| BV03 | Optional leaf marked N/A → weights renormalise; N/A refused for required leaf | `test_BV03_*` |
| BV04 | MIN roll-up: weakest child decides | `test_BV04_*` |
| BV05 | Critical parameter below floor fails the evaluation despite high average; default floor = target; critical parent | `test_BV05_*` |
| BV06 | Metric-scored leaf; value on boundary goes to upper band; multiple metrics → minimum; no values → judgement | `test_BV06_*`, `test_B09` |
| BV07 | Judge disagrees with metric score: metric wins unless an override reason is given (audited) | `test_BV07_*` |
| BV08 | QTC: quality met, cost missed → not green; missing inputs → pending | `test_BV08_*` |
| BV09 | Per-evaluation target (POC at 6) | `test_BV09_*` |
| BV10 | Clone a reference scorecard as a new draft | `test_BV10_*` |
| BV11 | User creates a new subject type and a new rating scale, then a scorecard on them | `test_BV11_*` |

## Lifecycle states
| ID | Scenario | Test / generator |
|---|---|---|
| L01 | Incomplete draft scorecard saves; issues returned, not blocking | `test_L01_*` |
| L02 | Published version is frozen (E009) | `test_L02_*` |
| L03 | New draft from published → publish v2 retires v1; v1 evaluations keep v1 scores; no new evaluations on v1; one draft at a time (E014) | `test_L03_*` |
| L04 | Partially rated evaluation shows provisional score, no verdict, cannot complete (E005, lists missing leaves) | `test_L04_*` · generator "in progress" |
| L05 | Completed evaluation is immutable (E006) | `test_L05_*` |
| L06 | Void with reason; excluded from analytics | `test_L05_*` · generator "duplicate" |
| L07 | Self-appraisal private by default; hidden from lists and analytics | `test_L07_*` · generator 30% |
| L08 | Failed gate → redo → attempt 2; first-attempt pass rate tracked | `test_L08_*` · generator 60% of fails |

## Boundary cases
| ID | Scenario | Test |
|---|---|---|
| B01 / B02 | All leaves at min / max | `test_B01_*` |
| B03 | Final exactly equals target → meets | `test_B03_*` |
| B04 | 7.99 vs target 8 → below target, Grey band (never rounded up) | `test_B04_*` |
| B05 | Single-parameter scorecard | `test_B05_*` |
| B06 | Depth exactly at max (4) is valid | `test_N01_assessment_quality_has_four_levels` |
| B07 | Zero-weight sibling contributes nothing | `test_B07_*` |
| B08 | All children N/A → parent N/A and excluded | `test_B08_*` |
| B09 | Metric value exactly on threshold boundary | `test_BV06_metric_scored_leaf_and_B09_boundary` |

## Invalid / flawed data (must be rejected with the documented code)
| ID | Scenario | Code |
|---|---|---|
| I00 | No parameters | V001 |
| I01 | Parameter deeper than max depth | V002 |
| I02 | Rating matrix leaves scores uncovered | V005 |
| I03 | Rating matrix overlaps | V006 |
| I04 | Target outside scale | V012 |
| I05 | All sibling weights zero | V003 |
| I06 | Metric thresholds overlap | V009 |
| I07 | Metric without thresholds | V011 |
| I08 | Missing purpose / objective | V016 |
| I09 | Metric on a parent | V017 |
| I10 | Duplicate parameter code (rejected at save) | V015 |
| I11 | Evaluation against a draft/retired version | E001 |
| I12 | Score outside scale | E002 |
| I13 | Rating a parent | E003 |
| I14 | N/A on a required leaf | E004 |
| I15 | Non-integer judged score | E012 |
| I16 | Duplicate scorecard code | E011 |
| I17 | Metric value invalid for type (percent > 100, fractional/negative count) | E013 |
| I18 | Completing a QTC evaluation without time/cost | E007 |
| I19 | Rating scale without a band at its minimum | V013 |
| I20 | Negative weight (contract level) | 422 |
| — | Parameter/metric from another scorecard version | E008 |
| — | LLM judge output: unknown codes, parents, duplicates, out-of-range scores dropped; confidence clamped | `test_judge_output_is_sanitised` |

## Generator archetypes (data patterns, `generate.py`)
| Archetype | Share | Meaning |
|---|---|---|
| excellent | 15% | Consistently strong work |
| solid | 30% | Typical good work around target |
| borderline | 20% | Around the organisational floor |
| weak | 15% | Clearly below standard |
| uneven-critical-miss | 10% | Strong average, one critical parameter fails → gate |
| sparse | 10% | Optional parameters N/A, high variance |

Evaluator profiles: human (no bias, σ 0.6), LLM (+0.3 lenient, σ 0.8), self (+1.0 optimistic, σ 0.8). The
analytics must detect the LLM and self-appraisal bias; that is the check that the BI layer works.

## Migration cases (Cycle 2 — catalogued, not yet implemented)
| ID | Scenario |
|---|---|
| M01 | Legacy spreadsheet scorecard: flat KPI list with weights in % that do not sum to 100 |
| M02 | Legacy ratings on 1–5 needing mapping to 0–10 |
| M03 | Legacy scores without rationale or evaluator |
| M04 | Duplicate legacy subjects with conflicting scores |
| M05 | Legacy KPI with a textual target ("good") instead of a number |
