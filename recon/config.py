from dataclasses import dataclass


@dataclass(frozen=True)
class Camp:
    name: str
    facility_id: str
    permit_id: str | None = None   # None = standard campground booking, not a permit system


@dataclass(frozen=True)
class Location:
    name: str
    lat: float
    lon: float
    camps: tuple[Camp, ...]


LOCATIONS: dict[str, Location] = {
    "point_reyes": Location(
        name="Point Reyes National Seashore",
        lat=38.037,
        lon=-122.803,
        camps=(
            Camp("Sky Camp",     "234059", "4675310"),
            Camp("Coast Camp",   "234061", "4675311"),
            Camp("Glen Camp",    "234060", "4675312"),
            Camp("Wildcat Camp", "234062", "4675313"),
        ),
    ),
    "big_sur": Location(
        name="Big Sur",
        lat=36.270,
        lon=-121.807,
        camps=(
            Camp("Kirk Creek",       "233116"),
            Camp("Plaskett Creek",   "233115"),
            Camp("Pfeiffer Big Sur", "233394"),
            Camp("Andrew Molera",    "234218"),
            Camp("Limekiln SP",      "10149046"),
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
