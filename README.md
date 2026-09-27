# Scorecard Studio

A generic **Scorecard Creation & Rating System**: Google Forms / SurveyMonkey for scorecards.

- **Create** a scorecard for anything (tasks, projects, milestones, documents, assessments, teams, individuals,
  products, and any subject type you add): purpose, scope, objective, KPIs in a hierarchy of up to 4+ levels,
  weights, qualitative and quantitative rating matrix, metrics with thresholds, target, critical gates, QTC.
- **Use** it: provide text, a document or metric data, and rate it manually, as a private self-appraisal, or with
  an LLM judge. The deterministic engine rolls up weighted and minimum scores, applies bands (never rounding up),
  the target and critical gates, and QTC. It shows the reasoning behind every score.
- **Learn**: analytics on honest RAG distribution, weakest parameters, first-time pass rate and LLM-vs-human
  agreement.

*Assessment Quality* is the pilot scorecard. It is **data** (`data/scorecards/assessment-quality.json`), not
code, and it sits alongside five other scorecards for different subject types.

Built with the **Data-Driven Development Framework v1.1**. Start with [`docs/00_MASTER_PLAN.md`](docs/00_MASTER_PLAN.md).

| Doc | Framework step |
|---|---|
| [01 Initial Product Scope](docs/01_INITIAL_PRODUCT_SCOPE.md) | Initial Product Scope |
| [02 Database design](docs/02_DATABASE_DESIGN.md) · [schema.sql](docs/schema.sql) | Cycle 1 §7.1 |
| [03 Data dictionary](docs/03_DATA_DICTIONARY.md) | Cycle 1 §7.2 |
| [04 Scenario catalogue](docs/04_SCENARIO_CATALOGUE.md) | Cycle 1 §7.3 |
| [05 Scoring engine spec](docs/05_SCORING_ENGINE_SPEC.md) | Rating mechanism |
| [06 Analytics & BI](docs/06_ANALYTICS_BI.md) | Cycle 1 §7.5 |
| [07 Cycle 2 plan](docs/07_CYCLE2_PLAN.md) · [08 Cycle 3 plan](docs/08_CYCLE3_PLAN.md) | Next cycles |
| [Pilot log](docs/PILOT_LOG.md) | Pilot measures & learning |

## Run it

```bash
# backend
cd backend
pip install -r requirements.txt
python ../data/tools/ingest.py --reset      # load + publish the 6 reference scorecards
python ../data/tools/generate.py            # scenario-based evaluation data (optional)
uvicorn app.main:app --reload               # http://localhost:8000/docs

# frontend (dev)
cd ../frontend && npm install && npm run dev  # http://localhost:5173 (proxies /api)
# or build once and let FastAPI serve it at http://localhost:8000
npm run build
```

The LLM judge uses the Anthropic API (`ANTHROPIC_API_KEY`; model via `SCORECARD_JUDGE_MODEL`, default
`claude-opus-5`). Without credentials everything else works, and the judge endpoint returns a clear 503.
The database defaults to `backend/scorecard.db`; override with `SCORECARD_DB_URL`.

## Test

```bash
cd backend && python -m pytest -q          # 68 scenario-traced tests
cd frontend && npm run typecheck
```

## Layout
```
backend/app/scoring.py      pure scoring engine (roll-ups, metrics, bands, gates, QTC)
backend/app/validation.py   coded scorecard validation (V/W codes)
backend/app/services.py     definition <-> DB, evaluation lifecycle (E codes)
backend/app/judge.py        LLM judge (structured output; proposes leaf scores only)
backend/app/analytics.py    BI queries
data/scorecards/*.json      scorecard definitions (import/export format)
data/tools/                 ingest + scenario-based generator
frontend/src/pages/         Library, Builder, New evaluation, Evaluation, Evaluations, Analytics
```
