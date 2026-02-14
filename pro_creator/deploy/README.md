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
- Asset URLs should be stored in Spaces (`S3_PUBLIC_URL`).
- Set `TTS_PROVIDER` to `xtts` or `elevenlabs` and provide the matching env vars.
- The production compose file includes an `xtts` service running on port `8020` (override `XTTS_IMAGE` if needed).
- Postgres is included in the production override and used via `DATABASE_URL`.
- Use `deploy/BACKUP_RESTORE.md` for backup and recovery procedures.
- Secrets can come from direct env vars, `*_FILE` mounted files, or AWS Secrets Manager (`*_AWS_SECRET_ID`).
- Admin dashboard access uses `ADMIN_DASHBOARD_PASSWORD` (separate from user login password).
- `ADMIN_2FA_ENABLED` exists as a scaffold flag; keep it `false` until OTP verification is implemented.
- Observability profile exposes localhost-only ports:
  - Prometheus: `127.0.0.1:9090`
  - Alertmanager: `127.0.0.1:9093`
  - Grafana: `127.0.0.1:3001`
