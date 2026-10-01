export interface Band {
  label: string;
  lower_bound: number;
  color_hex: string;
  font_hex: string;
  rag: string;
  meaning?: string | null;
}

export interface Scale {
  id: number;
  code: string;
  name: string;
  min_value: number;
  max_value: number;
  description?: string | null;
  bands: Band[];
}

export interface SubjectType {
  id: number;
  code: string;
  name: string;
  description?: string | null;
}

export interface VersionSummary {
  id: number;
  version_no: number;
  status: "draft" | "in_review" | "published" | "retired";
  published_at: string | null;
  created_at: string;
}

export interface ScorecardSummary {
  id: number;
  code: string;
  name: string;
  subject_type: string;
  subject_type_name: string;
  owner: string | null;
  tags: string[];
  is_template: boolean;
  requires_review: boolean;
  purpose: string;
  parameter_count: number;
  leaf_count: number;
  depth: number;
  evaluation_count: number;
  versions: VersionSummary[];
}

// ---- portable definition (builder) ----
export interface Threshold {
  min_value: number | null;
  max_value: number | null;
  score: number;
}
export interface MetricDef {
  code: string;
  name: string;
  unit?: string | null;
  data_type: "number" | "percent" | "count" | "boolean";
  description?: string | null;
  thresholds: Threshold[];
}
export interface Criterion {
  score_min: number;
  score_max: number;
  qualitative: string;
  quantitative?: string | null;
}
export type Aggregation = "weighted_mean" | "minimum";
export interface ParamDef {
  _key?: string;
  code: string;
  name: string;
  description?: string | null;
  weight: number;
  aggregation: Aggregation;
  is_critical: boolean;
  min_acceptable_score: number | null;
  is_optional: boolean;
  criteria: Criterion[];
  metrics: MetricDef[];
  children: ParamDef[];
}
export interface VersionDef {
  purpose: string;
  scope: string;
  objective: string;
  guidance?: string | null;
  rating_scale: string;
  target_score: number;
  aggregation: Aggregation;
  max_depth: number;
  qtc_enabled: boolean;
  required_judges: number;
  judge_tolerance_pct: number;
  require_self_appraisal: boolean;
  is_foundational: boolean;
  change_note?: string | null;
  parameters: ParamDef[];
}
export interface ScorecardDefinition {
  code: string;
  name: string;
  subject_type: string;
  owner?: string | null;
  tags: string[];
  is_template: boolean;
  requires_review?: boolean;
  version: VersionDef;
}

export interface Issue {
  code: string;
  severity: "error" | "warning";
  message: string;
  path?: string | null;
}

