// towereye desktop: a thin wrapper around `python -m towereye watch`.
// The Python process stays the source of truth and outlives this window:
// it is spawned detached with its output in a log file, and the app finds it
// again by the ports it holds (hub 8777, stream 8778).
const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn, execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const REPO = path.resolve(__dirname, "..", "..");
const PYTHON = path.join(REPO, ".venv", "bin", "python");
const LOG = path.join(REPO, ".towereye-watch.log");
const PORTS = [8777, 8778];

let win = null;
let logOffset = 0;

function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

function pidsOnPorts() {
  const pids = new Set();
  for (const port of PORTS) {
    try {
      const out = execFileSync("lsof", ["-ti", `tcp:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" });
      out.split(/\s+/).filter(Boolean).forEach((p) => pids.add(Number(p)));
    } catch { /* nothing listening */ }
  }
  return [...pids];
}

function killPids(pids, signal) {
  for (const pid of pids) {
    try { process.kill(pid, signal); } catch { /* already gone */ }
  }
}

async function stopWatch() {
  const pids = pidsOnPorts();
  if (!pids.length) return false;
  killPids(pids, "SIGINT");
  for (let i = 0; i < 20 && pidsOnPorts().length; i++) await new Promise((r) => setTimeout(r, 250));
  if (pidsOnPorts().length) killPids(pidsOnPorts(), "SIGKILL");
  return true;
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

// log pane: tail the watch log file (works for a watch started before this window)
function tailLog() {
  try {
    const size = fs.statSync(LOG).size;
    if (size < logOffset) logOffset = 0; // truncated by a fresh start
    if (size > logOffset) {
      const fd = fs.openSync(LOG, "r");
      const buf = Buffer.alloc(size - logOffset);
      fs.readSync(fd, buf, 0, buf.length, logOffset);
      fs.closeSync(fd);
      logOffset = size;
      buf.toString("utf8").split("\n").filter((l) => l && !/^\[|^OpenCV/.test(l)).forEach((l) => send("log", l));
    }
  } catch { /* no log yet */ }
}

ipcMain.handle("env", () => ({ repo: REPO, pythonOk: fs.existsSync(PYTHON), running: pidsOnPorts().length > 0 }));

ipcMain.handle("cameras", async () => {
  if (pidsOnPorts().length) return { error: "stop the watch before scanning: it owns the camera" };
  return new Promise((resolve) => {
    const p = spawn(PYTHON, ["-m", "towereye", "cameras", "--json"], { cwd: REPO });
    let out = "";
    p.stdout.on("data", (d) => { out += d; });
    p.on("close", () => {
      try { resolve({ cameras: JSON.parse(out) }); }
      catch { resolve({ error: "camera scan failed", raw: out }); }
    });
    p.on("error", (e) => resolve({ error: String(e) }));
  });
});

ipcMain.handle("start", async (_e, { camera }) => {
  if (await stopWatch()) send("log", "replaced the watch that was holding the ports");
  fs.writeFileSync(LOG, "");
  logOffset = 0;
  const out = fs.openSync(LOG, "a");
  const child = spawn(PYTHON, ["-u", "-m", "towereye", "watch", "--camera", String(camera)], {
    cwd: REPO,
    detached: true,               // survives this app closing
    stdio: ["ignore", out, out],
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  child.unref();
  fs.closeSync(out);
  send("state", { running: true, camera });
  return { ok: true, pid: child.pid };
});

ipcMain.handle("stop", async () => {
  const stopped = await stopWatch();
  send("state", { running: false });
  return { ok: stopped };
});

app.whenReady().then(() => {
  createWindow();
  setInterval(() => {
    tailLog();
    send("state", { running: pidsOnPorts().length > 0 });
  }, 1000);
});
app.on("window-all-closed", () => app.quit()); // the watch keeps running
