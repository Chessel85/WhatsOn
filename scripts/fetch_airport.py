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
"""
import json
from datetime import datetime, timezone

from _common import REPO_ROOT, fetch_text, run, write_json

CURRENT_PATH = REPO_ROOT / "data" / "current" / "airport.json"

FLIGHTS_URL = "https://www.southamptonairport.com/Umbraco/api/FlightsApi/RetrieveFlights"


def build_flight(raw, arriving):
    flight = {
        "time": raw["aggregatedDateTime"],
        "scheduled_time": raw["scheduledDateTime"],
        "flight_number": raw["flightNumber"],
        "airline": raw["airlineName"],
        "status": (raw.get("statusMessage") or {}).get("mainMessage") or "",
    }
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

    arrivals = sorted(
        (build_flight(a, arriving=True) for a in raw.get("arrivals", [])),
        key=lambda a: a["time"],
    )
    departures = sorted(
        (build_flight(d, arriving=False) for d in raw.get("departures", [])),
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
