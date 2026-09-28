# Phase 2 — Security & Governance Specification

Phase 1 (Cycles 1–3) asserted identity through a client-supplied name (`X-Actor` / "Acting as"). That was
explicitly out of scope for security: it stopped *mistakes* (a workflow guard rejecting the wrong actor) but not a
person typing someone else's name. Phase 2 replaces asserted identity with **authenticated** identity and adds
role-based authorisation on top of the separation-of-duties rules that already existed.

Implementation: `backend/app/auth.py` (hashing, sessions, dependencies), `backend/app/routers/auth.py` (endpoints),
`backend/app/models.py` (`UserAccount`, `AuthSession`). Tests: `backend/tests/test_auth.py`.

## 1. Identity
- A **UserAccount** has a unique `username`, optional `email`, a salted password hash, a `display_name` (what
  appears as the actor in workflow rules, audit trails and evaluator names), a list of `roles`, and `is_active`.
- **Registration is self-service** (`POST /api/auth/register`) into the default role `member`. Elevated roles
  (`admin`, `designer`, `reviewer`, `lead`, `importer`) are granted only by an admin (`PATCH /api/users/{id}`).
  This mirrors how the pilot actually runs: anyone can join and rate/submit work; only nominated people design
  scorecards, review them, lead diagnosis, or import legacy data.
- **Login** (`POST /api/auth/login`) verifies the password and issues an opaque bearer token, stored server-side
  as an **AuthSession** (hash of the token, not the token itself — a database leak does not yield usable tokens).
  Sessions expire after `SESSION_TTL_DAYS` (default 14) and can be revoked (`POST /api/auth/logout`, or by an admin
  deactivating the user).
- **Every workflow action now requires a valid session.** `flow.actor()`, the evaluation-editing guards and
  `publish` all resolve the actor from the authenticated user's `display_name`, never from a request header or
  body field. The old `X-Actor` header is ignored.
- **Brute-force protection:** 5 consecutive failed logins lock the account for `LOGIN_LOCKOUT_MINUTES` (default 15).

## 2. Password storage
PBKDF2-HMAC-SHA256, 260,000 iterations (OWASP's 2023 minimum for PBKDF2-SHA256), a random 16-byte salt per user,
stored as `pbkdf2_sha256$<iterations>$<salt-hex>$<hash-hex>`. No new dependency — the standard library's
`hashlib.pbkdf2_hmac` is used directly, verified with `hmac.compare_digest` (constant-time). Minimum password
length: 8 characters (checked at the contract level; a real deployment should add a breached-password check,
noted as a limitation below).

## 3. Roles and what they gate
| Role | Grants (beyond `member`) |
|---|---|
| `member` (default) | Everything a `member` could always do under Phase 1: create subjects, self-appraise, submit, judge, adjudicate — all still subject to the existing separation-of-duties guards (S003 etc.), which now use *verified* identity |
| `designer` | Create/edit/publish/retire scorecards; submit for review; create rating scales and subject types |
| `reviewer` | Approve or request changes on a scorecard version in review (still never their own submission — S003 unchanged) |
| `lead` | Cancel a submission; record a red diagnosis (still never about themselves — S003 unchanged) |
| `importer` | Commit a legacy migration (preview remains open to any member, since it writes nothing) |
| `admin` | Everything; manage users and roles; deactivate accounts |

A user can hold several roles. Role checks are **additive** to the identity checks: holding `designer` lets you
publish scorecards in general, but it never lets you approve your *own* submission — that guard compares the
authenticated display name, not the role.

## 4. What changed vs. Phase 1 (identity-spoofing fixes)
Two gaps existed under asserted identity and are closed now that identity is verified:
1. **Self-appraisal creation had no owner check.** `add_evaluation` let anyone create a `self` evaluation on
   someone else's submission (only *completing/editing* one was guarded). Fixed: creating a self-appraisal now
   requires `actor == submission.owner` (S003).
2. **A human judge's recorded name was client-supplied**, so a judge could evaluate under a name that was not
   their own. Fixed: for `evaluator_type == "human"`, the recorded name is always the authenticated actor's
   `display_name`; a client-supplied `evaluator_name` is accepted only for `llm` (a system judge, not a person).

## 5. Data governance (§ retention, classification, privacy)
- **Classification.** Self-appraisals and diagnosis notes are the most sensitive data in the system (personal
  performance information). Self-appraisals were already redacted from non-owners (S011); this phase adds the
  same treatment to diagnosis notes (visible to `lead`/`admin` and the diagnosed person only, `GET /api/diagnoses`).
- **Retention.** `data/tools/retention.py` reports and (with `--apply`) purges: audit events older than
  `AUDIT_RETENTION_DAYS` (default 400), and void evaluations older than `VOID_RETENTION_DAYS` (default 90) —
  voided data was already excluded from every read model, so keeping it indefinitely serves no purpose. Completed
  evaluations, submissions and diagnoses are **never** auto-purged: they are the record a red diagnosis and a
  scorecard's history depend on. A dry run is always printed before `--apply` deletes anything.
- **Right to erasure (partial).** `PATCH /api/users/{id}` with `is_active: false` disables login. Anonymising a
  departed person's historical `owner`/`evaluator_name` strings is not implemented (it would break the audit
  trail's meaning); see limitations.

## 6. Explicitly out of scope / limitations (honest, not fixed here)
- **SSO / OAuth2 / SAML.** Username+password only. A real deployment behind SSO would replace `auth.py`'s login
  endpoint, not the session/RBAC layer above it.
- **httpOnly cookies + CSRF.** The token is a bearer token in `localStorage` (consistent with the rest of this
  SPA's client-side state), which is simpler but vulnerable to XSS exfiltration. Acceptable for a single-origin
  internal tool; revisit before splitting the frontend to another origin.
- **No password reset flow** (no email sending is configured). An admin can only deactivate/reset via direct
  action; a self-service "forgot password" needs an email provider, which is an infrastructure decision, not a
  code gap.
- **No MFA, no breached-password check, no sliding session renewal.**
- **Anonymisation on erasure** is not implemented (see §5).
- **Field-level encryption at rest** is not implemented; this relies on the database's own encryption (e.g.
  Postgres disk encryption / managed-service encryption).

These are genuine Phase 2+ items, not corners cut silently — each is named here so it can be prioritised
deliberately rather than discovered later.
