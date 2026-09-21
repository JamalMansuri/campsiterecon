# Roadmap — proposed features

> **Status:** proposals only. Nothing on this page is implemented. Written 2026-09-20.
> Auto-cart is not here; it has its own plan in [auto-cart-mvp-plan.md](auto-cart-mvp-plan.md).
> Wiki home: [README.md](README.md)

External facts below were researched on 2026-09-20/21 by reading official docs, live public endpoints and camply's source, then re-checked by a second pass. Where something could not be verified it is listed as an open question, not stated as fact. **Every id on this page was read from a live directory on that date and must still go through `--verify`-style checking before it is used** (CLAUDE.md invariant 1).

## At a glance

| # | Feature | Tier | Effort | Blocked on |
|---|---|---|---|---|
| 1 | Party-size matching (`--party N`) | near-term | hours | nothing |
| 2 | Hot-watch cadence (every 5–10 min, next few days) | near-term | a day or two | watch de-duplication (follow-up A) |
| 3 | ReserveCalifornia (CA State Parks), read-only | near-term, strategic | about a week | a ToS / polling-budget decision |
| 4 | Smoke / AQI in the weather block | near-term | a day or two | nothing |
| 5 | Weather in search mode; arbitrary date range in weekend mode | medium | a day or two | nothing |
| 6 | Amenity + access filtering | medium | about a week | one keyed RIDB request to confirm the payload |
| 7 | First-come-first-served (FCFS) flag | medium | a day or two | three fixtures that don't exist yet |
| 8 | Permit lottery reminders | lower | a day or two | nothing |
| 9 | Drive-time ranking | lower | a day or two | a provider choice + privacy decision |
| 10 | Cancellation-history prediction | lower | multi-week (needs data to accumulate) | #2 |

By effort-to-impact: **#1, #2 and #4 are small and immediately useful. #3 is the strategic one** — it is the biggest coverage hole for a Bay Area tool — but it is a whole second provider.

## Rules every item inherits

- **Rec.gov's availability endpoint has a small per-IP budget** (HTTP 429 after a burst of roughly 60 requests a minute; the block lasts minutes; every early request extends it) and the main Mac and the Mac mini share one IP. Rec.gov's own front end says the same thing in its error text: wait at least a minute, reloading sooner re-triggers it. Any feature that polls more must poll *narrower*.
- New JSON fields are additive. Each one needs: `recon/models.py`, the producing module, SKILL.md (the runtime LLM must know what it means), the wiki page, a test, and a fixture cut from a real response.
- URLs come only from the builders in `recon/parser.py`. A new link shape means a new builder.
- `urllib` only; anything decorative (weather, smoke, drive time) returns empty on failure and never aborts a run.
- A failed or skipped check is reported (`unreachable`, `partial`, `warnings`, `excluded_*`), never presented as "nothing available".

---

## Near-term

### 1. Party-size matching

**Why.** The JSON already carries `min_people` / `max_people` per site, but nothing filters on it, so the reply can be "here's a site" followed by "…max 2 people".

**Sketch.** `--party N` on both modes. Search mode treats a site that cannot hold N the way it now treats group/boat-in sites: dropped before dates, counts, samples and `contiguous`, and counted in an additive `excluded_open_sites["party_size"]`. Weekend mode must not drop anything (`sites_by_id` is durable for the auto-cart matcher), so it tags instead: `site_details[*].fits_party` plus a per-camp `available_dates_for_party`.

**Watch out for.** `--party 12` makes group sites the *right* answer, so it has to interact with `--all-site-types` (auto-include `group` when N exceeds the largest ordinary site). `min_people` matters as much as `max_people`: Point Reyes group sites are 7–25. Coverage is good: RIDB's bulk export has `Max Num of People` on 96–98% of campsites sampled, and the availability payload's own `min/max_num_people` was present on every site we have fetched.

**First step.** Offline only: extend the search fixture tests with sites of capacity 2, 6 and 7–25 and pin the three behaviours (filtered, counted, group auto-included).

### 2. Hot-watch cadence

