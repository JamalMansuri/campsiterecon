---
name: campsite-recon
description: >
  Check campsite and wilderness permit availability. Three modes: preset
  Bay Area weekend scan (with weather), free-text search of any location
  over a specific date range, or a recurring watch that notifies only
  when sites open. Use when the user mentions camping, open sites,
  wilderness permits, a weekend trip, or asks to keep checking / be
  notified.
metadata:
  openclaw:
    emoji: "🏕"
    requires:
      bins: [python3]
---

# Campsite Recon

## API key — handling the "no key found" error

`main.py` looks up the RIDB key in this order: macOS Keychain → Windows Credential Manager → `RIDB_API_KEY` or `REC_GOV_API_KEY` env var → hardcoded constant `_HARDCODED_API_KEY_FALLBACK` in `main.py`. If all are empty it returns a JSON error and exits 1.

**If you (the LLM) see that error, do not run any commands until you've asked the user which platform they're on and walked them through one of these.** The user may not be a developer — pick the easiest option for their OS, ask them to paste their key once, and run the command for them.

- **macOS** — store in Keychain (recommended):
  ```
  security add-generic-password -a "$USER" -s recreation-gov-api -w '<KEY>'
  ```
  Verify: `security find-generic-password -a "$USER" -s recreation-gov-api -w`

- **Windows** — store in Credential Manager (recommended). Run in PowerShell or cmd:
  ```
  cmdkey /generic:recreation-gov-api /user:rec /pass:<KEY>
  ```
  Verify: `cmdkey /list:recreation-gov-api`. The Python loader reads it via `advapi32.CredReadW`, no extra deps.

- **Any OS, quickest** — env var for the current shell only. Either name works:
  ```
  export RIDB_API_KEY='<KEY>'        # macOS/Linux  (or REC_GOV_API_KEY)
  setx RIDB_API_KEY "<KEY>"          # Windows, new shells only  (or REC_GOV_API_KEY)
  ```

- **Last resort, non-developers** — open `main.py`, find `_HARDCODED_API_KEY_FALLBACK = ""`, paste the key between the quotes. Warn the user **not to commit the file** after doing this; suggest `git update-index --skip-worktree main.py` if they're version-controlling.

The user gets a key at `https://ridb.recreation.gov/profile` (free, instant). Never paste a real key into chat logs, commits, or this SKILL.md.

---

## First message — always ask which mode

When this skill is invoked, your **first** response must be exactly these three options and nothing else:

> Which do you want?
>
> **1.** All preconfigured Bay Area campsites/permits for this coming weekend (with weather).
> **2.** A specific location and date range — I'll return every open campground as a clean list.
> **3.** Watch a location on a recurring schedule (daily cron, notifies only when sites open).
>
> Reply `1`, `2`, or `3` (or just tell me the location + dates).

Do not run anything until the user picks. If they already gave enough info in the invocation to skip the question (e.g. "check Yosemite July 3–5"), skip straight to mode 2. If they say "watch", "keep checking", "daily", "notify me", or "alert me", skip straight to mode 3.

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
- **First reply: clean availability only — no booking links per line.** Show the 3-day weather after the availability list for each location.
- If the user asks for links, follow with a separate compact `Booking links:` section. Permit sites (`permit_required: true`) must use `/permits/{id}` URLs, not `/camping/`.
- If nothing is open anywhere, say so and still show weather.

Example:
```
⭐ Coast Camp — Fri+Sat+Sun
   Pfeiffer Big Sur — Sat only

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

**First reply — availability only, no links, no tables.** Telegram doesn't render Markdown tables, so present as a plain bullet list, contiguous first:

```
⭐ Pines Stanislaus — Jul 3, 4, 5
⭐ Lost Claim — Jul 3, 4, 5
   Summerdale — Jul 5
