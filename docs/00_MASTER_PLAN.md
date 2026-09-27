# Scorecard Studio — Master Plan

**Product:** a generic *Scorecard Creation & Rating System* (think Google Forms / SurveyMonkey, but the "form" is a
weighted, hierarchical scorecard with an anchored rating matrix, and the "response" is a scored, explained evaluation).

**Pilot scorecard:** *Assessment Quality*. It is **seed data**, not code. Nothing in the engine, schema or UI knows
what an "assessment" is.

**Method:** Data-Driven Development Framework v1.1, Phase 1:
Initial Product Scope → Cycle 1 (Data Foundation + first build) → Cycle 2 (Test & Migration) → Cycle 3 (Business
Behaviour, Refined PRD, Acceptance suite) → Tuning.

---

## 1. Scope alignment (what we are and are not building)

| We ARE building | We are NOT building |
|---|---|
| A **meta-system**: users author their own scorecards (purpose, scope, objective, KPIs, hierarchy, weights, rating matrix, quantitative metrics, target) | An app containing one hard-coded scorecard |
| A **rating runtime**: feed text / documents / metric data, get per-parameter scores, reasoning, roll-ups, final score, band, pass/fail vs target | A document-management or project-management tool |
| Pluggable **judges**: human, self-appraisal, LLM, deterministic metric rules | An "ask the AI how good my document is" button (the framework explicitly rejects unanchored ratings) |
| **Subject-agnostic**: tasks, projects, milestones, documents, teams, individuals, products, assessments… are just `subject_type` rows | Security, auth, multi-tenant governance (Phase 2 per the DDD framework) |

The generic test for every design decision: *"Would this still work if the scorecard were for a sales team, a
cloud deployment, or a meeting?"* If not, it belongs in data, not code.

---

## 2. Core concepts (the generic structure)

```
RatingScale (e.g. 0–10, 1–5)          ── has many ──> RatingBand (label, lower bound, colour)
Scorecard (stable identity, code)     ── has many ──> ScorecardVersion (draft → published → retired)
ScorecardVersion                      ── has a tree of ─> Parameter  (L1 → L2 → L3 → L4, max depth configurable)
Parameter (leaf)                      ── has many ──> RatingCriterion (score range → qualitative + quantitative guideline)
Parameter (leaf)                      ── has many ──> Metric ── has many ──> MetricThreshold (value range → score)
Evaluation (one "response")           ── against exactly one published ScorecardVersion
Evaluation                            ── has many ──> ParameterResult (leaf: judged/computed/final score + rationale;
                                                                        non-leaf: rolled-up score)
Evaluation                            ── has many ──> MetricValue, EvaluationDocument
```

Why **versions** are first-class: an evaluation must be reproducible. If someone edits a published scorecard, every
historic score would silently change meaning. So published versions are immutable; editing = "new draft version".

Why a **tree** rather than fixed levels: the requirement is "Level 1 → 2 → 3 → 4". A self-referencing adjacency list
supports any depth with one table; `max_depth` (default 4) is a per-version validation rule, not a schema limit.

Why **weights are sibling-relative**: users think "Question Quality is 30% of the scorecard, and inside it,
correctness is half". Normalising among siblings means users never have to make grand totals add to 100; the UI shows
both the local % and the effective global %.

Why **rating criteria are ranges**: the framework asks for 11 anchored statements per KPI but itself groups "0–3" as
one. Ranges allow both; the validator guarantees the whole scale is covered exactly once.

---

## 3. Scoring mechanism (summary — full spec in `05_SCORING_ENGINE_SPEC.md`)

