# M3: OBS overlay + Discord setup

Goal: Discord sees a composed feed — the dice tray with the towereye overlay
(roll labels, results, nat 20 / nat 1 flair) on top.

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

## 4. Discord

- OBS → Start Virtual Camera
- Discord → voice settings → Camera → "OBS Virtual Camera"

## 5. Live checklist

- [ ] `watch --camera 1` running, hub + stream lines printed
- [ ] overlay.html in a plain browser tab shows the live tray
- [ ] OBS scene shows tray + overlay, virtual camera started
- [ ] Drop a die: number pops on the overlay over the tray
- [ ] Roll until a 20 lands: gold burst visible in Discord
- [ ] Kill watch: overlay keeps the last state, red dot appears, Discord
      feed keeps showing the tray (the game never blocks)
