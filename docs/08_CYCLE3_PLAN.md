# Cycle 3 — Business Behaviour, Specification & Testing (plan)

Goal: make complex behaviour explicit, produce the refined PRD and an acceptance suite (DDD framework §9).

## 9.1 Workflows to model
1. **Evaluation workflow**: self-appraisal (private) → submission → judge (LLM first, human second) → gate →
   *redo* loop or proceed. Today these are independent evaluations linked by `subject_ref` + `attempt_no`; Cycle 3
   makes the chain a first-class `submission` entity.
2. **Scorecard governance**: draft → review (second designer) → publish; change requests on published versions.
3. **Roll-up across subjects**: task evaluations → milestone → project ("a project cannot be green if the items
   beneath it are red"). Needs a `subject` table with hierarchy and a roll-up policy per level.
4. **Multi-judge / parallel validation**: N judges score independently; disagreement beyond tolerance triggers
   adjudication (framework §14.1 audit stage 3).
5. **Red diagnosis**: on repeated reds, classify skill / aptitude / will and record the action (framework §12).

## 9.2 State transitions (current, to be formalised)
```
ScorecardVersion: draft --publish[no errors]--> published --publish(newer)--> retired
                  draft --delete--> ∅
Evaluation:       draft --complete[all required leaves, QTC inputs]--> completed
                  draft|completed --void[reason]--> void
```
To add: `submitted`, `under_review`, `redo_requested`, `accepted` with actor permissions.

## 9.3 Exceptions & alternate flows
Judge unavailable (LLM 503 → human path, already handled) · judge refuses/timeouts · conflicting judges ·
scorecard retired while evaluation in draft (allowed today; decide policy) · target changed mid-evaluation ·
subject withdrawn.

## 9.4 Refined PRD
Assemble from: Initial Product Scope + data model + scenario catalogue + Cycle 2 learning + the workflows above.

## 9.5 Acceptance suite (business-readable, sample)
```
Given the published "Assessment Quality" scorecard with target 8
And a quiz whose items contain 1 factual error
When a judge rates every other parameter 8
Then the final score is below 8, the band is Grey
And the evaluation fails the "Technical correctness" gate
And it cannot move to the next phase
```

## 9.6 Comprehensive suite
Functional, integration, data, migration, smoke, NFR (2,400 evaluations/day ≈ 0.03 rps average; target p95 < 300 ms
for rating updates, LLM judge p95 < 90 s), optimised for risk and scenario coverage.
