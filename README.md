# Scorecard Studio

A generic **Scorecard Creation & Rating System**: Google Forms / SurveyMonkey for scorecards, with a quality gate.

- **Create** a scorecard for anything: tasks, projects, milestones, documents, assessments, teams, individuals,
  products, and any subject type you add. It has a purpose, scope and objective; KPIs in a hierarchy (4 levels by
  default); relative weights; an anchored qualitative and quantitative rating matrix; metrics with thresholds;
  targets; critical gates; QTC; and optional two-person review. Versions are immutable once published.
  **AI Assist** in the builder drafts KPIs and their rating matrices from a short chat; you review the draft
  before anything is added (needs `GROQ_API_KEY`).
- **Rate** text, documents or metric data manually, as a private self-appraisal, or with an LLM judge that
  proposes scores for a human to confirm. A deterministic engine does all the maths and explains every score.
  Bands never round up.
- **Gate work**: projects → milestones → tasks go through self-appraisal → independent judges → decision, with
  adjudication when judges disagree, redo attempts, a stop rule for dark-red foundational work, and an honest
  roll-up (a project is green only when everything beneath it is green).
- **Learn**: RAG distribution, weakest parameters, first-time pass rate, LLM-vs-human agreement, guideline
  disputes, self-appraisal honesty, QTC misses; red diagnosis (skill, aptitude, will, allocation).
- **Import** legacy spreadsheet scorecards and their history, with a preview and reconciliation of old totals.

*Assessment Quality* is the pilot scorecard. It is **data** (`data/scorecards/assessment-quality.json`), alongside
five scorecards for other subject types on three rating scales.

Built with the **Data-Driven Development Framework v1.1**, Phase 1 complete:

| Step | Documents |
|---|---|
| Plan & Initial Product Scope | [00 Master plan](docs/00_MASTER_PLAN.md) · [01 Initial Product Scope](docs/01_INITIAL_PRODUCT_SCOPE.md) |
| Cycle 1: Data Foundation | [02 Database design](docs/02_DATABASE_DESIGN.md) · [schema.sql](docs/schema.sql) · [03 Data dictionary](docs/03_DATA_DICTIONARY.md) · [04 Scenario catalogue](docs/04_SCENARIO_CATALOGUE.md) · [05 Scoring engine](docs/05_SCORING_ENGINE_SPEC.md) · [06 Analytics](docs/06_ANALYTICS_BI.md) |
| Cycle 2: Test & Migration | [07 Plan](docs/07_CYCLE2_PLAN.md) · [09 Report](docs/09_CYCLE2_REPORT.md) · [Migration rules](docs/cycle2/MIGRATION_RULES.md) · [Corruption report](docs/cycle2/corruption_report.md) |
| Cycle 3: Behaviour, Specification & Testing | [08 Plan](docs/08_CYCLE3_PLAN.md) · [10 Behaviour spec](docs/10_CYCLE3_BEHAVIOUR_SPEC.md) · [11 Refined PRD](docs/11_REFINED_PRD.md) · [13 Report](docs/13_CYCLE3_REPORT.md) · [Acceptance scenarios](acceptance/) |
| Tuning & architecture | [Tuning report](docs/tuning/TUNING_REPORT.md) · [12 Architecture](docs/12_ARCHITECTURE.md) |
| Using it | [User guide](docs/USER_GUIDE.md) · [Pilot log](docs/PILOT_LOG.md) |

## Run it

```bash
# backend (Python 3.11+)
cd backend
pip install -r requirements.txt
python ../data/tools/ingest.py --reset          # load + publish the 6 reference scorecards
python ../data/tools/generate.py                # optional: scenario-based evaluation history
python ../data/tools/generate_flow.py           # optional: projects going through the quality gate
uvicorn app.main:app --reload                   # API docs at http://localhost:8000/docs

# frontend
cd ../frontend && npm install
npm run dev                                     # http://localhost:5173 (proxies /api), or:
npm run build                                   # then FastAPI serves the UI at http://localhost:8000
```

Shared deployment: `docker compose up` (app + Postgres 16; migrations run on start). Settings:
`SCORECARD_DB_URL`, `GROQ_API_KEY` (optional LLM judge; model `SCORECARD_JUDGE_MODEL`, default
`openai/gpt-oss-120b`), `RED_THRESHOLD`, `RED_WINDOW_DAYS`, `SCORECARD_AUTO_CREATE=0` in production.
Existing Cycle 1–2 pilot databases: `alembic stamp 0001_cycle2 && alembic upgrade head`.

> **Login required.** Every account is a real login (username + password, PBKDF2-hashed, bearer-token sessions).
> The first account ever registered on a fresh database becomes an admin automatically. See
> `docs/14_PHASE2_SECURITY_SPEC.md` for the identity, RBAC and data-governance model.

## Test

```bash
cd backend && python -m pytest -q      # 200+ tests: scenarios, engine properties, 76-case corruption catalogue,
                                       # migration + fuzzing, state x action matrix, 21 acceptance scenarios,
                                       # concurrency, Alembic upgrades, auth/RBAC
SCORECARD_TEST_DB_URL=postgresql+psycopg://user@host/db python -m pytest -q   # same suite on Postgres
cd ../frontend && npm run typecheck
BASE_URL=http://localhost:8000 npm run smoke                                 # browser smoke (running app)
python data/tools/perf.py --multiplier 20                                    # performance vs NFRs
python data/tools/migrate.py data/legacy/training-session-quality.xlsx      # legacy import preview
```

## Layout
```
backend/app/scoring.py         pure scoring engine (roll-ups, metrics, bands, gates, QTC)
backend/app/validation.py      coded scorecard validation
backend/app/services.py        scorecards, versions, evaluations (single write path)
backend/app/workflow.py        state-transition tables + audit trail
backend/app/services_flow.py   review, subjects, submissions/gate, roll-up, diagnosis
backend/app/judge.py           LLM judge (structured output; proposes leaf scores only)
backend/app/analytics.py       SQL analytics
backend/app/migration.py       legacy spreadsheet migration
backend/migrations/            Alembic revisions
acceptance/*.feature           business-readable acceptance scenarios
data/scorecards/*.json         scorecard definitions (the pilot is one of them)
data/tools/                    ingest, generators, corruption, legacy, migrate, perf, concurrency
frontend/src/pages/            Library, Builder, Work, Subject, Submission, Evaluate, Evaluations,
                               Analytics, Import
```
