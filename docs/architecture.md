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
