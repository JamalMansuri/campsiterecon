"""Preset locations.

Every facility_id here has been verified against RIDB and Rec.gov — run
`python main.py --verify` after editing this file. It checks that each id
resolves, is a Campground (or Permit when permit_id is set), sits within
150 km of the Location's lat/lon, and that any `loop` actually exists in
the live availability response. Never add an id from memory.

Not on Recreation.gov (booked through ReserveCalifornia, so they can't be
presets): Pfeiffer Big Sur SP, Andrew Molera SP, Limekiln SP, Julia Pfeiffer
Burns SP, Mt Tamalpais SP (Pantoll, Steep Ravine), Samuel P. Taylor SP,
Henry Cowell SP, Butano SP.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Camp:
    name: str
    facility_id: str
    permit_id: str | None = None   # None = standard campground booking, not a permit system
    loop: str | None = None        # restrict to campsites whose Rec.gov `loop` equals this
                                   # (one facility, many named camps — Point Reyes)


@dataclass(frozen=True)
class Location:
    name: str
    lat: float
    lon: float
    camps: tuple[Camp, ...]


LOCATIONS: dict[str, Location] = {
    # Point Reyes is ONE Rec.gov facility (233359, rec area 2864). Sky, Coast,
    # Glen and Wildcat are loops inside it, booked through the normal campground
    # flow — there is no permit system. (Tomales Bay boat-in loops exist too but
    # need a boat, so they're left out of the preset.)
    "point_reyes": Location(
        name="Point Reyes National Seashore",
        lat=38.037,
        lon=-122.803,
        camps=(
            Camp("Sky Camp",     "233359", loop="Sky"),
            Camp("Coast Camp",   "233359", loop="Coast"),
            Camp("Glen Camp",    "233359", loop="Glen"),
            Camp("Wildcat Camp", "233359", loop="Wildcat"),
        ),
    ),
    # Los Padres NF (rec area 1067) campgrounds on the south Big Sur coast.
    "big_sur": Location(
        name="Big Sur",
        lat=35.97,
        lon=-121.46,
        camps=(
            Camp("Kirk Creek",     "233116"),
            Camp("Plaskett Creek", "231959"),
            Camp("Ponderosa",      "233118"),
        ),
    ),
    "pinnacles": Location(
        name="Pinnacles National Park",
        lat=36.491,
        lon=-121.198,
        camps=(
            Camp("Pinnacles Campground", "234015"),
        ),
    ),
    "kings_canyon": Location(
        name="Kings Canyon National Park",
        lat=36.740,
        lon=-118.962,
        camps=(
            Camp("Sentinel",        "253917"),
            Camp("Moraine",         "10044761"),
            Camp("Sheep Creek",     "10044765"),
            Camp("Azalea",          "10124502"),
            Camp("Sunset",          "234752"),
            Camp("Crystal Springs", "10124445"),
        ),
    ),
    "sequoia": Location(
        name="Sequoia National Park",
        lat=36.600,
        lon=-118.726,
        camps=(
            Camp("Lodgepole",    "232461"),
            Camp("Dorst Creek",  "232460"),
            Camp("Buckeye Flat", "249982"),
            Camp("Potwisha",     "249979"),
            Camp("Cold Springs", "246864"),
            Camp("Atwell Mill",  "10044710"),
        ),
    ),
}
