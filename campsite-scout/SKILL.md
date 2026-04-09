---
name: campsite-scout
description: >
  Campsite availability surveillance for Recreation.gov — use this skill whenever the user asks about
  campsite availability, open permits, or camping options. Triggers on messages like "check Point Reyes
  this weekend", "any open sites near Big Sur next month?", "find me a campsite in Yosemite", "is
  [campground] available", or any message asking about camping availability, open dates, or wilderness
  permits. Always use this skill for campsite-related queries even if phrased casually.
---

# Campsite Scout

Read-only surveillance layer over Recreation.gov. No booking — GET calls only. Returns availability + weather so the user can act fast.

**API key:** `REDACTED_API_KEY`
**Reference files:** `references/facility-ids.md` (known IDs) · `references/api-endpoints.md` (full schemas)

---

## Step 1 — Parse intent

Extract **location** + **date window** from the user's message.
- "This weekend" = upcoming Fri–Sun. Resolve all relative dates against today.
- Default window if unspecified: next 30 days.

---

## Step 2 — Resolve facility IDs

Check `references/facility-ids.md` first. If the location is there, use those IDs directly — skip the RIDB search.

Otherwise search RIDB:
```
GET https://ridb.recreation.gov/api/v1/facilities?query={name}&radius=30&facilitytype=Campground&limit=10&apikey={key}
```
If empty, search `/recareas?query={name}` then drill into `/recareas/{id}/facilities`. Extract `FacilityID`, `FacilityName`, `FacilityLatitude`, `FacilityLongitude`. Cap at 5 facilities.

---

## Step 3 — Check availability

**Standard campgrounds:**
```
GET https://www.recreation.gov/api/camps/availability/campground/{facilityId}/month
    ?start_date={YYYY-MM-01T00:00:00.000Z}
    User-Agent: CampsiteScout/1.0
```
Open statuses: `Available`, `Open`. Closed: `Reserved`, `Not Available`, `Not Reservable`.

**Wilderness permits** (e.g. Point Reyes backcountry — check `references/facility-ids.md` for permit IDs):
```
GET https://www.recreation.gov/api/permits/{permitId}/availability/month
    ?start_date={YYYY-MM-01T00:00:00.000Z}&commercial_acct=false
```
Check `remaining` field per date.

Per date: count available sites, note Fri/Sat nights, flag availability <14 days out as likely cancellation. For multi-month windows, call once per calendar month and merge.

---

## Step 4 — Weather

```
GET https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}
    &daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max
    &temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch
    &timezone=auto&forecast_days=14
```
No key needed. Only surface dates within the user's window.

WMO → emoji: `0`☀️ `1-3`🌤️ `45/48`🌫️ `51-67`🌧️ `71-77`❄️ `80-82`🌦️ `95-99`⛈️. Flag winds >25mph.

---

## Step 5 — Format (Telegram markdown, ≤40 lines)

Lead with the headline finding — open sites up top, fully booked as a footnote.

```
🏕️ *{Area}* — Campsite Scout
_{date window}_

📍 *{Facility Name}* _(permit / drive-in)_
Fri Apr 11 — ✅ {N} site(s) open  ⚡ _cancellation_ (if <14 days out)
Sat Apr 12 — ❌ Full
🔗 recreation.gov/camping/campgrounds/{facilityId}
   (permits: recreation.gov/permits/{permitId})

—
🌤️ *Weather @ {location}*
Fri Apr 11: {max}°F / {min}°F · {label} {emoji}
Sat Apr 12: {max}°F / {min}°F · {label} {emoji}  🌧️ {precip}" (if >0.1)

—
💡 {1–2 lines: what's open, why, urgency signal}
```

If nothing is open anywhere: still show weather + suggest next available window.

---

## Edge cases

- **404 on availability** → switch to permit endpoint; note it in response.
- **No RIDB results** → widen radius to 50mi or ask user to clarify the name.
- **Not on Recreation.gov** (state parks, walk-up only) → say so; suggest ReserveCalifornia.
- **General area** ("Yosemite") → top 3 by popularity per `references/facility-ids.md`.
