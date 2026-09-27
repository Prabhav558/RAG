# Migration Rules — legacy spreadsheet scorecards (Cycle 2 · §8.3)

Implementation: `backend/app/migration.py` · CLI: `data/tools/migrate.py` · API: `POST /api/migrations/{preview,commit}`
· UI: **Import legacy** · Tests: `backend/tests/test_migration.py` · Sample sources: `data/legacy/` (built by
`data/tools/make_legacy.py`).

**Principles**
1. **Preview before commit.** `preview` never writes. `commit` re-plans from the same files and writes through the
   normal services, so imported data obeys every rule that user data obeys.
2. **Every source row ends in exactly one state**: *imported*, *warning* (imported, with a reason) or *rejected*
   (with a reason). Nothing is silently dropped.
3. **Never invent quality.** Unknown values stay unrated; fractional scores round **down**; conflicts are rejected,
   not guessed.
4. **Explain every difference.** Legacy totals are reconciled against the engine, and each difference is traced to
   a named cause.

## Source recognition
| Source element | Recognised as | Rule |
|---|---|---|
| Sheet | Definition sheet: name contains scorecard/kpi/parameter/definition/criteria, else the first sheet. Ratings sheet: name contains rating/score/result/evaluation, else the second sheet or the second CSV | |
| Lines above the header | Metadata `Key: value` or `Key \| value`: scorecard/name/title, purpose, scope, objective, scale, target, subject/applies to, owner | Unknown keys → warning |
| Header row | First row (of the first 50) with a column like KPI / Parameter / Criteria / Area / Metric | None → **fatal M002** |
| Columns | No/#/S.No/Code/ID · Weight/Weightage/Wt · Description/Definition · Critical/Mandatory/Gate · score-guideline columns: `10`, `Score 8-9`, `Rating 5`, `0-3` | Unrecognised columns → note M101 |
| Summary rows | Rows whose name starts with Total / Average / Overall / Sum / Mean | Skipped, recorded |
| End of table | Two consecutive blank rows | |

## Mapping rules
| Code | Source condition | Outcome |
|---|---|---|
| — | Dotted numbering `1`, `1.2`, `1.2.3` | Hierarchy from the numbering |
| — | No numbering | Hierarchy from Excel indent level, leading spaces (CSV, 2 per level) or bullets `-`/`•`/`>` |
| — | Missing / invalid / over-long codes | Generated from position (`2.1`); duplicates renamed `-r<row>` (M202) |
| M01 | Blank weight | 1, warning |
| M01 | Word weight `high/medium/low` | 3/2/1, warning |
| M01 | Weights not summing to 100 | Accepted: weights are relative to siblings |
| M201 | KPI row without a name | Row rejected |
| — | Guideline cells identical for adjacent scores | Merged into one range |
| M06 | Scores with no guideline | Placeholder row `[Migrated: …]`, scorecard tagged `needs-guidelines` (option `fill_missing_guidelines`, default on; required to publish and import ratings) |
| M105 | No `Scale:` line | Inferred from the guideline columns |
| M005 | Scale unknowable | **Fatal** |
| M007 | Scale not in the system (e.g. 1–7) | **Fatal**, unless `rescale_to` is given |
| M106 | `rescale_to` set | Each legacy score becomes the lowest score of its mapped band. The target maps linearly. Pass/fail is preserved when mapping onto a finer scale (tested) |
| M110 | Rescaling onto a coarser scale | Warning: verdicts near the target may change |
| M05 | Numeric target | Used (mapped when rescaled); outside scale → fatal |
| M05 | Word target | excellent 90%, very good 85%, good 80%, acceptable/satisfactory 70%, average/fair 50% of scale |
| M05 | Unknown word target | **Fatal** |
| M05 | No target | 80% of scale, note |
| M107 | Subject type missing | `task`, note. Unknown type → created on commit |
| M108 | Scorecard code exists | Suffix `-2`, `-3`, … |
| M008 | Anything that still violates the data contract | Fatal with the contract errors (safety net; never triggered in 8,000 fuzz runs) |

## Ratings rules
| Code | Source condition | Outcome |
|---|---|---|
| — | Subject column not named as expected | Header = first row naming two or more KPIs; subject = first mostly-text column (M109) |
| M102/M103/M104 | Column matches no KPI / matches a section / KPI has no column | Ignored / ignored (sections roll up) / noted |
| M301 | No subject | Row rejected |
| M02 | `N/A`, `NA`, `-`, `not applicable` | Not applicable; the KPI is marked **optional** |
| M303 | Non-numeric score (`good`) | Cell left unrated, warning |
| M304 | Score outside the legacy scale | Cell left unrated, warning |
| M305 | Fractional score | Rounded **down**, warning |
| M306 | No usable score at all | Row rejected |
| — | Any required KPI unrated | Imported as a **draft** evaluation for a human to finish |
| M03 | No evaluator | `legacy import`, warning. Comments → summary; missing rationale stays empty |
| M302 | Unparseable date (e.g. 31/02/2025) | Import date used, warning |
| M04 | Same subject + evaluator + date, identical scores | Later row rejected as a duplicate |
| M04 | Same subject + evaluator + date, different scores | **Both rejected**: resolve at source |
| M04 | Same subject + evaluator, different dates | Imported as attempts 1, 2, … in date order |
| M902 | Scorecard cannot be published | Scorecard saved as a draft; ratings rejected with a reason |

## Reconciliation
For each rating row with a legacy total, the importer recomputes the score with the real engine and compares
the two (±0.01). A mismatch is explained by testing the formulas spreadsheets commonly use:
Σ(score × weight% × parent weight% …) without normalisation, a flat weighted mean ignoring the hierarchy, a simple
average, or a plain sum. It also flags N/A renormalisation, fractional rounding, refused cells and rescaling. A
mismatch no rule explains is reported as **unexplained** and counted. The acceptance criterion is 0 unexplained.
