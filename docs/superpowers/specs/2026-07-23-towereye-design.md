# towereye — Dice Tower Camera Companion

**Date:** 2026-07-23
**Status:** Approved design, pre-implementation

## What it is

A camera watches the open tray of Austin's dice tower. When he rolls a physical
die during a D&D session (Taivas Isles campaign, played over Discord + Roll20
with D&D Beyond character sheets), the system reads the number on the top face
and injects the labeled result into Roll20 as a native-looking roll — plus a
picture-in-picture of the tray and nat 20 / nat 1 animations in his Discord
camera feed.

## Scope

- **One die at a time**, any type d4–d20. The reader's only job is "what number
  is face-up." Die type/count context comes from the roll being resolved, not
  from vision.
- Rolls are **user-initiated** ("armed") — no always-on watching. Arming happens
  implicitly by clicking a roll on the D&D Beyond sheet.
- Dice: dedicated high-contrast set — blue (slightly translucent) with white
  numerals. A backup white-with-black-ink set is acceptable if needed. Fixed
  camera framing + clip LED light keep imaging conditions constant.
- Roll20 free tier only (no API scripts). All Roll20 interaction goes through
  the browser.

## Key architectural decisions

1. **Ride Beyond20's "manual rolls" mode** rather than forking Beyond20 or
   building standalone Roll20 injection. Beyond20 (already open source, already
   handles DDB button interception, modifiers, advantage, crit detection, and
   native Roll20 roll templates) pops a dialog asking for the physical result;
   our browser companion auto-fills it. Fallback if the dialog proves
   unscriptable: fork Beyond20 and add a "camera dice" input source (as its
   Pixels dice integration did).
2. **Pluggable reader chain, cheapest-first:**
   `AppleVisionReader → HaikuReader → (phase 2) OnnxReader`.
   - *AppleVisionReader:* macOS Vision framework (`VNRecognizeTextRequest`) on
     the Intel Mac via pyobjc or a small Swift CLI. Free, local, instant. Known
     weak spots: single digits at arbitrary rotation, 6-vs-9 (mitigated by
     underscore/dot marks on the dice).
   - *HaikuReader:* one Claude Haiku vision call per roll on low confidence or
     implausible OCR output. At 30–60 rolls/session this is pennies; a
     per-session call counter is displayed (cost-consciousness rule).
   - *OnnxReader (phase 2):* small classifier trained on accumulated real
     rolls from Austin's own dice; trained on Colab or the local python3.12
     torch venv (no x86_64 torch at inference — ONNX Runtime only). Cuts the
     API dependency entirely.
3. **Every confirmed roll is a labeled training sample.** The human
   confirm/correct step in the Beyond20 dialog doubles as the labeling UI.
4. **iPhone is camera-only in phase 1.** Old iPhone mounted over the tray via
   Continuity Camera (iPhone XR+/iOS 16+) or an IP-camera app (MJPEG over WiFi)
   otherwise. A bespoke iOS app doing on-device capture + Vision/CoreML is a
   real v2 option (Austin already pays for an Apple developer account, so no
   sideloading friction): the phone would emit just `rolled N` events over the
   network, eliminating video streaming and offloading all CV from the Mac.
   Deferred from phase 1 purely for iteration speed — tuning settle detection
   and the reader chain is much faster in Python on the Mac.

## Components

1. **`dicecam` service** — Python 3.12 on the Mac. Captures the camera feed,
   runs settle detection (classical OpenCV motion analysis: die present +
   motion below threshold for ~0.5 s), passes the settled frame through the
   reader chain, hosts a localhost WebSocket hub, and logs every roll (frame,
   predicted value, confirmed value, confidence, reader used, roll context)
   to a local dataset directory.
2. **Browser companion** — Tampermonkey userscript first (fast iteration),
   proper WebExtension later if needed. Runs on dndbeyond.com and roll20.net
   tabs. Detects Beyond20's manual-roll dialog opening → sends
   `arm {label, die}` to the hub → fills the dialog when `result` arrives →
   reports the user-confirmed value back for the dataset.
3. **OBS overlay page** — local HTML page as an OBS browser source, listening
   to the same WebSocket. Events: `armed` (show roll label / cut to tray PiP),
   `result` (show number), `nat20` / `nat1` (animation). OBS Virtual Camera
   carries the composed feed into Discord.
4. **Physical rig** — iPhone mount aimed into the tray + clip-on LED light
   (diffused if glare appears). Fixed framing is a load-bearing assumption.

## Data flow (one roll)

Click "Initiative" on the DDB sheet → Beyond20 manual-roll dialog opens →
companion sends `arm {label: "Initiative", die: "d20"}` → overlay shows
"rolling for Initiative", dicecam watches → die dropped → settle detected →
frame → reader chain → `result {value: 17, confidence, reader}` → companion
fills dialog → **user confirms or corrects** → Beyond20 applies modifiers and
posts the native roll template to Roll20 chat → confirmed value returns to
dicecam → dataset row written → overlay celebrates if nat 20 (or mourns nat 1;
only the d20 can produce either).

## Error handling

Guiding rule: **every failure degrades to stock Beyond20 manual mode** — the
dialog still pops and the number can be typed by hand; the game never blocks
on this system.

- Camera offline / WebSocket dead: status indicator on overlay + companion;
  manual entry unaffected.
- Low-confidence read: dialog is filled but visually flagged, never silently
  authoritative.
- Die never settles (cocked, bounced out): ~10 s timeout → "re-roll?" state.
- Haiku API failure or offline: chain falls through to empty dialog + flag.
- API usage: per-session Haiku call counter surfaced in the overlay/status.

## Testing

- **Settle detection:** unit tests against recorded tray videos (fixtures
  recorded once).
- **Readers:** golden set of settled frames with known values; doubles as the
  accuracy benchmark for deciding when OnnxReader beats the Haiku/Vision chain.
- **Companion:** tested against a mock WebSocket hub.
- **End-to-end:** manual pre-session checklist (camera up, socket connected,
  test roll lands labeled in Roll20 chat).

## Milestones

- **M1 — proof of read:** rig mounted; CLI watches the tray and prints
  "you rolled 17" (settle detection + Vision/Haiku reader chain). Riskiest
  part first.
- **M2 — the bridge:** WebSocket hub + userscript; a physical roll lands in
  Roll20 chat, correctly labeled, via the Beyond20 dialog.
- **M3 — the show:** OBS overlay, tray PiP, nat 20 / nat 1 animations visible
  in Discord.
- **M4 — go local:** train the classifier on accumulated roll dataset, add
  OnnxReader as first in the chain, retire routine Haiku calls.
- **Post-M4 option (v2):** port capture + settle + CoreML inference into a
  bespoke iOS app; the phone emits `rolled N` events and the Mac drops video
  handling entirely.

## Stack

Python 3.12, OpenCV, thin `websockets` (or aiohttp) hub, pyobjc or Swift CLI
shim for Vision framework, ONNX Runtime (phase 2), Tampermonkey userscript
(JS), OBS browser source (plain HTML/JS/CSS). No torch at runtime on the
Intel Mac.
