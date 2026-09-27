import { Fragment, useEffect, useState } from "react";
import { api, AttentionPerson } from "../api";
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
    </>
  );
}
