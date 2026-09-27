/* Distribute Press Releases — newsroom embed.
   Usage: <div id="dpr-newsroom" data-company="your-slug"></div>
          <script async src="https://distributepressreleases.com/assets/newsroom.js"></script>
   Renders client-side. Passes no ranking credit in either direction. */
(function () {
  "use strict";
  var host = document.getElementById("dpr-newsroom");
  if (!host) return;
  var company = host.getAttribute("data-company") || "";
  var limit = parseInt(host.getAttribute("data-limit") || "5", 10);
  var base = "https://distributepressreleases.com";
  var src = company
    ? base + "/newsrooms/" + encodeURIComponent(company) + "/feed.json"
    : base + "/feed.json";

  var css = "#dpr-newsroom{font-family:inherit;line-height:1.55}" +
    ".dprn-i{padding:.95rem 0;border-bottom:1px solid rgba(0,0,0,.09)}" +
    ".dprn-i:last-child{border-bottom:0}" +
    ".dprn-d{font-size:.8rem;opacity:.65;margin-bottom:.2rem}" +
    ".dprn-t{font-weight:650;text-decoration:none;color:inherit}" +
    ".dprn-t:hover{text-decoration:underline}" +
    ".dprn-s{font-size:.9rem;opacity:.8;margin:.25rem 0 0}" +
    ".dprn-c{font-size:.75rem;opacity:.6;margin-top:.9rem}" +
    ".dprn-e{font-size:.9rem;opacity:.7}";
  var st = document.createElement("style");
  st.textContent = css;
  document.head.appendChild(st);

  function render(items) {
    if (!items.length) {
      host.innerHTML = '<p class="dprn-e">No announcements published yet.</p>';
      return;
    }
    var html = items.slice(0, limit).map(function (it) {
      var d = it.date_published ? new Date(it.date_published) : null;
      var ds = d ? d.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }) : "";
      var sum = (it.summary || "").replace(/</g, "&lt;");
      return '<div class="dprn-i">' +
        (ds ? '<div class="dprn-d">' + ds + "</div>" : "") +
        '<a class="dprn-t" href="' + it.url + '" rel="noopener">' +
        (it.title || "").replace(/</g, "&lt;") + "</a>" +
        (sum ? '<p class="dprn-s">' + sum + "</p>" : "") +
        "</div>";
    }).join("");
    host.innerHTML = html +
      '<div class="dprn-c">Published via <a href="' + base +
      '/" rel="noopener">Distribute Press Releases</a>. Announcements are paid placements.</div>';
  }

  fetch(src, { cache: "no-cache" })
    .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
    .then(function (j) { render(j.items || []); })
    .catch(function () {
      host.innerHTML = '<p class="dprn-e">Announcements are temporarily unavailable.</p>';
    });
})();
