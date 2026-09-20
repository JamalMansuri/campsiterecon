# recon/config.py

Static preset locations + their verified facility IDs. Pure data — no logic. Two dataclasses and a top-level `LOCATIONS` dict.

[Source](../recon/config.py) · Wiki home: [README.md](README.md)

## Public surface

```python
@dataclass(frozen=True)
class Camp:
    name: str
    facility_id: str
    permit_id: str | None = None     # None = standard campground, no permit URL needed
    loop: str | None = None          # restrict to campsites whose Rec.gov `loop` equals this

@dataclass(frozen=True)
class Location:
    name: str
    lat: float                       # for weather.md AND for --verify's distance check
    lon: float
    camps: tuple[Camp, ...]

LOCATIONS: dict[str, Location] = { ... }
```

The dict key (e.g. `"point_reyes"`) is what the user passes to `--location` in [main.md](main.md).

## Current presets (all ids verified 2026-09-20)

| Key | Location | Camps |
|---|---|---|
| `point_reyes` | Point Reyes National Seashore | Sky, Coast, Glen, Wildcat — **one facility (233359), four `loop` values**. Booked like any campsite; no permit. |
| `big_sur` | Big Sur | Kirk Creek 233116, Plaskett Creek 231959, Ponderosa 233118 (Los Padres NF) |
| `pinnacles` | Pinnacles National Park | 234015 |
| `kings_canyon` | Kings Canyon National Park | 6 campgrounds |
| `sequoia` | Sequoia National Park | 6 campgrounds |

## The `loop` field

Rec.gov models Point Reyes as a single campground whose campsites carry `loop: "Sky"` / `"Coast"` / `"Glen"` / `"Wildcat"` (plus two boat-in Tomales Bay loops that the preset leaves out). Four `Camp` entries share `facility_id="233359"` and differ only by `loop`; [parser.md](parser.md) filters campsites case-insensitively on it, and [api_client.md](api_client.md)'s cache means the month is fetched once, not four times.

## The `Location` lat/lon is a reference point, not every camp

Weather is fetched once per location from `Location.lat/lon`, and `--verify` only checks each camp is within 150 km of it. Kings Canyon's point is Grant Grove (~2,000 m) while Sentinel / Moraine / Sheep Creek are 27 km east at Cedar Grove (~1,400 m); Sequoia's point is Lodgepole (~2,050 m) while Potwisha / Buckeye Flat are in the Foothills (~600 m). SKILL.md tells the LLM to name the reference point for those camps. If per-camp forecasts are ever wanted, the verified coordinates are already recorded in `tests/fixtures/presets/directory.json` — add `lat`/`lon` to `Camp` and fetch per distinct coordinate, or split the presets (grant_grove / cedar_grove, lodgepole / foothills).

## What the presets deliberately exclude

California State Parks (Pfeiffer Big Sur, Andrew Molera, Limekiln, Julia Pfeiffer Burns, Mt Tam, Samuel P. Taylor, Henry Cowell, Butano) are booked through ReserveCalifornia and do not exist on Recreation.gov. Earlier versions of this file listed three of them under Big Sur with ids that actually pointed at campgrounds in New Mexico and Oregon.

## How to add a preset

1. Look the id up on RIDB — `campsite_api_checker.ipynb` or a direct `GET /facilities?query=<name>` — and confirm the name with `GET https://www.recreation.gov/api/camps/campgrounds/<id>`. **Never type an id from memory.**
2. If the camp is one loop of a bigger facility, fetch a month of availability and copy the exact `loop` string.
3. Add the entry to `LOCATIONS`.
4. Run `python main.py --verify` — it must print `"ok": true`. See [verify.md](verify.md) for what it checks.
5. Update the `--location` choices in [SKILL.md](../SKILL.md) Mode 1 and [../references/facility-ids.md](../references/facility-ids.md).

## Why a code constant, not a config file

IDs are stable, the list is small, frozen dataclasses give type safety, and there's no I/O at startup. If presets ever grow past ~50 entries or need user-customization, move to YAML/JSON then.
