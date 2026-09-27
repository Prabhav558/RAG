# Refined Product Requirements — Scorecard Studio (framework §9.4)

Status: **evidence-based PRD**, produced after Cycles 1–3. It consolidates the Initial Product Scope, the data model,
the scenario catalogue, migration learning and the business-behaviour specification. Every requirement below is
backed by an automated check (test ID or acceptance scenario), so this document and the system cannot silently
drift apart.

## 1. Product
A generic **Scorecard Creation & Rating System**. Users design scorecards for any subject (task, milestone,
project, document, assessment, team, individual, product, meeting, communication, deployment, or any type they
add) and use them to rate work consistently, gate it, and learn from the results. *Assessment Quality* is the pilot
scorecard, delivered as data.

**Problem it solves.** Quality judged by unanchored opinion or self-declared status; no way to review ~2,400
tasks/day by hand; spreadsheet scorecards without versioning, roll-up maths or audit.

## 2. Actors and permissions (Phase 1: identity asserted by name, no login)
| Actor | Can |
|---|---|
| Designer | Create/edit draft scorecards; submit for review; publish directly when review is not required; retire versions |
| Reviewer | Approve or return a version in review; **never their own submission** |
| Owner | Own subjects; self-appraise (private); submit; withdraw; resubmit after redo |
| Judge (human / LLM) | Evaluate a submission in review; **never their own work**; only they edit their judgement |
| Adjudicator | Settle judge disagreement; **neither owner nor judge**; reason mandatory |
| Lead | Cancel work; record red diagnoses (never about themselves) |
| Importer | Preview and commit legacy spreadsheet migrations |

## 3. Functional requirements

### 3.1 Scorecard design
| ID | Requirement | Verified by |
|---|---|---|
| R-D1 | A scorecard has purpose, scope, objective (purpose and objective required to publish), guidance, subject type, rating scale, target, root roll-up | `01_designing_scorecards` · V016 |
| R-D2 | Parameters form a tree, depth configurable 1–6 (default 4); weights relative to siblings; effective share shown | N01, B06 · acceptance "four levels" |
| R-D3 | Every leaf has a rating matrix covering every score on the scale exactly once, each row with a qualitative (required) and quantitative guideline | V005/V006/V019 · acceptance "every score needs a guideline" |
| R-D4 | Leaves may carry metrics with value→score thresholds (non-overlapping, finite) | BV06, V009–V011 |
| R-D5 | Parents roll up by weighted mean or minimum; parameters can be critical gates with a floor; leaves can be optional | BV03–BV05 |
| R-D6 | Rating scales and bands are user-defined; bands tile the scale | BV01/BV02/BV11, V013 |
| R-D7 | Published versions are immutable; change = new version; publishing retires the previous; retire explicitly with reason | L02/L03 · version matrix |
| R-D8 | Optional two-person review: submit → approve (not by submitter) / request changes (comment) | `test_review_workflow…` · acceptance |
| R-D9 | Gate settings per version: required judges (1–5), disagreement tolerance, self-appraisal required, foundational | workflow tests |
| R-D10 | Clone scorecards; import/export JSON; ≤ 500 parameters; size limits on text | BV10, V020, corruption D15/D16 |

### 3.2 Rating
| ID | Requirement | Verified by |
|---|---|---|
| R-R1 | Evaluate text, uploaded documents (txt/md/csv/json/docx/pdf) or metric data | N04, D80–D87 |
| R-R2 | Leaf score = metric score when all metric values present; else judged; judges override metrics only with a reason | BV06/BV07 · acceptance "metric beats opinion" |
| R-R3 | Deterministic roll-up; bands never round up; verdict only when complete | B03/B04, property tests · acceptance "never rounded up" |
| R-R4 | Critical parameters below their floor fail the evaluation regardless of average | BV05 · acceptance "one factual error" |
| R-R5 | QTC: green = quality AND time AND cost | BV08 · acceptance "green needs Q AND T AND C" |
| R-R6 | LLM judge proposes leaf scores, rationale, evidence and metric values from a structured-output schema; the engine does all maths; untrusted input cannot change the scale or codes | N03, judge sanitisation tests |
| R-R7 | Every leaf result shows its source (judged/metric/override/N/A), matched guideline, rationale, evidence | evaluation view |

