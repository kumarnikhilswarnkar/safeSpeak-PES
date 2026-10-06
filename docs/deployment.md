# Deployment

Status: local Docker and Codespaces deployment are implemented (Phase 1). Server deployment with
HTTPS, backups and GHCR images is Phase 8; the steps below are the plan and are **not yet performed**.

## Environments

| | Local laptop (native) | Docker / Codespaces | Production server (Phase 8) |
|---|---|---|---|
| Start | `uvicorn` + `npm run dev` | `docker compose up --build` | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` |
| Database | SQLite file | PostgreSQL container | PostgreSQL (managed service or server container) |
| `ENVIRONMENT` | development | development (demo accounts allowed) | **production** |
| Demo accounts / `DEMO_MODE` | yes | yes | **no** (refused by the backend in production) |
| Email domain | `safespeak.test` | `safespeak.test` | institutional domain |
| Transport | http://localhost | http (Codespaces forwards over HTTPS) | **HTTPS** (nginx `deploy/nginx/tls.conf`, HSTS) |
| Secrets | `backend/.env` | `.env` from `scripts/generate_env.py` | `.env` on the server (or a secrets manager), never in Git |

## Production checklist (Phase 8)

1. Server (VM) with Docker Engine + Compose; firewall open for 80/443 only.
2. DNS name pointing at the server; TLS certificate (e.g. Let's Encrypt) in `deploy/certs/`
   (`fullchain.pem`, `privkey.pem`, git-ignored).
3. `.env`: `ENVIRONMENT=production`, `DEMO_MODE=false`, `SEED_DEMO_USERS=false`,
   `ALLOWED_EMAIL_DOMAINS=<institution>`, fresh random passwords and `JWT_SECRET_KEY`.
4. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
   (or pull the GHCR images built by `release.yml`).
5. `docker compose run --rm seed` (base data only; institution replaces the sample departments/rules).
6. Create real accounts through an administrator process (user-management endpoints are future work).
7. Backups (below) and a restore test before go-live.

## Backups and recovery (planned, not yet implemented)

| Item | Plan |
|---|---|
| Frequency | Daily `pg_dump --format=custom` (plus point-in-time recovery if a managed database is used) |
| Retention | 7 daily, 4 weekly, 6 monthly; encrypted; stored off the server |
| Restore test | Monthly: restore into a scratch database, run `scripts/smoke_test.py` and compare row counts; record the result |
| Disaster recovery | New server → restore latest backup → redeploy images and the pinned model artifact → rotate secrets. Targets: RPO ≤ 24 h (minutes with PITR), RTO ≤ 4 h |

Local SQLite development database: `powershell -File scripts/backup_sqlite.ps1` before schema changes.

## Rollback

- Application: redeploy the previous image tag.
- Schema: `docker compose run --rm migrate alembic downgrade <revision>` (every migration is reversible),
  or restore the backup taken before the upgrade.
- Local Docker data: `docker compose down -v` removes the PostgreSQL volume entirely.
