# Pilot Log — Quality Scorecard Learning Sprint

Measures required by DDD framework §13, recorded per iteration.

## Iteration 1 — Initial Product Scope + Cycle 1

| Measure | Value |
|---|---|
| Time to first working build | One working session (plan → schema → engine → API → seed data → UI) |
| Scenario catalogue | 4 normal, 11 business-variant, 8 lifecycle, 9 boundary, 21 invalid, 5 migration (catalogued) |
| Seed scorecards | 6, across 6 subject types and 3 rating scales |
| Automated tests | 68 passing (engine, validation, lifecycle, invalid data, judge contract) |
| Schema changes triggered by scenarios | 2 (below) |
| Human corrections to AI-generated artefacts | To be recorded at team review |

### Defects and learning discovered from scenario data
| # | Found by | Finding | Action |
|---|---|---|---|
| 1 | Generated data → analytics | Overall "average score" mixed 0–10, 1–5 and 0–100 scales (19.6) | Cross-scorecard analytics normalised to % of scale |
| 2 | Generated data → judge agreement | Pairwise differences dominated by the 0–100 scorecard | Agreement measured in % of scale; tolerance in % |
| 3 | Generator | Coarse metric thresholds (e.g. 0 errors → 10, 1 → 7) snapped a latent 8.2 to 7, inflating gate failures | Generator picks between bracketing bands by proximity |
| 4 | Invalid scenario I10 | Duplicate parameter codes raised a DB IntegrityError (HTTP 500) | Rejected at save with V015 |
| 5 | UI walkthrough | Empty matrix produced 7 separate V019 errors per leaf | One aggregated V019 per leaf |

### Design questions for the team review
1. **Target 10 with weighted mean** (Requirements Document) is reachable only if every leaf is 10. Is that the
   intent for foundational artefacts, or should foundational targets use "≥ 9 with no leaf below 9"?
2. **Assessment Quality gate on 2.2** fails about 65% of generated assessments because one error scores 7 against
   a floor of 8. That is the policy as written (one factual error blocks issue). Confirm or relax.
3. **Pilot scorecard meaning**: seeded as *assessment instrument quality* (test/quiz/assignment). If the intended
   pilot is *assessment report* quality, swap the JSON. No code changes needed.
4. Should a judge be allowed to rate a metric-backed leaf at all when metrics are present, or should the UI hide
   judgement until the metric is missing?

## Iteration 2 — Cycle 2 (Test & Migration)

| Measure | Value |
|---|---|
| Defects found by flawed data before fixes | 19 of 76 corruption cases (9 crashes), + 7 migration defects during execution |
| Defects found by property-based / fuzz testing | 1 in migration (1-char file name → crash); 0 in the scoring engine (1 test bug) |
| Schema changes triggered | 1 (`evaluation.origin`, `origin_ref`); contract changes: finite numbers, size limits, weight bound, band format |
| Missed business situations discovered by migration | Legacy totals computed with unnormalised weights; conflicting duplicate ratings; repeat ratings of one subject; scales we do not support (1–7); sources with no guidelines at all |
| Tests | 98 automated + 6-step UI smoke |
| Human corrections to AI-generated artefacts | To be recorded at team review |

Details and decisions: [`09_CYCLE2_REPORT.md`](09_CYCLE2_REPORT.md).
