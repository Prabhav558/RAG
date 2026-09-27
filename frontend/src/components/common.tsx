import { ReactNode } from "react";
import { ApiError, Band, Scale, bandFor, fmt } from "../api";

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
