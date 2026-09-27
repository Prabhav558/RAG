# Cycle 3 — Business Behaviour, Specification & Testing: Summary

Cycle 3 made complex behaviour explicit, produced the refined PRD, and put a verification net around the
application. It was followed by application tuning.

| Framework step | Deliverable |
|---|---|
| 9.1 Complex workflows | Scorecard review; subjects tree; submission gate with self-appraisal, independent judges, adjudication, redo; foundational stop rule; red diagnosis. Spec: `10_CYCLE3_BEHAVIOUR_SPEC.md` |
| 9.2 Rules & state transitions | `workflow.py` transition tables; guards S001–S012; audit trail for every transition |
| 9.3 Exceptions & alternate flows | Spec §7: judge unavailable, disagreement, self-judging, retired version mid-flight, withdrawal, cancellation, QTC-only misses, redo |
| 9.4 Refined PRD | `11_REFINED_PRD.md`: every requirement mapped to a test or acceptance scenario |
| 9.5 Acceptance suite | `/acceptance/*.feature`: 21 business-readable scenarios, runner in `tests/test_acceptance.py`, sign-off sheet `acceptance/ACCEPTANCE_RESULTS.md` |
| 9.6 Comprehensive suite | 158 automated tests (scenario, property, corruption, migration, workflow matrix, acceptance, concurrency, Alembic) on SQLite and Postgres + an 8-step browser smoke suite |
| §10 Tuning | `tuning/TUNING_REPORT.md` |

## Defects found in Cycle 3 (all fixed, each with a regression test)
| # | Found by | Defect |
|---|---|---|
| 17 | Property tests | A scored zero-weight parameter produced a provisional score on behalf of its weighted siblings |
| 18 | Workflow tests | Judges inside QTC submissions were asked for time/cost, which are facts of the submission |
| 19 | Project simulation | Evaluations added to a submission were invisible to later calls in the same session |
| 20 | UI review (screenshot) | Private self-appraisal scores were visible to judges, breaking privacy and anchoring judges |
| 21 | Follow-on review | Anyone could edit another person's self-appraisal or judgement |
| 22 | UI review | "Passed" shown next to "Critical gate failed" after adjudication, without explanation |
| 23 | Concurrency test | 8 simultaneous "decide" calls recorded 8 decisions (also on SQLite, contrary to my first assumption) |
| 24 | Tuning measurement | Analytics cost grew with object count; parameter breakdown already over target at 3k evaluations |
| 25 | Tuning measurement | Pilot databases created before migrations could not be upgraded by a latest-schema baseline |

## What the simulated projects showed
`ingest.py → generate.py → generate_flow.py` is deterministic (verified by two identical runs). It drives three
projects through the real gate: **24 submissions, 19 decided: 5 passed, 14 redo, 1 adjudicated, 1 foundational
stop** (Zeus Analytics is blocked). The adjudication and the stop are deterministic showcase cases. The high redo
rate comes from the target-10 requirements scorecard and the one-error gate on assessments: configuration
questions for the business (PRD §6), not defects. The attention list surfaces the simulated allocation problems
(Eve: 6 reds, Chen: 5).

Earlier in the cycle, before the showcases existed, a random run produced 2 adjudications and 2 stops, and after
later changes a run produced none. That instability is why the showcases were added: a demo dataset that
sometimes does not demonstrate the key behaviours is a defect in the dataset.
