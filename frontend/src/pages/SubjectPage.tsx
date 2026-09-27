import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fmt, ScorecardSummary, SubjectDetail } from "../api";
import { ErrorBox, Field, RollupPill, SUBMISSION_LABEL, when } from "../components/common";

export default function SubjectPage() {
  const { subjectId } = useParams();
  const id = Number(subjectId);
  const nav = useNavigate();
  const [s, setS] = useState<SubjectDetail | null>(null);
  const [cards, setCards] = useState<ScorecardSummary[]>([]);
  const [versionId, setVersionId] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState(false);
  const load = useCallback(() => api.subject(id).then(setS).catch(setError), [id]);
  useEffect(() => { load(); api.scorecards().then(setCards); }, [load]);
  if (!s) return <>{error ? <ErrorBox error={error} /> : <div className="empty">Loading…</div>}</>;

  const published = cards.flatMap((c) => c.versions.filter((v) => v.status === "published").map((v) => ({ c, v })));

  async function start() {
    try {
      const sub = await api.startSubmission(id, { version_id: Number(versionId) });
      nav(`/submissions/${sub.id}`);
    } catch (e) {
      setError(e);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="row small muted"><Link to="/work">Work</Link>{s.path.map((p) => <span key={p.id}>/ <Link to={`/subjects/${p.id}`}>{p.name}</Link></span>)}</div>
          <h1>{s.name}</h1>
          <div className="row">
            <RollupPill status={s.status} />
            <span className="chip neutral">{s.subject_type_name}</span>
            <span className="small muted">owner <b>{s.owner}</b></span>
          </div>
        </div>
        <button onClick={() => setEditing(!editing)}>Edit details</button>
      </div>
      <ErrorBox error={error} />
      {s.blocked_by.length > 0 && (
        <div className="alert error">
          ⛔ The project is stopped by a foundational red: {s.blocked_by.map((b) => <Link key={b.id} to={`/subjects/${b.id}`}>{b.name} </Link>)}.
          Nothing else in it can start until that is fixed.
        </div>
      )}
      {editing && <EditSubject s={s} onDone={() => { setEditing(false); load(); }} />}

      <div className="grid two">
        <div className="card">
          <h2>Start a submission</h2>
          <p className="hint">A submission is one attempt at getting this work through a scorecard: self-appraisal → submit → independent judges → gate decision.</p>
          <Field label="Published scorecard">
            <select value={versionId} onChange={(e) => setVersionId(e.target.value)}>
              <option value="">Select…</option>
              {published.map(({ c, v }) => <option key={v.id} value={v.id}>{c.name} (v{v.version_no})</option>)}
            </select>
          </Field>
          <button className="primary" disabled={!versionId} onClick={start}>Start</button>
          <dl className="kv" style={{ marginTop: 14 }}>
            <dt>Due</dt><dd>{when(s.due_at)}</dd>
            <dt>Budget</dt><dd>{s.budget ?? "—"}</dd>
            <dt>Beneath</dt><dd>{Object.entries(s.descendant_counts).map(([k, v]) => `${v} ${k.replace("_", " ")}`).join(" · ") || "—"}</dd>
          </dl>
        </div>
        <div className="card" style={{ overflowX: "auto" }}>
          <h2>Submissions</h2>
          {s.submissions.length === 0 ? <p className="muted">None yet.</p> : (
            <table>
              <thead><tr><th>#</th><th>Scorecard</th><th>Status</th><th>Decision</th><th className="num">Score</th><th>Decided</th></tr></thead>
              <tbody>
                {s.submissions.map((x) => (
                  <tr key={x.id} className="clickable" onClick={() => nav(`/submissions/${x.id}`)}>
                    <td>{x.attempt_no}</td>
                    <td>{x.scorecard} <span className="muted small">v{x.version_no}</span></td>
                    <td>{SUBMISSION_LABEL[x.status]}{x.adjudicated && <span className="tag" style={{ marginLeft: 4 }}>ADJ</span>}</td>
                    <td>{x.decision ? <span className={`chip ${x.decision === "passed" ? "pass" : "fail"}`}>{x.decision}</span> : "—"}
                      {x.blocks_project && <span className="tag crit" style={{ marginLeft: 4 }}>STOPS PROJECT</span>}</td>
                    <td className="num">{fmt(x.official_score)}</td>
                    <td className="small muted">{when(x.decided_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      {s.children.length > 0 && (
        <div className="card" style={{ marginTop: 14 }}>
          <h2>Beneath this</h2>
          <table>
            <tbody>
              {s.children.map((c) => (
                <tr key={c.id}><td><Link to={`/subjects/${c.id}`}>{c.name}</Link></td><td className="muted">{c.subject_type_name}</td><td>{c.owner}</td><td><RollupPill status={c.status} /></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function EditSubject({ s, onDone }: { s: SubjectDetail; onDone: () => void }) {
  const [owner, setOwner] = useState(s.owner);
  const [due, setDue] = useState(s.due_at ? s.due_at.slice(0, 16) : "");
  const [budget, setBudget] = useState(s.budget === null ? "" : String(s.budget));
  const [error, setError] = useState<unknown>(null);
  async function save() {
    try {
      await api.updateSubject(s.id, { owner, due_at: due ? new Date(due).toISOString() : null, budget: budget === "" ? null : Number(budget) });
      onDone();
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <ErrorBox error={error} />
      <div className="form-grid">
        <Field label="Owner"><input value={owner} onChange={(e) => setOwner(e.target.value)} /></Field>
        <Field label="Due"><input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
        <Field label="Budget"><input type="number" value={budget} onChange={(e) => setBudget(e.target.value)} /></Field>
      </div>
      <div className="row"><button className="primary" onClick={save}>Save</button><button onClick={onDone}>Cancel</button></div>
    </div>
  );
}
