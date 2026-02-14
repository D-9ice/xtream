# Backup And Restore Runbook

## Scope

This runbook covers:
- Postgres database (`postgres` service volume)
- Object storage bucket (`S3_BUCKET`)
- Production environment config (`.env.production`)

## Backup Schedule

- Postgres: daily full dump + 7-day retention
- S3 bucket: daily sync + versioning enabled at provider
- `.env.production`: backup to secure secrets manager on each change

## Postgres Backup

Run from the host that has Docker access:

```zsh
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "backup-postgres-$(date +%F).sql"
```

## Postgres Restore

```zsh
cat backup-postgres-YYYY-MM-DD.sql | docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

## Object Storage Backup (Spaces/S3)

Use your preferred tool (for example `aws s3 sync`) with credentials scoped to read-only backup:

```zsh
aws s3 sync "s3://${S3_BUCKET}" "./backup-s3-$(date +%F)" --endpoint-url "${S3_ENDPOINT}"
```

## Config Backup

- Never commit `.env.production`.
- Store production secrets in a managed secret store.
- Keep a versioned, encrypted backup of key variables:
  - `JWT_SECRET`
  - `ADMIN_PASSWORD`
  - `POSTGRES_PASSWORD`
  - `S3_SECRET_KEY`
  - provider API keys

## Recovery Drill

Run at least monthly:
- Restore DB into a staging environment.
- Validate app login, project listing, and export paths.
- Validate sampled objects from S3 backup.
