# Pro Creator Pro — Production Deployment

## Target topology

- Vercel: Next.js frontend only (`pro_creator/frontend`)
- Persistent backend host: FastAPI + FFmpeg + Celery worker
- Postgres: production database
- Redis: Celery broker/result backend
- S3-compatible object storage: generated project/media assets
- xAI/Grok: text, image, video and TTS provider

## Vercel project

Project name: `procreator-pro`

Root Directory:

```text
pro_creator/frontend
```

Framework: Next.js

Install command:

```text
npm ci
```

Build command:

```text
npm run build
```

Required Vercel environment values once the backend URL is known:

```text
PRO_CREATOR_BACKEND_ORIGIN=https://<production-backend-host>
NEXT_PUBLIC_API_BASE=https://<production-backend-host>
NEXT_PUBLIC_PROJECTS_BASE=https://<production-asset-origin>/projects
NEXT_PUBLIC_ASSET_ORIGIN=https://<production-asset-origin>
```

Do not use localhost/127.0.0.1 values in Vercel Production.

## Backend production minimum

The backend must run persistently and must not be deployed as a short-lived frontend serverless function. Production must provide real values for at least:

```text
ENVIRONMENT=production
AUTH_REQUIRED=true
STRICT_PROVIDER_VALIDATION=true
JWT_SECRET=<strong-random-secret>
ADMIN_EMAIL=<owner-admin-email>
ADMIN_PASSWORD=<strong-password>
ADMIN_BOOTSTRAP_SYNC=false
ADMIN_DASHBOARD_PASSWORD=<different-strong-password>
OWNER_EMAIL_ALLOWLIST=<owner-admin-email>
ALLOWED_ORIGINS=https://<vercel-production-domain>
RATE_LIMIT_ENABLED=true
DATABASE_URL=<production-postgres-url>
STORAGE_BACKEND=s3
S3_BUCKET=<production-bucket>
S3_REGION=<region>
S3_ENDPOINT=<s3-compatible-endpoint>
S3_PUBLIC_URL=<public-asset-origin>
S3_ACCESS_KEY=<secret>
S3_SECRET_KEY=<secret>
REDIS_URL=<production-redis-url>
CELERY_BROKER_URL=<production-redis-url>
CELERY_RESULT_BACKEND=<production-redis-url>
ENABLE_CELERY=true
XAI_API_KEY=<secret>
XAI_BASE_URL=https://api.x.ai/v1
XAI_TEXT_MODEL=grok-4.20-beta-latest-non-reasoning
XAI_IMAGE_MODEL=grok-imagine-image
XAI_VIDEO_MODEL=grok-imagine-video
XAI_TTS_VOICE_ID=eve
PAYSTACK_SECRET_KEY=<secret-if-paystack-enabled>
PAYSTACK_CALLBACK_URL=https://<vercel-production-domain>/?checkout=success&provider=paystack
```

If Stripe is enabled, provide its production secret/webhook/price variables as well.

## Production gate

Do not mark production complete until all of the following pass:

1. Frontend install, lint, tests and production build.
2. Backend tests and production startup validation.
3. Postgres migration to latest Alembic revision.
4. Redis/Celery worker connectivity.
5. S3-compatible read/write test.
6. xAI provider smoke test.
7. Browser smoke test through the Vercel production URL.
8. Auth/admin access test.
9. Script -> character -> production queue -> completed media end-to-end test.
10. Payment callback test for each enabled payment provider.

## Naming

Human-facing product name: `Pro Creator Pro`

Vercel/project slug: `procreator-pro`


## Owner credential bootstrap / recovery

The owner identity is intentionally configured only on the persistent backend host. Do not place owner passwords in GitHub, Vercel frontend variables, client-side code, or screenshots.

Required owner values:

```text
ADMIN_EMAIL=<private owner email>
OWNER_EMAIL_ALLOWLIST=<same owner email>
ADMIN_PASSWORD=<strong primary owner login password>
ADMIN_DASHBOARD_PASSWORD=<different strong second-gate password>
ADMIN_BOOTSTRAP_SYNC=true
```

For a first bootstrap or credential recovery:

1. Set the five values above on the backend host.
2. Restart the backend once. Startup will create the owner if missing, or reset the matching owner's password/role if it already exists. It also enables persisted owner mode.
3. Use the hidden admin keyboard trigger in the frontend.
4. Authenticate first with `ADMIN_EMAIL` + `ADMIN_PASSWORD`.
5. Unlock the second gate with `ADMIN_DASHBOARD_PASSWORD` (and TOTP when enabled).
6. Immediately set `ADMIN_BOOTSTRAP_SYNC=false` on the backend host and restart again.
7. Confirm owner login still works.

`ADMIN_BOOTSTRAP_SYNC=false` is the steady-state configuration. Leaving it true would cause the environment-defined owner password to be re-applied on every backend restart.

Production validation also requires `ADMIN_EMAIL` to be included in `OWNER_EMAIL_ALLOWLIST`.
