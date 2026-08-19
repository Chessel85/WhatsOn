#!/usr/bin/env python3
"""Fetch the cruise ship schedule for Southampton from ABP Southampton VTS's
public XML data feed — the same one that powers the "Cruise Ship Schedule"
table on https://www.southamptonvts.co.uk (rendered client-side via XSLT,
see /xsl/sotcruiseship.xsl).

Not a documented/versioned API, but it's the feed ABP's own public page
consumes to build that table, so at least it's meant for public display —
unlike scraping rendered HTML off a page. It could still change or move
without notice.

The feed itself extends for months ahead, but is capped here to
LOOKAHEAD_DAYS to keep the page a manageable size.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests

from _common import REPO_ROOT, fetch_text, run, write_json

LOCAL_TZ = ZoneInfo("Europe/London")
LOOKAHEAD_DAYS = 14

CURRENT_PATH = REPO_ROOT / "data" / "current" / "cruise_ships.json"

FEED_URL = "https://www.southamptonvts.co.uk/xml/sotcruiseship.xml"

# CruiseMapper's own sitemap of ship pages — used to resolve a "ship
# details" link automatically. robots.txt only disallows /admin/, and a
# sitemap is explicitly meant for this kind of programmatic use, so this is
# a step more solid than the reverse-engineered endpoints elsewhere in this
# project. Slugs look like ".../ships/Fred-Olsen-Borealis-717" — only an
# EXACT name match (after stripping the trailing "-<id>") is trusted, since
# short/generic ship names can collide with unrelated vessels in the sitemap
# (e.g. "BOREALIS" also matches an unrelated icebreaker) and a wrong link is
# worse than no link.
CRUISEMAPPER_SITEMAP_URL = "https://www.cruisemapper.com/sitemap-ships.xml"

SHIP_SLUG_RE = re.compile(r"/ships/([^/<]+)-(\d+)$")


def fetch_cruisemapper_index():
    """Returns {SHIP NAME (upper, spaces): cruisemapper URL}, built from
    CruiseMapper's own ships sitemap. Only exact name matches are kept
    useful here deliberately — see the module docstring note above.
    """
    xml = fetch_text(CRUISEMAPPER_SITEMAP_URL)
    index = {}
    for url in re.findall(r"<loc>(https://www\.cruisemapper\.com/ships/[^<]+)</loc>", xml):
        match = SHIP_SLUG_RE.search(url)
        if not match:
            continue
        name = match.group(1).replace("-", " ").upper()
        index[name] = url
    return index


def wikipedia_search_url(ship_name):
    query = quote(f"{ship_name} cruise ship")
    return f"https://en.wikipedia.org/w/index.php?search={query}"


def marinetraffic_url(imo):
    return f"https://www.marinetraffic.com/en/ais/details/ships/imo:{imo}" if imo else None


def resolve_ship_links(ship_name, imo, cruisemapper_index):
    return {
        "marinetraffic_url": marinetraffic_url(imo),
        "cruisemapper_url": cruisemapper_index.get(ship_name.upper()),
        "wikipedia_search_url": wikipedia_search_url(ship_name),
    }


def parse_event(raw):
    """Feed values are "DD-Mon-YY HH:MM" in local UK time. Visits further
    out often don't have a firm time yet and use a placeholder word instead
    ("TBA", "AM", "PM", possibly others) — treated here as "time unknown,
    but here's a hint" rather than assumed to always be literally "TBA".
    Returns {"date": "YYYY-MM-DD", "time": <ISO UTC string or None>,
    "time_label": <the placeholder word, only present when time is None>},
    or None if the field was empty.
    """
    raw = raw.strip()
    if not raw:
        return None

    date_part, _, time_part = raw.partition(" ")
    local_date = datetime.strptime(date_part, "%d-%b-%y").date()

    try:
        local_dt = datetime.strptime(raw, "%d-%b-%y %H:%M").replace(tzinfo=LOCAL_TZ)
    except ValueError:
        event = {"date": local_date.isoformat(), "time": None}
        if time_part:
            event["time_label"] = time_part
        return event

    time_iso = local_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"date": local_date.isoformat(), "time": time_iso}


def fetch_visits():
    root = ElementTree.fromstring(fetch_text(FEED_URL))
    today = datetime.now(LOCAL_TZ).date()
    horizon = today + timedelta(days=LOOKAHEAD_DAYS)

    try:
        cruisemapper_index = fetch_cruisemapper_index()
    except requests.RequestException:
        cruisemapper_index = {}  # ship detail links are a nice-to-have, not worth failing the whole fetch over

    visits = []
    for row in root.iter("row"):
        arrival = parse_event(row.findtext("arrival", ""))
        departure = parse_event(row.findtext("departure", ""))
        if not arrival and not departure:
            continue

        dates = [datetime.fromisoformat(e["date"]).date() for e in (arrival, departure) if e]
        if all(d < today or d > horizon for d in dates):
            continue  # entirely outside the window we care about

        ship_name = row.findtext("ship_name", "").strip()
        imo = row.findtext("lloyds_no.", "").strip()

        visits.append(
            {
                "ship_name": ship_name,
                "berth": row.findtext("berth", "").strip(),
                "arrival": arrival,
                "departure": departure,
                "agent": row.findtext("agent", "").strip(),
                "links": resolve_ship_links(ship_name, imo, cruisemapper_index),
            }
        )

    visits.sort(key=lambda v: (v["arrival"] or v["departure"])["date"])
    return visits


def main():
    visits = fetch_visits()
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "https://www.southamptonvts.co.uk/live_information/shipping_movements_and_cruise_ship_schedule/cruise_ship_schedule/",
        "location": "Southampton",
        "visits": visits,
    }
    write_json(CURRENT_PATH, output)
    print(f"Cruise ships updated: {len(visits)} visits over the next {LOOKAHEAD_DAYS} days")


if __name__ == "__main__":
    run(main, "cruise ships")
