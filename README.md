# Campsite Recon — Recreation.gov availability CLI + OpenClaw skill

A small Python CLI and OpenClaw skill that checks **Recreation.gov campsite and wilderness-permit availability** for any US campground, pairs it with a Fri/Sat/Sun weather forecast, and surfaces openings in Telegram. Built on the public RIDB directory API plus Recreation.gov's internal availability endpoints, with a cron watch mode that notifies you only when sites actually open.

**Three modes:**

1. **Weekend recon** — preset Bay Area / Central California locations (Point Reyes hike-in camps, Big Sur, Pinnacles, Kings Canyon, Sequoia) for the upcoming weekend, with weather (Recreation.gov + Open-Meteo).
2. **Free-text search** — any location (e.g. "Yosemite", "Tahoe", "Joshua Tree", "Zion") over an arbitrary date range, no weather. For planning trips months ahead.
3. **Watch (cron)** — daily check of a specific location with a rolling date window. Notifies only when sites open; silent otherwise. Full install walkthrough in [SKILL.md](SKILL.md) Mode 3.

All three output structured JSON consumed by OpenClaw → Telegram.

## What it answers

Typical queries, phrased how a user would actually type them:

- "Any campsites open in Point Reyes this weekend?"
- "Find me an open Yosemite campground over July 4th"
- "Check Big Sur next weekend and tell me the weather"
- "Watch Sequoia daily and ping me when a site opens up"
- "Is Coast Camp open Saturday night?"
- "Is Kirk Creek bookable Sat+Sun?"

If you're looking to monitor Recreation.gov availability from the command line — or to drop that ability into an LLM agent loop (OpenClaw, Claude Code, any shell-capable agent) and pipe the results into Telegram — this repo is the minimum viable version.

Recreation.gov has no public POST/PATCH endpoints, so **this tool cannot book sites for you**. It's read-only surveillance: poll availability, surface openings, let the human click through to book. Their iOS app has a native watch feature; this CLI replicates that inside an LLM/Telegram workflow so the same loop can handle free-text queries, cron polling, and weather in one place.

---

## How it works

```mermaid
flowchart LR
    TG["Telegram"] --> OC["OpenClaw"]
    OC -->|shell exec| CLI["main.py"]
    CRON["cron<br/>(Mode 3)"] -->|daily, rolling window| CLI

    CLI -->|weekend mode| CFG["config.py"]
    CLI -->|search mode| SR["search.py"]
    CLI --> WX["weather.py"]

    CFG --> AV["availability.py"]
    AV --> AC["api_client.py"]
    SR --> AC

    AC <--> REC[("recreation.gov")]
    AC <--> RIDB[("ridb.recreation.gov")]
    WX <--> MET[("open-meteo.com")]

    AV --> PR["parser.py"]
    PR --> MDL["models.py"]
    SR --> MDL
    WX --> MDL
    MDL --> CLI

    CLI -.->|stdout JSON| OC
    OC -.->|reply| TG

    CLI -.->|stdout JSON| JQ{"jq gate<br/>results &gt; 0?"}
    JQ -.->|yes| NTF["osascript notification"]

    classDef skill fill:none,stroke:#f59e0b,stroke-width:3px,stroke-dasharray:5 3;
    class CRON,JQ,NTF skill;
```

Nodes with the dashed amber border (`cron`, `jq gate`, `osascript notification`) are shell orchestration configured by [SKILL.md](SKILL.md) Mode 3 — not Python code. The cron line just re-uses `main.py --search` on a schedule and gates the notification on non-empty results.

## Modules

Each row links to source and to a per-module wiki page. The wiki ([docs/](docs/)) is the curated, navigable layer for LLMs (and devs) who want context without reading every file — start at [docs/README.md](docs/README.md).

| File | Wiki | Responsibility |
|---|---|---|
| [main.py](main.py) | [docs/main.md](docs/main.md) | CLI entry point. Loads API key, routes between weekend + search modes, prints JSON to stdout |
| [recon/api_client.py](recon/api_client.py) | [docs/api_client.md](docs/api_client.md) | HTTP transport. Rec.gov availability endpoints + RIDB facility search. Knows nothing about campsites |
| [recon/availability.py](recon/availability.py) | [docs/availability.md](docs/availability.md) | Weekend mode: decides which endpoint to call, attaches Rec.gov's facility metadata |
| [recon/parser.py](recon/parser.py) | [docs/parser.md](docs/parser.md) | Weekend mode: transforms raw responses into `CampsiteResult`, flags contiguous nights, guards permit URLs |
| [recon/search.py](recon/search.py) | [docs/search.md](docs/search.md) | Search mode: RIDB query → facility list → multi-month availability scan → `SearchReport` |
| [recon/windows.py](recon/windows.py) | [docs/windows.md](docs/windows.md) | Pure date primitive — enumerates viable N-night `(start, checkout)` windows. Used by parser, search, and the future auto-cart matcher |
| [recon/weather.py](recon/weather.py) | [docs/weather.md](docs/weather.md) | Fetches Fri/Sat/Sun forecast from Open-Meteo. Returns `WeatherDay` per day |
| [recon/config.py](recon/config.py) | [docs/config.md](docs/config.md) | Preset location definitions with verified facility IDs (and `loop` for multi-camp facilities). Add new presets here only |
| [recon/verify.py](recon/verify.py) | [docs/verify.md](docs/verify.md) | `--verify`: checks every preset id against RIDB + Rec.gov |
| [recon/models.py](recon/models.py) | [docs/models.md](docs/models.md) | Data contracts — `CampsiteResult`, `WeatherDay`, `LocationReport`, `SearchResult`, `SearchReport` |
| [SKILL.md](SKILL.md) | — | OpenClaw skill definition — copy to `~/.openclaw/skills/campsite-recon/` |

