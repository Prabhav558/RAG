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
  Or let **AI draft a scorecard from any spreadsheet**, even one with vague KPIs and no guidelines: it keeps your KPIs,
  makes them judgeable, writes the rating matrices and lists what it assumed, for you to review before it is saved.

*Assessment Quality* is the pilot scorecard. It is **data** (`data/scorecards/assessment-quality.json`), alongside
five scorecards for other subject types on three rating scales.

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
> The first account ever registered on a fresh database becomes an admin automatically. Admins grant the Designer,
> Reviewer, Lead and Importer roles from **Users & roles**.

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
