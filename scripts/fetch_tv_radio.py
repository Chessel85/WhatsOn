#!/usr/bin/env python3
"""Fetch new TV/radio series starting in the next 7 days on BBC One, BBC Two,
BBC Three, BBC Four, BBC Radio 4, BBC World Service and ITV1.

Three independent, undocumented sources, each reverse-engineered from what a
normal visitor's browser is served rather than an official public API:

- BBC One/Two/Three/Four: BBC iPlayer's own internal schedule API
  (ibl.api.bbci.co.uk) — the same data the iPlayer guide renders. No key.
- BBC Radio 4 / BBC World Service: BBC's old radio schedule feeds (Nitro/ESS)
  stopped being updated in March 2025. Found instead: the BBC Sounds
  schedule page (bbc.co.uk/sounds/schedules/{station}/YYYY-MM-DD) is a
  Next.js app whose __NEXT_DATA__ blob reveals it calls rms.api.bbc.co.uk
  directly for its schedule data — so this hits that JSON API straight away
  rather than scraping the HTML. Unlike the iPlayer TV data, this endpoint
  doesn't expose a repeat/rerun flag, so a rerun of a series' first episode
  (Radio 4 does sometimes repeat a recent episode in an afternoon slot)
  could produce a false positive here in a way the TV channels can't — a
  real, accepted limitation, not an oversight (see confidence="medium"
  below). World Service in particular is mostly rolling news/strand
  programming with dated episode titles rather than "Series N: Episode M"
  numbering, so it will often legitimately have no matches at all — that's
  expected, not a sign the fetch is broken.
- ITV1: no BBC-iPlayer-style endpoint exists, so this uses TVmaze's public
  GB schedule instead. Structurally weaker signal than the BBC sources
  (no text/rerun signal, just "episode number 1") — flagged "low" confidence
  in the output and captioned as such on the detail page.

"New series starting" detection is a heuristic in all cases, tuned against
real BBC schedule data during development (see looks_like_new_series_bbc and
looks_like_new_series_radio). It is not guaranteed to be perfectly precise
or complete — see CLAUDE.md for the maintenance expectations that come with
using undocumented endpoints like these.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from _common import REPO_ROOT, fetch_text, run, write_json

WINDOW_DAYS = 7

CURRENT_PATH = REPO_ROOT / "data" / "current" / "tv_radio.json"

IBL_SCHEDULE_URL = "https://ibl.api.bbci.co.uk/ibl/v1/channels/{channel}/schedule/{date}"

# Region choice doesn't matter here — new series premiere dates/times don't
# vary by English region, only local opt-outs (e.g. regional news) do, and
# this feed only ever looks at series/episode metadata, never those opt-outs.
BBC_TV_CHANNELS = [
    {"id": "bbc_one", "name": "BBC One", "iplayer_id": "bbc_one_london"},
    {"id": "bbc_two", "name": "BBC Two", "iplayer_id": "bbc_two_england"},
    {"id": "bbc_three", "name": "BBC Three", "iplayer_id": "bbc_three"},
    {"id": "bbc_four", "name": "BBC Four", "iplayer_id": "bbc_four"},
]

RADIO_SCHEDULE_API = "https://rms.api.bbc.co.uk/v2/experience/inline/schedules/{station}/{date}"

# rms_id values confirmed against bbc.co.uk/sounds/schedules' own station
# list — note bbc_radio_fourfm, not the more obvious bbc_radio_four (404s).
BBC_RADIO_STATIONS = [
    {"id": "radio_4", "name": "BBC Radio 4", "rms_id": "bbc_radio_fourfm"},
    {"id": "world_service", "name": "BBC World Service", "rms_id": "bbc_world_service"},
]

TVMAZE_SCHEDULE_URL = "https://api.tvmaze.com/schedule"
ITV_NETWORK_NAME = "ITV1"


def dates_in_window(days=WINDOW_DAYS):
    today = datetime.now(timezone.utc).date()
    return [(today + timedelta(days=i)).isoformat() for i in range(days)]


def normalize_time(value):
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def looks_like_new_series_bbc(subtitle, repeat):
    """BBC iPlayer subtitles look like "Series 6: Edinburgh: Episode 1" or
    "Series 1: 15. Bangor" (series N, then either "Episode M" or "M. Title").
    A rerun never counts, even if it happens to be a series' first episode —
    only the first *original* broadcast is "starting"."""
    if repeat or not subtitle:
        return False, None

    match = re.match(r"^Series\s+(\d+):\s*(.*)$", subtitle.strip(), re.I)
    if not match:
        return False, None

    series_number = int(match.group(1))
    remainder = match.group(2).strip()
    is_first_episode = bool(re.search(r"\bEpisode\s+1\b", remainder, re.I)) or bool(
        re.match(r"^1\.\s", remainder)
    )
    if not is_first_episode:
        return False, None

    return True, series_number


def fetch_bbc_tv_channel(iplayer_id):
    entries = []
    for date in dates_in_window():
        url = IBL_SCHEDULE_URL.format(channel=iplayer_id, date=date)
        payload = json.loads(fetch_text(url))
        elements = payload.get("schedule", {}).get("elements", [])
        for element in elements:
            episode = element.get("episode")
            if not episode:
                continue
            matched, series_number = looks_like_new_series_bbc(
                episode.get("subtitle"), element.get("repeat", False)
            )
            if not matched:
                continue

            synopses = episode.get("synopses") or {}
            episode_id = episode.get("id")
            entries.append(
                {
                    "title": episode.get("title"),
                    "series_number": series_number,
                    "start_time": normalize_time(element.get("scheduled_start")),
                    "synopsis": synopses.get("medium") or synopses.get("small"),
                    "url": f"https://www.bbc.co.uk/iplayer/episode/{episode_id}" if episode_id else None,
                }
            )
    return entries


def looks_like_new_series_radio(secondary, tertiary):
    """BBC radio (Radio 4 / World Service) schedule entries carry a
    "secondary"/"tertiary" title pair with no fixed format across strands —
    observed live: "Series 12" / "Hypatia"; "Central Intelligence: Series 3"
    / "Episode 7"; "Series 1" / "4. The Fundraiser"; "Episode 1" / "" (serial
    dramas with no series numbering at all, still a genuine premiere). Look
    for an explicit "Episode N" anywhere, or else a leading "N." on the
    episode title, and treat N == 1 as a new series/programme starting;
    series number (if any) comes from a separate "Series N" search on
    secondary only, independent of whether that's what carried the episode
    number."""
    combined = f"{secondary or ''} {tertiary or ''}"
    episode_match = re.search(r"Episode\s+(\d+)", combined, re.I)
    if episode_match:
        episode_number = int(episode_match.group(1))
    else:
        leading_match = re.match(r"^(\d+)\.", (tertiary or "").strip())
        episode_number = int(leading_match.group(1)) if leading_match else None

    if episode_number != 1:
        return False, None

    series_match = re.search(r"Series\s+(\d+)", secondary or "", re.I)
    series_number = int(series_match.group(1)) if series_match else None
    return True, series_number


def fetch_bbc_radio_station(rms_id):
    entries = []
    for date in dates_in_window():
        url = RADIO_SCHEDULE_API.format(station=rms_id, date=date)
        payload = json.loads(fetch_text(url))
        modules = payload.get("data", [])
        items = modules[0].get("data", []) if modules else []
        for item in items:
            titles = item.get("titles") or {}
            matched, series_number = looks_like_new_series_radio(
                titles.get("secondary"), titles.get("tertiary")
            )
            if not matched:
                continue

            synopses = item.get("synopses") or {}
            playable_id = (item.get("playable_item") or {}).get("id")
            entries.append(
                {
                    "title": titles.get("primary"),
                    "series_number": series_number,
                    "start_time": normalize_time(item.get("start")),
                    "synopsis": synopses.get("medium") or synopses.get("short"),
                    "url": f"https://www.bbc.co.uk/sounds/play/{playable_id}" if playable_id else None,
                }
            )
    return entries


def fetch_itv_new_series():
    entries = []
    for date in dates_in_window():
        url = f"{TVMAZE_SCHEDULE_URL}?country=GB&date={date}"
        for item in json.loads(fetch_text(url)):
            show = item.get("show") or {}
            network = show.get("network") or {}
            if network.get("name") != ITV_NETWORK_NAME:
                continue
            if item.get("number") != 1:
                continue

            summary_html = item.get("summary") or ""
            synopsis = BeautifulSoup(summary_html, "html.parser").get_text(strip=True)
            entries.append(
                {
                    "title": show.get("name"),
                    "series_number": item.get("season"),
                    "start_time": normalize_time(item.get("airstamp")),
                    "synopsis": synopsis or None,
                    "url": item.get("url"),
                }
            )
    return entries


def build_channel(channel_id, name, channel_type, confidence, entries):
    deduped = {(e["title"], e["series_number"]): e for e in entries}
    new_series = sorted(deduped.values(), key=lambda e: e["start_time"] or "")
    return {
        "id": channel_id,
        "name": name,
        "type": channel_type,
        "confidence": confidence,
        "new_series": new_series,
    }


def safe_fetch(label, fetch_fn, *args):
    """Seven independent upstream channels feed this one feed — unlike
    every other fetch script here, one source breaking shouldn't blank out
    the rest."""
    try:
        return fetch_fn(*args)
    except Exception as exc:  # noqa: BLE001 - isolate one source's failure from the rest
        print(f"{label} schedule unavailable, skipping: {exc}", file=sys.stderr)
        return []


def main():
    channels = []
    for channel in BBC_TV_CHANNELS:
        entries = safe_fetch(channel["name"], fetch_bbc_tv_channel, channel["iplayer_id"])
        channels.append(build_channel(channel["id"], channel["name"], "tv", "high", entries))

    for station in BBC_RADIO_STATIONS:
        entries = safe_fetch(station["name"], fetch_bbc_radio_station, station["rms_id"])
        channels.append(build_channel(station["id"], station["name"], "radio", "medium", entries))

    itv_entries = safe_fetch("ITV1", fetch_itv_new_series)
    channels.append(build_channel("itv1", "ITV1", "tv", "low", itv_entries))

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "BBC iPlayer schedule API, BBC Sounds schedules, TVmaze",
        "window_days": WINDOW_DAYS,
        "channels": channels,
    }
    write_json(CURRENT_PATH, output)
    for channel in channels:
        print(f"{channel['name']}: {len(channel['new_series'])} new series")


if __name__ == "__main__":
    run(main, "TV & radio new series")
