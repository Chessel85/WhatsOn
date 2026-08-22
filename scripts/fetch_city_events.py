#!/usr/bin/env python3
"""Fetch upcoming Southampton city events from three independent sources.

hellosouthampton.co.uk is a normal WordPress site with server-rendered
event listings (robots.txt only disallows /wp-admin/) — a much better fit
than scraping Facebook, which explicitly prohibits automated access in its
Terms of Service. The listing page server-renders ~45 upcoming events
(roughly a month out); more are behind a JS "Load More" button, not
pursued here.

The University of Southampton's own events calendar
(events.soton.ac.uk) is a second, independent source added to catch
campus-hosted public events (lectures, concerts, festivals) that a
general city "what's on" blog doesn't cover — e.g. it missed the British
Science Festival, hosted at the University in September 2026. Despite the
JS-driven look, the whole year's events are server-rendered directly into
the page (progressive enhancement — JS just filters/hides the same
markup), so one plain GET returns everything; no separate search/API
endpoint was found. Most events link out to their own booking page
(Eventbrite, Zoom, a department site); ones without such a link fall back
to the calendar's own URL. A handful of entries (exhibitions, multi-day
courses) have no specific start time and are skipped, same discipline as
hellosouthampton's own "skip anything we can't display usefully" rule.

Visit Southampton (visitsouthampton.co.uk), the official destination-
marketing site for the city, is the third source — specifically its
"Top events of 2026" article (events/annual-events/), the one place that
was confirmed to actually list the British Science Festival. Visit
Southampton also runs a proper events database (988 individual event
pages per its sitemap, browsable at /events/ and per-category pages) but
that listing's plain HTML only ever surfaced ~5 near-term events with no
pagination/API call visible in the markup, so it wasn't usable here
without deeper reverse-engineering. The annual-events article is
editorial prose, not structured data: title/date/venue are squashed into
one comma-separated string per event (e.g. "British Science Festival,
16 - 20 September, city wide (locations TBC) (FREE)") under a month/year
`<h2>` heading, with no machine-readable date at all — parsed here with a
regex against the free text. This is more fragile than the other two
sources (irregular hyphen/en-dash date ranges, year inferred from the
section heading) and only covers ~20 flagship annual events rather than
day-to-day listings, but it's what actually closes the gap that prompted
adding a third source. None of these events carry a specific time
(`"all_day": true`), just a date.

Not an official API in any case — all three sources are undocumented,
same trade-off as this project's other feeds. Three independent upstream
sources feed this one feed — unlike most other fetch scripts here, one
source breaking shouldn't blank out the other two, so each is wrapped in
`safe_fetch()` (same pattern as `fetch_tv_radio.py`'s per-channel
isolation).
"""
import re
import sys
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from _common import REPO_ROOT, fetch_text, run, write_json

HELLOSOUTHAMPTON_URL = "https://hellosouthampton.co.uk/whats-on-in-southampton/"
UNIVERSITY_EVENTS_URL = "https://www.events.soton.ac.uk/"
VISIT_SOUTHAMPTON_URL = "https://www.visitsouthampton.co.uk/events/annual-events/"

MONTHS = {
    name.lower(): i
    for i, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}

CURRENT_PATH = REPO_ROOT / "data" / "current" / "city_events.json"


def fetch_hellosouthampton():
    soup = BeautifulSoup(fetch_text(HELLOSOUTHAMPTON_URL), "html.parser")

    events = []
    for article in soup.find_all("article", class_="type-event"):
        title = article.find("h2", class_="post_title")
        venue = article.find(class_="event_venue_name")
        time_tag = article.find("time", class_="event_date")
        link = article.find("a", class_="w-vwrapper-link")
        if not (title and time_tag and time_tag.get("datetime") and link and link.get("href")):
            continue  # skip anything that doesn't have what we need to display it usefully

        start = datetime.fromisoformat(time_tag["datetime"])
        events.append(
            {
                "title": title.get_text(strip=True),
                "venue": venue.get_text(strip=True) if venue else None,
                "time": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "url": link["href"],
                "source": "hellosouthampton",
            }
        )

    return events


