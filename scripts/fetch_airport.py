#!/usr/bin/env python3
"""Fetch today's arrivals and departures for Southampton Airport (SOU/EGHI)
from the airport's own live flight-board API
(southamptonairport.com/Umbraco/api/FlightsApi/RetrieveFlights) — the same
undocumented Umbraco CMS endpoint its own website's arrivals/departures page
calls client-side. Plain GET, no auth, no API key. Query parameters like a
date filter are accepted but ignored server-side — it always returns
whatever is currently on the live board, which is normally just today but
can include the next day's first departure or two once today's board has
mostly emptied out.

The API exposes no aircraft registration or tail number, so there's no way
to confirm which physical aircraft operates which flight. "Rotations" are
instead inferred: for each arrival, the next not-yet-claimed departure to
the same place is treated as the same aircraft turning around — a heuristic
based on route + arrival-then-departure ordering (see match_rotations), not
a confirmed tail-number match. It holds up well against Southampton's real
schedule (small airport, one aircraft shuttling most routes back and forth
all day) but should be presented as an educated guess, not fact.

Where the board's own status text signals a flight is actually in the air
right now — anything but "Scheduled" or "Arrived ..." on an arrival (the
board uses several in-flight states, e.g. "Expected HH:MM" or "On
Approach", not just one), and "Airborne ..." on a departure —
match_flight_position() also looks up a live distance-from-airport via
adsb.lol's public ADS-B tracker, since the flight board itself carries no
live position. The board's flight numbers can't be used to look up a
specific live flight directly: verified live against adsb.lol, most of
this board's airlines (easyJet, Loganair, Aurigny) broadcast a semi-random
per-rotation ADS-B callsign with no fixed relationship to their public
flight number. What IS reliable is the callsign's airline prefix
(AIRLINE_ICAO_PREFIXES) plus the route's known bearing from Southampton
(DESTINATION_COORDS) — together, that's enough to pick the one aircraft of
the right airline heading the right way out of everything adsb.lol reports
within range, without ever needing to guess an exact callsign.
"""
import json
import math
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from _common import REPO_ROOT, fetch_text, run, write_json

CURRENT_PATH = REPO_ROOT / "data" / "current" / "airport.json"

FLIGHTS_URL = "https://www.southamptonairport.com/Umbraco/api/FlightsApi/RetrieveFlights"

# adsb.lol's own aircraft-in-a-circle endpoint, capped by the API itself at
# 250 nautical miles — the largest single query that still covers most of
# this board's routes close to the Southampton end of the flight (Faro is
# too far to ever be caught this way; an accepted gap, see
# fetch_nearby_aircraft).
ADSBLOL_POINT_URL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radius}"
ADSBLOL_RADIUS_NM = 250

# EGHI's own published position (SkyBrary / Great Circle Mapper) — not the
# more general Southampton city-centre point fetch_weather.py/
# fetch_astronomy.py use.
AIRPORT_LAT = 50.950298
AIRPORT_LON = -1.356800

EARTH_RADIUS_MILES = 3958.8
BEARING_TOLERANCE_DEGREES = 25

# A single blended average groundspeed (mph) used only to estimate how far
# into its route a flight should be by now, from either its elapsed time
# since actual takeoff (departures — parsed straight from the board's own
# "Airborne HH:MM" status) or its remaining time to the board's current ETA
# (arrivals — flight["time"]). Deliberately one flat number rather than a
# per-aircraft-type figure (the board doesn't say what's flying the route):
# short hops are climb/descent-dominated and slower in practice, long hops
# spend more time at a jet's faster cruise speed, and this splits the
# difference — checked against this board's actual routes it lands close to
# real block times (e.g. ~30min for the ~125mi Jersey hop, ~85min for the
# ~355mi Edinburgh one). This estimate is only ever used to narrow down
# which live aircraft plausibly IS a given flight (see
# match_flight_position) — it's never shown to the user directly.
ASSUMED_CRUISE_MPH = 250

