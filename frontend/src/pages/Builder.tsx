import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api, Criterion, Issue, MetricDef, ParamDef, Scale, ScorecardDefinition, ScorecardSummary, SubjectType, VersionView,
} from "../api";
import AiAssist, { AssistTarget } from "../components/AiAssist";
import { ErrorBox, Field, ScaleLegend, StatusChip } from "../components/common";

let keySeq = 0;
const newKey = () => `k${++keySeq}`;

function withKeys(ps: ParamDef[]): ParamDef[] {
  return ps.map((p) => ({ ...p, _key: newKey(), children: withKeys(p.children) }));
}

function mapTree(ps: ParamDef[], key: string, fn: (p: ParamDef) => ParamDef | null): ParamDef[] {
  const out: ParamDef[] = [];
  for (const p of ps) {
    if (p._key === key) {
      const r = fn(p);
      if (r) out.push(r);
    } else out.push({ ...p, children: mapTree(p.children, key, fn) });
  }
  return out;
}

function findPath(ps: ParamDef[], key: string, trail: ParamDef[] = []): ParamDef[] | null {
  for (const p of ps) {
    if (p._key === key) return [...trail, p];
    const r = findPath(p.children, key, [...trail, p]);
    if (r) return r;
  }
  return null;
}

function allCodes(ps: ParamDef[]): string[] {
  return ps.flatMap((p) => [p.code, ...allCodes(p.children)]);
}

function nextCode(parent: ParamDef | null, siblings: ParamDef[], used: string[]): string {
  let i = siblings.length + 1;
  const make = (n: number) => (parent ? `${parent.code}.${n}` : String(n));
  while (used.includes(make(i))) i++;
  return make(i);
}

/** Give a proposed hierarchy fresh codes ("4", "4.1", ...) that cannot collide with what is already in the builder. */
function renumber(ps: ParamDef[], prefix: string, start: number): ParamDef[] {
  return ps.map((p, i) => {
    const code = prefix ? `${prefix}.${start + i}` : String(start + i);
    return { ...p, code, children: renumber(p.children, code, 1) };
  });
}

function blankParam(code: string): ParamDef {
  return {
    _key: newKey(), code, name: "New parameter", description: "", weight: 1, aggregation: "weighted_mean",
    is_critical: false, min_acceptable_score: null, is_optional: false, criteria: [], metrics: [], children: [],
  };
}

function share(siblings: ParamDef[], p: ParamDef) {
  const total = siblings.reduce((s, x) => s + x.weight, 0);
  return total > 0 ? p.weight / total : 1 / siblings.length;
}

function globalShares(ps: ParamDef[], parentShare = 1, acc: Record<string, number> = {}) {
  for (const p of ps) {
    acc[p._key!] = parentShare * share(ps, p);
    globalShares(p.children, acc[p._key!], acc);
  }
  return acc;
}

function issuesFor(issues: Issue[], code: string) {
  return issues.filter((i) => i.path && (i.path.endsWith(`/${code}`) || i.path.includes(`/${code}#`)));
}