def fetch_university_events():
    soup = BeautifulSoup(fetch_text(UNIVERSITY_EVENTS_URL), "html.parser")

    events = []
    for event_div in soup.find_all("div", class_="event"):
        heading = event_div.find("h3", itemprop="summary")
        start_tag = event_div.find("span", itemprop="startDate")
        if not (heading and start_tag and start_tag.get_text(strip=True)):
            continue  # skip anything without a title or a specific start time

        date_span = heading.find("span", class_="date")
        if date_span:
            date_span.decompose()
        title = heading.get_text(strip=True)

        venue = None
        for line in event_div.find_all("div"):
            text = line.get_text(strip=True)
            if text.startswith("Additional Place Info:"):
                venue = text.removeprefix("Additional Place Info:").strip()
                break

        url = UNIVERSITY_EVENTS_URL
        links_div = event_div.find("div", class_="event-links")
        if links_div:
            for a in links_div.find_all("a"):
                if "expand-link" not in (a.get("class") or []) and a.get("href"):
                    url = a["href"]
                    break

        events.append(
            {
                "title": title,
                "venue": venue,
                "time": start_tag.get_text(strip=True),
                "url": url,
                "source": "university",
            }
        )

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return [e for e in events if e["time"] >= now]


DATE_RE = re.compile(r"(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s+([A-Za-z]+)")
MONTH_HEADING_RE = re.compile(r"([A-Za-z]+)\s+(\d{4})")


def fetch_visit_southampton():
    soup = BeautifulSoup(fetch_text(VISIT_SOUTHAMPTON_URL), "html.parser")
    content = soup.find("main") or soup

    events = []
    year = None
    for tag in content.find_all(["h2", "h3"]):
        if tag.name == "h2":
            heading_match = MONTH_HEADING_RE.search(tag.get_text(" ", strip=True))
            if heading_match and heading_match.group(1).lower() in MONTHS:
                year = int(heading_match.group(2))
            continue

        if year is None:
            continue  # haven't reached a month heading yet

        text = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 2:
            continue  # not enough to find a date in

        title, date_text = parts[0], parts[1]
        venue = parts[2] if len(parts) > 2 else None

        date_match = DATE_RE.search(date_text)
        if not date_match or date_match.group(2).lower() not in MONTHS:
            continue  # couldn't find a parseable date

        try:
            start = datetime(
                year, MONTHS[date_match.group(2).lower()], int(date_match.group(1)),
                tzinfo=timezone.utc,
            )
        except ValueError:
            continue  # e.g. a day number that doesn't exist in that month

        link = tag.find("a", href=True)
        events.append(
            {
                "title": title,
                "venue": venue,
                "time": start.isoformat().replace("+00:00", "Z"),
                "url": link["href"] if link else VISIT_SOUTHAMPTON_URL,
                "source": "visit_southampton",
                "all_day": True,
            }
        )

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return [e for e in events if e["time"] >= now]


# When more than one source lists the same real-world event on the same day
# (e.g. hellosouthampton's "Southampton Pride 2026" and Visit Southampton's
# "Southampton Pride"), only one copy should survive. A raw fuzzy-match
# ratio on the full title is too easy to fool either way, so instead: strip
# years/punctuation, then treat titles as the same event if every word of
# the shorter one appears in the longer one — the pattern each real
# duplicate found here actually follows (one source's title is a trimmed or
# embellished version of the other's). Titles under two words are compared
# for an exact match only, to avoid a single common word (e.g. "Market")
# collapsing two unrelated same-day events into one.
SOURCE_PRIORITY = {"visit_southampton": 0, "university": 1, "hellosouthampton": 2}


def normalize_title(title):
    text = title.lower()
    text = re.sub(r"\b(19|20)\d{2}\b", "", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def same_event_title(a, b):
    words_a, words_b = set(normalize_title(a).split()), set(normalize_title(b).split())
    if not words_a or not words_b:
        return False
    shorter, longer = sorted([words_a, words_b], key=len)
    if len(shorter) < 2:
        return shorter == longer
    return shorter <= longer


def dedupe(events):
    kept = []
    for event in sorted(events, key=lambda e: (e["time"][:10], SOURCE_PRIORITY[e["source"]])):
        day = event["time"][:10]
        if any(
            k["time"][:10] == day and same_event_title(k["title"], event["title"])
            for k in kept
        ):
            continue
        kept.append(event)
    return kept


def safe_fetch(label, fetch_fn):
    try:
        return fetch_fn()
    except Exception as exc:  # noqa: BLE001 - isolate one source's failure from the rest
        print(f"{label} events unavailable, skipping: {exc}", file=sys.stderr)
        return []


def main():
    events = dedupe(
        safe_fetch("hellosouthampton", fetch_hellosouthampton)
        + safe_fetch("University of Southampton", fetch_university_events)
        + safe_fetch("Visit Southampton", fetch_visit_southampton)
    )
    events.sort(key=lambda e: e["time"])
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "hellosouthampton.co.uk, University of Southampton and Visit Southampton",
        "location": "Southampton, UK",
        "events": events,
    }
    write_json(CURRENT_PATH, output)
    print(f"City events updated: {len(events)} events")


if __name__ == "__main__":
    run(main, "city events")
