# SafeSpeak PES: Architecture

This records the approved from-scratch design. Labels show where each decision comes from:

- **[PD]** project documents (Review-1 PPT, Review-II faculty feedback, annotation guidelines)
- **[AR]** additional requirements given by the project owner
- **[TR]** technical recommendation, accepted as part of the approved blueprint

## Principle

The AI recommends; an authorized human decides. **[PD]**
The system never decides guilt, punishment, diagnosis or legal outcomes. **[PD]**

## Core workflow

Login → submit complaint → unique `SSP-YYYY-NNNNNN` ID → AI category, priority and confidence →
human review when required → TAT deadline → authority routing → accept / override / reroute →
audit event → TAT breach → escalation → new deadline → resolution → closure. **[PD + AR]**

## Components

```
React SPA (role-based areas)
   │  JSON, Authorization: Bearer <JWT>
FastAPI /api/v1
   ├─ api/        thin routers: validate input, call a service, shape the response
   ├─ api/deps    database session, current user (re-read from DB), permission checks
   ├─ services/   all business rules (complaints, IDs, triage, review, routing, TAT,
   │              escalation, lifecycle, audit, settings)
   ├─ models/     SQLAlchemy entities, migrated with Alembic
   └─ triage model loader → versioned artifacts produced by ml/
ml/ (offline research): dataset → train → evaluate → threshold analysis → artifacts/<version>/
```

- The research dataset is never used as the application database. **[AR]**
- Permissions are enforced by the backend; the frontend only shows or hides features. **[AR]**

## Final decisions

| # | Decision |
|---|---|
| D1 | Flagged complaints are reviewed first by the Level-1 authority for the AI-predicted category, who can reroute if the category is wrong. |
| D2 | Institutional email domains are configuration only (`ALLOWED_EMAIL_DOMAINS`); no domain is hard-coded. |
| D3 | Students, teaching staff, non-teaching staff, department authorities and higher authorities can all submit complaints. An authority's own complaint follows the normal workflow; their handling permissions stay active for complaints assigned to them. |
| D4 | View-only users have read-only access within their configured scope (institution-wide if configured) and can never accept, override, reroute, resolve, close or modify complaints. |
| D5 | The synthetic research dataset may be committed. The private annotation answer key, passwords, JWT secrets, `.env` files and API keys are never committed. |
| D6 | Alembic migrations from day 1. |
| D7 | `is_anonymous` is part of the schema; anonymous handling is built only if it does not delay the core workflow. |

Also fixed: complaint ID format `SSP-YYYY-NNNNNN` (generated from a database counter, never `count()+1`);
roles come only from the authenticated account; complainants cannot choose priority; High and Critical
complaints always need human review; low-confidence complaints get a review TAT; TAT uses calendar time;
TAT values and the escalation hierarchy are clearly labelled sample data, not the real PES hierarchy;
AI predictions and audit logs are immutable; no chatbot in the first phases.

## Time handling **[TR]**

All timestamps are stored in UTC (`UTCDateTime` column type rejects naive values).
Display uses `DISPLAY_TIMEZONE` (default `Asia/Kolkata`), which also sets the year in complaint IDs.

## Authentication and authorization (Phase 2)

### Roles **[AR]**

Seven roles, stored on the user account (`users.role`) and never chosen by the user:

| Role | Purpose |
|---|---|
| `student`, `teaching_staff`, `non_teaching_staff` | Complainants |
| `department_authority` | Handles complaints at department/office level (authority level L1–L2 in the sample hierarchy); can also file complaints |
| `higher_authority` | Handles escalated complaints (L3+ in the sample hierarchy); can also file complaints |
| `viewer` | Read-only access within its configured scope |
| `admin` | Manages users, rules and settings; does not handle complaints |

### Permission matrix **[AR + TR]**

Defined once in `backend/app/core/permissions.py`. Permissions say what *kind* of action a role may take;
whether a particular complaint is in scope (own, assigned, department) is checked separately by
`backend/app/services/complaint_service.py` (`can_view`, `_get_for_review`).

