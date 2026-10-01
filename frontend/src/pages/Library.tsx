import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Scale, ScorecardDefinition, ScorecardSummary, SubjectType } from "../api";
import { ErrorBox, Field, StatusChip } from "../components/common";

function slug(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
}

export default function Library() {
  const [cards, setCards] = useState<ScorecardSummary[] | null>(null);
  const [types, setTypes] = useState<SubjectType[]>([]);
  const [filter, setFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [cloning, setCloning] = useState<ScorecardSummary | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = () => api.scorecards().then(setCards).catch(setError);
  useEffect(() => {
    load();
    api.subjectTypes().then(setTypes);
  }, []);

  async function remove(c: ScorecardSummary) {
    const kept = c.evaluation_count > 0 ? ` Its ${c.evaluation_count} past evaluation${c.evaluation_count > 1 ? "s are" : " is"} kept.` : "";
    if (!window.confirm(`Delete the scorecard "${c.name}"? It will disappear from the library.${kept}`)) return;
    setError(null);
    try {
      await api.archiveScorecard(c.id);
      await load();
    } catch (e) {
      setError(e);
    }
  }

  const shown = (cards ?? []).filter((c) => !filter || c.subject_type === filter);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Scorecard library</h1>
          <div className="sub">Design scorecards for any subject, then use them to rate work consistently.</div>
        </div>
        <div className="row">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 180 }} aria-label="Filter by subject type">
            <option value="">All subject types</option>
            {types.map((t) => (
              <option key={t.code} value={t.code}>{t.name}</option>
            ))}
          </select>
          <button className="primary" onClick={() => setCreating(true)}>+ New scorecard</button>
        </div>
      </div>
      <ErrorBox error={error} />
      {creating && <CreateDialog types={types} onClose={() => setCreating(false)} onTypesChanged={setTypes} />}
      {cloning && <CloneDialog source={cloning} onClose={() => setCloning(null)} />}
      {cards === null ? (
        <div className="empty">Loading…</div>
      ) : shown.length === 0 ? (
        <div className="empty">No scorecards yet. Create one, or run <span className="mono">python data/tools/ingest.py</span> to load the reference library.</div>
      ) : (
        <div className="grid cards">
          {shown.map((c) => {
            const published = [...c.versions].reverse().find((v) => v.status === "published");
            const draft = c.versions.find((v) => v.status === "draft" || v.status === "in_review");
            return (
              <div className="card" key={c.id}>
                <div className="row" style={{ marginBottom: 6 }}>
                  <span className="chip neutral">{c.subject_type_name}</span>
                  {c.is_template && <span className="chip neutral">Template</span>}
                  <span className="spacer" />
                  {published && <StatusChip status={`published`} />}
                  {draft && <StatusChip status="draft" />}
                  {c.versions.some((v) => v.status === "in_review") && <StatusChip status="in_review" />}
                </div>
                <h2 style={{ marginBottom: 6 }}>{c.name}</h2>
                <p className="muted small" style={{ minHeight: 38 }}>{c.purpose || "No purpose stated yet."}</p>
                <div className="small muted" style={{ marginBottom: 10 }}>
                  {c.parameter_count} parameters · {c.leaf_count} rated · {c.depth} level{c.depth === 1 ? "" : "s"} ·{" "}
                  {c.evaluation_count} evaluations · v{c.versions[c.versions.length - 1].version_no}
                </div>
                <div className="row">
                  {published && (
                    <Link className="btn primary sm" to={`/evaluate?version=${published.id}`}>Evaluate</Link>
                  )}
                  <Link className="btn sm" to={`/versions/${(draft ?? published ?? c.versions[c.versions.length - 1]).id}`}>
                    {draft ? "Edit draft" : "View / edit"}
                  </Link>
                  <button className="sm" onClick={() => setCloning(c)}>Clone</button>
                  <Link className="btn sm" to={`/evaluations?scorecard=${c.id}`}>Results</Link>
                  <span className="spacer" />
                  <button className="sm ghost danger" onClick={() => remove(c)} aria-label={`Delete ${c.name}`}>Delete</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

function CreateDialog({ types, onClose, onTypesChanged }: {
  types: SubjectType[]; onClose: () => void; onTypesChanged: (t: SubjectType[]) => void;
}) {
  const nav = useNavigate();
  const [scales, setScales] = useState<Scale[]>([]);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("task");
  const [newType, setNewType] = useState("");
  const [scale, setScale] = useState("0-10-rag");
  const [target, setTarget] = useState(8);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { api.scales().then(setScales); }, []);
  const sc = scales.find((s) => s.code === scale);

  async function submit() {
    setError(null);
    try {
      let subjectCode = subject;
      if (subject === "__new") {
        const st = await api.createSubjectType({ code: slug(newType).replace(/-/g, "_"), name: newType });
        onTypesChanged([...types, st]);
        subjectCode = st.code;
      }
      const d: ScorecardDefinition = {
        code: slug(name) || `scorecard-${Date.now()}`,
        name,
        subject_type: subjectCode,
        tags: [],
        is_template: false,
        version: {
          purpose: "", scope: "", objective: "", guidance: "", rating_scale: scale, target_score: target,
          aggregation: "weighted_mean", max_depth: 4, qtc_enabled: false, parameters: [],
          required_judges: 1, judge_tolerance_pct: 10, require_self_appraisal: false, is_foundational: false,
        },
      };
      const card = await api.createScorecard(d);
      nav(`/versions/${card.versions[0].id}`);
    } catch (e) {
      setError(e);
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h2>New scorecard</h2>
      <ErrorBox error={error} />
      <div className="form-grid">
        <Field label="Name"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sales Proposal Quality" autoFocus /></Field>
        <Field label="What will it score?">
          <select value={subject} onChange={(e) => setSubject(e.target.value)}>
            {types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
            <option value="__new">+ New subject type…</option>
          </select>
        </Field>
        {subject === "__new" && (
          <Field label="New subject type"><input value={newType} onChange={(e) => setNewType(e.target.value)} placeholder="e.g. Vendor" /></Field>
        )}
        <Field label="Rating scale">
          <select value={scale} onChange={(e) => {
            setScale(e.target.value);
            const s = scales.find((x) => x.code === e.target.value);
            if (s) setTarget(Math.round(s.min_value + (s.max_value - s.min_value) * 0.8));
          }}>
            {scales.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Target score" hint={sc ? `Scale ${sc.min_value}–${sc.max_value}` : ""}>
          <input type="number" value={target} onChange={(e) => setTarget(Number(e.target.value))} />
        </Field>
      </div>
      <div className="row">
        <button className="primary" disabled={!name.trim() || (subject === "__new" && !newType.trim())} onClick={submit}>Create draft</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}

function CloneDialog({ source, onClose }: { source: ScorecardSummary; onClose: () => void }) {
  const nav = useNavigate();
  const [name, setName] = useState(`${source.name} (copy)`);
  const [error, setError] = useState<unknown>(null);
  async function submit() {
    try {
      const c = await api.cloneScorecard(source.id, { code: slug(name), name });
      nav(`/versions/${c.versions[0].id}`);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h2>Clone “{source.name}”</h2>
      <p className="muted small">Starts a new draft scorecard from the latest version. Understand the intent of the reference — adapt it, don't copy it blindly.</p>
      <ErrorBox error={error} />
      <Field label="New name"><input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
      <div className="row">
        <button className="primary" onClick={submit} disabled={!name.trim()}>Clone</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}
