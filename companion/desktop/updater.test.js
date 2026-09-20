const test = require("node:test");
const assert = require("node:assert");
const { EventEmitter } = require("events");
const { initUpdater } = require("./updater");

function rig({ running = false } = {}) {
  const calls = [];
  const autoUpdater = Object.assign(new EventEmitter(), {
    autoInstallOnAppQuit: true,
    checkForUpdates: () => { calls.push("check"); return Promise.resolve(); },
    quitAndInstall: () => calls.push("quitAndInstall"),
    setFeedURL: (o) => calls.push(["feed", o]),
  });
  const app = Object.assign(new EventEmitter(), { quit: () => calls.push("quit") });
  const handlers = {};
  const ipcMain = { handle: (name, fn) => { handlers[name] = fn; } };
  const sent = [];
  const state = { running };
  const updater = initUpdater({
    app, ipcMain, autoUpdater, delayMs: 0,
    send: (ch, p) => sent.push([ch, p]),
    watchRunning: () => state.running,
    stopWatch: async () => { calls.push("stopWatch"); state.running = false; return true; },
  });
  return { autoUpdater, app, handlers, sent, calls, state, updater };
}

const tick = () => new Promise((r) => setTimeout(r, 5));

test("checks for an update shortly after launch", async () => {
  const r = rig();
  await tick();
  assert.deepStrictEqual(r.calls, ["check"]);
});

test("a downloaded update reaches the window and later state queries", async () => {
  const r = rig();
  r.autoUpdater.emit("update-downloaded", { version: "0.4.3" });
  assert.deepStrictEqual(r.sent.filter(([ch]) => ch === "update"), [["update", { ready: true, version: "0.4.3" }]]);
  assert.deepStrictEqual(await r.handlers.updateState(), { ready: true, version: "0.4.3" });
});

test("no install on quit is staged while a watch runs from the bundle", () => {
  const r = rig({ running: true });
  r.autoUpdater.emit("update-available", { version: "0.4.3" });
  assert.strictEqual(r.autoUpdater.autoInstallOnAppQuit, false);
  r.state.running = false;
  r.autoUpdater.emit("update-available", { version: "0.4.3" });
  assert.strictEqual(r.autoUpdater.autoInstallOnAppQuit, true);
});

test("Restart stops the watch before installing", async () => {
  const r = rig({ running: true });
  r.autoUpdater.emit("update-downloaded", { version: "0.4.3" });
  await r.handlers.updateInstall();
  assert.deepStrictEqual(r.calls.filter((c) => c !== "check"), ["stopWatch", "quitAndInstall"]);
});

test("Restart without a downloaded update does nothing", async () => {
  const r = rig();
  assert.deepStrictEqual(await r.handlers.updateInstall(), { ok: false });
  assert.ok(!r.calls.includes("quitAndInstall"));
});

test("quitting with a staged install stops a watch started afterwards", async () => {
  const r = rig();
  r.autoUpdater.emit("update-available", { version: "0.4.3" }); // staged: no watch yet
  r.autoUpdater.emit("update-downloaded", { version: "0.4.3" });
  r.state.running = true;
  let prevented = false;
  r.app.emit("before-quit", { preventDefault: () => { prevented = true; } });
  await tick();
  assert.ok(prevented);
  assert.deepStrictEqual(r.calls.filter((c) => c !== "check"), ["stopWatch", "quit"]);
});

test("quitting leaves the watch alone when nothing is staged", () => {
  const r = rig({ running: true });
  r.autoUpdater.emit("update-available", { version: "0.4.3" }); // watch running: not staged
  r.autoUpdater.emit("update-downloaded", { version: "0.4.3" });
  let prevented = false;
  r.app.emit("before-quit", { preventDefault: () => { prevented = true; } });
  assert.ok(!prevented);
  assert.ok(!r.calls.includes("stopWatch"));
});

test("errors only reach the log", () => {
  const r = rig();
  r.autoUpdater.emit("error", new Error("offline"));
  assert.ok(r.sent.some(([ch, p]) => ch === "log" && /offline/.test(p)));
  assert.ok(!r.sent.some(([ch]) => ch === "update"));
});

test("TOWEREYE_UPDATE_URL points the updater at a local server", () => {
  process.env.TOWEREYE_UPDATE_URL = "http://127.0.0.1:9999/";
  try {
    const r = rig();
    assert.deepStrictEqual(r.calls[0], ["feed", { provider: "generic", url: "http://127.0.0.1:9999/" }]);
  } finally { delete process.env.TOWEREYE_UPDATE_URL; }
});