**Why.** Mode 3 is a daily cron. Cancellations on booked weekends appear for seconds to minutes, which is the whole auto-cart thesis. Daily is fine a month out and useless the week of.

**Sketch.** A second watch mode for a **named short list of facility ids** (not a free-text search: no RIDB calls, one availability request per facility-month per tick), every 5–10 minutes, waking hours only, for the next N days. On the Mac mini it runs as a LaunchAgent, like the auto-deployer; that box's crontab has been paused since 2026-08-08.

**Constraints that shape it.**
- Budget: 5 facilities every 10 minutes for 16 waking hours is ~480 requests a day, about 0.5 a minute. That is fine on its own. It is not fine stacked on an unpaced 40-facility search or on auto-cart's own polling, so all three need one shared budget, and the existing `~/.campsitescout/rate_limit.json` cooldown must be honoured by all of them.
- It **requires de-duplication first** (follow-up A). A stateless watch at this cadence would notify every ten minutes for as long as an opening lasts.
- Rec.gov states reservation cut-offs are typically 0–4 days before arrival, which overlaps a "next 3 days" window: many of those nights are walk-up only by then. ReserveCalifornia (item 3) closes online booking two days out. The window should be "nights that are still bookable online", not "the next 3 days".

**First step.** Build follow-up A, then a `targets`-style config of facility ids (it can share a schema with the auto-cart `targets.json`).

### 3. ReserveCalifornia — California State Parks, read-only

**Why.** Pfeiffer Big Sur, Andrew Molera, Limekiln, Samuel P. Taylor, Mt Tamalpais, Henry Cowell and Butano are where most "I want to camp this weekend" demand from the Bay Area lands, and none of them are on Recreation.gov. Even a read-only scan would roughly double the tool's usefulness.

