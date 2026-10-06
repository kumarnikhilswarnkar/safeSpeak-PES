# Security and personal-data protection

Status legend: **Implemented** (in code and tested) · **Future** (planned, not implemented).
Nothing below is claimed unless marked Implemented.

| Control | Status | Where |
|---|---|---|
| Passwords hashed with bcrypt (cost 12), >72-byte passwords refused, never returned or logged | Implemented | `app/core/security.py`; `test_security.py`, `test_privacy.py` |
| JWT validation (signature, expiry, issuer, type); account re-read on every request; inactive → 403 | Implemented | `app/api/deps.py`; `test_auth_api.py` |
| Server-side RBAC and complaint scope; out-of-scope complaints return 404 | Implemented | `app/core/permissions.py`, `complaint_service.can_view`; `test_rbac_matrix.py` |
| Request validation (unknown fields rejected, length limits) | Implemented | `app/schemas/*` |
| SQL injection protection (SQLAlchemy bound parameters) | Implemented | all data access |
| Bound parameter values never in SQL errors/logs (`hide_parameters`) | Implemented | `app/db/session.py`; `test_privacy.py` |
| No complaint text, passwords or tokens in application logs; proxy logs path without query string | Implemented | `test_privacy.py`; `deploy/nginx/*.conf` |
| Database unavailable → 503 with a generic message | Implemented | `app/main.py`; `test_privacy.py` |
| Append-only audit trail and AI predictions (ORM guard **and** database triggers, incl. TRUNCATE on PostgreSQL) | Implemented | migration `c7e4a9d2b310`; `test_audit_triggers.py`, `test_postgres.py` |
| Least-privilege database account for the API (no DELETE/TRUNCATE/DDL) | Implemented (Docker/PostgreSQL) | `deploy/postgres/*`; CI step, `test_postgres.py` |
| Secrets only in environment / git-ignored `.env`; weak JWT secret refused | Implemented | `app/core/config.py`, `scripts/generate_env.py`, `.dockerignore` |
| Non-root containers; no secrets in images | Implemented | `backend/Dockerfile`, `frontend/Dockerfile` |
| Login rate limiting (10/min per IP) and API rate limiting at the proxy | Implemented (Docker stack) | `deploy/nginx/default.conf` |
| Security headers (CSP, nosniff, frame denial, no referrer) | Implemented (Docker stack) | `deploy/nginx/*.conf` |
| HTTPS/TLS with HSTS | Future (configuration prepared) | `deploy/nginx/tls.conf`, Phase 8 |
| Encryption at rest | Future (provided by a managed PostgreSQL service; not by the app) | Phase 8 |
| Backups and restore testing | Future | `docs/deployment.md` |
| Account lockout, refresh tokens, password reset, institutional SSO | Future | — |
| Token storage: `sessionStorage` (cleared when the tab closes); HttpOnly cookies | Implemented / Future | `frontend/src/auth/AuthContext.jsx` |

## Personal data stored

| Data | Why | Who can see it | In API responses | In logs | In ML training |
|---|---|---|---|---|---|
| Name | display, accountability | self, admin, authorised readers of a complaint | yes (no email) | no | never |
| Institutional email | login identity | self, admin | only `/auth/me`, admin user list | no | never |
| Role, department, authority level | access control, routing | authorised readers | yes | no | never |
| Complaint text, resolution note, reviewer remarks | the complaint and decisions | complainant, assigned authority, scoped viewer, admin | to those only | no | never automatically (see below) |
| Password hash | authentication | nobody | never | never | never |
| Client IP address | proxy access log | server operator | no | yes (proxy) | never |

Not collected: SRN, phone number, address, files. Anonymous-to-reviewer mode (decision D7) is future work.

## ML data separation

The backend loads a pinned, checksummed model artifact and never trains. Training uses only approved,
versioned datasets in `ml/data`. A real complaint could enter a training dataset only after institutional
approval, consent where required, an administrator export, anonymisation with manual checking, labelling
by two annotators, a new dataset version with a checksum, retraining and re-evaluation.
