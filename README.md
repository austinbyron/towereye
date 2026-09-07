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

## Requirements

- macOS (Apple Vision for OCR, AVFoundation for the camera)
- Python 3.10 or newer
- A camera aimed straight down into the dice tray: a webcam on an arm, or an
  old phone on a mount used as a camera. A clip-on LED light helps a lot.
- Chrome (for the Roll20 / Beyond20 extension) and OBS (for the overlay)

The first run asks for camera permission. macOS grants it to the app that
launched towereye, so allow it for your terminal (or towereye.app) under
System Settings → Privacy & Security → Camera.

## Quick start

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

**1. Find the camera.** Device order differs between apps, so check by index:

    python -m towereye cameras
    python -m towereye capture --camera N     # preview; 's' saves a frame, 'q' quits

**2. Calibrate your dice.** towereye matches lettering against templates of
*your* dice, so photograph each face once per die you use. Place the shown
face up, press `s` to save (2 to 3 per face, nudging rotation between saves),
`n` for the next face, `b` back, `q` to quit. Templates land in
`templates/<die>/`.

    python -m towereye calibrate --camera N --die d20
    python -m towereye calibrate --camera N --die d8

**3. Watch.**

    python -m towereye watch --camera N --preview

The console prints the hub (`ws://127.0.0.1:8777`) and stream
(`http://127.0.0.1:8778/stream.mjpg`) URLs. Drop a die; the value prints.
`--zoom 1.5` center-crops if the tray is small in frame. Ctrl-C stops.

**4. Send rolls to Roll20.** Open `chrome://extensions`, turn on Developer
mode, choose Load unpacked, and pick `companion/extension/`. Open (or reload)
your Roll20 game tab. Each roll now appears in chat as a roll card. For the
Beyond20 dialog path see [docs/m2-checklist.md](docs/m2-checklist.md).

**5. Show it on stream (optional).** In OBS add a Browser source pointing at
the local file `companion/overlay.html`. It draws the tray feed with a result
pop and nat 20 / nat 1 flair. Full picture-in-picture setup for Discord is in
[docs/m3-obs-setup.md](docs/m3-obs-setup.md).

### Try it without a camera

`python -m towereye.hub --demo` replays fake roll events on the hub, so you
can test the extension, `companion/monitor.html`, and the overlay without a
rig. `python -m towereye watch --video clip.mp4` runs the reader on a
recorded clip.

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