**What was verified (2026-09-20).**
- The site runs on Tyler Technologies' platform (formerly US eDirect). The API base is published in the site's own [config.json](https://www.reservecalifornia.com/config.json) as `rdrApiUrl`. Resolve it from there rather than hard-coding: the host moved in November 2025 with no notice.
- It is **keyless and needed no cookies, browser UA or JS challenge**: `GET {rdr}/fd/places` (299 places), `GET {rdr}/fd/facilities` (517 facilities) and `POST {rdr}/search/grid` all answered 200 to stdlib `urllib` with this repo's fixed `CampsiteRecon/1.0` User-Agent from the home IP. Traffic is CloudFront + an AWS load balancer; no Akamai or Cloudflare.
- Grid request: `{FacilityId, StartDate, EndDate, InSeasonOnly, WebOnly, UnitSort}` with `yyyy-MM-dd` dates; `EndDate` is inclusive. One POST covered 14 nights of a 22-unit facility in ~68 KB.
- Grid response: `Facility.Units{…}` each with `AllowWebBooking` and `Slices{date: {IsFree, IsBlocked, IsWalkin, Lock, MinStay, IsReservationDraw}}`, plus `Facility.Restrictions{FutureBookingStarts, MinimumStay, MaximumStay}`.
- **`IsFree` alone over-reports.** The live Samuel P. Taylor sample had 13 nights that were `IsFree` *and* `IsWalkin`. `WebOnly: true` does not remove them; camply still has this false-positive bug ([PR #413](https://github.com/juftin/camply/pull/413), open). The bookable rule has to be `IsFree and not IsWalkin and unit.AllowWebBooking and not IsReservationDraw`.
- `Lock` is a gift: a cancelled night shows `IsFree: false` with `Lock: "<tomorrow>T08:00:00"`, i.e. "this re-enters inventory at 8 am tomorrow". No Rec.gov equivalent is known.
- Booking link shape: `https://www.reservecalifornia.com/park/{PlaceId}/{FacilityId}` (confirmed in the SPA's router).
- **Online booking closes two days before arrival at most parks** ([parks.ca.gov](https://www.parks.ca.gov/?page_id=31966); the grid shows it as `FutureBookingStarts = today + 2`). A Thursday "this weekend" check will legitimately find nothing bookable online; the reply has to say that rather than "full". Some inventory is sold by lottery draw (`IsReservationDraw`), which is not first-come even when free.

Ids as read from the live directory (PlaceId → FacilityIds), to be re-verified before use:

| Park | PlaceId | Facilities |
|---|---|---|
| Pfeiffer Big Sur SP | 690 | 611 South Camp, 612 Weyland Camp, 767 Main Camp (609 group sites: not web-bookable) |
| Andrew Molera SP | 1077 | 1940 Trail Camp |
| Limekiln SP | 666 | 546 Redwood Camp, 1130 Ocean Camp |
| Samuel P. Taylor SP | 705 | 653 Creekside Loop, 657 Orchard Hill Loop (654/656 group; cabins are place 706 → 919) |
| Mount Tamalpais SP | 682 | 590 Steep Ravine camp, 766 Steep Ravine cabins (captcha-flagged), 588 Alice Eastwood group, 589 Frank Valley horse (2008 Bootjack and 2009 Pantoll: not web-bookable) |
| Henry Cowell Redwoods SP | 655 | 504 South, 505 North |
| Butano SP | 622 | 783 Ben Ries Campground (2143 Trail Camp: not web-bookable) |

**Risks, stated plainly.**
- **The safe polling rate is unknown.** About eight polite requests have ever been made from this IP. Every published report of 403s and multi-minute lock-outs (camply [#319](https://github.com/juftin/camply/issues/319)) predates the November 2025 host move. 33 of 517 facilities carry an `IsCaptcha` flag and the front end ships reCAPTCHA v3, so the operator can start requiring a token whenever it likes. Design it as "may disappear": own pacing, own per-host cooldown file, first 403/429 stops the run.
- **A block would also lock you out of booking by hand**, since it is the same home IP. Hot-watch (#2) multiplies that exposure.
- **Terms of use were not found.** The oft-quoted "terms prohibit bots" line is from 2017 and refers to the previous contractor. The legal posture is an open question for the maintainer, not a settled "prohibited" or "fine".

**camply.** This repo's stance says multi-provider support is the moment to revisit camply as a dependency. camply does have a working provider (`camply/providers/usedirect/`), but it sends a random Chrome User-Agent per request and still has the walk-in false positive. The surface we need is two directory GETs and one POST, so porting with attribution still looks right. Record the decision in the spec.

**First step.** A spec in the style of the auto-cart plan that first records the ToS and polling-budget decision. Then zero-network groundwork: three trimmed fixtures (places, facilities, one grid response containing a walk-in-free slice and a `Lock` slice), Pydantic boundary models, the bookable rule and `consecutive_nights` windows, all tested offline. Transport, presets, `--verify` and SKILL.md come after.

### 4. Smoke / AQI in the weather block

**Why.** In California, wildfire smoke is as trip-relevant as rain, and it is the same data provider the repo already uses.

**What was verified.**
- It is a separate host: `GET https://air-quality-api.open-meteo.com/v1/air-quality` ([docs](https://open-meteo.com/en/docs/air-quality-api)). No key for non-commercial use.
- **There is no daily aggregate.** `daily=` returns HTTP 400. Request `hourly=` and reduce to a per-day maximum client-side.
- **Use `us_aqi_pm2_5`, not `us_aqi`.** Plain `us_aqi` is the maximum of six pollutant sub-indices and inland it is often driven by ozone, not smoke. The dedicated `pm10_wildfires` variable is Europe-only (all nulls for a Yosemite coordinate).
- **The usable horizon is about five days, not the 14 the weather block has.** `forecast_days` accepts up to 7, but values were null after ~126 hours. A Monday run cannot speak to Saturday. The JSON needs an explicit per-day "no smoke forecast yet" state, and SKILL.md has to tell the LLM to say so.
- Source is the CAMS global model on a ~45 km grid, updated at 00Z and 12Z. Canyon smoke pooling and coastal marine-layer scouring (half of a Point Reyes or Big Sur grid cell is ocean) are below its resolution. Fire emissions are held constant through the forecast per a 2016 ECMWF paper; not re-confirmed for the current model cycle.
- Free tier ([pricing](https://open-meteo.com/en/pricing)): under 10,000 calls a day, 5,000 an hour, 600 a minute, 300,000 a month, non-commercial. Matters only if #2 or #5 reuse the block heavily.

**Options worth a look later.** `mass_density_8m` on the ordinary forecast API is HRRR near-surface smoke: much finer, but only ~18–45 hours of lead. AirNow publishes a keyless file, `https://files.airnowtech.org/airnow/today/reportingarea.dat`, with human-issued AQI forecasts per reporting area; good as an observed cross-check.

**First step.** Save one real response (with its null tail) as a fixture; add `smoke_aqi_pm25` per day to `WeatherDay` as optional; reuse the never-raises wrapper from `recon/weather.py`.

---

## Medium

### 5. Weather in search mode; arbitrary date ranges in weekend mode

**Why.** Search is the trip-planning mode and returns no weather at all, while weekend mode is fixed to Fri/Sat/Sun. That asymmetry is arbitrary.

**Sketch.** `SearchResult` already carries `latitude` / `longitude`. Fetch one forecast per *distinct rounded* coordinate (0.1°), which is ~10 calls for a Yosemite search instead of 17, and only for dates inside Open-Meteo's horizon; beyond it, say "no forecast yet". For weekend mode, accept `--nights N` or `--start/--end` on presets: `consecutive_nights()` already generalises, and `months_spanned()` already fetches across month boundaries. The weather dict would gain date keys alongside `friday/saturday/sunday` (additive).

**Related.** Follow-up B (the Kings Canyon and Sequoia forecast points are 600–1,400 m above half their camps) is the same code path and should be done together.

### 6. Amenity + access filtering

**Why.** "Drive-up, takes my 25 ft trailer, has water" is a real query. Today search returns distance-sorted results with no way to filter.

**What was verified.**
- RIDB's spec embeds `ATTRIBUTES[{AttributeName, AttributeValue}]` and `PERMITTEDEQUIPMENT[{EquipmentName, MaxLength}]` in each record of `GET /facilities/{id}/campsites` (50 per page). There is no facility-level amenities array. **Not verified live** — no working key was available during research.
- RIDB `CampsiteID` is the same id space as Rec.gov's `campsite_id`, so attributes join straight onto `sites_by_id`.
- RIDB also publishes a **keyless bulk export** ([RIDBFullExport_V1_CSV.zip](https://ridb.recreation.gov/downloads/RIDBFullExport_V1_CSV.zip), ~247 MB, refreshed daily). Its files are stored uncompressed and the server honours HTTP Range, so a single CSV can be pulled by byte range with stdlib only. A local cache rebuilt from the export every week or so beats per-query API calls.
- Official docs say the rate limit is 50 requests a second; a third-party connector's docs say 50 a minute. Plan for the lower.

**The data is dirty, which drives the design.** Spellings vary (`Drive In` / `Drive-In` / `Drive in`; shade is `Yes` / `Full` / `Shade `). Coverage varies by region: in two 3 MB slices shade was present on ~78% of sites and site access on 20–60%, and `Max Vehicle Length` is the literal `0` on 8–9% of sites, a second "unrecorded" sentinel alongside `MaxLength == 0` on 27–29% of equipment rows. **So every filter must be tri-state (yes / no / unknown), and "unknown" must never silently drop a site.** camply's `MaxLength >= N` rule gets this wrong.

**First step.** One keyed request to confirm the list endpoint really populates both arrays. Also worth bundling: send the RIDB key as the documented `apikey` *header* instead of `?apikey=`, which keeps it out of URLs altogether.

### 7. First-come-first-served flag

**Why.** FCFS sites never show as available because they are not reservable, so a campground with 40 walk-up sites reads as "fully booked".

**What the research changed.**
- **`"Open"` is not the FCFS signal**, and this repo's docs describe it imprecisely. camply added `Open` to its denylist for *checkout-only* cells, not walk-up sites. Rec.gov's own front end gates **`Not Reservable`** behind a `canBookFCFS` flag, i.e. that is its FCFS status. Excluding both is still correct; the explanation in `recon/models.py`, `docs/parser.md` and SKILL.md should be corrected when this is built.
- FCFS-only campgrounds never reach the scanner: search keeps only RIDB `Reservable: true` facilities. Rec.gov links non-reservable campgrounds to `/camping/poi/{id}`, not `/camping/campgrounds/{id}`, so this needs a new URL builder.
- A keyless signal exists: FCFS-only campground pages carry the boilerplate "available on a first-come, first-served basis only" in their server-rendered meta description. It is prose matching, so treat it as a hint.
- Whatever this emits must stay **out of** `results`, `available_dates` and `sites_by_id`: the cron gate fires on `results`, and the auto-cart matcher reads `sites_by_id`. It belongs in its own field, e.g. `fcfs_site_count`.

**First step.** Three fixtures that do not exist yet: an FCFS-only campground, a mixed one, and a reservable one inside a walk-in season. Look the ids up in RIDB, capture with at most three requests outside watch hours, then design. See also follow-up C, which the same fixtures would settle.

---

## Lower / nice-to-have

### 8. Permit lottery reminders

**Why.** Half Dome, Mt Whitney and The Wave run on application windows, not availability. A deadline reminder fits the existing cron / LaunchAgent machinery.

**What was verified.**
- One public, keyless endpoint has everything: `GET https://www.recreation.gov/api/lottery/available` (~1.6 MB, ~1,860 records) with `open_at`, `close_at`, `announced_at`, `deadline_at`, `display_at` and a time zone per lottery. It is the endpoint Rec.gov's own lottery page uses.
- **It hides a lottery until `display_at`**, so lead time is short: Mt Whitney 42 days, Half Dome 14, Enchantments 5, Grand Canyon 0. "Opens in six weeks" reminders therefore need `GET /api/permitcontent/{id}` → `important_dates`, which does look forward, or a small hand-maintained recurrence table.
- **Stale-id trap.** The retired Mt Whitney id 233260 still answers 200, with `is_inactive: true` and 2023 dates. A watchlist entry must be rejected unless `is_inactive` is false *and* the id appears in the live feed. That check belongs in `--verify`.
- The feed contains junk to filter ("Fake Lottery Testing Do Not Apply", "Prod Test", "…Archived" records), and `deadline_at` does not always mean "accept by".
- Ids as read from the live feed: Half Dome 234652, Mt Whitney 445860, The Wave advanced 274309, Yosemite wilderness 445859, North Pines early-access 232449. Mt Whitney's stable window per the Forest Service: apply Feb 1 – Mar 1, results Mar 15, claim by Apr 21, unclaimed dates released Apr 22.
- camply offers no prior art; its permit PR has sat unmerged since 2023.

**First step.** A trimmed fixture of the feed, a boundary model, and an offline test that computes "opens in N days / closes in N days / results on" for a five-entry verified watchlist in each lottery's own time zone.

### 9. Drive-time ranking

**Why.** `distance_km` is a straight line from a park centroid. "Where can I actually get to on Friday night" is a drive-time question.

**What was verified.**
- The practical default is the OSRM table service: one keyless GET, `/table/v1/driving/{lon},{lat};…?sources=0&annotations=duration`, covering a whole search in a single request. The public demo's policy gives no numeric limit ("excessive use … we will block you") and requires an identifying User-Agent; the FOSSGIS instance states one request a second.
- Fallback: openrouteservice's free plan (Matrix 500 requests a day and 40 a minute, 3,500 pairs per request, needs a key; results are CC-BY-SA with a required attribution string).
- Mapbox and Google are out: both forbid caching durations, and Google needs a billing account.
- **Privacy is the design constraint.** Both OSM-stack providers' terms forbid sending personal data, and a home address is personal data. So: store the exact origin only in `~/.campsitescout/`, send a **coarsened** coordinate (2–3 decimals), and have the user supply lat/lon directly rather than geocoding an address. Nominatim's policy also now has an explicit clause on LLM-generated code, which is a second reason to skip geocoding.
- Results can be cached per `(origin, facility_id)` essentially forever. None of the free engines know about live traffic or seasonal closures (Tioga, Sonora and Ebbetts passes in winter), so label it an estimate.

**First step.** A short spec that records the provider and privacy decisions, then one 1×2 table probe per candidate host to confirm it is reachable. Treat it like weather: any failure falls back to `distance_km`.

### 10. Cancellation-history prediction

**Why.** "This campground drops most cancellations on Tuesdays at 9 am" (Campflare-style) is only possible with history, and watch mode already polls; persisting what it sees is the missing piece.

**Sketch.** stdlib `sqlite3` at `~/.campsitescout/history.sqlite`, one row per `(observed_at, facility_id, campsite_id, night, status)` written as a side effect of watch runs, recording *transitions* rather than full snapshots to keep it small. Analysis is a separate read-only command.

**Honest dependencies.** It is only meaningful at hot-watch cadence (#2); a daily poll cannot see a drop that lasts minutes. It needs weeks of data before it says anything. For State Parks there is a shortcut that needs no history: cancelled sites re-enter inventory at 08:00 the next day (the `Lock` field in #3), and the cancellation policy for stays from 2026-07-01 gives a full refund only seven or more days out ([parks.ca.gov](https://www.parks.ca.gov/?page_id=31977)), so drops should cluster a week ahead and at 8 am. That is an inference, not a measurement.

---

## Follow-ups carried over from the September 2026 fix

These are gaps found while fixing the wrong-id incident. They are smaller than features, and two of them are correctness risks rather than wishes.

- **A. Watch de-duplication.** Mode 3 is stateless and re-notifies every day an opening persists. camply's set-diff pattern is the fix (already noted in [camply-attribution.md](camply-attribution.md)). Prerequisite for #2.
- **B. Per-camp weather.** Kings Canyon's forecast point is Grant Grove, 27 km and ~600 m above the Cedar Grove camps; Sequoia's is Lodgepole, ~1,400 m above the Foothills camps. SKILL.md currently has the LLM name the reference point. Verified coordinates are already in `tests/fixtures/presets/directory.json`. Do it with #5.
- **C. Status denylist gap (correctness).** Rec.gov's own front end defines statuses that are not in `_REC_GOV_UNAVAILABLE_STATUSES`: `Not Reservable Cutoff`, `Current`, `Unavailable` and the `Early Access` family. Because the repo uses a denylist, any of these would be counted as bookable if the API emits them. Whether it does is unverified; camply's list has the same gap. The front end's own bookable rule for the public is simply `Available`, `Early Access - Available` or `Reserved Available`. Settle it with the fixtures from #7, then either extend the denylist or document why not.
- **D. Ask RIDB for the official Availability API.** RIDB publishes a spec for a key-authenticated availability endpoint ([availability.yaml](https://ridb.recreation.gov/shared/swagger/availability.yaml), `GET /api/availability/camping/{facilityId}?date=`) behind a "tier 1" access flag. Nobody established how a key gets that access or what its limits are. If obtainable it would move every scan off the undocumented, per-IP-throttled endpoint. One email to RIDB support is worth it before building more on `/api/camps/availability`.
- **E. Per-campsite stay rules.** `stay_rules` is facility-level. Some sites have their own (Point Reyes Sky 001: `maxConsecutiveStay = 1`), available from `/api/camps/campsites/{id}` at one request per site. Only worth fetching for sites about to be recommended or carted.
- **F. Weekend-mode group sites.** Search skips group and boat-in sites by default; presets do not, by design, so "Wildcat — available" can still mean a 7–25 person site. Decide whether presets should tag or filter. #1 largely answers it.
- **G. NPS wilderness permits.** `/api/permits/{id}/availability/month` answers 404 for Yosemite (445859) and SEKI (445857) wilderness permits; they use a different inventory API. Find it before wiring any permit preset.
- **H. Deploy hardening.** `main` is unprotected, and whoever can push to it runs code on the Mac mini within 15 minutes. Options, strongest last: passkey / 2FA on the GitHub account; a branch rule requiring a PR and the `test` check; have `deploy/auto_deploy.sh` refuse commits not signed by a trusted key. Also small: skip the gateway restart when a deploy changed only docs.
- **I. Names in a public repo.** The tracked deploy scripts name the `jambot` account, its paths and the 1Password vault and item names. None of it grants access, but it could move to an untracked config file on the box.
