# User Guide

Set **Acting as** (top of the sidebar) to your name first. Every action is recorded under it, and the rules
depend on who you are: owners can't judge their own work, and reviewers can't approve their own scorecards.

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
   budget if the scorecard applies QTC.
2. Open the task and **Start** a submission against a published scorecard. Paste the work or a link and notes.
3. **Self-appraise.** Score your own work honestly. Only you can see it.
4. **Submit for judging.**
5. If it comes back **Redo**, improve the work and **Start attempt 2**.

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
- The **Work** page shows the honest board: a project is green only when everything beneath it is green.

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
