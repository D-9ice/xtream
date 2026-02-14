const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("proCreator", {
  version: "0.1.0",
});
