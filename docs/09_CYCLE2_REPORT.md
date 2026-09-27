# Cycle 2 — Test & Migration Summary (§8.5)

Cycle 2 deliberately stressed the Cycle 1 application with flawed data and legacy migration. This is the record of
what broke, what changed and what it means for production.

## Headline
| Measure | Before Cycle 2 | After |
|---|---|---|
| Single-defect corruption cases | 76 cases: **57 pass, 19 fail (9 HTTP 500 crashes)** | 76/76 pass, 0 crashes |
| Automated tests | 68 | **98** (+ corruption catalogue, 8 engine properties over ~3,000 random trees, 21 migration tests incl. fuzzing) |
| Migration fuzzing | — | 8,000 random CSV pairs and file names: 0 crashes; every input ends in a coded outcome |
| Legacy datasets migrated | — | 6 sources / 7 runs: 4 scorecards, 53 evaluations imported, 5 rows rejected with reasons, 3 files refused with coded fatals |
| Legacy totals reconciled | — | 36 totals compared: 15 reproduced exactly, 21 differ, **0 unexplained** |
| UI smoke suite | Manual | `npm run smoke`: 6/6 pass (create → publish → evaluate → import → analytics, 0 browser errors) |

## 8.1 Test design
| Layer | What | Where |
|---|---|---|
| Scenario tests | Cycle 1 catalogue (normal, variants, lifecycle, boundary, invalid) | `tests/test_scoring.py`, `tests/test_api.py` |
| Property tests | Engine invariants over random trees, weights, N/A and scores | `tests/test_properties.py` |
| Corruption catalogue | 76 single-defect cases incl. 4 positive controls | `data/tools/corrupt.py`, `tests/test_corruption.py` |
| Migration | Every M-rule, reconciliation, commit, API, fuzzing, truncated workbooks | `tests/test_migration.py` |
| UI smoke | End-to-end in a real browser | `frontend/e2e/smoke.mjs` |

## 8.2 Defects found by the buggy datasets
Full before/after: `docs/cycle2/corruption_report_baseline.md` → `docs/cycle2/corruption_report.md`.

| # | Defect (injected data) | Severity | Root cause | Fix |
|---|---|---|---|---|
| 1 | NaN / Infinity in target, weight, judged score, metric value → **500** | Critical | JSON allows NaN; pydantic accepted it; SQLite NOT NULL and `int(nan)` then failed | `allow_inf_nan=False` on every inbound contract |
| 2 | Even after (1), NaN still returned **500** | Critical | FastAPI's 422 body echoes the input, and the JSON encoder refuses NaN, so the *error handler* crashed | Own 422 handler that never echoes raw input |
| 3 | Inverted criterion range / duplicate metric code → **500** | High | Draft save allowed what the DB CHECK/UNIQUE constraints forbid | `structural_errors()` blocks these at save (V007/V015) |
| 4 | Corrupt DOCX, DOCX without body, corrupt PDF → **500** | High | Parser exceptions not handled | Any parser failure → E015 |
| 5 | Sibling weights 1e308 accepted; sum overflows to ∞, so every score silently becomes 0 | High (silent wrong score) | No upper bound | `weight ≤ 1,000,000` |
| 6 | 2 MB purpose, 5 MB rationale, 5 MB input accepted | Medium | No size limits | Limits: names 200, texts 20k, input 400k |
| 7 | 5,000-parameter scorecard accepted | Medium | No volume limit | V020: 500 parameters max; depth hard cap 10 |
| 8 | Band colour `red`, RAG `BLUE` accepted | Low | Output schema reused for input | `BandIn` with hex pattern and RAG enum |
| 9 | Same parameter rated twice in one request: last one silently won | Medium (ambiguous data) | No duplicate check | E016 |
| — | Safety net | — | Any IntegrityError still reaching the API | Coded 409 E017 instead of 500 |

## 8.3–8.4 Migration: execution results
Reports per run: `docs/cycle2/migration/*.md`. Rules: `docs/cycle2/MIGRATION_RULES.md`.

