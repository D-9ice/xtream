# Production deployment (DigitalOcean + Ubuntu 22.04)

This guide deploys the stack to a single VM using Docker Compose, Caddy, Postgres, Redis, and DigitalOcean Spaces.

## Prerequisites

- Ubuntu 22.04 VPS with Docker + Docker Compose installed
- A domain pointed to the VPS
- DigitalOcean Spaces bucket + keys
- Postgres credentials (defined in `.env.production`)

## Steps

1. Copy `.env.production.example` to `.env.production` and fill values.
2. Replace all default secrets (`change-me`, `ChangeMe123!`) before first boot.
3. Prefer file-based secrets via `*_FILE` variables in `.env.production` (see `deploy/secrets/README.md`).
4. For managed secrets, you can enable AWS Secrets Manager via `AWS_SECRETS_ENABLED=true` and `*_AWS_SECRET_ID` mappings.
5. Validate compose files before deployment.
6. On the server, clone this repo and `cd pro_creator`.
7. Run Docker Compose with the production override.

Example commands:

```zsh
cp deploy/.env.production.example .env.production
export $(cat .env.production | xargs)
./deploy/preflight.sh
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
```

To run with observability enabled (Prometheus + Alertmanager + Grafana):

```zsh
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile observability up -d --build
```

## Notes

- Caddy automatically provisions TLS for `DOMAIN_NAME`.
- API routes are served from `/api` and proxied to the backend.
- `/metrics` is blocked at the edge by default in production.
- Frontend runtime URLs should be set with `NEXT_PUBLIC_API_BASE` and `NEXT_PUBLIC_PROJECTS_BASE`.
- Asset URLs should be stored in Spaces (`S3_PUBLIC_URL`).
- xAI/Grok is the supported generation stack; configure the required `XAI_*` and `GROK_IMAGINE_*` values before startup.
- To enable billing/credit purchases, configure Paystack and/or Stripe production credentials and price IDs as documented in `.env.production.example`.
- For branded receipt email delivery, use a transactional SMTP service such as Amazon SES and fill the `EMAIL_SMTP_*` values.
- Postgres is included in the production override and used via `DATABASE_URL`.
- Redis and Celery are included in the production override and are enabled via `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, and `ENABLE_CELERY=true`.
- Use `deploy/BACKUP_RESTORE.md` for backup and recovery procedures.
- Secrets can come from direct env vars, `*_FILE` mounted files, or AWS Secrets Manager (`*_AWS_SECRET_ID`).
- Admin dashboard access uses `ADMIN_DASHBOARD_PASSWORD` (separate from user login password).
- Optional owner-dashboard TOTP is supported through `ADMIN_2FA_ENABLED=true` with a configured `ADMIN_2FA_TOTP_SECRET`.
- Observability profile exposes localhost-only ports:
  - Prometheus: `127.0.0.1:9090`
  - Alertmanager: `127.0.0.1:9093`
  - Grafana: `127.0.0.1:3001`

## Admin Access

The subscriptions management dashboard (`/admin`) is protected by two layers:

1. Owner gate: the caller must be an admin user, and in production their email must be listed in `OWNER_EMAIL_ALLOWLIST`.
2. Dashboard gate: enter `ADMIN_DASHBOARD_PASSWORD` on the Admin Access screen to receive a short-lived access token used for admin endpoints.

Operational notes:

- If `AUTH_REQUIRED=true` (production default), you must sign in first (store JWT in `pc_token`) before admin actions will work.
- If you rotate `JWT_SECRET`, existing browser tokens become invalid; sign out (or clear `pc_token`) and sign in again.
