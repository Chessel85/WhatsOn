#!/usr/bin/env python3
"""Fetch this season's fixtures and results for Southampton FC, AFC
Bournemouth and Eastleigh FC from ESPN's public but undocumented soccer API
(site.api.espn.com) — the same data ESPN's own web/app clients render, not
an official product.

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
often two matchdays a week) can exceed over a wide span — so each
competition is queried in date-range chunks and results are merged.

"Current season" is a computed window, not a lookahead count: 1 August of
the season-start year through 31 July the following year, where the
season-start year is this year if today is in July-December, else last
year. That's also exactly the "results vs fixtures" flip the maintainer
wants at 1 July — before it, the season just finished, so the page shows
that season's results (and, naturally, few or no fixtures left); after it,
the new season's fixture list is usually out already but nothing's been
played yet, so the page shows fixtures with no results. No separate
UI-side date logic is needed for that; it falls out of which season is
"current" for a given date. This does mean quite a few more requests per
run than a 90-day lookahead would (season span / 21-day chunks, per
competition) — accepted, since most of a cup competition's chunks return
zero events until fixtures for that round are actually scheduled.

Cup coverage is what ESPN happens to carry, not a curated list: the FA Cup
slug (eng.fa) only returns events once a round's fixtures are scheduled,
which for a National League club's early qualifying rounds may not be until
closer to the date, so Eastleigh's cup fixtures can lag behind the league
ones appearing here. There's no ESPN slug found for the FA Trophy (the
non-League cup Eastleigh actually enters, distinct from the EFL Trophy),
so those fixtures aren't included — an accepted gap, not a bug.

League position/points come from a separate, also-undocumented endpoint:
site.api.espn.com/apis/v2/sports/soccer/{league}/standings (note: NOT
.../apis/site/v2/.../standings, which returns an empty object for soccer —
confirmed live). The standings lookup is best-effort and isolated from the
rest of the run (same philosophy as fetch_airport.py's live adsb.lol
lookups): if it fails or the response shape changes, a club's league
position/points just come back null rather than failing the whole fetch.

Cup status ("in the EFL Cup" vs "knocked out of the FA Cup") is a heuristic,
not a flag ESPN provides: a club is "in_progress" if it has an upcoming
fixture in that competition, "knocked_out" if its most recent result there
was a loss with no fixture yet scheduled, or "through" (progressed, next
round just not scheduled yet) if that most recent result was a win/draw —
the same early-rounds-lag gap noted above means a "through" club can sit in
that state for a while before ESPN publishes their next-round fixture.
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone

from _common import REPO_ROOT, fetch_text, run, write_json

CHUNK_DAYS = 21  # keeps each request comfortably under ESPN's ~100-event cap

CURRENT_PATH = REPO_ROOT / "data" / "current" / "football.json"

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard"
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/soccer/{slug}/standings"

CLUBS = [
    {"id": "southampton", "name": "Southampton FC", "espn_team_id": "376"},
    {"id": "bournemouth", "name": "AFC Bournemouth", "espn_team_id": "349"},
    {"id": "eastleigh", "name": "Eastleigh FC", "espn_team_id": "3897"},
]

# Which competition slug is each club's league (as opposed to a cup) —
# hardcoded like CLUBS/COMPETITIONS below; needs a manual update on
# promotion/relegation, same maintenance tradeoff as elsewhere in this repo.
CLUB_LEAGUE_SLUG = {
    "southampton": "eng.2",
    "bournemouth": "eng.1",
    "eastleigh": "eng.5",
}

# ESPN's own league names are usable as-is but a couple carry a redundant
# "English " prefix or a sponsor name not worth reproducing here.
COMPETITIONS = [
    {"slug": "eng.1", "name": "Premier League"},
    {"slug": "eng.2", "name": "Championship"},
    {"slug": "eng.5", "name": "National League"},
    {"slug": "eng.fa", "name": "FA Cup"},
    {"slug": "eng.league_cup", "name": "EFL Cup"},
]
COMPETITION_NAME_BY_SLUG = {c["slug"]: c["name"] for c in COMPETITIONS}


def season_bounds(today):
    """The '1 August - 31 July' window that's 'current' for a given date,
    with the flip happening 1 July (see module docstring)."""
    season_start_year = today.year if today.month >= 7 else today.year - 1
    return date(season_start_year, 8, 1), date(season_start_year + 1, 7, 31)


def date_chunks(start, end, chunk_days=CHUNK_DAYS):
    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def fetch_competition_events(slug, start, end):
    """Returns {event_id: event}, merged across date-range chunks."""
    events = {}
    for chunk_start, chunk_end in date_chunks(start, end):
        date_param = f"{chunk_start:%Y%m%d}-{chunk_end:%Y%m%d}"
        url = f"{SCOREBOARD_URL.format(slug=slug)}?dates={date_param}"
        data = json.loads(fetch_text(url))
        for event in data.get("events", []):
            events[event["id"]] = event
    return events


def build_event_record(event, club_team_id, competition_name):
    """Returns (record, is_completed_result). For a completed match, record
    carries goals_for/goals_against/outcome; otherwise it's a plain
    upcoming-fixture record (unplayed, postponed, or in-progress events are
    all treated as 'not yet a result')."""
    competition = event["competitions"][0]
    competitors = {c["homeAway"]: c for c in competition["competitors"]}
    home, away = competitors["home"], competitors["away"]
    is_home = home["team"]["id"] == club_team_id
    mine, theirs = (home, away) if is_home else (away, home)
    venue = (competition.get("venue") or {}).get("fullName")

    base = {
        "date": event["date"],
        "opponent": theirs["team"]["displayName"],
        "home_away": "home" if is_home else "away",
        "venue": venue,
        "competition": competition_name,
    }

    status = event.get("status", {}).get("type", {})
    if not status.get("completed"):
        return base, False

    goals_for = int(mine["score"])
    goals_against = int(theirs["score"])
    if mine.get("winner"):
        outcome = "W"
    elif theirs.get("winner"):
        outcome = "L"
    else:
        outcome = "D"
    return {**base, "goals_for": goals_for, "goals_against": goals_against, "outcome": outcome}, True


def fetch_fixtures_and_results_by_club(season_start, season_end):
    now = datetime.now(timezone.utc)

    club_by_team_id = {club["espn_team_id"]: club for club in CLUBS}
    fixtures_by_club = {club["id"]: {} for club in CLUBS}
    results_by_club = {club["id"]: {} for club in CLUBS}

    for competition in COMPETITIONS:
        events = fetch_competition_events(competition["slug"], season_start, season_end)
        for event in events.values():
            for competitor in event["competitions"][0]["competitors"]:
                club = club_by_team_id.get(competitor["team"]["id"])
                if not club:
                    continue
                record, is_result = build_event_record(event, competitor["team"]["id"], competition["name"])
                if is_result:
                    results_by_club[club["id"]][event["id"]] = record
                else:
                    kickoff = datetime.fromisoformat(record["date"].replace("Z", "+00:00"))
                    if kickoff < now:
                        continue  # not completed but already past - in progress, postponed, or
                        # abandoned; omitted from both lists until ESPN marks it completed
                    fixtures_by_club[club["id"]][event["id"]] = record

    fixtures = {
        club["id"]: sorted(fixtures_by_club[club["id"]].values(), key=lambda f: f["date"])
        for club in CLUBS
    }
    results = {
        club["id"]: sorted(results_by_club[club["id"]].values(), key=lambda r: r["date"])
        for club in CLUBS
    }
    return fixtures, results


def fetch_standings(slug, team_ids):
    """Best-effort {team_id: (position, points)}. Any failure (network,
    unexpected response shape) is swallowed - standings are an enrichment,
    not required for the run to succeed. See module docstring."""
    result = {}
    try:
        data = json.loads(fetch_text(STANDINGS_URL.format(slug=slug)))
        for child in data.get("children", []):
            for entry in child.get("standings", {}).get("entries", []):
                team_id = entry.get("team", {}).get("id")
                if team_id not in team_ids:
                    continue
                stats = {s.get("name"): s.get("value") for s in entry.get("stats", [])}
                rank = stats.get("rank")
                points = stats.get("points")
                result[team_id] = (
                    int(rank) if rank is not None else None,
                    int(points) if points is not None else None,
                )
    except Exception as exc:  # noqa: BLE001 - enrichment only, must not fail the run
        print(f"Standings lookup failed for {slug}: {exc}", file=sys.stderr)
    return result


def build_cup_status(competition_name, fixtures, results):
    comp_fixtures = [f for f in fixtures if f["competition"] == competition_name]
    comp_results = [r for r in results if r["competition"] == competition_name]
    if not comp_fixtures and not comp_results:
        return None  # club isn't in this competition at all this season
    if comp_fixtures:
        status = "in_progress"
    else:
        status = "knocked_out" if comp_results[-1]["outcome"] == "L" else "through"
    return {"competition": competition_name, "status": status}


def build_club(club, fixtures, results, standings_by_slug):
    league_slug = CLUB_LEAGUE_SLUG[club["id"]]
    league_name = COMPETITION_NAME_BY_SLUG[league_slug]
    position, points = standings_by_slug.get(league_slug, {}).get(club["espn_team_id"], (None, None))

    cups = [
        status
        for comp in COMPETITIONS
        if comp["slug"] != league_slug
        for status in [build_cup_status(comp["name"], fixtures, results)]
        if status is not None
    ]

    return {
        "id": club["id"],
        "name": club["name"],
        "league": {
            "competition": league_name,
            "position": position,
            "points": points,
            "played": len([r for r in results if r["competition"] == league_name]),
            "remaining": len([f for f in fixtures if f["competition"] == league_name]),
        },
        "cups": cups,
        "fixtures": fixtures,
        "past_results": results,
    }


def main():
    today = datetime.now(timezone.utc).date()
    season_start, season_end = season_bounds(today)

    fixtures_by_club, results_by_club = fetch_fixtures_and_results_by_club(season_start, season_end)

    standings_by_slug = {
        slug: fetch_standings(slug, {club["espn_team_id"] for club in CLUBS if CLUB_LEAGUE_SLUG[club["id"]] == slug})
        for slug in {CLUB_LEAGUE_SLUG[club["id"]] for club in CLUBS}
    }

    clubs = [
        build_club(club, fixtures_by_club[club["id"]], results_by_club[club["id"]], standings_by_slug)
        for club in CLUBS
    ]

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "ESPN",
        "season_start": season_start.isoformat(),
        "season_end": season_end.isoformat(),
        "clubs": clubs,
    }
    write_json(CURRENT_PATH, output)

    total_fixtures = sum(len(c["fixtures"]) for c in clubs)
    total_results = sum(len(c["past_results"]) for c in clubs)
    print(
        f"Football updated: {total_fixtures} fixtures, {total_results} results "
        f"across {len(CLUBS)} clubs"
    )


if __name__ == "__main__":
    run(main, "football")
