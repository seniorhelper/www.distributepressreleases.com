/* Distribute Press Releases — network module.
   Shows the releases the routing filter matched to this site.
   Usage:
     <section id="business-news" hidden> ...heading...
       <div data-dpr-network="site-id" data-limit="4"></div>
     </section>
     <script async src="https://distributepressreleases.com/assets/network.js"></script>
   The enclosing section stays hidden until there is at least one release, so a
   site never shows an empty box. Every item keeps its paid or affiliated label
   and links to the original release, marked sponsored. */
(function () {
  "use strict";
  var BASE = "https://distributepressreleases.com";
  var hosts = document.querySelectorAll("[data-dpr-network]");
  if (!hosts.length) return;

  var css = ".dprx{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:16px;margin:0;padding:0;list-style:none;font-family:inherit}" +
    ".dprx-i{border:1px solid rgba(127,127,127,.28);border-radius:12px;padding:16px 18px;background:rgba(127,127,127,.05);display:flex;flex-direction:column;gap:6px;min-width:0}" +
    ".dprx-l{font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;opacity:.72}" +
    ".dprx-t{font-weight:700;line-height:1.3;color:inherit;text-decoration:none;overflow-wrap:anywhere}" +
    ".dprx-t:hover,.dprx-t:focus{text-decoration:underline}" +
    ".dprx-s{font-size:.92rem;line-height:1.5;opacity:.85;margin:0;overflow-wrap:anywhere}" +
    ".dprx-m{font-size:.8rem;opacity:.7;margin-top:auto}" +
    ".dprx-f{font-size:.8rem;opacity:.7;margin-top:14px}" +
    ".dprx-f a{color:inherit}";
  var st = document.createElement("style");
  st.textContent = css;
  document.head.appendChild(st);

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[c];
    });
  }
  function safeUrl(u) { return /^https:\/\/distributepressreleases\.com\//.test(u || "") ? u : BASE + "/releases/"; }

  Array.prototype.forEach.call(hosts, function (host) {
    var id = (host.getAttribute("data-dpr-network") || "").replace(/[^a-z0-9-]/gi, "");
    var limit = parseInt(host.getAttribute("data-limit") || "4", 10);
    var box = host.closest("[hidden]") || null;
    if (!id) return;
    fetch(BASE + "/syndication/" + id + ".json", {cache: "no-cache"})
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (j) {
        var items = (j.items || []).slice(0, limit);
        if (!items.length) return;
        host.innerHTML = '<ul class="dprx">' + items.map(function (it) {
          var x = it._dpr || {};
          var d = it.date_published ? new Date(it.date_published) : null;
          var ds = d ? d.toLocaleDateString("en-US", {year: "numeric", month: "short", day: "numeric", timeZone: "UTC"}) : "";
          var where = [x.city, x.state].filter(Boolean).join(", ");
          return '<li class="dprx-i"><span class="dprx-l">' + esc(x.label || "Press release") + "</span>" +
            '<a class="dprx-t" href="' + esc(safeUrl(it.url)) + '" rel="sponsored noopener" target="_blank">' + esc(it.title) + "</a>" +
            '<p class="dprx-s">' + esc(it.summary) + "</p>" +
            '<span class="dprx-m">' + esc(x.company || "") + (where ? " · " + esc(where) : "") + (ds ? " · " + esc(ds) : "") + "</span></li>";
        }).join("") + "</ul>" +
          '<p class="dprx-f">Press releases are written by the companies named and published through <a href="' + BASE +
          '/network/" rel="noopener" target="_blank">Distribute Press Releases</a>, which shares ownership with this site. Each is labeled paid or affiliated. Publication is not endorsement.</p>';
        if (box) box.hidden = false;
      })
      .catch(function () { /* stay hidden */ });
  });
})();