// ---- version / evaluation views (with ids) ----
export interface ResultView {
  judged_score: number | null;
  computed_score: number | null;
  final_score: number | null;
  score_source: string;
  not_applicable: boolean;
  rationale: string | null;
  evidence: string | null;
  confidence: number | null;
  override_reason: string | null;
  effective_weight: number | null;
  band_label: string | null;
}
export interface MetricView {
  id: number;
  code: string;
  name: string;
  unit: string | null;
  data_type: string;
  description: string | null;
  thresholds: Threshold[];
  value?: number | null;
  value_source?: string | null;
  value_note?: string | null;
}
export interface NodeView {
  id: number;
  code: string;
  name: string;
  description: string | null;
  level: number;
  weight: number;
  effective_weight: number | null;
  aggregation: Aggregation;
  is_critical: boolean;
  min_acceptable_score: number | null;
  is_optional: boolean;
  is_leaf: boolean;
  criteria: Criterion[];
  metrics: MetricView[];
  children: NodeView[];
  result?: ResultView | null;
}
export interface VersionView {
  id: number;
  scorecard_id: number;
  scorecard_code: string;
  scorecard_name: string;
  subject_type: string;
  subject_type_name: string;
  version_no: number;
  status: string;
  purpose: string;
  scope: string;
  objective: string;
  guidance: string | null;
  target_score: number;
  aggregation: Aggregation;
  max_depth: number;
  qtc_enabled: boolean;
  required_judges: number;
  judge_tolerance_pct: number;
  require_self_appraisal: boolean;
  is_foundational: boolean;
  requires_review: boolean;
  rating_scale: Scale;
  parameters: NodeView[];
}
export interface GateFailure {
  parameter_id: number;
  code: string;
  name: string;
  score: number;
  floor: number;
}
export interface EvaluationView {
  id: number;
  status: "draft" | "completed" | "void";
  subject_name: string;
  subject_ref: string | null;
  input_text: string | null;
  evaluator_type: "self" | "human" | "llm";
  evaluator_name: string | null;
  judge_model: string | null;
  is_private: boolean;
  target_score: number;
  time_met: boolean | null;
  cost_met: boolean | null;
  attempt_no: number;
  origin: "app" | "import";
  origin_ref: string | null;
  submission_id: number | null;
  final_score: number | null;
  band_label: string | null;
  rag: string | null;
  quality_met: boolean | null;
  qtc_green: boolean | null;
  gate_failures: GateFailure[];
  pending_parameter_ids: number[];
  summary: string | null;
  notes: string | null;
  created_at: string;
  completed_at: string | null;
  voided_reason: string | null;
  documents: { id: number; filename: string; media_type: string | null; chars: number }[];
  version: VersionView;
  judge_unrated?: number;
}
export interface EvaluationRow {
  id: number;
  scorecard_id: number;
  scorecard_name: string;
  version_id: number;
  version_no: number;
  subject_name: string;
  subject_ref: string | null;
  evaluator_type: string;
  evaluator_name: string | null;
  status: string;
  final_score: number | null;
  target_score: number;
  band_label: string | null;
  rag: string | null;
  quality_met: boolean | null;
  qtc_green: boolean | null;
  is_private: boolean;
  origin: "app" | "import";
  submission_id: number | null;
  created_at: string;
  completed_at: string | null;
}
export interface RatingIn {
  parameter_id: number;
  judged_score: number | null;
  not_applicable: boolean;
  rationale: string | null;
  evidence: string | null;
  confidence: number | null;
  override_reason: string | null;
}

export interface MigrationRow {
  sheet: string;
  row: number;
  kind: "meta" | "kpi" | "rating";
  label: string;
  status: "imported" | "warning" | "rejected";
  messages: string[];
}
export interface MigrationReport {
  source: string;
  status: "ok" | "ok_with_warnings" | "failed";
  committed: boolean;
  fatal: string[];
  notes: string[];
  legacy_scale: [number, number] | null;
  scale: string | null;
  definition: ScorecardDefinition | null;
  validation_issues: Issue[];
  scorecard_id: number | null;
  version_id: number | null;
  counts: Record<string, number>;
  rows: MigrationRow[];
  evaluations: {
    row: number; subject: string; evaluator: string | null; date: string | null; attempt_no: number;
    status: string; import_as: "completed" | "draft"; legacy_total: number | null; recomputed: number | null;
    diff: number | null; explanation: string | null; evaluation_id: number | null;
  }[];
  reconciliation: { rows_with_legacy_total: number; matched: number; mismatched: number; mismatched_unexplained: number; max_abs_diff: number };
}

export type RollupStatus = "green" | "not_started" | "in_progress" | "red" | "blocked";
export interface SubjectNode {
  id: number;
  code: string;
  name: string;
  subject_type: string;
  subject_type_name: string;
  owner: string;
  due_at: string | null;
  budget: number | null;
  own_status: RollupStatus;
  status: RollupStatus;
  latest: { submission_id: number; scorecard: string; score: number | null; band: string | null; rag: string | null; decision: string; qtc_green: boolean | null } | null;
  active_submission: { id: number; status: string } | null;
  descendant_counts: Partial<Record<RollupStatus, number>>;
  children: SubjectNode[];
}
export interface SubmissionRow {
  id: number;
  subject_id: number;
  subject_name: string;
  scorecard: string;
  version_no: number;
  attempt_no: number;
  owner: string;
  status: string;
  decision: string | null;
  official_score: number | null;
  official_band: string | null;
  official_rag: string | null;
  qtc_green: boolean | null;
  adjudicated: boolean;
  blocks_project: boolean;
  created_at: string;
  decided_at: string | null;
}
export interface SubjectDetail extends SubjectNode {
  path: { id: number; name: string; code: string }[];
  description: string | null;
  objective: string | null;
  deliverable: string | null;
  quality_bar: string | null;
  risks: string | null;
  blocked_by: { id: number; name: string }[];
  submissions: SubmissionRow[];
}

