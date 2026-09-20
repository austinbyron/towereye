const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("towereye", {
  env: () => ipcRenderer.invoke("env"),
  cameras: () => ipcRenderer.invoke("cameras"),
  start: (camera, obs, die) => ipcRenderer.invoke("start", { camera, obs, die }),
  stop: () => ipcRenderer.invoke("stop"),
  openObs: () => ipcRenderer.invoke("openObs"),
  updateState: () => ipcRenderer.invoke("updateState"),
  updateInstall: () => ipcRenderer.invoke("updateInstall"),
  onUpdate: (fn) => ipcRenderer.on("update", (_e, u) => fn(u)),
  onLog: (fn) => ipcRenderer.on("log", (_e, line) => fn(line)),
  onState: (fn) => ipcRenderer.on("state", (_e, s) => fn(s)),
});
