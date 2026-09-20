# Recreation.gov API — Response Shapes & Observed Behaviour

Practical reference for building on this application. Documents actual response
structures, quirks, and lessons learned from live API calls. Complements
`api-endpoints.md` (URL patterns) and `facility-ids.md` (verified IDs).
Last re-verified live: **2026-09-20**.

---

## Critical gotcha 1 — URL encoding

The `start_date` parameter **must** have its colons URL-encoded. The API returns
`400 {"error":"query not encoded"}` if you pass raw colons.

```
# ❌ Breaks silently (returns None from client)
?start_date=2026-04-01T00:00:00.000Z

# ✅ Works
?start_date=2026-04-01T00%3A00%3A00.000Z
```

## Critical gotcha 2 — a wrong facility id still returns a valid-looking response

`/api/camps/availability/campground/{id}/month` answers 200 with a full
`campsites` payload for *any* real id. Nothing tells you the id you meant
"Sky Camp" is actually Devils Garden Campground in Utah. That is exactly what
happened in this repo from April to September 2026: four Point Reyes presets
and three Big Sur presets pointed at campgrounds in UT, WA, OR and NM, and the
output looked perfectly plausible. Always confirm an id with
`/api/camps/campgrounds/{id}` (`facility_name`, `facility_latitude`) or RIDB
`/facilities/{id}` before trusting it. `python main.py --verify` automates
this for the presets.

## Critical gotcha 3 — HTTP 429

The availability endpoints sit behind CloudFront and answer **429 Too Many
Requests** (empty body, no `Retry-After`) when polled in a burst. Observed
trigger: ~60+ requests inside a minute from one IP. Metadata endpoints
(`/api/camps/campgrounds/{id}`) and RIDB keep working while availability is
blocked. The block is per-IP, clears only after ~6 minutes of complete silence, and every request made while blocked restarts the clock. `RecGovClient` paces availability calls (0.6 s), trips `rate_limited` on the first 429, stops for the run, and writes a 10-minute cooldown to `~/.campsitescout/rate_limit.json` that later runs honour; reports carry a `warnings` entry naming the time.

---

## Campground availability response

```
GET /api/camps/availability/campground/{facilityId}/month
    ?start_date={YYYY-MM-01T00%3A00%3A00.000Z}
```

### Shape

```json
{
  "campsites": {
    "518310": {
      "campsite_id": "518310",
      "site": "BOAT A, 1-6 people",
      "loop": "Tomales Bay",
      "campsite_type": "BOAT IN",
      "campsite_reserve_type": "Non Site-Specific",
      "type_of_use": "Overnight",
      "min_num_people": 1,
      "max_num_people": 6,
      "capacity_rating": "Single",
      "hide_external": false,
      "campsite_rules": {},
      "supplemental_camping": {},
      "availabilities": {
        "2026-10-01T00:00:00Z": "Available",
        "2026-10-02T00:00:00Z": "Reserved",
        "2026-10-03T00:00:00Z": "NYR"
      },
      "quantities": {
        "2026-10-01T00:00:00Z": 1,
        "2026-10-02T00:00:00Z": 0
      }
    }
  },
  "count": 51
}
```

### Key observations

- Top-level key is `campsites`; `count` mirrors its length. An empty dict means no data for that facility/month.
- Outer key == `campsite_id`. `site` is the human label, `loop` is the named sub-area. **Point Reyes' four camps are loops** (`Sky`, `Coast`, `Glen`, `Wildcat`, plus `Tomales Bay` / `Tomales Bay Boat Only`) of facility 233359.
- Date keys are ISO timestamps ending in `Z`; parse with `dt_str[:10]`.
- `type_of_use` is `Overnight` or `Day`; `hide_external: true` sites are not shown on the public site. Both are filtered by `is_bookable_site()`.
- `quantities` is `null` for some facilities and a per-date count for others; not used for the open/closed decision (status is authoritative).
- `campsite_rules` was `{}` on every facility probed; min-stay rules are not exposed here.

### Status values (observed live 2026-09-20 across Point Reyes, Kirk Creek, Upper Pines, Pinnacles, Lodgepole)

| Status | Bookable? |
|---|---|
| `Available` | ✅ |
| `Open` | ❌ walk-up / first-come only (camply denylist — was a false-positive source) |
| `Reserved` | ❌ |
| `Not Available` | ❌ |
| `Not Reservable` | ❌ |
| `Not Reservable Management` | ❌ |
| `Not Available Cutoff` | ❌ |
| `NYR` | ❌ not yet released (outside the booking window) |
| `Closed` | ❌ |
| `Lottery` | ❌ |

Implemented as a **denylist** (`is_available`) so an unknown new status is treated as bookable and shows up in output where a human will notice it, rather than being silently dropped.

---

## Campground metadata

```
GET /api/camps/campgrounds/{facilityId}
```

