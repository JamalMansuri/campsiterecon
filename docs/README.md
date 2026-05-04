# Campsite Recon — Wiki

Curated per-module pages for future LLMs (and humans) who need to load context fast without re-reading every `.py`.

This wiki sits between the source and a question. Read the page that matches your question, follow links into neighbors, and only drop into source when the wiki page tells you the answer lives there.

## Request flow at a glance

```
Telegram → OpenClaw → main.py
                        │
        ┌───────────────┼──────────────────┐
        │               │                  │
        ▼               ▼                  ▼
 availability.py    search.py          weather.py
        │               │                  │
        └──────┬────────┘                  │
               ▼                           │
         api_client.py ────► Rec.gov / RIDB
                                            │
        parser.py ◄── availability.py       ▼
            │                          open-meteo.com
            ▼
        models.py (data contracts)
            │
            ▼
        stdout JSON ──► OpenClaw ──► Telegram
```

## Modules

| Page | One-line purpose |
|---|---|
| [main.md](main.md) | CLI entry. Loads API key, dispatches to weekend or search mode, prints JSON |
| [api_client.md](api_client.md) | Sole HTTP transport. Three endpoints (RIDB, Rec.gov campground, Rec.gov permit) |
| [availability.md](availability.md) | Weekend-mode dispatcher. Tries campground endpoint, falls back to permit |
| [parser.md](parser.md) | Weekend-mode normalizer. Turns raw API JSON into `CampsiteResult` |
| [search.md](search.md) | Free-text search mode. RIDB lookup + multi-month availability scan |
| [windows.md](windows.md) | Pure date-math primitive. Enumerates viable N-night `(start, checkout)` windows |
| [booker.md](booker.md) | Auto-cart Phase 1+. Playwright session manager — `login`, `health`, soon `cart` |
| [weather.md](weather.md) | Open-Meteo Fri/Sat/Sun forecast. Weekend mode only |
| [config.md](config.md) | Hardcoded preset locations + facility/permit IDs |
| [models.md](models.md) | Pydantic models that define every JSON shape the program emits |

## Attribution & prior art

| Page | What it covers |
|---|---|
| [camply-attribution.md](camply-attribution.md) | Borrowed: `RawCampgroundResponse`/`RawSiteAvailability` shapes + the unavailable-status denylist. No runtime dep |
| [banool-attribution.md](banool-attribution.md) | Borrowed: the `consecutive_nights` algorithm powering [windows.md](windows.md). No runtime dep |
| [auto-cart-mvp-plan.md](auto-cart-mvp-plan.md) | The Playwright auto-cart MVP plan + Phase tracker |

## Where to start by question

- **"How does the program decide between modes?"** → [main.md](main.md)
- **"Why doesn't search mode find Point Reyes?"** → [search.md](search.md), then [parser.md](parser.md) for the permit-vs-campground URL distinction
- **"Where does the API key come from?"** → [main.md](main.md) (the `_get_api_key` section)
- **"How do I add a new preset location?"** → [config.md](config.md)
- **"What's the JSON shape OpenClaw consumes?"** → [models.md](models.md)
- **"Which endpoints does this hit and what auth do they need?"** → [api_client.md](api_client.md)
- **"Why is Mode 1 weather-aware but Mode 2 isn't?"** → [weather.md](weather.md), [search.md](search.md)

## What's intentionally NOT in this wiki

- Code that's already self-explanatory (signatures, control flow you can read in 10 seconds).
- The CLI usage examples — those live in [../README.md](../README.md).
- The OpenClaw skill behavior — that's [../SKILL.md](../SKILL.md).
- API response field-by-field schemas — those live in [../references/api-response-shapes.md](../references/api-response-shapes.md).

The wiki is the connective tissue. The README is the entry point for users; SKILL.md is the entry point for the LLM at runtime; this wiki is the entry point for an LLM (or dev) who needs to *modify* the program.
