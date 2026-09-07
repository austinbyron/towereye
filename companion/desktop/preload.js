const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("towereye", {
  env: () => ipcRenderer.invoke("env"),
  cameras: () => ipcRenderer.invoke("cameras"),
  start: (camera) => ipcRenderer.invoke("start", { camera }),
  stop: () => ipcRenderer.invoke("stop"),
  onLog: (fn) => ipcRenderer.on("log", (_e, line) => fn(line)),
  onState: (fn) => ipcRenderer.on("state", (_e, s) => fn(s)),
});
