# Known Facility IDs

These are verified facility IDs for Recreation.gov. Use these directly instead of doing a live RIDB search — faster and more reliable for commonly requested spots.

> **Maintenance note:** Facility IDs are permanent and don't change. If an availability check returns 404 for an ID in this file, the campground may be temporarily closed or moved to a permit system — flag this to the user.

---

## Point Reyes National Seashore (POC Area)

**Rec Area ID:** `2733`
**Location:** Marin County, CA
**Distance from SF:** ~1.5 hrs
**Reservations via:** Recreation.gov (wilderness permits)
**Booking window:** Opens 90 days in advance; limited sites per day

Point Reyes backcountry operates as **wilderness permits** (not standard drive-in campsites). Each "campground" is accessed by trail only. The permit system uses a different availability endpoint — see `api-endpoints.md` section on Wilderness Permit Availability.

### Wilderness Camps

| Name | Facility ID | Permit ID | Lat | Lon | Miles from trailhead |
|------|-------------|-----------|-----|-----|---------------------|
| Sky Camp | 234059 | 4675310 | 38.037 | -122.803 | 1.7 mi (Sky trailhead) |
| Coast Camp | 234061 | 4675311 | 38.017 | -122.924 | 2.8 mi (Laguna trailhead) |
| Glen Camp | 234060 | 4675312 | 38.001 | -122.875 | 4.6 mi (Bear Valley) |
| Wildcat Camp | 234062 | 4675313 | 37.965 | -122.862 | 6.3 mi (Bear Valley) |

> **⚠️ Verify these IDs** on your first real query — pull from RIDB to confirm. The permit IDs in particular should be double-checked since the permit system migrated to Recreation.gov from a separate system in 2022.

### Drive-In Camps

| Name | Facility ID | Type | Lat | Lon |
|------|-------------|------|-----|-----|
| Olema Group Horse Camp | 233492 | Group / Equestrian | 38.043 | -122.785 |

---

## Bay Area — Within ~2 hours of SF

| Name | Facility ID | Type | Park | Approx Distance from SF |
|------|-------------|------|------|------------------------|
| Pantoll Walk-In Camp (Mt Tam) | 10097892 | Walk-in tent | GGNRA / Mt Tamalpais SP | 45 min |
| Kirby Cove | 234394 | Drive-in | GGNRA | 30 min |
| Haypress Camp (GGNRA) | 10100076 | Backpack | GGNRA | 45 min |
| Bicentennial Camp (GGNRA) | 10100078 | Hike-in | GGNRA | 1 hr |
| Steep Ravine (Mt Tam) | 233490 | Cabins + tent | Mt Tamalpais SP | 45 min |
| Samuel P. Taylor | 10150940 | Drive-in | Samuel P. Taylor SP | 1 hr |
| Butano SP | 10109846 | Drive-in | Butano SP | 1.5 hrs |
| Henry Cowell | 10147427 | Drive-in | Henry Cowell Redwoods SP | 1.5 hrs |

---

## Big Sur — ~3 hours from SF

| Name | Facility ID | Type | Highlight |
|------|-------------|------|-----------|
| Kirk Creek | 233116 | Drive-in | Ocean bluff sites, iconic |
| Plaskett Creek | 233115 | Drive-in | Next to Kirk Creek, less traffic |
| Pfeiffer Big Sur | 233394 | Drive-in | Most popular / amenities |
| Andrew Molera Walk-In | 234218 | Walk-in | Quieter, near beach |
| Limekiln SP | 10149046 | Drive-in | Near waterfalls |

---

## Pinnacles National Park — ~2 hours from SF

**Rec Area location:** `36.491, -121.198`
**Config key:** `pinnacles`

| Name | Facility ID | Type | Notes |
|------|-------------|------|-------|
| Pinnacles Campground | 234015 | Drive-in | Only campground in the park; low elevation so usable year-round |

---

## Kings Canyon National Park — ~5 hours from SF

**Rec Area location (Grant Grove):** `36.740, -118.962`
**Config key:** `kings_canyon`
**ParentRecAreaID:** `2931` (shared with Sequoia NP — "Sequoia & Kings Canyon")

| Name | Facility ID | Type | Notes |
|------|-------------|------|-------|
| Sentinel | 253917 | Drive-in | Grant Grove area |
| Moraine | 10044761 | Drive-in | Cedar Grove area (seasonal — typically closed until late May) |
| Sheep Creek | 10044765 | Drive-in | Cedar Grove area (seasonal) |
| Azalea | 10124502 | Drive-in | Grant Grove area, year-round |
| Sunset | 234752 | Drive-in | Grant Grove area |
| Crystal Springs | 10124445 | Drive-in | Grant Grove area |

> Most Cedar Grove campgrounds open ~late May through October. Expect empty availability returns in winter/spring — not a bug.

---

## Sequoia National Park — ~4.5 hours from SF

**Rec Area location (Giant Forest / Lodgepole):** `36.600, -118.726`
**Config key:** `sequoia`
**ParentRecAreaID:** `2931`

| Name | Facility ID | Type | Notes |
|------|-------------|------|-------|
| Lodgepole | 232461 | Drive-in | Near Giant Forest, seasonal |
| Dorst Creek | 232460 | Drive-in | Seasonal |
| Buckeye Flat | 249982 | Drive-in | Foothills, year-round |
| Potwisha | 249979 | Drive-in | Foothills, year-round |
| Cold Springs | 246864 | Drive-in | Mineral King area (seasonal, late May onward) |
| Atwell Mill | 10044710 | Drive-in | Mineral King area (seasonal) |

> **Sequoia & Kings Canyon Wilderness Permits** are issued under a different RIDB entry (FacilityID `445857`). Not currently wired into `recon/config.py`; if adding, treat it as a permit-only entry.

---

## Yosemite — ~3.5 hours from SF

| Name | Facility ID | Type | Notes |
|------|-------------|------|-------|
| Upper Pines | 232447 | Drive-in | Valley floor, high demand |
| Lower Pines | 232450 | Drive-in | Valley floor |
| North Pines | 232449 | Drive-in | Valley floor |
| Wawona | 232448 | Drive-in | Quieter, southern Yosemite |
| Hodgdon Meadow | 232446 | Drive-in | Near Big Oak Flat entrance |
| Tuolumne Meadows | 232452 | Drive-in | High Sierra, opens ~June |
| Crane Flat | 232451 | Drive-in | Mid-elevation |

**Yosemite note:** Valley campgrounds book out within seconds of the 5am reservation window opening (7 days in advance for day-of, up to 5 months for specific dates). Cancellations are the main opportunity. Flag this prominently to the user.

---

## Ranking by Popularity (for "best in area" queries)

When the user asks for general area recommendations without specifying a campground, prioritize in this order for the Bay Area:

1. **Point Reyes wilderness** — iconic, accessible, uniquely foggy/coastal
2. **Steep Ravine** — oceanfront cabins, extremely hard to get, but worth surfacing
3. **Kirby Cove** — close to SF, Golden Gate views, small and intimate
4. **Kirk Creek / Plaskett Creek** — Big Sur ocean bluffs if willing to drive

---

## ID Verification Queries

To verify or discover new facility IDs, use:

```
# Search by name
GET /facilities?query=sky+camp+point+reyes&apikey={key}

# Search rec area children
GET /recareas/2733/facilities?facilitytype=Campground&limit=20&apikey={key}

# Confirm a specific facility
GET /facilities/{facilityId}?apikey={key}
```
