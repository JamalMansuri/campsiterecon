# recon/search.py

Free-text location search. Turns "Yosemite, July 3–5" into a list of bookable campgrounds with their open nights, sample sites and where each campground actually is. The whole of Mode 2 lives here.

[Source](../recon/search.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def search(client: RecGovClient, query: str, start: date, end: date, max_results: int = 150) -> SearchReport
def rate_limit_warning(client, unchecked: int) -> list[str]
```

Returns a `SearchReport` (see [models.md](models.md)) with `results[]`, plus `facilities_total` / `facilities_scanned` / `unreachable[]` / `warnings[]` so the LLM can say how complete the scan was.

## Flow

1. **RIDB lookup** — `client.ridb_search_campgrounds(query)` pages through every match (RIDB caps pages at 50 and used to hide Upper/Lower/North Pines behind the old `limit=25`), keeping only `Campground` + `Reservable` + `Enabled` records.
2. **Resolve an anchor** — `client.ridb_search_recarea(query)` picks the first RIDB rec area whose name contains every word of the query and has coordinates ("Yosemite" → Yosemite National Park; "Big Sur" → none). With an anchor, each facility gets `distance_km` and anything beyond 150 km is put in `skipped_far[]` *before* any availability call — that's what keeps a Shasta-Trinity "Camp 4 Group Campground" out of a Yosemite watch (and out of Mode 3 notifications). Without an anchor nothing is filtered.
3. **Months spanned** — `months_spanned(start, end)` (in [windows.md](windows.md)) walks year/month; cross-month and cross-year ranges work.
4. **Per facility, per month** — `client.campground_month()`; responses are cached in the client. A facility whose every month returns `None` goes to `unreachable[]`; one with some months missing goes to `partial[]` with the months named. Neither is "no availability".
5. **Collect sites** — [`collect_open_sites()`](parser.md) with the full date range and no loop filter; per-site date sets are merged across months.
6. **Emit** a `SearchResult` per facility with at least one open night: display name (title-cased only when RIDB shouts), `official_name`, `rec_area` (one cached `/recareas/{id}` call per distinct parent), lat/lon, `distance_km`, `open_site_count`, `stay_rules` (one keyless `/api/camps/campgrounds/{id}` call per facility *with* openings), and `sample_sites` — the 5 sites with the most open nights, each with `campsite_type`, `min/max_people` and a `site_url` deep link. Results are sorted by distance from the anchor. An unreachable facility carries its reason: `"Name (HTTP 404)"`.
7. `warnings[]` gets a line if RIDB itself failed (bad key → HTTP 401/403 used to look like "no campgrounds"), if a later RIDB page failed (list truncated), if malformed campsite records were skipped, or if the client tripped its 429 breaker mid-run.

## Group and boat-in sites are skipped by default

After collecting open sites, `search()` drops every site whose [`site_category()`](parser.md) is `"group"` or `"boat_in"` — from `available_dates`, `open_site_count`, `sample_sites` and the `contiguous` test. A family looking for a campsite cannot book a 7–25-person group site or a beach reachable only by kayak, and before this a facility whose only opening was such a site looked available (and fired the Mode 3 cron gate: "Pines Group Stanislaus" for a Yosemite watch).

Nothing disappears silently:

- `SearchResult.excluded_open_sites` — `{"group": n, "boat_in": m}`, open sites that were not counted.
- `SearchReport.group_or_boat_only` — facilities with openings *only* at such sites; they are not in `results`.
- `SearchReport.site_types` — `"standard"` or `"all"`, so the consumer knows which mode produced the JSON.

`--all-site-types` (→ `include_all_site_types=True`) turns the filter off. Those sites are then counted like any other, and because the person asking for them needs to find them, each result carries `special_open_sites` (`{"group": n, "boat_in": m}`), every `SearchSite` carries `category`, and `_represent_categories` swaps the best site of any open-but-unsampled category into a tail sample slot — never index 0, which stays the site to link when `contiguous` is true. Categories are computed once per facility, after months are merged, so a site open in two months counts once. Equestrian, cabin, yurt and RV-only types are **not** filtered — only what `site_category` names. Weekend mode does not filter at all: its presets are curated (Point Reyes' boat-in loops are simply not presets) and `site_details.campsite_type` carries the information.

## `contiguous` is per site

`any(consecutive_nights(dates, 2) for each open site)` — a 2-night stay has to be at one site. The facility-level union (`available_dates`) can show two consecutive nights that belong to two different sites; that is two one-night trips, and `contiguous` is `False` for it. Same rule as [parser.md](parser.md).

## What search mode deliberately does NOT do

- **No weather.** Open-Meteo's forecast only goes 14 days out.
- **No permit endpoint.** Wilderness permits (Yosemite, Half Dome) won't appear; RIDB `Permit` records are filtered out before scanning.
- **No fine relevance ranking beyond distance.** RIDB's free-text match is fuzzy — "Yosemite" legitimately returns Stanislaus NF, Sierra NF and BLM Merced River campgrounds within 150 km. `rec_area` and `distance_km` are emitted so the LLM can qualify each result rather than pretend they're all inside the park.
- **No facility deduping.** Rare in practice.

## Cost

Each facility costs `len(months_spanned)` availability requests, paced at 0.6 s, plus one unthrottled metadata call per facility with openings. "Yosemite" over one month is ~31 facilities ≈ 12–15 s. Rec.gov answers 429 to bursts; see [api_client.md](api_client.md).

## Upstream / downstream

- **Called by**: [main.md](main.md) when `--search` is present (and `rate_limit_warning` from weekend mode)
- **Calls**: [api_client.md](api_client.md), [parser.md](parser.md)
- **Outputs**: `SearchReport` from [models.md](models.md)
