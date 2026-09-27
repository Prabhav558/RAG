# Application Tuning & Production Readiness (framework §10)

Tuning is the last-mile work that makes the real application meet the agreed suites and the non-functional
expectations. Everything here was measured, changed, and re-measured. Raw numbers: `perf_results.json`
(`python data/tools/perf.py`).

## Non-functional targets
| NFR | Target | Result |
|---|---|---|
| Volume | ~2,400 evaluations/day (framework §2) | One worker completes a full evaluation (create → rate all → complete) in 89 ms (SQLite) / 111 ms (Postgres): **~780k–970k/day**. 16 concurrent writers: 11.7/s (SQLite), 14.4/s (Postgres), **0 errors** |
| Page loads / rating updates | p95 < 300 ms at pilot volume | **All 13 measured endpoints ≤ 140 ms p95** at ~14–16k evaluations on both databases |
| Correctness under concurrency | a workflow action happens once | Proven: 8 simultaneous `decide` calls → exactly 1 succeeds (was 8 before the fix) |
| Portability | Postgres for shared deployment | Full suite (158 tests) green on SQLite **and** Postgres 16 |
| Schema evolution | upgrade existing databases in place | Alembic: empty → head equals the models; a real Cycle 2 pilot DB with data upgrades in place (tested on both databases) |
| LLM judge | p95 < 90 s | **Not measured**: no API key in the build environment. The judge is optional and failures degrade to a human judge (J001) |

## What was measured and changed

### 1. Analytics scaled with object count, not rows (fixed)
Measured at 3,282 evaluations: `analytics/parameters` p95 337 ms (**over target**). Overview, trend and judge agreement
materialised every evaluation as an ORM object and aggregated in Python: linear growth, seconds within a month
at framework volume.

**Change:** SQL `GROUP BY` for overview and the per-parameter breakdown; lean column projections for trend and
agreement (agreement only reads subjects that actually have an LLM evaluation); indexes on the filter columns
(`evaluation(version_id,status)`, `(status,is_private)`, `subject_ref`, `submission_id`; `submission(status)`,
`(decision,owner)`; `parameter(version_id)`, `(parent_id)`; `subject(parent_id)`). "Has a gate failure" was in a JSON
column that Postgres cannot compare, so a maintained `gate_failure_count` column replaces it for aggregation.

**Proof of equivalence:** old and new implementations ran side by side on the same 15,943-evaluation database and
produced **identical output** for every endpoint and every scorecard version.

| At 15,943 evaluations | Before | After |
|---|---|---|
| overview | 615 ms | 64 ms |
| parameter breakdown | 1,123 ms | 57 ms |
| judge agreement | 379 ms | 94 ms |
| trend | 414 ms | 102 ms |

### 2. Race condition in workflow actions (fixed)
With 8 threads calling `decide` on one submission at the same instant, **all 8 succeeded** and 8 decisions were
recorded. Every request read `in_review` before any of them wrote.

**Change:** two layers. (a) Optimistic concurrency: `row_version` columns on `submission`, `scorecard_version` and
`evaluation` (SQLAlchemy `version_id_col`), so a concurrent loser's UPDATE matches no row. It gets
**409 S012 "changed by someone else, reload"** on any database. (b) `SELECT … FOR UPDATE` on mutating workflow
actions, so on Postgres losers wait and then see the precise S001. The test first proved the race with the lock
disabled, then proved exactly-once with it enabled.

### 3. Schema migrations (added)
`backend/migrations` (Alembic): `0001_cycle2` is the frozen Cycle 2 schema (generated from the Cycle 2 models in git,
kept in `migrations/cycle2_models`); `0002_cycle3` adds the Cycle 3 tables and columns with **server defaults for
existing rows**, backfills `gate_failure_count` from the JSON, and rewrites the CHECK constraints that autogenerate
cannot detect. Pilot databases created before Alembic: `alembic stamp 0001_cycle2 && alembic upgrade head`.
Production startup sets `SCORECARD_AUTO_CREATE=0`, so only migrations change the schema.

### 4. Packaging (added, partially verified)
`Dockerfile` (builds the frontend, serves API + UI, runs `alembic upgrade head` on start, non-root user, healthcheck),
`docker-compose.yml` (app + Postgres 16), `.github/workflows/ci.yml` (tests on SQLite and Postgres, frontend build,
browser smoke suite). **The image was not built here: the environment has no Docker daemon.** Its startup sequence
was reproduced by hand on a fresh Postgres database (migrate → serve → seed → ingest → UI served) and works.

## Capacity guidance
Two workers on one small VM with Postgres cover the framework's 300 people × 8 tasks/day with more than two orders
of magnitude of headroom. The first thing to tune at larger scale is the LLM judge (latency and cost per
evaluation), not the application.
