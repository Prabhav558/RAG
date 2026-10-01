import { useEffect, useRef, useState } from "react";
import { api, ApiError, AssistRequest, Issue, ParamDef, ScorecardDefinition } from "../api";
import { useActor } from "./common";

interface ChatItem {
  role: "user" | "assistant";
  content: string;
  proposal?: ParamDef[];
  issues?: Issue[];
  applied?: "add" | "replace" | "dismissed";
  added?: string[]; // codes of drafted items already accepted one by one
}

/** An existing parameter in the builder that a drafted sub-parameter can be added under. */
export interface AssistTarget {
  key: string;
  code: string;
  name: string;
  depth: number; // 1 = top-level KPI
  hasContent: boolean; // a leaf with a matrix or metrics: adding a child replaces them
}

interface AddCtx {
  added: string[];
  targets: AssistTarget[];
  maxDepth: number;
  onAdd: (node: ParamDef, parentKey: string | null) => void;
}

const EXAMPLES = [
  "I want 3 KPIs: clarity, tone and actionability",
  "Suggest 5 KPIs for this scorecard",
  "Make the top band harder to earn",
];

function leaves(ps: ParamDef[]): ParamDef[] {
  return ps.flatMap((p) => (p.children.length ? leaves(p.children) : [p]));
}

const height = (p: ParamDef): number => 1 + Math.max(0, ...p.children.map(height));

function Proposal({ nodes, issues, ctx }: { nodes: ParamDef[]; issues: Issue[]; ctx: AddCtx }) {
  const total = nodes.reduce((s, p) => s + p.weight, 0) || 1;
  return (
    <div className="assist-proposal">
      {nodes.map((p) => (
        <Node key={p.code} p={p} share={p.weight / total} issues={issues} ctx={ctx} top />
      ))}
    </div>
  );
}

function AddControl({ p, top, ctx }: { p: ParamDef; top: boolean; ctx: AddCtx }) {
  if (ctx.added.includes(p.code)) return <span className="small" style={{ color: "var(--ok)", marginLeft: 8 }}>✓ added</span>;
  const stop = (e: React.SyntheticEvent) => { e.preventDefault(); e.stopPropagation(); };
  if (top) {
    return (
      <button className="sm assist-add" onClick={(e) => { stop(e); ctx.onAdd(p, null); }} title="Add this KPI, with everything under it">
        + Add
      </button>
    );
  }
  const h = height(p);
  const fits = ctx.targets.filter((t) => t.depth + h <= ctx.maxDepth);
  return (
    <select
      className="assist-add" value="" aria-label={`Add ${p.name}`} onClick={(e) => e.stopPropagation()}
      onChange={(e) => { const v = e.target.value; if (v) ctx.onAdd(p, v === "__top" ? null : v); }}
    >
      <option value="">+ Add to…</option>
      <option value="__top">a new top-level KPI</option>
      {fits.map((t) => (
        <option key={t.key} value={t.key}>
          under {t.code} {t.name}{t.hasContent ? " (replaces its matrix)" : ""}
        </option>
      ))}
    </select>
  );
}

