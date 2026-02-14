# Frontend

Next.js 14 + TypeScript + Tailwind UI for Pro Creator.

## Local development

1. Install dependencies.
2. Start the dev server.

The backend API is expected at `http://127.0.0.1:8000` by default.
Override with `NEXT_PUBLIC_API_BASE` if needed.

```zsh
npm install
npm run dev
```

## Run backend + frontend together (VS Code task)

Use the workspace task to launch both servers in one step:

1. Open the Command Palette.
2. Run **Tasks: Run Task**.
3. Select **Pro Creator: Dev (Backend + Frontend)**.

Keyboard shortcut (macOS): **Cmd + Shift + R**.

The task starts:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://localhost:3000`

## Backend manual start

If you want to run the backend directly, use the explicit app directory:

```zsh
/Users/williamdickson/Desktop/Pro_Creator_App/.venv/bin/python -m uvicorn app.main:app --reload --port 8000 --app-dir /Users/williamdickson/Desktop/Pro_Creator_App/pro_creator/backend
```

## App icon + favicon

Place the provided icon assets in:

- `frontend/public/app-icon.png`
- `frontend/public/favicon.ico`

Next.js will serve them automatically as the app icon and favicon.
