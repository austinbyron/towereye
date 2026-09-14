# towereye desktop (Electron wrapper)

A small window that starts/stops the watch, lets you pick the tray camera by
what it sees, and mirrors the live feed, hub/stream status, and the last roll.
The Python watch stays the source of truth; this is only a remote control.

## Run (dev)

    cd companion/desktop && npm install   # once
    npm start

## Build, sign, notarize (release)

The app ships its own Python: PyInstaller freezes the CLI into
`packaging/dist/towereye-core/` (spec: `packaging/towereye.spec`) and
electron-builder copies that folder into the app's Resources, signs every
binary with the Developer ID certificate, notarizes, and writes a DMG + zip.

One-time setup on the build Mac:

- A **Developer ID Application** certificate in the login keychain
  (`security find-identity -v -p codesigning` must list it).
- Notarization credentials saved as the `towereye` keychain profile:
  `xcrun notarytool store-credentials towereye --apple-id <apple id> --team-id <team id>`
- `GH_TOKEN` in the environment for `npm run release` (a GitHub token with
  `repo` scope) — not needed for a local build.

Then:

    cd companion/desktop && npm install                 # once
    APPLE_KEYCHAIN_PROFILE=towereye npm run dist        # dist/towereye-<version>-x64.dmg, signed + notarized
    APPLE_KEYCHAIN_PROFILE=towereye npm run release     # same, then uploads to a GitHub release draft

CI: pushing a `v*` tag runs `.github/workflows/release.yml`, which builds,
signs and notarizes both arm64 (macos-15 runner) and x64 (macos-13) and
attaches `towereye-mac-<arch>.dmg` to a draft GitHub release. Secrets live in
the repo's `release` environment (Developer ID .p12 + password, App Store
Connect API key). Actions are pinned to commit SHAs.

Install: open the DMG and drag towereye to Applications. Data (templates,
roll dataset, watch log) lives in `~/Library/Application Support/towereye`.
Bump `version` in `package.json` before a release; the tag is `v<version>`.

Dev shortcut (no signing): `npm start` runs the window against the repo's
`.venv` python with data in the repo dir. `TOWEREYE_REPO=<path>` makes even
the packaged app use a checkout instead of the bundled core.

Entitlements (`build/entitlements.mac.plist`): camera, plus allow-jit /
allow-unsigned-executable-memory / disable-library-validation, which the
frozen Python (ctypes, numpy, OpenCV) needs under the hardened runtime.

## Use

The window is a three-step journey; returning users land on step 3.

1. **Camera** – Find my camera probes every device and shows a thumbnail per
   camera; click the one showing the tray (device order differs between apps,
   so the picture is the only reliable way). Remembered.
2. **Dice** – the watch starts itself when you enter this step so the feed is
   live. Each die is a progress row; Calibrate opens a face-by-face panel:
   put the named face up, Save this face (two saves per face, nudge the
   rotation between them; it auto-advances). Templates take effect
   immediately. Roll reporting pauses while the panel is open. Uncalibrated
   dice fall back to Apple Vision OCR.
3. **Play** – pick the die on the tray (chips), Start reading rolls, watch the
   feed with each result popping over it. "stream via OBS" launches OBS with
   its virtual camera. The die choice is shared live with the Chrome
   extension's toolbar popup.

The Details disclosure at the bottom shows the watch/hub/stream state and
the watch log. The watch is found by the ports it holds, so one started from
a terminal shows up too, and Stop works on it. Start (or Restart) first kills
whatever holds the ports, then launches. Closing the window never stops the
watch; it is spawned detached and logs to `.towereye-watch.log` in the data
dir, which the log pane tails. Finding cameras stops a running watch first
(it owns the camera).

Dev aids: `TOWEREYE_STEP=dice npm start` opens on a step;
`TOWEREYE_SCREENSHOT=/tmp/shot.png npm start` captures the window and quits.
