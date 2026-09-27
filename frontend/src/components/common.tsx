import { ReactNode, useEffect, useState } from "react";
import { ApiError, Band, getActor, RollupStatus, Scale, bandFor, fmt, setActor } from "../api";

export function ScoreBadge({ score, scale, size }: { score: number | null | undefined; scale: Scale; size?: "lg" }) {
  const band = bandFor(score, scale);
  return (
    <span
      className={`band ${size ?? ""}`}
      style={band ? { background: band.color_hex, color: band.font_hex } : { background: "var(--surface-2)" }}
      title={band ? `${band.label}${band.meaning ? ` — ${band.meaning}` : ""}` : "Not scored yet"}
    >
      {fmt(score)}
    </span>
  );
}

export function BandChip({ band }: { band: Band | null | undefined }) {
  if (!band) return <span className="chip neutral">Not scored</span>;
  return (
    <span className="chip" style={{ background: band.color_hex, color: band.font_hex }}>
      {band.label}
    </span>
  );
}

export function Verdict({ met, pending }: { met: boolean | null | undefined; pending?: string }) {
  if (met === null || met === undefined) return <span className="chip neutral">{pending ?? "Pending"}</span>;
  return met ? <span className="chip pass">✓ Meets target</span> : <span className="chip fail">✗ Below target</span>;
}

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip ${status}`}>{status}</span>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as ApiError;
  const details = Array.isArray(e.details) ? e.details : null;
  return (
    <div className="alert error" role="alert">
      <b>{e.code ? `[${e.code}] ` : ""}</b>
      {e.message ?? String(error)}
      {details && details.length > 0 && (
        <ul>
          {details.map((d, i) => (
            <li key={i}>
              {typeof d === "string" ? d : `[${d.code}] ${d.path ? `${d.path}: ` : ""}${d.message}`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <div className="small muted">{hint}</div>}
    </label>
  );
}

export function ScaleLegend({ scale }: { scale: Scale }) {
  return (
    <div className="legend">
      {[...scale.bands]
        .sort((a, b) => b.lower_bound - a.lower_bound)
        .map((b) => (
          <span key={b.label} title={b.meaning ?? ""}>
            <i style={{ background: b.color_hex }} />
            {b.label} (≥ {b.lower_bound})
          </span>
        ))}
    </div>
  );
}

const ROLLUP: Record<RollupStatus, { label: string; icon: string; cls: string; title: string }> = {
  green: { label: "Green", icon: "✓", cls: "pass", title: "Passed: everything beneath is green too" },
  red: { label: "Red", icon: "✗", cls: "fail", title: "Below target, or quality met but time/cost missed" },
  blocked: { label: "Blocked", icon: "⛔", cls: "fail", title: "Stopped by a foundational red" },
  in_progress: { label: "In progress", icon: "◔", cls: "draft", title: "Being worked on or judged" },
  not_started: { label: "Not started", icon: "○", cls: "neutral", title: "No submission yet" },
};

export function RollupPill({ status }: { status: RollupStatus }) {
  const r = ROLLUP[status] ?? ROLLUP.not_started;
  return <span className={`chip ${r.cls}`} title={r.title}>{r.icon} {r.label}</span>;
}

export const SUBMISSION_LABEL: Record<string, string> = {
  open: "Open", in_review: "In review", adjudication: "Adjudication", decided: "Decided", withdrawn: "Withdrawn",
  cancelled: "Cancelled",
};

export function ActingAs() {
  const [name, setName] = useState(getActor());
  useEffect(() => {
    const h = () => setName(getActor());
    window.addEventListener("actor-changed", h);
    return () => window.removeEventListener("actor-changed", h);
  }, []);
  return (
    <label className="acting-as" title="Workflow actions are recorded under this name (Phase 1 has no login)">
      <span>Acting as</span>
      <input value={name} placeholder="your name" onChange={(e) => { setName(e.target.value); setActor(e.target.value.trim()); }} />
    </label>
  );
}

export function useActor(): string {
  const [name, setName] = useState(getActor());
  useEffect(() => {
    const h = () => setName(getActor());
    window.addEventListener("actor-changed", h);
    return () => window.removeEventListener("actor-changed", h);
  }, []);
  return name;
}

export function when(d: string | null | undefined): string {
  if (!d) return "—";
  const dt = new Date(d);
  return `${dt.toLocaleDateString()} ${dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}