// ---- ODTQRC clarity agent ----
export interface ClarityIssue {
  field: "objective" | "deliverable" | "time" | "quality" | "risk" | "cost";
  problem: string;
  suggestion: string;
}
export interface ClarityResult {
  model: string;
  is_clear: boolean;
  summary: string;
  issues: ClarityIssue[];
}

// ---- AI Assist: KPI and rating-matrix drafting in the builder (backend/app/kpi_assist.py) ----
export interface AssistMessage {
  role: "user" | "assistant";
  content: string;
}
export interface AssistRequest {
  messages: AssistMessage[];
  name: string;
  subject_type: string;
  purpose: string;
  scope: string;
  objective: string;
  guidance: string;
  rating_scale: string;
  target_score: number;
  max_depth: number;
  existing: string[];
  proposal: ParamDef[];
}
export interface AssistResult {
  model: string;
  reply: string;
  parameters: ParamDef[];
  issues: Issue[];
}

// ---- AI-assisted spreadsheet import (backend/app/ai_import.py) ----
export interface AiDraftResult {
  model: string;
  summary: string;
  assumptions: string[];
  truncated: boolean;
  sheets: { name: string; rows: number }[];
  definition: ScorecardDefinition;
  issues: Issue[];
}

// ---- capability & competency (C1-C6) ----
export interface CapabilityRow {
  id: number;
  person: string;
  scorecard: string;
  scorecard_name: string;
  level: number;
  level_label: string;
  notes: string | null;
  set_by: string;
  set_at: string;
}

// ---- predictive & prescriptive risk forecast ----
export interface RiskRow {
  submission_id: number;
  subject_id: number;
  subject_name: string;
  scorecard: string;
  owner: string;
  status: string;
  score: number;
  band: "green" | "amber" | "red";
  factors: string[];
  recommended_action: string;
}
export interface AuditEntry {
  action: string;
  from: string | null;
  to: string | null;
  actor: string;
  at: string;
  details: Record<string, unknown>;
}
export interface SubmissionView {
  id: number;
  status: "open" | "in_review" | "adjudication" | "decided" | "withdrawn" | "cancelled";
  allowed_actions: string[];
  subject: { id: number; code: string; name: string; owner: string; due_at: string | null; budget: number | null; blocked: boolean };
  version: {
    id: number; scorecard_id: number; scorecard_name: string; version_no: number; required_judges: number;
    judge_tolerance_pct: number; require_self_appraisal: boolean; is_foundational: boolean; qtc_enabled: boolean;
    target_score: number; rating_scale: Scale;
  };
  attempt_no: number;
  previous_id: number | null;
  owner: string;
  title: string | null;
  input_text: string | null;
  actual_cost: number | null;
  created_at: string;
  submitted_at: string | null;
  decided_at: string | null;
  decision: "passed" | "redo" | null;
  official_score: number | null;
  official_band: string | null;
  official_rag: string | null;
  judge_spread_pct: number | null;
  gate_failures: GateFailure[];
  time_met: boolean | null;
  cost_met: boolean | null;
  qtc_green: boolean | null;
  adjudicated: boolean;
  decided_by: string | null;
  decision_reason: string | null;
  blocks_project: boolean;
  evaluations: (EvaluationRow & { is_judge: boolean; redacted: boolean })[];
  events: AuditEntry[];
}
export interface AttentionPerson {
  person: string;
  reds: number;
  latest_red_at: string;
  needs_diagnosis: boolean;
  last_diagnosis: { cause: string; action: string; at: string; by: string } | null;
  subjects: string[];
}

