# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

WhatsOn is a personal "what's on" dashboard for Southampton, UK (weather, tides, cruise ships, roadworks, football fixtures, theatre, pub live music, city events, plus a few non-local favourites like TV/radio and sport). The original brief is in `docs/brief.md`.

## Architecture

Static site, no server, no database engine:

```
GitHub Actions (cron)  →  fetch script  →  data/current/*.json + data/history/*.csv  →  git commit/push
                                                              │
                                                              ▼
                                          GitHub Pages serves repo statically
                                                              │
                                                              ▼
                                    index.html / <feed>.html + app.js fetch()es the JSON, renders it
```

Each category (a "feed") is fully independent: its own fetch script, its own scheduled GitHub Actions workflow, its own JSON/CSV output, its own detail page. A broken or rate-limited feed can't affect the others. There is no build step and no client-side framework — plain HTML/CSS/JS.

### Adding a new feed

Follow the pattern of existing feeds (check `scripts/`, `.github/workflows/`, and `data/current/` for the latest example):

1. `scripts/fetch_<feed>.py` — calls the external source, normalizes the result, overwrites `data/current/<feed>.json`, appends a dated row to `data/history/<feed>.csv` if historical comparison is useful, exits non-zero on failure (no silent stale data).
2. `.github/workflows/fetch-<feed>.yml` — `schedule:` (cadence appropriate to how often the source actually changes) + `workflow_dispatch:` (for manual testing), `permissions: contents: write`, installs `requirements.txt`, runs the script, commits+pushes only if `data/` changed.
3. An overview card on `index.html` (a real `<a>` link, not a clickable `<div>`, whose visible/accessible text includes the current summary value) linking to `<feed>.html`.
4. `<feed>.html` — a detail page sharing the same header/skip-link/`styles.css`, with a "Back to dashboard" link before its content.
5. A registry entry + render function in `assets/app.js` (fetch path, overview summary renderer, detail renderer).

Secrets (API keys) go in GitHub repo secrets, injected as env vars only inside that feed's workflow — never exposed client-side, since GitHub Pages content is public.

### Accessibility (required, not optional)

The dashboard is built and verified against **NVDA + Firefox** (the maintainer's daily setup), with a Chrome spot-check per feed. Practical implications for any frontend change:

- Real semantic HTML only — `<header>`/`<nav>`/`<main>`, one `<h1>` per page, proper heading hierarchy. No custom interactive widgets or hand-rolled ARIA. No skip-to-content link — the maintainer navigates by heading (NVDA's `H` key) rather than relying on one.
- **Never make a heading itself a link.** A card is a heading (plain text) followed by its content, with any link (e.g. "View weather details") as its own element within that content — not wrapping the whole card/heading in an `<a>`. Overview cards are still real `<a>` elements for the actual link, never `<div onclick>`.
- Client-side data loading needs a visible loading state and a *scoped* `aria-live="polite"` region around just the content that updates (not the whole page).
- Tabular data (tide times, hourly forecasts, ship listings) uses real `<table>`/`<caption>`/`<th scope>` markup, not div-grids — NVDA's table navigation depends on it.
- Dates/times use `<time datetime="...">`.
- Verify with an actual NVDA+Firefox pass (heading/landmark nav, table nav, live-region announcement) before calling a feed done — not just a visual check.

## Running locally

No build step. Serve the repo root and open it:

```
python -m http.server
```

Fetch scripts can be run directly to regenerate data files before testing the frontend against them:

```
pip install -r requirements.txt
python scripts/fetch_weather.py
```

## Repo layout

```
index.html               # overview dashboard — one summary card/link per live category
<feed>.html               # one detail page per category (e.g. weather.html)
assets/
  app.js                  # feed registry + render functions
  styles.css
data/
  current/<feed>.json     # latest snapshot per feed, read by the frontend
  history/<feed>.csv      # append-only history per feed, where useful
scripts/fetch_<feed>.py   # one fetch script per feed
.github/workflows/fetch-<feed>.yml   # one scheduled workflow per feed
docs/brief.md             # original project brief
requirements.txt          # Python deps for the fetch scripts
```

## Build order

Feeds are built one at a time, fully shipped (script + workflow + page + NVDA-verified) before the next starts. Current order: weather → tides → cruise ships, then further categories as they're scoped. Check `data/current/` and `.github/workflows/` for what's actually live versus still planned — this file won't stay in sync with day-to-day progress.

Two feeds rely on undocumented endpoints rather than official APIs, both a deliberate judgment call by the maintainer (weighed against the alternative of an official signup) — don't "fix" fragility here by working around it technically, just expect occasional maintenance if the source changes:

- **Tides** (`scripts/fetch_tides.py`) calls EasyTide's own internal `Home/GetPredictionData` endpoint (reverse-engineered from its frontend JS) rather than the official ADMIRALTY UK Tidal API, because that API's developer-portal signup was too cumbersome. No API key needed.
- **Cruise ships** (`scripts/fetch_cruise_ships.py`) reads ABP Southampton VTS's public XML feed at `/xml/sotcruiseship.xml` — the same feed their own "Cruise Ship Schedule" page renders client-side via XSLT (`/xsl/sotcruiseship.xsl`). Not a documented API, but it's the actual data ABP serves to any visitor's browser, so a step more solid than scraping rendered HTML. Extends months ahead; capped to a 14-day window in the script (`LOOKAHEAD_DAYS`) to keep the page a manageable size — raise that constant if more lookahead is ever wanted.

Each cruise ship visit also gets a **MarineTraffic** tracking link (built directly from the IMO number, always available) and a **"ship details" link** — resolved automatically every fetch against CruiseMapper's own `sitemap-ships.xml` (explicitly crawler-permitted by their `robots.txt`), matched by exact ship name only. No manual ship→ID mapping file: unmatched/ambiguous names (e.g. a generic name that collides with an unrelated vessel in the sitemap) just fall back to a Wikipedia search link rather than risk linking the wrong ship. This also covers passenger/cabin capacity and itinerary/next-port questions — rather than scraping that data out, we link to CruiseMapper's own page where it's already shown, keeping the fetch script free of fragile HTML scraping.
