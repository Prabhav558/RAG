# Migration report — training-session-quality.xlsx

**Status:** ok_with_warnings · **committed:** True · scorecard id 8 / version 8
**Legacy scale:** 0–10 → **0-10-rag**

## Notes
- [M101] Column 'Owner notes' in 'KPIs' was not recognised and is ignored
- [M105] Scale not stated; inferred 0–10 from the guideline columns
- [M05] Text target 'good' mapped to 8
- [M107] The source does not say what it scores; subject type defaulted to 'task'

## Row outcomes

| Kind / status | Rows |
|---|---|
| kpi_imported | 3 |
| kpi_warning | 6 |
| meta_imported | 5 |
| meta_warning | 1 |
| rating_imported | 16 |
| rating_rejected | 5 |
| rating_warning | 8 |

## Migrated definition
`training-session-quality` · Training Session Quality · subject `task` · target 8.0 · tags legacy-import, needs-guidelines

- `1` Content (w 40)
  - `1.1` Relevance to role (w 60, 5 matrix rows)
  - `1.2` Accuracy (w 3, 5 matrix rows)
- `2` Delivery (w 50)
  - `2.1` Clarity (w 40, 6 matrix rows)
  - `2.2` Engagement (w 1, 6 matrix rows)
  - `2.3` Pace (w 20, 5 matrix rows)
- `3` Logistics (w 20)
  - `3.1` Venue & equipment (w 100, optional, 5 matrix rows)

## Validation of the migrated definition
- [W102] warning: /1/1.1 Only 5 rating-matrix rows; coarse anchors reduce consistency
- [W102] warning: /1/1.2 Only 5 rating-matrix rows; coarse anchors reduce consistency
- [W102] warning: /2/2.3 Only 5 rating-matrix rows; coarse anchors reduce consistency
- [W102] warning: /3/3.1 Only 5 rating-matrix rows; coarse anchors reduce consistency

## Rows with warnings or rejections

| Sheet | Row | Kind | Item | Status | Messages |
|---|---|---|---|---|---|
| KPIs | 5 | meta | last updated | warning | Unrecognised metadata 'last updated' ignored |
| KPIs | 9 | kpi | Relevance to role | warning | Identical adjacent guidelines merged into ranges |
| KPIs | 10 | kpi | Accuracy | warning | [M01] Weight 'high' mapped to 3 (high=3, medium=2, low=1)<br>Identical adjacent guidelines merged into ranges |
| KPIs | 12 | kpi | Clarity | warning | [M06] No source guideline for scores 4-5; placeholder added |
| KPIs | 13 | kpi | Engagement | warning | [M01] Blank weight; defaulted to 1 |
| KPIs | 14 | kpi | Pace | warning | Identical adjacent guidelines merged into ranges |
| KPIs | 16 | kpi | Venue & equipment | warning | [M02] Rated N/A in the history; marked optional<br>Identical adjacent guidelines merged into ranges |
| KPIs | 18 | meta | Total | imported | Summary row skipped |
| Feedback log | 17 | rating | Workshop: SQL | warning | [M305] 'Pace': 7.5 rounded down to 7 (scores are whole numbers; never rounded up) |
| Feedback log | 18 | rating | Workshop: Cloud | warning | [M304] 'Clarity': 12 is outside the 0–10 scale; left unrated<br>Incomplete (2.1 unrated): imported as a draft evaluation |
| Feedback log | 19 | rating | Workshop: Testing | warning | [M303] 'Engagement': 'good' is not a score; left unrated<br>Incomplete (2.2 unrated): imported as a draft evaluation |
| Feedback log | 20 | rating | Workshop: Docker | warning | Incomplete (1.2 unrated): imported as a draft evaluation |
| Feedback log | 21 | rating | Workshop: APIs | warning | [M03] No evaluator recorded |
| Feedback log | 22 | rating | Workshop: Security | warning | [M302] Date '31/02/2025' not understood; import date used |
| Feedback log | 24 | rating | Workshop: Python | rejected | [M04] Exact duplicate of row 23; skipped |
| Feedback log | 25 | rating | Workshop: Agile | rejected | [M04] Conflicting scores for the same subject, evaluator and date (rows 25 and 26); neither imported — resolve at source |
| Feedback log | 26 | rating | Workshop: Agile | rejected | [M04] Conflicting scores for the same subject, evaluator and date (rows 25 and 26); neither imported — resolve at source |
| Feedback log | 27 | rating | Workshop: Kafka | warning | [M04] Repeat rating of the same subject by the same evaluator: imported as attempt 1 |
| Feedback log | 28 | rating | Workshop: Kafka | warning | [M04] Repeat rating of the same subject by the same evaluator: imported as attempt 2 |
| Feedback log | 29 | rating |  | rejected | [M301] Rating row has no subject |
| Feedback log | 30 | rating | Workshop: Linux | rejected | [M306] Row has no usable scores |
| Feedback log | 32 | meta | Average | imported | Summary row skipped |

## Reconciliation (legacy total vs recomputed)
21 rows with a legacy total · 0 match (±0.01) · 21 differ (0 unexplained) · max |diff| 2.05

| Row | Subject | Import as | Legacy total | Recomputed | Diff | Explanation |
|---|---|---|---|---|---|---|
| 2 | Onboarding batch 1 | completed | 5.45 | 7.09 | 1.64 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 3 | Onboarding batch 2 | completed | 5.97 | 7.9 | 1.93 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 4 | Onboarding batch 3 | completed | 5.43 | 7.27 | 1.84 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 5 | Onboarding batch 4 | completed | 5.38 | 6.91 | 1.53 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 6 | Onboarding batch 5 | completed | 5.39 | 6.91 | 1.52 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 7 | Onboarding batch 6 | completed | 6.5 | 8.53 | 2.03 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 8 | Onboarding batch 7 | completed | 6.28 | 8.33 | 2.05 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 9 | Onboarding batch 8 | completed | 5.04 | 6.75 | 1.71 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 10 | Onboarding batch 9 | completed | 5.26 | 6.72 | 1.46 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 11 | Onboarding batch 10 | completed | 4.99 | 6.8 | 1.81 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 12 | Onboarding batch 11 | completed | 5.75 | 7.53 | 1.78 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 13 | Onboarding batch 12 | completed | 6.23 | 8.24 | 2.01 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 14 | Onboarding batch 13 | completed | 5.14 | 6.78 | 1.64 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 15 | Onboarding batch 14 | completed | 5.93 | 7.96 | 2.03 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 16 | Workshop: Git | completed | — | 8.0 | — |  |
| 17 | Workshop: SQL | completed | 6.01 | 7.85 | 1.84 | fractional legacy scores rounded down |
| 18 | Workshop: Cloud | draft | 6.86 | 8.0 | 1.14 | the legacy total includes a score that was refused on import (not a number or outside the scale) |
| 19 | Workshop: Testing | draft | — | 8.0 | — |  |
| 20 | Workshop: Docker | draft | — | 8.0 | — |  |
| 21 | Workshop: APIs | completed | 6.06 | 8.0 | 1.94 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 22 | Workshop: Security | completed | 6.06 | 8.0 | 1.94 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 23 | Workshop: Python | completed | 6.06 | 8.0 | 1.94 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 27 | Workshop: Kafka | completed | 5.46 | 7.11 | 1.65 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
| 28 | Workshop: Kafka | completed | 6.06 | 8.0 | 1.94 | legacy total matches 'Σ(score × weight% × parent weight% …), no normalisation'; the system uses normalised weighted means, so the legacy totals were not comparable on the scale |
