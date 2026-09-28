import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, AttentionPerson, CapabilityRow, RiskRow, ScorecardSummary } from "../api";
import { ErrorBox, Field, useActor, when } from "../components/common";

const CAUSES = [
  ["skill", "Skill: good aptitude, has not learned the method yet", "train"],
  ["aptitude", "Aptitude: struggles even after training", "reassign"],
  ["will", "Will: capable but not willing", "discuss"],
  ["allocation", "Allocation: the task or team setup is wrong", "rescope"],
] as const;

export default function Attention() {
  const actor = useActor();
  const [data, setData] = useState<{ threshold: number; window_days: number; people: AttentionPerson[] } | null>(null);
  const [history, setHistory] = useState<Awaited<ReturnType<typeof api.diagnoses>>>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [cause, setCause] = useState("skill");
  const [action, setAction] = useState("train");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<unknown>(null);
  const load = () => { api.attention().then(setData).catch(setError); api.diagnoses().then(setHistory); };
  useEffect(load, []);


  async function record(person: string) {
    try {
      await api.recordDiagnosis({ person, cause, action, notes });
      setOpen(null);
      setNotes("");
      load();
    } catch (e) {
      setError(e);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Needs attention</h1>
          <div className="sub">
            A red is information, not blame. People with {data?.threshold ?? 3}+ reds in {data?.window_days ?? 90} days are listed until a lead
            records a diagnosis: skill, aptitude, will, or allocation. If everyone is red, the problem is the allocation, not the people.
          </div>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        {!data ? <div className="empty">Loading…</div> : data.people.length === 0 ? <div className="empty">No reds in the window.</div> : (
          <table>
            <thead><tr><th>Person</th><th className="num">Reds</th><th>Latest red</th><th>Work</th><th>Last diagnosis</th><th /></tr></thead>
            <tbody>
              {data.people.map((p) => (
                <Fragment key={p.person}>
                  <tr>
                    <td><b>{p.person}</b> {p.needs_diagnosis && <span className="chip fail">needs diagnosis</span>}</td>
                    <td className="num">{p.reds}</td>
                    <td className="small">{when(p.latest_red_at)}</td>
                    <td className="small">{p.subjects.slice(0, 3).join(", ")}{p.subjects.length > 3 ? ` +${p.subjects.length - 3}` : ""}</td>
                    <td className="small">{p.last_diagnosis ? `${p.last_diagnosis.cause} → ${p.last_diagnosis.action} (${p.last_diagnosis.by})` : "—"}</td>
                    <td><button className="sm" onClick={() => setOpen(open === p.person ? null : p.person)}>Diagnose</button></td>
                  </tr>
                  {open === p.person && (
                    <tr>
                      <td colSpan={6}>
                        <div className="form-grid">
                          <Field label="Cause">
                            <select value={cause} onChange={(e) => { setCause(e.target.value); setAction(CAUSES.find((c) => c[0] === e.target.value)![2]); }}>
                              {CAUSES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                            </select>
                          </Field>
                          <Field label="Action">
                            <select value={action} onChange={(e) => setAction(e.target.value)}>
                              {["train", "reassign", "discuss", "rescope", "none"].map((a) => <option key={a} value={a}>{a}</option>)}
                            </select>
                          </Field>
                        </div>
                        <Field label="Notes (facts, not conclusions)"><textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
                          placeholder="e.g. Needs C2 capability, is at C4; closing the gap takes ~18h; 8 free hours this week" /></Field>
                        <button className="primary" disabled={!actor} onClick={() => record(p.person)}>Record as {actor || "…"}</button>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {history.length > 0 && (
        <div className="card" style={{ marginTop: 14 }}>
          <h2>Diagnosis history</h2>
          <table>
            <thead><tr><th>When</th><th>Person</th><th>Cause</th><th>Action</th><th>Notes</th><th>By</th></tr></thead>
            <tbody>{history.map((d) => (
              <tr key={d.id}><td className="small">{when(d.recorded_at)}</td><td>{d.person}</td><td>{d.cause}</td><td>{d.action}</td><td className="small">{d.notes}</td><td>{d.recorded_by}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <RiskForecast />
      <Capabilities />
    </>
  );
}

const BAND_CLASS: Record<string, string> = { red: "fail", amber: "draft", green: "pass" };

function RiskForecast() {
  const [rows, setRows] = useState<RiskRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { api.riskForecast().then(setRows).catch(setError); }, []);
  return (
    <div className="card" style={{ marginTop: 14, padding: 0, overflowX: "auto" }}>
      <div style={{ padding: 16, paddingBottom: 0 }}>
        <h2>Risk forecast</h2>
        <p className="sub">
          Predictive: a risk score for every open submission, from signals already on record — overdue, over
          budget, a recent pattern of reds, a capability level below Competent, or a repeat attempt. Prescriptive:
          a recommended next action from the same vocabulary as diagnosis. No ML — every score is fully explained
          by its factors.
        </p>
      </div>
      <ErrorBox error={error} />
      {!rows ? <div className="empty">Loading…</div> : rows.length === 0 ? <div className="empty">No open submissions to forecast.</div> : (
        <table>
          <thead><tr><th>Subject</th><th>Scorecard</th><th>Owner</th><th className="num">Score</th><th>Factors</th><th>Recommended</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.submission_id}>
                <td><Link to={`/submissions/${r.submission_id}`}>{r.subject_name}</Link></td>
                <td className="muted">{r.scorecard}</td>
                <td>{r.owner}</td>
                <td className="num"><span className={`chip ${BAND_CLASS[r.band]}`}>{r.score}</span></td>
                <td className="small">{r.factors.length ? r.factors.map((f) => f.replace("_", " ")).join(", ") : "—"}</td>
                <td className="small">{r.recommended_action}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Capabilities() {
  const [rows, setRows] = useState<CapabilityRow[] | null>(null);
  const [cards, setCards] = useState<ScorecardSummary[]>([]);
  const [person, setPerson] = useState("");
  const [scorecard, setScorecard] = useState("");
  const [level, setLevel] = useState(3);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<unknown>(null);
  const actor = useActor();
  const load = () => api.capabilities().then(setRows).catch(setError);
  useEffect(() => { load(); api.scorecards().then(setCards); }, []);

  async function record() {
    try {
      await api.recordCapability({ person, scorecard, level, notes: notes || undefined });
      setPerson(""); setNotes("");
      load();
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h2>Capability &amp; competency</h2>
      <p className="sub">
        A person's assessed level for a scorecard's skill domain, C1 (unaware) through C6 (expert). Recorded by a
        lead, never by the person themselves — same rule as diagnosis. Only lead/admin see everyone's levels;
        everyone else sees only their own.
      </p>
      <ErrorBox error={error} />
      <div className="form-grid">
        <Field label="Person"><input value={person} onChange={(e) => setPerson(e.target.value)} placeholder="who this is about" /></Field>
        <Field label="Scorecard">
          <select value={scorecard} onChange={(e) => setScorecard(e.target.value)}>
            <option value="">Select…</option>
            {cards.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Level">
          <select value={level} onChange={(e) => setLevel(Number(e.target.value))}>
            {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>C{n} — {["Unaware", "Aware", "Developing", "Competent", "Proficient", "Expert"][n - 1]}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Notes"><textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <button className="primary" disabled={!actor || !person.trim() || !scorecard} onClick={record}>Record as {actor || "…"}</button>

      {rows && rows.length > 0 && (
        <table style={{ marginTop: 14 }}>
          <thead><tr><th>When</th><th>Person</th><th>Scorecard</th><th>Level</th><th>Notes</th><th>By</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="small">{when(r.set_at)}</td>
                <td>{r.person}</td>
                <td className="muted">{r.scorecard_name}</td>
                <td><span className="chip neutral">C{r.level} — {r.level_label}</span></td>
                <td className="small">{r.notes}</td>
                <td>{r.set_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
