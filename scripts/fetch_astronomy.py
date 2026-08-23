#!/usr/bin/env python3
"""Fetch sunrise/sunset/moon-phase data for Southampton from
sunrisesunset.io's free JSON API (api.sunrisesunset.io/json) — no API key
required. Covers today plus the next LOOKAHEAD_DAYS days in a single
request via the API's date_start/date_end range support.

Also computes, rather than fetches, the next Moon perigee/apogee, next
Earth perihelion/aphelion, and next solstice/equinox — these aren't served
by sunrisesunset.io (or any free API found), so they're derived directly
from NASA JPL's DE421 ephemeris via Skyfield, using its documented
distance-extrema recipe (search a window for local minima/maxima of the
relevant body-pair distance) for the apsides, and its built-in
`almanac.seasons` event finder for solstices/equinoxes. This is standard,
well-tested astronomical-library computation rather than a hand-rolled
formula — chosen deliberately over implementing the classic low-precision
Meeus algorithms by hand, since a subtle coefficient bug in a hand-rolled
version could go unnoticed for months (these events are only checkable a
few times a year). The DE421 kernel (~17MB, public domain) is downloaded
once into `scripts/.ephemeris-cache/` (gitignored) and reused on later
runs; the GitHub Actions workflow caches that directory so it isn't
re-downloaded from NASA's server every day.
"""
import json
from datetime import date, datetime, timedelta, timezone

from skyfield.api import Loader, load
from skyfield import almanac
from skyfield.searchlib import find_maxima, find_minima

from _common import REPO_ROOT, fetch_text, run, write_json

LATITUDE = 50.9097
LONGITUDE = -1.4044

LOOKAHEAD_DAYS = 6  # today + 6 = a 7-day window

CURRENT_PATH = REPO_ROOT / "data" / "current" / "astronomy.json"
EPHEMERIS_CACHE_DIR = REPO_ROOT / "scripts" / ".ephemeris-cache"

API_URL = "https://api.sunrisesunset.io/json"

MOON_SEARCH_DAYS = 40  # comfortably covers the ~27.5-day anomalistic month
EARTH_SEARCH_DAYS = 400  # comfortably covers the ~365-day cycle
SEASON_SEARCH_DAYS = 400


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


def iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def days_until(target_dt, now_dt):
    return round((target_dt - now_dt).total_seconds() / 86400)


def next_apsis(ts, t0, search_days, distance_fn, step_days, near_label, far_label, now):
    """Finds whichever comes first, after t0, of a near-extreme (e.g.
    perigee/perihelion) or far-extreme (apogee/aphelion) of distance_fn."""
    t1 = ts.tt_jd(t0.tt + search_days)
    distance_fn.step_days = step_days
    t_min, _ = find_minima(t0, t1, distance_fn)
    t_max, _ = find_maxima(t0, t1, distance_fn)
    candidates = [(t, near_label) for t in t_min] + [(t, far_label) for t in t_max]
    candidates = [c for c in candidates if c[0].tt > t0.tt]
    candidates.sort(key=lambda c: c[0].tt)
    t, label = candidates[0]
    when = t.utc_datetime()
    return {"type": label, "date": iso(when), "days_until": days_until(when, now)}


def next_solstice_equinox(ts, eph, t0, search_days, now):
    t1 = ts.tt_jd(t0.tt + search_days)
    times, kinds = almanac.find_discrete(t0, t1, almanac.seasons(eph))
    when = times[0].utc_datetime()
    return {
        "name": almanac.SEASON_EVENTS[kinds[0]],
        "date": iso(when),
        "days_until": days_until(when, now),
    }


def compute_astronomical_events(now):
    loader = Loader(EPHEMERIS_CACHE_DIR)
    ts = loader.timescale()
    eph = loader("de421.bsp")
    earth, moon, sun = eph["earth"], eph["moon"], eph["sun"]
    t0 = ts.from_datetime(now)

    def moon_distance(t):
        return earth.at(t).observe(moon).distance().km

    def earth_sun_distance(t):
        return sun.at(t).observe(earth).distance().km

    return {
        "moon_apsis": next_apsis(ts, t0, MOON_SEARCH_DAYS, moon_distance, 0.5, "perigee", "apogee", now),
        "earth_apsis": next_apsis(ts, t0, EARTH_SEARCH_DAYS, earth_sun_distance, 5, "perihelion", "aphelion", now),
        "next_solstice_equinox": next_solstice_equinox(ts, eph, t0, SEASON_SEARCH_DAYS, now),
    }


def main():
    days = [build_day(d) for d in fetch_days()]
    now = datetime.now(timezone.utc)

    output = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "source": "https://sunrisesunset.io/",
        "location": "Southampton, UK",
        "days": days,
        **compute_astronomical_events(now),
    }
    write_json(CURRENT_PATH, output)

    today = days[0]
    print(
        f"Astronomy updated: sunrise {today['sunrise']}, sunset {today['sunset']}, "
        f"moon {today['moon_phase']} ({today['moon_illumination_percent']}% illuminated)"
    )


if __name__ == "__main__":
    run(main, "astronomy")
