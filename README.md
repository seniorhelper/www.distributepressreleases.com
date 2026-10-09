# distributepressreleases.com

Static site on GitHub Pages. Nothing here needs a server, a database or a paid API.

## Publishing a release

1. Copy `content/releases/_TEMPLATE.md` to `content/releases/YYYY-MM-DD-slug.md`.
2. Fill in the front matter and write the body.
3. Commit and push.

The **Publish releases** workflow does the rest, in two passes:

1. **Build.** Release page, markdown mirror, claims file, narration (piper, in
   CI) and podcast episode; every feed including the per-industry, per-region
   and per-company feeds; the company newsroom page and the newsroom directory;
   the 48-hour news sitemap; and one syndication feed per destination in
   `syndication/`. It verifies the site and commits.
2. **Announce.** It waits for GitHub Pages to serve the new release, then pushes
   the URLs to IndexNow and posts to Bluesky and Mastodon. It records each
   result in `data/announced.json` and rebuilds the receipts.

It runs on every push that touches `content/releases/`, and every morning at
07:07 Denver time. A release dated in the future is held back and goes out on
the morning of its date.

Files whose name starts with `_` are treated as drafts and never published.

To run it by hand: Actions tab -> Publish releases -> Run workflow. There are
toggles there to skip narration or skip the announcements.

The free release builder at `/tools/release-builder/` writes a release file in
this format, previews its routing and has an "Open in GitHub" button that
prefills the new file for anyone with write access.

## The chain reaction: routing and syndication

`config/network.json` holds the filter. Every release is scored against every
network site. Points come from a matching industry, a matching region and topic
words in the text. Local sites also require a local region. The best matches,
up to three, get the release.

- `syndication/actionglobalnews.json`: every release. The Action Global News
  hourly job republishes each one at `/press-releases/<slug>/`, with a canonical
  link back to this site and the paid or affiliated label.
- `syndication/<site-id>.json`: only the releases routed to that site. Each
  network site carries a business-news module (`assets/network.js`) that reads
  its feed and stays hidden until there is something to show.

To add a site: add an entry to `network.json`, then paste the module into the
site:

    <section id="business-news" hidden aria-label="Business news">
      <h2>Business news</h2>
      <div data-dpr-network="site-id" data-limit="4"></div>
    </section>
    <script async src="https://distributepressreleases.com/assets/network.js"></script>

Set `"live": true` once the module is installed. Only live sites go on
receipts.

Front matter controls, all optional:

| Field | Effect |
| --- | --- |
| `affiliated: operator` | Eye To Ad Media's own release. Prints the operator disclosure instead of the paid label |
| `affiliated: common-ownership` | A company under common ownership. Prints that disclosure |
| `network: none` | Keeps the release off network sites |
| `network: site-id, site-id` | Forces specific network sites |
| `syndicate: no` | Also keeps the release off the news property |
| `keywords: a, b, c` | Extra routing hints. Never displayed |

## Secrets to add

Repository Settings -> Secrets and variables -> Actions. Every one is optional.
A missing secret makes that one step say "skipped" on the receipt page and
changes nothing else.

| Secret | What it does | Where to get it |
| --- | --- | --- |
| `INDEXNOW_KEY` | Optional. The committed key file is used when this is unset | See below |
| `BLUESKY_HANDLE` | Your handle, e.g. `distributepressreleases.com` | Bluesky account |
| `BLUESKY_APP_PASSWORD` | App password, not your login password | Bluesky Settings -> App Passwords |
| `MASTODON_HOST` | Instance hostname, no `https://` | Your instance |
| `MASTODON_TOKEN` | Access token with `write:statuses` | Instance Preferences -> Development |

### IndexNow

Already set up. `31ffee6f3195d2295c6e886a76531979.txt` at the root is the key
file, and the publisher finds it on its own. To rotate the key, replace the file
and, if you use the secret, update `INDEXNOW_KEY` to match.

The engines fetch that file to confirm you control the domain. The key in the
secret and the key in the filename must match exactly. Google does not
participate in IndexNow, so this affects Bing, Yandex, Naver and Seznam only.

## Rebuilding the marketing pages

The 26 marketing pages are generated from `src/` in the build project, not from
this repository. Edit them here directly, or regenerate and copy the whole tree.
`scripts/verify.py` validates whichever way you do it.

## What the verifier checks

Unbalanced HTML tags, unbalanced comments, missing canonical or verification
tags, missing or over-length titles and descriptions, more or fewer than one
`h1`, invalid JSON-LD, FAQ structured data that no longer matches the visible
page, broken internal links, uppercase or `.html` URLs, and orphan pages.

It runs on every push via the **Verify site** workflow, and again inside the
publish job before anything is committed.

## Structure

    assets/          css, shared js, the Wire assistant, the newsroom embed
    content/releases/  source markdown, one file per release
    scripts/         publish.py and verify.py
    releases/        generated release pages, mirrors, claims files, receipts
    newsrooms/       generated company newsroom pages, feeds and the directory
    network/         generated page listing the network and its filter
    syndication/     generated per-destination feeds (news property + network sites)
    config/          network.json routing rules
    data/            announced.json, the announcement ledger behind the receipts
    feeds/           generated per-industry and per-region feeds
    images/          logo, mark, favicons, share card
