# towereye

Point a webcam at your dice tower. towereye reads each physical roll and sends it
to Roll20 (or a D&D Beyond / Beyond20 dialog), with an OBS overlay so your
Discord camera shows the tray and the result.

Real dice, online table.

## How it works

1. **Watch** the tray with OpenCV: detect a die landing, wait for it to settle,
   crop the top face.
2. **Read** the face. First a keypoint match against per-die templates you
   calibrate from your own dice (shape-verified), then Apple Vision OCR as a
   fallback. No LLM in the loop.
3. **Publish** the roll on a local WebSocket hub (port 8777) and an MJPEG
   camera stream (port 8778).
4. **Companions** consume the hub:
   - a Chrome extension posts each roll into Roll20 chat or fills a Beyond20
     manual-roll dialog (`companion/extension/`)
   - an OBS browser-source overlay draws the tray feed plus a result pop
     with nat 20 / nat 1 flair (`companion/overlay.html`)
   - a small Electron app starts/stops the watch and picks the camera by
     thumbnail (`companion/desktop/`)

macOS only for now (Apple Vision, AVFoundation camera access). The core
pipeline is numpy/OpenCV with Vision behind a small shim, so porting is on the
roadmap.

## Quick start

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

    python -m towereye cameras            # find your tray camera index
    python -m towereye calibrate --camera N --die d20   # photograph each face once
    python -m towereye watch --camera N --preview

Then load `companion/extension/` as an unpacked Chrome extension and open your
Roll20 game. Rolls appear in chat as you throw them.

## Commands

| Command | What it does |
|---------|--------------|
| `watch` | Watch the tray, read rolls, run the hub + stream |
| `calibrate --die d20` | Capture per-face keypoint templates for one die |
| `cameras` | List openable camera indices (`--json` adds thumbnails) |
| `capture` | Preview the camera and save frames for a golden set |
| `read IMAGE` | Read a die from a still image |
| `bench GOLDEN_DIR` | Score the readers against labeled frames |

`python -m towereye <command> --help` lists every flag.

## Docs

- [docs/desktop-app.md](docs/desktop-app.md): build and install the Mac app
- [docs/m3-obs-setup.md](docs/m3-obs-setup.md): OBS + Discord picture-in-picture
- [docs/m2-checklist.md](docs/m2-checklist.md): Roll20 / Beyond20 bridge checklist
- [docs/superpowers/specs/](docs/superpowers/specs/): design notes and roadmap

## Tests

    pytest

## License

MIT. See [LICENSE](LICENSE).
