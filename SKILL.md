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

**Repo path.** Every command below runs from the repo checkout, written as `<REPO>`. On Jamal's main Mac it is `/Users/jamal/Documents/campsitescout`; on the JamBot Mac mini it is `/Users/jambot/.openclaw/workspace/campsiterecon`. Substitute the one for the machine you are on; never invent a third.

## Hard rules — read these before replying in any mode

1. **Never build, guess, or recall a Recreation.gov link.** The only links you may send are strings copied verbatim from the JSON: `reservation_url`, `site_details.<id>.url`, `sample_sites[].url`. Do not construct `/camping/campgrounds/<id>` yourself, do not use ids from memory, and do not use `references/facility-ids.md` to make links — that file is for developers adding presets.
2. **Never guess a facility id or a campground name.** Use `name` as the row label (in Mode 1 that is the camp: "Sky Camp", "Coast Camp"…). When `official_name` differs, add it once as a qualifier ("Sky Camp (Point Reyes National Seashore Campground)"), never as a replacement — the four Point Reyes camps share one `official_name`. If a search result has `rec_area`, say it ("Lost Claim — Stanislaus NF, outside the park") because free-text search is fuzzy and returns campgrounds near the query, not only inside it.
3. **`available_dates` are nights.** "2026-10-09" means the night of Fri Oct 9 → checkout Sat morning. `--end` is the last *night*, so checkout is the morning after it. A weekend needs two nights (Fri + Sat). `contiguous: true` means at least one single site has two consecutive open nights; `windows_by_site_id` lists the exact `[first_night, checkout]` pairs per site. Two different sites open on two different nights is **not** contiguous — say "one-night openings".
4. **"Unreachable" is not "full".** If `unreachable` or `warnings` is non-empty, say which camps could not be checked and why. A rate-limit warning names the time before which retrying is pointless — do **not** offer to "try again now"; every early request extends the block. Never tell the user those camps are booked.
4b. **Respect `stay_rules`, including the policy.** When present, `min_nights` / `min_weekend_nights` / `min_holiday_weekend_nights` are Rec.gov's minimum stays and each has a `*_policy`: `strict` means Rec.gov refuses a shorter booking ("1 night open, but Kirk Creek requires 3 on holiday weekends — not bookable"); `soft` / `softAny` (or any other value, e.g. "Ignore Holidays") means a shorter orphan night *may* still go through at checkout ("1 night open; Kirk Creek prefers 2-night stays, so it may or may not let you book just the one"). Never call a non-strict minimum "not bookable".
5. **Group, boat-in and equestrian sites are not ordinary campsites.** Check `campsite_type` in `site_details` / `sample_sites`; if the only open sites say `GROUP`, `BOAT`, or `HORSE`/`EQUESTRIAN`, say so ("Wildcat — group site only").
6. **California State Parks are not on Recreation.gov** (Pfeiffer Big Sur, Andrew Molera, Limekiln, Julia Pfeiffer Burns, Mt Tam, Samuel P. Taylor, Henry Cowell, Butano, Angel Island). If asked, say they book through reservecalifornia.com and this tool cannot check them.
7. Run the command exactly as written for the mode. No extra flags, no editing paths.

## API key — handling the "no key found" error

`main.py` looks up the RIDB key in this order: the 1Password-synced cache `~/.campsitescout/ridb_api_key` (Mac mini only; written by `deploy/fetch_ridb_key.sh`, refreshed automatically — if search reports `HTTP 401` there, tell the user the 1Password item `recreation_gov_api` needs the current key, do not ask them to paste it) → macOS Keychain (service `recreation-gov-api`, also `recreation_gov_api`) → Windows Credential Manager → `RIDB_API_KEY` or `REC_GOV_API_KEY` env var → hardcoded constant `_HARDCODED_API_KEY_FALLBACK` in `main.py`. Only **Mode 2 / Mode 3 (`--search`) and `--verify`** need it — Rec.gov's availability endpoints are keyless, so Mode 1 runs without one. If it is missing where needed, `main.py` prints a JSON error and exits 1.

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
> **1.** All preconfigured Bay Area campsites for this coming weekend (with weather).
> **2.** A specific location and date range — I'll return every open campground as a clean list.
> **3.** Watch a location on a recurring schedule (daily cron, notifies only when sites open).
>
> Reply `1`, `2`, or `3` (or just tell me the location + dates).

Do not run anything until the user picks. If they already gave enough info in the invocation to skip the question (e.g. "check Yosemite July 3–5"), skip straight to mode 2. If they say "watch", "keep checking", "daily", "notify me", or "alert me", skip straight to mode 3.

---

## Mode 1 — Weekend presets

Run **exactly one** of these. Do not run both. Do not add flags.

```
cd <REPO> && ./.venv/bin/python main.py
```

