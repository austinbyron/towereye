// towereye desktop: a thin wrapper around `python -m towereye watch`.
// The Python process stays the source of truth; this window only starts and
// stops it, helps pick the right camera by what it sees, and mirrors status.
const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const readline = require("readline");

const REPO = path.resolve(__dirname, "..", "..");
const PYTHON = path.join(REPO, ".venv", "bin", "python");

let win = null;
let watch = null;

function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

function createWindow() {
  win = new BrowserWindow({
    width: 460,
    height: 760,
    minWidth: 380,
    title: "towereye",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true },
  });
  win.loadFile("index.html");
}

ipcMain.handle("env", () => ({
  repo: REPO,
  pythonOk: fs.existsSync(PYTHON),
  running: watch !== null,
}));

ipcMain.handle("cameras", () => new Promise((resolve) => {
  if (watch) return resolve({ error: "stop the watch before scanning: it owns the camera" });
  const p = spawn(PYTHON, ["-m", "towereye", "cameras", "--json"], { cwd: REPO });
  let out = "";
  p.stdout.on("data", (d) => { out += d; });
  p.on("close", () => {
    try { resolve({ cameras: JSON.parse(out) }); }
    catch { resolve({ error: "camera scan failed", raw: out }); }
  });
  p.on("error", (e) => resolve({ error: String(e) }));
}));

ipcMain.handle("start", (_e, { camera }) => {
  if (watch) return { ok: false, error: "already running" };
  const args = ["-u", "-m", "towereye", "watch", "--camera", String(camera)];
  watch = spawn(PYTHON, args, { cwd: REPO, env: { ...process.env, PYTHONUNBUFFERED: "1" } });
  send("state", { running: true, camera });
  const forward = (stream) => {
    readline.createInterface({ input: stream }).on("line", (line) => {
      if (/^\[|^OpenCV/.test(line)) return; // OpenCV/AVFoundation chatter
      send("log", line);
    });
  };
  forward(watch.stdout);
  forward(watch.stderr);
  watch.on("exit", (code) => {
    watch = null;
    send("log", `watch exited (code ${code})`);
    send("state", { running: false });
  });
  return { ok: true };
});

ipcMain.handle("stop", () => {
  if (!watch) return { ok: false };
  watch.kill("SIGINT");
  return { ok: true };
});

app.whenReady().then(createWindow);
app.on("before-quit", () => { if (watch) watch.kill("SIGINT"); });
app.on("window-all-closed", () => app.quit());
