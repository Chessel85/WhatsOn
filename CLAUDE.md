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

1. `scripts/fetch_<feed>.py` — calls the external source, normalizes the result, overwrites `data/current/<feed>.json`, appends a dated row to `data/history/<feed>.csv` if historical comparison is useful, exits non-zero on failure (no silent stale data). Use the shared helpers in `scripts/_common.py` rather than re-implementing them: `REPO_ROOT`, `USER_AGENT`, `fetch_text(url)` (GET with the shared UA + `raise_for_status`, returns `.text`), `write_json(path, data)`, and `run(main, label)` (wraps `main()` in the standard try/except → stderr + `sys.exit(1)` pattern — the whole `if __name__ == "__main__":` block should just be `run(main, "<feed>")`).
2. `.github/workflows/fetch-<feed>.yml` — `schedule:` (cadence appropriate to how often the source actually changes) + `workflow_dispatch:` (for manual testing), `permissions: contents: write`, installs `requirements.txt`, runs the script, commits+pushes only if `data/` changed.
3. An overview card on `index.html` (a real `<a>` link, not a clickable `<div>`, whose visible/accessible text includes the current summary value) linking to `<feed>.html`.
4. `<feed>.html` — a detail page sharing the same header/`styles.css`, with a "Back to dashboard" link before its content.
5. A registry entry + render function in `assets/app.js` (fetch path, overview summary renderer, detail renderer). Reuse the existing shared helpers rather than re-duplicating: `groupByLocalDate`/`localDateKey`/`formatDayHeading`/`formatTime` for date handling, and `pushHeading(elements, text)` / `pushFetchedAt(elements, data, sourceName)` for the two small pieces every `renderDetail` needs (a day/section `<h2>`, and the trailing "Data fetched ... from ..." paragraph).

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
scripts/
  _common.py              # shared fetch-script helpers — REPO_ROOT, USER_AGENT, fetch_text(), write_json(), run()
  fetch_<feed>.py          # one fetch script per feed
.github/workflows/fetch-<feed>.yml   # one scheduled workflow per feed
docs/brief.md             # original project brief
requirements.txt          # Python deps for the fetch scripts
```

## Build order

Feeds are built one at a time, fully shipped (script + workflow + page + NVDA-verified) before the next starts. Current order: weather → tides → cruise ships → city events → TV/radio new series, then further categories as they're scoped. Check `data/current/` and `.github/workflows/` for what's actually live versus still planned — this file won't stay in sync with day-to-day progress.

Several feeds rely on undocumented endpoints/scraping rather than official APIs, all a deliberate judgment call by the maintainer — don't "fix" fragility here by working around it technically, just expect occasional maintenance if the source changes:

- **Tides** (`scripts/fetch_tides.py`) calls EasyTide's own internal `Home/GetPredictionData` endpoint (reverse-engineered from its frontend JS) rather than the official ADMIRALTY UK Tidal API, because that API's developer-portal signup was too cumbersome. No API key needed.
- **Cruise ships** (`scripts/fetch_cruise_ships.py`) reads ABP Southampton VTS's public XML feed at `/xml/sotcruiseship.xml` — the same feed their own "Cruise Ship Schedule" page renders client-side via XSLT (`/xsl/sotcruiseship.xsl`). Not a documented API, but it's the actual data ABP serves to any visitor's browser, so a step more solid than scraping rendered HTML. Extends months ahead; capped to a 14-day window in the script (`LOOKAHEAD_DAYS`) to keep the page a manageable size — raise that constant if more lookahead is ever wanted.
- **City events** (`scripts/fetch_city_events.py`) scrapes hellosouthampton.co.uk's "What's On" page with `beautifulsoup4` — chosen specifically *instead of* the user's original idea of scraping `facebook.com/hellosoton`, since Facebook's Terms of Service explicitly prohibit automated access (a firm line, unlike the other two sources here) and its real event data sits behind a login wall anyway. hellosouthampton.co.uk is a normal WordPress site (`robots.txt` only disallows `/wp-admin/`) with clean server-rendered event cards. Server-renders ~45 upcoming events (~a month out); more are behind a JS "Load More" button, not pursued. Deliberately unfiltered — includes anything the page lists (festivals, gigs, markets, family events, and any sports fixtures that happen to be advertised there too) rather than building category-guessing logic.
- **TV & radio new series** (`scripts/fetch_tv_radio.py`) combines three undocumented sources for one feed: BBC One/Two/Three/Four use BBC iPlayer's own internal schedule API (`ibl.api.bbci.co.uk/ibl/v1/channels/{id}/schedule/{date}`) — the same data iPlayer's own schedule view renders, keyed by an arbitrary-but-stable English region id since regional opt-outs don't affect series/episode metadata. BBC Radio 4 and BBC World Service use the JSON API BBC Sounds' own Next.js schedule page calls client-side (`rms.api.bbc.co.uk/v2/experience/inline/schedules/{station}/{date}`, discovered via that page's embedded `__NEXT_DATA__` — station ids are `bbc_radio_fourfm` and `bbc_world_service`; note `bbc_radio_four` without the `fm` 404s). Unlike the BBC TV source, this radio endpoint exposes no repeat/rerun flag, so a same-week repeat of a series' first episode could occasionally register as a false "new series" — an accepted gap, not a bug, reflected in those channels' `confidence: "medium"`. World Service specifically is mostly rolling news/strand programming without "Series N" numbering, so it will often legitimately show no matches at all. ITV1 has no BBC-style endpoint at all, so it falls back to TVmaze's public GB schedule (`api.tvmaze.com/schedule?country=GB&date={date}`) filtered to network `"ITV1"` — structurally the weakest signal (no rerun/text cue, just "episode number 1"), hence `confidence: "low"` with a caveat shown on its detail-page section. "New series starting" itself is a heuristic in all cases (subtitle/episode-number pattern matching, tuned against real schedule data but not a guarantee) — see the docstring and comments in `fetch_tv_radio.py` for the exact rules. Each of the 7 channels is fetched independently and failures are isolated per-channel (unlike every other fetch script here, where any exception fails the whole run) so one source breaking doesn't blank out the rest.

Each cruise ship visit's name links to a **CruiseMapper** details page (specs, deck plans, itinerary) — resolved automatically every fetch against CruiseMapper's own `sitemap-ships.xml` (explicitly crawler-permitted by their `robots.txt`), matched by exact ship name only. No manual ship→ID mapping file: unmatched/ambiguous names (e.g. a generic name that collides with an unrelated vessel in the sitemap) fall back to a Wikipedia search link instead, rather than risk linking the wrong ship. A MarineTraffic tracking URL (built directly from IMO) is also computed into the JSON but not currently rendered — dropped from the table on request to avoid a redundant "Links" column, easy to re-add if wanted later.
