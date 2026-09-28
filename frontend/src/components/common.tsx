import { ReactNode, useEffect, useState } from "react";
import { ApiError, AuthUser, Band, RollupStatus, Scale, bandFor, fmt, getUser, logout, subscribeAuth } from "../api";

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

/** The authenticated user, live-updated on login/logout (Phase 2: docs/14_PHASE2_SECURITY_SPEC.md). */
export function useAuth(): { user: AuthUser | null } {
  const [user, setUser] = useState(getUser());
  useEffect(() => subscribeAuth(() => setUser(getUser())), []);
  return { user };
}

/** Workflow actions are recorded under this name — always the authenticated user's, never client-asserted. */
export function useActor(): string {
  return useAuth().user?.display_name ?? "";
}

export function hasRole(user: AuthUser | null, role: string): boolean {
  return !!user && (user.roles.includes("admin") || user.roles.includes(role));
}

export function LoggedInAs() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="acting-as">
      <span>Logged in as</span>
      <div className="row" style={{ alignItems: "baseline", justifyContent: "space-between" }}>
        <b title={user.roles.length ? user.roles.join(", ") : "member"}>{user.display_name}</b>
        <button className="sm" onClick={() => logout()}>Log out</button>
      </div>
    </div>
  );
}

export function when(d: string | null | undefined): string {
  if (!d) return "—";
  const dt = new Date(d);
  return `${dt.toLocaleDateString()} ${dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}
