/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import { api, fmt, pct, ScorecardSummary } from "../api";
import { ErrorBox } from "../components/common";

// RAG status colours come from the framework's fixed band convention; they always ship with a text label.
const RAG = [
  { key: "GREEN", label: "Green", color: "#00B050", font: "#fff" },
  { key: "AMBER", label: "Amber", color: "#FFC000", font: "#000" },
  { key: "RED", label: "Red", color: "#C00000", font: "#fff" },
];

function RagStack({ dist }: { dist: Record<string, number> }) {
  const total = RAG.reduce((s, r) => s + (dist[r.key] ?? 0), 0);
  if (!total) return <span className="muted small">No data</span>;
  return (
    <div className="stack" role="img" aria-label={RAG.map((r) => `${r.label} ${dist[r.key] ?? 0}`).join(", ")}>
      {RAG.filter((r) => dist[r.key]).map((r) => (
        <div key={r.key} style={{ width: `${(dist[r.key] / total) * 100}%`, background: r.color, color: r.font }}
          title={`${r.label}: ${dist[r.key]} (${Math.round((dist[r.key] / total) * 100)}%)`}>
          {dist[r.key] / total > 0.08 ? `${Math.round((dist[r.key] / total) * 100)}%` : ""}
        </div>
      ))}
    </div>
  );
}

