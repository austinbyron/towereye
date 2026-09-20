// Auto-update from GitHub Releases (electron-updater reads latest-mac.yml, see
// scripts/merge-manifest.js). Quiet by design: check once after launch, download
// in the background, then show a "Restart" chip. Nothing ever interrupts a
// session; an ignored update installs the next time the app quits.
//
// The watch runs from Resources/towereye-core INSIDE the bundle being replaced,
// so it is always stopped before an install swaps the bundle.
//
// TOWEREYE_UPDATE_URL=<http dir with latest-mac.yml + zip>: test against a local
// server instead of GitHub (see docs/desktop-app.md).
function initUpdater({ app, ipcMain, autoUpdater, send, watchRunning, stopWatch, delayMs = 5000 }) {
  let state = { ready: false, version: null };
  let staged = false;   // Squirrel will install on quit
  let quitting = false;

  if (process.env.TOWEREYE_UPDATE_URL) {
    autoUpdater.setFeedURL({ provider: "generic", url: process.env.TOWEREYE_UPDATE_URL });
  }

  autoUpdater.on("update-available", (info) => {
    // read when the download completes: hand the update to Squirrel for
    // install-on-quit only if no watch is running out of the bundle right now
    autoUpdater.autoInstallOnAppQuit = !watchRunning();
    staged = autoUpdater.autoInstallOnAppQuit;
    send("log", `update ${info.version} found; downloading`);
  });
  autoUpdater.on("update-downloaded", (info) => {
    state = { ready: true, version: info.version };
    send("update", state);
    send("log", `update ${info.version} ready; restart to install`);
  });
  autoUpdater.on("error", (e) => send("log", `update check failed: ${e && e.message ? e.message : e}`));

  ipcMain.handle("updateState", () => state);
  ipcMain.handle("updateInstall", async () => {
    if (!state.ready) return { ok: false };
    if (await stopWatch()) send("log", "stopped the watch to install the update");
    autoUpdater.quitAndInstall();
    return { ok: true };
  });

  app.on("before-quit", (e) => {
    if (!staged || !state.ready || quitting || !watchRunning()) return;
    e.preventDefault();
    quitting = true;
    stopWatch().finally(() => app.quit());
  });

  setTimeout(() => {
    Promise.resolve(autoUpdater.checkForUpdates()).catch(() => { /* reported through the error event */ });
  }, delayMs);

  return { state: () => state };
}

module.exports = { initUpdater };