1. **Leaf score**
   - If the leaf has metrics and every metric has a value → `computed_score` = min of each metric's threshold score
     (conservative "all conditions must hold", matching how the framework's quantitative guidelines read).
   - A judge (human / self / LLM) gives `judged_score` against the rating matrix.
   - `final_score` = computed score when available, else judged score. A judge may override a computed score **only
     with a written override reason** (audited).
   - Optional leaves can be marked *Not Applicable* and are excluded (weights renormalise).
2. **Roll-up** — each non-leaf aggregates its children with its `aggregation` rule: `weighted_mean` (default) or
   `minimum` ("a project cannot be green if the items beneath it are red").
3. **Final score** — same aggregation at the root level.
4. **Band** — highest band whose lower bound ≤ score (no rounding up: *green must be really green*).
5. **Gate** — `meets_target = final ≥ target AND no critical parameter below its minimum`.
6. **QTC (optional per scorecard)** — `green = Q AND T AND C` (logical AND, not average).

---

## 4. Delivery plan mapped to the DDD framework

### Step 0 — Initial Product Scope ✅ (this commit) → `01_INITIAL_PRODUCT_SCOPE.md`

### Cycle 1 — Data Foundation (current implementation target)

| # | Framework activity | Deliverable in this repo | Status |
|---|---|---|---|
| 1.1 | Database design | SQLAlchemy models `backend/app/models.py`; exported DDL `docs/schema.sql`; ERD in `02_DATABASE_DESIGN.md` | In this iteration |
| 1.2 | Data dictionary | `03_DATA_DICTIONARY.md` (type, format, nullability, keys, business + validation rules per field) | In this iteration |
| 1.3 | Scenario-based dataset design | `04_SCENARIO_CATALOGUE.md` — normal, variants, lifecycle, boundary, invalid, migration | In this iteration |
| 1.4 | Data generation & ingestion | `data/scorecards/*.json` (hand-authored definitions), `data/tools/generate.py` (scenario multiplier), `data/tools/ingest.py` (loads through the same validation as the API) | In this iteration |
| 1.5 | Analytics / BI | `/api/analytics/*` endpoints + dashboard page; spec in `06_ANALYTICS_BI.md` | In this iteration |
| 1.6 | First working application | FastAPI backend + React frontend: Library, Builder, Evaluate, Result, Analytics | In this iteration |

### Cycle 2 — Test & Migration (next iteration) → `07_CYCLE2_PLAN.md`
Buggy/invalid datasets with injected-defect traceability, legacy spreadsheet scorecard migration (CSV → versioned
scorecard), 1–5 → 0–10 scale mapping, reconciliation report, defect log.

### Cycle 3 — Business Behaviour, Specification & Testing → `08_CYCLE3_PLAN.md`
Formal state machines (scorecard version + evaluation), resubmission / redo loop, reviewer workflow (self → judge →
gate), subject hierarchy roll-ups (task → milestone → project), refined PRD, business-readable acceptance suite.

### Tuning
Judge reliability (LLM vs expert agreement), performance at ~2,400 evaluations/day, NFRs.

---

## 5. Architecture & technology choices

| Concern | Choice | Reason (first principles) |
|---|---|---|
| Data store | Relational (SQLite in dev, Postgres-compatible SQL) | Framework §11: relational is the natural start for structured workflow apps. Trees + versions + roll-ups need referential integrity. |
| Backend | Python, FastAPI, SQLAlchemy 2, Pydantic 2 | Same language for API, scoring engine, data generator and BI; Pydantic doubles as the data contract. |
| Scoring engine | Pure functions (`app/scoring.py`), no DB access | Deterministic, unit-testable, reusable by the API, generator and analytics. The single most important piece of logic. |
| Validation | Pure functions (`app/validation.py`) returning coded issues | Scenario catalogue references error codes, so invalid-data scenarios are traceable to tests. |
| LLM judge | Anthropic API, structured JSON output, optional | Framework: "LLM first, human second". Must be optional — a scorecard must remain usable with human judges alone. |
| Frontend | React + Vite + TypeScript, no UI kit | Tree editing and live score recomputation need a real client; minimal dependencies. |

---

## 6. What "done" means for Cycle 1

- A user can create a brand-new scorecard for **any subject type** in the UI, with a 4-level hierarchy, weights,
  rating matrix, metrics and target; validation blocks publication of an incomplete scorecard.
- A user can evaluate an input (pasted text, uploaded document, metric values) manually or with the LLM judge and
  see per-parameter scores, reasoning, roll-ups, final score, band, gate and QTC result.
- At least **five scorecards across different subject types** are seeded through the same ingestion path, proving the
  system is generic. Assessment Quality is one of them.
- Every scenario in the catalogue has a matching automated test; every invalid scenario is rejected with its
  documented error code.
- Analytics show band distribution, weakest parameters, pass rates and judge agreement from generated data.

## 7. Pilot measurements (framework §13) — tracked in `PILOT_LOG.md`
Time to first working build · scenario catalogue completeness · schema changes triggered by scenarios · missed
business situations · human corrections to AI-generated artefacts · defects before/after Cycle 3 · rule coverage ·
human effort per iteration.

## 8. Risks & open decisions

| Risk / open point | Current position |
|---|---|
| "Assessment" is ambiguous (trainee test? assessment report?) | Pilot seeds an *assessment instrument* (test/quiz/assignment) scorecard. It is data — swapping it for "assessment report quality" costs zero code. **Needs confirmation.** |
| LLM judge reliability (framework: wrong scores destroy trust) | Store judge model + confidence per rating; analytics compare LLM vs human on the same subject; metric leaves are deterministic and cannot be silently overridden. |
| Coarse rating matrix (ranges) weakens anchoring | Validator warns when a leaf has fewer than 6 criteria rows; full 11-row matrices remain supported. |
| Weighted mean hides a red child | `minimum` aggregation and `is_critical` gates exist precisely for this. |
| Self-appraisal privacy without auth | `is_private` flag; excluded from analytics. Real enforcement arrives with Phase 2 security. |
