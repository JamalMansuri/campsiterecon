---
name: campsite-recon
description: >
  Check campsite availability and weekend weather for Bay Area locations.
  Use when the user asks about camping, open sites, wilderness permits,
  or spur-of-the-moment weekend trips near the Bay Area.
metadata:
  openclaw:
    emoji: "🏕"
    requires:
      bins: [python3]
---

# Campsite Recon

Checks Recreation.gov availability + Open-Meteo weather for the upcoming weekend.
Returns structured JSON — surface the open sites with reservation links, star contiguous ones, show weather.

## Commands

Check all supported locations for the upcoming weekend:
```
python /Users/jamal/Documents/campsitescout/main.py
```

Check a specific location:
```
python /Users/jamal/Documents/campsitescout/main.py --location [point_reyes|big_sur]
```

Check a specific weekend (pass the Friday date):
```
python /Users/jamal/Documents/campsitescout/main.py --location point_reyes --date YYYY-MM-DD
```

## Output format

Returns a JSON array of location reports. For each location:
- `available` — boolean, any sites open this weekend
- `sites` — array of campsites, each with:
  - `available_dates` — ISO dates with open availability
  - `reservation_url` — direct link to book on recreation.gov
  - `contiguous` — true if available for 2+ consecutive nights (mark these with ⭐)
  - `permit_required` — whether it's a wilderness permit system
- `weather` — Friday/Saturday/Sunday forecast in Celsius
- `weekend_start` / `weekend_end` — date range checked

## How to present results

Lead with what's open. Format as:

⭐ Sky Camp — Fri + Sat available → recreation.gov/permits/4675310
   Coast Camp — Sat only → recreation.gov/permits/4675311

🌤 Weather @ Point Reyes
Fri: 16°C / 10°C · Mainly clear
Sat: 18°C / 11°C · Clear
Sun: 14°C / 9°C · Light drizzle 🌧

If nothing is available anywhere, say so and still show the weather.
Wilderness permit sites (permit_required: true) use /permits/ links, not /camping/.