| Permission | Student / Teaching / Non-teaching | Dept authority | Higher authority | Viewer | Admin |
|---|---|---|---|---|---|
| `submit_complaint` | ✓ | ✓ | ✓ | – | – |
| `view_own_complaints` | ✓ | ✓ | ✓ | – | – |
| `view_assigned_complaints` | – | ✓ | ✓ | – | – |
| `review_complaints` | – | ✓ | ✓ | – | – |
| `reroute_complaints` | – | ✓ | ✓ | – | – |
| `resolve_complaints` | – | ✓ | ✓ | – | – |
| `view_scoped_complaints` (read-only) | – | – | – | ✓ | ✓ |
| `manage_users` | – | – | – | – | ✓ |
| `manage_rules_and_settings` | – | – | – | – | ✓ |

Enforced by endpoints: `manage_users` on `GET /api/v1/admin/users`; `submit_complaint`,
`view_own_complaints`, `view_assigned_complaints`, `review_complaints` and `view_scoped_complaints` on the
`/api/v1/concerns` endpoints; `manage_rules_and_settings` on the admin-only escalation and
breach-simulation endpoints (see "Complaint workflow" below). `reroute_complaints` and
`resolve_complaints` are defined but not checked on their own: rerouting and resolving go through
`POST /api/v1/concerns/{id}/review`, which requires `review_complaints` and that the complaint is
assigned to the caller.

### Login and JWT flow **[AR + TR]**

```
POST /api/v1/auth/login  {email, password}        (JSON body only; unknown fields such as "role" → 422)
  1. ALLOWED_EMAIL_DOMAINS empty?            → 503 (sign-in disabled, fail closed)
  2. email domain not allowed?               → 401 "Use your institutional email address"
  3. unknown account or wrong password       → 401 "Invalid email or password" (identical; unknown
                                               accounts still spend bcrypt time to avoid timing leaks)
  4. correct password but inactive account   → 403 "This account is disabled"
  5. success → {access_token, token_type: "bearer", expires_in}

JWT (HS256, signed with JWT_SECRET_KEY, lifetime ACCESS_TOKEN_EXPIRE_MINUTES):
  sub = user id, role (informational for the UI), typ = "access", iss = "safespeak-pes", iat, exp

Every protected request: Authorization: Bearer <token>
  get_current_user → verify signature, expiry, issuer, type → load user from DB
                   → missing/invalid/expired token or deleted user: 401
                   → inactive user: 403
  require_permission(...) → checks the role ON THE DATABASE ACCOUNT, not the token's role claim
```

Because the account is re-read on every request, deactivating a user or changing their role takes
effect immediately, even for tokens already issued. There are no refresh tokens yet; the client
signs the user out when the token expires.

`GET /api/v1/auth/me` returns the safe profile (id, name, email, role, department, authority level,
active status) plus the role's permission list, which the frontend uses only to decide what to show.

### Account creation **[AR + TR]**

There is no public sign-up. Accounts are created through `user_service.create_user`, which validates
the email domain, password length (10 characters to 72 bytes), and role rules. The database repeats the
key rules as CHECK constraints (valid role, lowercase email, authority level only and always for
authority roles, department required for complainant roles and department authorities).

For development, `python -m seed.demo_users` creates sample departments and one demo account per role
plus one inactive account. Passwords are random (or `DEMO_PASSWORD` if set) and are written only to the
git-ignored `backend/demo_credentials.local.txt`; the database stores bcrypt hashes. The seed refuses to
run when `ENVIRONMENT=production`.

### Email domains **[AR, decision D2]**

`ALLOWED_EMAIL_DOMAINS` (comma-separated, exact match, no subdomains implied) is the only place
institutional domains are defined. If it is empty, sign-in and account creation are refused and the API
logs a warning at startup. The local demo uses the reserved, clearly fake domain `safespeak.test`;
reserved test domains are accepted only outside production.

### Frontend **[TR]**

The login page has email and password only. After login the app calls `/auth/me` and routes by the role
the server returned. The access token is kept in `sessionStorage` (survives reload, cleared when the tab
closes); any 401 signs the user out. Route guards redirect anonymous users to `/login` and show a 403 page
for other roles' areas. These guards only control what is displayed; the API enforces every permission.

### Security decisions **[TR]**

