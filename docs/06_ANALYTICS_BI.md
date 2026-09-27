# Analytics & BI (Cycle 1 · §7.5)

Purpose: test that the data model supports the *intelligence* expected from the product, not just transactions.
Implemented in `backend/app/analytics.py`, exposed under `/api/analytics/*`, rendered on the Analytics page.

## Rules
- Only `completed`, non-private evaluations count. Drafts, voids and self-appraisals are excluded.
- Cross-scorecard aggregates use **% of scale** `(score − min)/(max − min)`, because averaging 0–10, 1–5 and
  0–100 scores is meaningless. Per-scorecard views show native scores too.

## Questions answered
| Question (leadership) | Endpoint / measure |
|---|---|
| How honest is the board? | RAG distribution (overall and per scorecard) |
| Is work reaching target? First time? | `pass_rate`, `first_attempt_pass_rate` |
| How often do critical gates stop work? | `gate_failure_rate` per scorecard |
| QTC: are we green on quality, time **and** cost? | `qtc_green_rate` |
| Which parameters drag scores down? | `/parameters/{version}`: avg, min, max, % below target, overrides, metric-scored count per node; weakest leaves |
| Can we trust the LLM judge? | `/judge-agreement`: paired subjects, mean absolute difference, within tolerance, same-verdict rate, signed bias |
| Are evaluators biased? | average by evaluator type |
| Is quality improving? | `/trend`: monthly average and pass rate |

## Framework pilot measures covered (Quality Scorecard Framework §16)
- Share of tasks reaching target on first submission ✔
- Distribution of scores and colour bands by work type ✔ (by team: needs a team dimension; Cycle 3)
- Agreement between LLM judge and expert judge ✔
- Guideline revisions triggered by disputed scores ◐ (overrides counted per parameter; revision tracking is Cycle 3)
- QTC outcomes ✔ (quality/time/cost misses tracked separately: Cycle 3)

## Observed on generated data (seed 42, multiplier 1)
The generator injects a +0.3 lenient LLM and a +1.0 optimistic self-appraiser. The dashboard surfaces the LLM
bias in the "LLM judge vs human" panel, and excludes self-appraisal from every aggregate, as designed.
Requirements Document Quality shows a 0% pass rate at target 10. That is correct maths, but a real signal for the
pilot review: with a weighted mean, target 10 means *every* leaf must be 10.
