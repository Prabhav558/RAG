# Cycle 2 — Test & Migration (plan)

Goal: evidence of behaviour under flawed and migrated data (DDD framework §8).

## 8.1 Test design
- Property-based tests on the engine (Hypothesis): the invariants in `05_SCORING_ENGINE_SPEC.md §7` over random trees.
- API contract tests generated from the OpenAPI schema (fuzz types, missing fields, huge payloads).
- UI smoke suite (Playwright): create scorecard → publish → evaluate → complete → analytics.

## 8.2 Buggy / invalid scenario datasets
`data/tools/corrupt.py` (to build): takes valid seed definitions and evaluations and injects one defect per record,
tagged `{scenario_id, defect_type}` so every rejection is traceable:
missing references, inverted ranges, overlapping thresholds, duplicate codes, wrong scale codes, unicode/huge
text, metric values of the wrong type, ratings for parameters of other versions, circular parent references
(import path), truncated documents, and corrupt DOCX/PDF files.
Expected result: 100% rejected with the documented code; 0 HTTP 500s.

## 8.3 Migration strategy — legacy spreadsheet scorecards
| Source (typical spreadsheet) | Target | Transformation / rule |
|---|---|---|
| Sheet name | scorecard.name, code (slug) | Duplicate code → suffix `-2` |
| KPI rows (flat or indented "1.1") | parameter tree | Infer parent from numbering; indentation as fallback |
| Weight % column | parameter.weight | Accept any sum; flag rows with blank weight → default 1 + warning |
| Score description columns 0..10 | rating_criterion | Merge identical adjacent descriptions into ranges |
| Rating columns per subject | evaluation + parameter_result | One evaluation per subject column; evaluator from header |
| 1–5 ratings | 0–10 | Configurable map; default linear `(x−1)·2.5`, flag as `source=import` |
| Missing rationale | rationale = null | Reported, not rejected |
| Text target ("good") | target_score | Map table; unmapped → reject row |

Rejection and reconciliation: every source row ends in exactly one of *imported*, *imported with warning*,
*rejected (reason)*. The reconciliation report compares row counts and recomputed totals against the sheet's own
totals, and explains every difference.

## 8.4 Execution & 8.5 Summary
Run the migration on 3 real team spreadsheets plus the corrupted set. Record defects, affected scenarios,
schema/dictionary changes and production impact in `PILOT_LOG.md`.

## Exit criteria
Zero 500s on the corrupted set · every rejection coded · reconciliation within 0.01 of sheet totals for clean rows ·
engine properties hold for 10k random trees.