# How far a live candidate's actual distance from Southampton is allowed to
# differ from the elapsed-time estimate above and still count as a
# plausible match — generous, since the estimate is only ever a rough
# approximation (headwinds, holding, non-great-circle routing, actual
# aircraft type all shift it).
PROGRESS_TOLERANCE_MIN_MILES = 40
PROGRESS_TOLERANCE_FRACTION = 0.35

# The one reliable signal in an otherwise semi-random live ADS-B callsign
# (see the module docstring) — a flight's airline prefix — mapped from the
# airline names southamptonairport.com gives. Manually maintained, same
# spirit as fetch_football.py's CLUBS/COMPETITIONS — expect occasional
# upkeep as routes/airlines change. Aer Lingus's Southampton routes are
# actually operated by Emerald Airlines under an "Aer Lingus Regional"
# codeshare, which may broadcast a different prefix entirely (unconfirmed)
# — those flights may simply never get a live match, an accepted gap
# rather than a bug.
AIRLINE_ICAO_PREFIXES = {
    "Loganair": "LOG",
    "Aurigny": "AUR",
    "KLM": "KLM",
    "easyJet": "EZY",
    "Aer Lingus": "EIN",
}

# Coordinates for every route currently on the board (southamptonairport.com
# locationCode -> lat/lon), used only to work out each route's expected
# bearing/distance from Southampton for match_flight_position(). Manually
# maintained — a new route needs an entry added here, same tradeoff as
# AIRLINE_ICAO_PREFIXES.
DESTINATION_COORDS = {
    "JER": (49.2079, -2.1955),   # Jersey
    "GCI": (49.4347, -2.6019),   # Guernsey
    "ACI": (49.7061, -2.2147),   # Alderney
    "BHD": (54.6181, -5.8725),   # Belfast City
    "BFS": (54.6575, -6.2158),   # Belfast International
    "DUB": (53.4213, -6.2701),   # Dublin
    "EDI": (55.9508, -3.3615),   # Edinburgh
    "GLA": (55.8642, -4.4331),   # Glasgow
    "NCL": (55.0375, -1.6917),   # Newcastle
    "AMS": (52.3086, 4.7639),    # Amsterdam Schiphol
    "ORY": (48.7233, 2.3794),    # Paris Orly
    "FAO": (37.0144, -7.9659),   # Faro
}


