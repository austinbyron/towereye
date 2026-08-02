# M3: OBS overlay + Discord setup

Goal: Discord sees a composed feed — the dice tray with the towereye overlay
(roll labels, results, nat 20 / nat 1 flair) on top.

## 1. Tray video source

The watch process owns the Continuity Camera, and macOS may refuse OBS a
second handle on the same device. Two paths, try in order:

- **Direct (try first):** OBS → Sources → Video Capture Device → the iPhone
  camera. If it shows video while `watch` is running, done.
- **Window capture (always works):** run watch with `--preview`, then
  OBS → Sources → macOS Screen Capture → Window Capture → the
  "towereye watch" window. Crop in OBS if needed.

## 2. Overlay browser source

- OBS → Sources → Browser → Local file → `companion/overlay.html`
- Width 1920, Height 1080 (or your canvas size); background is transparent
- Add `?port=NNNN` to the URL field if the hub runs on a non-default port
- Layer it above the tray source

## 3. Smoke test without the rig

1. `.venv/bin/python -m towereye.hub --demo --interval 2`
2. The overlay should cycle: armed chip → result pop (17, keypoints ring) →
   armed → "camera couldn't read it" note → result 20 with gold burst
3. Tiny red dot bottom-right = hub offline; it vanishes when connected

## 4. Discord

- OBS → Start Virtual Camera
- Discord → voice settings → Camera → "OBS Virtual Camera"

## 5. Live checklist

- [ ] `watch --camera 1 --preview` running, hub line printed
- [ ] OBS scene shows tray + overlay, virtual camera started
- [ ] Drop a die: number pops on the overlay over the tray
- [ ] Roll until a 20 lands: gold burst visible in Discord
- [ ] Kill watch: overlay keeps the last state, red dot appears, Discord
      feed keeps showing the tray (the game never blocks)
