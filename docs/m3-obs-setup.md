# OBS + Discord setup

Goal: Discord sees your face cam with the dice tray picture-in-picture in a
corner, towereye's overlay (result pop, nat 20 / nat 1 flair) on top of the
tray.

## 0. Install OBS (once)

    brew install --cask obs      # or download from obsproject.com

First launch: allow the camera and screen-recording prompts. In the
Auto-Configuration Wizard pick "I will only be using the virtual camera".

Virtual camera extension: the first "Start Virtual Camera" click asks macOS to
install a camera extension. Approve it under System Settings → General →
Login Items & Extensions → Camera Extensions, then fully quit and reopen OBS.
On a cold start with `--startvirtualcam` (what the desktop app's "open OBS"
box does) OBS may say "virtual camera is not installed" while the extension is
still activating (~9 s); it starts anyway. Click OK, or just press Start
Virtual Camera yourself.

## 0.5 Keep the laptop happy (Intel Macs)

- Settings → Video → Output (Scaled) Resolution **1280x720**, FPS 30 (or 24).
  Discord downscales anyway; this halves the encode work for OBS and Discord.
- Right-click the preview → **Disable Preview** while playing.
- Discord → Settings → Advanced → Hardware Acceleration on.

## 1. One browser source: tray feed + overlay

The watch process owns the Continuity Camera and macOS won't give OBS a second
handle, so the watch republishes its own frames as an MJPEG stream on
`http://127.0.0.1:8778/stream.mjpg` (console prints the URL at startup). The
overlay page shows that feed full-bleed under the result graphics.

- OBS → Sources → Browser → Local file → `companion/overlay.html`
- Width 1920, Height 1080 (or your canvas size)
- URL options: `?port=NNNN` (hub), `?feedport=NNNN` (stream), `?feed=0`
  (overlay only, no camera layer)
- Feed is 960 px wide at up to 15 fps; the reader still sees full resolution.
  Change `STREAM_WIDTH` / `MAX_FPS` in `towereye/stream.py` if you want more.
- If the watch is down the camera layer hides itself and the overlay keeps
  its last state; it reattaches on its own when the stream returns.
- `--no-stream` on watch disables all of this (e.g. when using a second
  capture device instead).

Fallback if you ever need a second source for the tray: watch `--preview` +
OBS Window Capture of the "towereye watch" window.

## 3. Smoke test without the rig

1. `.venv/bin/python -m towereye.hub --demo --interval 2`
2. The overlay should cycle: armed chip → result pop (17, keypoints ring) →
   armed → "camera couldn't read it" note → result 20 with gold burst
3. Tiny red dot bottom-right = hub offline; it vanishes when connected

## 2. Picture-in-picture with your face cam

1. Sources → + → **Video Capture Device** → name it "face" → Device: FaceTime
   HD Camera (or your webcam). Right-click it → Transform → Fit to Screen.
2. In the Sources list drag **towereye** above **face** (top draws in front).
3. Click the towereye source in the preview, drag a corner handle to about a
   third of the canvas (corners keep aspect), then drag it into the
   bottom-right corner (it snaps).
4. Optional crop so only the tray shows: right-click towereye → Transform →
   Edit Transform → Crop Right ≈ 600 (the tower base fills the right third of
   the camera frame). Re-drag into the corner if it shifted.

OBS remembers all of this; it is one-time.

## 4. Discord

- OBS → Start Virtual Camera (or tick "open OBS + virtual cam" in the desktop app)
- Discord → User Settings → Voice & Video → Camera → "OBS Virtual Camera"
- Your own preview in Discord is mirrored by design; others see it correctly.

## 5. Live checklist (every session)

1. Lamps on: the reader needs the die clearly lit (a dim frame reads as an
   empty tray and nothing posts).
2. Open **towereye** (Applications) → Start watching (tick "open OBS + virtual
   cam" or start OBS yourself).
3. Discord camera on.

- [ ] watch running (green dot in the app), hub + stream lines in its log
- [ ] overlay.html in a plain browser tab shows the live tray
- [ ] OBS scene shows tray + overlay, virtual camera started
- [ ] Drop a die: number pops on the overlay over the tray
- [ ] Roll until a 20 lands: gold burst visible in Discord
- [ ] Kill watch: overlay keeps the last state, red dot appears, Discord
      feed keeps showing the tray (the game never blocks)