| Source | Injected problems | Outcome |
|---|---|---|
| `code-review-quality.xlsx` (clean, 1–5, flat) | none: the control | 5/5 KPIs, 15/15 ratings, **15/15 totals reproduced** |
| `training-session-quality.xlsx` (0–10, hierarchy) | text target, no scale line, word/blank weights summing to 110, guideline gaps, duplicate guidelines, unknown column, summary rows, N/A, 7.5, 12, `good`, blank cell, missing evaluator, 31/02 date, exact + conflicting duplicates, re-run, no subject, no scores | 24 evaluations (21 completed, 3 draft), 5 rejected with reasons. 21 totals differ, all explained: the legacy formula did not normalise weights, so **the legacy totals understated quality by ~1.5–2 points** |
| `vendor-assessment.csv` + ratings CSV (%, `;`-delimited) | no codes, indentation hierarchy, no guidelines, new subject type, `Y`/`yes` critical flags | 6/6 ratings; codes generated; `vendor` subject type created; placeholders + `needs-guidelines` tag |
| `meeting-effectiveness-7pt.xlsx` (1–7) | scale not in the system; subject column called "Meeting" | Fatal M007 as designed. With `rescale_to=0-10-rag`: 8/8 imported, verdicts preserved, subject column inferred |
| `broken-no-header.xlsx`, `corrupt.xlsx` | not a scorecard / not a workbook | Fatal M002 / M001; commit refused (M900) |

### Migration defects found while executing (fixed)
| # | Found by | Defect | Fix |
|---|---|---|---|
| 10 | Vendor CSV run | CSVs without a code column: every KPI got the same empty code, so all ratings collided and every row looked "unrated" | Codes assigned before ratings are matched |
| 11 | Training run | Reconciliation blamed "hierarchy" for differences actually caused by the legacy formula | Reconciler tests candidate legacy formulas and names the match |
| 12 | Training run | Differences caused by refused cells (12, `good`) reported as unexplained | Explained explicitly |
| 13 | Vendor run | Unknown subject type silently became `task` | Created on commit (subject types are user-extendable) |
| 14 | 7-point run | Ratings sheet whose subject column is named "Meeting" → fatal | Subject column inferred from the data (M109) |
| 15 | Fuzzing | One-character file name → invalid scorecard code → uncaught ValidationError; over-long KPI codes likewise | Slug ≥ 2 chars, codes ≤ 30 chars, M008 safety net |
| 16 | UI smoke | Reconciliation table repeated one long explanation on every row | Explanations grouped and referenced |

## Schema and contract changes
| Change | Why |
|---|---|
| `evaluation.origin` (`app`/`import`), `evaluation.origin_ref` (`file!sheet:row`) | Traceability of migrated history (framework §8.2: "preserve traceability") |
| Input contracts: finite numbers only, size limits, weight bound, band format | Defects 1, 5, 6, 8 |
| New codes: V020, E016, E017, M-series | See data dictionary |

**Production impact / open risk:** there is no schema-migration tool for our *own* database yet. The pilot recreates
SQLite; before any shared deployment, add Alembic and a baseline revision. The `origin` columns are the first
change that needs it.

## Decisions for the team
1. **Legacy totals were wrong, not just different.** The training-feedback workbook used Σ(weight × score)/100 with
   weights that did not sum to 100, so every historic total understated the sessions. Communicate this before
   people compare old and new numbers.
2. **Placeholders vs blocking.** Importing ratings requires a publishable scorecard, so missing guidelines are
   filled with marked placeholders and tagged `needs-guidelines`. The alternative is to import the definition only.
   Confirm the default.
3. **Rescaling rule.** A legacy score maps to the lowest score of its band. That preserves pass/fail when mapping
   onto a finer scale, but not onto a coarser one (M110 warns). Confirm.
4. **Conflicting duplicates** are rejected outright. The alternative is to keep the later row. Rejecting is safer but
   needs someone to fix the source.
