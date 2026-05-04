# CLAUDE.md — campsitescout

Operational guide for working in this repo. README is for users; this file is for the LLM.

## What this is

Small Python CLI + OpenClaw skill that polls Recreation.gov availability and pushes openings to Telegram. Three modes:

1. **Weekend recon** — preset Bay Area / Central CA locations + Open-Meteo weather. `python main.py [--location KEY] [--date YYYY-MM-DD]`.
2. **Free-text search** — `python main.py --search "Yosemite" --start YYYY-MM-DD --end YYYY-MM-DD`. RIDB lookup → multi-month availability scan. No weather.
3. **Watch (cron)** — orchestration, not a CLI flag. Cron wraps `--search` with `jq -e '.results | length > 0'` gating notifications. Walkthrough in [SKILL.md](SKILL.md) Mode 3.

All three emit JSON consumed by OpenClaw → Telegram.

## Where to look first

- [docs/README.md](docs/README.md) — wiki index. One curated page per module under [recon/](recon/). Read this before exploring source.
- [docs/auto-cart-mvp-plan.md](docs/auto-cart-mvp-plan.md) — canonical plan for the in-flight Playwright auto-cart extension. Phase tracker lives here.
- [docs/camply-attribution.md](docs/camply-attribution.md) and [docs/banool-attribution.md](docs/banool-attribution.md) — what was borrowed (and what was deliberately *not* borrowed) from prior art.
- [SKILL.md](SKILL.md) — OpenClaw runtime instructions. Public-facing for the LLM at runtime.

## Invariants — don't break these

1. **Denylist, not allowlist.** Use `is_available(status)` from [recon/models.py](recon/models.py). Rec.gov's `"Open"` is **not** bookable (walk-up only). The full list is `_REC_GOV_UNAVAILABLE_STATUSES`. Reason in [docs/camply-attribution.md](docs/camply-attribution.md).
2. **Permit URL is keyed off `camp.permit_id`, not the response type.** Rec.gov sometimes serves Point Reyes through the campground endpoint, but bookings still flow through `/permits/`. See `_reservation_url` in [recon/parser.py](recon/parser.py).
3. **`sites_by_id` and `windows_by_site_id` are durable** on `CampsiteResult`. The Phase 3 auto-cart matcher reads them. Add fields additively; don't drop these.
4. **No runtime deps on `camply` or `banool/recreation-gov-campsite-checker`.** Borrowed patterns are documented in their attribution docs. If a useful pattern surfaces, port + attribute, don't `pip install`.
5. **`urllib`, not `requests`.** Don't randomize User-Agent. The auto-cart context cares about session signals under Akamai; switching HTTP clients or flipping UA would actively hurt.
6. **`recon/api_client.py` swallows network errors silently** by returning `None`. That's intentional for cron — one bad request shouldn't kill a multi-facility scan. Don't switch to `raise`.

## Architecture

```
main.py
  ├─ weekend mode → availability.py → api_client.py → parser.py → models.py
  ├─ search mode  → search.py        ↗                            ↗
  └─ both         → weather.py (weekend only)
                    windows.py — consecutive_nights() primitive, used by parser + search
```

Key types in [recon/models.py](recon/models.py): `CampsiteResult`, `LocationReport`, `SearchResult`, `SearchReport`, plus boundary-validation `RawCampgroundResponse` / `RawSiteAvailability`.

## Auto-cart MVP status

In flight. Plan at [docs/auto-cart-mvp-plan.md](docs/auto-cart-mvp-plan.md).

- ✅ **Phase 0 + 0.5 done**: Pydantic boundary, `sites_by_id`, denylist, `consecutive_nights` ported into [recon/windows.py](recon/windows.py), `windows_by_site_id` field added.
- ✅ **Phase 1 closed (2026-05-03)**: [recon/booker.py](recon/booker.py) `login` + `health` validated live — saved session survives the headed→headless transition, no captcha on fresh login from residential IP. `heartbeat` **deferred** (not rejected) — periodic 30-min cadence is itself a bot fingerprint and the OSS prior art doesn't actually validate the warming assumption. Revisit only if cron-`health` shows fast session expiry. See [docs/booker.md](docs/booker.md) and plan §4.3.
- Phases 2–5: core booker `cart` command → `targets.json` matcher → shell wiring → hardening.

Stack decisions locked: Playwright sync API + headless Chromium, `~/.campsitescout/rec_gov_session.json` `storage_state`, captcha → screenshot → Telegram for human solve. Mac mini host, residential IP, no cloud/proxies.

## Smoke tests

- Weekend mode, multi-night case: `python main.py --location big_sur --date 2026-06-12` — Plaskett Creek should produce non-empty `windows_by_site_id`.
- Weekend mode, single-day case: `python main.py --location pinnacles` — `sites_by_id` populated, `windows_by_site_id` empty.
- Search mode: `python main.py --search "Yosemite" --start 2026-08-01 --end 2026-08-15` — ~10 results with `contiguous` flags.
- Validate JSON shape: pipe any of the above through `python -m json.tool`.

## Conventions

- Pydantic over dataclasses (boundary validation, `model_dump(mode="json")`, `extra="ignore"` for the undocumented Rec.gov endpoint).
- Native `date` inside modules; ISO strings only at the JSON boundary.
- [recon/](recon/) is the package; [main.py](main.py) is a thin dispatcher with no business logic beyond mode routing + API-key resolution.
- Wiki docs in [docs/](docs/) mirror modules 1:1. When a module's behavior changes, update its `.md` page (and [SKILL.md](SKILL.md) if the JSON shape changed).

## When extending this repo

- **New preset location** → edit only [recon/config.py](recon/config.py). Look up facility/permit IDs on RIDB.
- **New JSON field** → `recon/models.py` + the producing module + [SKILL.md](SKILL.md) (the OpenClaw skill needs to know it exists) + the wiki page.
- **New CLI mode** → start by reading [docs/README.md](docs/README.md) and the dispatch logic in [main.py](main.py). Existing pattern: `main.py` routes to a top-level function in a `recon/X.py` module that returns a Pydantic model.
- **Auto-cart / booker work** → read [docs/auto-cart-mvp-plan.md](docs/auto-cart-mvp-plan.md) first. Don't re-design from scratch.
