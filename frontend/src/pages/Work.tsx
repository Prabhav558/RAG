import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmt, SubjectNode, SubjectType } from "../api";
import { ErrorBox, Field, RollupPill, useActor } from "../components/common";

function flatten(nodes: SubjectNode[], depth = 0, out: { node: SubjectNode; depth: number }[] = []) {
  for (const n of nodes) {
    out.push({ node: n, depth });
    flatten(n.children, depth + 1, out);
  }
  return out;
}

export default function Work() {
  const [forest, setForest] = useState<SubjectNode[] | null>(null);
  const [types, setTypes] = useState<SubjectType[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const load = () => api.subjects().then(setForest).catch(setError);
  useEffect(() => { load(); api.subjectTypes().then(setTypes); }, []);
  const rows = forest ? flatten(forest) : [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Work</h1>
          <div className="sub">Projects, milestones and tasks, each gated by a scorecard. A parent is green only when everything beneath it is green.</div>
        </div>
        <button className="primary" onClick={() => setCreating(true)}>+ New subject</button>
      </div>
      <ErrorBox error={error} />
      {creating && <NewSubject types={types} parents={rows.map((r) => r.node)} onDone={() => { setCreating(false); load(); }} />}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        {forest === null ? <div className="empty">Loading…</div> : rows.length === 0 ? (
          <div className="empty">Nothing yet. Create a project, add tasks under it, and start submissions against published scorecards.</div>
        ) : (
          <table className="work-tree">
            <thead><tr><th>Subject</th><th>Type</th><th>Owner</th><th>Status</th><th>Latest decision</th><th>Beneath</th><th /></tr></thead>
            <tbody>
              {rows.map(({ node: n, depth }) => (
                <tr key={n.id}>
                  <td style={{ paddingLeft: 10 + depth * 22 }}>
                    <Link to={`/subjects/${n.id}`}>{depth === 0 ? <b>{n.name}</b> : n.name}</Link>
                  </td>
                  <td className="muted">{n.subject_type_name}</td>
                  <td>{n.owner}</td>
                  <td><RollupPill status={n.status} />{n.own_status !== n.status && n.own_status !== "not_started" && (
                    <div className="hint">own: {n.own_status.replace("_", " ")}</div>)}</td>
                  <td className="small">
                    {n.latest ? (
                      <Link to={`/submissions/${n.latest.submission_id}`}>
                        {n.latest.decision} · {fmt(n.latest.score)} {n.latest.band ? `(${n.latest.band})` : ""}
                      </Link>
                    ) : <span className="muted">—</span>}
                    {n.latest && <div className="hint">{n.latest.scorecard}</div>}
                  </td>
                  <td className="small">
                    {Object.entries(n.descendant_counts).map(([k, v]) => <span key={k} style={{ marginRight: 8 }}>{v} {k.replace("_", " ")}</span>)}
                  </td>
                  <td>{n.active_submission && <Link className="btn sm" to={`/submissions/${n.active_submission.id}`}>{n.active_submission.status.replace("_", " ")} →</Link>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function NewSubject({ types, parents, onDone }: { types: SubjectType[]; parents: SubjectNode[]; onDone: () => void }) {
  const actor = useActor();
  const [name, setName] = useState("");
  const [type, setType] = useState("task");
  const [parent, setParent] = useState("");
  const [owner, setOwner] = useState(actor);
  const [due, setDue] = useState("");
  const [budget, setBudget] = useState("");
  const [error, setError] = useState<unknown>(null);
  async function create() {
    try {
      await api.createSubject({
        name, subject_type: type, owner, parent_id: parent ? Number(parent) : null,
        due_at: due ? new Date(due).toISOString() : null, budget: budget === "" ? null : Number(budget),
      });
      onDone();
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <h2>New subject</h2>
      <ErrorBox error={error} />
      <div className="form-grid">
        <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        <Field label="Type">
          <select value={type} onChange={(e) => setType(e.target.value)}>{types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}</select>
        </Field>
        <Field label="Under">
          <select value={parent} onChange={(e) => setParent(e.target.value)}>
            <option value="">— top level —</option>
            {parents.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Owner"><input value={owner} onChange={(e) => setOwner(e.target.value)} /></Field>
        <Field label="Due (QTC time)"><input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
        <Field label="Budget (QTC cost)"><input type="number" min={0} value={budget} onChange={(e) => setBudget(e.target.value)} /></Field>
      </div>
      {!actor && <p className="hint">Set “Acting as” in the sidebar first: every change is recorded under a name.</p>}
      <div className="row">
        <button className="primary" disabled={!name.trim() || !owner.trim()} onClick={create}>Create</button>
        <button onClick={onDone}>Cancel</button>
      </div>
    </div>
  );
}
