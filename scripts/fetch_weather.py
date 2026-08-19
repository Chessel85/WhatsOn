#!/usr/bin/env python3
"""Fetch current + hourly weather for Southampton from Open-Meteo.

Writes data/current/weather.json (overwritten each run) and appends a row
to data/history/weather.csv. No API key required.
"""
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

from _common import REPO_ROOT, run, write_json

LATITUDE = 50.9097
LONGITUDE = -1.4044
TIMEZONE = "Europe/London"
LOCAL_TZ = ZoneInfo(TIMEZONE)
FORECAST_HOURS = 48
RECENT_DAYS = 5

CURRENT_PATH = REPO_ROOT / "data" / "current" / "weather.json"
HISTORY_PATH = REPO_ROOT / "data" / "history" / "weather.csv"

API_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes used by Open-Meteo.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def describe(code):
    return WEATHER_CODES.get(code, f"Unknown ({code})")


COMPASS_POINTS = [
    "North", "Northeast", "East", "Southeast",
    "South", "Southwest", "West", "Northwest",
]


def compass_direction(degrees):
    index = round(degrees / 45) % 8
    return COMPASS_POINTS[index]


def fetch_raw():
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,wind_speed_10m,wind_direction_10m,relative_humidity_2m,weather_code",
        "daily": "daylight_duration,sunshine_duration,precipitation_sum,wind_speed_10m_mean",
        "wind_speed_unit": "mph",
        "timezone": TIMEZONE,
        # 3 days (not 2) so there's still a full 48h of hourly data left
        # after trimming today's already-passed hours below, however late
        # in the day this runs.
        "forecast_days": 3,
        # RECENT_DAYS extra days of daily data before today, for the "last
        # N days" summary. Also pulls in that many extra hourly rows, which
        # the past-hour filter below discards — harmless, just a slightly
        # bigger response.
        "past_days": RECENT_DAYS,
    }
    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def build_output(raw):
    hourly = raw["hourly"]

    current_hour_start = datetime.now(LOCAL_TZ).replace(minute=0, second=0, microsecond=0)

    hourly_out = []
    for i, time in enumerate(hourly["time"]):
        entry_time = datetime.fromisoformat(time).replace(tzinfo=LOCAL_TZ)
        if entry_time < current_hour_start:
            continue  # drop hours that have already passed today
        hourly_out.append(
            {
                "time": time,
                "temperature_c": hourly["temperature_2m"][i],
                "feels_like_c": hourly["apparent_temperature"][i],
                "precipitation_probability": hourly["precipitation_probability"][i],
                "precipitation_mm": hourly["precipitation"][i],
                "wind_speed_mph": hourly["wind_speed_10m"][i],
                "wind_direction": compass_direction(hourly["wind_direction_10m"][i]),
                "humidity_percent": hourly["relative_humidity_2m"][i],
                "condition": describe(hourly["weather_code"][i]),
            }
        )
        if len(hourly_out) >= FORECAST_HOURS:
            break

    # The headline "current conditions" is just the first (nearest-hour)
    # row of the same hourly series used for the table below, rather than
    # Open-Meteo's separate `current` nowcast — those two data sources can
    # legitimately disagree by a degree or so, which reads as a bug.
    current = hourly_out[0]

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "https://open-meteo.com/",
        "location": "Southampton, UK",
        "current": current,
        "hourly": hourly_out,
        "recent_days": build_recent_days(raw["daily"]),
    }


def duration_hm(seconds):
    total_minutes = round(seconds / 60)
    return {"hours": total_minutes // 60, "minutes": total_minutes % 60}


def build_recent_days(daily):
    # The daily series covers RECENT_DAYS days before today, today itself
    # (a partial/in-progress day), and a few forecast days after — we only
    # want the RECENT_DAYS complete days strictly before today.
    today = datetime.now(LOCAL_TZ).date().isoformat()
    today_index = daily["time"].index(today)
    start_index = today_index - RECENT_DAYS

    return [
        {
            "date": daily["time"][i],
            "daylight": duration_hm(daily["daylight_duration"][i]),
            "sunshine": duration_hm(daily["sunshine_duration"][i]),
            "precipitation_mm": daily["precipitation_sum"][i],
            "wind_speed_mph_avg": round(daily["wind_speed_10m_mean"][i]),
        }
        for i in range(start_index, today_index)
    ]


def append_history(data):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not HISTORY_PATH.exists()
    with HISTORY_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                ["fetched_at", "temperature_c", "feels_like_c", "condition", "wind_speed_mph", "precipitation_mm"]
            )
        current = data["current"]
        writer.writerow(
            [
                data["fetched_at"],
                current["temperature_c"],
                current["feels_like_c"],
                current["condition"],
                current["wind_speed_mph"],
                current["precipitation_mm"],
            ]
        )


def main():
    data = build_output(fetch_raw())
    write_json(CURRENT_PATH, data)
    append_history(data)
    print(f"Weather updated: {data['current']['temperature_c']}°C, {data['current']['condition']}")


if __name__ == "__main__":
    run(main, "weather")
