# CLAUDE.md — campsitescout

Operational guide for working in this repo. README is for users; this file is for the LLM.

## What this is

Small Python CLI + OpenClaw skill that polls Recreation.gov availability and pushes openings to Telegram. Three modes:

1. **Weekend recon** — preset Bay Area / Central CA locations + Open-Meteo weather. `python main.py [--location KEY] [--date YYYY-MM-DD]`.
2. **Free-text search** — `python main.py --search "Yosemite" --start YYYY-MM-DD --end YYYY-MM-DD`. RIDB lookup → multi-month availability scan. No weather.
3. **Watch (cron)** — orchestration, not a CLI flag. Cron wraps `--search` with `jq -e '.results | length > 0'` gating notifications. Walkthrough in [SKILL.md](SKILL.md) Mode 3.

Plus a maintenance mode: `python main.py --verify` checks every preset id against RIDB + Rec.gov (exit 1 on any mismatch).

All three emit JSON consumed by OpenClaw → Telegram.

## Where to look first

- [docs/README.md](docs/README.md) — wiki index. One curated page per module under [recon/](recon/). Read this before exploring source.
- [docs/auto-cart-mvp-plan.md](docs/auto-cart-mvp-plan.md) — canonical plan for the in-flight Playwright auto-cart extension. Phase tracker lives here.
- [docs/camply-attribution.md](docs/camply-attribution.md) and [docs/banool-attribution.md](docs/banool-attribution.md) — what was borrowed (and what was deliberately *not* borrowed) from prior art.
- [SKILL.md](SKILL.md) — OpenClaw runtime instructions. Public-facing for the LLM at runtime.

## Invariants — don't break these

1. **Never add a facility id, permit id, or rec-area id from memory.** Look it up on RIDB, add it to [recon/config.py](recon/config.py) or [references/facility-ids.md](references/facility-ids.md), then run `python main.py --verify`. The September 2026 "broken links" bug was entirely LLM-hallucinated ids (Point Reyes presets pointed at campgrounds in Utah and Washington; the reference doc was ~60% fabricated). [recon/verify.py](recon/verify.py) checks distance-from-preset, RIDB type, and loop existence; a new preset that fails it is wrong, not the check.
2. **Denylist, not allowlist.** Use `is_available(status)` from [recon/models.py](recon/models.py). Rec.gov's `"Open"` is **not** bookable (walk-up only). Also apply `is_bookable_site()` (drops `hide_external` and day-use sites). Reason in [docs/camply-attribution.md](docs/camply-attribution.md).
3. **Point Reyes is one facility (233359) with loops, not four facilities and not a permit.** `Camp.loop` restricts a preset to campsites whose `loop` matches. Keep the permit-URL rule in `_reservation_url` (keyed off `camp.permit_id`) — no preset uses it today, but it is the correct rule for any future permit camp.
4. **`sites_by_id` and `windows_by_site_id` are durable** on `CampsiteResult`. The Phase 3 auto-cart matcher reads them. Add fields additively; don't drop these. `site_details` (per-site label + deep link) is keyed by the same campsite_id.
5. **All Rec.gov URLs come from the three builders in [recon/parser.py](recon/parser.py)** (`campground_url`, `site_url`, `permit_url`). SKILL.md forbids the runtime LLM from constructing links; don't reintroduce a second place that formats them.
6. **No runtime deps on `camply` or `banool/recreation-gov-campsite-checker`.** Borrowed patterns are documented in their attribution docs. Port + attribute, don't `pip install`.
7. **`urllib`, not `requests`.** Don't randomize User-Agent. The auto-cart context cares about session signals under Akamai; switching HTTP clients or flipping UA would actively hurt.
8. **`recon/api_client.py` swallows network errors** by returning `None` — intentional for cron, and it must catch *everything* (`OSError`, `http.client.HTTPException`, `ValueError`), not just `HTTPError`. But failures must be *visible in the JSON*: `unreachable[]` and `warnings[]` on both report types, with the reason (404 = wrong id, 400 = bad date). The first 429 trips `rate_limited` and writes a 10-minute cooldown to `~/.campsitescout/rate_limit.json` that later runs honour — the block is per-IP and every early request extends it, so never add "retry sooner" logic. `--debug` / `CAMPSITESCOUT_DEBUG=1` prints the swallowed errors.
9. **Weather never aborts a run.** `fetch_weekend_weather` returns `{}` on any failure or null-padded day. It is decoration.
10. **Only RIDB needs the API key** (search, verify). Weekend mode must work without one and under cron (no `$USER`). On the Mac mini the key's source of truth is 1Password; `deploy/fetch_ridb_key.sh` caches it to `~/.campsitescout/ridb_api_key` and `main.py` reads that file first. **Never call `op` from `main.py` or any request path** — on that box it hangs rather than fails and leaked `op daemon`s caused a 55-day outage.

## Architecture

```
main.py
  ├─ weekend mode → availability.py → api_client.py → parser.py → models.py
  ├─ search mode  → search.py        ↗                ↗ (collect_open_sites, URL builders)
  ├─ --verify     → verify.py        ↗
  └─ weekend only → weather.py
                    windows.py — consecutive_nights() primitive, used by parser + search
```

