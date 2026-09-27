import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ScorecardSummary, VersionView } from "../api";
import { ErrorBox, Field, ScaleLegend } from "../components/common";

export default function NewEvaluation() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [cards, setCards] = useState<ScorecardSummary[]>([]);
  const [versionId, setVersionId] = useState<number | null>(params.get("version") ? Number(params.get("version")) : null);
  const [version, setVersion] = useState<VersionView | null>(null);
  const [subject, setSubject] = useState("");
  const [ref, setRef] = useState("");
  const [evaluator, setEvaluator] = useState<"human" | "self" | "llm">("human");
  const [evaluatorName, setEvaluatorName] = useState("");
  const [target, setTarget] = useState<string>("");
  const [attempt, setAttempt] = useState(1);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => { api.scorecards().then(setCards).catch(setError); }, []);
  useEffect(() => {
    if (versionId) api.version(versionId).then((v) => { setVersion(v); setTarget(String(v.target_score)); }).catch(setError);
  }, [versionId]);

  const publishedCards = cards.filter((c) => c.versions.some((v) => v.status === "published"));

  async function start() {
    if (!version) return;
    setBusy(true);
    setError(null);
    try {
      const ev = await api.createEvaluation({
        version_id: version.id,
        subject_name: subject,
        subject_ref: ref || undefined,
        input_text: text || undefined,
        evaluator_type: evaluator,
        evaluator_name: evaluatorName || undefined,
        target_score: target === "" ? undefined : Number(target),
        attempt_no: attempt,
      });
      if (file) await api.uploadDocument(ev.id, file);
      let next = ev;
      if (evaluator === "llm") {
        try {
          next = await api.llmJudge(ev.id);
        } catch (e) {
          nav(`/evaluations/${ev.id}`, { state: { judgeError: e } });
          return;
        }
      }
      nav(`/evaluations/${next.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>New evaluation</h1>
          <div className="sub">Choose a published scorecard, describe the subject and provide the input to evaluate.</div>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="grid two">
        <div className="card">
          <h2>1. Scorecard</h2>
          <Field label="Published scorecard">
            <select value={versionId ?? ""} onChange={(e) => setVersionId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Select…</option>
              {publishedCards.map((c) => {
                const v = [...c.versions].reverse().find((x) => x.status === "published")!;
                return <option key={v.id} value={v.id}>{c.name} (v{v.version_no}) — {c.subject_type_name}</option>;
              })}
            </select>
          </Field>
          {version && (
            <>
              <p><b>Purpose:</b> {version.purpose}</p>
              <p><b>Objective:</b> {version.objective}</p>
              <p className="small muted">
                {version.rating_scale.name} · target {version.target_score}
                {version.qtc_enabled ? " · QTC rule applies" : ""}
              </p>
              <ScaleLegend scale={version.rating_scale} />
            </>
          )}
        </div>
        <div className="card">
          <h2>2. Subject & evaluator</h2>
          <div className="form-grid">
            <Field label={`${version?.subject_type_name ?? "Subject"} name`}>
              <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="What is being evaluated?" />
            </Field>
            <Field label="Reference / ID" hint="Links repeat evaluations of the same subject">
              <input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="e.g. JIRA-123" />
            </Field>
            <Field label="Evaluated by">
              <select value={evaluator} onChange={(e) => setEvaluator(e.target.value as typeof evaluator)}>
                <option value="human">Human judge</option>
                <option value="self">Self-appraisal (private)</option>
                <option value="llm">LLM judge (human reviews)</option>
              </select>
            </Field>
            <Field label="Evaluator name"><input value={evaluatorName} onChange={(e) => setEvaluatorName(e.target.value)} /></Field>
            <Field label="Target for this context" hint="Defaults to the scorecard target">
              <input type="number" step="0.5" value={target} onChange={(e) => setTarget(e.target.value)} />
            </Field>
            <Field label="Attempt">
              <input type="number" min={1} value={attempt} onChange={(e) => setAttempt(Number(e.target.value))} />
            </Field>
          </div>
        </div>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <h2>3. Input</h2>
        <Field label="Paste text / notes / data" hint="The LLM judge reads this plus any uploaded document. Human judges can use it as reference.">
          <textarea rows={10} value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
        <Field label="…or upload a document (txt, md, csv, json, docx, pdf)">
          <input type="file" accept=".txt,.md,.csv,.json,.docx,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        <div className="row">
          <button className="primary" disabled={!version || !subject.trim() || busy} onClick={start}>
            {busy ? (evaluator === "llm" ? "Judging… this can take a minute" : "Starting…") : evaluator === "llm" ? "Start and run LLM judge" : "Start evaluation"}
          </button>
        </div>
      </div>
    </>
  );
}
