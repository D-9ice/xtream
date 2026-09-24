const { app, BrowserWindow, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const path = require("path");

// Prefer IPv4 loopback to avoid localhost -> ::1 resolution issues.
const DEFAULT_URL = process.env.PRO_CREATOR_URL || "http://127.0.0.1:3000";

function parseHttpUrl(value, label) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${label} must be a valid URL.`);
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(`${label} must use http or https.`);
  }
  return parsed;
}

function openExternalSafely(url) {
  try {
    const parsed = parseHttpUrl(url, "External URL");
    void shell.openExternal(parsed.toString());
  } catch {
    // Deny unsupported or malformed schemes silently.
  }
}

function createWindow() {
  const appUrl = parseHttpUrl(DEFAULT_URL, "PRO_CREATOR_URL");
  const allowedOrigin = appUrl.origin;
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#020617",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.loadURL(appUrl.toString()).catch(() => {
    win.loadFile(path.join(__dirname, "renderer", "offline.html"));
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternalSafely(url);
    return { action: "deny" };
  });

  win.webContents.on("will-navigate", (event, url) => {
    try {
      const target = new URL(url);
      if (target.origin === allowedOrigin) {
        return;
      }
      event.preventDefault();
      openExternalSafely(url);
    } catch {
      event.preventDefault();
    }
  });
}

function configureAutoUpdates() {
  const updateUrl = process.env.PRO_CREATOR_UPDATE_URL;
  if (!updateUrl) {
    return;
  }
  const parsedUpdateUrl = parseHttpUrl(updateUrl, "PRO_CREATOR_UPDATE_URL");
  if (app.isPackaged && parsedUpdateUrl.protocol !== "https:") {
    throw new Error("PRO_CREATOR_UPDATE_URL must use https in packaged builds.");
  }
  autoUpdater.setFeedURL({ provider: "generic", url: parsedUpdateUrl.toString() });
  autoUpdater.on("error", (error) => {
    console.error("Auto-update error:", error);
  });
  autoUpdater.on("update-available", () => {
    console.log("Update available.");
  });
  autoUpdater.on("update-downloaded", () => {
    console.log("Update downloaded. Will install on quit.");
  });
  autoUpdater.checkForUpdatesAndNotify();
}

app.whenReady().then(() => {
  createWindow();
  configureAutoUpdates();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
