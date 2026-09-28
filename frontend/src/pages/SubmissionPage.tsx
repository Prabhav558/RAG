import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, bandFor, fmt, SubmissionView } from "../api";
import { BandChip, ErrorBox, Field, ScoreBadge, SUBMISSION_LABEL, useActor, when } from "../components/common";

const same = (a?: string | null, b?: string | null) => !!a && !!b && a.trim().toLowerCase() === b.trim().toLowerCase();

function Stepper({ s }: { s: SubmissionView }) {
  const order = ["open", "in_review", s.status === "adjudication" || s.adjudicated ? "adjudication" : null, "decided"].filter(Boolean) as string[];
  const idx = order.indexOf(s.status);
  if (s.status === "withdrawn" || s.status === "cancelled") {
    return <div className="stepper"><span className="s bad">{SUBMISSION_LABEL[s.status]}</span></div>;
  }
  return (
    <div className="stepper" aria-label="Progress">
      {order.map((st, i) => (
        <span key={st} className={`s ${i < idx ? "done" : i === idx ? (st === "decided" && s.decision === "redo" ? "bad" : "now") : ""}`}>
          {i < idx ? "✓ " : ""}{SUBMISSION_LABEL[st]}{st === "decided" && s.decision ? `: ${s.decision}` : ""}
        </span>
      ))}
    </div>
  );
}

