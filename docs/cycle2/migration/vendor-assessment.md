# Migration report — vendor-assessment.csv

**Status:** ok_with_warnings · **committed:** True · scorecard id 9 / version 9
**Legacy scale:** 0–100 → **0-100-pct**

## Notes
- [M107] Subject type 'Vendor' does not exist; it will be created as 'vendor'

## Row outcomes

| Kind / status | Rows |
|---|---|
| kpi_imported | 3 |
| kpi_warning | 6 |
| meta_imported | 4 |
| rating_imported | 6 |

## Migrated definition
`vendor-assessment` · Vendor Assessment · subject `vendor` · target 75.0 · tags legacy-import, needs-guidelines

- `1` Commercials (w 30)
  - `1.1` Pricing competitiveness (w 60, 1 matrix rows)
  - `1.2` Payment terms (w 40, 1 matrix rows)
- `2` Delivery (w 40)
  - `2.1` On-time delivery (w 70, critical, 1 matrix rows)
  - `2.2` Quality of goods (w 30, critical, 1 matrix rows)
- `3` Compliance (w 30)
  - `3.1` ISO certification (w 50, 1 matrix rows)
  - `3.2` Data protection (w 50, critical, 1 matrix rows)

## Validation of the migrated definition
- [W102] warning: /1/1.1 Only 1 rating-matrix rows; coarse anchors reduce consistency
- [W102] warning: /1/1.2 Only 1 rating-matrix rows; coarse anchors reduce consistency
- [W102] warning: /2/2.1 Only 1 rating-matrix rows; coarse anchors reduce consistency
- [W102] warning: /2/2.2 Only 1 rating-matrix rows; coarse anchors reduce consistency
- [W102] warning: /3/3.1 Only 1 rating-matrix rows; coarse anchors reduce consistency
- [W102] warning: /3/3.2 Only 1 rating-matrix rows; coarse anchors reduce consistency

## Rows with warnings or rejections

| Sheet | Row | Kind | Item | Status | Messages |
|---|---|---|---|---|---|
| vendor-assessment.csv | 8 | kpi | Pricing competitiveness | warning | [M06] No source guideline for scores 0-100; placeholder added |
| vendor-assessment.csv | 9 | kpi | Payment terms | warning | [M06] No source guideline for scores 0-100; placeholder added |
| vendor-assessment.csv | 11 | kpi | On-time delivery | warning | [M06] No source guideline for scores 0-100; placeholder added |
| vendor-assessment.csv | 12 | kpi | Quality of goods | warning | [M06] No source guideline for scores 0-100; placeholder added |
| vendor-assessment.csv | 14 | kpi | ISO certification | warning | [M06] No source guideline for scores 0-100; placeholder added |
| vendor-assessment.csv | 15 | kpi | Data protection | warning | [M06] No source guideline for scores 0-100; placeholder added |

## Reconciliation (legacy total vs recomputed)
0 rows with a legacy total · 0 match (±0.01) · 0 differ (0 unexplained) · max |diff| 0

| Row | Subject | Import as | Legacy total | Recomputed | Diff | Explanation |
|---|---|---|---|---|---|---|
| 2 | Acme Supplies | completed | — | 75.38 | — |  |
| 3 | Globex | completed | — | 70.52 | — |  |
| 4 | Initech | completed | — | 76.86 | — |  |
| 5 | Umbrella Corp | completed | — | 76.62 | — |  |
| 6 | Hooli | completed | — | 75.04 | — |  |
| 7 | Stark Industries | completed | — | 76.29 | — |  |
