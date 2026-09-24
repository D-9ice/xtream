# Pro Creator Execution Guide (Single-Tenant Now, SaaS Later)

This document is the code-execution checklist to take Pro Creator from the current MVP to:

1. A reliable **single-tenant internal tool** (you only).
2. A **multi-tenant SaaS** (many users, isolation, billing-critical) afterward with minimal rework.

Principle: **Build SaaS-grade foundations now** (migrations, tenant-ready schema, deletion correctness, deterministic builds),
but keep product behavior **single-tenant** until the workflows are stable.

---

## Current Baseline (Already In Repo)

- Backend: FastAPI + SQLModel, JWT auth gate, credits/billing + Stripe webhook, S3/local storage abstraction, Celery worker tasks, orchestration queue/schedules, ffmpeg video render/export, `/metrics`.
- Frontend: Next.js dashboard UI + lint/tests/build in CI, basic admin dashboard access pattern.
- Deploy: docker-compose + production override (Caddy TLS, Postgres, Redis, S3/Spaces), preflight, backup runbook, optional observability profile.

---

## Phase 1: Single-Tenant With SaaS-Grade Foundations

Goal: everything runs in production topology (Docker Compose + Postgres + Redis + S3) with predictable upgrades, safe deletion,
and a schema that will not require a rewrite to become multi-tenant.

### Phase 1 Status (As Of 2026-09-24)

- Migrations framework: Implemented (Alembic scaffolding added; production requires Alembic).
- Tenant-ready schema (single tenant): Implemented (`tenant_id` default `"default"` + query scoping).
- Deletion correctness: Implemented (project delete/delete-all also delete clips/jobs/schedules).
- Deterministic builds: Implemented for frontend (`frontend/package-lock.json`, CI uses `npm ci`).
- Queue model cleanup: Implemented (in-process runner disabled when `ENABLE_CELERY=true`).
- Production-topology smoke test: Implemented (Compose smoke test + CI job).

### 1) Migrations (Alembic) [BLOCKER FOR SaaS]

- Implemented:
  - Alembic scaffolding + baseline revisions in `pro_creator/backend/alembic_migrations/`.
  - Runtime migration entrypoint in `pro_creator/backend/app/migrations.py`.
  - `ENVIRONMENT=production` now fails fast if Alembic isn't installed (no silent schema drift).
- Note:
  - Dev/offline still has a best-effort fallback for restricted environments.

Acceptance:
- Fresh Postgres database + `alembic upgrade head` produces the full schema.
- Upgrading between versions is reproducible (no silent try/except schema changes).

### 2) Tenant-Ready Schema (Single Tenant Enabled)

Add `tenant_id` (or `workspace_id`) to the data model, but keep the app behaving as a single tenant.

Implemented:
- `tenant_id` added to the core models and scoped throughout routers/services using `current_tenant_id()`.
- Phase 1 tenant is resolved from `DEFAULT_TENANT_ID` (defaults to `"default"`).
- Storage keying is still `project_id/...` for now; Phase 2 can change to `tenant_id/project_id/...` when multi-tenant ships.

Acceptance:
- No UI changes required (still “one workspace”), but the backend enforces tenant scoping internally.

### 3) Deletion Correctness (No Orphans)

Problem to solve:
- Project deletion currently deletes `Scene` + `Project` rows and assets, but other tables can be left orphaned
  (jobs/schedules/clips).

Implemented:
- `DELETE /project/{id}`, `DELETE /project/`, and stale purge now delete:
  - scenes, clips, orchestration jobs, orchestration schedules, project row, and then storage prefix.

Acceptance:
- After delete-all, the database contains no rows referencing deleted project ids.
- After delete-all, pipeline UI stays empty after refetch.

### 4) Deterministic Builds + CI Alignment

Implemented:
- Frontend now has `pro_creator/frontend/package-lock.json`.
- CI uses `npm ci --legacy-peer-deps` for frontend.
- Frontend Dockerfile uses `npm ci` with the lockfile.

Acceptance:
- Fresh clone + CI passes on a clean runner.
- Docker builds don’t drift dependency versions over time.