export default function SubmissionPage() {
  const { submissionId } = useParams();
  const id = Number(submissionId);
  const nav = useNavigate();
  const actor = useActor();
  const [s, setS] = useState<SubmissionView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [verdict, setVerdict] = useState<"passed" | "redo">("passed");
  const [reason, setReason] = useState("");
  const load = useCallback(() => api.submission(id).then(setS).catch(setError), [id]);
  useEffect(() => { load(); }, [load]);
  if (!s) return <>{error ? <ErrorBox error={error} /> : <div className="empty">Loading…</div>}</>;

  const scale = s.version.rating_scale;
  const isOwner = same(actor, s.owner);
  const judges = s.evaluations.filter((e) => e.is_judge);
  const completedJudges = judges.filter((e) => e.status === "completed");
  const selfEval = s.evaluations.find((e) => !e.is_judge && e.status !== "void");
  const myJudging = judges.find((e) => same(e.evaluator_name, actor) && e.status === "draft");

  async function act<T>(fn: () => Promise<T>, goto?: (r: T) => string | undefined) {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      const target = goto?.(r);
      if (target) nav(target);
      else await load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="row small muted"><Link to="/work">Work</Link> / <Link to={`/subjects/${s.subject.id}`}>{s.subject.name}</Link></div>
          <h1>{s.title ?? s.subject.name} <span className="muted" style={{ fontWeight: 400 }}>· attempt {s.attempt_no}</span></h1>
          <div className="small muted">
            {s.version.scorecard_name} v{s.version.version_no} · owner <b>{s.owner}</b> · {s.version.required_judges} judge{s.version.required_judges > 1 ? "s" : ""} within {s.version.judge_tolerance_pct}%
            {s.version.require_self_appraisal ? " · self-appraisal required" : ""}{s.version.is_foundational ? " · foundational" : ""}{s.version.qtc_enabled ? " · QTC" : ""}
            {s.previous_id && <> · <Link to={`/submissions/${s.previous_id}`}>previous attempt</Link></>}
          </div>
          <Stepper s={s} />
        </div>
      </div>
      <ErrorBox error={error} />

      <div className="eval-layout">
        <div>
          <div className="card">
            <h2>What happens next</h2>
            <NextStep s={s} actor={actor} isOwner={isOwner} completedJudges={completedJudges.length} selfDone={selfEval?.status === "completed"} />
            <div className="actions-bar" style={{ marginTop: 10 }}>
              {s.status === "open" && !selfEval && (
                <button disabled={busy || !isOwner} title={isOwner ? "" : `Only ${s.owner} self-appraises`}
                  onClick={() => act(() => api.addSubmissionEvaluation(s.id, { evaluator_type: "self" }), (ev) => `/evaluations/${ev.id}`)}>
                  Self-appraise
                </button>
              )}
              {s.allowed_actions.includes("submit") && (
                <button className="primary" disabled={busy || !isOwner} title={isOwner ? "" : `Only ${s.owner} submits`}
                  onClick={() => act(() => api.submissionAction(s.id, "submit"))}>Submit for judging</button>
              )}
              {s.status === "in_review" && !myJudging && (
                <>
                  <button disabled={busy || !actor || isOwner} title={isOwner ? "Owners cannot judge their own work" : ""}
                    onClick={() => act(() => api.addSubmissionEvaluation(s.id, { evaluator_type: "human", evaluator_name: actor }), (ev) => `/evaluations/${ev.id}`)}>
                    Judge as {actor || "…"}
                  </button>
                  <button disabled={busy} onClick={() => act(() => api.addSubmissionEvaluation(s.id, { evaluator_type: "llm" }), (ev) => `/evaluations/${ev.id}`)}>
                    Add LLM judge
                  </button>
                </>
              )}
              {myJudging && <Link className="btn" to={`/evaluations/${myJudging.id}`}>Continue my judgement →</Link>}
              {s.allowed_actions.includes("decide") && (
                <button className="primary" disabled={busy || completedJudges.length < s.version.required_judges}
                  onClick={() => act(() => api.submissionAction(s.id, "decide"))}>
                  Decide ({completedJudges.length}/{s.version.required_judges} judges done)
                </button>
              )}
              {s.allowed_actions.includes("withdraw") && isOwner && (
                <button disabled={busy} onClick={() => act(() => api.submissionAction(s.id, "withdraw"))}>Withdraw</button>
              )}
              {s.allowed_actions.includes("cancel") && !isOwner && (
                <button className="danger" disabled={busy} onClick={() => {
                  const r = window.prompt("Why cancel this work?");
                  if (r) act(() => api.cancelSubmission(s.id, r));
                }}>Cancel</button>
              )}
              {s.status === "decided" && s.decision === "redo" && (
                <button className="primary" disabled={busy} onClick={() => act(() => api.startSubmission(s.subject.id, { version_id: s.version.id }), (r) => `/submissions/${r.id}`)}>
                  Start attempt {s.attempt_no + 1}
                </button>
              )}
            </div>
            {s.status === "adjudication" && (
              <div className="card flat" style={{ marginTop: 12 }}>
                <h3>Adjudication</h3>
                <p className="hint">The judges disagree (spread {fmt(s.judge_spread_pct, 1)}% vs tolerance {s.version.judge_tolerance_pct}%, or different verdicts).
                  An adjudicator who is neither the owner nor a judge settles it. The reason is kept as a guideline dispute.</p>
                <div className="form-grid">
                  <Field label="Verdict">
                    <select value={verdict} onChange={(e) => setVerdict(e.target.value as "passed" | "redo")}>
                      <option value="passed">Passed</option><option value="redo">Redo</option>
                    </select>
                  </Field>
                </div>
                <Field label="Reason (required)"><textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} /></Field>
                <button className="primary" disabled={busy || reason.trim().length < 3} onClick={() => act(() => api.adjudicate(s.id, verdict, reason))}>Record adjudication</button>
              </div>
            )}
          </div>

          <div className="card" style={{ marginTop: 14, overflowX: "auto" }}>
            <h2>Evaluations</h2>
            {s.evaluations.length === 0 ? <p className="muted">None yet.</p> : (
              <table>
                <thead><tr><th>Role</th><th>By</th><th>Status</th><th className="num">Score</th><th>Band</th><th>Verdict</th></tr></thead>
                <tbody>
                  {s.evaluations.map((e) => (
                    <tr key={e.id} className={e.redacted ? "" : "clickable"} onClick={() => !e.redacted && nav(`/evaluations/${e.id}`)}>
                      <td>{e.is_judge ? (e.evaluator_type === "llm" ? "LLM judge" : "Judge") : "Self-appraisal"}</td>
                      <td>{e.evaluator_name}</td>
                      <td>{e.status}</td>
                      {e.redacted ? (
                        <td colSpan={3} className="muted small">🔒 private to {s.owner}</td>
                      ) : (
                        <>
                          <td className="num"><b>{fmt(e.final_score)}</b></td>
                          <td>{e.band_label ?? "—"}</td>
                          <td>{e.quality_met === null ? "—" : e.quality_met ? <span className="chip pass">✓</span> : <span className="chip fail">✗</span>}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <h2>The work</h2>
            {s.status === "open" ? (
              <textarea rows={6} defaultValue={s.input_text ?? ""} placeholder="Paste the work, or a link and notes, for judges to evaluate"
                onBlur={(e) => e.target.value !== (s.input_text ?? "") && act(() => api.updateSubmission(s.id, { input_text: e.target.value }))} />
            ) : <p style={{ whiteSpace: "pre-wrap" }}>{s.input_text || <span className="muted">—</span>}</p>}
            {s.version.qtc_enabled && (
              <div className="row" style={{ marginTop: 8 }}>
                <span className="small">Actual cost of this attempt</span>
                <input type="number" min={0} style={{ width: 140 }} defaultValue={s.actual_cost ?? ""} disabled={["decided", "withdrawn", "cancelled"].includes(s.status)}
                  onBlur={(e) => act(() => api.updateSubmission(s.id, { actual_cost: e.target.value === "" ? null : Number(e.target.value) }))} />
                <span className="hint">due {when(s.subject.due_at)} · budget {s.subject.budget ?? "—"}</span>
              </div>
            )}
          </div>
        </div>

        <div className="sticky">
          <div className="card">
            <h3>Gate decision</h3>
            {s.official_score === null ? <p className="muted">Not decided yet.</p> : (
              <>
                <div className="row">
                  <ScoreBadge score={s.official_score} scale={scale} size="lg" />
                  <div>
                    <BandChip band={bandFor(s.official_score, scale)} />
                    <div className="hint">mean of {completedJudges.length} judge(s) · target {s.version.target_score} · spread {fmt(s.judge_spread_pct, 1)}%</div>
                  </div>
                </div>
                {s.decision && (
                  <div style={{ marginTop: 10 }}>
                    <span className={`chip ${s.decision === "passed" ? "pass" : "fail"}`}>{s.decision === "passed" ? "✓ Passed the gate" : "✗ Redo"}</span>
                    {s.adjudicated && <span className="chip neutral" style={{ marginLeft: 6 }}>adjudicated by {s.decided_by}</span>}
                    {s.decision_reason && <p className="small" style={{ marginTop: 6 }}>{s.decision_reason}</p>}
                  </div>
                )}
                {s.gate_failures.length > 0 && (
                  s.adjudicated && s.decision === "passed" ? (
                    <div className="alert warn" style={{ marginTop: 10 }}>Gate concern raised by a judge, overruled at adjudication:
                      <ul>{s.gate_failures.map((g) => <li key={g.code}>{g.code} {g.name}: {fmt(g.score)} &lt; {fmt(g.floor)}</li>)}</ul>
                    </div>
                  ) : (
                    <div className="alert error" style={{ marginTop: 10 }}>Critical gate failed:
                      <ul>{s.gate_failures.map((g) => <li key={g.code}>{g.code} {g.name}: {fmt(g.score)} &lt; {fmt(g.floor)}</li>)}</ul>
                    </div>
                  )
                )}
                {s.version.qtc_enabled && s.decision && (
                  <div className="row" style={{ marginTop: 8 }}>
                    <span className={`chip ${s.decision === "passed" ? "pass" : "fail"}`}>Q</span>
                    <span className={`chip ${s.time_met ? "pass" : "fail"}`}>T {s.time_met ? "met" : "missed"}</span>
                    <span className={`chip ${s.cost_met ? "pass" : "fail"}`}>C {s.cost_met ? "met" : "missed"}</span>
                    <b className="small">{s.qtc_green ? "Green" : "Not green"}</b>
                  </div>
                )}
                {s.blocks_project && <div className="alert error" style={{ marginTop: 10 }}>⛔ Foundational red: the project is stopped until this is fixed.</div>}
              </>
            )}
          </div>
          <div className="card" style={{ marginTop: 14 }}>
            <h3>Timeline</h3>
            <ul className="timeline">
              {s.events.map((e, i) => (
                <li key={i}>
                  <b>{e.action.replace("_", " ")}</b>{e.to && e.to !== e.from ? ` → ${SUBMISSION_LABEL[e.to] ?? e.to}` : ""}
                  <div className="hint">{e.actor} · {when(e.at)}</div>
                  {typeof e.details?.reason === "string" && <div className="small">“{e.details.reason as string}”</div>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </>
  );
}

function NextStep({ s, actor, isOwner, completedJudges, selfDone }: {
  s: SubmissionView; actor: string; isOwner: boolean; completedJudges: number; selfDone: boolean;
}) {
  let text = "";
  if (s.status === "open") {
    text = s.version.require_self_appraisal && !selfDone
      ? `${s.owner} self-appraises the work privately, then submits it.`
      : `${s.owner} submits the work for judging${selfDone ? "" : " (a private self-appraisal first is recommended)"}.`;
  } else if (s.status === "in_review") {
    text = completedJudges < s.version.required_judges
      ? `Waiting for ${s.version.required_judges - completedJudges} more independent judgement(s). Anyone except ${s.owner} can judge.`
      : "All judgements are in: anyone can ask the gate to decide.";
  } else if (s.status === "adjudication") text = "Judges disagree: an independent adjudicator records the verdict.";
  else if (s.status === "decided") text = s.decision === "passed" ? "Passed. The work can move on." : "Below target. The owner redoes the work as a new attempt.";
  else text = `This submission was ${s.status}.`;
  return <p>{text}{isOwner && s.status === "in_review" ? " (You are the owner.)" : ""}{!actor ? "" : ""}</p>;
}
