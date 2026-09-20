# recon/models.py

The data contracts. Pydantic models define every JSON shape the program emits, every internal record that flows between modules, and the boundary validation for raw Rec.gov responses.

[Source](../recon/models.py) · Wiki home: [README.md](README.md)

## Weekend mode (Mode 1)

```python
class SiteDetail(BaseModel):            # one open campsite
    site: str | None                   # Rec.gov label, e.g. "003"
    loop: str | None
    campsite_type: str | None          # "STANDARD NONELECTRIC", "GROUP HIKE TO", "BOAT IN" ...
    min_people: int | None; max_people: int | None
    url: str                           # /camping/campsites/{campsite_id}

class StayRules(BaseModel):            # from Rec.gov facility_rules; None when the facility has none
    min_nights, min_weekend_nights, min_holiday_weekend_nights, max_nights: int | None
    min_nights_policy, min_weekend_policy, min_holiday_weekend_policy: str | None   # "strict" | "soft" | "softAny"

class CampsiteResult(BaseModel):       # one camp, one weekend
    name: str                          # preset label
    facility_id: str
    official_name: str | None          # Rec.gov's facility_name — present this
    loop: str | None                   # set for loop-scoped presets (Point Reyes)
    loop_matched: bool | None          # False = the loop matched no campsite at all → warning
    skipped_sites: int                 # malformed campsite records ignored
    available_dates: list[str]         # ISO nights within Fri/Sat/Sun, union across sites
    sites_by_id: dict[str, list[str]]  # {campsite_id: [iso_nights]} — fuel for the auto-cart booker (durable)
    windows_by_site_id: dict[str, list[tuple[str, str]]]   # viable 2-night (first_night, checkout) pairs (durable)
    site_details: dict[str, SiteDetail]                    # same keys as sites_by_id
    stay_rules: StayRules | None       # a lone open night at a min_nights=2 campground is not bookable
    permit_required: bool
    reservation_url: str
    contiguous: bool

class LocationReport(BaseModel):
    location: str
    weekend_start: str                 # Friday
    weekend_end: str                   # Sunday (last night checked)
    nights: list[str]                  # the three nights, explicit
    available: bool
    sites: list[CampsiteResult]
    unreachable: list[str]             # camps whose fetch failed — "couldn't check", never "full"
    warnings: list[str]                # e.g. Rec.gov rate-limited this run
    weather: dict[str, WeatherDay]     # "friday"/"saturday"/"sunday"; empty beyond 14 days
```

## Search mode (Mode 2)

```python
class SearchSite(BaseModel):
    campsite_id: str; site: str | None; loop: str | None; campsite_type: str | None
    min_people: int | None; max_people: int | None; dates: list[str]; url: str

class SearchResult(BaseModel):
    name: str                          # display name (title-cased only if RIDB shouted)
    official_name: str | None          # RIDB FacilityName verbatim
    facility_id: str
    rec_area: str | None               # parent rec area — the query is fuzzy, say where it is
    latitude: float | None; longitude: float | None
    distance_km: float | None          # from the report's `anchor` rec area, when resolved
    available_dates: list[str]
    open_site_count: int
    skipped_sites: int
    sample_sites: list[SearchSite]     # up to 5; any site with a 2-night window first, then most open nights
    stay_rules: StayRules | None
    reservation_url: str
    contiguous: bool                   # per-site; always False for permits

class SearchReport(BaseModel):
    query: str; start: str; end: str
    anchor: str | None                 # rec area the query resolved to; results sorted by distance from it
    facilities_total: int              # RIDB TOTAL_COUNT
    facilities_scanned: int
    skipped_far: list[str]             # keyword matches > 150 km from the anchor, not checked
    unreachable: list[str]; partial: list[str]; warnings: list[str]
    results: list[SearchResult]        # contiguous is per-site, see parser.md
```

## `--verify`

`VerifiedCamp` / `VerifyReport` — see [verify.md](verify.md).

## Raw-response types (boundary validation)

```python
class RawSiteAvailability(BaseModel):  # extra="ignore"
    availabilities: dict[str, str]; quantities: dict[str, int] | None
    campsite_id, loop, site, campsite_type, campsite_reserve_type, type_of_use: str | None
    hide_external: bool = False

class RawCampgroundResponse(BaseModel):
    campsites: dict[str, RawSiteAvailability]; count: int | None

class RawPermitDate(BaseModel):        total, remaining: int | None; show_walkup, is_secret_quota: bool
class RawPermitDivision(BaseModel):    division_id: str | None; date_availability: dict[str, RawPermitDate]
```

Shape borrowed from camply — see [camply-attribution.md](camply-attribution.md).

## Helpers

- `is_available(status)` — denylist (`Reserved`, `Not Available`, `Not Reservable`, `Not Reservable Management`, `Not Available Cutoff`, `Lottery`, `Open`, `NYR`, `Closed`). **`"Open"` is not bookable.**
- `is_bookable_site(site)` — drops `hide_external` and `type_of_use == "Day"` sites before any date is counted.

## Output contracts

| Mode | Top-level emitted by main.py | JSON shape |
|---|---|---|
| Weekend | `list[LocationReport]` | array |
| Search | `SearchReport` | object; cron gates on `.results \| length > 0` |
| Verify | `VerifyReport` | object; exit 1 unless `ok` |

Every field is additive; nothing that existed before 2026-09-20 was renamed or removed, so existing cron lines keep working.
