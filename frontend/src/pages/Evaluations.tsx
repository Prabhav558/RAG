import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, EvaluationRow, fmt, ScorecardSummary } from "../api";
import { ErrorBox, StatusChip } from "../components/common";

const RAG_COLOR: Record<string, string> = { GREEN: "#00B050", AMBER: "#FFC000", RED: "#C00000" };

export default function Evaluations() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const [rows, setRows] = useState<EvaluationRow[] | null>(null);
  const [cards, setCards] = useState<ScorecardSummary[]>([]);
  const [error, setError] = useState<unknown>(null);
  const scorecard = params.get("scorecard") ?? "";
  const status = params.get("status") ?? "";
  const priv = params.get("private") === "1";

  useEffect(() => { api.scorecards().then(setCards); }, []);
  useEffect(() => {
    setRows(null);
    api.evaluations({ scorecard_id: scorecard ? Number(scorecard) : undefined, status: status || undefined, include_private: priv })
      .then(setRows).catch(setError);
  }, [scorecard, status, priv]);

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v); else p.delete(k);
    setParams(p);
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Evaluations</h1>
          <div className="sub">Every rating, its score, band and verdict.</div>
        </div>
        <div className="row">
          <select value={scorecard} onChange={(e) => set("scorecard", e.target.value)} style={{ width: 220 }} aria-label="Scorecard">
            <option value="">All scorecards</option>
            {cards.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select value={status} onChange={(e) => set("status", e.target.value)} style={{ width: 140 }} aria-label="Status">
            <option value="">Any status</option>
            <option value="draft">Draft</option>
            <option value="completed">Completed</option>
            <option value="void">Void</option>
          </select>
          <label className="check small"><input type="checkbox" checked={priv} onChange={(e) => set("private", e.target.checked ? "1" : "")} /> include self-appraisals</label>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        {rows === null ? <div className="empty">Loading…</div> : rows.length === 0 ? <div className="empty">No evaluations match.</div> : (
          <table>
            <thead>
              <tr>
                <th>Subject</th><th>Scorecard</th><th>Evaluator</th><th>Status</th>
                <th className="num">Score</th><th className="num">Target</th><th>Band</th><th>Verdict</th><th>Date</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => nav(`/evaluations/${r.id}`)}>
                  <td>{r.subject_name}{r.subject_ref && <div className="small muted">{r.subject_ref}</div>}</td>
                  <td>{r.scorecard_name} <span className="muted small">v{r.version_no}</span></td>
                  <td>{r.evaluator_type}{r.evaluator_name && <div className="small muted">{r.evaluator_name}</div>}</td>
                  <td><StatusChip status={r.status} /></td>
                  <td className="num"><b>{fmt(r.final_score)}</b></td>
                  <td className="num">{fmt(r.target_score)}</td>
                  <td>
                    {r.rag && <i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 2, background: RAG_COLOR[r.rag], marginRight: 6 }} />}
                    {r.band_label ?? "—"}
                  </td>
                  <td>{r.quality_met === null ? <span className="muted">—</span> : r.quality_met ? <span className="chip pass">✓ met</span> : <span className="chip fail">✗ below</span>}</td>
                  <td className="small muted">{new Date(r.completed_at ?? r.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
