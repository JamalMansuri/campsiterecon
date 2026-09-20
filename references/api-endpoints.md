# API Endpoints Reference

## 1. RIDB — Recreation Information Database

**Base URL:** `https://ridb.recreation.gov/api/v1`
**Auth:** `apikey` query param (or `apikey` header)
**API Key:** Stored in macOS Keychain as `recreation-gov-api`. Load with `security find-generic-password -a "$USER" -s "recreation-gov-api" -w`. Never hardcode in this repo.
**Docs:** https://ridb.recreation.gov/docs

### Search Facilities

```
GET /facilities
```

| Param | Type | Description |
|-------|------|-------------|
| `query` | string | Name or keyword search |
| `latitude` | float | Center point for geo search |
| `longitude` | float | Center point for geo search |
| `radius` | float | Miles from lat/lon (default 25) |
| `facilitytype` | string | `"Campground"` to filter |
| `limit` | int | Max results per page (default 50, **max 50**) |
| `offset` | int | Pagination — walk it until `METADATA.RESULTS.TOTAL_COUNT`; "Yosemite" has 43 matches and the Valley campgrounds are on page 2 |
| `apikey` | string | Your API key |

**Response:**
```json
{
  "RECDATA": [
    {
      "FacilityID": "233359",
      "FacilityName": "Point Reyes National Seashore Campground",
      "FacilityLatitude": 38.04121,
      "FacilityLongitude": -122.800354,
      "FacilityTypeDescription": "Campground",
      "Reservable": true,
      "Enabled": true,
      "ParentRecAreaID": "2864",
      "RECAREA": []
    }
  ],
  "METADATA": {
    "RESULTS": {"TOTAL_COUNT": 12, "CURRENT_COUNT": 5}
  }
}
```

### Search Recreation Areas

```
GET /recareas
```

Same params as `/facilities`. Useful when facility search returns nothing — search the parent rec area, then drill into its facilities.

### Get Facilities in a Rec Area

```
GET /recareas/{recAreaId}/facilities
  ?facilitytype=Campground
  &limit=20
  &apikey={key}
```

### Get a Single Facility

```
GET /facilities/{facilityId}?apikey={key}
```

Returns full facility detail including lat/lon, amenities, links.

### Get Campsites in a Facility

```
GET /facilities/{facilityId}/campsites?limit=50&apikey={key}
```

Returns individual site metadata (loop name, site type, max occupancy). Not needed for availability checks but useful if the user asks about specific site types (hookups, tent-only, etc.).

---

## 2. Recreation.gov Availability API

> **Unofficial API** — no documented key, but publicly accessible and widely used by third-party checkers. Be respectful with request rates.

**Base URL:** `https://www.recreation.gov/api/camps/availability/campground`
**Headers:** Always include `User-Agent: CampsiteRecon/1.0` (what `recon/api_client.py` sends)
**No API key required.**

### Get Monthly Availability

```
GET /{facilityId}/month?start_date={YYYY-MM-01T00:00:00.000Z}
```

The `start_date` must be the **first of a month** in ISO format. To check availability for May 2026:
```
?start_date=2026-05-01T00%3A00%3A00.000Z
```

**Response:**
```json
{
  "campsites": {
    "12345": {
      "site": "A1",
      "loop": "Main Loop",
      "campsite_reserve_type": "Site-Specific",
      "availabilities": {
        "2026-05-01T00:00:00Z": "Reserved",
        "2026-05-02T00:00:00Z": "Available",
        "2026-05-03T00:00:00Z": "Not Available",
        "2026-05-04T00:00:00Z": "Open"
      },
      "quantities": null
    }
  }
}
```

**Availability status values** (full list + rationale in `api-response-shapes.md`):

| Status | Meaning |
|--------|---------|
| `Available` | ✅ Open to book |
| `Open` | ❌ Walk-up / first-come only — **not** bookable online (camply denylist) |
| `Reserved` | ❌ Already booked |
| `Not Available` | ❌ Closed / not offered |
| `Not Reservable` | ❌ Cannot be reserved online |
| `Not Reservable Management` | ❌ Held by park staff |
| `NYR` | ❌ Not yet released (outside the booking window) |
| `Closed`, `Lottery`, `Not Available Cutoff` | ❌ |

