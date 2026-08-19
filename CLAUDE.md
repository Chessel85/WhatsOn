# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository has no code yet. It contains a single file, `requirements.txt`, which despite its name is **not** a Python dependency list — it is a prose project brief describing the intended application. There is no build system, test suite, or source tree to document.

## Project brief (from requirements.txt)

The goal is a personal "what's on" dashboard for Southampton, UK, plus selected non-local info. Key constraints stated by the user:

- **Local categories**: weather, tides, cruise ship movements, major roadworks, Southampton FC fixtures, theatre listings, pub live music, city-centre events (free family/music events, marathon/half/10k/5k races).
- **Non-local categories**: new TV/radio series on favourite channels, weather for favourite places abroad, upcoming sporting events.
- **Varying time horizons**: some categories update hourly, others daily/weekly/monthly/yearly; some need historical data stored for comparisons.
- **Data sourcing**: pulled from many external sources for accuracy.
- **Performance**: page must load in a few seconds.
- **Deployment**: local-only, no server to set up/maintain.
- **Update scheduling**: background refresh should run when the machine is idle or a time threshold has passed, but must never add load right at machine startup — a startup delay is required.
- **Platform**: Windows 11.

When starting implementation, treat the above as the source requirements and confirm architectural decisions (data storage format, scheduling mechanism, tech stack for a serverless local page) with the user before assuming defaults, since none have been chosen yet.
