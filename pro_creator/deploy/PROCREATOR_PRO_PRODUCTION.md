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
ADMIN_DASHBOARD_PASSWORD=<strong-password>
OWNER_EMAIL_ALLOWLIST=<authorized-owner-email-list>
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
