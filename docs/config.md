# recon/config.py

Static preset locations + their facility/permit IDs. Pure data — no logic. Two dataclasses and a top-level `LOCATIONS` dict.

[Source](../recon/config.py) · Wiki home: [README.md](README.md)

## Public surface

```python
@dataclass(frozen=True)
class Camp:
    name: str
    facility_id: str
    permit_id: str | None = None     # None = standard campground, no permit URL needed

@dataclass(frozen=True)
class Location:
    name: str
    lat: float                       # for weather.md
    lon: float
    camps: tuple[Camp, ...]

LOCATIONS: dict[str, Location] = { ... }
```

The dict key (e.g. `"point_reyes"`) is what the user passes to `--location` in [main.md](main.md).

## Current presets

| Key | Location | Notes |
|---|---|---|
| `point_reyes` | Point Reyes National Seashore | All 4 camps are wilderness permits — every `Camp` has a `permit_id` |
| `big_sur` | Big Sur | Drive-in campgrounds, no permits |
| `pinnacles` | Pinnacles National Park | Single campground |
| `kings_canyon` | Kings Canyon National Park | 6 standard campgrounds |
| `sequoia` | Sequoia National Park | 6 standard campgrounds |

## Why a code constant, not a config file

- IDs are stable. Recreation.gov rarely changes them.
- The list is small (~20 camps) and fits comfortably in a 60-line file.
- Frozen dataclasses give type safety the LLM and IDE can both check.
- No I/O at startup, no parsing errors, no schema migration.

If presets ever grow past ~50 entries or need user-customization, *then* move to YAML / JSON. Until then, the code constant wins.

## How to add a preset

1. Look up facility IDs on RIDB (the [campsite_api_checker.ipynb](../campsite_api_checker.ipynb) notebook is the easiest tool for this — query by name, copy the `FacilityID`).
2. For permit camps, also grab the permit ID from `recreation.gov/permits/{id}`.
3. Add an entry to `LOCATIONS`:
   ```python
   "joshua_tree": Location(
       name="Joshua Tree National Park",
       lat=33.873, lon=-115.901,
       camps=(
           Camp("Jumbo Rocks", "232489"),
           Camp("Hidden Valley", "232485"),
       ),
   ),
   ```
4. Update the `--location` choices in [SKILL.md](../SKILL.md) Mode 1 if the LLM should know about it.

No other files need to change. [availability.md](availability.md), [parser.md](parser.md), and [weather.md](weather.md) all consume `Location` / `Camp` generically.

## Permit ID is the source of truth for booking URLs

If a `Camp` has a `permit_id`, [parser.md](parser.md) will route its booking URL through `/permits/`, regardless of which endpoint actually returned the data. Setting `permit_id=None` for a permit camp is a bug that will hand the user a broken `/camping/` URL.

## Reference

For the full known-IDs list (presets and beyond), see [../references/facility-ids.md](../references/facility-ids.md).
