// towereye companion: posts each roll the dice tower camera reads into the
// Roll20 chat of the open game. Talks only to the towereye app on this
// computer (a WebSocket on localhost); nothing leaves the machine.
(function () {
  "use strict";

  const CONFIG = {
    hubUrl: "ws://127.0.0.1:8777",
    reconnectMs: 3000,
    DEBUG: false, // true: reader/confidence on the Roll20 card + verbose console
    // Roll20 VTT chat: selectors are Roll20's long-stable chat markup.
    roll20ChatInput: "#textchat-input textarea",
    roll20ChatSend: "#textchat-input button, #chatSendBtn",
    rollName: "d20", // card name when the watch didn't say which die (auto)
  };

  let ws = null;
  let currentDie = "auto"; // follows the hub's `die` events (popup / desktop app)
  const log = (...a) => CONFIG.DEBUG && console.log("[towereye]", ...a);

  function connect() {
    ws = new WebSocket(CONFIG.hubUrl);
    ws.onopen = () => { console.log("[towereye] hub connected"); badge(dieLabel()); };
    ws.onclose = () => { badge("🎲✖"); setTimeout(connect, CONFIG.reconnectMs); };
    ws.onerror = () => ws.close();
    ws.onmessage = (m) => {
      let e; try { e = JSON.parse(m.data); } catch { return; }
      if (e.type === "result") {
        console.log(`[towereye] rolled ${e.value} (${e.reader} ${Number(e.confidence).toFixed(2)}) id=${e.roll_id}`);
      } else if (e.type !== "history") {
        log(e.type, e.reason || "");
      }
      if (e.type === "history") return; // late-join replay: never post old rolls
      if (e.type === "die") { currentDie = e.die; badge(dieLabel()); return; }
      if (e.type === "result") postToRoll20(e);
    };
  }

  // the die a roll was read as: stamped on the event by the watch, else the
  // live selection, else the d20 default
  function dieName(e) {
    const d = (e && e.die) || currentDie;
    return d && d !== "auto" ? d : CONFIG.rollName;
  }
  function dieLabel() { return currentDie === "auto" ? "🎲" : `🎲 ${currentDie}`; }

  const posted = new Set();
  function postToRoll20(e) {
    if (posted.has(e.roll_id)) return;
    const input = document.querySelector(CONFIG.roll20ChatInput);
    const send = document.querySelector(CONFIG.roll20ChatSend);
    if (!input || !send) { log("roll20 chat not found"); return; }
    posted.add(e.roll_id);
    const conf = Number.isFinite(e.confidence) ? ` ${e.confidence.toFixed(2)}` : "";
    const via = CONFIG.DEBUG ? ` {{via=${e.reader}${conf}}}` : "";
    const text = `&{template:default} {{name=🎲 ${dieName(e)}}} {{Result=**${e.value}**}}${via}`;
    input.value = text;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    send.click();
    log("posted to roll20", e.value);
  }

  function badge(text) {
    let b = document.getElementById("towereye-badge");
    if (!b) {
      b = document.createElement("div");
      b.id = "towereye-badge";
      b.style.cssText =
        "position:fixed;bottom:8px;right:8px;z-index:99999;font-size:14px;opacity:.6;";
      document.body.appendChild(b);
    }
    b.textContent = text;
  }

  connect();
})();