### 5) Production Queue Model (No In-App Background Loops)

Implemented:
- In-process runner endpoints are disabled when `ENABLE_CELERY=true`.
- Celery Beat is the production schedule authority.
- Due-schedule dispatch is protected by a Redis distributed lock.
- Scheduled production uses the same approved workflow/Grok Imagine path as normal production.

Acceptance:
- With `ENABLE_CELERY=true`, queue processing happens entirely via worker(s).
- Schedules run via beat/scheduler, not via an app-process async loop.

### 6) Auth Hardening (Even Single-Tenant)

Work:
- Review all auth endpoints and lock down anything that should not be public in production.
- Confirm admin-only endpoints are protected and not usable without proper access tokens.
- Keep `ADMIN_2FA_ENABLED=false` until OTP is actually implemented end-to-end.

Acceptance:
- In production configuration (`AUTH_REQUIRED=true`), all non-public endpoints require a valid JWT.

### 7) Integration Test Harness (Compose-Based)

Implemented:
- Compose smoke test starts Redis + MinIO + backend and validates create/script/storage/delete-all.
- CI runs the smoke test.
- Optional hardening: add a "full-stack smoke" that also validates Celery worker processing (recommended if production will rely on Celery).

Acceptance:
- One command can validate the “production topology” works end-to-end.

---

## Phase 1.5: Product Hardening (Still Single-Tenant)

Goal: reduce surprises before adding multi-tenant complexity.

- Maintain bounded xAI/Grok provider retries, cancellation, timeout handling, and validated media outputs.
- Ensure billing/credits are consistent and idempotent for all billable actions.
- Maintain the global authentication guard so expired/invalid sessions redirect cleanly instead of leaking protected API errors.
- Break up the monolithic dashboard component (`frontend/app/page.clean.tsx`) into maintainable modules.

---

## Phase 2: Multi-Tenant SaaS (After Phase 1 Is Stable)

Only start this after the single-tenant workflows are stable and you’ve run them in a production-like environment.

### 0) Already Implemented In Phase 1 (Do Not Rebuild)

- `tenant_id` columns exist and are used across core tables.
- A single-tenant resolver (`DEFAULT_TENANT_ID`) exists as the Phase 1 default.

### 1) Tenant Provisioning (New Work)

- Workspace creation, membership/invites, roles.
- Every request resolves a tenant context (subdomain, header, or token claims).

### 2) Isolation Guarantees (New Work)

- Enforce tenant scoping in every query.
- Optionally add Postgres RLS (Row-Level Security) once the model is clean.
- Storage prefix moves to `tenant_id/project_id/...` (breaking change; plan a migration).

### 3) Billing-Critical Implementation (New Work)

- Stripe subscriptions/payments: webhook idempotency and reconciliation.
- Credit ledger invariants:
  - Atomic reserve/consume/refund
  - No negative balances unless explicitly allowed
  - Exactly-once application of webhooks
- Audit logs for admin billing actions.

### 4) Abuse / Rate Limits / Quotas

- Per-tenant quotas and backpressure (queue limits, rate limits).
- Per-tenant cost caps.

### 5) Observability + Operations

- Structured logs with request_id + tenant_id + job_id.
- Error reporting (Sentry or equivalent).
- Dashboards + alerts for queue failures, webhook failures, latency spikes.

---

## Suggested Execution Order (Recommended)

1. Alembic migrations (Phase 1.1)
2. Tenant-ready schema (Phase 1.2)
3. Deletion correctness + tests (Phase 1.3)
4. Deterministic builds + CI alignment (Phase 1.4)
5. Queue model cleanup (Phase 1.5)
6. Compose-based integration tests (Phase 1.7)
7. Product hardening + UX polish (Phase 1.5)
8. Multi-tenant provisioning + isolation (Phase 2)
9. Billing-critical + audit + quotas (Phase 2)

---

## Non-Goals For Phase 1 (Explicitly Not Now)

- Multi-tenant UI and workspace switching.
- Complex subscription tiers and proration logic.
- Full OTP/2FA until the security model is finalized.
