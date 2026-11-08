# distributepressreleases.com · MASTER-GAMEPLAN
Last updated 2026-11-08 (overnight marketing session). Network plan: `Desktop\01 SEARCH CONVERTS LLC\Search Converts Website Network\05 TIER 3 - Authority - PR, News & Directories\`.

## Role
The network newswire: real announcements from Zach's businesses and clients, with per-newsroom feeds, claims files and receipts. Authority asset; links to eyetoad.com are sponsored/nofollow only.

## State (Nov 8, 2026)
- Repo on `main`, live on GitHub Pages at the www host (Search Console property is the www host).
- GA4 G-NXFKB23X85 live on the home page; 50 of 79 index pages in the repo lack the tag (newsroom and release detail pages). Fix: run `node C:\Users\zachw\ga4tag.mjs <repo> G-NXFKB23X85` (idempotent) and rebuild the pages the generator owns so the tag survives the next publish.
- Lighthouse mobile (local lab): home 92 perf / 96 a11y / 92 BP / 100 SEO.
- llms.txt present. No AdSense; adding it is a monetization decision for Zach (a newswire can carry it, but it dilutes the authority signal).

## Next steps
1. GA4 tag on every generated page (fix the generator template, not just the output).
2. Keep every release real and dated; claims.json per release stays the standard.
3. Link GA4 to Search Console.
