# API Endpoints Reference

## 1. RIDB — Recreation Information Database

**Base URL:** `https://ridb.recreation.gov/api/v1`
**Auth:** `apikey` query param (or `apikey` header)
**API Key:** `REDACTED_API_KEY`
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
| `limit` | int | Max results (default 50, max 50) |
| `offset` | int | Pagination |
| `apikey` | string | Your API key |

**Response:**
```json
{
  "RECDATA": [
    {
      "FacilityID": "234059",
      "FacilityName": "SKY CAMP",
      "FacilityLatitude": 38.0371,
      "FacilityLongitude": -122.8027,
      "FacilityTypeDescription": "Campground",
      "FacilityDescription": "...",
      "FacilityPhone": "...",
      "RECAREA": [{"RecAreaName": "Point Reyes National Seashore"}]
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
**Headers:** Always include `User-Agent: CampsiteScout/1.0`
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

**Availability status values:**

| Status | Meaning |
|--------|---------|
| `Available` | ✅ Open to book |
| `Open` | ✅ Open to book (walk-up or first-come-first-served) |
| `Reserved` | ❌ Already booked |
| `Not Available` | ❌ Closed / not offered |
| `Not Reservable` | ❌ Cannot be reserved online (may be walk-up only) |
| `Not Reservable Management` | ❌ Held by park staff |
| `Open (2 of 2)` | ✅ Group site with quantity — parse the number |

### Wilderness Permit Availability

For backcountry / wilderness permit campgrounds (common at Point Reyes), the endpoint is different:

```
GET https://www.recreation.gov/api/permits/{permitId}/availability/month
  ?start_date={YYYY-MM-01T00:00:00.000Z}
  &commercial_acct=false
```

Permit IDs for Point Reyes wilderness are listed in `facility-ids.md`. The response structure is similar but keyed by entry point / zone rather than campsite.

### Rate Limiting

There's no published rate limit, but be conservative:
- Don't hammer more than 1 request/second
- Cache results within the same session — don't re-fetch the same month twice
- For multi-month windows, make sequential calls with a brief pause

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
  &temperature_unit=fahrenheit
  &wind_speed_unit=mph
  &precipitation_unit=inch
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
    "temperature_2m_max": [68.2, 72.1, 58.4, ...],
    "temperature_2m_min": [51.8, 54.3, 47.2, ...],
    "precipitation_sum": [0.0, 0.0, 0.42, ...],
    "windspeed_10m_max": [12.3, 8.7, 18.2, ...]
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

Wind over **25 mph** is worth flagging for camping — mention it in the output:
`💨 Winds up to {X} mph — exposed sites may be rough`

---

## 4. Recreation.gov Direct Links

Use these URL patterns to generate booking links:

| Type | URL Pattern |
|------|-------------|
| Campground page | `https://www.recreation.gov/camping/campgrounds/{facilityId}` |
| Campground availability calendar | `https://www.recreation.gov/camping/campgrounds/{facilityId}/availability` |
| Permit page | `https://www.recreation.gov/permits/{permitId}` |
| Specific campsite | `https://www.recreation.gov/camping/campsites/{campsiteId}` |