Only pass `--location` if the user named a specific preset:
```
cd <REPO> && ./.venv/bin/python main.py --location [point_reyes|big_sur|pinnacles|kings_canyon|sequoia]
```

Only pass `--date YYYY-MM-DD` if the user asked for a weekend other than "this weekend" (pass the Friday; a Sat/Sun date snaps back to its Friday and a `warnings` line says so). Run on a Friday, "this weekend" means the *following* weekend. Always state `weekend_start` in the reply so the user knows which weekend was checked.

Presets: `point_reyes` = Sky, Coast, Glen, Wildcat camps (all one Rec.gov campground, booked like any campsite — **not** a permit); `big_sur` = Kirk Creek, Plaskett Creek, Ponderosa (the Forest Service camps — State Parks aren't checkable); `pinnacles`; `kings_canyon`; `sequoia`.

**Output is a JSON array of location reports.** For each location:
- `nights` — the three nights checked (Fri, Sat, Sun)
- `available` — any site open on any of those nights
- `sites[]` — each with `name`, `official_name`, `loop`, `available_dates` (nights), `contiguous`, `windows_by_site_id`, `site_details` (per open site: `site` label, `loop`, `campsite_type`, `min_people`/`max_people`, `url`), `stay_rules`, `reservation_url`, `permit_required`
- `unreachable[]`, `warnings[]` — camps that could not be checked, a loop that matched nothing, a month Rec.gov listed no sites for; see hard rule 4
- `weather` — Fri/Sat/Sun forecast for the location's reference point (Point Reyes: Bear Valley; Big Sur: the coast near Kirk Creek; Kings Canyon: Grant Grove, ~2,000 m; Sequoia: Lodgepole, ~2,050 m). Cedar Grove (Sentinel/Moraine/Sheep Creek) and the Foothills camps (Potwisha/Buckeye Flat) sit 600–1,400 m lower and warmer — say "forecast for Grant Grove / Lodgepole" when presenting those. Missing days (all of them beyond ~14 days out, or just Sunday at 12–13 days out) mean "no forecast yet for that day" — say so, don't invent one

**Present as:**
- Lead with what's open, per camp, naming the nights. Star ⭐ camps with `contiguous: true` (a Fri+Sat or Sat+Sun pair exists).
- A camp with one open night is a one-night trip — say so, don't call it "the weekend".
- **First reply: clean availability only — no booking links per line.** Show the 3-day weather after the availability list for each location.
- If the user asks for links, follow with a separate compact `Booking links:` section using `reservation_url` for the campground and, when they want a specific site, `site_details.<id>.url`. Copy them verbatim.
- If nothing is open anywhere, say so and still show weather. If `unreachable` is non-empty, list those camps as "couldn't check".

Example:
```
⭐ Coast Camp — Fri + Sat nights (3 sites)
   Sky Camp — Sat night only
   Glen, Wildcat — full
   Couldn't check: (none)

🌤 Point Reyes
Fri: 16°C / 8°C · Overcast
Sat: 15°C / 10°C · Overcast
Sun: 13°C / 9°C · Drizzle 🌧
```

---

## Mode 2 — Location search

Required: location name + start date + end date. Ask for whichever is missing, then run **exactly this command** with no extra flags:

```
cd <REPO> && ./.venv/bin/python main.py --search "<LOCATION>" --start YYYY-MM-DD --end YYYY-MM-DD
```

Cross-month ranges work (e.g. `--start 2026-07-30 --end 2026-08-02`). A 15-day range over ~40 campgrounds takes 20–40 seconds; that's normal.

**Output is a single JSON object.** Top level: `anchor` (the rec area the query resolved to, e.g. "Yosemite National Park" — results are sorted by distance from it and keyword matches more than 150 km away are listed in `skipped_far[]` instead of being checked), `facilities_total` (how many facilities RIDB matched, including ones skipped as too far), `facilities_scanned` (how many were actually checked), `skipped_far[]`, `unreachable[]`, `partial[]` (a month that couldn't be checked for a facility), `warnings[]`, `results[]`. `sample_sites` puts any site with a 2-night window first, so when `contiguous` is true the first sample site is the one to link. Each result: `name`, `official_name`, `facility_id`, `rec_area`, `distance_km`, `available_dates` (nights), `open_site_count`, `sample_sites[]` (up to 5 sites with the most open nights: `site`, `loop`, `campsite_type`, `min_people`/`max_people`, `dates`, `url`), `stay_rules`, `reservation_url`, `contiguous`.

**First reply — availability only, no links, no tables.** Telegram doesn't render Markdown tables, so present as a plain bullet list, contiguous first, with the rec area when it isn't the place the user named:

```
⭐ Upper Pines (Yosemite NP) — Oct 3, 4, 5 · 12 sites
⭐ Lost Claim (Stanislaus NF, outside the park) — Oct 3, 4, 5 · 4 sites
   Summerdale (Sierra NF) — Oct 5
Checked 30 of 43 RIDB matches for "Yosemite" (1 skipped as >150 km away).   ← facilities_scanned / facilities_total / len(skipped_far)
```

If the user asks for links, follow with a separate booking section, copying `reservation_url` verbatim (and `sample_sites[].url` if they want a specific site):

```
Booking links:
- Upper Pines: https://www.recreation.gov/camping/campgrounds/232447
- Lost Claim: https://www.recreation.gov/camping/campgrounds/234761
```

Rules:

- Sort `contiguous: true` rows first, star them with ⭐.
- Format `available_dates` compactly: "Jul 3, 4, 5" — not ISO strings.
- **Do not use Markdown tables in Telegram replies.**
- **Default behavior:** first reply with clean availability only. Links only on request, in a separate `Booking links:` section.
- Empty result → `No campgrounds with availability for <query> between <start> and <end>.` — but if `unreachable`/`warnings` is non-empty, say instead that N campgrounds could not be checked and repeat the time the rate-limit warning names; do not offer to retry before it (hard rule 4).
- No weather in this mode. Do not call it.
- Wilderness permits (Yosemite, Half Dome) and State Parks do not appear in search results. Say so if asked.

---

## Mode 3 — Watch (recurring cron)

Wraps mode 2 in a daily crontab job with a rolling date window. Notifies only when the search returns at least one open site — no notification on empty results (a lack of availability isn't actionable; the user wants a campsite, not a status report).

**Required from the user:**
- `location` — free-text, same as mode 2
- `window` — how many days out to scan, e.g. "next 30 days" (default 30 if unspecified)
- `time of day` — when the job runs, e.g. "8am" (default `0 8 * * *` if unspecified)

Ask for whichever is missing. Do not assume location.

**Prerequisite check.** Before installing, find `jq` — the cron line uses it to gate notifications, and cron's PATH is only `/usr/bin:/bin`, so the absolute path must be substituted:
```
command -v jq || brew install jq && command -v jq
```
Use the printed path for `<JQ>` below (`/usr/bin/jq` on recent macOS, `/opt/homebrew/bin/jq` if installed via Homebrew).

**The cron line.** Substitute `<REPO>`, `<LOCATION>`, `<WINDOW>` (integer days) and `<JQ>`. The `\%` escapes are required — bare `%` is a newline in crontab. It uses the repo's own virtualenv Python; the system `python3` does not have the dependencies installed. The Keychain lookup works under cron (it does not rely on `$USER`).

```
0 8 * * * cd <REPO> && ./.venv/bin/python main.py --search "<LOCATION>" --start $(date -v+1d +\%Y-\%m-\%d) --end $(date -v+<WINDOW>d +\%Y-\%m-\%d) 2>>/tmp/campsitescout.err | tee -a /tmp/campsitescout.log | <JQ> -e '.results | length > 0' >/dev/null && /usr/bin/osascript -e 'display notification "Open sites found for <LOCATION> — check /tmp/campsitescout.log" with title "🏕 Campsite Scout"'
```

What it does, left to right:
1. `cd` into the repo so relative paths resolve.
2. Run mode 2 with a rolling window starting tomorrow.
3. `tee` the JSON to `/tmp/campsitescout.log` (append) so the user can read full results.
4. `jq -e '.results | length > 0'` — exits non-zero if `results[]` is empty, killing the chain.
5. On non-empty, `osascript` fires a macOS notification.

A run that was rate-limited writes a `warnings` entry into the log but does not notify — mention that the log is where to look if notifications go quiet. Crashes go to `/tmp/campsitescout.err`.

**Two variants to offer.** If the user wants at least two nights, gate on `contiguous` instead so a lone orphan night doesn't page them: replace `'.results | length > 0'` with `'[.results[] | select(.contiguous)] | length > 0'`. To put names in the banner, add `$(<JQ> -r '[.results[].name] | join(", ")' /tmp/campsitescout.log | tail -1)` into the notification text.

**Known limitation to state up front:** the watch is stateless — while an opening persists it notifies again every day. Deduplicating against the previous run (camply's set-diff pattern, tracked in docs/camply-attribution.md) is not implemented yet.

**Install it.** Append the line without clobbering the user's existing crontab:
```
( crontab -l 2>/dev/null; echo '<THE CRON LINE ABOVE>' ) | crontab -
```
Then verify with `crontab -l`.

**Remove it.** Tell the user: `crontab -e`, delete the line, save.

**Caveats to surface to the user, every time:**
- Cron only fires while the machine is awake and logged in. A closed lid = no checks. For 24/7 watching, this needs to live on a server or GitHub Actions — say so and stop; don't try to set that up from here.
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
| Names a California State Park | none — explain reservecalifornia.com |
| Ambiguous — just "camping?" | Ask the three-option question above |
