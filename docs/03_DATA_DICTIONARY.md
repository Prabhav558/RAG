# Data Dictionary (Cycle 1 · §7.2)

The contract used to generate, ingest and validate data. Types are logical; physical DDL is in `schema.sql`.
PK = primary key, FK = foreign key, U = unique, N = nullable. Validation codes refer to `backend/app/validation.py`
(V/W) and `backend/app/services.py` (E); migration codes (M) to `docs/cycle2/MIGRATION_RULES.md`.

## Contract-wide rules (Cycle 2)
- Numbers must be finite: NaN / ±Infinity are rejected (HTTP 422) everywhere.
- Size limits: names ≤ 200 chars; purpose, scope, objective, guidance, guidelines, rationale, evidence, notes
  ≤ 20,000; evaluation input ≤ 400,000; weight ≤ 1,000,000; ≤ 500 parameters per version (V020); depth hard cap 10.
- A request may not rate the same parameter, or value the same metric, twice (E016).
- Integrity violations that slip past validation return 409 E017, never 500.

| Code | Meaning |
|---|---|
| V001–V019, W101–W105 | Definition validation (see `04_SCENARIO_CATALOGUE.md`) |
| V020 | Too many parameters (> 500) |
| E001–E015 | Evaluation / lifecycle / upload errors |
| E016 | Duplicate parameter or metric in one request |
| E017 | Database integrity violation (safety net) |
| M001–M008, M101–M110, M201–M306, M900–M902 | Migration (`cycle2/MIGRATION_RULES.md`) |

## rating_scale
| Field | Type | N | Key | Rules |
|---|---|---|---|---|
| id | int | | PK | |
| code | varchar(40) | | U | Referenced by definitions (`rating_scale`). e.g. `0-10-rag`, `1-5-likert`, `0-100-pct` |
| name | varchar(120) | | | |
| min_value | int | | | Integer scale floor |
| max_value | int | | | `> min_value` (CHECK) |
| description | text | Y | | |

## rating_band
| Field | Type | N | Key | Rules |
|---|---|---|---|---|
| id | int | | PK | |
| scale_id | int | | FK→rating_scale | cascade |
| label | varchar(40) | | | Shown to users, e.g. "Light green" |
| lower_bound | float | | U(scale) | Band applies to scores ≥ lower_bound and < next band's bound. A band must start at the scale minimum (V013) |
| color_hex / font_hex | char(7) | | | `#RRGGBB`; fill and text colour |
| rag | varchar(5) | | | GREEN / AMBER / RED — used for roll-up RAG views |
| meaning | text | Y | | |

## subject_type
| Field | Type | N | Key | Rules |
|---|---|---|---|---|
| id | int | | PK | |
| code | varchar(40) | | U | `^[a-z0-9][a-z0-9_-]*$`. User-extendable; the engine never branches on it |
| name, description | text | (desc Y) | | |

## scorecard
| Field | Type | N | Key | Rules |
|---|---|---|---|---|
| id | int | | PK | |
| code | varchar(60) | | U | Slug `^[a-z0-9][a-z0-9-]*$`; duplicate → E011 |
| name | varchar(200) | | | |
| subject_type_id | int | | FK | Must exist (E008) |
| owner | varchar(120) | Y | | |
| tags | json array | | | |
| is_template | bool | | | Shown as reference scorecard in the library |
| created_at / archived_at | timestamptz | archived Y | | Archived scorecards are hidden from the library |

## scorecard_version
| Field | Type | N | Key | Rules |
|---|---|---|---|---|
| id | int | | PK | |
| scorecard_id | int | | FK | |
| version_no | int | | U(scorecard) | 1, 2, … |
| status | enum | | | `draft → published → retired`. Only drafts are editable (E009) or deletable. Publishing retires the previous published version. One draft at a time (E014) |
| purpose | text | | | Required to publish (V016) |
| scope | text | | | |
| objective | text | | | Assessment/quality objective. Required to publish (V016) |
| guidance | text | Y | | Scoring manual for judges; sent to the LLM judge |
| rating_scale_id | int | | FK | |
| target_score | float | | | Within scale (V012) |
| aggregation | enum | | | Root roll-up: `weighted_mean` \| `minimum` |
| max_depth | int | | | 1–6, default 4. Deeper parameters → V002 |
| qtc_enabled | bool | | | If true, completion requires time_met and cost_met (E007) |
| based_on_version_id | int | Y | FK→self | Lineage of new versions |
| change_note | text | Y | | |
| created_at / published_at / retired_at | timestamptz | Y | | |

