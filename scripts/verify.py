# -*- coding: utf-8 -*-
import os, re, json, sys, html
from html.parser import HTMLParser

BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", ".github", "content", "scripts", "node_modules"}
VOID = {"area","base","br","col","embed","hr","img","input","link","meta","param",
        "source","track","wbr"}
errors, warns = [], []


class Bal(HTMLParser):
    def __init__(self, f):
        super().__init__(convert_charrefs=False)
        self.f = f; self.stack = []; self.in_script = False
    def handle_starttag(self, tag, attrs):
        if tag in VOID: return
        if tag == "script": self.in_script = True
        self.stack.append((tag, self.getpos()))
    def handle_startendtag(self, tag, attrs): pass
    def handle_endtag(self, tag):
        if tag in VOID: return
        if tag == "script": self.in_script = False
        if not self.stack:
            errors.append("%s: stray </%s>" % (self.f, tag)); return
        if self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            for i in range(len(self.stack)-1, -1, -1):
                if self.stack[i][0] == tag:
                    unclosed = [t for t, _ in self.stack[i+1:]]
                    errors.append("%s: </%s> closes but %s left open (line %d)"
                                  % (self.f, tag, unclosed, self.getpos()[0]))
                    del self.stack[i:]
                    return
            errors.append("%s: </%s> has no opener (line %d)" % (self.f, tag, self.getpos()[0]))


def strip_scripts(s):
    return re.sub(r"<script\b[^>]*>.*?</script>", "", s, flags=re.S | re.I)


def check(path, rel):
    src = open(path, encoding="utf-8").read()

    # --- tag balance (scripts removed so JS < > doesn't confuse the parser)
    body = strip_scripts(src)
    p = Bal(rel); p.feed(body); p.close()
    if p.stack:
        errors.append("%s: unclosed %s" % (rel, [(t, l[0]) for t, l in p.stack]))

    # --- comments balanced
    if src.count("<!--") != src.count("-->"):
        errors.append("%s: unbalanced HTML comments (%d open, %d close)"
                      % (rel, src.count("<!--"), src.count("-->")))

    # --- required head bits
    for needle, label in [
        ('name="google-site-verification"', "GSC verification tag"),
        ('rel="canonical"', "canonical"),
        ('name="description"', "meta description"),
        ("/assets/dpr.css", "stylesheet"),
        ("/favicon.ico", "favicon"),
    ]:
        if needle not in src:
            errors.append("%s: missing %s" % (rel, label))

    # --- title / description length
    t = re.search(r"<title>(.*?)</title>", src, re.S)
    if not t:
        errors.append("%s: no <title>" % rel)
    elif len(t.group(1)) > 62:
        warns.append("%s: title %d chars (%s)" % (rel, len(t.group(1)), t.group(1)[:70]))
    d = re.search(r'<meta name="description" content="(.*?)">', src, re.S)
    if d:
        dl = len(html.unescape(d.group(1)))
        if dl > 165 or dl < 70:
            warns.append("%s: description %d chars" % (rel, dl))

    # --- single h1
    h1 = re.findall(r"<h1[ >]", body)
    if len(h1) != 1:
        errors.append("%s: %d h1 tags" % (rel, len(h1)))

    # --- JSON-LD valid
    faq_schema = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', src, re.S):
        raw = m.group(1)
        try:
            data = json.loads(raw)
        except Exception as e:
            errors.append("%s: invalid JSON-LD (%s)" % (rel, e)); continue
        for node in data.get("@graph", []) if isinstance(data, dict) else []:
            if node.get("@type") == "FAQPage":
                for q in node.get("mainEntity", []):
                    faq_schema.append((q["name"], q["acceptedAnswer"]["text"]))
            if node.get("@type") == "WebPage" and "speakable" in node:
                sp = node["speakable"]
                if sp.get("@type") != "SpeakableSpecification":
                    errors.append("%s: bad speakable" % rel)

    # --- FAQ visible/schema parity
    vis = []
    for m in re.finditer(r"<details>\s*<summary>(.*?)</summary>\s*<div><p>(.*?)</p></div>",
                         body, re.S):
        vis.append((html.unescape(m.group(1)).strip(),
                    html.unescape(m.group(2)).strip()))
    if faq_schema or vis:
        if len(faq_schema) != len(vis):
            errors.append("%s: FAQ parity count %d schema vs %d visible"
                          % (rel, len(faq_schema), len(vis)))
        else:
            for i, (sq, sa) in enumerate(faq_schema):
                vq, va = vis[i]
                if sq.strip() != vq.strip():
                    errors.append("%s: FAQ Q%d mismatch\n   schema: %s\n   visible: %s"
                                  % (rel, i + 1, sq[:80], vq[:80]))
                if sa.strip() != va.strip():
                    errors.append("%s: FAQ A%d mismatch\n   schema: %s\n   visible: %s"
                                  % (rel, i + 1, sa[:90], va[:90]))

    # --- collect internal links
    links = set()
    for m in re.finditer(r'href="(/[^"#?]*)', body):
        links.add(m.group(1))
    return links


def main():
    pages, all_links = [], {}
    for root, dirs, files in os.walk(BUILD):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(".html"):
                full = os.path.join(root, fn)
                rel = "/" + os.path.relpath(full, BUILD).replace("\\", "/")
                pages.append(rel)
                all_links[rel] = check(full, rel)

    # --- link targets exist
    existing = set()
    for rel in pages:
        if rel.endswith("/index.html"):
            existing.add(rel[: -len("index.html")])
        existing.add(rel)
    for root, dirs, files in os.walk(BUILD):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            full = os.path.join(root, fn)
            existing.add("/" + os.path.relpath(full, BUILD).replace("\\", "/"))

    for src, links in all_links.items():
        for l in links:
            if l in existing: continue
            if l.rstrip("/") + "/" in existing: continue
            if l + "/" in existing: continue
            errors.append("%s: broken internal link -> %s" % (src, l))

    # --- uppercase / .html in URLs
    for src, links in all_links.items():
        for l in links:
            if any(c.isupper() for c in l):
                errors.append("%s: uppercase in URL %s" % (src, l))
            if l.endswith(".html") and l != "/404.html":
                errors.append("%s: .html extension in URL %s" % (src, l))

    # --- orphan check
    linked = set()
    for links in all_links.values():
        linked |= links
    for rel in pages:
        if rel == "/404.html": continue
        pretty = rel[: -len("index.html")] if rel.endswith("/index.html") else rel
        if pretty.startswith("/releases/") or pretty.startswith("/newsrooms/"): continue
        if pretty != "/" and pretty not in linked:
            warns.append("orphan (not linked from anywhere): %s" % pretty)

    print("pages checked:", len(pages))
    if errors:
        print("\n=== ERRORS (%d) ===" % len(errors))
        for e in errors: print(" -", e)
    if warns:
        print("\n=== WARNINGS (%d) ===" % len(warns))
        for x in warns: print(" -", x)
    if not errors:
        print("\nNo errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
