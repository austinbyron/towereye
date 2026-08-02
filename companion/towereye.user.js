// ==UserScript==
// @name         towereye companion
// @namespace    towereye
// @version      0.1
// @description  Fill Beyond20 manual-roll dialogs from the dice tower camera
// @match        https://*.dndbeyond.com/*
// @match        https://*.roll20.net/*
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  // ---- CONFIG: adjust selectors after inspecting the live Beyond20 dialog ----
  const CONFIG = {
    hubUrl: "ws://127.0.0.1:8777",
    // Beyond20's manual roll prompt: set DEBUG=true, open a manual roll, and
    // read the candidate nodes from the console, then pin these selectors.
    dialogSelector: ".beyond20-manual-roll, [class*='manual-roll']",
    inputSelector: "input[type='number'], input[type='text']",
    labelSelector: ".beyond20-roll-title, h3, h4",
    submitSelector: "button[type='submit'], .beyond20-roll-button",
    DEBUG: true,
    reconnectMs: 3000,
  };
  // ---------------------------------------------------------------------------

  let ws = null;
  let activeDialog = null; // {node, input, rollId}
  const log = (...a) => CONFIG.DEBUG && console.log("[towereye]", ...a);

  function connect() {
    ws = new WebSocket(CONFIG.hubUrl);
    ws.onopen = () => { log("hub connected"); badge("🎲"); };
    ws.onclose = () => { badge("🎲✖"); setTimeout(connect, CONFIG.reconnectMs); };
    ws.onerror = () => ws.close();
    ws.onmessage = (m) => {
      let e; try { e = JSON.parse(m.data); } catch { return; }
      log("event", e);
      if (e.type === "result" && activeDialog) fill(e);
      if (e.type === "unread" && activeDialog) flag("camera couldn't read - enter manually");
    };
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }

  function fill(e) {
    const { input } = activeDialog;
    input.value = e.value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    if (Number.isFinite(e.confidence)) {
      input.style.outline = e.confidence >= 0.95 ? "2px solid #2e7d32" : "2px solid #f9a825";
      flag(`camera: ${e.value} (${e.reader} ${e.confidence.toFixed(2)}) - confirm or correct`);
    } else {
      flag(`camera: ${e.value} - confirm or correct`);
    }
    activeDialog.rollId = e.roll_id;
  }

  function flag(text) {
    if (!activeDialog) return;
    let note = activeDialog.node.querySelector(".towereye-note");
    if (!note) {
      note = document.createElement("div");
      note.className = "towereye-note";
      note.style.cssText = "font-size:12px;opacity:.8;margin-top:4px;";
      activeDialog.node.appendChild(note);
    }
    note.textContent = text;
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

  function onDialog(node) {
    const input = node.querySelector(CONFIG.inputSelector);
    if (!input) return;
    const labelNode = node.querySelector(CONFIG.labelSelector);
    const label = labelNode ? labelNode.textContent.trim() : "roll";
    activeDialog = { node, input, rollId: null };
    const dialog = activeDialog;
    log("armed for", label);
    send({ type: "arm", label, die: "d20" });
    const submit = node.querySelector(CONFIG.submitSelector);
    if (submit) {
      submit.addEventListener("click", () => {
        if (activeDialog === dialog && dialog.rollId) {
          const v = parseInt(input.value, 10);
          if (Number.isFinite(v)) {
            send({ type: "confirm", roll_id: dialog.rollId, value: v });
          }
        }
        if (activeDialog === dialog) activeDialog = null;
      }, { once: true });
    }
  }

  const observer = new MutationObserver((muts) => {
    for (const mut of muts) {
      for (const added of mut.addedNodes) {
        if (!(added instanceof HTMLElement)) continue;
        if (CONFIG.DEBUG && added.querySelector && added.querySelector("input")) {
          log("candidate dialog node:", added);
        }
        const node = added.matches && added.matches(CONFIG.dialogSelector)
          ? added
          : added.querySelector && added.querySelector(CONFIG.dialogSelector);
        if (node) onDialog(node);
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
  connect();
})();