```

If the user asks for links, follow with a separate booking section:

```
Booking links:
- Pines Stanislaus: https://www.recreation.gov/camping/campgrounds/10180062
- Lost Claim: https://www.recreation.gov/camping/campgrounds/234761
- Summerdale: https://www.recreation.gov/camping/campgrounds/233837
```

Rules:

- Sort `contiguous: true` rows first, star them with ⭐.
- Format `available_dates` compactly: "Jul 3, 4, 5" — not ISO strings.
- **Do not use Markdown tables in Telegram replies.**
- **Default behavior:** first reply with clean availability only.
- Only provide booking links in a second reply if the user asks for them.
- If links are requested, prefer a separate `Booking links:` section instead of attaching a link to every bullet.
- Empty result → `No campgrounds with availability for <query> between <start> and <end>.`
- No weather in this mode. Do not call it.
- Wilderness-permit-only sites (Point Reyes pattern) will not appear — if the user asks about those by name, route them to mode 1 with the matching preset.

---

## Mode 3 — Watch (recurring cron)

Wraps mode 2 in a daily crontab job with a rolling date window. Notifies only when the search returns at least one open site — no notification on empty results (a lack of availability isn't actionable; the user wants a campsite, not a status report).

**Required from the user:**
- `location` — free-text, same as mode 2
- `window` — how many days out to scan, e.g. "next 30 days" (default 30 if unspecified)
- `time of day` — when the job runs, e.g. "8am" (default `0 8 * * *` if unspecified)

Ask for whichever is missing. Do not assume location.

**Prerequisite check.** Before installing, confirm `jq` is available — the cron line uses it to gate notifications:
```
command -v jq >/dev/null || brew install jq
```

**The cron line.** Substitute `<LOCATION>` and `<WINDOW>` (integer days). The `\%` escapes are required — bare `%` is a newline in crontab.

```
0 8 * * * cd /Users/jamal/Documents/campsitescout && /usr/bin/env python3 main.py --search "<LOCATION>" --start $(date -v+1d +\%Y-\%m-\%d) --end $(date -v+<WINDOW>d +\%Y-\%m-\%d) 2>>/tmp/campsitescout.err | tee -a /tmp/campsitescout.log | /opt/homebrew/bin/jq -e '.results | length > 0' >/dev/null && /usr/bin/osascript -e 'display notification "Open sites found for <LOCATION> — check /tmp/campsitescout.log" with title "🏕 Campsite Scout"'
```

What it does, left to right:
1. `cd` into the repo so relative paths resolve.
2. Run mode 2 with a rolling window starting tomorrow.
3. `tee` the JSON to `/tmp/campsitescout.log` (append) so the user can read full results.
4. `jq -e '.results | length > 0'` — exits non-zero if `results[]` is empty, killing the chain.
5. On non-empty, `osascript` fires a macOS notification.

**Install it.** Append the line without clobbering the user's existing crontab:
```
( crontab -l 2>/dev/null; echo '<THE CRON LINE ABOVE>' ) | crontab -
```
Then verify with `crontab -l`.

**Remove it.** Tell the user: `crontab -e`, delete the line, save.

**Caveats to surface to the user, every time:**
- Cron only fires while the laptop is awake and logged in. A closed lid = no checks. For 24/7 watching, this needs to live on a server or GitHub Actions — say so and stop; don't try to set that up from here.
- Notification stops at a macOS banner. To pipe results into Telegram instead, swap the final `osascript` for a `curl` to a bot's `sendMessage` endpoint — offer this if the user asks.
- The log at `/tmp/campsitescout.log` grows unbounded. Mention it; don't auto-rotate.

**After installing, reply with:**
- The exact cron line that was installed (so the user can sanity-check).
- The schedule in plain English ("daily at 8:00 AM, scanning the next 30 days").
- The two caveats above (awake-only, log location).

---

## Routing cheatsheet

| User says... | Mode |
|---|---|
| "this weekend", "next weekend", names a preset | 1 |
| Gives a specific date range > 2 weeks out | 2 |
| Names a location not in presets (Yosemite, Tahoe, Joshua Tree, Zion...) | 2 |
| Mentions a holiday weekend months ahead | 2 |
| "watch", "keep checking", "daily", "notify me", "alert me when..." | 3 |
| Ambiguous — just "camping?" | Ask the three-option question above |
