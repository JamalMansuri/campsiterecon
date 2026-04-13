---
name: campsite-recon
description: >
  Check campsite and wilderness permit availability. Two modes: preset
  Bay Area weekend scan (with weather), or free-text search of any
  location over a specific date range. Use when the user mentions
  camping, open sites, wilderness permits, or a weekend trip.
metadata:
  openclaw:
    emoji: "🏕"
    requires:
      bins: [python3]
---

# Campsite Recon

## First message — always ask which mode

When this skill is invoked, your **first** response must be exactly these two options and nothing else:

> Which do you want?
>
> **1.** All preconfigured Bay Area campsites/permits for this coming weekend (with weather).
> **2.** A specific location and date range — I'll return every open campground as a table.
>
> Reply `1` or `2` (or just tell me the location + dates).

Do not run anything until the user picks. If they already gave enough info in the invocation to skip the question (e.g. "check Yosemite July 3–5"), skip straight to mode 2.

---

## Mode 1 — Weekend presets

Run **exactly one** of these. Do not run both. Do not add flags.

```
python /Users/jamal/Documents/campsitescout/main.py
```

Only pass `--location` if the user named a specific preset:
```
python /Users/jamal/Documents/campsitescout/main.py --location [point_reyes|big_sur|pinnacles|kings_canyon|sequoia]
```

Only pass `--date YYYY-MM-DD` if the user asked for a weekend other than "this weekend" (pass the Friday).

**Output is a JSON array of location reports.** For each location:
- `available` — any sites open
- `sites[]` — each with `name`, `available_dates`, `reservation_url`, `contiguous`, `permit_required`
- `weather` — Fri/Sat/Sun forecast

**Present as:**
- Lead with what's open. Star ⭐ contiguous sites.
- Permit sites (`permit_required: true`) — use `/permits/{id}` URLs, not `/camping/`.
- Show the 3-day weather after the availability list for each location.
- If nothing is open anywhere, say so and still show weather.

Example:
```
⭐ Coast Camp — Fri+Sat+Sun → recreation.gov/permits/4675311
   Pfeiffer Big Sur — Sat only → recreation.gov/camping/campgrounds/233394

🌤 Point Reyes
Fri: 16°C / 8°C · Overcast
Sat: 15°C / 10°C · Overcast
Sun: 13°C / 9°C · Drizzle 🌧
```

---

## Mode 2 — Location search

Required: location name + start date + end date. Ask for whichever is missing, then run **exactly this command** with no extra flags:

```
python /Users/jamal/Documents/campsitescout/main.py --search "<LOCATION>" --start YYYY-MM-DD --end YYYY-MM-DD
```

Cross-month ranges work (e.g. `--start 2026-07-30 --end 2026-08-02`).

**Output is a single JSON object with a `results[]` array.** Each result has `name`, `facility_id`, `available_dates`, `reservation_url`, `contiguous`.

**Present as a Markdown table, sorted contiguous-first:**

| Campground | Dates | Booking | Contiguous |
|---|---|---|---|
| Pines Stanislaus | Jul 3, 4, 5 | [book](https://www.recreation.gov/camping/campgrounds/10180062) | ✅ |
| Lost Claim | Jul 3, 4, 5 | [book](https://www.recreation.gov/camping/campgrounds/234761) | ✅ |
| Summerdale | Jul 5 | [book](https://www.recreation.gov/camping/campgrounds/233837) |  |

Rules:
- Sort `contiguous: true` rows first.
- Format `available_dates` compactly: "Jul 3, 4, 5" — not ISO strings.
- Use `[book](url)` links, not raw URLs.
- Empty table → "No campgrounds with availability for <query> between <start> and <end>."
- No weather in this mode. Do not call it.
- Wilderness-permit-only sites (Point Reyes pattern) will not appear — if the user asks about those by name, route them to mode 1 with the matching preset.

---

## Routing cheatsheet

| User says... | Mode |
|---|---|
| "this weekend", "next weekend", names a preset | 1 |
| Gives a specific date range > 2 weeks out | 2 |
| Names a location not in presets (Yosemite, Tahoe, Joshua Tree, Zion...) | 2 |
| Mentions a holiday weekend months ahead | 2 |
| Ambiguous — just "camping?" | Ask the two-option question above |
