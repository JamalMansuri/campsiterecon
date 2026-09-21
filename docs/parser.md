# recon/parser.py

Weekend-mode response normalizer plus the shared pieces search mode borrows: the campsite collector and the three URL builders. Turns raw Rec.gov JSON into a flat `CampsiteResult` for one camp + one weekend.

[Source](../recon/parser.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def parse(response: dict, camp: Camp, friday: date) -> CampsiteResult
def collect_open_sites(response: RawCampgroundResponse, targets: set[date], loop: str | None = None)
        -> dict[str, tuple[RawSiteAvailability, set[date]]]
def permit_open_dates(raw: dict) -> dict[date, int]
def campground_url(facility_id) / site_url(campsite_id) / permit_url(permit_id) -> str
```

`response` is the tagged dict from [availability.md](availability.md). `parse` dispatches on `response["type"]`.

## URL builders — the only place links are made

Every Rec.gov link in the output comes from `campground_url`, `site_url` or `permit_url`. [SKILL.md](../SKILL.md) forbids the runtime LLM from constructing links itself; if you need a new link shape, add a builder here and a field in [models.md](models.md), don't format it inline somewhere else.

`_reservation_url(camp)` keys off `camp.permit_id`, not the endpoint that answered — a permit-system camp books through `/permits/` even if availability came from elsewhere. No preset exercises this today, but it's the correct rule.

## `validate_campground` — boundary validation that degrades per site

`RawCampgroundResponse.model_validate` on the whole payload meant one campsite record with a null where a string/int was expected aborted the entire run. `validate_campground(raw)` validates each site separately, skips (and counts) the ones that fail, and `RawSiteAvailability`'s before-validators coerce the common drift (null booleans, `""` counts, non-string labels, null statuses) to defaults. The count surfaces as `skipped_sites` and a `warnings[]` line.

## `site_category` — group and boat-in

`site_category(site)` returns `"boat_in"`, `"group"` or `None` from Rec.gov's fixed `campsite_type` vocabulary (case- and whitespace-insensitive): `BOAT IN` / `MOORING` / `ANCHORAGE`, or any type containing the word `BOAT` → boat-in; any type containing the word `GROUP` → group; boat wins when both apply. The site label plays two limited roles. It **refines a GROUP type**: Rec.gov types Point Reyes' boat-only group beaches as plain `GROUP TENT ONLY AREA NONELECTRIC` with the access only in the label ("TOMALES BEACH GROUP, BOAT ONLY, 15-25 people"), so a GROUP-typed site whose label contains the word `BOAT` is boat-in. And it **stands in for a missing type** (`008 GROUP`, `BOAT A, 1-6 people`). It never turns an ordinarily-typed site into a special one (`HIKE TO` + "BOAT LAUNCH VIEW 4" stays ordinary), and matching is on whole words, so `GROUPER COVE` is not a group site. [search.md](search.md) uses it to skip those sites by default; weekend mode does not.

## `collect_open_sites` — the filter chain

For each campsite in the response, in order:

1. `is_bookable_site()` — drop `hide_external` and day-use sites ([models.md](models.md)).
2. `loop` filter — when `camp.loop` is set, keep only sites whose `loop` matches (case-insensitive, whitespace-trimmed). This is how four Point Reyes presets share one facility.
3. Per date: `is_available(status)` denylist (`"Open"` is **not** bookable), then `date.fromisoformat(dt_str[:10])`, then membership in `targets`.

Sites with no open target date are dropped. Search mode calls this with the whole date range and no loop.

## Output assembly (`_parse_campground`)

- `available_dates` — union of open nights across surviving sites.
- `sites_by_id` / `windows_by_site_id` — per campsite; `windows_by_site_id` only lists sites with a viable 2-night `(first_night, checkout)` window via [`consecutive_nights()`](windows.md).
- `site_details` — same keys, each with `site` label, `loop`, `campsite_type`, and `site_url(campsite_id)`.
- `official_name` — `meta["facility_name"]` from Rec.gov, so the LLM shows "Point Reyes National Seashore Campground" rather than trusting the preset label.
- `stay_rules` — `stay_rules_from_meta(meta)` reads `facility_rules.{minConsecutiveStay, minWeekendStay, minHolidayWeekendStay, maxConsecutiveStay}` **with Rec.gov's `secondary_value` qualifier** (`strict` / `soft` / `softAny`) as `*_policy`. Kirk Creek's 2-night minimum is `softAny` (an orphan night may still book) but its 3-night holiday minimum is `strict`. Surfaced, not enforced — SKILL.md tells the LLM how to phrase each.
- `loop_matched` — `False` when a loop preset matched no campsite of any status; main.py turns that into a warning so a renamed loop can't masquerade as "nothing open".
- `contiguous` — `bool(windows_by_site_id)`: some **single site** has two consecutive open nights. It is deliberately not computed on the union `available_dates` — Fri at site A plus Sat at site B used to be reported as a bookable weekend, which was one of the "says it's available but it isn't" complaints.

## Permit responses

`permit_open_dates` reads the live shape `payload.availability[division_id].date_availability[date].remaining` (summed across divisions) and, defensively, a flat `payload.availability[date].remaining` that has never been observed live. `_parse_permit` intersects those dates with the weekend; `sites_by_id` stays empty and `contiguous` is always `False` because permit dates are trip *start* dates with quota, not nights at a site. Validated only against lottery/day-use-style permits (4675311, Half Dome 234652); NPS wilderness permits such as Yosemite 445859 answer 404 on this endpoint.

## Upstream / downstream

- **Called by**: [main.md](main.md) (`_run_location`), [search.md](search.md) (`collect_open_sites`, URL builders)
- **Input from**: [availability.md](availability.md)
- **Outputs**: `CampsiteResult` from [models.md](models.md)
