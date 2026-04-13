# Recreation.gov API — Response Shapes & Observed Behaviour

Practical reference for building on this application. Documents actual response structures, quirks, and lessons learned from live API calls. Complements `api-endpoints.md` (which covers URL patterns) and `facility-ids.md` (which covers known IDs).

---

## Critical Gotcha — URL Encoding

The `start_date` parameter **must** have its colons URL-encoded. The API returns `400 {"error":"query not encoded"}` if you pass raw colons.

```
# ❌ Breaks silently (returns None from client)
?start_date=2026-04-01T00:00:00.000Z

# ✅ Works
?start_date=2026-04-01T00%3A00%3A00.000Z
```

This is not documented anywhere officially. Discovered during smoke testing April 2026.

---

## Two Distinct Endpoint Types

Recreation.gov has two completely different availability endpoints with different response shapes. The type of camp determines which one to use — and sometimes you won't know until you try.

| Type | Used for | Response key |
|---|---|---|
| Campground | Drive-in / standard sites | `campsites` |
| Permit | Wilderness / backcountry | `payload.availability` |

**Point Reyes is permit-only.** The campground endpoint returns `{}` for all 4 wilderness camps. Always fall back to the permit endpoint when `campsites` is empty or absent.

**Big Sur uses the campground endpoint.** Standard drive-in sites, no permit system.

---

## Campground Availability Response

```
GET /api/camps/availability/campground/{facilityId}/month
    ?start_date={YYYY-MM-01T00%3A00%3A00.000Z}
```

### Shape

```json
{
  "campsites": {
    "12345": {
      "site": "A1",
      "loop": "Main Loop",
      "campsite_reserve_type": "Site-Specific",
      "availabilities": {
        "2026-04-17T00:00:00Z": "Available",
        "2026-04-18T00:00:00Z": "Reserved",
        "2026-04-19T00:00:00Z": "Not Available"
      },
      "quantities": null
    },
    "12346": { ... }
  }
}
```

### Key observations

- Top-level key is always `campsites` — if absent or empty dict, the endpoint has no data for this facility (try permit endpoint instead)
- Date keys inside `availabilities` are ISO timestamps ending in `Z` — parse with `dt_str[:10]` to get the date portion only
- Each key in `campsites` is an internal site ID (not human-readable) — the `site` field inside has the human label (e.g. "A1")
- A campground with 32 sites returns 32 keys — you aggregate across all of them to determine if *any* site is open on a given date
- `quantities` is used for group sites — usually `null` for individual sites

### Status values

| Status | Bookable |
|---|---|
| `Available` | ✅ Yes |
| `Open` | ✅ Yes (walk-up or first-come) |
| `Reserved` | ❌ No |
| `Not Available` | ❌ No (closed or not offered) |
| `Not Reservable` | ❌ No (walk-up only, cannot book online) |
| `Not Reservable Management` | ❌ No (held by park staff) |

Only `Available` and `Open` should be treated as bookable. Everything else is a no.

### Real observation — Big Sur (April 2026)

Kirk Creek (233116) returned 32 sites. Pfeiffer Big Sur (233394) had availability on all 3 days of the weekend. Andrew Molera (234218) and Plaskett Creek (233115) were fully booked. Limekiln SP (10149046) returned `None` — likely closed or temporarily off Recreation.gov.

---

## Permit Availability Response

```
GET /api/permits/{permitId}/availability/month
    ?start_date={YYYY-MM-01T00%3A00%3A00.000Z}
    &commercial_acct=false
```

### Shape

```json
{
  "payload": {
    "availability": {
      "2026-04-17T00:00:00Z": {
        "remaining": 2,
        "total": 8,
        "status": "Available"
      },
      "2026-04-18T00:00:00Z": {
        "remaining": 0,
        "total": 8,
        "status": "Sold Out"
      }
    }
  }
}
```

### Key observations

