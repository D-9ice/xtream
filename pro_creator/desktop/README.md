# Pro Creator Desktop

Electron shell for the Pro Creator web app.

## Development

```zsh
npm install
npm run dev
```

The desktop app expects the frontend to be running at `http://localhost:3000`.
Override with `PRO_CREATOR_URL` if needed.

## Branding assets

Place the provided icon files in `desktop/assets/`:

- `icon.png` (1024x1024)
- `icon.icns` (macOS build)
- `icon.ico` (Windows build)

## Auto-update

Set the update feed URL before launching the desktop shell:

```zsh
export PRO_CREATOR_UPDATE_URL="https://your-update-host/desktop"
```

## Build installers

```zsh
npm run build
```

Build artifacts land in `desktop/dist/` (DMG on macOS, NSIS on Windows, AppImage on Linux).
