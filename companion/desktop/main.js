// towereye desktop: a thin wrapper around `python -m towereye watch`.
// The Python process stays the source of truth and outlives this window:
// it is spawned detached with its output in a log file, and the app finds it
// again by the ports it holds (hub 8777, stream 8778).
const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn, execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const { initUpdater } = require("./updater");

// Packaged: the frozen CLI (PyInstaller, see packaging/towereye.spec) ships in
// Resources/towereye-core and data lives in ~/Library/Application Support.
// Dev (or TOWEREYE_REPO set): the repo's .venv python and the repo dir.
const REPO = process.env.TOWEREYE_REPO || path.resolve(__dirname, "..", "..");
const PACKAGED = app.isPackaged && !process.env.TOWEREYE_REPO;
const CORE = path.join(process.resourcesPath || "", "towereye-core", "towereye-core");
const PYTHON = path.join(REPO, ".venv", "bin", "python");
const DATA = PACKAGED ? path.join(app.getPath("appData"), "towereye") : REPO;
fs.mkdirSync(DATA, { recursive: true }); // spawn cwd must exist before the first scan
const LOG = path.join(DATA, ".towereye-watch.log");
const PIDFILE = path.join(DATA, ".towereye-watch.pid");
const PORTS = [8777, 8778];

function coreCommand(args) {
  // [file, argv] for `towereye <args>` in either mode
  return PACKAGED ? [CORE, args] : [PYTHON, ["-u", "-m", "towereye", ...args]];
}
function coreOk() { return fs.existsSync(PACKAGED ? CORE : PYTHON); }
function coreEnv() {
  return { ...process.env, PYTHONUNBUFFERED: "1", TOWEREYE_DATA: DATA };
}

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
    width: 540,
    height: 820,
    minWidth: 440,
    title: "towereye",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true },
  });
  win.loadFile("index.html", process.env.TOWEREYE_STEP ? { query: { step: process.env.TOWEREYE_STEP } } : undefined);
  // TOWEREYE_SCREENSHOT=<png path>: capture the window a few seconds after load, then quit (dev aid)
  if (process.env.TOWEREYE_SCREENSHOT) {
    win.webContents.once("did-finish-load", () => setTimeout(async () => {
      win.webContents.invalidate();            // an untouched first paint can be captured half-drawn
      await new Promise((r) => setTimeout(r, 400));
      const img = await win.capturePage();
      fs.writeFileSync(process.env.TOWEREYE_SCREENSHOT, img.toPNG());
      if (process.env.TOWEREYE_DUMP) {
        const info = await win.webContents.executeJavaScript(`(() => {
          const r = (id) => { const e = document.getElementById(id); if (!e) return null; const b = e.getBoundingClientRect(); return { hidden: e.hidden, x: b.x, y: b.y, w: b.width, h: b.height, display: getComputedStyle(e).display }; };
          const at = (x, y) => { const e = document.elementFromPoint(x, y); return e ? (e.id || e.className || e.tagName) : null; };
          return { scroll: document.documentElement.scrollHeight, inner: innerHeight, scan: r("scan"), chosen: r("chosen"), cams: r("cams"), feedWrap: r("feedWrap"), details: r("dotWatch"), at250: at(100, 250), at400: at(100, 400), err: window.__err || null };
        })()`);
        fs.writeFileSync(process.env.TOWEREYE_DUMP, JSON.stringify(info, null, 1));
      }
      app.quit();
    }, Number(process.env.TOWEREYE_SCREENSHOT_DELAY || 4000)));
  }
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

ipcMain.handle("env", () => ({
  data: DATA, core: PACKAGED ? CORE : PYTHON, coreOk: coreOk(), packaged: PACKAGED,
  running: watchPids().length > 0,
}));

ipcMain.handle("cameras", async () => {
  if (watchPids().length) return { error: "stop the watch before scanning: it owns the camera" };
  return new Promise((resolve) => {
    const [file, argv] = coreCommand(["cameras", "--json"]);
    const p = spawn(file, argv, { cwd: DATA, env: coreEnv() });
    let out = "", err = "";
    p.stdout.on("data", (d) => { out += d; });
    p.stderr.on("data", (d) => { err += d; });
    p.on("close", (code) => {
      // stderr carries OpenCV's per-index noise; keep only the last real line
      const reason = err.split("\n").map((l) => l.trim()).filter((l) => l && !/^OpenCV|^\[/.test(l)).pop();
      let parsed = null;
      try { parsed = JSON.parse(out); } catch { /* not json */ }
      if (Array.isArray(parsed)) return resolve({ cameras: parsed });
      if (parsed && parsed.error) return resolve({ error: parsed.error });
      resolve({ error: `camera scan failed (exit ${code})${reason ? ": " + reason : ""}` });
    });
    p.on("error", (e) => resolve({ error: String(e) }));
  });
});

ipcMain.handle("openObs", () => { openObs(); return true; });

function openObs() {
  // `open -a` activates OBS if it is already running; the flag only applies
  // on a cold start, which is the case that matters (virtual camera armed).
  if (!fs.existsSync("/Applications/OBS.app")) { send("log", "OBS not found in /Applications"); return; }
  spawn("open", ["-a", "OBS", "--args", "--startvirtualcam"], { detached: true, stdio: "ignore" }).unref();
  send("log", "opened OBS with the virtual camera started");
}

const DICE = new Set(["auto", "d4", "d6", "d8", "d10", "d12", "d20"]);

ipcMain.handle("start", async (_e, { camera, obs, die }) => {
  if (starting) return { ok: false, error: "already starting" };
  starting = true;
  send("state", { running: true, starting: true });
  try {
    if (await stopWatch()) send("log", "replaced the running watch");
    if (obs) openObs();
    return startWatch(camera, DICE.has(die) ? die : "auto");
  } finally {
    // hold Start until the ports are bound (or 15s), so a double click can't
    // launch a duplicate that loses the camera race
    for (let i = 0; i < 60 && portsBound() < PORTS.length; i++) await new Promise((r) => setTimeout(r, 250));
    starting = false;
    send("state", { running: watchPids().length > 0, starting: false });
  }
});

function startWatch(camera, die) {
  fs.mkdirSync(DATA, { recursive: true });
  fs.writeFileSync(LOG, "");
  logOffset = 0;
  const out = fs.openSync(LOG, "a");
  const [file, argv] = coreCommand(["watch", "--camera", String(camera), "--die", die]);
  const child = spawn(file, argv, {
    cwd: DATA,
    detached: true,               // survives this app closing
    stdio: ["ignore", out, out],
    env: coreEnv(),
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
  if (app.isPackaged) {
    initUpdater({
      app, ipcMain, autoUpdater: require("electron-updater").autoUpdater, send,
      watchRunning: () => watchPids().length > 0, stopWatch,
    });
  } else {
    ipcMain.handle("updateState", () => ({ ready: false, version: null }));
    ipcMain.handle("updateInstall", () => ({ ok: false }));
  }
  setInterval(() => {
    tailLog();
    if (!starting) send("state", { running: watchPids().length > 0, starting: false });
  }, 1000);
});
app.on("window-all-closed", () => app.quit()); // the watch keeps running
