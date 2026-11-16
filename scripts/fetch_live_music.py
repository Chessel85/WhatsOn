#!/usr/bin/env python3
"""Fetch upcoming live-music events in/around Southampton from Visit
Southampton's event database.

Visit Southampton's `/events/live-music/` page is editorial copy, not a
gig list, and its `/events/` listing exposes only a handful of events in
plain HTML. But the site's sitemap lists every individual event page
(`/event/<slug>/<id>/`, ~1000 of them, each with a `<lastmod>`), and each
event page embeds a `var data = {...}` JSON blob holding its title,
categories (we keep those tagged "Music"), venue name (the "Address1"
user-defined field), booking URL and its `openings` (start/end dates plus
a weekday/start-time pattern for recurring events). robots.txt allows this
(Crawl-delay: 2, honoured here).

~1000 pages at a 2s crawl-delay is far too slow to refetch every day, so
parsed results are cached in `data/cache/live_music_pages.json`, keyed by
page URL and the sitemap's `lastmod` — a page is only refetched when it's
new or its lastmod changed. Non-music and already-finished events are
cached too (as `null` / no upcoming dates) so they aren't refetched. A
per-run cap (`MAX_PAGES_PER_RUN`) spreads the first-ever backfill across
several scheduled runs rather than one very long one; the output just fills
in as the cache does.

Recurring events (e.g. a weekly Saturday gig) are expanded into one entry
per occurrence within `LOOKAHEAD_DAYS`. Opening times in the data carry a
spurious "Z" suffix but are really UK local clock times, so they're
converted via Europe/London.

Not an official API — same undocumented-source trade-off as this project's
other feeds. Mostly promoter-listed shows (touring/tribute acts, festivals,
Christmas shows) rather than pub nights, so pub coverage is thin; other
sources can be added to the dedupe step later.
"""
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from _common import REPO_ROOT, fetch_text, run, write_json
from fetch_city_events import dedupe

SITEMAP_URL = "https://www.visitsouthampton.co.uk/sitemap.xml"
EVENT_URL_RE = re.compile(r"<url>\s*<loc>([^<]*/event/[^<]*)</loc>(?:\s*<lastmod>([^<]*)</lastmod>)?", re.S)

CRAWL_DELAY_SECONDS = 2
MAX_PAGES_PER_RUN = 500
LOOKAHEAD_DAYS = 90
MUSIC_CATEGORY = "music"
LONDON = ZoneInfo("Europe/London")

CURRENT_PATH = REPO_ROOT / "data" / "current" / "live_music.json"
CACHE_PATH = REPO_ROOT / "data" / "cache" / "live_music_pages.json"


def load_cache():
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def parse_page(html):
    """Return {title, venue, booking_url, openings} for a music event page,
    or None if it isn't a music event / has no usable data."""
    marker = "var data = "
    start = html.find(marker)
    if start == -1:
        return None
    data, _ = json.JSONDecoder().raw_decode(html[start + len(marker):])

    categories = {c.get("catName", "").lower() for c in data.get("categories") or []}
    if MUSIC_CATEGORY not in categories:
        return None

    udfs = {u.get("name"): u.get("value") for u in data.get("udfs") or []}
    venue = (udfs.get("Address1") or "").strip() or None

    openings = []
    for o in data.get("openings") or []:
        days = []
        for d in o.get("days") or []:
            if not d.get("open"):
                continue
            times = [t.get("timeopen", "")[11:16] for t in d.get("times") or [] if t.get("timeopen")]
            days.append({"day": d.get("day"), "time": times[0] if times else None})
        openings.append(
            {
                "start": (o.get("startdate") or "")[:10],
                "end": (o.get("enddate") or "")[:10],
                "days": days,
            }
        )
    if not openings:
        return None

    return {
        "title": (data.get("title") or "").strip(),
        "venue": venue,
        "openings": openings,
    }


def expand_occurrences(page, today, horizon):
    """One (date, "HH:MM" or None) per real occurrence in [today, horizon]."""
    seen = set()
    for o in page["openings"]:
        try:
            first = date.fromisoformat(o["start"])
            last = date.fromisoformat(o["end"] or o["start"])
        except ValueError:
            continue
        day = max(first, today)
        weekday_times = {(d["day"] % 7): d["time"] for d in o["days"]}  # Sunday may be 0 or 7
        # A single-day opening is one event regardless of weekday data.
        single_time = o["days"][0]["time"] if o["days"] else None
        while day <= min(last, horizon):
            if first == last:
                seen.add((day, single_time))
            else:
                wd = day.isoweekday() % 7
                if wd in weekday_times:
                    seen.add((day, weekday_times[wd]))
            day += timedelta(days=1)
    return sorted(seen, key=lambda s: (s[0], s[1] or ""))


def to_event(page, url, day, clock):
    if clock:
        local = datetime.fromisoformat(f"{day.isoformat()}T{clock}").replace(tzinfo=LONDON)
        when = local.astimezone(timezone.utc)
        all_day = False
    else:
        when = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        all_day = True
    event = {
        "title": page["title"],
        "venue": page["venue"],
        "time": when.isoformat().replace("+00:00", "Z"),
        "url": url,
        "source": "visit_southampton",
    }
    if all_day:
        event["all_day"] = True
    return event


def main():
    sitemap = fetch_text(SITEMAP_URL)
    entries = {url: lastmod or "" for url, lastmod in EVENT_URL_RE.findall(sitemap)}
    if not entries:
        raise RuntimeError("no event URLs found in sitemap")

    cache = load_cache()
    cache = {url: v for url, v in cache.items() if url in entries}  # drop pages no longer listed

    todo = [url for url, lastmod in entries.items() if cache.get(url, {}).get("lastmod") != lastmod]
    print(f"{len(entries)} event pages listed, {len(todo)} new/changed, fetching up to {MAX_PAGES_PER_RUN}")

    fetched = 0
    for url in todo[:MAX_PAGES_PER_RUN]:
        if fetched:
            time.sleep(CRAWL_DELAY_SECONDS)
        fetched += 1
        try:
            page = parse_page(fetch_text(url))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                page = None  # stale sitemap entry: cache as "nothing here" until its lastmod changes
            else:
                print(f"skipping {url}: {exc}", file=sys.stderr)
                continue  # not cached, so retried next run
        except Exception as exc:  # noqa: BLE001 - one bad page shouldn't stop the rest
            print(f"skipping {url}: {exc}", file=sys.stderr)
            continue  # not cached, so retried next run
        cache[url] = {"lastmod": entries[url], "page": page}
        if fetched % 50 == 0:
            write_json(CACHE_PATH, cache)  # checkpoint so an interrupted run isn't wasted

    write_json(CACHE_PATH, cache)

    today = datetime.now(LONDON).date()
    horizon = today + timedelta(days=LOOKAHEAD_DAYS)
    events = []
    for url, entry in cache.items():
        page = entry.get("page")
        if not page:
            continue
        for day, clock in expand_occurrences(page, today, horizon):
            events.append(to_event(page, url, day, clock))

    events = dedupe(events)
    events.sort(key=lambda e: e["time"])
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Visit Southampton",
        "location": "Southampton, UK",
        "pages_pending": max(0, len(todo) - MAX_PAGES_PER_RUN),
        "events": events,
    }
    write_json(CURRENT_PATH, output)
    print(f"Live music updated: {len(events)} events ({output['pages_pending']} pages still to fetch)")


if __name__ == "__main__":
    run(main, "live music")
