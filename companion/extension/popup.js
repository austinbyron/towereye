// Toolbar popup: pick the die on the tray. Sends set_die to the hub; the hub
// echoes the choice to every client (desktop app, content scripts, overlay).
(function () {
  "use strict";
  const HUB = "ws://127.0.0.1:8777";
  const $ = (id) => document.getElementById(id);
  const ws = new WebSocket(HUB);
  ws.onopen = () => { $("dot").className = "dot on"; $("note").textContent = "rolls post as this die"; };
  ws.onclose = () => { $("dot").className = "dot"; $("note").textContent = "watch not running (hub offline)"; };
  ws.onerror = () => ws.close();
  ws.onmessage = (m) => {
    let e; try { e = JSON.parse(m.data); } catch { return; }
    if (e.type === "die") $("die").value = e.die;
  };
  $("die").onchange = () => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "set_die", die: $("die").value }));
    else $("note").textContent = "watch not running - start it in the towereye app";
  };
})();
