from pydantic import BaseModel, ConfigDict, Field


class RawSiteAvailability(BaseModel):
    """One campsite's per-date status, mirroring the Rec.gov API shape."""
    model_config = ConfigDict(extra="ignore")

    availabilities: dict[str, str] = Field(default_factory=dict)
    loop: str | None = None
    site: str | None = None
    campsite_type: str | None = None


class RawCampgroundResponse(BaseModel):
    """Top-level shape of /api/camps/availability/campground/{id}/month."""
    model_config = ConfigDict(extra="ignore")

    campsites: dict[str, RawSiteAvailability] = Field(default_factory=dict)


_REC_GOV_UNAVAILABLE_STATUSES = frozenset({
    "Reserved", "Not Available", "Not Reservable",
    "Not Reservable Management", "Not Available Cutoff",
    "Lottery", "Open", "NYR", "Closed",
})


def is_available(status: str) -> bool:
    """Denylist filter for Rec.gov availability status strings.

    Mirrored from camply's CAMPSITE_UNAVAILABLE_STRINGS — see
    docs/camply-attribution.md. "Open" reads as bookable but means
    walk-up-only at most parks; treating it as available causes false
    positives in the scout output.
    """
    return status not in _REC_GOV_UNAVAILABLE_STATUSES


class CampsiteResult(BaseModel):
    name: str
    facility_id: str
    available_dates: list[str]
    sites_by_id: dict[str, list[str]] = Field(default_factory=dict)
    windows_by_site_id: dict[str, list[tuple[str, str]]] = Field(default_factory=dict)
    permit_required: bool
    reservation_url: str
    contiguous: bool


class WeatherDay(BaseModel):
    date: str
    high_c: float
    low_c: float
    rain_mm: float
    wind_kph: float
    condition: str


class LocationReport(BaseModel):
    location: str
    weekend_start: str
    weekend_end: str
    available: bool
    sites: list[CampsiteResult]
    weather: dict[str, WeatherDay]


class SearchResult(BaseModel):
    name: str
    facility_id: str
    available_dates: list[str]
    reservation_url: str
    contiguous: bool


class SearchReport(BaseModel):
    query: str
    start: str
    end: str
    results: list[SearchResult]