## parameter
| Field | Type | N | Key | Rules |
|---|---|---|---|---|
| id | int | | PK | |
| version_id | int | | FK | |
| parent_id | int | Y | FK→self | Null = level 1 |
| code | varchar(40) | | U(version) | Unique within version, enforced at save (V015). Convention `1`, `1.2`, `1.2.3` |
| name | varchar(200) | | | |
| description | text | Y | | What exactly is judged |
| weight | float | | | ≥ 0 (schema + V004). Relative to siblings; siblings need Σ > 0 (V003) |
| sort_order | int | | | |
| aggregation | enum | | | For parents: `weighted_mean` \| `minimum` |
| is_critical | bool | | | Gate: final score below floor fails the evaluation regardless of total |
| min_acceptable_score | float | Y | | Gate floor; null = evaluation target. Within scale (V014) |
| is_optional | bool | | | Leaf may be marked N/A; weights renormalise. Optional+critical → W105 |

**Leaf** = parameter with no children. Only leaves carry criteria and metrics (metrics on parents → V017;
criteria on parents → W104, ignored).

## rating_criterion (the rating matrix)
| Field | Type | N | Rules |
|---|---|---|---|
| parameter_id | int | | FK (leaf) |
| score_min, score_max | int | | Inclusive range within scale (V007). Across a leaf's rows every integer score is covered exactly once (V005 gap / V006 overlap). < 6 rows → W102 |
| qualitative | text | | Required (V019). English anchor: what this score looks like |
| quantitative | text | Y | Measurable anchor: counts, %, thresholds |

## metric / metric_threshold
| Field | Type | N | Rules |
|---|---|---|---|
| metric.code | varchar(60) | | U(parameter) |
| metric.data_type | enum | | `percent` (0–100), `count` (integer ≥ 0), `number`, `boolean` (0/1). Values violating type → E013 |
| metric.unit, description | text | Y | |
| threshold.min_value | float | Y | Inclusive; null = −∞ |
| threshold.max_value | float | Y | Exclusive; null = +∞. `max > min` (V009) |
| threshold.score | float | | Within scale (V010). A metric needs ≥ 1 threshold (V011); thresholds must not overlap (V009); gaps → W103 |

## evaluation
| Field | Type | N | Rules |
|---|---|---|---|
| version_id | int | | FK. New evaluations only on `published` versions (E001) |
| subject_name | varchar(300) | | Required |
| subject_ref | varchar(120) | Y | External ID; links repeat and cross-judge evaluations of one subject |
| input_text | text | Y | Pasted content / notes / data |
| evaluator_type | enum | | `self` \| `human` \| `llm` |
| evaluator_name, judge_model | varchar | Y | judge_model set by the LLM judge |
| is_private | bool | | Default true for `self`. Private rows are excluded from lists (unless asked) and all analytics |
| status | enum | | `draft → completed`, or `→ void` (with reason). Completed/void are immutable (E006) |
| target_score | float | | Copied from version; overridable per context; within scale |
| time_met, cost_met | bool | Y | QTC inputs |
| attempt_no | int | | ≥ 1; resubmissions after a failed gate |
| origin | enum | | `app` \| `import` (Cycle 2). Imported evaluations come from legacy migration |
| origin_ref | varchar(300) | Y | Source trace, e.g. `training.xlsx!Feedback log:17` |
| final_score, band_label, rag, quality_met, qtc_green, gate_failures | computed | Y | Written only by the scoring engine on every change |
| summary, notes, voided_reason | text | Y | |

## parameter_result
| Field | Type | N | Rules |
|---|---|---|---|
| evaluation_id, parameter_id | int | | U(pair). One row per parameter, created with the evaluation |
| is_leaf | bool | | |
| judged_score | float | Y | Leaves only (E003). Whole number (E012) within scale (E002) |
| computed_score | float | Y | From metric thresholds (min across the leaf's metrics) |
| final_score | float | Y | override › metric › judged; roll-up for parents; rounded to 2 dp |
| score_source | enum | | judged, metric, override, rollup, not_applicable, pending |
| not_applicable | bool | | Only for optional leaves (E004) |
| rationale, evidence | text | Y | Why; which part of the input |
| confidence | float | Y | 0–1 (LLM judge) |
| override_reason | text | Y | Required to override a metric score; needs a judged score (E010) |
| effective_weight | float | Y | Share of the final score (0–1) after N/A renormalisation |
| band_label | varchar | Y | |

## metric_value
| Field | Type | N | Rules |
|---|---|---|---|
| evaluation_id, metric_id | int | | U(pair); metric must belong to the evaluation's version (E008) |
| value | float | | Type-checked (E013). Sending `null` deletes the value |
| source | enum | | manual \| llm \| import |

## evaluation_document
| Field | Type | Rules |
|---|---|---|
| filename, media_type | text | txt, md, csv, json, docx, pdf. ≤ 20 MB upload, ≤ 400k extracted chars (E015) |
| content_text | text | Extracted text passed to the LLM judge |