- bcrypt with a configurable work factor (`BCRYPT_ROUNDS`, default 12); passwords over 72 bytes are
  refused rather than silently truncated.
- Passwords are never accepted in URLs, never returned (no response schema has a password field), and
  never logged (the server logs paths and status codes, not bodies).
- Out of scope for now: rate limiting, account lockout, refresh tokens, password reset.

## Complaint workflow (Review-II vertical slice)

### Flow

```
POST /api/v1/concerns  (authenticated, submit_complaint permission; body: description only)
  1. complaint code SSP-YYYY-NNNNNN from the id_counters table (UPDATE ... RETURNING, per IST year)
  2. AI triage: category + priority + confidence (TF-IDF + Logistic Regression, ml/artifacts/v1)
  3. review check: needs human review if category or priority confidence < threshold,
     or AI priority is High/Critical (REVIEW_HIGH_SEVERITY)
  4. routing: first level of the escalation chain with an active authority (never the complainant)
  5. TAT: REVIEW stage if flagged, RESOLUTION stage otherwise; deadline = start + rule hours
  6. stored: complaints row + immutable ai_predictions row + complaint_events (audit)

POST /api/v1/concerns/{id}/review  (review_complaints permission AND assigned to the caller)
  accept | override (new category/priority) | reroute (target authority) | resolve (note required)

POST /api/v1/concerns/{id}/simulate_breach  (admin, DEMO_MODE only)  → deadline moved into the past
POST /api/v1/concerns/escalate-overdue      (admin)                   → overdue complaints move up the chain
```

### Tables

| Table | Purpose |
|---|---|
| `complaints` | Current state: code, complainant, description, current category/priority, decision source, status, assignee, handling department, escalation level, TAT stage/rule/hours, deadline, resolution |
| `ai_predictions` | The model's original output (category, priority, both confidences, overall confidence, threshold used and its source, flag reasons, class probabilities). One per complaint; updates and deletes are refused. |
| `complaint_events` | Audit trail: action, actor user and role (empty = system), previous and new values, remarks, timestamp. Append-only. |
| `tat_rules` | Stage + optional category / priority / level → hours. Most specific match wins; a missing or ambiguous rule is an explicit 503, never a hidden default. |
| `escalation_rules` | Ordered chain per category (or the default chain): target role, authority level and scope (complainant's department, a fixed department, or institution-wide). |
| `id_counters` | Per-year sequence for complaint codes. |

All foreign keys are enforced (SQLite `PRAGMA foreign_keys=ON` on every connection) and CHECK constraints
restrict categories, priorities, statuses, decision sources, stages, scopes and confidence ranges.

### Statuses and decisions

`PENDING_REVIEW → ASSIGNED → (IN_PROGRESS) → RESOLVED`. Escalation keeps the status and sets
`escalation_level` and `escalated`; reaching the end of the chain sets `breached_at_top` once.
`decision_source` records whether the current category/priority are `AI_AUTO`, `AI_PENDING_REVIEW`,
`HUMAN_ACCEPTED` or `HUMAN_OVERRIDDEN`, so acceptance and override rates can be measured (RQ5).
`IN_PROGRESS` and `CLOSED` exist in the model but no endpoint sets them yet.

### Confidence threshold

Configured by `CONFIDENCE_THRESHOLD`. If unset, the threshold selected by `ml/train_triage.py` on the
validation split is used (recorded in `metadata.json`): the lowest threshold at which complaints at or above
it have both labels correct at least 70% of the time. For model v1 this is **0.24** (validation: 18.9% of
complaints handled without review at 70.6% joint accuracy; test: 20% at 61.1%). Every prediction stores the
threshold and its source.

### Security rules in this slice

- Identity, role and reviewer come only from the verified JWT and the database account.
- Request bodies reject unknown fields, so `user_id`, `reviewer_id`, `role`, `status` etc. cannot be supplied.
- Complaints outside a user's scope return 404 (not 403), so codes cannot be probed.
- Only the assigned authority can review; nobody can review or be routed their own complaint.
- Reroute targets must be other active authority accounts.
- The model files are loaded only if their SHA-256 matches `metadata.json`.
- `simulate_breach` exists only when `DEMO_MODE=true`, which is refused in production.
