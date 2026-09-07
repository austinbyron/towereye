# towereye desktop (Electron wrapper)

A small window that starts/stops the watch, lets you pick the tray camera by
what it sees, and mirrors the live feed, hub/stream status, and the last roll.
The Python watch stays the source of truth; this is only a remote control.

## Run

    cd companion/desktop && npm install   # once
    npm start

## Use

1. **Scan cameras** – probes device indices and shows a thumbnail per camera.
   Click the one showing the tray (device order differs between apps, so the
   picture is the only reliable way). The choice is remembered.
2. **Start watching** – runs `python -m towereye watch --camera N` from the
   repo's `.venv`. Console lines stream into the log pane. Stop sends Ctrl-C.
3. Dots: watch process · hub (8777) · stream (8778). If a watch is already
   running from a terminal, the app shows its feed and disables Start.

The camera scan can't run while a watch owns the camera: stop first.
