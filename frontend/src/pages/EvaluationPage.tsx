import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { api, bandFor, EvaluationView, fmt, MetricView, NodeView, RatingIn, Scale } from "../api";
import { BandChip, ErrorBox, ScoreBadge, StatusChip, Verdict } from "../components/common";

function ratingFrom(n: NodeView): RatingIn {
  const r = n.result!;
  return {
    parameter_id: n.id,
    judged_score: r.judged_score,
    not_applicable: r.not_applicable,
    rationale: r.rationale,
    evidence: r.evidence,
    confidence: r.confidence,
    override_reason: r.override_reason,
  };
}

const SOURCE_LABEL: Record<string, string> = {
  judged: "judged",
  metric: "from metrics",
  override: "override",
  rollup: "rolled up",
  not_applicable: "N/A",
  pending: "not scored",
};

export default function EvaluationPage() {
  const { evaluationId } = useParams();
  const id = Number(evaluationId);
  const location = useLocation();
  const [ev, setEv] = useState<EvaluationView | null>(null);
  const [error, setError] = useState<unknown>((location.state as { judgeError?: unknown } | null)?.judgeError ?? null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => api.evaluation(id).then(setEv).catch(setError), [id]);
  useEffect(() => { load(); }, [load]);

  if (!ev) return <>{error ? <ErrorBox error={error} /> : <div className="empty">Loading…</div>}</>;
  const scale = ev.version.rating_scale;
  const editable = ev.status === "draft";

  async function run<T>(label: string, fn: () => Promise<T>) {
    setBusy(label);
    setError(null);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "version" in (r as object)) setEv(r as unknown as EvaluationView);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  const saveRating = (n: NodeView, patch: Partial<RatingIn>) =>
    run("save", () => api.updateEvaluation(ev.id, { ratings: [{ ...ratingFrom(n), ...patch }] }));
  const saveMetric = (m: MetricView, value: number | null) =>
    run("save", () => api.updateEvaluation(ev.id, { metric_values: [{ metric_id: m.id, value, source: "manual" }] }));

  const band = bandFor(ev.final_score, scale);
  const pendingCount = ev.pending_parameter_ids.length;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="row small muted">
            <Link to="/evaluations">Evaluations</Link> / {ev.version.scorecard_name} v{ev.version.version_no}
          </div>
          <h1>{ev.subject_name}</h1>
          <div className="row">
            <StatusChip status={ev.status} />
            <span className="chip neutral">{ev.evaluator_type === "llm" ? "LLM judge" : ev.evaluator_type === "self" ? "Self-appraisal" : "Human judge"}</span>
            {ev.is_private && <span className="chip neutral">Private</span>}
            {ev.subject_ref && <span className="chip neutral">{ev.subject_ref}</span>}
            {ev.attempt_no > 1 && <span className="chip neutral">Attempt {ev.attempt_no}</span>}
            {ev.origin === "import" && <span className="chip neutral" title={ev.origin_ref ?? ""}>Imported</span>}
            {ev.judge_model && <span className="small muted">judge: {ev.judge_model}</span>}
          </div>
        </div>
      </div>
      <ErrorBox error={error} />
      {ev.status === "void" && <div className="alert warn">Voided: {ev.voided_reason}</div>}
      {ev.judge_unrated ? (
        <div className="alert warn">The LLM judge did not rate {ev.judge_unrated} parameter(s). Rate them before completing.</div>
      ) : null}

      <div className="eval-layout">
        <div>
          {ev.version.parameters.map((n) => (
            <ParamNode key={n.id} node={n} scale={scale} editable={editable} busy={!!busy} onRate={saveRating} onMetric={saveMetric} />
          ))}
        </div>

        <div className="sticky">
          <div className="card">
            <div className="row">
              <ScoreBadge score={ev.final_score} scale={scale} size="lg" />
              <div>
                <BandChip band={band} />
                <div className="small muted" style={{ marginTop: 4 }}>Target {fmt(ev.target_score)} · {scale.name}</div>
              </div>
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <Verdict met={ev.quality_met} pending={pendingCount ? `${pendingCount} to rate` : "Pending"} />
              {ev.version.qtc_enabled && (
                ev.qtc_green === null ? <span className="chip neutral">QTC pending</span>
                  : ev.qtc_green ? <span className="chip pass">QTC green</span> : <span className="chip fail">QTC not green</span>
              )}
            </div>
            {pendingCount > 0 && ev.final_score !== null && (
              <p className="small muted" style={{ marginTop: 8 }}>Provisional: computed over the parameters rated so far.</p>
            )}
            {ev.gate_failures.length > 0 && (
              <div className="alert error" style={{ marginTop: 10 }}>
                Critical gate failed:
                <ul>{ev.gate_failures.map((g) => <li key={g.parameter_id}>{g.code} {g.name}: {fmt(g.score)} &lt; {fmt(g.floor)}</li>)}</ul>
              </div>
            )}
            {ev.version.qtc_enabled && (
              <div style={{ marginTop: 10 }}>
                <b className="small">QTC rule — Quality AND Time AND Cost</b>
                {(["time_met", "cost_met"] as const).map((k) => (
                  <div className="row" key={k} style={{ marginTop: 4 }}>
                    <span style={{ width: 90 }}>{k === "time_met" ? "Time met?" : "Cost met?"}</span>
                    <select
                      disabled={!editable}
                      value={ev[k] === null ? "" : ev[k] ? "yes" : "no"}
                      onChange={(e) => run("save", () => api.updateEvaluation(ev.id, { [k]: e.target.value === "" ? null : e.target.value === "yes" }))}
                      style={{ width: 110 }}
                    >
                      <option value="">—</option><option value="yes">Yes</option><option value="no">No</option>
                    </select>
                  </div>
                ))}
              </div>
            )}
            {editable && (
              <div className="row" style={{ marginTop: 14 }}>
                <button className="primary" disabled={!!busy || pendingCount > 0} onClick={() => run("complete", () => api.complete(ev.id))}
                  title={pendingCount ? "Rate every required parameter first" : "Lock the evaluation"}>
                  Complete evaluation
                </button>
                <button disabled={!!busy} onClick={() => {
                  const reason = window.prompt("Why void this evaluation?");
                  if (reason) run("void", () => api.void(ev.id, reason));
                }}>Void</button>
              </div>
            )}
            {ev.status === "completed" && (
              <button style={{ marginTop: 12 }} onClick={() => {
                const reason = window.prompt("Why void this completed evaluation?");
                if (reason) run("void", () => api.void(ev.id, reason));
              }}>Void</button>
            )}
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <h3>Input</h3>
            {editable ? (
              <textarea rows={6} defaultValue={ev.input_text ?? ""} placeholder="Text, notes or data to evaluate"
                onBlur={(e) => e.target.value !== (ev.input_text ?? "") && run("save", () => api.updateEvaluation(ev.id, { input_text: e.target.value }))} />
            ) : (
              <p className="small" style={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>{ev.input_text || <span className="muted">No text input</span>}</p>
            )}
            {ev.documents.map((d) => <div key={d.id} className="small">📄 {d.filename} <span className="muted">({d.chars.toLocaleString()} chars)</span></div>)}
            {editable && (
              <>
                <input type="file" accept=".txt,.md,.csv,.json,.docx,.pdf" style={{ marginTop: 8 }}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) run("upload", () => api.uploadDocument(ev.id, f)); }} />
                <button style={{ marginTop: 10, width: "100%", justifyContent: "center" }} disabled={!!busy}
                  onClick={() => run("judge", () => api.llmJudge(ev.id))}>
                  {busy === "judge" ? "LLM judge is scoring…" : "✨ Run LLM judge on the input"}
                </button>
                <p className="small muted" style={{ marginTop: 6 }}>LLM first, human second: the judge proposes scores and reasons; you review and adjust.</p>
              </>
            )}
          </div>

          <div className="card" style={{ marginTop: 14 }}>
            <h3>Overall summary</h3>
            {editable ? (
              <textarea rows={4} defaultValue={ev.summary ?? ""} key={ev.summary ?? ""}
                onBlur={(e) => e.target.value !== (ev.summary ?? "") && run("save", () => api.updateEvaluation(ev.id, { summary: e.target.value }))} />
            ) : (
              <p style={{ whiteSpace: "pre-wrap" }}>{ev.summary || <span className="muted">—</span>}</p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function ParamNode({ node, scale, editable, busy, onRate, onMetric }: {
  node: NodeView; scale: Scale; editable: boolean; busy: boolean;
  onRate: (n: NodeView, patch: Partial<RatingIn>) => void; onMetric: (m: MetricView, v: number | null) => void;
}) {
  const r = node.result!;
  if (!node.is_leaf) {
    return (
      <div className="param-group" style={{ borderLeftColor: bandFor(r.final_score, scale)?.color_hex }}>
        <div className="param-head">
          <ScoreBadge score={r.final_score} scale={scale} />
          <span className="mono muted">{node.code}</span>
          <span className="title">{node.name}</span>
          {node.is_critical && <span className="tag crit">GATE ≥ {node.min_acceptable_score ?? "target"}</span>}
          {node.aggregation === "minimum" && <span className="tag">MIN roll-up</span>}
          <span className="small muted">{fmt((r.effective_weight ?? 0) * 100, 1)}% of total</span>
        </div>
        {node.description && <p className="small muted" style={{ margin: "4px 0 0" }}>{node.description}</p>}
        {node.children.map((c) => <ParamNode key={c.id} node={c} scale={scale} editable={editable} busy={busy} onRate={onRate} onMetric={onMetric} />)}
      </div>
    );
  }

  const matched = node.criteria.find((c) => r.final_score !== null && r.final_score >= c.score_min && r.final_score <= c.score_max);
  const hasMetrics = node.metrics.length > 0;
  const scores: number[] = [];
  if (scale.max_value - scale.min_value <= 20) for (let s = scale.min_value; s <= scale.max_value; s++) scores.push(s);

  return (
    <div className={`leaf ${r.score_source === "pending" ? "pending" : ""}`}>
      <div className="param-head">
        <ScoreBadge score={r.not_applicable ? null : r.final_score} scale={scale} />
        <span className="mono muted">{node.code}</span>
        <span className="title">{node.name}</span>
        {node.is_critical && <span className="tag crit">GATE ≥ {node.min_acceptable_score ?? "target"}</span>}
        <span className="chip neutral">{SOURCE_LABEL[r.score_source] ?? r.score_source}</span>
        <span className="spacer" />
        <span className="small muted">{fmt((r.effective_weight ?? 0) * 100, 1)}% of total</span>
      </div>
      {node.description && <p className="small muted" style={{ margin: "4px 0" }}>{node.description}</p>}

      {node.is_optional && (
        <label className="check small" style={{ margin: "4px 0" }}>
          <input type="checkbox" disabled={!editable || busy} checked={r.not_applicable}
            onChange={(e) => onRate(node, { not_applicable: e.target.checked })} />
          Not applicable to this subject
        </label>
      )}

      {!r.not_applicable && (
        <>
          {hasMetrics && (
            <div className="row" style={{ margin: "8px 0", gap: 14 }}>
              {node.metrics.map((m) => (
                <label key={m.id} className="small" style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 180 }}>
                  <span><b>{m.name}</b>{m.unit ? ` (${m.unit})` : ""}{m.value_source === "llm" ? " · from LLM" : ""}</span>
                  <input type="number" step="any" disabled={!editable || busy} defaultValue={m.value ?? ""} key={`${m.id}-${m.value}`}
                    onBlur={(e) => {
                      const v = e.target.value === "" ? null : Number(e.target.value);
                      if (v !== (m.value ?? null)) onMetric(m, v);
                    }} />
                </label>
              ))}
              {r.computed_score !== null && <span className="small">→ metric score <b>{fmt(r.computed_score)}</b></span>}
            </div>
          )}
          {scores.length > 0 ? (
            <div className="scores" role="radiogroup" aria-label={`Score for ${node.name}`}>
              {scores.map((s) => {
                const b = bandFor(s, scale);
                const crit = node.criteria.find((c) => s >= c.score_min && s <= c.score_max);
                return (
                  <button key={s} className={`score-btn ${r.judged_score === s ? "selected" : ""}`} disabled={!editable || busy}
                    style={{ background: b?.color_hex, color: b?.font_hex, borderColor: "transparent" }}
                    title={crit ? `${crit.qualitative}${crit.quantitative ? `\n— ${crit.quantitative}` : ""}` : ""}
                    onClick={() => onRate(node, { judged_score: r.judged_score === s ? null : s })}
                    aria-pressed={r.judged_score === s}>
                    {s}
                  </button>
                );
              })}
            </div>
          ) : (
            <input type="number" style={{ width: 120, margin: "8px 0" }} disabled={!editable || busy} min={scale.min_value} max={scale.max_value}
              defaultValue={r.judged_score ?? ""} key={`j-${r.judged_score}`}
              onBlur={(e) => onRate(node, { judged_score: e.target.value === "" ? null : Number(e.target.value) })} />
          )}
          {hasMetrics && r.judged_score !== null && r.computed_score !== null && r.judged_score !== r.computed_score && (
            <div className="small" style={{ marginBottom: 6 }}>
              The metric score ({fmt(r.computed_score)}) takes precedence over the judged score ({fmt(r.judged_score)}).{" "}
              {editable ? "To override it, give a reason:" : r.override_reason ? `Overridden: ${r.override_reason}` : ""}
              {editable && (
                <input style={{ marginTop: 4 }} defaultValue={r.override_reason ?? ""} placeholder="Override reason (audited)"
                  onBlur={(e) => e.target.value !== (r.override_reason ?? "") && onRate(node, { override_reason: e.target.value || null })} />
              )}
            </div>
          )}
          {matched && (
            <div className="criterion">
              <b>{matched.score_min === matched.score_max ? matched.score_min : `${matched.score_min}–${matched.score_max}`}</b>
              {matched.qualitative}
              {matched.quantitative && <div className="muted small">Quantitative: {matched.quantitative}</div>}
            </div>
          )}
          {editable ? (
            <textarea rows={2} placeholder="Rationale: why this score? Point to evidence." defaultValue={r.rationale ?? ""} key={`r-${r.rationale}`}
              onBlur={(e) => e.target.value !== (r.rationale ?? "") && onRate(node, { rationale: e.target.value })} />
          ) : r.rationale ? (
            <p className="small"><b>Rationale:</b> {r.rationale}</p>
          ) : null}
          {r.evidence && <p className="small muted" style={{ marginTop: 4 }}><b>Evidence:</b> {r.evidence}</p>}
          {r.confidence !== null && <p className="small muted">Judge confidence: {Math.round(r.confidence * 100)}%</p>}
          <details className="matrix-view">
            <summary>Rating matrix</summary>
            <table>
              <tbody>
                {node.criteria.map((c, i) => (
                  <tr key={i} style={matched === c ? { fontWeight: 600 } : undefined}>
                    <td style={{ width: 60 }}><ScoreBadge score={c.score_max} scale={scale} />{c.score_min !== c.score_max && <span className="small"> ≥{c.score_min}</span>}</td>
                    <td>{c.qualitative}</td>
                    <td className="muted">{c.quantitative}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </div>
  );
}
