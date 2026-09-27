# distributepressreleases.com

Static site on GitHub Pages. Nothing here needs a server, a database or a paid API.

## Publishing a release

1. Copy `content/releases/_TEMPLATE.md` to `content/releases/YYYY-MM-DD-slug.md`.
2. Fill in the front matter and write the body.
3. Commit and push.

The **Publish releases** workflow does the rest: builds the release page, the
markdown mirror, the claims file and the distribution receipt; narrates it and
adds a podcast episode; rebuilds every feed including the per-industry,
per-region and per-company newsroom feeds; refreshes the 48-hour news sitemap;
pushes the URL to IndexNow; posts to Bluesky and Mastodon; then commits the lot.

Files whose name starts with `_` are treated as drafts and never published.

To run it by hand: Actions tab -> Publish releases -> Run workflow. There are
toggles there to skip narration or skip the announcements.

Locally:

    python3 scripts/publish.py --dry-run --no-audio --no-ping   # build nothing, print everything
    python3 scripts/publish.py --no-audio --no-ping             # build the files, announce nothing
    python3 scripts/verify.py                                   # validate the whole site

## Secrets to add

Repository Settings -> Secrets and variables -> Actions. Every one is optional.
A missing secret makes that one step say "skipped" on the receipt page and
changes nothing else.

| Secret | What it does | Where to get it |
| --- | --- | --- |
| `INDEXNOW_KEY` | Pushes new URLs to Bing, Yandex, Naver and Seznam | See below |
| `BLUESKY_HANDLE` | Your handle, e.g. `distributepressreleases.com` | Bluesky account |
| `BLUESKY_APP_PASSWORD` | App password, not your login password | Bluesky Settings -> App Passwords |
| `MASTODON_HOST` | Instance hostname, no `https://` | Your instance |
| `MASTODON_TOKEN` | Access token with `write:statuses` | Instance Preferences -> Development |

### Setting up IndexNow

1. Invent a key: 32 or more hex characters, e.g. `openssl rand -hex 16`.
2. Save it as the `INDEXNOW_KEY` secret.
3. Create a file at the repository root named `<that key>.txt` whose only
   content is the key itself. Commit it.

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
    newsrooms/       generated per-company feeds for the newsroom embed
    feeds/           generated per-industry and per-region feeds
    images/          logo, mark, favicons, share card