Returns `{"campground": {...}}` with `facility_name`, `facility_latitude`,
`facility_longitude`, `parent_asset_id`, `facility_time_zone`, `is_deactivated`,
and **`facility_rules`** — a dict of `{"value": int, "units": str,
"secondary_value": "soft"|"strict"|"softAny", "start_date", "end_date"}` keyed by
rule name. Observed rules: `minConsecutiveStay` (Kirk Creek 2 softAny, Plaskett Creek 2 softAny),
`minWeekendStay` (Kirk Creek 2 soft), `minHolidayWeekendStay` (Kirk Creek 3 **strict**) — the `secondary_value` qualifier is surfaced as `stay_rules.*_policy`; only `strict` is a hard refusal,
`maxConsecutiveStay` (14), `reservationCutOff`, `blockReleaseDay` (Upper Pines:
"Blocks released on the 15th of each month"), `maxConcurrentStay`. `stay_limit`
is an empty string everywhere. No key needed; 404 for unknown ids; **not subject
to the 429 throttle** in our observations. This is where `official_name` and
`stay_rules` in the output come from, and what `--verify` cross-checks against
RIDB. Per-campsite rules (`/api/camps/campsites/{id}` → `campsite_rules`, e.g.
Point Reyes Sky 001 `maxConsecutiveStay=1`) exist too but cost one call per
site and are not fetched.

---

## Permit availability response (2026 shape)

```
GET /api/permits/{permitId}/availability/month
    ?start_date={YYYY-MM-01T00%3A00%3A00.000Z}
    &commercial_acct=false
```

```json
{
  "payload": {
    "permit_id": "4675311",
    "next_available_date": "2026-10-01T00:00:00Z",
    "availability": {
      "467531100": {
        "division_id": "467531100",
        "date_availability": {
          "2026-10-01T00:00:00Z": {"total": 1, "remaining": 1, "show_walkup": false, "is_secret_quota": false},
          "2026-10-02T00:00:00Z": {"total": 1, "remaining": 0, "show_walkup": false, "is_secret_quota": false}
        },
        "quota_type_maps": {}
      }
    }
  }
}
```

- `availability` is keyed by **division id** (entry point / trailhead / zone), and each division carries its own `date_availability`. The older flat `availability[date].remaining` shape is still handled by `permit_open_dates()` for safety.
- A permit with nothing released yet returns divisions with empty `date_availability` and a stale `next_available_date`.
- **No preset uses the permit path today.** Point Reyes was believed to be permit-booked; it is not (the "permit ids" in the old config were Zion Angels Landing and Central Cascades permits).
- **This endpoint does not serve NPS wilderness permits.** Live 2026-09-20: `/api/permits/445859/availability/month` (Yosemite Wilderness) and `445857` (SEKI Wilderness) answer **HTTP 404**; only lottery / day-use style permits (Half Dome `234652`, Central Cascades `4675311`) answer 200. Wilderness permits use a different inventory API — verify before wiring one, and add a `--verify` check that `permit_month` returns 200 for any `permit_id` preset.

---

## RIDB facility search (used by search mode)

```
GET https://ridb.recreation.gov/api/v1/facilities
    ?query={free_text}&facilitytype=Campground&limit=50&offset={n}&apikey={KEY}
```

- `apikey` is required. Availability endpoints are unauthenticated.
- **Page size max is 50 and results are paginated**: `METADATA.RESULTS.TOTAL_COUNT` vs `CURRENT_COUNT`. "Yosemite" has 43 matches; the first 25 do *not* include Upper/Lower/North Pines. The client now walks `offset` until `TOTAL_COUNT` (cap 150).
- `facilitytype=Campground` is only a hint: `Permit`, `Timed Entry`, `Visitor Center` and `Facility` records still come back. Filter on `FacilityTypeDescription == "Campground"`, `Reservable`, and `Enabled`.
- `FacilityName` is inconsistent in case (`LOST CLAIM` vs `McCabe Flat Campground`); only title-case the all-caps ones.
- `RECAREA` is an empty list in search results; use `ParentRecAreaID` → `/recareas/{id}` (`RecAreaName`) to say where a campground is. Free-text search is fuzzy — "Yosemite" returns Stanislaus NF, Sierra NF, Inyo NF and BLM Merced River campgrounds too.
- `/facilities/{id}` for an unknown id returns **200 with every field empty**, not 404.
- `FacilityID` is the same id the availability endpoint uses.

### `/recareas?query=` as a relevance anchor

Its first hit is frequently unrelated ("Pinnacles" → Cottonwood Point Wilderness, UT; "Tahoe" → Sugar Pine Reservoir; "Joshua Tree" → Castle Mountains NM), and some records have `0,0` coordinates ("Route 1 - Big Sur Coast Highway"). `ridb_search_recarea` therefore only accepts a record whose `RecAreaName` contains every word of the query *and* has non-zero coordinates — "Yosemite" → 2991, "Point Reyes" → 2864, "Zion" → 2994, "Sequoia" → 2931; "Big Sur" → none, so that search is unfiltered.

---

## Open-Meteo (weather)

No key, no observed rate limit, 14-day daily forecast. Weekends further out
than 14 days produce an empty `weather` object — expected, not a bug.

```
GET https://api.open-meteo.com/v1/forecast
    ?latitude={lat}&longitude={lon}
    &daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max
    &temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm
    &timezone=auto&forecast_days=14
```

`daily.time` is plain `YYYY-MM-DD`; arrays are parallel; `precipitation_sum`
can be `null`. Wind > 25 kph is worth flagging for exposed coastal/ridge
sites. Full WMO mapping in `recon/weather.py`.