def haversine_miles(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(EARTH_RADIUS_MILES * c, 1)


def bearing_degrees(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def bearing_difference(a, b):
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def fetch_nearby_aircraft():
    """One snapshot of every aircraft adsb.lol currently reports within
    ADSBLOL_RADIUS_NM of Southampton Airport, shared by every flight's
    match_flight_position() call this run. This is a bonus enhancement
    layered on the primary southamptonairport.com feed, so a failure here
    must not fail the whole fetch_airport run — isolated and logged, an
    empty list just means no flight gets a live distance this run."""
    try:
        payload = json.loads(fetch_text(
            ADSBLOL_POINT_URL.format(lat=AIRPORT_LAT, lon=AIRPORT_LON, radius=ADSBLOL_RADIUS_NM)
        ))
    except Exception as exc:  # noqa: BLE001 - isolate this from the rest of the run
        print(f"adsb.lol nearby-aircraft lookup failed: {exc}", file=sys.stderr)
        return []
    return payload.get("ac") or []


DEPARTURE_TIME_RE = re.compile(r"Airborne (\d{2}):(\d{2})")


def estimate_progress_distance(arriving, flight_time, status, route_distance, now):
    """How far from Southampton (in miles) a flight should plausibly be
    right now, estimated from elapsed/remaining time rather than any live
    signal — used only to narrow down which live aircraft could be this
    flight (see match_flight_position). now, flight_time are naive
    datetimes in the same clock as the southamptonairport.com feed itself:
    UK local time (BST/GMT), not UTC — confirmed live on 2026-08-23 when an
    "Airborne 12:40" status (BST) showed up in a 12:04 UTC fetch, which is
    only sane if that 12:40 is local (13:40 BST would be in the future;
    12:40 BST = 11:40 UTC, safely in the past). Getting this wrong silently
    breaks every departure estimate: a takeoff time misread as UTC reads as
    up to an hour in the future, elapsed time clamps to ~0, and the search
    window collapses to "still at the gate" even for a flight that's been
    airborne for a while.

    For an arrival, flight_time is the board's current ETA: however long is
    left until then, at ASSUMED_CRUISE_MPH, is however much of the route
    should still be ahead of it. For a departure, the actual takeoff time
    has to be parsed out of the status text itself (flight_time there is
    only the scheduled departure, which "Airborne HH:MM" may differ from);
    if it can't be parsed, there's nothing to estimate from. A departure
    whose estimated progress already reaches the destination is treated as
    landed — southamptonairport.com never updates a departure's status past
    "Airborne", so without this cutoff every long-since-landed flight would
    keep being (mis)attempted run after run."""
    if arriving:
        remaining_minutes = max((flight_time - now).total_seconds() / 60, 0)
        distance = remaining_minutes / 60 * ASSUMED_CRUISE_MPH
    else:
        match = DEPARTURE_TIME_RE.search(status)
        if not match:
            return None
        takeoff = flight_time.replace(hour=int(match.group(1)), minute=int(match.group(2)), second=0)
        elapsed_minutes = max((now - takeoff).total_seconds() / 60, 0)
        distance = elapsed_minutes / 60 * ASSUMED_CRUISE_MPH
        if distance >= route_distance * 0.95:
            return None  # plausibly already landed — don't bother attempting a match

    return min(distance, route_distance)


def match_flight_position(nearby_aircraft, airline, other_code, expected_progress_distance):
    """Picks the aircraft among nearby_aircraft that's the best plausible
    match for this flight: same airline (by ADS-B callsign prefix — see
    AIRLINE_ICAO_PREFIXES), on roughly the right bearing from Southampton
    for its route to/from other_code (the flight's destination if it's a
    departure, origin if it's an arrival), AND roughly the right distance
    out for how long it's been flying (expected_progress_distance — see
    estimate_progress_distance). Bearing alone isn't a fine enough filter
    for a busy airline (KLM/Aer Lingus mainline traffic, or easyJet, have
    enough aircraft in UK/European airspace at once that some will share a
    similar bearing from Southampton by pure coincidence); this second,
    independent signal is what actually narrows it down. Returns the best-
    scoring candidate's distance from Southampton in miles, or None if the
    airline/route isn't known or nothing plausible is found nearby."""
    icao_prefix = AIRLINE_ICAO_PREFIXES.get(airline)
    dest_coord = DESTINATION_COORDS.get(other_code)
    if not icao_prefix or not dest_coord:
        return None

    expected_bearing = bearing_degrees(AIRPORT_LAT, AIRPORT_LON, *dest_coord)
    progress_window = max(PROGRESS_TOLERANCE_MIN_MILES, expected_progress_distance * PROGRESS_TOLERANCE_FRACTION)

    best_score, best_distance = None, None
    for aircraft in nearby_aircraft:
        flight = (aircraft.get("flight") or "").strip()
        alt = aircraft.get("alt_baro")
        lat, lon = aircraft.get("lat"), aircraft.get("lon")
        if not flight.startswith(icao_prefix) or alt == "ground" or lat is None or lon is None:
            continue

        distance = haversine_miles(AIRPORT_LAT, AIRPORT_LON, lat, lon)
        distance_error = abs(distance - expected_progress_distance)
        if distance_error > progress_window:
            continue

        bearing = bearing_degrees(AIRPORT_LAT, AIRPORT_LON, lat, lon)
        bearing_error = bearing_difference(bearing, expected_bearing)
        if bearing_error > BEARING_TOLERANCE_DEGREES:
            continue

        score = bearing_error / BEARING_TOLERANCE_DEGREES + distance_error / progress_window
        if best_score is None or score < best_score:
            best_score, best_distance = score, distance

    return best_distance


def build_flight(raw, arriving, nearby_aircraft, now):
    flight = {
        "time": raw["aggregatedDateTime"],
        "scheduled_time": raw["scheduledDateTime"],
        "flight_number": raw["flightNumber"],
        "airline": raw["airlineName"],
        "status": (raw.get("statusMessage") or {}).get("mainMessage") or "",
    }

    status = flight["status"]
    if arriving:
        # "Scheduled" = not yet tracked (still on the ground pre-departure);
        # "Arrived ..." = already landed. Anything else the board reports
        # ("Expected HH:MM", "On Approach", ...) means it has live tracking
        # and hasn't landed yet, so a distance lookup is worth attempting.
        live_lookup_wanted = status != "Scheduled" and not status.startswith("Arrived")
    else:
        # Departures only get an explicit "Airborne HH:MM" once they've
        # actually taken off — ground states ("Scheduled", "Check In Open
        # ...") shouldn't attempt a lookup.
        live_lookup_wanted = status.startswith("Airborne")

    distance_miles = None
    other_code = raw["locationCode"]
    dest_coord = DESTINATION_COORDS.get(other_code)
    if live_lookup_wanted and dest_coord:
        route_distance = haversine_miles(AIRPORT_LAT, AIRPORT_LON, *dest_coord)
        flight_time = datetime.fromisoformat(flight["time"])
        expected_progress = estimate_progress_distance(arriving, flight_time, status, route_distance, now)
        if expected_progress is not None:
            distance_miles = match_flight_position(nearby_aircraft, flight["airline"], other_code, expected_progress)
    flight["distance_miles"] = distance_miles

    if arriving:
        flight["from"] = raw["location"]
        flight["from_code"] = raw["locationCode"]
    else:
        flight["to"] = raw["location"]
        flight["to_code"] = raw["locationCode"]
        desk_from, desk_to = raw.get("checkInDeskFrom"), raw.get("checkInDeskTo")
        if desk_from and desk_to:
            flight["check_in_desk"] = desk_from if desk_from == desk_to else f"{desk_from}-{desk_to}"
        else:
            flight["check_in_desk"] = None
    return flight


def match_rotations(arrivals, departures):
    """Greedily pairs each departure with the earliest still-unclaimed
    arrival that landed at the same place before it departed — modelling
    one aircraft shuttling a route back and forth. See module docstring for
    why this is a heuristic, not a confirmed match."""
    queues = {}
    for arrival in sorted(arrivals, key=lambda a: a["time"]):
        queues.setdefault(arrival["from_code"], []).append(arrival)

    rotations = []
    for departure in sorted(departures, key=lambda d: d["time"]):
        queue = queues.get(departure["to_code"], [])
        candidates = [a for a in queue if a["time"] < departure["time"]]
        if not candidates:
            continue
        arrival = candidates[0]
        queue.remove(arrival)

        turnaround = datetime.fromisoformat(departure["time"]) - datetime.fromisoformat(arrival["time"])
        rotations.append({
            "arrival_flight_number": arrival["flight_number"],
            "arrival_time": arrival["time"],
            "arrival_from": arrival["from"],
            "departure_flight_number": departure["flight_number"],
            "departure_time": departure["time"],
            "departure_to": departure["to"],
            "turnaround_minutes": round(turnaround.total_seconds() / 60),
        })

    return rotations


def main():
    raw = json.loads(fetch_text(FLIGHTS_URL))
    nearby_aircraft = fetch_nearby_aircraft()
    # Naive, matching the feed's own timestamps — UK local time (BST/GMT),
    # not UTC, despite carrying no timezone suffix. See
    # estimate_progress_distance's docstring for how that was confirmed.
    now = datetime.now(ZoneInfo("Europe/London")).replace(tzinfo=None)

    arrivals = sorted(
        (build_flight(a, arriving=True, nearby_aircraft=nearby_aircraft, now=now) for a in raw.get("arrivals", [])),
        key=lambda a: a["time"],
    )
    departures = sorted(
        (build_flight(d, arriving=False, nearby_aircraft=nearby_aircraft, now=now) for d in raw.get("departures", [])),
        key=lambda d: d["time"],
    )
    rotations = match_rotations(arrivals, departures)

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Southampton Airport",
        "arrivals": arrivals,
        "departures": departures,
        "rotations": rotations,
    }
    write_json(CURRENT_PATH, output)

    print(f"Airport board updated: {len(arrivals)} arrivals, {len(departures)} departures, {len(rotations)} inferred rotations")


if __name__ == "__main__":
    run(main, "airport")
