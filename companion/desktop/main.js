// towereye desktop: a thin wrapper around `python -m towereye watch`.
// The Python process stays the source of truth and outlives this window:
// it is spawned detached with its output in a log file, and the app finds it
// again by the ports it holds (hub 8777, stream 8778).
const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn, execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const os = require("os");
// Packaged app lives in /Applications; the Python side stays in the repo checkout.
const REPO = process.env.TOWEREYE_REPO
  || (app.isPackaged ? path.join(os.homedir(), "CodeProjects", "towereye") : path.resolve(__dirname, "..", ".."));
const PYTHON = path.join(REPO, ".venv", "bin", "python");
const LOG = path.join(REPO, ".towereye-watch.log");
const PIDFILE = path.join(REPO, ".towereye-watch.pid");
const PORTS = [8777, 8778];

let win = null;
let logOffset = 0;

function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

function alive(pid) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

function watchPids() {
  // the pid file covers a watch that is still booting (ports not bound yet)
  const pids = new Set(pidsOnPorts());
  try {
    const pid = Number(fs.readFileSync(PIDFILE, "utf8").trim());
    if (pid && alive(pid)) pids.add(pid);
  } catch { /* no pid file */ }
  return [...pids];
}

function listeners(port) {
  try {
    const out = execFileSync("lsof", ["-ti", `tcp:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" });
    return out.split(/\s+/).filter(Boolean).map(Number);
  } catch { return []; }
}

function pidsOnPorts() {
  return [...new Set(PORTS.flatMap(listeners))];
}

function portsBound() {
  return PORTS.filter((p) => listeners(p).length).length;
}

function killPids(pids, signal) {
  for (const pid of pids) {
    try { process.kill(pid, signal); } catch { /* already gone */ }
  }
}

async function stopWatch() {
  const pids = watchPids();
  if (!pids.length) return false;
  killPids(pids, "SIGINT");
  for (let i = 0; i < 20 && watchPids().length; i++) await new Promise((r) => setTimeout(r, 250));
  if (watchPids().length) killPids(watchPids(), "SIGKILL");
  return true;
}

let starting = false;

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

ipcMain.handle("env", () => ({ repo: REPO, pythonOk: fs.existsSync(PYTHON), running: watchPids().length > 0 }));

ipcMain.handle("cameras", async () => {
  if (watchPids().length) return { error: "stop the watch before scanning: it owns the camera" };
  return new Promise((resolve) => {
    const p = spawn(PYTHON, ["-m", "towereye", "cameras", "--json"], { cwd: REPO });
    let out = "", err = "";
    p.stdout.on("data", (d) => { out += d; });
    p.stderr.on("data", (d) => { err += d; });
    p.on("close", (code) => {
      try {
        const cameras = JSON.parse(out);
        if (!cameras.length) {
          resolve({ error: "no cameras opened. If macOS never asked, allow towereye under System Settings → Privacy & Security → Camera." });
        } else resolve({ cameras });
      } catch {
        resolve({ error: `camera scan failed (exit ${code}): ${err.split("\n").filter((l) => l && !/^\[|^OpenCV/.test(l)).slice(-2).join(" ")}` });
      }
    });
    p.on("error", (e) => resolve({ error: String(e) }));
  });
});

function openObs() {
  // `open -a` activates OBS if it is already running; the flag only applies
  // on a cold start, which is the case that matters (virtual camera armed).
  if (!fs.existsSync("/Applications/OBS.app")) { send("log", "OBS not found in /Applications"); return; }
  spawn("open", ["-a", "OBS", "--args", "--startvirtualcam"], { detached: true, stdio: "ignore" }).unref();
  send("log", "opened OBS with the virtual camera started");
}

ipcMain.handle("start", async (_e, { camera, obs }) => {
  if (starting) return { ok: false, error: "already starting" };
  starting = true;
  send("state", { running: true, starting: true });
  try {
    if (await stopWatch()) send("log", "replaced the running watch");
    if (obs) openObs();
    return startWatch(camera);
  } finally {
    // hold Start until the ports are bound (or 15s), so a double click can't
    // launch a duplicate that loses the camera race
    for (let i = 0; i < 60 && portsBound() < PORTS.length; i++) await new Promise((r) => setTimeout(r, 250));
    starting = false;
    send("state", { running: watchPids().length > 0, starting: false });
  }
});

function startWatch(camera) {
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
  return { ok: true, pid: child.pid };
}

ipcMain.handle("stop", async () => {
  const stopped = await stopWatch();
  send("state", { running: false });
  return { ok: stopped };
});

app.whenReady().then(() => {
  createWindow();
  setInterval(() => {
    tailLog();
    if (!starting) send("state", { running: watchPids().length > 0, starting: false });
  }, 1000);
});
app.on("window-all-closed", () => app.quit()); // the watch keeps running
