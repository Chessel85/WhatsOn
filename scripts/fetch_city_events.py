#!/usr/bin/env python3
"""Fetch upcoming Southampton city events from hellosouthampton.co.uk.

Not an official source, but a normal WordPress site with server-rendered
event listings (robots.txt only disallows /wp-admin/) — a much better fit
than scraping Facebook, which explicitly prohibits automated access in its
Terms of Service. The listing page server-renders ~45 upcoming events
(roughly a month out); more are behind a JS "Load More" button, not
pursued here.
"""
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from _common import REPO_ROOT, fetch_text, run, write_json

EVENTS_URL = "https://hellosouthampton.co.uk/whats-on-in-southampton/"

CURRENT_PATH = REPO_ROOT / "data" / "current" / "city_events.json"


def fetch_events():
    soup = BeautifulSoup(fetch_text(EVENTS_URL), "html.parser")

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
            }
        )

    events.sort(key=lambda e: e["time"])
    return events


def main():
    events = fetch_events()
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": EVENTS_URL,
        "location": "Southampton, UK",
        "events": events,
    }
    write_json(CURRENT_PATH, output)
    print(f"City events updated: {len(events)} events")


if __name__ == "__main__":
    run(main, "city events")
