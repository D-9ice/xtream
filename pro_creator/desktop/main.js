const { app, BrowserWindow, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const path = require("path");

const DEFAULT_URL = process.env.PRO_CREATOR_URL || "http://localhost:3000";

function createWindow() {
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
    },
  });

  win.loadURL(DEFAULT_URL).catch(() => {
    win.loadFile(path.join(__dirname, "renderer", "offline.html"));
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http")) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    return { action: "allow" };
  });
}

function configureAutoUpdates() {
  const updateUrl = process.env.PRO_CREATOR_UPDATE_URL;
  if (!updateUrl) {
    return;
  }
  autoUpdater.setFeedURL({ provider: "generic", url: updateUrl });
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
