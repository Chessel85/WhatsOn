#!/usr/bin/env python3
"""Fetch sunrise/sunset and moon phase data for Southampton from
sunrisesunset.io's free JSON API (api.sunrisesunset.io/json) — no API key
required. Covers today plus the next LOOKAHEAD_DAYS days in a single
request via the API's date_start/date_end range support.
"""
import json
from datetime import date, datetime, timedelta, timezone

from _common import REPO_ROOT, fetch_text, run, write_json

LATITUDE = 50.9097
LONGITUDE = -1.4044

LOOKAHEAD_DAYS = 6  # today + 6 = a 7-day window

CURRENT_PATH = REPO_ROOT / "data" / "current" / "astronomy.json"

API_URL = "https://api.sunrisesunset.io/json"


def duration_hm(seconds):
    total_minutes = round(seconds / 60)
    return {"hours": total_minutes // 60, "minutes": total_minutes % 60}


def fetch_days():
    today = date.today()
    params = {
        "lat": LATITUDE,
        "lng": LONGITUDE,
        "date_start": today.isoformat(),
        "date_end": (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat(),
        "timezone": "UTC",
        "formatted": 0,
    }
    raw = json.loads(fetch_text(API_URL, params=params))
    if raw.get("status") != "OK":
        raise RuntimeError(f"Unexpected API status: {raw.get('status')}")
    return raw["results"]


def build_day(raw):
    return {
        "date": raw["date"],
        "sunrise": raw["sunrise"],
        "sunset": raw["sunset"],
        "day_length": duration_hm(raw["day_length"]),
        # The moon doesn't necessarily rise or set within every 24h window
        # (see the API's moon_always_up/moon_always_down flags), so these
        # can legitimately be null.
        "moonrise": raw.get("moonrise"),
        "moonset": raw.get("moonset"),
        "moon_phase": raw["moon_phase"],
        "moon_illumination_percent": raw["moon_illumination"],
    }


def main():
    days = [build_day(d) for d in fetch_days()]

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "https://sunrisesunset.io/",
        "location": "Southampton, UK",
        "days": days,
    }
    write_json(CURRENT_PATH, output)

    today = days[0]
    print(
        f"Astronomy updated: sunrise {today['sunrise']}, sunset {today['sunset']}, "
        f"moon {today['moon_phase']} ({today['moon_illumination_percent']}% illuminated)"
    )


if __name__ == "__main__":
    run(main, "astronomy")
