/* Distribute Press Releases — shared behavior.
   Keep regression rules only:
   - Endpoint is never written into markup.
   - Address parts live as encoded attributes and are joined at runtime.
   - Submit path requires a prior genuine user gesture.
*/
(function () {
  "use strict";

  /* ---------- nav ---------- */
  var burger = document.querySelector(".burger");
  var nav = document.getElementById("nav");
  if (burger && nav) {
    burger.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      burger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.addEventListener("click", function (e) {
      if (e.target.tagName === "A") {
        nav.classList.remove("open");
        burger.setAttribute("aria-expanded", "false");
      }
    });
  }

  /* ---------- address assembly ---------- */
  var AT = String.fromCharCode(64);
  function dec(s) { try { return atob(s); } catch (e) { return ""; } }
  function joinAddr(el) {
    if (!el) return "";
    var u = dec(el.getAttribute("data-a") || "");
    var d = dec(el.getAttribute("data-b") || "");
    if (!u || !d) return "";
    return u + AT + d;
  }
  // visible mail links
  Array.prototype.forEach.call(document.querySelectorAll("a.eml"), function (a) {
    var addr = joinAddr(a);
    if (!addr) return;
    a.setAttribute("href", "mailto:" + addr);
    if (!a.textContent.trim() || a.textContent.trim() === "\u2026") a.textContent = addr;
  });

  /* ---------- gesture gate ---------- */
  var gestured = false;
  ["keydown", "pointerdown", "touchstart"].forEach(function (ev) {
    window.addEventListener(ev, function () { gestured = true; }, { once: true, passive: true });
  });
  var loadedAt = Date.now();

  /* ---------- hardened forms ---------- */
  Array.prototype.forEach.call(document.querySelectorAll("form[data-guard]"), function (form) {
    var status = form.querySelector(".form-status");
    var btn = form.querySelector("button[type=submit],input[type=submit]");
    function say(msg, cls) {
      if (!status) return;
      status.textContent = msg;
      status.className = "form-status " + (cls || "");
    }
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var hp = form.querySelector('input[name="_honey"]');
      if (hp && hp.value) { say("Could not send.", "err"); return; }
      if (!gestured) { say("Could not send.", "err"); return; }
      if (Date.now() - loadedAt < 3500) {
        say("Give the form a moment, then send again.", "err");
        return;
      }
      var addr = joinAddr(form);
      if (!addr) { say("Could not send. Please email us directly.", "err"); return; }
      var required = form.querySelectorAll("[required]");
      for (var i = 0; i < required.length; i++) {
        if (!required[i].value.trim()) {
          say("Fill in " + (required[i].getAttribute("data-label") || "every required field") + " first.", "err");
          required[i].focus();
          return;
        }
      }
      if (btn) { btn.disabled = true; btn.textContent = "Sending\u2026"; }
      say("Sending\u2026", "");
      var fd = new FormData(form);
      fd.delete("_honey");
      fetch("https://formsubmit.co/ajax/" + addr, {
        method: "POST",
        headers: { Accept: "application/json" },
        body: fd
      }).then(function (r) {
        return r.ok ? r.json() : Promise.reject(r.status);
      }).then(function () {
        form.reset();
        say("Sent. We reply to every message, usually within one business day.", "ok");
        if (btn) { btn.disabled = false; btn.textContent = btn.getAttribute("data-label") || "Send"; }
      }).catch(function () {
        say("That did not go through. Please email us directly and we will pick it up.", "err");
        if (btn) { btn.disabled = false; btn.textContent = btn.getAttribute("data-label") || "Send"; }
      });
    });
  });

  /* ---------- live board ---------- */
  var board = document.getElementById("board");
  if (board && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var rows = board.querySelectorAll("[data-state]");
    var clock = board.querySelector(".b-time");
    var step = 0;
    function tick() {
      step++;
      rows.forEach(function (row, i) {
        var el = row.querySelector(".b-state");
        var seq = (row.getAttribute("data-seq") || "").split("|");
        var idx = Math.max(0, Math.min(seq.length - 1, step - i));
        var parts = seq[idx].split(":");
        el.textContent = parts[1];
        el.className = "b-state " + parts[0];
      });
      if (clock) {
        var d = new Date();
        clock.textContent = String(d.getHours()).padStart(2, "0") + ":" +
          String(d.getMinutes()).padStart(2, "0") + ":" +
          String(d.getSeconds()).padStart(2, "0");
      }
      if (step > rows.length + 4) step = 0;
    }
    tick();
    setInterval(tick, 1400);
  }

  /* ---------- read aloud (device voices, no service, no cost) ---------- */
  Array.prototype.forEach.call(document.querySelectorAll("[data-speak]"), function (btn) {
    var synth = window.speechSynthesis;
    if (!synth) { btn.style.display = "none"; return; }
    var speaking = false;
    btn.addEventListener("click", function () {
      var src = document.querySelector(btn.getAttribute("data-speak"));
      if (!src) return;
      if (speaking) { synth.cancel(); speaking = false; btn.textContent = btn.getAttribute("data-label") || "Listen"; return; }
      var u = new SpeechSynthesisUtterance(src.innerText.replace(/\s+/g, " ").slice(0, 5000));
      u.rate = 1.0; u.pitch = 1.0;
      u.onend = function () { speaking = false; btn.textContent = btn.getAttribute("data-label") || "Listen"; };
      synth.cancel();
      synth.speak(u);
      speaking = true;
      btn.textContent = "Stop";
    });
  });

  /* ---------- copy buttons ---------- */
  Array.prototype.forEach.call(document.querySelectorAll("[data-copy]"), function (btn) {
    btn.addEventListener("click", function () {
      var src = document.querySelector(btn.getAttribute("data-copy"));
      if (!src) return;
      var text = src.value !== undefined ? src.value : src.textContent;
      var done = function () {
        var old = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = old; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var ta = document.createElement("textarea");
        ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
    });
  });

  /* ---------- download buttons ---------- */
  Array.prototype.forEach.call(document.querySelectorAll("[data-download]"), function (btn) {
    btn.addEventListener("click", function () {
      var src = document.querySelector(btn.getAttribute("data-download"));
      if (!src) return;
      var text = src.value !== undefined ? src.value : src.textContent;
      var blob = new Blob([text], { type: btn.getAttribute("data-mime") || "text/plain;charset=utf-8" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = btn.getAttribute("data-filename") || "download.txt";
      document.body.appendChild(a); a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); document.body.removeChild(a); }, 400);
    });
  });
})();
