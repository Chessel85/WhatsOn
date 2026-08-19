"""Shared helpers for the fetch scripts. See CLAUDE.md for the pattern each
one follows (fetch → normalize → write data/current/<feed>.json → exit
non-zero on failure)."""
import json
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent

USER_AGENT = "WhatsOn-Southampton-Dashboard/1.0 (personal, non-commercial; https://github.com/Chessel85/WhatsOn)"


def fetch_text(url, **kwargs):
    kwargs.setdefault("timeout", 30)
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    response = requests.get(url, headers=headers, **kwargs)
    response.raise_for_status()
    return response.text


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run(main, label):
    """Call main(), turning any exception into a clean failure message and
    a non-zero exit code so the GitHub Actions run is visibly marked
    failed rather than silently leaving stale data in place."""
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - top-level script guard
        print(f"Failed to fetch {label}: {exc}", file=sys.stderr)
        sys.exit(1)
