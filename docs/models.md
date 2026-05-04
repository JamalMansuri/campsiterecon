# recon/models.py

The data contracts. Pydantic models define every JSON shape the program emits, every internal record that flows between modules, and the boundary validation for the raw Rec.gov response.

[Source](../recon/models.py) · Wiki home: [README.md](README.md)

## The output types

```python
class CampsiteResult(BaseModel):       # one camp, one weekend (Mode 1 row)
    name: str
    facility_id: str
    available_dates: list[str]         # ISO dates within the weekend (flat across all sites)
    sites_by_id: dict[str, list[str]]  # {campsite_id: [iso_dates]} — fuel for the auto-cart booker
    windows_by_site_id: dict[str, list[tuple[str, str]]]
                                       # {campsite_id: [(start_iso, checkout_iso), ...]} — viable 2-night stays
    permit_required: bool              # drives reservation_url shape
    reservation_url: str               # /camping/... or /permits/...
    contiguous: bool                   # 2+ consecutive nights of the weekend

class WeatherDay(BaseModel):           # one forecast day
    date: str
    high_c: float
    low_c: float
    rain_mm: float
    wind_kph: float
    condition: str                     # WMO label, e.g. "Drizzle"

class LocationReport(BaseModel):       # Mode 1 top-level, one per location
    location: str
    weekend_start: str                 # Friday ISO
    weekend_end: str                   # Sunday ISO
    available: bool                    # any sites open at all
    sites: list[CampsiteResult]
    weather: dict[str, WeatherDay]     # keys: "friday", "saturday", "sunday"

class SearchResult(BaseModel):         # one facility (Mode 2 row)
    name: str
    facility_id: str
    available_dates: list[str]         # ISO dates within the search range
    reservation_url: str
    contiguous: bool                   # any 2 consecutive days, weekend or not

class SearchReport(BaseModel):         # Mode 2 top-level
    query: str
    start: str
    end: str
    results: list[SearchResult]
```

## The raw-response types (boundary validation)

Two additional models describe the shape of the raw `/api/camps/availability/campground/{id}/month` response. These are not emitted as JSON — they exist so [parser.md](parser.md) and [search.md](search.md) can validate the API response at the boundary:

```python
class RawSiteAvailability(BaseModel):
    model_config = ConfigDict(extra="ignore")  # tolerate Rec.gov adding fields
    availabilities: dict[str, str]             # {iso_datetime: status}
    loop: str | None = None
    site: str | None = None                    # human-readable, e.g. "A007"
    campsite_type: str | None = None

class RawCampgroundResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    campsites: dict[str, RawSiteAvailability]  # outer key = campsite_id (the bit the booker needs)
```

Shape borrowed from camply — see [camply-attribution.md](camply-attribution.md).

## The `is_available(status)` helper

Module-level function. Returns `False` for any status in the Rec.gov denylist (`Reserved`, `Not Available`, `Not Reservable`, `Not Reservable Management`, `Not Available Cutoff`, `Lottery`, `Open`, `NYR`, `Closed`). Used by both [parser.md](parser.md) and [search.md](search.md). Note that **`"Open"` is *not* bookable** — see [camply-attribution.md](camply-attribution.md) for why.

## Window enumeration: `windows_by_site_id`

The new `CampsiteResult.windows_by_site_id` field gives, per campsite, every viable 2-night `(start_iso, checkout_iso)` window. A 3-night run produces 2 entries; a 5-night run produces 4. Empty for sites with only single-night availability. Powered by [windows.md](windows.md) — see [banool-attribution.md](banool-attribution.md) for the algorithm's provenance.

The Phase 3 auto-cart matcher (see [auto-cart-mvp-plan.md](auto-cart-mvp-plan.md)) calls `consecutive_nights()` directly with arbitrary `nights` from `targets.json`; this field surfaces the default-2 case in the JSON output for OpenClaw.

## Output contracts

| Mode | Top-level emitted by main.py | JSON shape |
|---|---|---|
| Weekend (Mode 1) | `list[LocationReport]` | array — one per preset location |
| Search (Mode 2) | `SearchReport` | object with `results[]` |

[../SKILL.md](../SKILL.md) tells the LLM how to read each shape and present it to the user. Watch mode (Mode 3) emits the same `SearchReport` — it's just Mode 2 on a cron with `jq -e '.results | length > 0'` gating notifications.

## Why Pydantic, not dataclasses

- `model_dump(mode="json")` serializes cleanly to JSON in [main.md](main.md) — no custom encoder.
- `model_validate()` enforces the API contract at the boundary — if Rec.gov renames or removes a field, we find out at parse time, not when the auto-cart booker silently clicks the wrong site.
- `extra="ignore"` lets the API add fields without breaking us — important for an undocumented endpoint.
- Same field-list-as-contract benefit as dataclasses, but with validation included.

## Field naming conventions

- **`name`** is always the human-readable camp/facility name (title case).
- **`facility_id`** is always a string, even though Rec.gov sometimes returns ints.
- **`available_dates`** is always sorted ISO strings (`YYYY-MM-DD`), never `date` objects — JSON serialization wants strings, and the LLM-facing reply layer formats them into "Jul 3, 4, 5".
- **`contiguous`** uses the same primitive ([`consecutive_nights`](windows.md)) in both modes — the difference is the prefiltered window passed in (Fri/Sat/Sun in weekend mode, the `--start..--end` range in search mode). See [parser.md](parser.md) and [search.md](search.md).
- **`reservation_url`** is constructed in [parser.md](parser.md) (Mode 1) and inline in [search.md](search.md) (Mode 2). Both honor the permit-vs-campground URL distinction — see [config.md](config.md).

## Adding a field

If a new field is added to any of these:

1. Update the model here.
2. Set it in whichever module produces the type ([parser.md](parser.md), [search.md](search.md), or [weather.md](weather.md)).
3. Update [../SKILL.md](../SKILL.md) so the LLM knows it exists in the JSON.
4. Update the relevant wiki page so future readers see the shape change.

The JSON output is the program's contract with OpenClaw. Treat field renames as breaking changes.
