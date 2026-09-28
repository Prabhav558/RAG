# User Guide

**Log in** (or **Register** the first time). Every action is recorded under your account, and the rules depend
on who you are: owners can't judge their own work, and reviewers can't approve their own scorecards. The very
first account ever created on a fresh system becomes an admin automatically — see **Admins**, below, for what
that means. Everyone else starts as a plain member and can already do everything under *Owners*, *Judges* and
*Adjudicators*; an admin grants the *Designer*, *Reviewer*, *Lead* and *Importer* roles as needed.

## Designers: build a scorecard
1. **Scorecard library → + New scorecard.** Name it, choose what it scores (or add a new subject type), a rating
   scale and a target.
2. **1. Purpose & scope.** Say *why* it exists (one or two sentences), what is in and out of scope, and what
   "good enough" means. Set how submissions are judged: number of judges, disagreement tolerance, whether
   self-appraisal is required, and whether a dark-red result should stop the whole project.
3. **2. Parameters & rating matrix.** Add 5–6 top-level KPIs and break them down where it helps judging (up to 4
   levels by default). For every rated parameter, fill the rating matrix. **One row per band** is a quick start; then
   write what each score looks like and how to measure it. Add metrics where something can be counted: their
   thresholds score the parameter automatically.
4. **3. Review & publish.** Fix everything in red. Publish, or submit for review if the scorecard needs a second
   person's approval.
5. To change a published scorecard, **Create new version**. Old results keep their old meaning.

Tip: start from a reference scorecard (**Clone**), and understand its intent rather than copying it.

## Owners: get work through the gate
1. **Work & gates → + New subject.** Create the project, then milestones and tasks under it. Set a due date and
   budget if the scorecard applies QTC. Optionally add its **task definition**: Objective, Deliverable, Quality
   and Risk (Time and Cost are the due date and budget you just set) — the six things worth writing down before
   work starts.
2. Open the task and **Check clarity** to have an agent flag anything too vague to act on (a goal with no
   measurable "done", a missing deadline) — purely advisory, it never changes anything.
3. **Start** a submission against a published scorecard. Paste the work or a link and notes.
4. **Self-appraise.** Score your own work honestly. Only you can see it.
5. **Submit for judging.**
6. If it comes back **Redo**, improve the work and **Start attempt 2**.

## Judges: evaluate
1. Open a submission that is *In review* (from Work, or a link) and click **Judge as <you>**. You can also add an
   **LLM judge** to get a first proposal.
2. For each parameter, click the score whose guideline matches the evidence, and write why. Enter metric values
   where asked.
3. **Complete evaluation**, then go **back to the submission**. Once enough judges are done, anyone can press
   **Decide**.

## Adjudicators
If judges disagree, the submission shows **Adjudication**. If you are neither the owner nor one of its judges,
choose the verdict and give the reason. Your reason becomes a guideline dispute that designers should fix.

## Leads
- **Needs attention** lists people with repeated reds. Talk to them, then record a diagnosis: skill (train),
  aptitude (reassign), will (discuss) or allocation (rescope). A red is information, not blame.
- The same page's **risk forecast** flags open submissions before they fail — overdue, over budget, a recent
  pattern of reds, a capability level below Competent, or a repeat attempt — each with a recommended next action
  from the same vocabulary as diagnosis. It's a forecast, not a verdict: read the factors before acting on it.
- **Capability & competency**, further down the same page, records a person's C1 (unaware) through C6 (expert)
  level for a scorecard's skill domain — never about yourself, same rule as diagnosis. History is kept, not
  overwritten, so you can see how someone progressed.
- The **Work** page shows the honest board: a project is green only when everything beneath it is green.

## Admins
**Users & roles** (visible only to admins) grants the elevated roles — Designer, Reviewer, Lead, Importer — to
registered members, and can deactivate an account (never your own). Everything a member can already do (create
subjects, self-appraise, submit, judge, adjudicate) needs no role; these four gate the rest.

## Quick evaluations
**Quick evaluation** rates anything against a published scorecard without the gate, for example a one-off review
or an LLM pre-check.

## Importing legacy spreadsheets
**Import legacy → choose the file → Preview.** Read the row-by-row outcomes and the reconciliation. Commit only
when every difference is explained. Recognised layout: metadata lines such as `Scale: 1-5` and `Target: 8` above a
header row with a KPI/Parameter column, optional Weight and Description columns, and score columns such as `10` or
`Score 8-9`; plus a ratings sheet with a subject column and one column per KPI.

## Analytics
Compare scorecards on a % of scale. Look for the weakest parameters, judge disagreement (rewrite those
guidelines), self-appraisal honesty, and QTC misses split into quality, time and cost.
