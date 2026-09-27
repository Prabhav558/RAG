# Cycle 3 — Business Behaviour Specification (§9.1–9.3)

Complex behaviour made explicit. Implementation: `backend/app/workflow.py` (transition tables and guards) and
`backend/app/services_flow.py`. Tests: `tests/test_workflow.py` (the exhaustive state × action matrix) and
`acceptance/*.feature`.

## Actors
No authentication in Phase 1 (framework §3). Every workflow action carries an **actor name** (HTTP header
`X-Actor`, or "Acting as" in the UI). Guards use it for separation of duties; Phase 2 swaps it for real identity.

| Actor | Does |
|---|---|
| Designer | authors a scorecard; submits it for review |
| Reviewer | approves or returns a scorecard version (must not be its designer) |
| Owner | owns a subject; self-appraises, submits, resubmits |
| Judge | human or LLM; evaluates a submission (must not be its owner) |
| Adjudicator | settles judge disagreement (must be neither the owner nor one of its judges) |
| Lead | records red diagnoses; cancels work |

## 1. Scorecard version lifecycle
```
            submit_for_review [no errors]          approve [actor ≠ submitter, no errors]
   draft ─────────────────────────────▶ in_review ───────────────────────────────▶ published
     ▲ │                                   │                                           │
     │ └── publish [scorecard does not     │ request_changes [comment]                  │ retire [reason]
     │     require review, no errors] ─────┼──────────────────────────────▶ draft      ▼
     └──────────────────────────────────────┘                                        retired
```
- Publishing (either way) retires the previously published version automatically.
- Only `draft` is editable or deletable. `in_review` is frozen so the reviewer sees what will ship.
- Every action writes a `version_review` record and an audit event.

## 2. Subjects and hierarchy
A **subject** is the thing being scored, of any subject type (task, milestone, project, team, document, …).
Subjects form a tree (`parent_id`, depth ≤ 6, no cycles: S008). Type order is **not** enforced: the system is generic.
A subject carries the agreed **due date** and **budget** used by the QTC rule.

## 3. Submission lifecycle (the quality gate)
A submission is one attempt at getting a subject through a published scorecard version.
```
                 submit [owner; self-appraisal done if required]       decide [≥ N judge evaluations completed]
      open ──────────────────────────────────────▶ in_review ─────────────────────┬──▶ decided (passed | redo)
       │  ▲                                          │                             │
       │  └── (self-appraisal allowed here)          │  judges disagree ──────────▶ adjudication
       │                                             │                              │ adjudicate [actor ∉ owner ∪ judges, reason]
       │ withdraw [owner]                            │ cancel [reason]               ▼
       ▼                                             ▼                            decided
   withdrawn                                     cancelled
   decided(redo) ── resubmit [owner] ──▶ new submission, attempt + 1, state open
```
**Evaluations inside a submission**
- Self-appraisal (`evaluator_type=self`): only while `open`. Always private.
- Judge evaluations (`human`/`llm`): only while `in_review`. A human judge's name must differ from the owner's (S003).
- Once a submission is terminal, none of its evaluations can be created or completed (S009).

**Decide** (computed, never typed in)
1. Judges = completed, non-void judge evaluations. Fewer than the version's `required_judges` → S004.
2. Official score = mean of the judges' final scores. Gate failures = union of the judges' failures.
3. The judges **disagree** when their pass/fail verdicts differ, or when the spread of their scores exceeds the
   version's `judge_tolerance_pct` of the scale. Disagreement → `adjudication`, which is also logged as a guideline
   dispute.
4. Otherwise: all pass → `passed`; all fail → `redo`.
5. QTC (if the version applies it): Time = submitted before the subject's due date; Cost = cumulative actual cost
   of all attempts ≤ budget. Missing due date, budget or actual cost → S006. `qtc_green = passed ∧ T ∧ C`.

**Adjudicate**: the adjudicator records the verdict (`passed`/`redo`) and a reason. The official score stays the
judges' mean. This is the audit trail of every disputed judgement.

## 4. Stop rule for foundational work
A version flagged `is_foundational` whose submission ends `redo` in a **RED** band blocks its subject. While it is
blocked, no new submission may start anywhere else in the same root project (S007): "nothing downstream should
start". The blocked subject itself can still be resubmitted, and a passing decision lifts the block.

## 5. Roll-up (derived, never stored)
Each subject's own status comes from its latest **decided** submission; an open attempt shows as `in_progress`.

| Own status | Meaning |
|---|---|
| `not_started` | no submission |
| `in_progress` | a submission is open, in review or in adjudication, and there is no decision yet |
| `green` | latest decision passed (and QTC green where applied) |
| `red` | latest decision redo, or passed but QTC not green |
| `blocked` | foundational red (stop rule) |

Rolled-up status = the worst of the subject's own status and its children's rolled-up statuses, in the order
blocked › red › in_progress › not_started › green. A subject with no evaluation of its own takes its children's
status. **A project is green only when everything beneath it is green.**

## 6. Red diagnosis (framework §12)
- A *red* is a submission decided `redo`. An owner with ≥ `RED_THRESHOLD` (default 3) reds in the last 90 days,
  and no diagnosis recorded since the latest red, appears on the **attention list**.
- A lead records a diagnosis: cause `skill | aptitude | will | allocation`, action
  `train | reassign | discuss | rescope | none`, and notes. That clears the person from the list until the next red.
- The threshold is a policy parameter (the framework marks "three reds" as proposed and subject to HR policy).

## 7. Exceptions and alternate flows (§9.3)
| Situation | Behaviour |
|---|---|
| LLM judge unavailable / refuses | 503/502 J001; a human judge proceeds (no state change) |
| Judges disagree | `adjudication` (never averaged away silently) |
| Owner judges own work | S003 |
| Reviewer approves own scorecard | S003 |
| Scorecard retired while a submission is open | Allowed: the submission keeps its version (reproducibility) |
| Subject withdrawn by owner | `withdrawn` (terminal); a new submission can be started later |
| Work cancelled by a lead | `cancelled` with reason |
| Target missed on time/cost only | `passed` on quality, but `qtc_green = false`; roll-up shows red |
| Redo | New attempt; previous attempts and their evaluations stay as history |

## 8. Error codes
| Code | Meaning |
|---|---|
| S001 | Action not allowed in the current state (response lists the allowed actions) |
| S002 | Actor required |
| S003 | Separation of duties violated |
| S004 | Not enough completed judge evaluations |
| S005 | Self-appraisal required before submitting |
| S006 | QTC inputs missing (due date, budget or actual cost) |
| S007 | Project blocked by a foundational red |
| S008 | Invalid subject hierarchy (cycle or depth > 6) |
| S009 | Submission is not accepting this evaluation |
| S010 | Version not usable (not published) for a new submission |