**A wrong facility id still returns a 200 with a full `campsites` payload.** Confirm ids with the metadata endpoint below before trusting them.

### Campground metadata

```
GET https://www.recreation.gov/api/camps/campgrounds/{facilityId}
```

No key. Returns `{"campground": {"facility_name": ..., "facility_latitude": ..., "facility_longitude": ..., "parent_asset_id": ...}}`; 404 for unknown ids. Used for `official_name` in output and by `main.py --verify`.

### Wilderness Permit Availability

For backcountry / wilderness permits (Yosemite Wilderness, Half Dome), the endpoint is different:

```
GET https://www.recreation.gov/api/permits/{permitId}/availability/month
  ?start_date={YYYY-MM-01T00:00:00.000Z}
  &commercial_acct=false
```

The response is `payload.availability[division_id].date_availability[date].{total, remaining}` — keyed by division (entry point / zone), dates nested inside. **Point Reyes is not a permit** — it is campground 233359 with loops; see `facility-ids.md`. Genuine permits: Yosemite Wilderness `445859`, Half Dome `234652`.

### Rate Limiting

Observed 2026-09-20: the availability endpoints return **HTTP 429** (CloudFront, no `Retry-After`) after a burst of roughly 60+ requests in a minute, and stay blocked for a few minutes. `RecGovClient` paces availability calls at 0.6 s, caches per run, trips a breaker on the FIRST 429 (retrying only extends the block) and writes a 10-minute cooldown to `~/.campsitescout/rate_limit.json` that later runs honour. Don't run several scans in parallel from one IP.

---

## 3. Open-Meteo Weather Forecast

**Free, no API key, no account needed.**
**Docs:** https://open-meteo.com/en/docs

### 14-Day Forecast

```
GET https://api.open-meteo.com/v1/forecast
  ?latitude={lat}
  &longitude={lon}
  &daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max
  &temperature_unit=celsius
  &wind_speed_unit=kmh
  &precipitation_unit=mm
  &timezone=auto
  &forecast_days=14
```

**Response:**
```json
{
  "latitude": 38.04,
  "longitude": -122.80,
  "timezone": "America/Los_Angeles",
  "daily": {
    "time": ["2026-05-17", "2026-05-18", ...],
    "weathercode": [1, 3, 61, ...],
    "temperature_2m_max": [20.1, 22.3, 14.7, ...],
    "temperature_2m_min": [11.0, 12.4, 8.4, ...],
    "precipitation_sum": [0.0, 0.0, 10.7, ...],
    "windspeed_10m_max": [19.8, 14.0, 29.3, ...]
  }
}
```

### WMO Weather Code Reference

| Code(s) | Description | Emoji |
|---------|-------------|-------|
| 0 | Clear sky | ☀️ |
| 1 | Mainly clear | 🌤️ |
| 2 | Partly cloudy | ⛅ |
| 3 | Overcast | ☁️ |
| 45, 48 | Fog | 🌫️ |
| 51, 53, 55 | Drizzle (light→heavy) | 🌦️ |
| 61, 63, 65 | Rain (light→heavy) | 🌧️ |
| 71, 73, 75 | Snow (light→heavy) | ❄️ |
| 77 | Snow grains | 🌨️ |
| 80, 81, 82 | Rain showers | 🌦️ |
| 85, 86 | Snow showers | 🌨️ |
| 95 | Thunderstorm | ⛈️ |
| 96, 99 | Thunderstorm + hail | ⛈️ |

### High Wind Flag

Wind over **25 kph** (`wind_kph` in the output) is worth flagging for camping — mention it in the reply:
`💨 Winds up to {X} km/h — exposed sites may be rough`

---

## 4. Recreation.gov Direct Links

Use these URL patterns to generate booking links:

| Type | URL Pattern |
|------|-------------|
| Campground page | `https://www.recreation.gov/camping/campgrounds/{facilityId}` |
| Permit page | `https://www.recreation.gov/permits/{permitId}` |
| Specific campsite | `https://www.recreation.gov/camping/campsites/{campsiteId}` |

(`/availability` redirects to the plain campground page; the three patterns above are the ones `recon/parser.py` emits, and the only ones the runtime LLM may use.)
