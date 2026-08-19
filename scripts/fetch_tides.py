#!/usr/bin/env python3
"""Fetch tide predictions for Southampton via EasyTide's internal prediction
endpoint — the same one https://easytide.admiralty.co.uk itself calls.

This is not a documented/versioned public API; it was found by reading
EasyTide's frontend JS (js/olmap.js -> GetPredictionData). No signup or API
key is needed, which is why it's used here instead of the official ADMIRALTY
UK Tidal API (that one requires a developer-portal signup the maintainer
chose to skip). Because it's undocumented, Admiralty could change or remove
it without notice — if this script starts failing, first check whether
https://easytide.admiralty.co.uk/?PortID=0062 still works in a browser
before assuming the script itself is broken.
"""
from datetime import datetime, timezone

import requests

from _common import REPO_ROOT, USER_AGENT, run, write_json

STATION_ID = "0062"  # Southampton — see https://easytide.admiralty.co.uk/?PortID=0062
STATION_NAME = "Southampton"

CURRENT_PATH = REPO_ROOT / "data" / "current" / "tides.json"

PREDICTION_URL = "https://easytide.admiralty.co.uk/Home/GetPredictionData"

EVENT_LABELS = {
    0: "High tide",  # HighWater, per EasyTide's js/tidalTable.js
    1: "Low tide",   # LowWater
}

# Spring tides (bigger range) occur at new and full moon; neap tides
# (smaller range) at the quarter moons in between. This derives where we
# are in that cycle purely from the Moon's astronomical phase — it is NOT
# read from actual predicted tide heights (those are only available a few
# days out from this source), so it's an approximation: real spring/neap
# extremes typically lag the exact new/full/quarter moon by a day or two
# due to ocean/coastline inertia ("tidal priming/lag").
SYNODIC_MONTH_DAYS = 29.530588861
REFERENCE_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)


def tidal_cycle_info(now=None):
    now = now or datetime.now(timezone.utc)
    moon_age = (now - REFERENCE_NEW_MOON).total_seconds() / 86400.0 % SYNODIC_MONTH_DAYS

    quarter = SYNODIC_MONTH_DAYS / 4
    reference_points = [
        (0.0, "spring"),            # new moon
        (quarter, "neap"),          # first quarter
        (quarter * 2, "spring"),    # full moon
        (quarter * 3, "neap"),      # last quarter
        (SYNODIC_MONTH_DAYS, "spring"),  # next new moon
    ]

    offset, phase_type = min(reference_points, key=lambda rp: abs(rp[0] - moon_age))
    days_from_now = offset - moon_age  # positive = future, negative = past
    days_rounded = round(abs(days_from_now))

    direction = "today" if days_rounded == 0 else ("until" if days_from_now > 0 else "after")

    return {"type": phase_type, "direction": direction, "days": days_rounded}


def fetch_events():
    response = requests.get(
        PREDICTION_URL,
        params={"stationId": STATION_ID},
        headers={
            "Accept": "application/json",
            "Referer": f"https://easytide.admiralty.co.uk/?PortID={STATION_ID}",
            "User-Agent": USER_AGENT,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    today = datetime.now(timezone.utc).date()

    events = []
    for e in data["tidalEventList"]:
        # EasyTide's dateTime values are GMT baseline (its own UI adds an
        # hour during BST); normalize to a UTC "Z" string so the frontend
        # can do correct local/BST conversion just by using `new Date(...)`.
        dt = datetime.fromisoformat(e["dateTime"]).replace(tzinfo=timezone.utc)
        if dt.date() < today:
            continue  # EasyTide includes a trailing event from the day before
        events.append(
            {
                "event_type": EVENT_LABELS.get(e["eventType"], f"Unknown ({e['eventType']})"),
                "time": dt.isoformat().replace("+00:00", "Z"),
                "height_m": round(e["height"], 2),
            }
        )
    return events


def main():
    events = fetch_events()
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "https://easytide.admiralty.co.uk/",
        "location": STATION_NAME,
        "events": events,
        "tidal_cycle": tidal_cycle_info(),
    }
    write_json(CURRENT_PATH, output)
    print(f"Tides updated: {len(events)} events")


if __name__ == "__main__":
    run(main, "tides")
