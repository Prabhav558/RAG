# Migration report — meeting-effectiveness-7pt.xlsx

**Status:** ok · **committed:** True · scorecard id 10 / version 10
**Legacy scale:** 1–7 → **0-10-rag**

## Notes
- [M106] Legacy 1–7 scores mapped onto 0–10 Quality Scale (RAG): each legacy score becomes the lowest score of its mapped band
- [M109] Subject column not named as expected; using 'Meeting' (the first text column next to the KPI columns)

## Row outcomes

| Kind / status | Rows |
|---|---|
| kpi_imported | 4 |
| meta_imported | 4 |
| rating_imported | 8 |

## Migrated definition
`meeting-effectiveness` · Meeting Effectiveness · subject `meeting` · target 6.67 · tags legacy-import

- `1` Agenda shared in advance (w 1, 7 matrix rows)
- `2` Decisions recorded (w 2, 7 matrix rows)
- `3` Actions with owners (w 2, 7 matrix rows)
- `4` Timekeeping (w 1, 7 matrix rows)

## Reconciliation (legacy total vs recomputed)
0 rows with a legacy total · 0 match (±0.01) · 0 differ (0 unexplained) · max |diff| 0

| Row | Subject | Import as | Legacy total | Recomputed | Diff | Explanation |
|---|---|---|---|---|---|---|
| 2 | Weekly sync 1 | completed | — | 6.33 | — |  |
| 3 | Weekly sync 2 | completed | — | 8.33 | — |  |
| 4 | Weekly sync 3 | completed | — | 5.83 | — |  |
| 5 | Weekly sync 4 | completed | — | 7.33 | — |  |
| 6 | Weekly sync 5 | completed | — | 6.83 | — |  |
| 7 | Weekly sync 6 | completed | — | 5.33 | — |  |
| 8 | Weekly sync 7 | completed | — | 6.33 | — |  |
| 9 | Weekly sync 8 | completed | — | 7.83 | — |  |
