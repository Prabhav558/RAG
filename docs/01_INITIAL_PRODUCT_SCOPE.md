# Initial Product Scope — Scorecard Studio

Deliberately lighter than a PRD (DDD framework §6). The refined PRD is produced in Cycle 3 from evidence.

## Problem
Quality of work (documents, tasks, projects, teams, people, products) is judged by unanchored opinion or
self-declared status. Ratings are arbitrary, not comparable, and do not scale (≈2,400 tasks/day at 300 people).
The Quality Scorecard Framework solves this *methodologically* — purpose, KPIs, anchored guidelines, targets,
gates — but there is no tool that lets anyone **author** such scorecards and **apply** them consistently.
Every team currently rebuilds scorecards in spreadsheets, with no versioning, no roll-up maths and no audit of why a
score was given.

## Actors
| Actor | Does |
|---|---|
| Scorecard designer | Creates/edits scorecards: purpose, scope, objective, KPIs, hierarchy, weights, rating matrix, metrics, target; publishes versions |
| Evaluator (human expert) | Rates a subject against a published scorecard, gives rationale |
| Task owner (self-appraiser) | Privately scores own work before submission |
| LLM judge | Rates a subject against the rating matrix, returns score + rationale + evidence per leaf |
| Lead / manager | Sets context-specific target, reads results, acts on reds |
| Leadership / analyst | Reads RAG distributions, weak parameters, pass rates, judge agreement |

## Expected outcomes
1. Any user can create a scorecard for any subject type without developer involvement.
2. The same input scored twice against the same scorecard version yields explainable, comparable results.
3. Every score shows *why*: criterion matched, rationale, evidence, metric values.
4. Honest RAG: banding never rounds up; critical parameters and QTC act as gates.
5. A growing, reusable library of reference scorecards (clone → adapt).

## Constraints
- Phase 1: no auth/security/governance (framework §3). Single-user assumptions are acceptable.
- LLM must be optional and replaceable; framework is tool-independent.
- Scoring must be deterministic given the same leaf scores.
- Published scorecard versions are immutable (reproducibility).
- Target POC quality 6–7 for the build; foundational data model held to a higher bar.

## Broad functional scope
**In:** scorecard authoring (all elements in the brief), hierarchy up to 4 levels (configurable), custom rating
scales and colour bands, validation & publishing, versioning & cloning, evaluation of text/document/metric input,
manual + self + LLM + metric scoring, weighted/min roll-ups, target gate, critical gates, QTC, results view,
analytics, data generator & ingestion, JSON import/export of scorecards.

**Later:** subject hierarchy roll-ups across evaluations (task → project), reviewer workflow and resubmission loop
(Cycle 3), legacy spreadsheet migration (Cycle 2), clarity agent for ODTQRC, capability/competency diagnosis,
multi-judge parallel validation, auth & governance (Phase 2).