export default function Builder() {
  const { versionId } = useParams();
  const vid = Number(versionId);
  const nav = useNavigate();
  const [def, setDef] = useState<ScorecardDefinition | null>(null);
  const [view, setView] = useState<VersionView | null>(null);
  const [card, setCard] = useState<ScorecardSummary | null>(null);
  const [scales, setScales] = useState<Scale[]>([]);
  const [types, setTypes] = useState<SubjectType[]>([]);
  const [tab, setTab] = useState<"basics" | "params" | "review">("basics");
  const [selected, setSelected] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [assistOpen, setAssistOpen] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    const [d, v, s, t] = await Promise.all([api.definition(vid), api.version(vid), api.scales(), api.subjectTypes()]);
    d.version.parameters = withKeys(d.version.parameters);
    setDef(d);
    setView(v);
    setScales(s);
    setTypes(t);
    setCard(await api.scorecard(v.scorecard_id));
    setDirty(false);
    if (!d.version.purpose) setTab("basics");
  }, [vid]);

  useEffect(() => { load().catch(setError); }, [load]);

  // live validation (debounced)
  const timer = useRef<number>();
  useEffect(() => {
    if (!def) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      api.validateDefinition(def.version).then(setIssues).catch(() => undefined);
    }, 400);
  }, [def]);

  const readOnly = view?.status !== "draft";
  const scale = scales.find((s) => s.code === def?.version.rating_scale);
  const shares = useMemo(() => (def ? globalShares(def.version.parameters) : {}), [def]);
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");

  if (!def || !view) return <>{error ? <ErrorBox error={error} /> : <div className="empty">Loading…</div>}</>;

  const setVersion = (patch: Partial<ScorecardDefinition["version"]>) => {
    setDef({ ...def, version: { ...def.version, ...patch } });
    setDirty(true);
  };
  const setParams = (parameters: ParamDef[]) => setVersion({ parameters });
  const updateParam = (key: string, patch: Partial<ParamDef>) =>
    setParams(mapTree(def.version.parameters, key, (p) => ({ ...p, ...patch })));

  async function save(): Promise<boolean> {
    if (!def || !card) return false;
    setBusy(true);
    setError(null);
    try {
      if (def.name !== card.name || def.subject_type !== card.subject_type || def.owner !== card.owner) {
        setCard(await api.updateScorecardMeta(card.id, { name: def.name, subject_type: def.subject_type, owner: def.owner ?? null }));
      }
      const r = await api.saveDraft(vid, def.version);
      setView(r.version);
      setIssues(r.issues);
      setDirty(false);
      setNotice("Draft saved");
      window.setTimeout(() => setNotice(null), 2500);
      return true;
    } catch (e) {
      setError(e);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (dirty && !(await save())) return;
    setBusy(true);
    try {
      await api.publish(vid);
      await load();
      setNotice("Published. This version is now frozen and available for evaluations.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function newVersion() {
    const note = window.prompt("What will change in the new version? (optional)") ?? undefined;
    try {
      const v = await api.newDraft(vid, note || undefined);
      nav(`/versions/${v.id}`);
    } catch (e) {
      setError(e);
    }
  }

  async function discardDraft() {
    if (!window.confirm("Delete this draft version? This cannot be undone.")) return;
    try {
      await api.deleteDraft(vid);
      nav("/");
    } catch (e) {
      setError(e);
    }
  }

  function exportJson() {
    const clean = JSON.parse(JSON.stringify(def, (k, v) => (k === "_key" ? undefined : v)));
    const blob = new Blob([JSON.stringify(clean, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${def!.code}-v${view!.version_no}.json`;
    a.click();
  }

  function applyAssist(proposed: ParamDef[], mode: "add" | "replace", parentKey: string | null = null) {
    const parent = parentKey ? findPath(def!.version.parameters, parentKey)?.slice(-1)[0] : undefined;
    if (parent) {
      // one drafted sub-parameter (or more) goes under an existing parameter, which becomes a roll-up
      const last = Math.max(0, ...parent.children.map((c) => Number(c.code.split(".").pop()) || 0));
      const start = Math.max(parent.children.length, last) + 1;
      const fresh = withKeys(renumber(proposed, parent.code, start));
      setParams(mapTree(def!.version.parameters, parent._key!, (p) => ({
        ...p, children: [...p.children, ...fresh], criteria: [], metrics: [],
      })));
      setSelected(fresh[0]?._key ?? null);
      setNotice(`AI Assist: added '${fresh[0]?.name}' under ${parent.code} ${parent.name}. Review, then save.`);
    } else {
      const base = mode === "replace" ? [] : def!.version.parameters;
      const start = Math.max(base.length, ...base.map((p) => Number(p.code) || 0)) + 1;
      const fresh = withKeys(renumber(proposed, "", start));
      setParams([...base, ...fresh]);
      setSelected(fresh[0]?._key ?? null);
      setNotice(`AI Assist: ${mode === "replace" ? "replaced with" : "added"} ${fresh.length} KPI${fresh.length > 1 ? "s" : ""}. Review, then save.`);
    }
    window.setTimeout(() => setNotice(null), 4000);
  }

  const assistTargets = (() => {
    const out: AssistTarget[] = [];
    const walk = (ps: ParamDef[], depth: number) => ps.forEach((p) => {
      out.push({ key: p._key!, code: p.code, name: p.name, depth, hasContent: p.children.length === 0 && (p.criteria.some((c) => c.qualitative.trim() || c.quantitative?.trim()) || p.metrics.length > 0) });
      walk(p.children, depth + 1);
    });
    walk(def.version.parameters, 1);
    return out;
  })();

  const selPath = selected ? findPath(def.version.parameters, selected) : null;
  const selNode = selPath ? selPath[selPath.length - 1] : null;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="row small muted"><Link to="/">Library</Link> / {card?.name}</div>
          <h1>{def.name} <span className="muted" style={{ fontWeight: 400 }}>v{view.version_no}</span></h1>
          <div className="row">
            <StatusChip status={view.status} />
            <span className="chip neutral">{types.find((t) => t.code === def.subject_type)?.name}</span>
            {card && card.versions.length > 1 && (
              <select
                value={vid}
                onChange={(e) => nav(`/versions/${e.target.value}`)}
                style={{ width: "auto", padding: "2px 6px" }}
                aria-label="Switch version"
              >
                {card.versions.map((v) => <option key={v.id} value={v.id}>v{v.version_no} · {v.status}</option>)}
              </select>
            )}
          </div>
        </div>
        <div className="row">
          {notice && <span className="chip pass">{notice}</span>}
          <button onClick={exportJson}>Export JSON</button>
          {readOnly ? (
            <>
              {view.status === "published" && <Link className="btn primary" to={`/evaluate?version=${vid}`}>Evaluate with this</Link>}
              {view.status === "published" && (
                <button onClick={async () => {
                  const r = window.prompt("Why retire this version? New evaluations will no longer be possible.");
                  if (r) { try { await api.retire(vid, r); await load(); } catch (e) { setError(e); } }
                }}>Retire</button>
              )}
              {!card?.versions.some((v) => v.status === "draft" || v.status === "in_review") ? (
                <button onClick={newVersion}>Create new version</button>
              ) : (
                <Link className="btn" to={`/versions/${card.versions.find((v) => v.status === "draft" || v.status === "in_review")!.id}`}>Open draft</Link>
              )}
            </>
          ) : (
            <>
              <button className="danger" onClick={discardDraft}>Delete draft</button>
              <button onClick={save} disabled={busy || !dirty}>{dirty ? "Save draft" : "Saved"}</button>
              {card?.requires_review ? (
                <button className="primary" onClick={() => setTab("review")}>Review & approval →</button>
              ) : (
                <button className="primary" onClick={publish} disabled={busy || errors.length > 0} title={errors.length ? "Fix validation errors first" : ""}>
                  Publish
                </button>
              )}
            </>
          )}
        </div>
      </div>
      {readOnly && (
        <div className="alert warn">
          This version is <b>{view.status}</b> and frozen, so past evaluations stay reproducible. Create a new version to make changes.
        </div>
      )}
      <ErrorBox error={error} />

      <div className="tabs" role="tablist">
        <button className={tab === "basics" ? "active" : ""} onClick={() => setTab("basics")}>1. Purpose & scope</button>
        <button className={tab === "params" ? "active" : ""} onClick={() => setTab("params")}>
          2. Parameters & rating matrix ({allCodes(def.version.parameters).length})
        </button>
        <button className={tab === "review" ? "active" : ""} onClick={() => setTab("review")}>
          3. Review & publish {errors.length > 0 && <span className="tag err">{errors.length}</span>}
        </button>
      </div>

      <fieldset disabled={readOnly} style={{ border: "none", padding: 0, margin: 0 }}>
        {tab === "basics" && (
          <div className="grid two">
            <div className="card">
              <h2>Identity</h2>
              <Field label="Scorecard name"><input value={def.name} onChange={(e) => { setDef({ ...def, name: e.target.value }); setDirty(true); }} /></Field>
              <div className="form-grid">
                <Field label="Subject type (what is scored)">
                  <select value={def.subject_type} onChange={(e) => { setDef({ ...def, subject_type: e.target.value }); setDirty(true); }}>
                    {types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
                  </select>
                </Field>
                <Field label="Owner"><input value={def.owner ?? ""} onChange={(e) => { setDef({ ...def, owner: e.target.value }); setDirty(true); }} /></Field>
              </div>
              <Field label="Purpose — why does this scorecard exist?" hint="One or two statements. Required to publish.">
                <textarea value={def.version.purpose} onChange={(e) => setVersion({ purpose: e.target.value })} rows={3} />
              </Field>
              <Field label="Scope — what is covered, and what is not?">
                <textarea value={def.version.scope} onChange={(e) => setVersion({ scope: e.target.value })} rows={3} />
              </Field>
              <Field label="Assessment / quality objective — what does 'good enough' mean?" hint="Required to publish.">
                <textarea value={def.version.objective} onChange={(e) => setVersion({ objective: e.target.value })} rows={3} />
              </Field>
              <Field label="Scoring guidance (manual for judges)">
                <textarea value={def.version.guidance ?? ""} onChange={(e) => setVersion({ guidance: e.target.value })} rows={3} />
              </Field>
            </div>
            <div className="card">
              <h2>Rating mechanism</h2>
              <div className="form-grid">
                <Field label="Rating scale">
                  <select value={def.version.rating_scale} onChange={(e) => setVersion({ rating_scale: e.target.value })}>
                    {scales.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                  </select>
                </Field>
                <Field label="Target score" hint="Pass mark. Set it for the context: 10 foundational, 8 standard, 6–7 POC.">
                  <input type="number" step="0.5" value={def.version.target_score} onChange={(e) => setVersion({ target_score: Number(e.target.value) })} />
                </Field>
                <Field label="Final score roll-up">
                  <select value={def.version.aggregation} onChange={(e) => setVersion({ aggregation: e.target.value as "weighted_mean" | "minimum" })}>
                    <option value="weighted_mean">Weighted average</option>
                    <option value="minimum">Minimum (weakest area decides)</option>
                  </select>
                </Field>
                <Field label="Max hierarchy depth">
                  <select value={def.version.max_depth} onChange={(e) => setVersion({ max_depth: Number(e.target.value) })}>
                    {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>Level {n}</option>)}
                  </select>
                </Field>
              </div>
              <label className="check" style={{ marginBottom: 10 }}>
                <input type="checkbox" checked={def.version.qtc_enabled} onChange={(e) => setVersion({ qtc_enabled: e.target.checked })} />
                Apply the QTC rule (green = Quality AND Time AND Cost met)
              </label>
              <h3 style={{ marginTop: 12 }}>Quality gate (submissions)</h3>
              <div className="form-grid">
                <Field label="Independent judges required">
                  <select value={def.version.required_judges} onChange={(e) => setVersion({ required_judges: Number(e.target.value) })}>
                    {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </Field>
                <Field label="Judge disagreement tolerance (% of scale)" hint="Wider spread → adjudication">
                  <input type="number" min={0} max={100} value={def.version.judge_tolerance_pct} onChange={(e) => setVersion({ judge_tolerance_pct: Number(e.target.value) })} />
                </Field>
              </div>
              <label className="check" style={{ display: "flex", marginBottom: 6 }}>
                <input type="checkbox" checked={def.version.require_self_appraisal} onChange={(e) => setVersion({ require_self_appraisal: e.target.checked })} />
                Owner must self-appraise before submitting
              </label>
              <label className="check" style={{ display: "flex", marginBottom: 6 }}>
                <input type="checkbox" checked={def.version.is_foundational} onChange={(e) => setVersion({ is_foundational: e.target.checked })} />
                Foundational: a dark-red result stops the whole project
              </label>
              {view.version_no > 1 && (
                <Field label="Change note for this version">
                  <input value={def.version.change_note ?? ""} onChange={(e) => setVersion({ change_note: e.target.value })} />
                </Field>
              )}
              {scale && (
                <>
                  <h3 style={{ marginTop: 12 }}>Bands on this scale</h3>
                  <ScaleLegend scale={scale} />
                  <p className="small muted" style={{ marginTop: 8 }}>
                    Scores are never rounded up into a better band: 7.99 is not 8.
                  </p>
                </>
              )}
            </div>
          </div>
        )}

        {tab === "params" && scale && !readOnly && (
          <div className="row" style={{ marginBottom: 10 }}>
            <button className="primary" type="button" onClick={() => setAssistOpen((o) => !o)}>✨ AI Assist</button>
            <span className="small muted">Describe the KPIs you want and let AI draft the rating matrix.</span>
          </div>
        )}
        {tab === "params" && scale && (
          <div className="builder">
            <div className="card">
              <div className="row" style={{ marginBottom: 8 }}>
                <h2 style={{ margin: 0 }}>Hierarchy</h2>
                <span className="spacer" />
                <button className="sm" onClick={() => {
                  const p = blankParam(nextCode(null, def.version.parameters, allCodes(def.version.parameters)));
                  setParams([...def.version.parameters, p]);
                  setSelected(p._key!);
                }}>+ Level-1 KPI</button>
              </div>
              {def.version.parameters.length === 0 ? (
                <p className="muted small">Start with 5–6 top-level KPIs. Break each down into sub-parameters where it helps judging.</p>
              ) : (
                <Tree nodes={def.version.parameters} selected={selected} onSelect={setSelected} shares={shares} issues={issues} />
              )}
              <p className="small muted" style={{ marginTop: 10 }}>
                Weights are relative to siblings; % is the share of the final score. Only leaves are rated — parents are rolled up.
              </p>
            </div>
            <div>
              {selNode && selPath ? (
                <NodeEditor
                  key={selNode._key}
                  node={selNode}
                  path={selPath}
                  siblings={selPath.length > 1 ? selPath[selPath.length - 2].children : def.version.parameters}
                  globalShare={shares[selNode._key!]}
                  maxDepth={def.version.max_depth}
                  scale={scale}
                  issues={issuesFor(issues, selNode.code)}
                  readOnly={readOnly}
                  onChange={(patch) => updateParam(selNode._key!, patch)}
                  onAddChild={() => {
                    const c = blankParam(nextCode(selNode, selNode.children, allCodes(def.version.parameters)));
                    updateParam(selNode._key!, { children: [...selNode.children, c], criteria: [], metrics: [] });
                    setSelected(c._key!);
                  }}
                  onDelete={() => {
                    if (!window.confirm(`Delete '${selNode.name}' and everything beneath it?`)) return;
                    setParams(mapTree(def.version.parameters, selNode._key!, () => null));
                    setSelected(null);
                  }}
                  onMove={(dir) => {
                    const parent = selPath.length > 1 ? selPath[selPath.length - 2] : null;
                    const sibs = [...(parent ? parent.children : def.version.parameters)];
                    const i = sibs.findIndex((s) => s._key === selNode._key);
                    const j = i + dir;
                    if (j < 0 || j >= sibs.length) return;
                    [sibs[i], sibs[j]] = [sibs[j], sibs[i]];
                    if (parent) updateParam(parent._key!, { children: sibs });
                    else setParams(sibs);
                  }}
                />
              ) : (
                <div className="card empty">Select a parameter to edit it, or add a Level-1 KPI.</div>
              )}
            </div>
          </div>
        )}
      </fieldset>

      {tab === "params" && assistOpen && !readOnly && (
        <AiAssist
          version={def.version} name={def.name} subjectType={def.subject_type}
          targets={assistTargets}
          onApply={applyAssist} onClose={() => setAssistOpen(false)}
        />
      )}

      {tab === "review" && (
        <div className="grid two">
          <div className="card">
            <h2>Validation</h2>
            {errors.length === 0 ? (
              <div className="alert ok">No blocking errors{readOnly ? "" : " — ready to publish"}.</div>
            ) : (
              <div className="alert error">
                {errors.length} error{errors.length > 1 ? "s" : ""} must be fixed before publishing:
                <ul>{errors.map((i, n) => <li key={n}>[{i.code}] {i.path ? `${i.path}: ` : ""}{i.message}</li>)}</ul>
              </div>
            )}
            {warnings.length > 0 && (
              <div className="alert warn">
                Advisory:
                <ul>{warnings.map((i, n) => <li key={n}>[{i.code}] {i.path ? `${i.path}: ` : ""}{i.message}</li>)}</ul>
              </div>
            )}
            <dl className="kv">
              <dt>Purpose</dt><dd>{def.version.purpose || <span className="muted">—</span>}</dd>
              <dt>Objective</dt><dd>{def.version.objective || <span className="muted">—</span>}</dd>
              <dt>Target</dt><dd>{def.version.target_score} on {scale?.name}</dd>
              <dt>QTC rule</dt><dd>{def.version.qtc_enabled ? "Applied" : "Not applied"}</dd>
            </dl>
          </div>
          <div>
            <ReviewPanel vid={vid} view={view} requiresReview={!!card?.requires_review} dirty={dirty} errors={errors.length}
              onChanged={async () => { await load(); }} onError={setError}
              onToggleReview={async (on) => { if (card) setCard(await api.updateScorecardMeta(card.id, { requires_review: on })); }} />
            <div className="card" style={{ marginTop: 14 }}>
              <h2>Weight distribution (rated parameters)</h2>
              <WeightTable params={def.version.parameters} shares={shares} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Tree({ nodes, selected, onSelect, shares, issues }: {
  nodes: ParamDef[]; selected: string | null; onSelect: (k: string) => void; shares: Record<string, number>; issues: Issue[];
}) {
  return (
    <ul className="tree">
      {nodes.map((n) => {
        const errs = issuesFor(issues, n.code).filter((i) => i.severity === "error").length;
        return (
          <li key={n._key}>
            <div className={`tree-node ${selected === n._key ? "selected" : ""}`} onClick={() => onSelect(n._key!)}>
              <span className="code">{n.code}</span>
              <span className="name">{n.name}</span>
              {n.is_critical && <span className="tag crit" title="Critical gate">GATE</span>}
              {n.is_optional && <span className="tag" title="Optional (can be N/A)">OPT</span>}
              {n.aggregation === "minimum" && n.children.length > 0 && <span className="tag" title="Minimum roll-up">MIN</span>}
              {n.metrics.length > 0 && <span className="tag" title="Scored from metrics">#</span>}
              {errs > 0 && <span className="tag err">{errs}</span>}
              <span className="w">{(shares[n._key!] * 100).toFixed(1)}%</span>
            </div>
            {n.children.length > 0 && <Tree nodes={n.children} selected={selected} onSelect={onSelect} shares={shares} issues={issues} />}
          </li>
        );
      })}
    </ul>
  );
}

function WeightTable({ params, shares }: { params: ParamDef[]; shares: Record<string, number> }) {
  const rows: { p: ParamDef; path: string }[] = [];
  const walk = (ps: ParamDef[], path: string) =>
    ps.forEach((p) => (p.children.length ? walk(p.children, `${path}${p.name} › `) : rows.push({ p, path })));
  walk(params, "");
  const max = Math.max(...rows.map((r) => shares[r.p._key!] ?? 0), 0.0001);
  return (
    <table>
      <thead><tr><th>Parameter</th><th className="num">Share</th><th style={{ width: "35%" }} /></tr></thead>
      <tbody>
        {rows.map(({ p, path }) => (
          <tr key={p._key}>
            <td><span className="mono muted">{p.code}</span> <span className="muted small">{path}</span>{p.name}</td>
            <td className="num">{(shares[p._key!] * 100).toFixed(1)}%</td>
            <td><div className="bar-track"><div className="bar-fill" style={{ width: `${(shares[p._key!] / max) * 100}%` }} /></div></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function NodeEditor(props: {
  node: ParamDef; path: ParamDef[]; siblings: ParamDef[]; globalShare: number; maxDepth: number; scale: Scale;
  issues: Issue[]; readOnly: boolean;
  onChange: (p: Partial<ParamDef>) => void; onAddChild: () => void; onDelete: () => void; onMove: (d: number) => void;
}) {
  const { node, path, siblings, scale, onChange } = props;
  const isLeaf = node.children.length === 0;
  const level = path.length;
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}>
        <span className="chip neutral">Level {level}</span>
        <span className="small muted">{path.map((p) => p.name).join(" › ")}</span>
        <span className="spacer" />
        {!props.readOnly && (
          <>
            <button className="sm ghost" onClick={() => props.onMove(-1)} title="Move up">↑</button>
            <button className="sm ghost" onClick={() => props.onMove(1)} title="Move down">↓</button>
            <button className="sm" onClick={props.onAddChild} disabled={level >= props.maxDepth}
              title={level >= props.maxDepth ? `Max depth is ${props.maxDepth}` : "Break this parameter down"}>
              + Sub-parameter
            </button>
            <button className="sm danger" onClick={props.onDelete}>Delete</button>
          </>
        )}
      </div>
      {props.issues.length > 0 && (
        <div className={`alert ${props.issues.some((i) => i.severity === "error") ? "error" : "warn"}`}>
          <ul style={{ margin: 0 }}>{props.issues.map((i, n) => <li key={n}>[{i.code}] {i.message}</li>)}</ul>
        </div>
      )}
      <div className="form-grid">
        <Field label="Code"><input value={node.code} onChange={(e) => onChange({ code: e.target.value })} /></Field>
        <Field label="Weight" hint={`${(share(siblings, node) * 100).toFixed(1)}% of parent · ${(props.globalShare * 100).toFixed(1)}% of total`}>
          <input type="number" min={0} step="any" value={node.weight} onChange={(e) => onChange({ weight: Number(e.target.value) })} />
        </Field>
        {!isLeaf && (
          <Field label="Roll-up of children">
            <select value={node.aggregation} onChange={(e) => onChange({ aggregation: e.target.value as ParamDef["aggregation"] })}>
              <option value="weighted_mean">Weighted average</option>
              <option value="minimum">Minimum (weakest child decides)</option>
            </select>
          </Field>
        )}
      </div>
      <Field label="Name"><input value={node.name} onChange={(e) => onChange({ name: e.target.value })} /></Field>
      <Field label="Description — what exactly is judged?">
        <textarea value={node.description ?? ""} onChange={(e) => onChange({ description: e.target.value })} rows={2} />
      </Field>
      <div className="row" style={{ marginBottom: 12, gap: 16 }}>
        <label className="check">
          <input type="checkbox" checked={node.is_critical} onChange={(e) => onChange({ is_critical: e.target.checked })} />
          Critical gate
        </label>
        {node.is_critical && (
          <label className="check">
            floor
            <input type="number" style={{ width: 80 }} value={node.min_acceptable_score ?? ""} placeholder="target"
              onChange={(e) => onChange({ min_acceptable_score: e.target.value === "" ? null : Number(e.target.value) })} />
          </label>
        )}
        {isLeaf && (
          <label className="check">
            <input type="checkbox" checked={node.is_optional} onChange={(e) => onChange({ is_optional: e.target.checked })} />
            Optional (may be marked N/A)
          </label>
        )}
      </div>
      {isLeaf ? (
        <>
          <MatrixEditor criteria={node.criteria} scale={scale} readOnly={props.readOnly} onChange={(criteria) => onChange({ criteria })} />
          <MetricsEditor metrics={node.metrics} scale={scale} readOnly={props.readOnly} onChange={(metrics) => onChange({ metrics })} />
        </>
      ) : (
        <p className="small muted">
          This parameter has {node.children.length} sub-parameter{node.children.length > 1 ? "s" : ""}; its score is rolled up from them.
        </p>
      )}
    </div>
  );
}

function MatrixEditor({ criteria, scale, readOnly, onChange }: {
  criteria: Criterion[]; scale: Scale; readOnly: boolean; onChange: (c: Criterion[]) => void;
}) {
  const covered = new Map<number, number>();
  criteria.forEach((c) => { for (let s = c.score_min; s <= c.score_max; s++) covered.set(s, (covered.get(s) ?? 0) + 1); });
  const missing: number[] = [];
  const overlap: number[] = [];
  for (let s = scale.min_value; s <= scale.max_value; s++) {
    if (!covered.has(s)) missing.push(s);
    else if (covered.get(s)! > 1) overlap.push(s);
  }
  const set = (i: number, patch: Partial<Criterion>) => onChange(criteria.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const sorted = [...scale.bands].sort((a, b) => b.lower_bound - a.lower_bound);

  function generate(mode: "score" | "band") {
    if (criteria.length && !window.confirm("Replace the current rating matrix rows?")) return;
    if (mode === "score") {
      const rows: Criterion[] = [];
      for (let s = scale.max_value; s >= scale.min_value; s--) rows.push({ score_min: s, score_max: s, qualitative: "", quantitative: "" });
      onChange(rows);
    } else {
      onChange(sorted.map((b, i) => ({
        score_min: Math.ceil(b.lower_bound),
        score_max: i === 0 ? scale.max_value : Math.ceil(sorted[i - 1].lower_bound) - 1,
        qualitative: "",
        quantitative: "",
      })));
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      <div className="row" style={{ marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>Rating matrix</h3>
        <span className="small muted">Qualitative anchor + quantitative measure for every score</span>
        <span className="spacer" />
        {!readOnly && (
          <>
            {scale.max_value - scale.min_value <= 20 && <button className="sm" onClick={() => generate("score")}>One row per score</button>}
            <button className="sm" onClick={() => generate("band")}>One row per band</button>
          </>
        )}
      </div>
      {missing.length > 0 && <div className="small" style={{ color: "var(--danger)" }}>Not covered: {missing.join(", ")}</div>}
      {overlap.length > 0 && <div className="small" style={{ color: "var(--danger)" }}>Defined twice: {overlap.join(", ")}</div>}
      <table className="matrix">
        <thead><tr><th style={{ width: 70 }}>From</th><th style={{ width: 70 }}>To</th><th>Qualitative guideline</th><th>Quantitative guideline</th><th /></tr></thead>
        <tbody>
          {criteria.map((c, i) => (
            <tr key={i}>
              <td><input type="number" value={c.score_min} onChange={(e) => set(i, { score_min: Number(e.target.value) })} /></td>
              <td><input type="number" value={c.score_max} onChange={(e) => set(i, { score_max: Number(e.target.value) })} /></td>
              <td><textarea value={c.qualitative} onChange={(e) => set(i, { qualitative: e.target.value })} placeholder="What does this score look like?" /></td>
              <td><textarea value={c.quantitative ?? ""} onChange={(e) => set(i, { quantitative: e.target.value })} placeholder="Counts, %, thresholds…" /></td>
              <td>{!readOnly && <button className="sm ghost danger" onClick={() => onChange(criteria.filter((_, j) => j !== i))} aria-label="Remove row">✕</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!readOnly && (
        <button className="sm" style={{ marginTop: 6 }} onClick={() => onChange([...criteria, { score_min: scale.min_value, score_max: scale.min_value, qualitative: "", quantitative: "" }])}>
          + Row
        </button>
      )}
    </div>
  );
}

function MetricsEditor({ metrics, scale, readOnly, onChange }: {
  metrics: MetricDef[]; scale: Scale; readOnly: boolean; onChange: (m: MetricDef[]) => void;
}) {
  const set = (i: number, patch: Partial<MetricDef>) => onChange(metrics.map((m, j) => (j === i ? { ...m, ...patch } : m)));
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <div style={{ marginTop: 18 }}>
      <div className="row" style={{ marginBottom: 6 }}>
        <h3 style={{ margin: 0 }}>Quantitative metrics</h3>
        <span className="small muted">When values are entered, the score is computed from thresholds (lowest metric score wins)</span>
      </div>
      {metrics.map((m, i) => (
        <div key={i} className="card flat" style={{ marginBottom: 8, padding: 10 }}>
          <div className="form-grid">
            <Field label="Code"><input value={m.code} onChange={(e) => set(i, { code: e.target.value })} /></Field>
            <Field label="Name"><input value={m.name} onChange={(e) => set(i, { name: e.target.value })} /></Field>
            <Field label="Type">
              <select value={m.data_type} onChange={(e) => set(i, { data_type: e.target.value as MetricDef["data_type"] })}>
                <option value="percent">Percent</option><option value="count">Count</option>
                <option value="number">Number</option><option value="boolean">Yes / no (1 / 0)</option>
              </select>
            </Field>
            <Field label="Unit"><input value={m.unit ?? ""} onChange={(e) => set(i, { unit: e.target.value })} /></Field>
          </div>
          <table className="matrix">
            <thead><tr><th>Value from (≥)</th><th>Value to (&lt;)</th><th>Score ({scale.min_value}–{scale.max_value})</th><th /></tr></thead>
            <tbody>
              {m.thresholds.map((t, k) => (
                <tr key={k}>
                  <td><input type="number" value={t.min_value ?? ""} placeholder="−∞" onChange={(e) => set(i, { thresholds: m.thresholds.map((x, j) => (j === k ? { ...x, min_value: num(e.target.value) } : x)) })} /></td>
                  <td><input type="number" value={t.max_value ?? ""} placeholder="+∞" onChange={(e) => set(i, { thresholds: m.thresholds.map((x, j) => (j === k ? { ...x, max_value: num(e.target.value) } : x)) })} /></td>
                  <td><input type="number" value={t.score} onChange={(e) => set(i, { thresholds: m.thresholds.map((x, j) => (j === k ? { ...x, score: Number(e.target.value) } : x)) })} /></td>
                  <td>{!readOnly && <button className="sm ghost danger" onClick={() => set(i, { thresholds: m.thresholds.filter((_, j) => j !== k) })} aria-label="Remove threshold">✕</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!readOnly && (
            <div className="row" style={{ marginTop: 6 }}>
              <button className="sm" onClick={() => set(i, { thresholds: [...m.thresholds, { min_value: null, max_value: null, score: scale.max_value }] })}>+ Threshold</button>
              <span className="spacer" />
              <button className="sm danger" onClick={() => onChange(metrics.filter((_, j) => j !== i))}>Remove metric</button>
            </div>
          )}
        </div>
      ))}
      {!readOnly && (
        <button className="sm" onClick={() => onChange([...metrics, { code: `m${metrics.length + 1}`, name: "New metric", data_type: "percent", unit: "%", thresholds: [] }])}>
          + Metric
        </button>
      )}
    </div>
  );
}


function ReviewPanel({ vid, view, requiresReview, dirty, errors, onChanged, onError, onToggleReview }: {
  vid: number; view: VersionView; requiresReview: boolean; dirty: boolean; errors: number;
  onChanged: () => Promise<void>; onError: (e: unknown) => void; onToggleReview: (on: boolean) => Promise<void>;
}) {
  const [history, setHistory] = useState<{ action: string; actor: string; comment: string | null; at: string }[]>([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.reviews(vid).then(setHistory).catch(() => undefined); }, [vid, view.status]);
  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      setComment("");
      await onChanged();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="card">
      <h2>Review & approval</h2>
      <label className="check" style={{ display: "flex", marginBottom: 10 }}>
        <input type="checkbox" checked={requiresReview} onChange={(e) => onToggleReview(e.target.checked)} />
        Changes to this scorecard need approval by a second person
      </label>
      {requiresReview && view.status === "draft" && (
        <>
          <Field label="Note for the reviewer"><input value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
          <button className="primary" disabled={busy || dirty || errors > 0} title={dirty ? "Save first" : errors ? "Fix validation errors first" : ""}
            onClick={() => run(() => api.submitForReview(vid, comment || undefined))}>Submit for review</button>
        </>
      )}
      {view.status === "in_review" && (
        <>
          <p className="hint">Frozen while in review. The reviewer must be someone other than the person who submitted it.</p>
          <Field label="Comment (required to request changes)"><input value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
          <div className="row">
            <button className="primary" disabled={busy} onClick={() => run(() => api.approve(vid, comment || undefined))}>Approve & publish</button>
            <button disabled={busy || !comment.trim()} onClick={() => run(() => api.requestChanges(vid, comment))}>Request changes</button>
          </div>
        </>
      )}
      {history.length > 0 && (
        <ul className="timeline" style={{ marginTop: 12 }}>
          {history.map((h, i) => (
            <li key={i}><b>{h.action.replace("_", " ")}</b> by {h.actor}<div className="hint">{new Date(h.at).toLocaleString()}</div>
              {h.comment && <div className="small">“{h.comment}”</div>}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
