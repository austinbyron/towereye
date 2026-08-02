# M2 manual verification checklist

## Monitor page
Open `companion/monitor.html` in any browser (double-click works; add `?port=NNNN`
for a non-default hub port). Shows hub connection status, the armed roll label,
a live feed of recent rolls with reader/confidence, and session counters.
Late joins replay the last 50 events. Also works as an OBS browser source.

## Against the demo hub (no rig needed)
1. `.venv/bin/python -m towereye.hub --demo`
2. Install `companion/towereye.user.js` in Tampermonkey; open any dndbeyond.com page.
3. Badge shows a die icon (connected). Kill the demo hub: badge shows disconnected; restart it: badge recovers (auto-reconnect).
4. With DEBUG=true, check the console logs each demo event.

## Against the real rig
1. `.venv/bin/python -m towereye watch --camera 1 --preview` — note "Hub listening on ws://127.0.0.1:8777".
2. Open the DDB character sheet with Beyond20 manual rolls enabled; open a roll dialog.
3. Console shows "armed for <label>"; if not, read the candidate-dialog DEBUG logs and pin CONFIG selectors.
4. Drop a die. The dialog input fills with the value, green outline for keypoints/vision, yellow for haiku.
5. Correct the value if wrong, submit. Check `dataset/rolls.jsonl` gained a confirm row, and `templates/` gained a file if that face was under the cap.
6. Roll20 chat shows the labeled roll via Beyond20's native template.
7. Kill the watch process mid-dialog: manual typing still works (degrades to stock Beyond20).
8. Note: templates harvested from confirms load at startup - restart watch for them to take effect.
