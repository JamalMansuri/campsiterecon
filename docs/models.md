# recon/models.py

The data contracts. Five dataclasses define every JSON shape the program emits and every internal record that flows between modules.

[Source](../recon/models.py) · Wiki home: [README.md](README.md)

## The five types

```python
@dataclass
class CampsiteResult:                  # one camp, one weekend (Mode 1 row)
    name: str
    facility_id: str
    available_dates: list[str]         # ISO dates within the weekend
    permit_required: bool              # drives reservation_url shape
    reservation_url: str               # /camping/... or /permits/...
    contiguous: bool                   # 2+ consecutive nights of the weekend

@dataclass
class WeatherDay:                      # one forecast day
    date: str
    high_c: float
    low_c: float
    rain_mm: float
    wind_kph: float
    condition: str                     # WMO label, e.g. "Drizzle"

@dataclass
class LocationReport:                  # Mode 1 top-level, one per location
    location: str
    weekend_start: str                 # Friday ISO
    weekend_end: str                   # Sunday ISO
    available: bool                    # any sites open at all
    sites: list[CampsiteResult]
    weather: dict[str, WeatherDay]     # keys: "friday", "saturday", "sunday"

@dataclass
class SearchResult:                    # one facility (Mode 2 row)
    name: str
    facility_id: str
    available_dates: list[str]         # ISO dates within the search range
    reservation_url: str
    contiguous: bool                   # any 2 consecutive days, weekend or not

@dataclass
class SearchReport:                    # Mode 2 top-level
    query: str
    start: str
    end: str
    results: list[SearchResult]
```

## Output contracts

| Mode | Top-level emitted by main.py | JSON shape |
|---|---|---|
| Weekend (Mode 1) | `list[LocationReport]` | array — one per preset location |
| Search (Mode 2) | `SearchReport` | object with `results[]` |

[../SKILL.md](../SKILL.md) tells the LLM how to read each shape and present it to the user. Watch mode (Mode 3) emits the same `SearchReport` — it's just Mode 2 on a cron with `jq -e '.results | length > 0'` gating notifications.

## Why dataclasses, not dicts

- `dataclasses.asdict()` serializes cleanly to JSON in [main.md](main.md) — no custom encoder.
- Static fields catch typos at parse time instead of at the LLM-presentation layer.
- Frozen-by-default isn't used here (parsers build them up), but the field list is the contract that other modules can rely on.

## Field naming conventions

- **`name`** is always the human-readable camp/facility name (title case).
- **`facility_id`** is always a string, even though Rec.gov sometimes returns ints.
- **`available_dates`** is always sorted ISO strings (`YYYY-MM-DD`), never `date` objects — JSON serialization wants strings, and the LLM-facing reply layer formats them into "Jul 3, 4, 5".
- **`contiguous`** has different definitions in `CampsiteResult` (Fri+Sat or Sat+Sun) vs `SearchResult` (any consecutive pair). See [parser.md](parser.md) and [search.md](search.md).
- **`reservation_url`** is constructed in [parser.md](parser.md) (Mode 1) and inline in [search.md](search.md) (Mode 2). Both honor the permit-vs-campground URL distinction — see [config.md](config.md).

## Adding a field

If a new field is added to any of these:

1. Update the dataclass here.
2. Set it in whichever module produces the type ([parser.md](parser.md), [search.md](search.md), or [weather.md](weather.md)).
3. Update [../SKILL.md](../SKILL.md) so the LLM knows it exists in the JSON.
4. Update the relevant wiki page so future readers see the shape change.

The JSON output is the program's contract with OpenClaw. Treat field renames as breaking changes.
