# recon/availability.py

Weekend-mode endpoint dispatcher. One function: pick which Rec.gov endpoint to ask, attach the facility's metadata, and tag the result so the parser knows which response shape to expect.

[Source](../recon/availability.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def fetch_camp_availability(client: RecGovClient, camp: Camp, friday: date) -> dict | None
```

Returns one of three things:

```python
{"type": "campground", "data": {...}, "meta": {...} | None, "missing_months": [...]}
{"type": "permit",     "data": {...}, "meta": {...} | None, "missing_months": [...]}
None                                                          # nothing came back at all
```

`meta` is Rec.gov's own facility record (`/api/camps/campgrounds/{id}`), used by the parser for `official_name`. `missing_months` names any month whose fetch failed.

## Logic

1. Work out which months the three nights touch — `months_spanned(friday, friday+2)`. A weekend like Fri Oct 30 / Sat Oct 31 / Sun Nov 1 needs **two** months; fetching only the Friday's month (the pre-2026-09 behaviour) silently never checked the Sunday night.
2. Fetch each month with `campground_month()` (cached, paced). Merge the `campsites` dicts — per-site `availabilities` are unioned.
3. If at least one month answered, tag it `campground` and return, listing any failed months in `missing_months`. main.py turns that into a `warnings[]` line.
4. Otherwise, if `camp.permit_id` is set, do the same with `permit_month()` (divisions' `date_availability` unioned) and tag it `permit`.
5. If nothing answered, return `None`. **main.py records the camp in `unreachable[]`** — a `None` here means "couldn't check", never "full".

## The permit fallback today

No preset currently has a `permit_id` (Point Reyes turned out to be an ordinary campground, see [config.md](config.md)), so step 3 is dormant. It stays because genuine wilderness permits (Yosemite 445859) will need it, and [parser.md](parser.md) now handles the 2026 division-keyed permit shape.

## Upstream / downstream

- **Called by**: [main.md](main.md) (`_run_location` loop, weekend mode only)
- **Calls**: [api_client.md](api_client.md) (`campground_month`, `permit_month`, `campground_meta`)
- **Output consumed by**: [parser.md](parser.md)

## Not used by search mode

[search.md](search.md) only hits the campground endpoint directly. Permit-only facilities are invisible to search mode by design.
