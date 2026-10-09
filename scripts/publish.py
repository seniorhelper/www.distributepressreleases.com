#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Distribute Press Releases - publisher.

Reads every file in content/releases/*.md and regenerates the whole
published surface: release pages, machine-readable companions, receipts,
all feeds, the news sitemap, per-industry and per-region feeds, per-company
newsroom feeds, and the podcast feed.

Run with no arguments from the repository root:

    python3 scripts/publish.py

Flags:
    --dry-run     build everything, write nothing
    --no-audio    skip narration even if piper is installed
    --no-ping     never announce, even with --announce
    --announce    after the build, push new URLs to IndexNow and post to
                  Bluesky and Mastodon, record the results in data/announced.json
                  and rebuild the receipts. Run this once the pages are live.

Optional front matter beyond the example below:
    affiliated: operator            the company is Eye To Ad Media itself
    affiliated: common-ownership    the company shares ownership with the operator
    network: none                   keep the release off network sites
    network: site-id, site-id       force specific network sites (config/network.json)
    syndicate: no                   also keep it off the news property
    keywords: words, for, routing   extra routing hints, never displayed
A release dated in the future is held back and publishes on its date.

Every network step is optional and failure there never blocks publishing.
The site is built first; announcements go out after.

Release file format - YAML-ish front matter, then the body in markdown:

    ---
    title: Northgate Plumbing Adds 14 Technicians and Opens Second Aurora Location
    slug: northgate-plumbing-second-aurora-location
    company: Northgate Plumbing
    company_url: https://example.com
    company_slug: northgate-plumbing
    city: Aurora
    state: Colo.
    date: 2026-03-04
    industry: home-services
    region: colorado
    summary: One sentence for feeds and search results.
    image: https://example.com/photo.jpg
    contact_name: Dana Ruiz
    contact_email: press@example.com
    contact_phone: 303-555-0142
    claims:
      - statement: Northgate Plumbing opened a second service center on March 1, 2026.
        type: event
        date: 2026-03-01
    ---

    Body paragraphs here. Blank line between paragraphs.
"""

import os, sys, re, json, html, glob, datetime, hashlib, subprocess, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://distributepressreleases.com"
NAME = "Distribute Press Releases"
GSC = "6HBMgSReUu5XrKZvv5L7rxL1f8MsIUgrbHGY9rSRNuo"
CONTENT = os.path.join(ROOT, "content", "releases")

DRY = "--dry-run" in sys.argv
NO_AUDIO = "--no-audio" in sys.argv
NO_PING = "--no-ping" in sys.argv
# Announcing (IndexNow, Bluesky, Mastodon) happens only with --announce, after the
# pages are live. The workflow builds, pushes, waits for Pages to serve the new
# release, then runs again with --announce so engines and link cards never hit a 404.
ANNOUNCE = "--announce" in sys.argv and not NO_PING
TODAY = datetime.datetime.now(datetime.timezone.utc).date()
LEDGER = os.path.join(ROOT, "data", "announced.json")
NETWORK = os.path.join(ROOT, "config", "network.json")

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def log(*a):
    print("[publish]", *a, flush=True)


def esc(s):
    return html.escape(str(s), quote=True)


def write(rel, text, binary=False):
    p = os.path.join(ROOT, rel.lstrip("/"))
    if DRY:
        log("would write", rel, "(%d bytes)" % len(text))
        return p
    os.makedirs(os.path.dirname(p), exist_ok=True)
    mode = "wb" if binary else "w"
    with open(p, mode) as f:
        f.write(text if binary else text)
    return p


# ---------------------------------------------------------------- parsing

def parse_front_matter(raw):
    """Small, dependency-free front matter reader. Supports scalars, simple
    lists, and a list of single-level mappings (used for claims)."""
    if not raw.startswith("---"):
        raise ValueError("file does not start with front matter")
    _, fm, body = raw.split("---", 2)
    meta, key_stack = {}, None
    lines = fm.strip("\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        if re.match(r"^\s*-\s", line) and key_stack:
            item = line.strip()[2:]
            if ":" in item and not item.startswith("http"):
                obj, k, v = {}, *item.split(":", 1)
                obj[k.strip()] = v.strip()
                j = i + 1
                while j < len(lines) and re.match(r"^\s{4,}\S", lines[j]) and ":" in lines[j]:
                    k2, v2 = lines[j].split(":", 1)
                    obj[k2.strip()] = v2.strip()
                    j += 1
                meta[key_stack].append(obj)
                i = j
                continue
            meta[key_stack].append(item)
            i += 1
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v == "":
                meta[k] = []
                key_stack = k
            else:
                meta[k] = v.strip('"').strip("'")
                key_stack = None
        i += 1
    return meta, body.strip()


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return re.sub(r"-{2,}", "-", s) or "release"


def md_paragraphs(body):
    out = []
    for block in re.split(r"\n\s*\n", body.strip()):
        b = block.strip()
        if not b:
            continue
        if b.startswith("## "):
            out.append(("h2", b[3:].strip()))
        elif all(re.match(r"^\s*[-*]\s+", ln) for ln in b.split("\n")):
            out.append(("ul", [re.sub(r"^\s*[-*]\s+", "", ln).strip() for ln in b.split("\n")]))
        elif b.startswith("> "):
            out.append(("quote", re.sub(r"^> ?", "", b, flags=re.M).strip()))
        else:
            out.append(("p", b))
    return out


def inline_md(s, sponsored=True):
    """Bold, italic and links. Every link is marked sponsored - not optional."""
    rel = ' rel="sponsored noopener" target="_blank"' if sponsored else ""
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               lambda m: '<a href="%s"%s>%s</a>' % (m.group(2), rel, m.group(1)), s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"(https?://[^\s<]+)(?![^<]*</a>)",
               lambda m: '<a href="%s"%s>%s</a>' % (m.group(1), rel, m.group(1)), s)
    return s


def long_date(iso):
    try:
        y, m, d = [int(x) for x in str(iso).split("-")]
        return "%s %d, %d" % (MONTHS[m - 1], d, y)
    except Exception:
        return str(iso)


def rfc2822(iso):
    try:
        y, m, d = [int(x) for x in str(iso).split("-")]
        return datetime.datetime(y, m, d, 12, 0, 0).strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def load_releases():
    if not os.path.isdir(CONTENT):
        log("no content/releases directory - nothing to publish")
        return []
    items = []
    for path in sorted(glob.glob(os.path.join(CONTENT, "*.md"))):
        # files beginning with _ are drafts and templates, never published
        if os.path.basename(path).startswith("_"):
            continue
        try:
            meta, body = parse_front_matter(open(path, encoding="utf-8").read())
        except Exception as e:
            log("SKIP %s - %s" % (os.path.basename(path), e))
            continue
        missing = [k for k in ("title", "company", "date") if not meta.get(k)]
        if missing:
            log("SKIP %s - missing %s" % (os.path.basename(path), ", ".join(missing)))
            continue
        try:
            if datetime.date.fromisoformat(str(meta["date"])) > TODAY:
                log("HOLD %s - dated %s, publishes on that day" % (os.path.basename(path), meta["date"]))
                continue
        except ValueError:
            log("SKIP %s - date must be YYYY-MM-DD" % os.path.basename(path))
            continue
        aff = str(meta.get("affiliated") or "").strip().lower()
        meta["affiliated"] = ("operator" if aff in ("operator", "self")
                              else "common-ownership" if aff in ("yes", "true", "common-ownership", "common ownership")
                              else "")
        meta["slug"] = meta.get("slug") or slugify(meta["title"])[:80]
        meta["company_slug"] = meta.get("company_slug") or slugify(meta["company"])
        meta["industry"] = slugify(meta.get("industry") or "general")
        meta["region"] = slugify(meta.get("region") or "national")
        meta["url"] = "%s/releases/%s/" % (SITE, meta["slug"])
        meta["body"] = body
        meta["source_file"] = path
        if not meta.get("summary"):
            first = next((t for k, t in md_paragraphs(body) if k == "p"), "")
            meta["summary"] = re.sub(r"\s+", " ", first)[:200].rsplit(" ", 1)[0] + "\u2026"
        items.append(meta)
    items.sort(key=lambda r: (str(r["date"]), r["slug"]), reverse=True)
    return items


# ---------------------------------------------------------------- render

DISCLOSURE = (
    "This is a paid press release. It was submitted and paid for by the company "
    "named in it and published by Distribute Press Releases. It is not independent "
    "journalism, and publication here is not verification of any claim it contains. "
    "Links in this release are marked sponsored."
)
DISCLOSURE_OPERATOR = (
    "This is a press release from Eye To Ad Media, the company that operates "
    "Distribute Press Releases. It was not paid for, it is not independent journalism, "
    "and publication here is not verification of any claim it contains. "
    "Links in this release are marked sponsored."
)
DISCLOSURE_COMMON = (
    "This is a press release from a company under common ownership with Eye To Ad Media, "
    "which operates Distribute Press Releases. It was not paid for, it is not independent "
    "journalism, and publication here is not verification of any claim it contains. "
    "Links in this release are marked sponsored."
)


def disclosure(r):
    return {"operator": DISCLOSURE_OPERATOR,
            "common-ownership": DISCLOSURE_COMMON}.get(r.get("affiliated"), DISCLOSURE)


def label(r):
    """Short label for feeds, cards and the network module."""
    return {"operator": "Affiliated: operator’s own release",
            "common-ownership": "Affiliated: common ownership"}.get(r.get("affiliated"), "Paid press release")


def release_html(r, prev_next):
    blocks = md_paragraphs(r["body"])
    # the first paragraph joins the dateline rather than trailing after an empty one
    lede = ""
    if blocks and blocks[0][0] == "p":
        lede = inline_md(blocks[0][1])
        blocks = blocks[1:]
    paras = []
    for kind, text in blocks:
        if kind == "ul":
            paras.append("      <ul>%s</ul>" % "".join("<li>%s</li>" % inline_md(t) for t in text))
        elif kind == "h2":
            paras.append("      <h2>%s</h2>" % esc(text))
        elif kind == "quote":
            paras.append('      <blockquote style="border-left:3px solid var(--signal);'
                         'padding-left:1.1rem;margin:1.4rem 0;font-style:normal">%s</blockquote>'
                         % inline_md(text))
        else:
            paras.append("      <p>%s</p>" % inline_md(text))
    body_html = "\n".join(paras)

    claims = r.get("claims") or []
    graph = [
        {
            "@type": "NewsArticle",
            "@id": r["url"] + "#article",
            "headline": r["title"][:110],
            "description": r["summary"],
            "datePublished": str(r["date"]),
            "dateModified": str(r.get("modified") or r["date"]),
            "mainEntityOfPage": {"@type": "WebPage", "@id": r["url"]},
            "url": r["url"],
            "isAccessibleForFree": True,
            "author": {"@type": "Organization", "name": r["company"]},
            "publisher": {
                "@type": "Organization",
                "name": NAME,
                "url": SITE + "/",
                "logo": {"@type": "ImageObject",
                         "url": SITE + "/images/distribute-press-releases-logo.png"},
            },
            "about": {
                "@type": "Organization",
                "name": r["company"],
                **({"url": r["company_url"], "sameAs": [r["company_url"]]}
                   if r.get("company_url") else {}),
            },
            "creditText": label(r),
            "isBasedOn": r["url"] + "claims.json",
        },
        {
            "@type": "NewsMediaOrganization",
            "@id": SITE + "/#org",
            "name": NAME,
            "url": SITE + "/",
            "logo": {"@type": "ImageObject",
                     "url": SITE + "/images/distribute-press-releases-logo.png"},
            "email": "info@eyetoad.com",
            "ethicsPolicy": SITE + "/editorial-standards/",
            "correctionsPolicy": SITE + "/corrections/",
            "diversityPolicy": SITE + "/editorial-standards/",
            "actionableFeedbackPolicy": SITE + "/corrections/",
            "publishingPrinciples": SITE + "/editorial-standards/",
            "address": {"@type": "PostalAddress", "streetAddress": "1001 Bannock St #660",
                        "addressLocality": "Denver", "addressRegion": "CO",
                        "postalCode": "80204", "addressCountry": "US"},
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
                {"@type": "ListItem", "position": 2, "name": "Releases", "item": SITE + "/releases/"},
                {"@type": "ListItem", "position": 3, "name": r["title"][:80], "item": r["url"]},
            ],
        },
    ]
    if r.get("image"):
        graph[0]["image"] = [r["image"]]

    audio_block = ""
    if r.get("has_audio"):
        audio_block = """      <div class="audio-row" style="margin:1.6rem 0">
        <audio controls preload="none" style="flex:1;min-width:240px" src="%saudio.mp3"></audio>
        <span style="font-size:.84rem;color:var(--slate-2)">Synthetic narration. <a href="/ai-disclosure/">AI disclosure</a>.</span>
      </div>""" % r["url"]
        graph[0]["audio"] = {"@type": "AudioObject", "contentUrl": r["url"] + "audio.mp3",
                             "encodingFormat": "audio/mpeg"}

    contact = []
    if r.get("contact_name"): contact.append(esc(r["contact_name"]))
    if r.get("contact_email"): contact.append(esc(r["contact_email"]))
    if r.get("contact_phone"): contact.append(esc(r["contact_phone"]))
    contact_html = ("<p>" + "<br>".join(contact) + "</p>") if contact else ""

    prev_link, next_link = prev_next
    nav = []
    if prev_link: nav.append('<a href="%s">&larr; Previous release</a>' % prev_link)
    if next_link: nav.append('<a href="%s">Next release &rarr;</a>' % next_link)

    return """<!DOCTYPE html>
<html lang="en-US">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="google-site-verification" content="{gsc}">
<title>{title_short}</title>
<meta name="description" content="{summary}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<meta property="og:type" content="article">
<meta property="og:title" content="{title_attr}">
<meta property="og:description" content="{summary}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img}">
<meta property="article:published_time" content="{date}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/images/distribute-press-releases-apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#08214A">
<meta property="og:locale" content="en_US">
<link rel="alternate" type="text/markdown" href="{url}index.md">
<link rel="alternate" type="application/json" title="Machine-readable service description" href="{site}/api/service.json">
<link rel="alternate" type="application/json" href="{url}claims.json">
<link rel="alternate" type="application/rss+xml" title="{name}" href="{site}/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<link rel="stylesheet" href="/assets/dpr.css">
<script type="application/ld+json">
{graph}
</script>
</head>
<body>
<a class="sr-only" href="#main">Skip to content</a>
<header class="site-head">
  <div class="wrap head-in">
    <a class="brand" href="/">
      <img src="/images/distribute-press-releases-mark.png" alt="" width="52" height="38">
      <span>Distribute Press Releases</span>
    </a>
    <button class="burger" type="button" aria-label="Menu" aria-expanded="false" aria-controls="nav">
      <span></span><span></span><span></span>
    </button>
    <nav class="nav" id="nav" aria-label="Main">
      <a href="/releases/">Releases</a>
      <a href="/press-release-distribution-service/">Distribution</a>
      <a href="/tools/">Free tools</a>
      <a href="/pricing/">Pricing</a>
      <a class="nav-cta" href="/contact/">Start a release</a>
    </nav>
  </div>
</header>
<main id="main">
  <article>
    <section class="hero" style="padding-bottom:clamp(1.4rem,3vw,2rem)">
      <div class="wrap-narrow">
        <p class="paid-label">{disclosure}</p>
        <h1>{title}</h1>
        <p style="color:var(--slate);font-size:.94rem;margin-bottom:0">
          Published {long_date}{company_line}
        </p>
      </div>
    </section>
    <section style="padding-top:clamp(1.4rem,3vw,2rem)">
      <div class="wrap-narrow">
{audio}
        <div class="release-body">
          <p><span class="dateline">{city_state}{long_date}</span> &mdash; {first}</p>
{body}
        </div>
        <div class="audio-row" style="margin-top:1.8rem">
          <button class="btn btn-ghost" type="button" data-speak=".release-body" data-label="Listen">Listen</button>
          <a class="btn btn-ghost" href="{url}index.md">Markdown</a>
          <a class="btn btn-ghost" href="{url}claims.json">Claims file</a>
          <a class="btn btn-ghost" href="{url}receipt/">Distribution receipt</a>
          <a class="btn btn-ghost" href="/newsrooms/{cslug}/">{company} newsroom</a>
        </div>{carried}
        <h2 style="margin-top:2.4rem;font-size:1.15rem">Media contact</h2>
        {contact}
        <div class="note note-caution" style="margin-top:2rem">
          <p>{disclosure}</p>
          <p style="margin-bottom:0"><a href="/corrections/">Report an error in this release</a> &mdash; corrections are free and we make them regardless of who reports them.</p>
        </div>
        <p style="margin-top:2rem;display:flex;gap:1.4rem;flex-wrap:wrap">{nav}</p>
      </div>
    </section>
  </article>
</main>
<footer class="site-foot">
  <div class="wrap">
    <div class="foot-legal" style="border-top:0;margin-top:0">
      <span>&copy; 2026 Distribute Press Releases. Powered by <a href="https://eyetoad.com/">Eye To Ad Media</a>.</span>
      <a href="/editorial-standards/">Editorial standards</a>
      <a href="/corrections/">Corrections</a>
      <a href="/ai-disclosure/">AI disclosure</a>
      <a href="/terms/">Terms</a>
      <a href="/privacy/">Privacy</a>
    </div>
  </div>
  <div class="stamp"><a href="https://eyetoad.com/" aria-label="Built by Eye To Ad Media" title="Built by Eye To Ad Media">&#10084;&#65039;</a></div>
</footer>
<script src="/assets/dpr.js" defer></script>
<script src="/assets/wire-bot.js" defer></script>
</body>
</html>
""".format(
        gsc=GSC, title=esc(r["title"]), title_attr=esc(r["title"]),
        title_short=esc(r["title"][:58] + (" | DPR" if len(r["title"]) < 52 else "")),
        summary=esc(r["summary"]), url=r["url"], site=SITE, name=NAME,
        img=r.get("image") or SITE + "/images/distribute-press-releases-share-card.png",
        date=str(r["date"]), graph=json.dumps({"@context": "https://schema.org", "@graph": graph},
                                              indent=2, ensure_ascii=False),
        disclosure=disclosure(r), long_date=long_date(r["date"]),
        company_line=(" by " + esc(r["company"])) if r.get("company") else "",
        city_state=("%s, %s, " % (esc(r.get("city", "")).upper(), esc(r.get("state", "")))
                    if r.get("city") else ""),
        first=lede, body=body_html, audio=audio_block, contact=contact_html,
        nav=" ".join(nav) or '<a href="/releases/">All releases</a>',
        cslug=r["company_slug"], company=esc(r["company"]), carried=carried_html(r),
    )


def carried_html(r):
    """Where the routing engine sent this release, shown under the actions."""
    dests = placements(r)
    if not dests:
        return ""
    links = ", ".join('<a href="%s" rel="noopener">%s</a>' % (esc(d["link"]), esc(d["name"]))
                      for d in dests)
    return ('\n        <p style="margin-top:1.2rem;font-size:.92rem;color:var(--slate)">'
            "Also carried on %s. Each carries this same label and points back here as the original."
            "</p>" % links)


def release_markdown(r):
    lines = ["# " + r["title"], ""]
    lines.append("> %s" % disclosure(r))
    lines.append("")
    lines.append("- Published: %s" % long_date(r["date"]))
    lines.append("- Company: %s%s" % (r["company"],
                                      " (%s)" % r["company_url"] if r.get("company_url") else ""))
    if r.get("city"):
        lines.append("- Dateline: %s, %s" % (r["city"], r.get("state", "")))
    lines.append("- Canonical: %s" % r["url"])
    lines.append("")
    lines.append(r["body"].strip())
    lines.append("")
    if r.get("contact_name") or r.get("contact_email"):
        lines.append("## Media contact")
        for k in ("contact_name", "contact_email", "contact_phone"):
            if r.get(k):
                lines.append("- %s" % r[k])
    return "\n".join(lines) + "\n"


def release_claims(r):
    claims = []
    for c in (r.get("claims") or []):
        if isinstance(c, dict):
            claims.append({
                "statement": c.get("statement", ""),
                "type": c.get("type", "statement"),
                "date": c.get("date", str(r["date"])),
                "source": r["url"],
                "attributedTo": r["company"],
            })
        else:
            claims.append({"statement": str(c), "type": "statement",
                           "date": str(r["date"]), "source": r["url"],
                           "attributedTo": r["company"]})
    return json.dumps({
        "release": r["url"],
        "title": r["title"],
        "published": str(r["date"]),
        "modified": str(r.get("modified") or r["date"]),
        "publisher": NAME,
        "disclosure": "affiliated, not paid" if r.get("affiliated") else "paid placement",
        "verification": "Statements are attributed to the subject. Publication is not verification.",
        "subject": {
            "name": r["company"], "type": "Organization",
            **({"sameAs": [r["company_url"]]} if r.get("company_url") else {}),
        },
        "industry": r["industry"], "region": r["region"],
        "claims": claims,
        "artifacts": {
            "html": r["url"], "markdown": r["url"] + "index.md",
            "claims": r["url"] + "claims.json", "receipt": r["url"] + "receipt/",
            **({"audio": r["url"] + "audio.mp3"} if r.get("has_audio") else {}),
        },
    }, indent=2, ensure_ascii=False) + "\n"


def receipt_html(r, results):
    rows = "\n".join(
        '        <tr><td><strong>%s</strong><br><span style="color:var(--slate-2);font-size:.85rem">%s</span></td>'
        '<td>%s</td><td>%s</td></tr>' % (esc(a), esc(b), esc(c),
                                         ('<a href="%s" rel="noopener">open</a>' % esc(d)) if d else "\u2014")
        for a, b, c, d in results
    )
    return """<!DOCTYPE html>
<html lang="en-US">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="google-site-verification" content="{gsc}">
<title>Distribution receipt</title>
<meta name="description" content="Public record of every channel this press release was published to, with dates and working links.">
<link rel="canonical" href="{url}receipt/">
<meta name="robots" content="index, follow">
<meta property="og:locale" content="en_US">
<meta name="theme-color" content="#08214A">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="manifest" href="/site.webmanifest">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700;800&display=swap">
<link rel="stylesheet" href="/assets/dpr.css">
</head>
<body>
<header class="site-head"><div class="wrap head-in">
  <a class="brand" href="/"><img src="/images/distribute-press-releases-mark.png" alt="" width="52" height="38"><span>Distribute Press Releases</span></a>
</div></header>
<main id="main"><section class="hero"><div class="wrap-narrow">
  <span class="eyebrow">Distribution receipt</span>
  <h1>Where this release went</h1>
  <p class="lede"><a href="{url}">{title}</a></p>
  <p style="color:var(--slate);font-size:.92rem">Generated automatically when the release published. Every row is a real destination with a working link, or an honest note that a channel did not take it.</p>
</div></section>
<section style="padding-top:0"><div class="wrap-narrow">
  <div class="table-wrap"><table>
    <thead><tr><th>Channel</th><th>Result</th><th>Link</th></tr></thead>
    <tbody>
{rows}
    </tbody>
    <caption>A row recorded here means the publish job completed that step. It does not mean a search engine indexed the page, a directory surfaced it, or anyone read it \u2014 those are decisions made by systems we do not control.</caption>
  </table></div>
  <p style="margin-top:1.6rem"><a class="btn btn-ghost" href="{url}">Back to the release</a></p>
</div></section></main>
<footer class="site-foot"><div class="wrap"><div class="foot-legal" style="border-top:0;margin-top:0">
  <span>&copy; 2026 Distribute Press Releases.</span>
  <a href="/editorial-standards/">Editorial standards</a><a href="/corrections/">Corrections</a>
</div></div><div class="stamp"><a href="https://eyetoad.com/" title="Built by Eye To Ad Media">&#10084;&#65039;</a></div></footer>
</body></html>
""".format(gsc=GSC, url=r["url"], title=esc(r["title"]), rows=rows)


# ---------------------------------------------------------------- feeds

def rss(items, self_url, title_suffix=""):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    entries = []
    for r in items:
        enc = ('\n      <enclosure url="%saudio.mp3" type="audio/mpeg" length="%d"/>'
               % (r["url"], audio_len(r))) if r.get("has_audio") else ""
        media = ('\n      <media:content url="%s" medium="image"/>' % esc(r["image"])) \
            if r.get("image") else ""
        entries.append("""    <item>
      <title>{t}</title>
      <link>{u}</link>
      <guid isPermaLink="true">{u}</guid>
      <pubDate>{d}</pubDate>
      <dc:creator>{c}</dc:creator>
      <category>{cat}</category>
      <description>{s}</description>{enc}{media}
    </item>""".format(t=esc(r["title"]), u=r["url"], d=rfc2822(r["date"]),
                      c=esc(r["company"]), cat=esc(r["industry"]),
                      s=esc(r["summary"]), enc=enc, media=media))
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>{n}{sfx}</title>
    <link>{s}/</link>
    <description>Press releases published and syndicated by {n}. Every item is labeled as a paid or affiliated placement, and publication is not verification.</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
    <atom:link href="{self}" rel="self" type="application/rss+xml"/>
    <copyright>2026 {n}</copyright>
{items}
  </channel>
</rss>
""".format(n=NAME, sfx=title_suffix, s=SITE, now=now, self=self_url,
           items="\n".join(entries))


def atom(items):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = "\n".join("""  <entry>
    <title>{t}</title>
    <link href="{u}"/>
    <id>{u}</id>
    <updated>{d}T12:00:00Z</updated>
    <author><name>{c}</name></author>
    <summary>{s}</summary>
    <rights>{lab}</rights>
  </entry>""".format(t=esc(r["title"]), u=r["url"], d=str(r["date"]),
                     c=esc(r["company"]), s=esc(r["summary"]), lab=esc(label(r))) for r in items)
    return """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{n}</title>
  <link href="{s}/"/>
  <link href="{s}/atom.xml" rel="self"/>
  <updated>{now}</updated>
  <id>{s}/</id>
  <subtitle>Paid press releases, published and syndicated.</subtitle>
{e}
</feed>
""".format(n=NAME, s=SITE, now=now, e=entries)


def jsonfeed(items, url=None):
    return json.dumps({
        "version": "https://jsonfeed.org/version/1.1",
        "title": NAME,
        "home_page_url": SITE + "/",
        "feed_url": url or SITE + "/feed.json",
        "description": "Press releases published and syndicated by %s. Every item is labeled as a paid or affiliated placement." % NAME,
        "language": "en-US",
        "authors": [{"name": NAME, "url": SITE + "/"}],
        "items": [{
            "id": r["url"],
            "url": r["url"],
            "title": r["title"],
            "summary": r["summary"],
            "content_text": re.sub(r"\s+", " ", r["body"])[:1200],
            "date_published": "%sT12:00:00Z" % r["date"],
            "authors": [{"name": r["company"]}],
            "tags": [r["industry"], r["region"], label(r).lower()],
            **({"image": r["image"]} if r.get("image") else {}),
            **({"attachments": [{"url": r["url"] + "audio.mp3",
                                 "mime_type": "audio/mpeg"}]} if r.get("has_audio") else {}),
        } for r in items],
    }, indent=2, ensure_ascii=False) + "\n"


def audio_len(r):
    p = os.path.join(ROOT, "releases", r["slug"], "audio.mp3")
    return os.path.getsize(p) if os.path.exists(p) else 0


def podcast(items):
    eps = "\n".join("""    <item>
      <title>{t}</title>
      <link>{u}</link>
      <guid isPermaLink="false">{u}audio.mp3</guid>
      <pubDate>{d}</pubDate>
      <description>{s} This episode is a press release from {c} and uses synthetic narration.</description>
      <itunes:summary>{s} Press release. Synthetic narration.</itunes:summary>
      <itunes:author>{c}</itunes:author>
      <itunes:explicit>false</itunes:explicit>
      <enclosure url="{u}audio.mp3" type="audio/mpeg" length="{n}"/>
    </item>""".format(t=esc(r["title"]), u=r["url"], d=rfc2822(r["date"]),
                      s=esc(r["summary"]), c=esc(r["company"]), n=audio_len(r))
                    for r in items if r.get("has_audio"))
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Distribute Press Releases \u2014 Announcements</title>
    <link>{s}/podcast/</link>
    <description>Business announcements, read aloud. Every episode is a press release, labeled paid or affiliated on its page, and uses synthetic narration, disclosed in each episode.</description>
    <language>en-us</language>
    <itunes:author>Distribute Press Releases</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Business"/>
    <itunes:image href="{s}/images/distribute-press-releases-share-card.png"/>
    <itunes:owner><itunes:name>Distribute Press Releases</itunes:name><itunes:email>info@eyetoad.com</itunes:email></itunes:owner>
    <atom:link href="{s}/podcast.xml" rel="self" type="application/rss+xml"/>
{e}
  </channel>
</rss>
""".format(s=SITE, e=eps)


def news_sitemap(items):
    cutoff = datetime.date.today() - datetime.timedelta(days=2)
    recent = []
    for r in items:
        try:
            y, m, d = [int(x) for x in str(r["date"]).split("-")]
            if datetime.date(y, m, d) >= cutoff:
                recent.append(r)
        except Exception:
            pass
    urls = "\n".join("""  <url>
    <loc>{u}</loc>
    <news:news>
      <news:publication>
        <news:name>{n}</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>{d}</news:publication_date>
      <news:title>{t}</news:title>
    </news:news>
  </url>""".format(u=r["url"], n=NAME, d=str(r["date"]), t=esc(r["title"]))
                    for r in recent)
    return """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <!-- Only releases from the last 48 hours appear here, per the news sitemap
       specification. Regenerated on every publish. -->
{u}
</urlset>
""".format(u=urls)


STATIC_PAGES = [
    ("/", "1.0", "weekly"), ("/releases/", "0.9", "daily"),
    ("/press-release-distribution-service/", "0.9", "monthly"),
    ("/pricing/", "0.9", "monthly"), ("/how-it-works/", "0.8", "monthly"),
    ("/press-release-distribution-channels/", "0.8", "monthly"),
    ("/newsroom/", "0.8", "monthly"), ("/podcast/", "0.7", "monthly"),
    ("/tools/", "0.8", "monthly"),
    ("/tools/press-release-grader/", "0.8", "monthly"),
    ("/tools/newsworthiness-check/", "0.8", "monthly"),
    ("/tools/press-release-template/", "0.8", "monthly"),
    ("/tools/press-release-schema-generator/", "0.7", "monthly"),
    ("/tools/headline-scorer/", "0.7", "monthly"),
    ("/tools/distribution-cost-calculator/", "0.7", "monthly"),
    ("/press-release-seo/", "0.8", "monthly"),
    ("/ai-press-release/", "0.8", "monthly"),
    ("/how-to-write-a-press-release/", "0.8", "monthly"),
    ("/tools/release-builder/", "0.8", "monthly"),
    ("/network/", "0.7", "weekly"), ("/newsrooms/", "0.6", "weekly"),
    ("/agents/", "0.6", "monthly"), ("/about/", "0.5", "yearly"),
    ("/contact/", "0.8", "yearly"), ("/faq/", "0.7", "monthly"),
    ("/editorial-standards/", "0.4", "yearly"), ("/corrections/", "0.4", "yearly"),
    ("/ai-disclosure/", "0.4", "yearly"), ("/terms/", "0.3", "yearly"),
    ("/privacy/", "0.3", "yearly"),
]


def sitemap(items, newsrooms=()):
    today = TODAY.isoformat()
    rows = ['  <url>\n    <loc>%s%s</loc>\n    <lastmod>%s</lastmod>\n'
            '    <changefreq>%s</changefreq>\n    <priority>%s</priority>\n  </url>'
            % (SITE, p, today, c, pr) for p, pr, c in STATIC_PAGES]
    for r in items:
        rows.append('  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n'
                    '    <changefreq>yearly</changefreq>\n    <priority>0.7</priority>\n  </url>'
                    % (r["url"], str(r.get("modified") or r["date"])))
        rows.append('  <url>\n    <loc>%sreceipt/</loc>\n    <lastmod>%s</lastmod>\n'
                    '    <changefreq>yearly</changefreq>\n    <priority>0.3</priority>\n  </url>'
                    % (r["url"], str(r.get("modified") or r["date"])))
    for cs in newsrooms:
        rows.append('  <url>\n    <loc>%s/newsrooms/%s/</loc>\n    <lastmod>%s</lastmod>\n'
                    '    <changefreq>weekly</changefreq>\n    <priority>0.5</priority>\n  </url>'
                    % (SITE, cs, today))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(rows) + "\n</urlset>\n")


def releases_index(items):
    cards = "\n".join(
        '        <a class="card card-link" href="{u}">'
        '<div class="card-kicker">{d} \u00b7 {c}</div>'
        '<h3 style="font-size:1.08rem">{t}</h3><p style="font-size:.93rem">{s}</p></a>'.format(
            u=r["url"], d=long_date(r["date"]), c=esc(r["company"]),
            t=esc(r["title"]), s=esc(r["summary"]))
        for r in items[:60])
    return """<!DOCTYPE html>
<html lang="en-US"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="google-site-verification" content="{gsc}">
<title>Published Press Releases | Distribute Press Releases</title>
<meta name="description" content="Every press release published through Distribute Press Releases, newest first. Every item is labeled as a paid or affiliated placement.">
<link rel="canonical" href="{s}/releases/">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<meta property="og:type" content="website">
<meta property="og:title" content="Published Press Releases">
<meta property="og:description" content="Every press release published through Distribute Press Releases, newest first.">
<meta property="og:url" content="{s}/releases/">
<meta property="og:image" content="{s}/images/distribute-press-releases-share-card.png">
<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image">
<meta name="author" content="Distribute Press Releases">
<meta name="theme-color" content="#08214A">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="manifest" href="/site.webmanifest">
<link rel="alternate" type="application/json" title="Machine-readable service description" href="{s}/api/service.json">
<link rel="sitemap" type="application/xml" href="{s}/sitemap.xml">
<link rel="alternate" type="application/rss+xml" title="Distribute Press Releases" href="{s}/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&display=swap">
<link rel="stylesheet" href="/assets/dpr.css">
<script type="application/ld+json">
{graph}
</script>
</head><body>
<header class="site-head"><div class="wrap head-in">
  <a class="brand" href="/"><img src="/images/distribute-press-releases-mark.png" alt="" width="52" height="38"><span>Distribute Press Releases</span></a>
  <button class="burger" type="button" aria-label="Menu" aria-expanded="false" aria-controls="nav"><span></span><span></span><span></span></button>
  <nav class="nav" id="nav" aria-label="Main">
    <a href="/press-release-distribution-service/">Distribution</a>
    <a href="/tools/">Free tools</a>
    <a href="/pricing/">Pricing</a>
    <a class="nav-cta" href="/contact/">Start a release</a>
  </nav>
</div></header>
<main id="main">
  <section class="hero"><div class="wrap-narrow">
    <h1>Published releases</h1>
    <p class="lede">Everything published through this service, newest first. Every item is labeled as a paid or affiliated placement, and publication here is not verification of any claim a release contains.</p>
  </div></section>
  <section style="padding-top:0"><div class="wrap">
      <h2 class="sr-only">All published releases</h2>
      <div class="grid g-3">
{cards}
      </div>
  </div></section>
</main>
<footer class="site-foot"><div class="wrap"><div class="foot-legal" style="border-top:0;margin-top:0">
  <span>&copy; 2026 Distribute Press Releases.</span>
  <a href="/editorial-standards/">Editorial standards</a><a href="/corrections/">Corrections</a><a href="/ai-disclosure/">AI disclosure</a>
</div></div><div class="stamp"><a href="https://eyetoad.com/" title="Built by Eye To Ad Media">&#10084;&#65039;</a></div></footer>
<script src="/assets/dpr.js" defer></script>
<script src="/assets/wire-bot.js" defer></script>
</body></html>
""".format(gsc=GSC, s=SITE, cards=cards or
           '<p style="color:var(--slate)">No releases published yet.</p>',
           graph=json.dumps({
               "@context": "https://schema.org",
               "@graph": [
                   {"@type": "CollectionPage",
                    "@id": SITE + "/releases/#page",
                    "url": SITE + "/releases/",
                    "name": "Published press releases",
                    "description": "Every press release published through Distribute Press Releases, newest first. Every item is labeled as a paid or affiliated placement.",
                    "inLanguage": "en-US",
                    "isPartOf": {"@id": SITE + "/#website"},
                    "dateModified": datetime.date.today().isoformat(),
                    "creditText": "Paid press releases",
                    "mainEntity": {
                        "@type": "ItemList",
                        "numberOfItems": len(items),
                        "itemListOrder": "https://schema.org/ItemListOrderDescending",
                        "itemListElement": [
                            {"@type": "ListItem", "position": i + 1,
                             "name": r["title"], "url": r["url"]}
                            for i, r in enumerate(items[:60])
                        ],
                    }},
                   {"@type": "BreadcrumbList", "itemListElement": [
                       {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
                       {"@type": "ListItem", "position": 2, "name": "Releases", "item": SITE + "/releases/"}]},
               ]}, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------- audio

def make_audio(r):
    """Narrate with piper if it is installed. Never fatal."""
    if NO_AUDIO:
        return False
    out_rel = "releases/%s/audio.mp3" % r["slug"]
    out_abs = os.path.join(ROOT, out_rel)
    if os.path.exists(out_abs):
        return True
    piper = shutil.which("piper")
    if not piper:
        log("piper not installed - skipping narration for", r["slug"])
        return False
    model = os.environ.get("PIPER_VOICE", "")
    if not model or not os.path.exists(model):
        log("PIPER_VOICE not set or missing - skipping narration for", r["slug"])
        return False
    text = "%s. %s, %s. %s %s" % (
        r["title"], r.get("city", ""), long_date(r["date"]),
        re.sub(r"\s+", " ", re.sub(r"[#>*\[\]()]|https?://\S+", " ", r["body"]))[:4000],
        "This has been a %s from %s, published by Distribute Press Releases "
        "and read by a synthetic voice." % ("press release" if r.get("affiliated") else "paid press release",
                                            r["company"]))
    if DRY:
        log("would narrate", r["slug"], "(%d chars)" % len(text))
        return False
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    wav = out_abs.replace(".mp3", ".wav")
    try:
        subprocess.run([piper, "--model", model, "--output_file", wav],
                       input=text.encode("utf-8"), check=True, timeout=300)
        ff = shutil.which("ffmpeg")
        if ff:
            subprocess.run([ff, "-y", "-loglevel", "error", "-i", wav,
                            "-codec:a", "libmp3lame", "-b:a", "96k", out_abs],
                           check=True, timeout=300)
            os.remove(wav)
        else:
            log("ffmpeg missing - keeping wav for", r["slug"])
            return False
        log("narrated", r["slug"])
        return True
    except Exception as e:
        log("narration failed for %s: %s" % (r["slug"], e))
        for f in (wav, out_abs):
            if os.path.exists(f) and os.path.getsize(f) == 0:
                os.remove(f)
        return False


# ---------------------------------------------------------------- network

def indexnow_key():
    """The INDEXNOW_KEY secret wins; otherwise the key file committed at the root.
    The key is public by design: engines fetch the file to confirm the domain."""
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    if key:
        return key
    for f in sorted(glob.glob(os.path.join(ROOT, "*.txt"))):
        name = os.path.basename(f)[:-4]
        if re.fullmatch(r"[0-9a-f]{32,128}", name):
            if open(f, encoding="utf-8").read().strip() == name:
                return name
    return ""


def indexnow(urls):
    key = indexnow_key()
    if NO_PING or DRY or not key or not urls:
        return "skipped", ""
    import urllib.request
    payload = json.dumps({
        "host": "distributepressreleases.com",
        "key": key,
        "keyLocation": "%s/%s.txt" % (SITE, key),
        "urlList": urls[:10000],
    }).encode()
    try:
        req = urllib.request.Request("https://api.indexnow.org/IndexNow", data=payload,
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            log("IndexNow HTTP", resp.status)
            return ("accepted (HTTP %d)" % resp.status), "https://www.indexnow.org/"
    except Exception as e:
        log("IndexNow failed:", e)
        return ("not accepted (%s)" % e), ""


def post_mastodon(r):
    tok = os.environ.get("MASTODON_TOKEN", "")
    host = os.environ.get("MASTODON_HOST", "")
    if NO_PING or DRY or not tok or not host:
        return "skipped", ""
    import urllib.request, urllib.parse
    status = "%s\n\n%s\n\n%s" % (r["title"], r["summary"], r["url"])
    data = urllib.parse.urlencode({"status": status[:490]}).encode()
    try:
        req = urllib.request.Request("https://%s/api/v1/statuses" % host, data=data,
                                     headers={"Authorization": "Bearer " + tok})
        with urllib.request.urlopen(req, timeout=30) as resp:
            j = json.loads(resp.read().decode())
            return "posted", j.get("url", "")
    except Exception as e:
        log("Mastodon failed:", e)
        return ("not posted (%s)" % e), ""


def post_bluesky(r):
    handle = os.environ.get("BLUESKY_HANDLE", "")
    pw = os.environ.get("BLUESKY_APP_PASSWORD", "")
    if NO_PING or DRY or not handle or not pw:
        return "skipped", ""
    import urllib.request
    api = "https://bsky.social/xrpc/"

    def call(path, body, token=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        req = urllib.request.Request(api + path, data=json.dumps(body).encode(), headers=h)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    try:
        s = call("com.atproto.server.createSession",
                 {"identifier": handle, "password": pw})
        text = "%s\n\n%s" % (r["title"][:200], r["url"])
        rec = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.datetime.now(datetime.timezone.utc)
                                  .strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "langs": ["en"],
            "embed": {"$type": "app.bsky.embed.external",
                      "external": {"uri": r["url"], "title": r["title"][:280],
                                   "description": r["summary"][:280]}},
        }
        out = call("com.atproto.repo.createRecord",
                   {"repo": s["did"], "collection": "app.bsky.feed.post", "record": rec},
                   s["accessJwt"])
        rkey = out.get("uri", "").split("/")[-1]
        return "posted", "https://bsky.app/profile/%s/post/%s" % (handle, rkey)
    except Exception as e:
        log("Bluesky failed:", e)
        return ("not posted (%s)" % e), ""


# ---------------------------------------------------------------- routing

_NET = None


def network():
    global _NET
    if _NET is None:
        try:
            _NET = json.load(open(NETWORK, encoding="utf-8"))
        except Exception as e:
            log("no usable config/network.json (%s) - routing off" % e)
            _NET = {"sites": [], "news": None}
    return _NET


def _split(v):
    if isinstance(v, list):
        return [slugify(x) for x in v if str(x).strip()]
    return [slugify(x) for x in str(v or "").split(",") if x.strip()]


def route(r):
    """Score the release against every network site. Returns site ids, best first.
    The filter: industry match, region match, and keyword hits in the title,
    summary, body and any `keywords:` front matter."""
    net = network()
    sc = net.get("scoring", {})
    override = _split(r.get("network"))
    if override == ["none"]:
        return []
    ids = {s["id"]: s for s in net.get("sites", [])}
    if override:
        return [i for i in override if i in ids]
    text = " ".join([r["title"], r["summary"], r["body"], str(r.get("keywords") or "")]).lower()
    region = r["region"]
    city = slugify(r.get("city") or "")
    scored = []
    for s in net.get("sites", []):
        regions = s.get("regions") or []
        in_region = region in regions or city in regions
        if s.get("require_region") and not in_region:
            continue
        score = 0
        if r["industry"] in (s.get("industries") or []):
            score += sc.get("industry", 3)
        if in_region and regions:
            score += sc.get("region", 2)
        hits = sum(1 for k in (s.get("keywords") or [])
                   if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(k.lower()), text))
        score += min(hits, sc.get("keyword_cap", 3)) * sc.get("keyword", 1)
        if score >= s.get("min_score", 3):
            scored.append((score, s["id"]))
    scored.sort(key=lambda x: -x[0])
    return [i for _, i in scored[: net.get("max_network_sites_per_release", 3)]]


def placements(r):
    """Destinations that are real today: the news property plus live network sites."""
    net = network()
    out = []
    news = net.get("news")
    if news and news.get("live") and str(r.get("syndicate", "yes")).lower() not in ("no", "false"):
        out.append({"id": news["id"], "name": news["name"], "kind": "news",
                    "link": news["release_url"].format(slug=r["slug"])})
    ids = {s["id"]: s for s in net.get("sites", [])}
    for i in r.get("routes", []):
        s = ids[i]
        if s.get("live"):
            out.append({"id": i, "name": s["name"], "kind": "network", "link": s["landing"]})
    return out


def body_html(r):
    """Release body as clean HTML for syndication partners. Links stay sponsored."""
    out = []
    for i, (kind, text) in enumerate(md_paragraphs(r["body"])):
        if i == 0 and kind == "p":
            dl = ("%s, %s, " % (r.get("city", "").upper(), r.get("state", ""))) if r.get("city") else ""
            out.append("<p><strong>%s%s</strong> — %s</p>" % (esc(dl), long_date(r["date"]), inline_md(text)))
        elif kind == "ul":
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline_md(t) for t in text))
        elif kind == "h2":
            out.append("<h2>%s</h2>" % esc(text))
        elif kind == "quote":
            out.append("<blockquote>%s</blockquote>" % inline_md(text))
        else:
            out.append("<p>%s</p>" % inline_md(text))
    return "\n".join(out)


def syndication_feed(site, items):
    return json.dumps({
        "version": "https://jsonfeed.org/version/1.1",
        "title": "%s — releases routed to %s" % (NAME, site["name"]),
        "home_page_url": SITE + "/network/",
        "feed_url": "%s/syndication/%s.json" % (SITE, site["id"]),
        "description": "Press releases the %s routing engine matched to %s. %s" % (NAME, site["name"], site.get("beat", "")),
        "language": "en-US",
        "_dpr": {"site": site["id"], "rules": "https://distributepressreleases.com/config/network.json",
                 "terms": "Republish with rel=canonical to item.url, keep the label and disclosure, "
                          "keep links rel=sponsored."},
        "items": [{
            "id": r["url"],
            "url": r["url"],
            "title": r["title"],
            "summary": r["summary"],
            "content_html": body_html(r),
            "date_published": "%sT12:00:00Z" % r["date"],
            "authors": [{"name": r["company"], **({"url": r["company_url"]} if r.get("company_url") else {})}],
            "tags": [r["industry"], r["region"]],
            **({"image": r["image"]} if r.get("image") else {}),
            "_dpr": {
                "slug": r["slug"], "label": label(r), "disclosure": disclosure(r),
                "affiliated": r.get("affiliated") or None,
                "company": r["company"], "company_url": r.get("company_url") or None,
                "city": r.get("city") or None, "state": r.get("state") or None,
                "industry": r["industry"], "region": r["region"],
                "receipt": r["url"] + "receipt/", "newsroom": "%s/newsrooms/%s/" % (SITE, r["company_slug"]),
                "contact": {k[8:]: r[k] for k in ("contact_name", "contact_email", "contact_phone") if r.get(k)},
            },
        } for r in items],
    }, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- shared chrome

HEAD = """<!DOCTYPE html>
<html lang="en-US">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="google-site-verification" content="{gsc}">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site}/images/distribute-press-releases-share-card.png">
<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#08214A">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/images/distribute-press-releases-apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
{alt}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&display=swap">
<link rel="stylesheet" href="/assets/dpr.css">
<script type="application/ld+json">
{graph}
</script>
</head>
<body>
<a class="sr-only" href="#main">Skip to content</a>
<header class="site-head"><div class="wrap head-in">
  <a class="brand" href="/"><img src="/images/distribute-press-releases-mark.png" alt="" width="52" height="38"><span>Distribute Press Releases</span></a>
  <button class="burger" type="button" aria-label="Menu" aria-expanded="false" aria-controls="nav"><span></span><span></span><span></span></button>
  <nav class="nav" id="nav" aria-label="Main">
    <a href="/releases/">Releases</a>
    <a href="/press-release-distribution-service/">Distribution</a>
    <a href="/tools/">Free tools</a>
    <a href="/pricing/">Pricing</a>
    <a class="nav-cta" href="/contact/">Start a release</a>
  </nav>
</div></header>
<main id="main">
"""

FOOT = """</main>
<footer class="site-foot"><div class="wrap"><div class="foot-legal" style="border-top:0;margin-top:0">
  <span>&copy; 2026 Distribute Press Releases. Powered by <a href="https://eyetoad.com/">Eye To Ad Media</a>.</span>
  <a href="/editorial-standards/">Editorial standards</a><a href="/corrections/">Corrections</a><a href="/ai-disclosure/">AI disclosure</a>
  <a href="/network/">Network</a><a href="/newsrooms/">Newsroom directory</a>
</div></div><div class="stamp"><a href="https://eyetoad.com/" title="Built by Eye To Ad Media">&#10084;&#65039;</a></div></footer>
<script src="/assets/dpr.js" defer></script>
</body></html>
"""


def page(path, title, desc, graph, body, alt=""):
    url = SITE + path
    return HEAD.format(gsc=GSC, title=esc(title), desc=esc(desc), url=url, site=SITE, alt=alt,
                       graph=json.dumps({"@context": "https://schema.org", "@graph": graph},
                                        indent=2, ensure_ascii=False)) + body + FOOT


def crumbs(*pairs):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + p}
        for i, (n, p) in enumerate((("Home", "/"),) + pairs)]}


def card(r):
    return ('        <a class="card card-link" href="{u}"><div class="card-kicker">{d} · {lab}</div>'
            '<h3 style="font-size:1.08rem">{t}</h3><p style="font-size:.93rem">{s}</p></a>').format(
        u=r["url"], d=long_date(r["date"]), lab=esc(label(r)), t=esc(r["title"]), s=esc(r["summary"]))


# ---------------------------------------------------------------- newsroom directory

def newsroom_page(items):
    r0 = items[0]
    path = "/newsrooms/%s/" % r0["company_slug"]
    loc = ", ".join(x for x in (r0.get("city"), r0.get("state")) if x)
    title = "%s Newsroom" % r0["company"]
    if len(title) < 46:
        title += " | Press Releases"
    desc = ("Press releases from %s, newest first, with RSS and JSON feeds and an embed "
            "for the company's own website." % r0["company"])[:158]
    org = {"@type": "Organization", "@id": SITE + path + "#org", "name": r0["company"]}
    if r0.get("company_url"):
        org.update({"url": r0["company_url"], "sameAs": [r0["company_url"]]})
    if loc:
        org["address"] = {"@type": "PostalAddress", "addressLocality": r0.get("city", ""),
                          "addressRegion": r0.get("state", ""), "addressCountry": "US"}
    graph = [
        {"@type": "CollectionPage", "@id": SITE + path + "#page", "url": SITE + path, "name": title,
         "description": desc, "inLanguage": "en-US", "about": {"@id": org["@id"]},
         "mainEntity": {"@type": "ItemList", "numberOfItems": len(items), "itemListElement": [
             {"@type": "ListItem", "position": i + 1, "name": r["title"], "url": r["url"]}
             for i, r in enumerate(items[:50])]}},
        org, crumbs(("Newsroom directory", "/newsrooms/"), (r0["company"], path)),
    ]
    site_line = ('<p style="margin:0"><a href="%s" rel="sponsored noopener">%s</a></p>'
                 % (esc(r0["company_url"]), esc(re.sub(r"^https?://(www\.)?", "", r0["company_url"]).rstrip("/")))
                 if r0.get("company_url") else "")
    body = """  <section class="hero"><div class="wrap-narrow">
    <span class="eyebrow">Company newsroom</span>
    <h1>{name}</h1>
    <p class="lede">{n} press release{pl} published{loc}. The list updates itself whenever a new one goes out.</p>
    {site_line}
  </div></section>
  <section style="padding-top:0"><div class="wrap">
    <h2 class="sr-only">Releases from {name}</h2>
    <div class="grid g-3">
{cards}
    </div>
  </div></section>
  <section style="padding-top:0"><div class="wrap-narrow">
    <h2 style="font-size:1.15rem">Feeds and embed</h2>
    <p><a href="{s}/newsrooms/{cs}/feed.xml">RSS feed</a> &middot; <a href="{s}/newsrooms/{cs}/feed.json">JSON Feed</a></p>
    <p>Put this list on your own site with one line. It updates when you publish and passes no ranking credit either way.</p>
    <pre class="mono-out" style="white-space:pre-wrap">&lt;div id="dpr-newsroom" data-company="{cs}"&gt;&lt;/div&gt;
&lt;script async src="{s}/assets/newsroom.js"&gt;&lt;/script&gt;</pre>
    <p style="font-size:.9rem;color:var(--slate)">Releases are labeled paid or affiliated on their own pages. Publication is not verification. <a href="/newsrooms/">Browse every company newsroom</a>.</p>
  </div></section>
""".format(name=esc(r0["company"]), n=len(items), pl="" if len(items) == 1 else "s",
           loc=(" by this " + esc(loc) + " company") if loc else "", site_line=site_line,
           cards="\n".join(card(r) for r in items[:60]), s=SITE, cs=r0["company_slug"])
    alt = ('<link rel="alternate" type="application/rss+xml" title="%s" href="%s/newsrooms/%s/feed.xml">\n'
           % (esc(r0["company"]), SITE, r0["company_slug"]))
    return page(path, title, desc, graph, body, alt)


def newsrooms_index(groups):
    path = "/newsrooms/"
    by_state = {}
    for items in groups:
        st = items[0].get("state") or "National"
        by_state.setdefault(st, []).append(items)
    blocks = []
    for st in sorted(by_state, key=lambda x: (x == "National", x)):
        rows = "\n".join(
            '        <a class="card card-link" href="/newsrooms/{cs}/"><div class="card-kicker">{ind} · {city}</div>'
            '<h3 style="font-size:1.05rem">{n}</h3><p style="font-size:.9rem">{k} release{pl} · latest {d}</p></a>'.format(
                cs=g[0]["company_slug"], ind=esc(g[0]["industry"].replace("-", " ")),
                city=esc(g[0].get("city") or "United States"), n=esc(g[0]["company"]), k=len(g),
                pl="" if len(g) == 1 else "s", d=long_date(g[0]["date"]))
            for g in sorted(by_state[st], key=lambda g: g[0]["company"].lower()))
        blocks.append('    <h2 style="font-size:1.2rem;margin-top:2rem">%s</h2>\n    <div class="grid g-3">\n%s\n    </div>'
                      % (esc(st), rows))
    desc = ("A directory of US companies with a press newsroom on Distribute Press Releases, grouped by state, "
            "each with its full release history, feeds and an embed.")
    graph = [{"@type": "CollectionPage", "@id": SITE + path + "#page", "url": SITE + path,
              "name": "Company newsroom directory", "description": desc, "inLanguage": "en-US",
              "mainEntity": {"@type": "ItemList", "numberOfItems": len(groups), "itemListElement": [
                  {"@type": "ListItem", "position": i + 1, "name": g[0]["company"],
                   "url": "%s/newsrooms/%s/" % (SITE, g[0]["company_slug"])} for i, g in enumerate(groups)]}},
             crumbs(("Newsroom directory", path))]
    body = """  <section class="hero"><div class="wrap-narrow">
    <span class="eyebrow">Directory</span>
    <h1>Company newsroom directory</h1>
    <p class="lede">Every company that has published here gets a permanent newsroom: its release history, feeds, and an embed for its own site. Listed by state.</p>
    <p><a class="btn btn-primary" href="/contact/">Get your company listed</a> <a class="btn btn-ghost" href="/newsroom/">How newsrooms work</a></p>
  </div></section>
  <section style="padding-top:0"><div class="wrap">
{blocks}
  </div></section>
""".format(blocks="\n".join(blocks) or '    <p>No newsrooms yet.</p>')
    return page(path, "Company Newsroom Directory | Distribute Press Releases", desc, graph, body)


def network_page(releases):
    net = network()
    path = "/network/"
    news = net.get("news")
    sites = [s for s in net.get("sites", []) if s.get("live")]
    recent = {}
    for r in releases:
        for i in r.get("routes", []):
            recent.setdefault(i, []).append(r)
    rows = []
    if news:
        rows.append('<tr><td><a href="{u}" rel="noopener"><strong>{n}</strong></a></td><td>News property</td><td>{b}</td><td>{k}</td></tr>'.format(
            u=esc(news["landing"]), n=esc(news["name"]), b=esc(news["beat"]), k=len(releases)))
    for s in sites:
        rows.append('<tr><td><a href="{u}" rel="noopener"><strong>{n}</strong></a></td><td>Network site</td><td>{b}</td><td>{k}</td></tr>'.format(
            u=esc(s["url"]), n=esc(s["name"]), b=esc(s["beat"]), k=len(recent.get(s["id"], []))))
    desc = ("Where a release can land: our news site, plus the local network sites a public "
            "filter matches by industry, region and topic.")
    graph = [{"@type": "WebPage", "@id": SITE + path + "#page", "url": SITE + path,
              "name": "Our publishing network", "description": desc, "inLanguage": "en-US"},
             crumbs(("Network", path))]
    body = """  <section class="hero"><div class="wrap-narrow">
    <span class="eyebrow">Network</span>
    <h1>Where your release can land</h1>
    <p class="lede">Every release is republished on our news property. Then a routing filter reads its industry, region and wording and places it on the network sites where it actually fits &mdash; a Denver restaurant opening goes to the restaurant site, a camping gear launch goes to the camping site, a Honolulu hotel goes to the Hawaii site.</p>
  </div></section>
  <section style="padding-top:0"><div class="wrap">
    <div class="table-wrap"><table>
      <thead><tr><th>Site</th><th>Role</th><th>What it takes</th><th>Releases carried</th></tr></thead>
      <tbody>
      {rows}
      </tbody>
      <caption>These sites share ownership with Distribute Press Releases; all are operated by or affiliated with Eye To Ad Media. A release only appears where the filter matches it, and every placement keeps the paid or affiliated label and points back to the original as canonical.</caption>
    </table></div>
  </div></section>
  <section style="padding-top:0"><div class="wrap-narrow">
    <h2 style="font-size:1.2rem">How the filter decides</h2>
    <p>Each site has a list of industries, regions and topic words. A release scores points for a matching industry, a matching region and topic words in its text; local sites also require the release to be local. The best matches win, up to three network sites per release. The rules are public: <a href="/config/network.json">network.json</a>.</p>
    <p>Publishers outside our network can take the same filtered feeds for free: <a href="/feeds/">industry and region feeds</a>.</p>
    <p><a class="btn btn-primary" href="/tools/release-builder/">Build your release and preview its routing</a></p>
  </div></section>
""".format(rows="\n      ".join(rows))
    return page(path, "Press Release Network | Distribute Press Releases", desc, graph, body)


# ---------------------------------------------------------------- ledger

def load_ledger():
    try:
        return json.load(open(LEDGER, encoding="utf-8"))
    except Exception:
        return {}


def save_ledger(ledger):
    write("data/announced.json", json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


SOCIAL_OFF = "not posted — account not connected yet"


def receipt_rows(r, entry):
    pub = entry.get("published", TODAY.isoformat())

    def ann(key, fallback):
        v = entry.get(key)
        return (v[0], v[1]) if v else (fallback, "")
    idx = ann("indexnow", "queued — sent once the page is live")
    bs = ann("bluesky", "queued")
    md = ann("mastodon", "queued")
    rows = [
        ("Canonical release page", "distributepressreleases.com", "published " + pub, r["url"]),
        ("Markdown mirror", "plain text for machines", "published " + pub, r["url"] + "index.md"),
        ("Claims file", "attributed facts as JSON", "published " + pub, r["url"] + "claims.json"),
        ("Company newsroom", r["company"], "listed " + pub, "%s/newsrooms/%s/" % (SITE, r["company_slug"])),
        ("RSS 2.0", "site-wide feed", "included " + pub, SITE + "/feed.xml"),
        ("Atom 1.0", "site-wide feed", "included " + pub, SITE + "/atom.xml"),
        ("JSON Feed 1.1", "site-wide feed", "included " + pub, SITE + "/feed.json"),
        ("Media RSS", "feed-ingesting publishers", "included " + pub, SITE + "/media.xml"),
        ("Industry feed", r["industry"].replace("-", " "), "included " + pub,
         "%s/feeds/industry/%s.xml" % (SITE, r["industry"])),
        ("Region feed", r["region"].replace("-", " "), "included " + pub,
         "%s/feeds/region/%s.xml" % (SITE, r["region"])),
        ("Company feed", r["company"], "included " + pub,
         "%s/newsrooms/%s/feed.xml" % (SITE, r["company_slug"])),
        ("News sitemap", "48-hour window", "included " + pub, SITE + "/news-sitemap.xml"),
    ]
    for d in placements(r):
        if d["kind"] == "news":
            rows.append(("News syndication", d["name"], "routed " + pub + "; republished on its hourly sync", d["link"]))
        else:
            rows.append(("Network placement", d["name"], "routed " + pub + "; shown in its business-news module", d["link"]))
    rows += [
        ("IndexNow", "Bing, Yandex, Naver, Seznam", idx[0], idx[1]),
        ("Podcast RSS", "listening apps that subscribe to our feed",
         ("episode published " + pub) if r.get("has_audio") else "no audio for this release",
         SITE + "/podcast.xml" if r.get("has_audio") else ""),
        ("Bluesky", "open social protocol", bs[0], bs[1]),
        ("Mastodon", "open social protocol", md[0], md[1]),
    ]
    return rows


def wait_live(url, minutes=10):
    import urllib.request, time
    end = time.time() + minutes * 60
    while time.time() < end:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "dpr-publish"}),
                                        timeout=20) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(20)
    return False


def announce(releases, ledger):
    """Push and post anything not yet announced. Social posts are only retried for a
    week, so connecting an account later does not flood it with old releases."""
    todo = [r for r in releases if "indexnow" not in ledger.get(r["slug"], {})]
    retry = []
    for r in releases:
        e = ledger.get(r["slug"], {})
        try:
            fresh = (TODAY - datetime.date.fromisoformat(e.get("published", ""))).days <= 7
        except ValueError:
            fresh = False
        if fresh and any(e.get(k, [SOCIAL_OFF])[0] in (SOCIAL_OFF, "queued") for k in ("bluesky", "mastodon")):
            retry.append(r)
    if not todo and not retry:
        log("nothing to announce")
        return
    if todo and not wait_live(todo[0]["url"]):
        log("release page not live yet - announcements left queued for the next run")
        return
    if todo:
        urls = []
        for r in todo:
            urls += [r["url"], r["url"] + "receipt/", "%s/newsrooms/%s/" % (SITE, r["company_slug"])]
        urls += [SITE + "/releases/", SITE + "/newsrooms/"]
        state, link = indexnow(urls)
        if state == "skipped":
            state = "not sent — no IndexNow key configured"
        for r in todo:
            ledger.setdefault(r["slug"], {})["indexnow"] = [state + " " + TODAY.isoformat(), link]
    for r in {x["slug"]: x for x in todo + retry}.values():
        e = ledger.setdefault(r["slug"], {})
        for key, fn in (("bluesky", post_bluesky), ("mastodon", post_mastodon)):
            if key in e and e[key][0] not in (SOCIAL_OFF, "queued"):
                continue
            state, link = fn(r)
            e[key] = [SOCIAL_OFF if state == "skipped" else state + " " + TODAY.isoformat(), link]


# ---------------------------------------------------------------- main

def main():
    releases = load_releases()
    log("found %d release file(s)" % len(releases))
    ledger = load_ledger()

    for r in releases:
        r["has_audio"] = os.path.exists(os.path.join(ROOT, "releases", r["slug"], "audio.mp3")) \
            or make_audio(r)
        r["routes"] = route(r)
        ledger.setdefault(r["slug"], {}).setdefault("published", TODAY.isoformat())
        log("route %s -> %s" % (r["slug"], ", ".join(d["name"] for d in placements(r)) or "nowhere"))

    # per-release artifacts
    for i, r in enumerate(releases):
        prev_url = releases[i + 1]["url"] if i + 1 < len(releases) else None
        next_url = releases[i - 1]["url"] if i > 0 else None
        base = "releases/%s/" % r["slug"]
        write(base + "index.html", release_html(r, (prev_url, next_url)))
        write(base + "index.md", release_markdown(r))
        write(base + "claims.json", release_claims(r))

    # feeds and indexes
    write("releases/index.html", releases_index(releases))
    write("feed.xml", rss(releases[:50], SITE + "/feed.xml"))
    write("media.xml", rss(releases[:50], SITE + "/media.xml"))
    write("atom.xml", atom(releases[:50]))
    write("feed.json", jsonfeed(releases[:50]))
    write("podcast.xml", podcast(releases[:100]))
    write("news-sitemap.xml", news_sitemap(releases))

    by = {}
    for r in releases:
        by.setdefault(("industry", r["industry"]), []).append(r)
        by.setdefault(("region", r["region"]), []).append(r)
        by.setdefault(("newsroom", r["company_slug"]), []).append(r)
    newsroom_groups = []
    for (kind, slug), items in by.items():
        if kind == "newsroom":
            newsroom_groups.append(items)
            write("newsrooms/%s/index.html" % slug, newsroom_page(items))
            write("newsrooms/%s/feed.json" % slug,
                  jsonfeed(items[:50], "%s/newsrooms/%s/feed.json" % (SITE, slug)))
            write("newsrooms/%s/feed.xml" % slug,
                  rss(items[:50], "%s/newsrooms/%s/feed.xml" % (SITE, slug),
                      " — " + items[0]["company"]))
        else:
            write("feeds/%s/%s.xml" % (kind, slug),
                  rss(items[:50], "%s/feeds/%s/%s.xml" % (SITE, kind, slug),
                      " — " + slug.replace("-", " ")))
    write("newsrooms/index.html", newsrooms_index(newsroom_groups))
    write("network/index.html", network_page(releases))
    log("wrote %d filtered feed group(s)" % len(by))

    # syndication feeds, one per destination, read by the news property's sync
    # job and by assets/network.js on each network site
    net = network()
    dests = ([net["news"]] if net.get("news") else []) + net.get("sites", [])
    for site in dests:
        if site is net.get("news"):
            items = [r for r in releases if any(d["kind"] == "news" for d in placements(r))]
        else:
            items = [r for r in releases if site["id"] in r["routes"]]
        write("syndication/%s.json" % site["id"], syndication_feed(site, items[:30]))
    write("syndication/index.json", json.dumps({
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feeds": {s["id"]: "%s/syndication/%s.json" % (SITE, s["id"]) for s in dests},
        "routes": {r["slug"]: [d["id"] for d in placements(r)] for r in releases},
    }, indent=2) + "\n")

    if ANNOUNCE and not DRY:
        announce(releases, ledger)

    for r in releases:
        write("releases/%s/receipt/index.html" % r["slug"],
              receipt_html(r, receipt_rows(r, ledger.get(r["slug"], {}))))
    if not DRY:
        save_ledger(ledger)
    write("sitemap.xml", sitemap(releases, [g[0]["company_slug"] for g in newsroom_groups]))
    log("done. %d release(s)." % len(releases))


if __name__ == "__main__":
    main()