- Response is nested under `payload.availability` — not flat like the campground response
- Some responses omit `payload` entirely and put `availability` at the top level — always check both: `raw.get("payload", raw).get("availability", {})`
- Date keys are the same ISO timestamp format — parse with `[:10]`
- `remaining` is the number of permit slots left for that entry date — check `isinstance(remaining, int) and remaining > 0`
- `total` is the daily quota — useful for showing "2 of 8 remaining"
- `commercial_acct=false` must be included — omitting it may return commercial quota numbers instead of public availability

### Real observation — Point Reyes (April 2026)

All 4 wilderness camps (Sky, Coast, Glen, Wildcat) returned `remaining: 0` for the upcoming weekend — fully booked. This is normal for Point Reyes; the 90-day booking window opens at midnight and sells out within minutes.

---

## Reservation URL Patterns

The URL to give users depends on which endpoint type the camp uses:

```python
# Campground (drive-in)
f"https://www.recreation.gov/camping/campgrounds/{facility_id}"

# Permit (wilderness)
f"https://www.recreation.gov/permits/{permit_id}"
```

Do not use the campground URL for permit-only camps — it will land the user on the wrong page.

---

## The Campground → Permit Fallback Pattern

Some facilities are listed in RIDB with a `FacilityID` but their actual bookings run through the permit system. Point Reyes is the clearest example — the facility IDs exist, but the campground availability endpoint returns empty.

The pattern we use in `availability.py`:

1. Try campground endpoint with `facility_id`
2. If response is `None` or `campsites` is empty → try permit endpoint with `permit_id`
3. Tag the response `{"type": "campground"}` or `{"type": "permit"}` so `parser.py` knows which shape to expect
4. If both return nothing → return `None` (camp may be closed or offline)

---

## Noise in API Responses

The RIDB search endpoint (`/facilities?query=...`) returns everything associated with a rec area — visitor centres, ranger stations, trailhead parking, group event spaces. These are not campable.

Filter criteria:
- `reservable: true` — the primary flag. Visitor centres are not reservable
- `FacilityTypeDescription: "Campground"` — use as the `facilitytype` query param when searching RIDB

Even with filtering, some results still slip through. Using hardcoded facility IDs from `facility-ids.md` avoids this entirely for known locations.

---

## Rate Limiting

No published limit, but observed behaviour:
- Rapid sequential calls (< 1s apart) work fine for small batches (under ~10 calls)
- Hitting the same endpoint twice in a session is wasteful — results don't change within minutes
- If building multi-month lookahead, add a brief pause between month calls
- The availability endpoint is read-only and widely used by third-party scrapers — be reasonable

---

## Open-Meteo (Weather)

No API key, no rate limiting observed. Returns 14-day daily forecast.

```
GET https://api.open-meteo.com/v1/forecast
    ?latitude={lat}&longitude={lon}
    &daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max
    &temperature_unit=celsius
    &wind_speed_unit=kmh
    &precipitation_unit=mm
    &timezone=auto
    &forecast_days=14
```

### Shape

```json
{
  "daily": {
    "time":                ["2026-04-17", "2026-04-18", ...],
    "weathercode":         [2, 3, 61, ...],
    "temperature_2m_max":  [16.1, 16.4, 13.1, ...],
    "temperature_2m_min":  [7.6, 8.5, 9.5, ...],
    "precipitation_sum":   [0.0, 0.0, 4.2, ...],
    "windspeed_10m_max":   [15.6, 11.3, 31.4, ...]
  }
}
```

- `time` is plain `YYYY-MM-DD` (no timestamp) — no parsing needed
- All arrays are parallel — index `i` in `time` corresponds to index `i` in all other arrays
- `precipitation_sum` can be `null` for days with no precipitation — coerce with `value or 0.0`
- Wind > 25 kph is worth flagging for exposed coastal/ridge campsites
- `timezone=auto` uses the lat/lon to determine local timezone — always include it

### WMO weather codes (relevant subset)

| Code | Condition |
|---|---|
| 0 | Clear |
| 1 | Mainly clear |
| 2 | Partly cloudy |
| 3 | Overcast |
| 45, 48 | Fog |
| 51–55 | Drizzle |
| 61–65 | Rain |
| 71–75 | Snow |
| 80–82 | Showers |
| 95, 96, 99 | Thunderstorm |

Full mapping in `recon/weather.py`.
