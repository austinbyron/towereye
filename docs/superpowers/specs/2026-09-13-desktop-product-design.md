# towereye desktop product (2026-09-13)

Decision after Austin's first real session: the Electron app is the product;
the mobile v2 idea is retired. Any camera the Mac can open feeds the watch.

## 1. Calibrate screen (in the app)

Calibration runs inside the running watch, which already owns the camera and
serves the feed. Hub messages (all replies are broadcast to every client):

| request | reply |
|---|---|
| `{"type":"templates"}` | `{"type":"templates","pools":{"d20":{"1":2,...}}}` |
| `{"type":"calibrate_start","die":"d8"}` | `{"type":"calibrating","die":"d8","faces":8,"counts":{...}}` |
| `{"type":"calibrate_save","value":3}` | `{"type":"template_saved","die":"d8","value":3,"counts":{...}}` or `{"type":"calibrate_error","reason":"..."}` |
| `{"type":"calibrate_stop"}` | `{"type":"calibrating","die":null}` |

While calibrating, the watch loop reports nothing (detector reset each frame).
A saved template is written to `<templates>/<die>/<value>_<n>.png` and added
to the live keypoint pool at once, so no restart is needed. The app screen
shows the feed, die + face counter, Save / Back / Next / Done, and per-face
counts; a face with 2+ templates is marked done.

## 2. Bundled Python

`towereye/paths.py` decides where data lives: `TOWEREYE_DATA` env, else
`~/Library/Application Support/towereye` when frozen, else the working
directory (repo). Templates, dataset, watch log and pid file all derive from
it. PyInstaller freezes the CLI (`packaging/towereye.spec`) into
`towereye-core/`, shipped in the app's Resources. The app runs that binary
when packaged and the repo `.venv` in dev; `TOWEREYE_REPO` still overrides.

## 3. Release

electron-builder replaces electron-packager: appId `com.austinbyron.towereye`,
hardened runtime + entitlements (camera, JIT/unsigned-memory/library
validation for Python), DMG + zip targets, GitHub Releases publish, notarize
via the `towereye` notarytool keychain profile (`APPLE_KEYCHAIN_PROFILE`).
`npm run release` builds, signs, notarizes and uploads.
