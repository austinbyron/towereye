# towereye v2 direction (2026-09-06)

Decisions from the first live Roll20 session:

- **No LLM reader.** Haiku removed. Chain is keypoints -> Apple Vision. When neither
  is confident the watch resamples fresh frames (RESAMPLE_ROUNDS) and each reader
  retries alternate crop scales (CROP_SCALES) before an `unread` event asks for a
  reroll. A wrong number in chat is worse than a reroll, so the chain never
  returns a low-confidence guess.
- **No confirm/correct step in chat.** The camera feed is on stream; viewers
  verify with their own eyes. Templates are harvested offline from frames the
  user vouches for.
- **Dice differ by face count, not size.** Each die has its own template pool
  (`templates/<die>/<value>_<n>.png`, e.g. `templates/d8/6_000.png`, whose 6 is
  underlined rather than dotted). All pools load together; the value falls out of
  whichever die's lettering matches. `towereye calibrate --die d8` walks faces 1-8.
- **Roll20 first.** The extension posts every live result to Roll20 chat; the
  Beyond20 dialog path is optional.

## Target product: mobile app + thin receiver

1. User mounts their phone over the tray (guided framing screen).
2. User photographs each face of each die (calibration = template pool, on device).
3. The app runs the whole pipeline on device: settle detection, presence gate,
   top-face crop, segmented-lettering keypoints with shape verification, Vision
   OCR fallback, resample/retry.
4. The phone emits `result` / `unread` / `reroll` events (the existing hub
   protocol) to a local receiver on the computer or straight to the browser
   extension.

Implication for the Python codebase now: keep the reader pipeline pure and
framework-free (numpy/OpenCV only, Vision behind a small shim) so it ports to
Swift/Metal or runs as an ONNX/CoreML model later; keep the hub event schema
stable since it becomes the phone-to-desktop contract.
