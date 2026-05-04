# recon/parser.py

Weekend-mode response normalizer. Turns raw Rec.gov JSON into a flat `CampsiteResult` for one camp + one weekend. Search mode has its own equivalent inline in [search.md](search.md).

[Source](../recon/parser.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def parse(response: dict, camp: Camp, friday: date) -> CampsiteResult
```

`response` is the tagged dict from [availability.md](availability.md). `parse` dispatches on `response["type"]` to one of two private parsers.

## The two response shapes

Rec.gov returns campground availability and permit availability in completely different JSON shapes. The parser handles both:

| Endpoint | Path through JSON | Open test |
|---|---|---|
| Campground | `campsites[campsite_id].availabilities[date]` | `is_available(status)` (denylist) |
| Permit | `payload.availability[date].remaining` | integer `> 0` |

For campgrounds, the parser validates the raw response against [`RawCampgroundResponse`](models.md) at the boundary, then iterates `response.campsites.items()` to preserve the outer `campsite_id` key (used by the auto-cart booker). For permits, the per-site dimension doesn't exist — `sites_by_id` and `windows_by_site_id` stay empty.

The output `CampsiteResult` shape is identical for both.

## Filtering: denylist, not allowlist

`is_available(status)` (defined in [models.md](models.md)) returns `False` for the full Rec.gov denylist: `Reserved`, `Not Available`, `Not Reservable`, `Not Reservable Management`, `Not Available Cutoff`, `Lottery`, `Open`, `NYR`, `Closed`.

**`"Open"` is in the denylist on purpose.** It means the campground is open for the season but the site itself is walk-up-only. Treating it as available used to cause false positives. See [camply-attribution.md](camply-attribution.md).

## The permit URL gotcha

`_reservation_url(camp)` decides the booking URL based on `camp.permit_id`, **not** the response type:

```python
if camp.permit_id:
    return f".../permits/{camp.permit_id}"
return f".../camping/campgrounds/{camp.facility_id}"
```

This matters because Rec.gov sometimes serves Point Reyes data through the campground endpoint now (see [availability.md](availability.md)). If we keyed the URL off the response type, those camps would get a `/camping/` URL — which would 404 the user. By keying off `permit_id`, the URL stays correct regardless of which endpoint the data came from.

This is the one rule a future LLM is most likely to break when refactoring. Don't.

## Contiguous detection + per-site windows

Both the `contiguous` flag and the new `windows_by_site_id` field are powered by [`consecutive_nights()`](windows.md), with `nights=2` for weekend mode:

- `contiguous` — `bool(consecutive_nights(flat, 2))`. True if any 2 adjacent nights exist anywhere in the Fri/Sat/Sun window. Replaces the prior hardcoded "Fri+Sat or Sat+Sun" check.
- `windows_by_site_id` — for each campsite with at least one viable 2-night window, the list of `(start, checkout)` ISO date pairs. Empty for sites with only single-night availability. This is the field the Phase 3 auto-cart matcher will read.

The algorithm comes from banool — see [banool-attribution.md](banool-attribution.md). The function generalizes to arbitrary `nights`, so the matcher can call it directly with values from `targets.json`.

Search mode also uses `consecutive_nights`, but with looser inputs (full search range, not weekend window) and without per-site detail (search merges across sites). See [search.md](search.md).

## Upstream / downstream

- **Called by**: [main.md](main.md) (`_run_location`)
- **Input from**: [availability.md](availability.md)
- **Outputs**: `CampsiteResult` from [models.md](models.md), wrapped into a `LocationReport` by main.py

## Filtering rules

Dates outside the Fri/Sat/Sun window are dropped silently. A camp with zero open dates still produces a `CampsiteResult` (with empty `available_dates` and `contiguous=False`) — main.py decides whether to mark the location as available based on `any(s.available_dates ...)`.
