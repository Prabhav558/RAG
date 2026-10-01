import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AiDraftResult, api, fmt, MigrationReport, ParamDef, Scale, SubjectType } from "../api";
import { ErrorBox, Field } from "../components/common";

const STATUS_CHIP: Record<string, string> = { imported: "pass", warning: "draft", rejected: "fail" };

function StandardImport() {
  const [files, setFiles] = useState<File[]>([]);
  const [scales, setScales] = useState<Scale[]>([]);
  const [types, setTypes] = useState<SubjectType[]>([]);
  const [rescale, setRescale] = useState("");
  const [subject, setSubject] = useState("");
  const [placeholders, setPlaceholders] = useState(true);
  const [publish, setPublish] = useState(true);
  const [report, setReport] = useState<MigrationReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [filter, setFilter] = useState<"problems" | "all">("problems");

  useEffect(() => { api.scales().then(setScales); api.subjectTypes().then(setTypes); }, []);

  const opts = { rescale_to: rescale, subject_type: subject, fill_missing_guidelines: placeholders, publish };

  async function go(mode: "preview" | "commit") {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.migrate(mode, files, opts));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const explanations: [string, number][] = [];
  report?.evaluations.forEach((e) => {
    if (e.status === "rejected" || e.diff === null || Math.abs(e.diff) <= 0.01 || !e.explanation) return;
    const hit = explanations.find(([t]) => t === e.explanation);
    if (hit) hit[1]++; else explanations.push([e.explanation, 1]);
  });
  const rows = report ? report.rows.filter((r) => filter === "all" || r.status !== "imported") : [];

  return (
    <>
      <ErrorBox error={error} />
      <div className="grid two">
        <div className="card">
          <h2>1. Source</h2>
          <Field label="Workbook (.xlsx), or a definition CSV plus a ratings CSV"
            hint="Recognised: a header row with KPI / Parameter / Criteria, optional Weight, Description and score columns (e.g. '10', 'Score 8-9'); metadata lines above it such as 'Scale: 1-5', 'Target: 8'. Ratings: a sheet with a subject column and one column per KPI.">
            <input type="file" multiple accept=".xlsx,.csv" onChange={(e) => { setFiles(Array.from(e.target.files ?? []).slice(0, 2)); setReport(null); }} />
          </Field>
          {files.length > 0 && <p className="small">{files.map((f) => f.name).join(" + ")}</p>}
        </div>
        <div className="card">
          <h2>2. Options</h2>
          <div className="form-grid">
            <Field label="Map scores onto another scale" hint="Needed when the legacy scale does not exist here">
              <select value={rescale} onChange={(e) => setRescale(e.target.value)}>
                <option value="">Keep the legacy scale</option>
                {scales.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="Subject type" hint="Overrides what the sheet says">
              <select value={subject} onChange={(e) => setSubject(e.target.value)}>
                <option value="">From the sheet</option>
                {types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </select>
            </Field>
          </div>
          <label className="check" style={{ display: "flex", marginBottom: 6 }}>
            <input type="checkbox" checked={placeholders} onChange={(e) => setPlaceholders(e.target.checked)} />
            Fill missing guidelines with clearly-marked placeholders (needed to import ratings)
          </label>
          <label className="check" style={{ display: "flex" }}>
            <input type="checkbox" checked={publish} onChange={(e) => setPublish(e.target.checked)} />
            Publish the scorecard and import historical ratings
          </label>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="primary" disabled={!files.length || busy} onClick={() => go("preview")}>{busy ? "Working…" : "Preview"}</button>
            <button disabled={!report || report.status === "failed" || report.committed || busy} onClick={() => go("commit")}>Commit import</button>
          </div>
        </div>
      </div>

      {report && (
        <>
          <div className="card" style={{ marginTop: 14 }}>
            <div className="row">
              <h2 style={{ margin: 0 }}>{report.committed ? "Imported" : "Preview"}: {report.source}</h2>
              <span className={`chip ${report.status === "ok" ? "pass" : report.status === "failed" ? "fail" : "draft"}`}>{report.status.replace(/_/g, " ")}</span>
              <span className="spacer" />
              {report.committed && report.version_id && <Link className="btn primary" to={`/versions/${report.version_id}`}>Open scorecard</Link>}
              {report.committed && report.scorecard_id && <Link className="btn" to={`/evaluations?scorecard=${report.scorecard_id}`}>Imported evaluations</Link>}
            </div>
            {report.fatal.length > 0 && <div className="alert error" style={{ marginTop: 10 }}><ul style={{ margin: 0 }}>{report.fatal.map((f) => <li key={f}>{f}</li>)}</ul></div>}
            {report.notes.length > 0 && <div className="alert warn" style={{ marginTop: 10 }}><ul style={{ margin: 0 }}>{report.notes.map((n) => <li key={n}>{n}</li>)}</ul></div>}
            {report.legacy_scale && <p className="small">Legacy scale {report.legacy_scale[0]}–{report.legacy_scale[1]} → <b>{report.scale}</b></p>}
            <div className="grid tiles" style={{ marginTop: 8 }}>
              {(["kpi", "rating"] as const).map((k) => (
                <div className="card tile flat" key={k}>
                  <div className="v">{report.counts[`${k}_imported`] ?? 0} / {report.counts[`${k}_warning`] ?? 0} / {report.counts[`${k}_rejected`] ?? 0}</div>
                  <div className="l">{k === "kpi" ? "KPI rows" : "Rating rows"}: imported / with warning / rejected</div>
                </div>
              ))}
              <div className="card tile flat">
                <div className="v">{report.reconciliation.matched}/{report.reconciliation.rows_with_legacy_total}</div>
                <div className="l">Legacy totals reproduced ({report.reconciliation.mismatched_unexplained} unexplained)</div>
              </div>
            </div>
          </div>

          {report.definition && (
            <div className="grid two" style={{ marginTop: 14 }}>
              <div className="card">
                <h2>Migrated definition</h2>
                <p className="small">
                  <b>{report.definition.name}</b> · <span className="mono">{report.definition.code}</span> · subject {report.definition.subject_type} ·
                  target {report.definition.version.target_score} · {report.definition.tags.join(", ")}
                </p>
                <DefTree params={report.definition.version.parameters} />
                {report.validation_issues.length > 0 && (
                  <div className="alert warn" style={{ marginTop: 10 }}>
                    <ul style={{ margin: 0 }}>{report.validation_issues.map((i, n) => <li key={n}>[{i.code}] {i.path} {i.message}</li>)}</ul>
                  </div>
                )}
              </div>
              <div className="card" style={{ overflowX: "auto" }}>
                <h2>Reconciliation</h2>
                {explanations.length > 0 && (
                  <ol className="small" style={{ paddingLeft: 18, marginTop: 0 }}>
                    {explanations.map(([text, n]) => <li key={text}><b>{n} row{n > 1 ? "s" : ""}:</b> {text}</li>)}
                  </ol>
                )}
                <table>
                  <thead><tr><th>Row</th><th>Subject</th><th>As</th><th className="num">Legacy</th><th className="num">New</th><th>Difference</th></tr></thead>
                  <tbody>
                    {report.evaluations.filter((e) => e.status !== "rejected").map((e) => (
                      <tr key={e.row}>
                        <td>{e.row}</td>
                        <td>{e.subject}{e.attempt_no > 1 && <span className="small muted"> (attempt {e.attempt_no})</span>}</td>
                        <td><span className={`chip ${e.import_as === "completed" ? "completed" : "draft"}`}>{e.import_as}</span></td>
                        <td className="num">{fmt(e.legacy_total)}</td>
                        <td className="num">{fmt(e.recomputed)}</td>
                        <td className="small">
                          {e.diff !== null && Math.abs(e.diff) > 0.01
                            ? `see ${explanations.findIndex(([t]) => t === e.explanation) + 1}`
                            : e.legacy_total !== null ? "✓ matches" : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {report.rows.length > 0 && (
            <div className="card" style={{ marginTop: 14, overflowX: "auto" }}>
              <div className="row" style={{ marginBottom: 8 }}>
                <h2 style={{ margin: 0 }}>Row-by-row outcome</h2>
                <span className="spacer" />
                <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} style={{ width: 200 }} aria-label="Row filter">
                  <option value="problems">Warnings and rejections</option>
                  <option value="all">All rows</option>
                </select>
              </div>
              <table>
                <thead><tr><th>Sheet</th><th>Row</th><th>Kind</th><th>Item</th><th>Status</th><th>What happened</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={`${r.sheet}-${r.row}-${r.kind}`}>
                      <td className="small">{r.sheet}</td><td>{r.row}</td><td>{r.kind}</td><td>{r.label || <span className="muted">—</span>}</td>
                      <td><span className={`chip ${STATUS_CHIP[r.status]}`}>{r.status}</span></td>
                      <td className="small">{r.messages.map((m) => <div key={m}>{m}</div>)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}

export default function ImportPage() {
  const [mode, setMode] = useState<"standard" | "ai">("ai");
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Import a legacy scorecard</h1>
          <div className="sub">
            {mode === "ai"
              ? "Bring any spreadsheet you already use, however messy or vague, and let AI draft a proper scorecard from it. You review the draft before anything is saved."
              : "Bring an existing spreadsheet scorecard (and its historical ratings) into the system. Preview first: nothing is written until you commit."}
          </div>
        </div>
      </div>
      <div className="tabs" role="tablist">
        <button className={mode === "ai" ? "active" : ""} onClick={() => setMode("ai")}>✨ AI-assisted build (any sheet)</button>
        <button className={mode === "standard" ? "active" : ""} onClick={() => setMode("standard")}>Standard import (recognised layout, with ratings)</button>
      </div>
      {mode === "ai" ? <AiImport /> : <StandardImport />}
    </>
  );
}

const DEPTHS = [
  [1, "Level 1: KPIs only"],
  [2, "Level 2: KPIs and sub-parameters (recommended)"],
  [3, "Level 3: three levels of detail"],
  [4, "Level 4: four levels of detail"],
] as const;

function AiImport() {
  const nav = useNavigate();
  const [files, setFiles] = useState<File[]>([]);
  const [scales, setScales] = useState<Scale[]>([]);
  const [types, setTypes] = useState<SubjectType[]>([]);
  const [scale, setScale] = useState("0-10-rag");
  const [subject, setSubject] = useState("");
  const [depth, setDepth] = useState(2);
  const [hint, setHint] = useState("");
  const [result, setResult] = useState<AiDraftResult | null>(null);
  const [busy, setBusy] = useState<"draft" | "create" | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => { api.scales().then(setScales); api.subjectTypes().then(setTypes); }, []);

  async function draft() {
    setBusy("draft");
    setError(null);
    setResult(null);
    try {
      setResult(await api.aiDraft(files, { rating_scale: scale, subject_type: subject, max_depth: depth, hint }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  async function create() {
    if (!result) return;
    setBusy("create");
    setError(null);
    try {
      const sc = await api.createScorecard(result.definition, false);
      nav(`/versions/${sc.versions[sc.versions.length - 1].id}`);
    } catch (e) {
      setError(e);
      setBusy(null);
    }
  }

  const def = result?.definition;
  const errors = result?.issues.filter((i) => i.severity === "error") ?? [];
  const warnings = result?.issues.filter((i) => i.severity === "warning") ?? [];
  const leafCount = (ps: ParamDef[]): number => ps.reduce((n, p) => n + (p.children.length ? leafCount(p.children) : 1), 0);

  return (
    <>
      <ErrorBox error={error} />
      <div className="grid two">
        <div className="card">
          <h2>1. Your spreadsheet</h2>
          <Field label="Workbook (.xlsx) or CSV" hint="Any layout works: a list of KPIs with or without weights, guideline text or scores. A second sheet of ratings is read for context but is not imported.">
            <input type="file" multiple accept=".xlsx,.csv" onChange={(e) => { setFiles(Array.from(e.target.files ?? []).slice(0, 2)); setResult(null); }} />
          </Field>
          {files.length > 0 && <p className="small">{files.map((f) => f.name).join(" + ")}</p>}
          <Field label="What is this sheet for? (optional)" hint="A line of context helps when the KPIs are vague, e.g. “quarterly review of our logistics vendors”.">
            <textarea rows={2} value={hint} maxLength={1000} onChange={(e) => setHint(e.target.value)} />
          </Field>
        </div>
        <div className="card">
          <h2>2. Options</h2>
          <div className="form-grid">
            <Field label="Rating scale for the new scorecard">
              <select value={scale} onChange={(e) => setScale(e.target.value)}>
                {scales.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="Subject type" hint="What is scored">
              <select value={subject} onChange={(e) => setSubject(e.target.value)}>
                <option value="">Let AI decide</option>
                {types.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="Level of detail">
              <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
                {DEPTHS.map(([n, label]) => <option key={n} value={n}>{label}</option>)}
              </select>
            </Field>
          </div>
          <p className="small muted">
            AI reads the sheet, keeps your KPIs, sharpens the vague ones into things a judge can check, and writes a rating matrix
            for each. It lists what it assumed so you can check it. Nothing is saved until you click create, and then only as a <b>draft</b>.
          </p>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="primary" disabled={!files.length || busy !== null} onClick={draft}>
              {busy === "draft" ? "Reading and drafting… (up to a minute)" : result ? "✨ Draft again" : "✨ Draft scorecard with AI"}
            </button>
          </div>
        </div>
      </div>

      {result && def && (
        <>
          <div className="card" style={{ marginTop: 14 }}>
            <div className="row">
              <h2 style={{ margin: 0 }}>{def.name}</h2>
              <span className="chip neutral">{types.find((t) => t.code === def.subject_type)?.name ?? def.subject_type}</span>
              <span className="chip neutral">target {def.version.target_score}</span>
              <span className="spacer" />
              <button className="primary" disabled={busy !== null} onClick={create}
                title="Saves it as a draft scorecard and opens it in the builder">
                {busy === "create" ? "Creating…" : "Create draft scorecard and review →"}
              </button>
            </div>
            <p style={{ margin: "8px 0 0" }}>{result.summary}</p>
            <p className="small muted" style={{ margin: "4px 0 0" }}>
              Drafted by {result.model} from {result.sheets.map((s) => `${s.name} (${s.rows} rows)`).join(", ")}.
              {result.truncated && " The sheet was long, so only the first rows of each sheet were read."}
            </p>
          </div>
          <div className="grid two" style={{ marginTop: 14 }}>
            <div className="card">
              <h2>KPIs ({def.version.parameters.length}) and rated parameters ({leafCount(def.version.parameters)})</h2>
              <DefTree params={def.version.parameters} />
              <p className="small muted" style={{ marginTop: 10 }}>
                Each rated parameter has a full rating matrix. Open the draft in the builder to read and edit them.
              </p>
            </div>
            <div>
              {result.assumptions.length > 0 && (
                <div className="card">
                  <h2>What the AI assumed. Please check.</h2>
                  <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
                    {result.assumptions.map((a, i) => <li key={i} style={{ marginBottom: 4 }}>{a}</li>)}
                  </ul>
                </div>
              )}
              <div className="card" style={{ marginTop: result.assumptions.length ? 14 : 0 }}>
                <h2>Scorecard details</h2>
                <dl className="kv">
                  <dt>Purpose</dt><dd>{def.version.purpose || <span className="muted">—</span>}</dd>
                  <dt>Scope</dt><dd>{def.version.scope || <span className="muted">—</span>}</dd>
                  <dt>Objective</dt><dd>{def.version.objective || <span className="muted">—</span>}</dd>
                  <dt>Guidance</dt><dd>{def.version.guidance || <span className="muted">—</span>}</dd>
                </dl>
                {errors.length > 0 && (
                  <div className="alert error" style={{ marginTop: 10 }}>
                    The draft has {errors.length} problem{errors.length > 1 ? "s" : ""} to fix before it can be published. You can still
                    create it and fix them in the builder.
                    <ul>{errors.map((i, n) => <li key={n}>[{i.code}] {i.path ? `${i.path}: ` : ""}{i.message}</li>)}</ul>
                  </div>
                )}
                {warnings.length > 0 && (
                  <div className="alert warn" style={{ marginTop: 10 }}>
                    <ul style={{ margin: 0 }}>{warnings.map((i, n) => <li key={n}>[{i.code}] {i.path ? `${i.path}: ` : ""}{i.message}</li>)}</ul>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function DefTree({ params }: { params: ParamDef[] }) {
  return (
    <ul className="tree">
      {params.map((p) => (
        <li key={p.code}>
          <div className="tree-node" style={{ cursor: "default" }}>
            <span className="code">{p.code}</span>
            <span className="name">{p.name}</span>
            {p.is_critical && <span className="tag crit">GATE</span>}
            {p.is_optional && <span className="tag">OPT</span>}
            {p.criteria.some((c) => c.qualitative.startsWith("[Migrated")) && <span className="tag" title="Contains placeholder guidelines">TODO</span>}
            <span className="w">w {p.weight}</span>
          </div>
          {p.children.length > 0 && <DefTree params={p.children} />}
        </li>
      ))}
    </ul>
  );
}