export class ApiError extends Error {
  code: string;
  details: unknown;
  constructor(code: string, message: string, details: unknown) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

// ---- authentication ----
// Replaces the old free-text "Acting as" / X-Actor header with a real login: a bearer token, stored here, sent
// on every request, verified server-side against a session record.

export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  roles: string[];
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

const TOKEN_KEY = "scorecard-studio.token";
let currentUser: AuthUser | null = null;

function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function setSession(token: string, user: AuthUser | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session lives for this page only */
  }
  currentUser = user;
  window.dispatchEvent(new Event("auth-changed"));
}

export function getUser(): AuthUser | null {
  return currentUser;
}

export function subscribeAuth(fn: () => void): () => void {
  window.addEventListener("auth-changed", fn);
  return () => window.removeEventListener("auth-changed", fn);
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const r = await request<{ token: string; user: AuthUser }>("POST", "/api/auth/login", { username, password });
  setSession(r.token, r.user);
  return r.user;
}

export async function register(b: { username: string; password: string; display_name: string; email?: string }): Promise<AuthUser> {
  const r = await request<{ token: string; user: AuthUser }>("POST", "/api/auth/register", b);
  setSession(r.token, r.user);
  return r.user;
}

export async function logout(): Promise<void> {
  try {
    await request("POST", "/api/auth/logout");
  } catch {
    /* the session may already be gone server-side; clear it locally regardless */
  }
  setSession("", null);
}

/** Called once at startup: if a token is stored, confirm it still works and load the current user. */
export async function restoreSession(): Promise<AuthUser | null> {
  if (!getToken()) return null;
  try {
    const u = await request<AuthUser>("GET", "/api/auth/me");
    setSession(getToken(), u);
    return u;
  } catch {
    setSession("", null);
    return null;
  }
}

async function request<T>(method: string, url: string, body?: unknown, isForm = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  });
  if (res.status === 401 && currentUser) setSession("", null); // session expired/revoked server-side: log out here too
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (data?.code) throw new ApiError(data.code, data.message, data.details);
    const msg = Array.isArray(data?.detail)
      ? data.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join("; ")
      : `${res.status} ${res.statusText}`;
    throw new ApiError("HTTP", msg, data);
  }
  return data as T;
}