## Supported preset locations

| Key | Location |
|---|---|
| `point_reyes` | Point Reyes National Seashore — Sky, Coast, Glen, Wildcat hike-in camps (one Rec.gov campground, four loops) |
| `big_sur` | Big Sur — Kirk Creek, Plaskett Creek, Ponderosa (Los Padres NF) |
| `pinnacles` | Pinnacles National Park |
| `kings_canyon` | Kings Canyon National Park |
| `sequoia` | Sequoia National Park |

To add a preset: look up the facility ID on RIDB (never from memory), add an entry to [recon/config.py](recon/config.py), then run `python main.py --verify` — it cross-checks every preset against RIDB and Rec.gov (id resolves, key word of the name matches, within 150 km of the preset, right type, loop present) and exits 1 on a mismatch.

California State Parks (Pfeiffer Big Sur, Andrew Molera, Limekiln, Mt Tam, Samuel P. Taylor, …) book through ReserveCalifornia, not Recreation.gov, so they can't be presets or search results.

To check a location that isn't a preset, use search mode — no code change required.

## What's next

Proposed features and known follow-ups live in [docs/roadmap.md](docs/roadmap.md): party-size matching, a hot-watch cadence for last-minute cancellations, California State Parks via ReserveCalifornia, smoke/AQI in the forecast, and more. None are built yet.

## Deploying to the Mac mini

Production runs from a separate clone on the JamBot Mac mini, and OpenClaw loads its own copy of `SKILL.md`, so a change is not live until that box has it. The pipeline is: push to `main` → [CI](.github/workflows/ci.yml) runs the offline suite on GitHub → a LaunchAgent on the box ([deploy/auto_deploy.sh](deploy/auto_deploy.sh), every 15 min, outbound only) sees a new green commit → [deploy_jambot.sh](deploy_jambot.sh) fast-forwards, re-tests (rolling back on failure), installs `SKILL.md` → the OpenClaw gateway restarts. One-time setup and the reasoning (why not a self-hosted runner on a public repo) are in [docs/deploy.md](docs/deploy.md).

## Usage

**Weekend mode** — presets + weather:

```bash
# All preset locations, upcoming weekend
python main.py

# Specific preset
python main.py --location point_reyes

# Specific weekend (pass the Friday)
python main.py --location big_sur --date 2026-05-01
```

**Search mode** — arbitrary location + date range, no weather:

```bash
# Yosemite over July 4th weekend
python main.py --search "Yosemite" --start 2026-07-03 --end 2026-07-05

# Cross-month range works too
python main.py --search "Tahoe" --start 2026-07-30 --end 2026-08-02
```

Search mode pages through every RIDB match (RIDB caps pages at 50) and reports where each campground actually is (`rec_area`) — a "Yosemite" search legitimately returns Stanislaus NF and BLM Merced River campgrounds too. Wilderness permits (Yosemite Wilderness, Half Dome) are skipped.

Group and boat-in campsites are skipped by default (they are reported in `excluded_open_sites` / `group_or_boat_only`, never counted as availability); pass `--all-site-types` to include them.

**Verify + debug:**

```bash
# Cross-check every preset facility id against RIDB and Rec.gov; exit 1 on any mismatch
python main.py --verify

# Show the HTTP errors the client normally swallows (e.g. Rec.gov's 429 throttle)
python main.py --debug --location big_sur
```

Failed fetches are never reported as "no availability": both report shapes carry `unreachable[]` and `warnings[]`.

**Watch mode** — cron-driven notifications, only when sites open:

Mode 3 is orchestration rather than a new CLI flag. You wrap the search-mode command in a crontab line that gates notifications on non-empty results with `jq`, so you never see "nothing available" noise — you only hear from it when a site actually opens. Install walkthrough lives in [SKILL.md](SKILL.md) Mode 3; short version:

```bash
# Daily at 8am, scan the next 30 days for Yosemite, notify only when results[] is non-empty.
# One line (crontab has no line continuation); substitute the absolute jq path from `command -v jq`.
0 8 * * * cd /path/to/campsitescout && ./.venv/bin/python main.py --search "Yosemite" --start $(date -v+1d +\%Y-\%m-\%d) --end $(date -v+30d +\%Y-\%m-\%d) 2>>/tmp/campsitescout.err | tee -a /tmp/campsitescout.log | /usr/bin/jq -e '.results | length > 0' >/dev/null && /usr/bin/osascript -e 'display notification "Open sites found for Yosemite" with title "🏕 Campsite Scout"'
```

Swap `osascript` for a `curl` to a Telegram bot's `sendMessage` endpoint to route notifications into chat instead of a macOS banner. Cron only fires while the machine is awake — for 24/7 watching, host this on a server or GitHub Actions.

## OpenClaw setup

```bash
mkdir -p ~/.openclaw/skills/campsite-recon
cp SKILL.md ~/.openclaw/skills/campsite-recon/SKILL.md
```