function Tile({ value, label, hint }: { value: string; label: string; hint?: string }) {
  return (
    <div className="card tile" title={hint}>
      <div className="v">{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}

function TrendChart({ data }: { data: any[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (data.length === 0) return <div className="muted small">No completed evaluations yet.</div>;
  const W = 560, H = 180, P = { l: 36, r: 12, t: 12, b: 26 };
  const x = (i: number) => P.l + (data.length === 1 ? (W - P.l - P.r) / 2 : (i * (W - P.l - P.r)) / (data.length - 1));
  const y = (v: number) => P.t + (1 - v / 100) * (H - P.t - P.b);
  const d = data.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.avg_score_pct)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Average score by month, as % of scale">
      {[0, 25, 50, 75, 100].map((g) => (
        <g key={g}>
          <line x1={P.l} x2={W - P.r} y1={y(g)} y2={y(g)} stroke="var(--border)" strokeWidth={1} />
          <text x={P.l - 6} y={y(g) + 4} textAnchor="end" fontSize={10} fill="var(--muted)">{g}%</text>
        </g>
      ))}
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2} />
      {data.map((p, i) => (
        <g key={p.period} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
          <rect x={x(i) - 16} y={P.t} width={32} height={H - P.t - P.b} fill="transparent" />
          <circle cx={x(i)} cy={y(p.avg_score_pct)} r={hover === i ? 5 : 4} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />
          <text x={x(i)} y={H - 8} fontSize={10} fill="var(--muted)"
            textAnchor={data.length > 1 && i === 0 ? "start" : data.length > 1 && i === data.length - 1 ? "end" : "middle"}>{p.period}</text>
        </g>
      ))}
      {hover !== null && (
        <g>
          <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="var(--muted)" strokeDasharray="3 3" />
          <rect x={Math.min(x(hover) + 8, W - 150)} y={P.t} width={140} height={48} rx={6} fill="var(--surface)" stroke="var(--border)" />
          <text x={Math.min(x(hover) + 16, W - 142)} y={P.t + 16} fontSize={11} fill="var(--text)" fontWeight={600}>{data[hover].period}</text>
          <text x={Math.min(x(hover) + 16, W - 142)} y={P.t + 30} fontSize={11} fill="var(--text-2)">Avg {data[hover].avg_score_pct}% · n={data[hover].count}</text>
          <text x={Math.min(x(hover) + 16, W - 142)} y={P.t + 43} fontSize={11} fill="var(--text-2)">Pass rate {pct(data[hover].pass_rate)}</text>
        </g>
      )}
    </svg>
  );
}

export default function Analytics() {
  const [cards, setCards] = useState<ScorecardSummary[]>([]);
  const [scorecardId, setScorecardId] = useState<number | undefined>();
  const [overview, setOverview] = useState<any>(null);
  const [agreement, setAgreement] = useState<any>(null);
  const [trend, setTrend] = useState<any[]>([]);
  const [params, setParams] = useState<any>(null);
  const [versionId, setVersionId] = useState<number | undefined>();
  const [error, setError] = useState<unknown>(null);
  const [behaviour, setBehaviour] = useState<any>(null);

  useEffect(() => { api.scorecards().then(setCards); api.behaviour().then(setBehaviour).catch(() => undefined); }, []);
  useEffect(() => {
    Promise.all([api.overview(scorecardId), api.agreement(scorecardId), api.trend(scorecardId)])
      .then(([o, a, t]) => { setOverview(o); setAgreement(a); setTrend(t); })
      .catch(setError);
    const card = cards.find((c) => c.id === scorecardId);
    const v = card ? [...card.versions].reverse().find((x) => x.status !== "draft") : undefined;
    setVersionId(v?.id);
  }, [scorecardId, cards]);
  useEffect(() => {
    if (versionId) api.parameterBreakdown(versionId).then(setParams).catch(setError);
    else setParams(null);
  }, [versionId]);

  const card = cards.find((c) => c.id === scorecardId);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Analytics</h1>
          <div className="sub">Completed, non-private evaluations. Scores are compared across scorecards as % of each scale.</div>
        </div>
        <select value={scorecardId ?? ""} onChange={(e) => setScorecardId(e.target.value ? Number(e.target.value) : undefined)} style={{ width: 260 }} aria-label="Scorecard">
          <option value="">All scorecards</option>
          {cards.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <ErrorBox error={error} />
      {!overview ? <div className="empty">Loading…</div> : (
        <>
          <div className="grid tiles">
            <Tile value={String(overview.total_completed)} label="Completed evaluations" />
            <Tile value={overview.avg_score_pct === null ? "—" : `${overview.avg_score_pct}%`} label="Average score (% of scale)" />
            <Tile value={pct(overview.pass_rate)} label="Meet target" />
            <Tile value={pct(overview.first_attempt_pass_rate)} label="Meet target first time" hint="Share of first submissions that reach target" />
            {overview.qtc_green_rate !== null && <Tile value={pct(overview.qtc_green_rate)} label="QTC green" />}
            <Tile value={String(overview.library.scorecards)} label="Scorecards in library" />
          </div>

          <div className="grid two" style={{ marginTop: 14 }}>
            <div className="card">
              <h2>Honest RAG distribution</h2>
              <RagStack dist={overview.rag_distribution} />
              <div className="legend">
                {RAG.map((r) => <span key={r.key}><i style={{ background: r.color }} />{r.label}: {overview.rag_distribution[r.key] ?? 0}</span>)}
              </div>
              <p className="small muted" style={{ marginTop: 10 }}>
                An all-green board with poor outcomes is the failure mode. An early rainbow is healthy.
              </p>
              <h3 style={{ marginTop: 16 }}>By evaluator</h3>
              <table>
                <thead><tr><th>Evaluator</th><th className="num">Count</th><th className="num">Avg (% of scale)</th></tr></thead>
                <tbody>
                  {Object.entries(overview.by_evaluator_type).map(([k, v]: [string, any]) => (
                    <tr key={k}><td>{k}</td><td className="num">{v.count}</td><td className="num">{v.avg_score_pct}%</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card">
              <h2>Average score over time</h2>
              <TrendChart data={trend} />
            </div>
          </div>

          <div className="card" style={{ marginTop: 14, overflowX: "auto" }}>
            <h2>Scorecards</h2>
            <table>
              <thead>
                <tr><th>Scorecard</th><th>Subject</th><th className="num">Evaluations</th><th className="num">Avg score</th>
                  <th className="num">Meet target</th><th className="num">Gate failures</th><th style={{ width: 220 }}>RAG</th></tr>
              </thead>
              <tbody>
                {overview.scorecards.map((s: any) => (
                  <tr key={s.scorecard_id} className="clickable" onClick={() => setScorecardId(s.scorecard_id)}>
                    <td>{s.name}</td><td className="muted">{s.subject_type}</td>
                    <td className="num">{s.evaluations}</td>
                    <td className="num">{fmt(s.avg_score)} <span className="muted small">({s.avg_score_pct}%)</span></td>
                    <td className="num">{pct(s.pass_rate)}</td>
                    <td className="num">{pct(s.gate_failure_rate)}</td>
                    <td><RagStack dist={s.rag} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid two" style={{ marginTop: 14 }}>
            <div className="card">
              <h2>Parameter breakdown {card && <span className="muted" style={{ fontWeight: 400 }}>— {card.name}</span>}</h2>
              {!params ? <p className="muted">Select a scorecard to see which parameters drag scores down.</p> : params.evaluations === 0 ? (
                <p className="muted">No completed evaluations for this version yet.</p>
              ) : (
                <ParamBars params={params} card={card} />
              )}
            </div>
            <div className="card">
              <h2>LLM judge vs human</h2>
              {!agreement || agreement.pairs === 0 ? (
                <p className="muted">Needs the same subject (reference) evaluated by both an LLM and a human on the same version.</p>
              ) : (
                <>
                  <div className="grid tiles">
                    <Tile value={String(agreement.pairs)} label="Paired subjects" />
                    <Tile value={`${agreement.mean_abs_diff_pct}%`} label="Mean |difference|" hint="% of scale; 10% = 1 point on 0–10" />
                    <Tile value={pct(agreement.within_tolerance_rate)} label={`Within ±${agreement.tolerance_pct}%`} />
                    <Tile value={pct(agreement.verdict_agreement_rate)} label="Same pass/fail verdict" />
                  </div>
                  <p className="small" style={{ marginTop: 10 }}>
                    Bias (LLM − human): <b>{agreement.mean_bias_pct_llm_minus_human > 0 ? "+" : ""}{agreement.mean_bias_pct_llm_minus_human}%</b>{" "}
                    {Math.abs(agreement.mean_bias_pct_llm_minus_human) >= 5 ? "— systematic; refine guidelines or judge prompt." : "— no strong systematic bias."}
                  </p>
                  <h3 style={{ marginTop: 12 }}>Largest disagreements</h3>
                  <table>
                    <thead><tr><th>Subject</th><th className="num">LLM</th><th className="num">Human</th><th className="num">Δ %</th></tr></thead>
                    <tbody>
                      {agreement.details.slice(0, 8).map((d: any) => (
                        <tr key={d.subject_ref}>
                          <td>{d.subject_name}<div className="small muted">{d.scorecard}</div></td>
                          <td className="num">{fmt(d.llm_score)}</td><td className="num">{fmt(d.human_score)}</td>
                          <td className="num">{d.diff_pct > 0 ? "+" : ""}{d.diff_pct}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </div>
          </div>
          {behaviour && behaviour.gates.decided > 0 && <Behaviour b={behaviour} />}
        </>
      )}
    </>
  );
}

function Behaviour({ b }: { b: any }) {
  const g = b.gates;
  return (
    <>
      <h2 style={{ marginTop: 22 }}>Quality gate behaviour</h2>
      <div className="grid tiles">
        <Tile value={String(g.decided)} label="Gate decisions" />
        <Tile value={pct(g.first_attempt_pass_rate)} label="Passed at first attempt" />
        <Tile value={`${g.passed} / ${g.redo}`} label="Passed / redo" />
        <Tile value={String(g.adjudicated)} label="Adjudicated disputes" hint="Judges disagreed beyond tolerance" />
        <Tile value={String(g.blocked_projects)} label="Foundational stops" />
      </div>
      <div className="grid two" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>QTC misses, tracked separately</h3>
          {g.qtc.n === 0 ? <p className="muted">No QTC scorecards decided yet.</p> : (
            <table>
              <tbody>
                <tr><td>Quality missed</td><td className="num">{g.qtc.quality_missed}</td></tr>
                <tr><td>Time missed</td><td className="num">{g.qtc.time_missed}</td></tr>
                <tr><td>Cost missed</td><td className="num">{g.qtc.cost_missed}</td></tr>
                <tr><td><b>Green (Q × T × C)</b></td><td className="num"><b>{g.qtc.green} / {g.qtc.n}</b></td></tr>
              </tbody>
            </table>
          )}
          <h3 style={{ marginTop: 16 }}>Guideline disputes: where judges differ most</h3>
          {b.disputed_parameters.length === 0 ? <p className="muted">Needs submissions with 2+ judges.</p> : (
            <table>
              <thead><tr><th>Parameter</th><th className="num">Mean spread</th><th className="num">Max</th><th className="num">n</th></tr></thead>
              <tbody>{b.disputed_parameters.map((d: any) => (
                <tr key={d.parameter_id}><td><span className="mono muted">{d.code}</span> {d.name}</td><td className="num">{d.mean_spread}</td><td className="num">{d.max_spread}</td><td className="num">{d.n}</td></tr>
              ))}</tbody>
            </table>
          )}
          <p className="hint" style={{ marginTop: 6 }}>High spread means the guideline allows interpretation: rewrite it until it doesn't.</p>
        </div>
        <div className="card">
          <h3>Self-appraisal honesty</h3>
          {b.self_appraisal.pairs === 0 ? <p className="muted">No decided submissions with a self-appraisal yet.</p> : (
            <>
              <p className="small">Self score minus the judges' official score, across {b.self_appraisal.pairs} submissions:
                <b> {b.self_appraisal.mean_gap_pct > 0 ? "+" : ""}{b.self_appraisal.mean_gap_pct}%</b> of scale ·
                same pass/fail verdict {pct(b.self_appraisal.verdict_match_rate)}</p>
              <table>
                <thead><tr><th>Person</th><th className="num">n</th><th className="num">Mean gap</th><th className="num">Verdict match</th></tr></thead>
                <tbody>{b.self_appraisal.people.map((p: any) => (
                  <tr key={p.person}><td>{p.person}</td><td className="num">{p.n}</td>
                    <td className="num" style={{ color: Math.abs(p.mean_gap_pct) >= 15 ? "var(--danger)" : undefined }}>{p.mean_gap_pct > 0 ? "+" : ""}{p.mean_gap_pct}%</td>
                    <td className="num">{pct(p.verdict_match_rate)}</td></tr>
                ))}</tbody>
              </table>
              <p className="hint" style={{ marginTop: 6 }}>A leading indicator (framework §11): people who cannot score their own work honestly struggle to apply any scorecard.</p>
            </>
          )}
        </div>
      </div>
    </>
  );
}

function ParamBars({ params, card }: { params: any; card?: ScorecardSummary }) {
  const depth = (code: string) => code.split(".").length - 1;
  void card;
  const maxAvg = Math.max(...params.parameters.map((p: any) => p.avg ?? 0), 1);
  return (
    <>
      <p className="small muted">{params.evaluations} completed evaluations. Bar = average score; red text = share scored below target.</p>
      <table>
        <thead><tr><th>Parameter</th><th className="num">Avg</th><th style={{ width: "30%" }} /><th className="num">Below target</th></tr></thead>
        <tbody>
          {params.parameters.map((p: any) => (
            <tr key={p.parameter_id}>
              <td style={{ paddingLeft: 8 + depth(p.code) * 14 }}>
                <span className="mono muted">{p.code}</span> {p.is_leaf ? p.name : <b>{p.name}</b>}
                {p.is_critical && <span className="tag crit" style={{ marginLeft: 4 }}>GATE</span>}
              </td>
              <td className="num">{fmt(p.avg)}</td>
              <td><div className="bar-track" title={`avg ${fmt(p.avg)} · min ${fmt(p.min)} · max ${fmt(p.max)} · n=${p.n}`}>
                <div className="bar-fill" style={{ width: `${((p.avg ?? 0) / maxAvg) * 100}%`, opacity: p.is_leaf ? 1 : 0.55 }} />
              </div></td>
              <td className="num" style={{ color: (p.below_target_rate ?? 0) > 0.3 ? "var(--danger)" : undefined }}>{pct(p.below_target_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {params.weakest_leaves.length > 0 && (
        <p className="small" style={{ marginTop: 10 }}>
          Weakest: {params.weakest_leaves.slice(0, 3).map((p: any) => `${p.code} ${p.name} (${fmt(p.avg)})`).join(" · ")}
        </p>
      )}
    </>
  );
}