### 3.3 The quality gate (submissions)
| ID | Requirement | Verified by |
|---|---|---|
| R-G1 | Subjects form a tree with owner, due date and budget | S008 tests |
| R-G2 | A submission is one attempt through a published version: open → in review → decided (passed/redo) / adjudication; withdrawn; cancelled | transition matrix (every state × action) |
| R-G3 | Self-appraisal only while open; private to the owner; optionally mandatory before submit | S005, S009, S011 |
| R-G4 | Judges only while in review; owner cannot judge; decision needs N completed judges; official score = mean | S003/S004 · acceptance "agreeing judges" |
| R-G5 | Different verdicts or spread > tolerance → adjudication by an independent person, with reason | acceptance "disagreeing judges" |
| R-G6 | Redo → new attempt linked to the previous; history kept | acceptance "redone as a new attempt" |
| R-G7 | QTC computed from facts: submitted ≤ due; cumulative cost ≤ budget | `test_qtc_*`, `test_cost_is_cumulative…` |
| R-G8 | Foundational dark-red result stops every other start in the project until fixed | acceptance "dark-red specification stops the project" |
| R-G9 | Roll-up: a parent is green only when it and everything beneath it is green; blocked › red › in progress › not started › green | acceptance "project is green only when…" |
| R-G10 | Every transition is audited (who, when, from → to, why) | audit tests |
| R-G11 | Concurrent actions on one record happen once; losers get S001/S012 | `test_concurrent_decide…` |

### 3.4 Learning
| ID | Requirement | Verified by |
|---|---|---|
| R-L1 | RAG distribution, pass and first-attempt pass rates, per-scorecard summary on a common % scale | analytics tests |
| R-L2 | Per-parameter breakdown: weakest leaves, % below target, overrides | analytics tests |
| R-L3 | LLM vs human agreement and bias | analytics tests |
| R-L4 | Gate outcomes, QTC misses separately, guideline disputes (judge spread per parameter), self-appraisal honesty | `test_behaviour_analytics` |
| R-L5 | Red diagnosis: ≥ 3 reds in 90 days (configurable) → attention list until a lead records skill/aptitude/will/allocation + action | acceptance "three reds" |

### 3.5 Migration
| ID | Requirement | Verified by |
|---|---|---|
| R-M1 | Import legacy xlsx/csv scorecards and ratings with dry-run preview, row-level outcomes and reconciliation | `05_migration.feature`, 21 migration tests |
| R-M2 | Never invent quality: unknown → unrated; fractions round down; conflicts rejected | M02–M06 tests |
| R-M3 | Every difference from legacy totals explained, or reported as unexplained | `test_every_difference_is_explained` |

## 4. Non-functional requirements
| ID | Requirement | Evidence |
|---|---|---|
| N1 | p95 < 300 ms for page loads and rating updates at pilot volume | ≤ 140 ms at ~14–16k evaluations (`tuning/TUNING_REPORT.md`) |
| N2 | ≥ 2,400 evaluations/day | ~780k/day per worker; 0 errors with 16 concurrent writers |
| N3 | No HTTP 500 on any malformed input | 76-case corruption catalogue, 8k migration fuzz inputs |
| N4 | Runs on SQLite (pilot) and Postgres (shared) | full suite on both |
| N5 | Schema changes by migration; existing databases upgrade in place | Alembic tests |
| N6 | Accessible status: never colour alone (icons + labels), keyboard-usable controls, responsive to phone width | UI review, smoke suite |

## 5. Out of scope (Phase 2 per the framework)
Authentication and authorisation (actor names are asserted, not proven), data classification, retention,
encryption policy, multi-tenancy, SSO. ODTQRC task definition and the clarity agent; C1–C6 capability and competency
levels; predictive and prescriptive analytics.

## 6. Open decisions (need a business owner)
1. **Target 10 with a weighted mean** needs every parameter to be a 10. Keep it, or use "≥ 9 with no parameter below 9"
   for foundational work?
2. **One factual error fails an assessment** (critical floor 8; one error scores 7). Intended?
3. **"Assessment" pilot meaning**: assessment instrument (implemented) vs assessment report: a JSON swap.
4. **Legacy totals** in at least one real-style workbook understated quality by ~1.5–2 points (weights never
   normalised). Communicate before comparing old and new numbers.
5. **Import defaults**: placeholders for missing guidelines (on), conflicting duplicates rejected, rescale rule.
6. **Red threshold** (3 in 90 days) is a proposal subject to HR policy.