Key types in [recon/models.py](recon/models.py): `CampsiteResult`, `LocationReport`, `SearchResult`, `SearchReport`, `VerifyReport`, plus boundary-validation `RawCampgroundResponse` / `RawSiteAvailability` / `RawPermitDivision`.

## Auto-cart MVP status

In flight. Plan at [docs/auto-cart-mvp-plan.md](docs/auto-cart-mvp-plan.md).

- ✅ **Phase 0 + 0.5 done**: Pydantic boundary, `sites_by_id`, denylist, `consecutive_nights` ported into [recon/windows.py](recon/windows.py), `windows_by_site_id` field added.
- ✅ **Phase 1 closed (2026-05-03)**: [recon/booker.py](recon/booker.py) `login` + `health` validated live. `heartbeat` **deferred** (not rejected). See [docs/booker.md](docs/booker.md) and plan §4.3.
- Phases 2–5: core booker `cart` command → `targets.json` matcher → shell wiring → hardening.

Stack decisions locked: Playwright sync API + headless Chromium, `~/.campsitescout/rec_gov_session.json` `storage_state`, captcha → screenshot → Telegram for human solve. Mac mini host, residential IP, no cloud/proxies.

## Deployment reality

Production is **not** this checkout. It is `/Users/jambot/.openclaw/workspace/campsiterecon` on the Mac mini (a separate clone with local edits) plus `~/.openclaw/workspace/skills/campsite-recon/SKILL.md`, which OpenClaw loads. Nothing here is live until the commit is on `main` with green CI and the box's LaunchAgent ([deploy/auto_deploy.sh](deploy/auto_deploy.sh) → [deploy_jambot.sh](deploy_jambot.sh)) has picked it up and restarted the gateway — see [docs/deploy.md](docs/deploy.md). Never add a self-hosted Actions runner while this repo is public. SKILL.md is path-agnostic (`<REPO>`) for that reason — keep it so. Both Macs share one residential IP and therefore one Rec.gov 429 budget; never schedule overlapping scans.

## Tests and smoke tests

- Unit tests (offline, fixture-driven, <1 s): `.venv/bin/python -m pytest -q tests`. Fixtures under [tests/fixtures/](tests/fixtures/) are trimmed real responses; refresh them if Rec.gov changes shape. `tests/test_main.py` spawns the CLI for argument validation.
- Preset ids: `python main.py --verify` — must print `"ok": true`. Offline, `tests/test_presets_offline.py` checks the same thing against `tests/fixtures/presets/directory.json`; adding a preset means refreshing that fixture (snippet in [docs/verify.md](docs/verify.md)).
- Weekend mode, loop case: `python main.py --location point_reyes` — four sites all with `facility_id` 233359, distinct `loop`, `official_name` "Point Reyes National Seashore Campground".
- Weekend mode, single-day case: `python main.py --location pinnacles` — `sites_by_id` populated, `windows_by_site_id` empty when only one night is open.
- Search mode: `python main.py --search "Yosemite" --start 2026-10-01 --end 2026-10-15` — `anchor` "Yosemite National Park", `facilities_total` ≈ 43, a few far keyword matches in `skipped_far`, Upper/Lower/North Pines scanned (they may simply be full), each result carrying `rec_area` + `distance_km`, sorted nearest-first.
- Site types: `--search "Point Reyes"` results exclude the Tomales Bay boat-in and the `* GROUP` sites by default and report them in `excluded_open_sites`; `--all-site-types` brings them back. Weekend mode never filters by type.
- Month boundary: `python main.py --location pinnacles --date 2026-10-30` — nights Oct 30/31 + Nov 1; no `warnings` about a missing month.
- Validate JSON shape: pipe any of the above through `python -m json.tool`.
- If everything comes back `unreachable`, run with `--debug`: Rec.gov's availability endpoint answers HTTP 429 to bursts (it did during the 2026-09-20 investigation); wait a few minutes.

## Conventions

- Pydantic over dataclasses (boundary validation, `model_dump(mode="json")`, `extra="ignore"` for the undocumented Rec.gov endpoint).
- Native `date` inside modules; ISO strings only at the JSON boundary.
- [recon/](recon/) is the package; [main.py](main.py) is a thin dispatcher with no business logic beyond mode routing + API-key resolution.
- Wiki docs in [docs/](docs/) mirror modules 1:1. When a module's behavior changes, update its `.md` page (and [SKILL.md](SKILL.md) if the JSON shape changed).
- Secrets never go in tracked files. The old packaged `campsite-scout.skill` zip carried a plaintext RIDB key and was removed on 2026-09-20; the key it contained should be treated as public.

## When extending this repo

- **New preset location** → edit only [recon/config.py](recon/config.py), then `--verify`. California State Parks are on ReserveCalifornia, not Rec.gov — they cannot be presets.
- **New JSON field** → `recon/models.py` + the producing module + [SKILL.md](SKILL.md) (the OpenClaw skill needs to know it exists) + the wiki page + a test.
- **New CLI mode** → start by reading [docs/README.md](docs/README.md) and the dispatch logic in [main.py](main.py). Existing pattern: `main.py` routes to a top-level function in a `recon/X.py` module that returns a Pydantic model.
- **Auto-cart / booker work** → read [docs/auto-cart-mvp-plan.md](docs/auto-cart-mvp-plan.md) first. Don't re-design from scratch.
