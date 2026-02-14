# Database Notes (Local)

This project currently uses a lightweight "startup migration" approach:

- The backend calls `init_db()` on startup.
- If a table/column is missing (common when switching branches or restoring old DB files), the app will add the missing schema elements automatically for local/dev.
- The singleton `AppSettings` row (id=1) is created on startup if missing and is used for local runtime toggles such as the password gate.

Production guidance:

- Prefer explicit migrations (Alembic) before deploying to a real multi-user environment.
- Keep `AUTH_REQUIRED=true` in production and manage credentials via infrastructure and secrets.