export const api = {
  scales: () => request<Scale[]>("GET", "/api/meta/scales"),
  subjectTypes: () => request<SubjectType[]>("GET", "/api/meta/subject-types"),
  createSubjectType: (b: { code: string; name: string; description?: string }) =>
    request<SubjectType>("POST", "/api/meta/subject-types", b),
  createScale: (b: Omit<Scale, "id">) => request<Scale>("POST", "/api/meta/scales", b),

  scorecards: () => request<ScorecardSummary[]>("GET", "/api/scorecards"),
  scorecard: (id: number) => request<ScorecardSummary>("GET", `/api/scorecards/${id}`),
  createScorecard: (d: ScorecardDefinition, publish = false) =>
    request<ScorecardSummary>("POST", `/api/scorecards?publish=${publish}`, d),
  updateScorecardMeta: (id: number, b: Partial<Pick<ScorecardSummary, "name" | "owner" | "tags" | "is_template" | "requires_review">> & { subject_type?: string }) =>
    request<ScorecardSummary>("PATCH", `/api/scorecards/${id}`, b),
  archiveScorecard: (id: number) => request<void>("DELETE", `/api/scorecards/${id}`),
  cloneScorecard: (id: number, b: { code: string; name: string; version_id?: number }) =>
    request<ScorecardSummary>("POST", `/api/scorecards/${id}/clone`, b),

  version: (id: number) => request<VersionView>("GET", `/api/versions/${id}`),
  definition: (id: number) => request<ScorecardDefinition>("GET", `/api/versions/${id}/definition`),
  saveDraft: (id: number, v: VersionDef) =>
    request<{ version: VersionView; issues: Issue[] }>("PUT", `/api/versions/${id}`, v),
  validateDefinition: (v: VersionDef) => request<Issue[]>("POST", "/api/validate-definition", v),
  publish: (id: number) => request<{ version: VersionView; issues: Issue[] }>("POST", `/api/versions/${id}/publish`),
  newDraft: (id: number, note?: string) =>
    request<VersionView>("POST", `/api/versions/${id}/new-draft${note ? `?change_note=${encodeURIComponent(note)}` : ""}`),
  deleteDraft: (id: number) => request<void>("DELETE", `/api/versions/${id}`),

  evaluations: (q: { scorecard_id?: number; status?: string; include_private?: boolean } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && v !== "" && p.set(k, String(v)));
    return request<EvaluationRow[]>("GET", `/api/evaluations?${p}`);
  },
  evaluation: (id: number) => request<EvaluationView>("GET", `/api/evaluations/${id}`),
  createEvaluation: (b: {
    version_id: number;
    subject_name: string;
    subject_ref?: string;
    input_text?: string;
    evaluator_type: string;
    evaluator_name?: string;
    target_score?: number;
    attempt_no?: number;
  }) => request<EvaluationView>("POST", "/api/evaluations", b),
  updateEvaluation: (
    id: number,
    b: {
      ratings?: RatingIn[];
      metric_values?: { metric_id: number; value: number | null; source?: string }[];
      input_text?: string;
      time_met?: boolean | null;
      cost_met?: boolean | null;
      summary?: string;
      notes?: string;
    },
  ) => request<EvaluationView>("PUT", `/api/evaluations/${id}`, b),
  uploadDocument: (id: number, file: File) => {
    const f = new FormData();
    f.append("file", file);
    return request<EvaluationView>("POST", `/api/evaluations/${id}/documents`, f, true);
  },
  llmJudge: (id: number) => request<EvaluationView>("POST", `/api/evaluations/${id}/llm-judge`),
  complete: (id: number) => request<EvaluationView>("POST", `/api/evaluations/${id}/complete`),
  void: (id: number, reason: string) => request<EvaluationView>("POST", `/api/evaluations/${id}/void`, { reason }),

  // ---- Cycle 3: review, subjects, submissions, diagnosis
  submitForReview: (vid: number, comment?: string) => request<VersionView>("POST", `/api/versions/${vid}/submit-for-review`, { comment }),
  approve: (vid: number, comment?: string) => request<VersionView>("POST", `/api/versions/${vid}/approve`, { comment }),
  requestChanges: (vid: number, comment: string) => request<VersionView>("POST", `/api/versions/${vid}/request-changes`, { comment }),
  retire: (vid: number, reason: string) => request<VersionView>("POST", `/api/versions/${vid}/retire`, { reason }),
  reviews: (vid: number) => request<{ action: string; actor: string; comment: string | null; at: string }[]>("GET", `/api/versions/${vid}/reviews`),

  subjects: () => request<SubjectNode[]>("GET", "/api/subjects"),
  subject: (id: number) => request<SubjectDetail>("GET", `/api/subjects/${id}`),
  createSubject: (b: {
    name: string; subject_type: string; owner: string; parent_id?: number | null; description?: string;
    due_at?: string | null; budget?: number | null;
    objective?: string | null; deliverable?: string | null; quality_bar?: string | null; risks?: string | null;
  }) => request<SubjectNode>("POST", "/api/subjects", b),
  updateSubject: (id: number, b: Record<string, unknown>) => request<SubjectNode>("PATCH", `/api/subjects/${id}`, b),
  aiAssist: (b: AssistRequest) => request<AssistResult>("POST", "/api/ai-assist/parameters", b),
  clarityCheck: (subjectId: number) => request<ClarityResult>("POST", `/api/subjects/${subjectId}/clarity-check`),
  startSubmission: (subjectId: number, b: { version_id: number; title?: string; input_text?: string }) =>
    request<SubmissionView>("POST", `/api/subjects/${subjectId}/submissions`, b),
  submissions: (q: { subject_id?: number; status?: string; owner?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && v !== "" && p.set(k, String(v)));
    return request<SubmissionRow[]>("GET", `/api/submissions?${p}`);
  },
  submission: (id: number) => request<SubmissionView>("GET", `/api/submissions/${id}`),
  updateSubmission: (id: number, b: { title?: string; input_text?: string; actual_cost?: number | null }) =>
    request<SubmissionView>("PATCH", `/api/submissions/${id}`, b),
  addSubmissionEvaluation: (id: number, b: { evaluator_type: string; evaluator_name?: string }) =>
    request<EvaluationView>("POST", `/api/submissions/${id}/evaluations`, b),
  submissionAction: (id: number, action: "submit" | "withdraw" | "decide") =>
    request<SubmissionView>("POST", `/api/submissions/${id}/${action}`),
  cancelSubmission: (id: number, reason: string) => request<SubmissionView>("POST", `/api/submissions/${id}/cancel`, { reason }),
  adjudicate: (id: number, verdict: "passed" | "redo", reason: string) =>
    request<SubmissionView>("POST", `/api/submissions/${id}/adjudicate`, { verdict, reason }),
  attention: () => request<{ threshold: number; window_days: number; people: AttentionPerson[] }>("GET", "/api/attention"),
  recordDiagnosis: (b: { person: string; cause: string; action: string; notes?: string }) => request<unknown>("POST", "/api/diagnoses", b),
  diagnoses: () => request<{ id: number; person: string; cause: string; action: string; notes: string | null; recorded_by: string; recorded_at: string }[]>("GET", "/api/diagnoses"),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  behaviour: () => request<any>("GET", "/api/analytics/behaviour"),

  capabilities: (person?: string) => request<CapabilityRow[]>("GET", `/api/capabilities${person ? `?person=${encodeURIComponent(person)}` : ""}`),
  recordCapability: (b: { person: string; scorecard: string; level: number; notes?: string }) =>
    request<{ id: number; person: string; level: number; level_label: string }>("POST", "/api/capabilities", b),
  riskForecast: () => request<RiskRow[]>("GET", "/api/analytics/risk-forecast"),

  migrate: (mode: "preview" | "commit", files: File[], opts: Record<string, string | boolean>) => {
    const f = new FormData();
    files.forEach((x) => f.append("files", x));
    Object.entries(opts).forEach(([k, v]) => v !== "" && f.append(k, String(v)));
    return request<MigrationReport>("POST", `/api/migrations/${mode}`, f, true);
  },

  aiDraft: (files: File[], opts: { rating_scale: string; subject_type: string; max_depth: number; hint: string }) => {
    const f = new FormData();
    files.forEach((x) => f.append("files", x));
    Object.entries(opts).forEach(([k, v]) => v !== "" && f.append(k, String(v)));
    return request<AiDraftResult>("POST", "/api/migrations/ai-draft", f, true);
  },

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  overview: (scorecard_id?: number) => request<any>("GET", `/api/analytics/overview${scorecard_id ? `?scorecard_id=${scorecard_id}` : ""}`),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  parameterBreakdown: (version_id: number) => request<any>("GET", `/api/analytics/parameters/${version_id}`),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  agreement: (scorecard_id?: number) => request<any>("GET", `/api/analytics/judge-agreement${scorecard_id ? `?scorecard_id=${scorecard_id}` : ""}`),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  trend: (scorecard_id?: number) => request<any[]>("GET", `/api/analytics/trend${scorecard_id ? `?scorecard_id=${scorecard_id}` : ""}`),

  // ---- admin: user & role management (Phase 2) ----
  users: () => request<AuthUser[]>("GET", "/api/users"),
  updateUser: (id: number, b: { roles?: string[]; is_active?: boolean; display_name?: string }) =>
    request<AuthUser>("PATCH", `/api/users/${id}`, b),
};

export const ROLES = ["admin", "designer", "reviewer", "lead", "importer"] as const;

export function bandFor(score: number | null | undefined, scale: Scale): Band | null {
  if (score === null || score === undefined) return null;
  const sorted = [...scale.bands].sort((a, b) => b.lower_bound - a.lower_bound);
  return sorted.find((b) => score >= b.lower_bound - 1e-9) ?? null;
}

export function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "");
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}
