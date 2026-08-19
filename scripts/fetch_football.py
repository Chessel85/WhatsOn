#!/usr/bin/env python3
"""Fetch upcoming fixtures for Southampton FC, AFC Bournemouth and Eastleigh
FC from ESPN's public but undocumented soccer API (site.api.espn.com) — the
same data ESPN's own web/app clients render, not an official product.

Chosen because it's the one source that covers all three clubs uniformly:
Southampton (Championship), Bournemouth (Premier League) and Eastleigh
(National League, tier 5) span three divisions plus cup competitions, and no
single free, keyless API otherwise covers all of that. TheSportsDB's free
tier only ever returns a single next fixture per team/league; the clubs' own
official sites don't share a common template to scrape (and saintsfc.co.uk
didn't even respond to a plain request while building this).

The per-league scoreboard endpoint
(site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates=...)
caps out at 100 events per request, which the National League (24 teams,
often two matchdays a week) can exceed over a 90-day span — so each
competition is queried in date-range chunks and results are merged.

Cup coverage is what ESPN happens to carry, not a curated list: the FA Cup
slug (eng.fa) only returns events once a round's fixtures are scheduled,
which for a National League club's early qualifying rounds may not be until
closer to the date, so Eastleigh's cup fixtures can lag behind the league
ones appearing here. There's no ESPN slug found for the FA Trophy (the
non-League cup Eastleigh actually enters, distinct from the EFL Trophy),
so those fixtures aren't included — an accepted gap, not a bug.
"""
import json
from datetime import datetime, timedelta, timezone

from _common import REPO_ROOT, fetch_text, run, write_json

LOOKAHEAD_DAYS = 90
CHUNK_DAYS = 21  # keeps each request comfortably under ESPN's ~100-event cap

CURRENT_PATH = REPO_ROOT / "data" / "current" / "football.json"

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"

CLUBS = [
    {"id": "southampton", "name": "Southampton FC", "espn_team_id": "376"},
    {"id": "bournemouth", "name": "AFC Bournemouth", "espn_team_id": "349"},
    {"id": "eastleigh", "name": "Eastleigh FC", "espn_team_id": "3897"},
]

# ESPN's own league names are usable as-is but a couple carry a redundant
# "English " prefix or a sponsor name not worth reproducing here.
COMPETITIONS = [
    {"slug": "eng.1", "name": "Premier League"},
    {"slug": "eng.2", "name": "Championship"},
    {"slug": "eng.5", "name": "National League"},
    {"slug": "eng.fa", "name": "FA Cup"},
    {"slug": "eng.league_cup", "name": "EFL Cup"},
]


def date_chunks(start, horizon, chunk_days=CHUNK_DAYS):
    chunks = []
    current = start
    while current <= horizon:
        chunk_end = min(current + timedelta(days=chunk_days - 1), horizon)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def fetch_competition_events(slug, start, horizon):
    """Returns {event_id: event}, merged across date-range chunks."""
    events = {}
    for chunk_start, chunk_end in date_chunks(start, horizon):
        date_param = f"{chunk_start:%Y%m%d}-{chunk_end:%Y%m%d}"
        url = f"{SCOREBOARD_URL.format(slug=slug)}?dates={date_param}"
        data = json.loads(fetch_text(url))
        for event in data.get("events", []):
            events[event["id"]] = event
    return events


def build_fixture(event, club_team_id, competition_name):
    competition = event["competitions"][0]
    competitors = {c["homeAway"]: c for c in competition["competitors"]}
    home, away = competitors["home"], competitors["away"]
    is_home = home["team"]["id"] == club_team_id
    opponent = (away if is_home else home)["team"]["displayName"]
    venue = (competition.get("venue") or {}).get("fullName")

    return {
        "date": event["date"],
        "opponent": opponent,
        "home_away": "home" if is_home else "away",
        "venue": venue,
        "competition": competition_name,
    }


def fetch_fixtures_by_club():
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=LOOKAHEAD_DAYS)
    now = datetime.now(timezone.utc)

    club_by_team_id = {club["espn_team_id"]: club for club in CLUBS}
    fixtures_by_club = {club["id"]: {} for club in CLUBS}

    for competition in COMPETITIONS:
        events = fetch_competition_events(competition["slug"], today, horizon)
        for event in events.values():
            for competitor in event["competitions"][0]["competitors"]:
                club = club_by_team_id.get(competitor["team"]["id"])
                if not club:
                    continue
                fixture = build_fixture(event, competitor["team"]["id"], competition["name"])
                kickoff = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00"))
                if kickoff < now:
                    continue
                fixtures_by_club[club["id"]][event["id"]] = fixture

    return {
        club["id"]: sorted(fixtures_by_club[club["id"]].values(), key=lambda f: f["date"])
        for club in CLUBS
    }


def main():
    fixtures_by_club = fetch_fixtures_by_club()

    clubs = [
        {"id": club["id"], "name": club["name"], "fixtures": fixtures_by_club[club["id"]]}
        for club in CLUBS
    ]

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "ESPN",
        "lookahead_days": LOOKAHEAD_DAYS,
        "clubs": clubs,
    }
    write_json(CURRENT_PATH, output)

    total = sum(len(c["fixtures"]) for c in clubs)
    print(f"Football fixtures updated: {total} fixtures across {len(CLUBS)} clubs")


if __name__ == "__main__":
    run(main, "football")
