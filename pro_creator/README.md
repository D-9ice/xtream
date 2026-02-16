# Pro Creator

Pro Creator is a modular AI-powered content creation platform with a production-ready backend, async jobs, and a full Next.js UI.

## What’s included

- **FastAPI backend** with JWT auth, RBAC hooks, and metrics
- **Async jobs** with Celery + Redis
- **Storage abstraction** for local or S3-compatible backends
- **Next.js frontend** with editor, automation, and voice workflows
- **TTS provider switching** (XTTS or ElevenLabs)
- **Lip sync artifacts** (viseme timelines) for downstream animation (Rhubarb optional)
- **Deployment assets** for single-VM production (Caddy + Spaces)

## Repository layout

```text
pro_creator/
  backend/
  frontend/
  android_companion/
  projects/
```

## Backend quickstart

1. Create a Python 3.10+ environment.
2. Install backend dependencies.
3. Start the API.

The API will be available at `http://127.0.0.1:8000/docs`.

## One-command dev (frontend + backend)

From the repository root:

```zsh
cd pro_creator
npm install
npm run dev
```

This runs the FastAPI backend on port 8000 and the Next.js frontend on port 3000.

### Dependency lockfile policy

Lockfiles are committed per package:

- Repo root: `pro_creator/package-lock.json` (root dev tools like `concurrently`)
- Frontend: `pro_creator/frontend/package-lock.json`

Use `npm ci` in each package directory when possible for deterministic installs.

### Experimental UI

Some UI panels are gated behind `NEXT_PUBLIC_EXPERIMENTAL_FEATURES=true` (disabled by default).

## Production-ready stack (Docker Compose)

This includes **FastAPI**, **Next.js**, **Redis**, **Celery**, and **MinIO (S3-compatible)**.

```zsh
cd pro_creator
cp .env.example .env
docker compose up --build
```

Services:

- Frontend: `http://localhost:3000`
- Backend docs: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

Default admin credentials (change in `.env`):

- Email: `admin@procreator.local`
- Password: `ChangeMe123!`

## Production deployment (Single VM)

For DigitalOcean + Ubuntu 22.04, use the production override with Caddy + Spaces. See `deploy/README.md` for a full checklist.

```zsh
cp deploy/.env.production.example .env.production
export $(cat .env.production | xargs)
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
```

## Frontend direction

The frontend runs on **Next.js 16 + TypeScript + Tailwind CSS**. See `frontend/README.md` for local dev instructions.

### UI behavior notes

- The header shows **Sign out** when a `pc_token` is present; sign-out clears the token and redirects to `/login` if the tab cannot be closed.
- Clicking **Sign out** opens an account panel with password change controls.
- Password fields in the account panel include show/hide (eye) toggles.
- The API badge is visible in development, but hidden in production builds.

### TTS providers

You can switch between XTTS (self-hosted) and ElevenLabs via `TTS_PROVIDER` and the Voice panel selector.
Set `XTTS_ENDPOINT` for XTTS or `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID` for ElevenLabs.

### Image generation provider

Image generation supports OpenAI Images with quality-first defaults. Set:

- `IMAGE_PROVIDER=openai`
- `OPENAI_API_KEY=<your key>`
- Optional tuning: `OPENAI_IMAGE_MODEL`, `OPENAI_IMAGE_SIZE`, `OPENAI_IMAGE_QUALITY`

If `IMAGE_PROVIDER=auto`, the backend uses OpenAI when a key is configured, otherwise local placeholder generation.

### Lip sync (Rhubarb)

Lip sync artifacts are generated automatically after voice generation. For higher
quality visemes, install the Rhubarb binary and set `RHUBARB_PATH` (or add it to
your PATH). Control auto-generation with `AUTO_LIPSYNC`.

You can use the helper script to download and verify Rhubarb:

```zsh
cd pro_creator/backend
python scripts/install_rhubarb.py --sha256 <EXPECTED_SHA256>
```

Set `RHUBARB_PATH` to the installed binary.

To validate ElevenLabs once keys are available, run `backend/scripts/validate_elevenlabs.py`.

To validate ElevenLabs credentials, run the helper script:

```zsh
python backend/scripts/validate_elevenlabs.py
```

## Desktop app (Electron)

A desktop shell lives in `desktop/`. It loads the running web app (default `http://localhost:3000`).

```zsh
cd desktop
npm install
npm run dev
```

To build installers:

```zsh
npm run build
```

Build artifacts are saved to `desktop/dist/`.

## Next steps

- Add dedicated monitoring dashboards (Grafana/Prometheus)
- Expand orchestration templates and reporting
- Harden production secrets management

## Execution roadmap

See `README_EXECUTION.md` for the step-by-step code checklist to ship single-tenant first and then evolve into multi-tenant SaaS.
