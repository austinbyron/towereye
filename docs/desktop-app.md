# towereye desktop (Electron wrapper)

A small window that starts/stops the watch, lets you pick the tray camera by
what it sees, and mirrors the live feed, hub/stream status, and the last roll.
The Python watch stays the source of truth; this is only a remote control.

## Run (dev)

    cd companion/desktop && npm install   # once
    npm start

## Build + install as a Mac app

    cd companion/desktop
    npx @electron/packager . towereye --platform=darwin --arch=x64 --out=dist --overwrite --ignore="dist|build/icon.iconset|build/icon_1024.png"
    cp build/icon.icns dist/towereye-darwin-x64/towereye.app/Contents/Resources/electron.icns
    rm -rf /Applications/towereye.app && cp -R dist/towereye-darwin-x64/towereye.app /Applications/

The packaged app expects the repo at `~/CodeProjects/towereye` (override with
the `TOWEREYE_REPO` env var). The icon is drawn by a small OpenCV script
(`build/icon_1024.png` → `iconutil` → `build/icon.icns`).

"open OBS + virtual cam" on Start launches `/Applications/OBS.app` with
`--startvirtualcam`, so Discord's camera is live without touching OBS.

## Use

1. **Scan cameras** – probes device indices and shows a thumbnail per camera.
   Click the one showing the tray (device order differs between apps, so the
   picture is the only reliable way). The choice is remembered.
2. **Start watching** – runs `python -m towereye watch --camera N` from the
   repo's `.venv`. Console lines stream into the log pane. Stop sends Ctrl-C.
3. Dots: watch process · hub (8777) · stream (8778). The watch is found by the
   ports it holds, so a watch started from a terminal shows up too, and Stop
   works on it.

Rules: Start (or Restart) first kills whatever holds the ports, then launches.
Closing the window never stops the watch; it is spawned detached and logs to
`.towereye-watch.log` in the repo, which the log pane tails. The camera scan
can't run while a watch owns the camera: stop first.
