# Known Facility IDs (verified 2026-09-20)

Every id below was checked against RIDB (`/facilities/{id}`) and Rec.gov
(`/api/camps/campgrounds/{id}`) on the date above. **Do not add ids from
memory** — an earlier version of this file was written that way and almost
every Bay Area id in it pointed at a campground in another state. If you need
an id that isn't here, look it up:

```
GET https://ridb.recreation.gov/api/v1/facilities?query=<name>&limit=50&apikey=<KEY>
GET https://ridb.recreation.gov/api/v1/facilities/<id>?apikey=<KEY>
GET https://www.recreation.gov/api/camps/campgrounds/<id>          # no key; returns facility_name
```

Presets in [recon/config.py](../recon/config.py) are re-checked by `python main.py --verify`.

## Not on Recreation.gov at all

California State Parks book through **ReserveCalifornia**, not Rec.gov, so
they can never appear in this tool: Pfeiffer Big Sur SP, Andrew Molera SP,
Limekiln SP, Julia Pfeiffer Burns SP, Mt Tamalpais SP (Pantoll, Steep
Ravine), Samuel P. Taylor SP, Henry Cowell SP, Butano SP, Angel Island SP.
Tell the user to use reservecalifornia.com for those.

---

## Point Reyes National Seashore — rec area 2864

**One facility**, booked through the ordinary campground flow (no permit
system). The named camps are `loop` values on its campsites.

| Facility | ID | URL |
|---|---|---|
| Point Reyes National Seashore Campground | `233359` | https://www.recreation.gov/camping/campgrounds/233359 |

| Loop (as returned by the API) | Sites | Preset |
|---|---|---|
| `Sky` | 12 hike-in | `Camp("Sky Camp", "233359", loop="Sky")` |
| `Coast` | 14 hike-in | `Camp("Coast Camp", "233359", loop="Coast")` |
| `Glen` | 12 hike-in | `Camp("Glen Camp", "233359", loop="Glen")` |
| `Wildcat` | 8 hike-in | `Camp("Wildcat Camp", "233359", loop="Wildcat")` |
| `Tomales Bay` | 2 boat-in group | not in preset (needs a boat) |
| `Tomales Bay Boat Only` | 3 boat-in | not in preset |

## Golden Gate National Recreation Area (Marin Headlands) — rec area 2730

| Name | ID | Type |
|---|---|---|
| Kirby Cove Campground | `232491` | drive-in, Golden Gate views |
| Bicentennial Campground | `272229` | walk-in |
| Haypress Campground | `10067346` | hike-in |
| Hawk Campground | `258815` | hike-in |

## Big Sur coast — Los Padres National Forest, rec area 1067

| Name | ID | Notes |
|---|---|---|
| Kirk Creek Campground | `233116` | ocean bluff, Hwy 1 |
| Plaskett Creek Campground | `231959` | 5 mi south of Kirk Creek |
| Ponderosa Campground | `233118` | Nacimiento-Fergusson Rd, inland |
| Arroyo Seco | `231958` | east side of the Santa Lucias (Greenfield) |
| China Camp Campground | `273878` | Tassajara Rd |
| White Oaks Campground | `273819` | Tassajara Rd |
| Escondido Campground | `273869` | Indians Rd |
| Memorial Campground | `273874` | Indians Rd |

## Pinnacles National Park — rec area 2893

| Name | ID |
|---|---|
| Pinnacles Campground | `234015` |

## Sequoia & Kings Canyon National Parks — rec area 2931

| Name | ID | Area |
|---|---|---|
| Sentinel Campground | `253917` | Cedar Grove |
| Moraine Campground (CA) | `10044761` | Cedar Grove (seasonal) |
| Sheep Creek Campground | `10044765` | Cedar Grove (seasonal) |
| Azalea Campground | `10124502` | Grant Grove, year-round |
| Sunset Campground (CA) | `234752` | Grant Grove |
| Crystal Springs Campground (CA) | `10124445` | Grant Grove |
| Lodgepole Campground | `232461` | Giant Forest |
| Dorst Creek Campground | `232460` | seasonal |
| Buckeye Flat Campground | `249982` | Foothills |
| Potwisha Campground | `249979` | Foothills, year-round |
| Cold Springs Campground (CA) | `246864` | Mineral King (seasonal) |
| Atwell Mill Campground | `10044710` | Mineral King (seasonal) |

## Yosemite National Park — rec area 2991

| Name | ID | Notes |
|---|---|---|
| Upper Pines Campground | `232447` | Valley; books out in seconds |
| Lower Pines Campground | `232450` | Valley |
| North Pines Campground | `232449` | Valley |
| Camp 4 | `10004152` | Valley, walk-in |
| Wawona Campground | `232446` | south |
| Hodgdon Meadow Campground | `232451` | Big Oak Flat entrance |
| Crane Flat Campground | `232452` | mid-elevation |
| Bridalveil Creek Campground | `232453` | Glacier Point Rd |
| Tuolumne Meadows Campground | `232448` | high country, summer |
| Tamarack Flat Campground | `10083845` | Tioga Rd |
| White Wolf Campground | `10083567` | Tioga Rd |
| Yosemite Creek Campground | `10083840` | Tioga Rd |
| Porcupine Flat Campground | `10083831` | Tioga Rd |
| Yosemite National Park Wilderness Permits | `445859` | **Permit** — `/permits/445859`; NOT served by `/api/permits/{id}/availability/month` (404) |
| Half Dome Permits | `234652` | **Permit** — `/permits/234652`; lottery-style, the availability endpoint answers |

Nearby campgrounds that a `--search "Yosemite"` also returns (they are *outside* the park — say so):

| Name | ID | Rec area |
|---|---|---|
| Lost Claim | `234761` | Stanislaus NF (1076) |
| Dimond O | `233772` | Stanislaus NF |
| Pines Stanislaus | `10180062` | Stanislaus NF |
| Cherry Valley | `234756` | Stanislaus NF |
| Sweetwater | `10174943` | Stanislaus NF |
| Summerdale Campground | `233837` | Sierra NF (1074) |
| McCabe Flat / Railroad Flat / Willow Placer | `273833` / `273836` / `273838` | BLM Merced River (610) |
| Oh Ridge / June Lake | `232269` / `232268` | Inyo NF (1064) |

## Rec area IDs

| Rec area | ID |
|---|---|
| Point Reyes National Seashore | 2864 |
| Golden Gate NRA | 2730 |
| Los Padres National Forest | 1067 |
| Pinnacles National Park | 2893 |
| Sequoia & Kings Canyon National Parks | 2931 |
| Yosemite National Park | 2991 |
| Stanislaus National Forest | 1076 |
| Sierra National Forest | 1074 |
| Inyo National Forest | 1064 |

(2733 is Grand Canyon — it was listed here as Point Reyes before.)