function Node({ p, share, issues, ctx, top = false }: { p: ParamDef; share: number; issues: Issue[]; ctx: AddCtx; top?: boolean }) {
  const total = p.children.reduce((s, c) => s + c.weight, 0) || 1;
  const mine = issues.filter((i) => i.path?.endsWith(`/${p.code}`) || i.path?.includes(`/${p.code}#`));
  return (
    <details className="assist-node" open={p.code.indexOf(".") < 0 && p.children.length > 0 ? true : undefined}>
      <summary>
        <span className="mono muted">{p.code}</span> <b>{p.name}</b>
        <span className="muted small"> · {(share * 100).toFixed(0)}%</span>
        {p.is_critical && <span className="tag crit" style={{ marginLeft: 6 }}>GATE</span>}
        {p.metrics.length > 0 && <span className="tag" style={{ marginLeft: 6 }}>#</span>}
        {mine.length > 0 && <span className="tag err" style={{ marginLeft: 6 }} title={mine.map((i) => i.message).join("\n")}>{mine.length}</span>}
        <span style={{ marginLeft: 8 }}><AddControl p={p} top={top} ctx={ctx} /></span>
      </summary>
      {p.description && <div className="small muted" style={{ margin: "2px 0 6px 14px" }}>{p.description}</div>}
      {p.children.length > 0 ? (
        <div style={{ marginLeft: 14 }}>
          {p.children.map((c) => <Node key={c.code} p={c} share={c.weight / total} issues={issues} ctx={ctx} />)}
        </div>
      ) : (
        <table className="matrix assist-matrix">
          <thead><tr><th style={{ width: 44 }}>Score</th><th>Qualitative</th><th>Quantitative</th></tr></thead>
          <tbody>
            {p.criteria.map((c, i) => (
              <tr key={i}>
                <td>{c.score_min === c.score_max ? c.score_min : `${c.score_min}–${c.score_max}`}</td>
                <td>{c.qualitative}</td>
                <td>{c.quantitative}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {p.metrics.map((m) => (
        <div key={m.code} className="small" style={{ margin: "4px 0 6px 14px" }}>
          <b>Metric:</b> {m.name} ({m.data_type}) →{" "}
          {m.thresholds.map((t) => `${t.min_value ?? "−∞"} to ${t.max_value ?? "+∞"}: ${t.score}`).join(" · ")}
        </div>
      ))}
    </details>
  );
}

const MAX_SAVED = 40;

/** The chat is kept per scorecard (and per person) in this browser, so it survives closing the panel, switching
 * tabs, reloading the page and coming back later. Storage can be unavailable or full: then it just isn't kept. */
function loadChat(key: string): ChatItem[] {
  try {
    const raw = window.localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((i) => i && (i.role === "user" || i.role === "assistant") && typeof i.content === "string") : [];
  } catch {
    return [];
  }
}

function saveChat(key: string, items: ChatItem[]) {
  try {
    if (items.length === 0) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(items.slice(-MAX_SAVED)));
  } catch {
    /* private mode or storage full: the chat just isn't kept */
  }
}

export default function AiAssist({ open, scorecardId, version, name, subjectType, targets, onApply, onClose }: {
  open: boolean; scorecardId: number;
  version: ScorecardDefinition["version"]; name: string; subjectType: string; targets: AssistTarget[];
  onApply: (parameters: ParamDef[], mode: "add" | "replace", parentKey?: string | null) => void; onClose: () => void;
}) {
  const existing = targets.filter((t) => t.depth === 1).map((t) => t.name);
  const actor = useActor();
  const storageKey = `scorecard-studio:ai-assist:${actor || "anonymous"}:${scorecardId}`;
  const [items, setItems] = useState<ChatItem[]>(() => loadChat(storageKey));
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { saveChat(storageKey, items); }, [storageKey, items]);
  useEffect(() => { if (open) end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [items, busy, open]);

  const missing = !version.purpose.trim() || !version.objective.trim();

  async function send(raw: string) {
    const content = raw.trim();
    if (!content || busy) return;
    const next: ChatItem[] = [...items, { role: "user", content }];
    setItems(next);
    setText("");
    setError(null);
    setBusy(true);
    const pending = [...items].reverse().find((i) => i.proposal && !i.applied);
    const req: AssistRequest = {
      messages: next.slice(-30).map((i) => ({ role: i.role, content: i.content })),
      name, subject_type: subjectType, purpose: version.purpose, scope: version.scope, objective: version.objective,
      guidance: version.guidance ?? "", rating_scale: version.rating_scale, target_score: version.target_score,
      max_depth: version.max_depth, existing, proposal: pending?.proposal ?? [],
    };
    try {
      const r = await api.aiAssist(req);
      const done: ChatItem[] = [...next, {
        role: "assistant", content: r.reply || (r.parameters.length ? "Here is a draft." : "Could you tell me more?"),
        proposal: r.parameters.length ? r.parameters : undefined, issues: r.issues,
      }];
      saveChat(storageKey, done); // saved even if the panel was left while the answer was on its way
      setItems(done);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function apply(i: number, mode: "add" | "replace") {
    const it = items[i];
    if (!it.proposal) return;
    if (mode === "replace" && !window.confirm("Replace every KPI currently in the builder with this draft?")) return;
    // KPIs already accepted one by one are not added a second time
    const rest = mode === "add" ? it.proposal.filter((p) => !it.added?.includes(p.code)) : it.proposal;
    onApply(rest, mode);
    setItems(items.map((x, j) => (j === i ? { ...x, applied: mode } : x)));
  }

  function addOne(i: number, node: ParamDef, parentKey: string | null) {
    const target = parentKey ? targets.find((t) => t.key === parentKey) : null;
    if (target?.hasContent && !window.confirm(`'${target.name}' already has its own rating matrix. Adding a sub-parameter replaces it with a roll-up of its sub-parameters. Continue?`)) return;
    onApply([node], "add", parentKey);
    setItems(items.map((x, j) => (j === i ? { ...x, added: [...(x.added ?? []), node.code] } : x)));
  }

  function clearChat() {
    if (items.length && !window.confirm("Start a new chat? This clears the conversation saved for this scorecard.")) return;
    setItems([]);
    setError(null);
  }

  if (!open) return null; // stays mounted (and keeps its chat) while closed or while another tab is showing

  return (
    <div className="assist" role="dialog" aria-label="AI Assist">
      <div className="assist-head">
        <b>✨ AI Assist</b>
        <span className="small muted">Describe the KPIs you want; review the draft before it is added. Your chat is saved for this scorecard.</span>
        <span className="spacer" />
        {items.length > 0 && <button className="sm ghost" onClick={clearChat} disabled={busy} title="Clear the saved conversation for this scorecard">New chat</button>}
        <button className="sm ghost" onClick={onClose} aria-label="Close AI Assist">✕</button>
      </div>
      <div className="assist-body">
        {missing && (
          <div className="alert warn small">
            Fill in the <b>Purpose</b> and <b>Objective</b> on the first tab so the draft fits your scorecard.
          </div>
        )}
        {items.length === 0 && (
          <div className="assist-empty">
            <p className="small muted" style={{ marginTop: 0 }}>
              Tell me which KPIs you want, or ask me to suggest some. I will draft the hierarchy, weights and the
              rating matrix for each, and you accept or ask for changes.
            </p>
            {EXAMPLES.map((e) => <button key={e} className="sm assist-chip" onClick={() => send(e)} disabled={busy}>{e}</button>)}
          </div>
        )}
        {items.map((it, i) => (
          <div key={i} className={`assist-msg ${it.role}`}>
            <div>{it.content}</div>
            {it.proposal && (
              <>
                <div className="small muted" style={{ margin: "8px 0 4px" }}>
                  Draft: {it.proposal.length} KPI{it.proposal.length > 1 ? "s" : ""}, {leaves(it.proposal).length} rated parameter{leaves(it.proposal).length > 1 ? "s" : ""}. Click an item to see its rating matrix; use <b>+ Add</b> to take just that one.
                </div>
                <Proposal nodes={it.proposal} issues={it.issues ?? []}
                  ctx={{ added: it.added ?? [], targets, maxDepth: version.max_depth, onAdd: (n, k) => addOne(i, n, k) }} />
                {(it.issues ?? []).some((x) => x.severity === "error") && (
                  <div className="alert error small" style={{ marginTop: 6 }}>
                    The draft has {(it.issues ?? []).filter((x) => x.severity === "error").length} problem(s) (marked in red).
                    You can still add it and fix them, or ask me to correct it.
                  </div>
                )}
                {!it.applied && it.proposal.every((x) => it.added?.includes(x.code)) ? (
                  <div className="small" style={{ marginTop: 8, color: "var(--ok)" }}>✓ Every KPI in this draft has been added.</div>
                ) : !it.applied ? (
                  <div className="row" style={{ marginTop: 8 }}>
                    <button className="primary sm" onClick={() => apply(i, "add")}>
                      {existing.length ? "Add to scorecard" : "Use this draft"}
                    </button>
                    {existing.length > 0 && <button className="sm" onClick={() => apply(i, "replace")}>Replace existing KPIs</button>}
                    <button className="sm ghost" onClick={() => setItems(items.map((x, j) => (j === i ? { ...x, applied: "dismissed" } : x)))}>Dismiss</button>
                  </div>
                ) : (
                  <div className="small" style={{ marginTop: 8, color: it.applied === "dismissed" ? "var(--muted)" : "var(--ok)" }}>
                    {it.applied === "dismissed" ? "Dismissed." : it.applied === "replace" ? "✓ Replaced the KPIs in the builder." : "✓ Added to the builder."}
                  </div>
                )}
              </>
            )}
          </div>
        ))}
        {busy && <div className="assist-msg assistant muted">Thinking… drafting the matrix can take 10 to 30 seconds.</div>}
        {error && <div className="alert error small">{error}</div>}
        <div ref={end} />
      </div>
      <form className="assist-input" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <textarea
          value={text} rows={2} placeholder={items.length ? "Ask for changes, e.g. “make tone weigh 40%”" : "e.g. I want 3 KPIs: clarity, tone and actionability"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
          disabled={busy}
        />
        <button className="primary" type="submit" disabled={busy || !text.trim()}>Send</button>
      </form>
    </div>
  );
}
