/*
 * ИИ-риелтор — встраиваемый виджет чата.
 *
 * Компания добавляет на свой сайт ОДНУ строку:
 *   <script src="https://ВАШ-СЕРВЕР/widget.js"
 *           data-tenant="demo"
 *           data-api="https://ВАШ-СЕРВЕР"></script>
 *
 * data-tenant — идентификатор компании (папка в tenants/)
 * data-api    — базовый URL сервера агента
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var TENANT = (script && script.getAttribute("data-tenant")) || "demo";
  // Адрес сервера: берём из data-api, иначе — из адреса самого этого скрипта.
  // Так клиенту достаточно вставить одну строку без data-api.
  var API = (script && script.getAttribute("data-api")) || "";
  if (!API && script && script.src) {
    try { API = new URL(script.src).origin; } catch (e) { API = ""; }
  }
  var TITLE = (script && script.getAttribute("data-title")) || "Online Realtor";
  var COLOR = (script && script.getAttribute("data-color")) || "#2563eb";

  var sessionId =
    "s_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);

  // --- Стили ---
  var css = [
    ".rea-btn{position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;",
    "background:" + COLOR + ";color:#fff;border:none;cursor:pointer;font-size:26px;z-index:99998;",
    "box-shadow:0 6px 20px rgba(0,0,0,.25)}",
    ".rea-panel{position:fixed;bottom:90px;right:20px;width:360px;max-width:calc(100vw - 40px);",
    "height:520px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;display:none;",
    "flex-direction:column;overflow:hidden;z-index:99999;box-shadow:0 12px 40px rgba(0,0,0,.28);",
    "font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif}",
    ".rea-panel.open{display:flex}",
    ".rea-head{background:" + COLOR + ";color:#fff;padding:14px 16px;font-weight:600;font-size:15px;",
    "display:flex;justify-content:space-between;align-items:center}",
    ".rea-head button{background:none;border:none;color:#fff;font-size:20px;cursor:pointer}",
    ".rea-msgs{flex:1;overflow-y:auto;padding:14px;background:#f7f8fa}",
    ".rea-m{margin:6px 0;padding:9px 12px;border-radius:14px;max-width:82%;font-size:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}",
    ".rea-m.bot{background:#fff;border:1px solid #e6e8ec;color:#111;border-bottom-left-radius:4px}",
    ".rea-m.user{background:" + COLOR + ";color:#fff;margin-left:auto;border-bottom-right-radius:4px}",
    ".rea-foot{display:flex;border-top:1px solid #eee;padding:8px}",
    ".rea-foot input{flex:1;border:1px solid #dcdfe4;border-radius:20px;padding:9px 14px;font-size:14px;outline:none}",
    ".rea-foot button{background:" + COLOR + ";color:#fff;border:none;border-radius:20px;padding:0 16px;margin-left:6px;cursor:pointer}",
    ".rea-typing{font-size:13px;color:#888;padding:0 14px 8px}",
  ].join("");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  // --- DOM ---
  var btn = el("button", "rea-btn", "💬");
  var panel = el("div", "rea-panel");
  panel.innerHTML =
    '<div class="rea-head"><span>' + esc(TITLE) + '</span><button aria-label="Close">×</button></div>' +
    '<div class="rea-msgs"></div>' +
    '<div class="rea-typing" style="display:none">typing…</div>' +
    '<div class="rea-foot"><input type="text" placeholder="Type a message…"/><button>➤</button></div>';
  document.body.appendChild(btn);
  document.body.appendChild(panel);

  var msgs = panel.querySelector(".rea-msgs");
  var input = panel.querySelector(".rea-foot input");
  var sendBtn = panel.querySelector(".rea-foot button");
  var closeBtn = panel.querySelector(".rea-head button");
  var typing = panel.querySelector(".rea-typing");
  var greeted = false;

  btn.onclick = function () {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) {
      input.focus();
      if (!greeted) {
        greeted = true;
        addMsg("bot", "Hi there! 👋 I can help you find a home within your budget. Are you looking to buy or to rent?");
      }
    }
  };
  closeBtn.onclick = function () { panel.classList.remove("open"); };
  sendBtn.onclick = send;
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") send();
  });

  function send() {
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMsg("user", text);
    typing.style.display = "block";
    sendBtn.disabled = true;

    fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Tenant-Id": TENANT },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        addMsg("bot", data.reply);
      })
      .catch(function () {
        addMsg("bot", "Sorry, a technical glitch. Please try again in a moment.");
      })
      .finally(function () {
        typing.style.display = "none";
        sendBtn.disabled = false;
        input.focus();
      });
  }

  function addMsg(role, text) {
    var m = el("div", "rea-m " + role, text);
    msgs.appendChild(m);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
})();
