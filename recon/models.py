from dataclasses import dataclass


@dataclass
class CampsiteResult:
    name: str
    facility_id: str
    available_dates: list[str]
    permit_required: bool
    reservation_url: str
    contiguous: bool          # True if available for 2+ consecutive nights of the weekend


@dataclass
class WeatherDay:
    date: str
    high_c: float
    low_c: float
    rain_mm: float
    wind_kph: float
    condition: str


@dataclass
class LocationReport:
    location: str
    weekend_start: str        # Friday ISO date
    weekend_end: str          # Sunday ISO date
    available: bool           # True if any site has available dates
    sites: list[CampsiteResult]
    weather: dict[str, WeatherDay]   # keys: "friday", "saturday", "sunday"


@dataclass
class SearchResult:
    name: str
    facility_id: str
    available_dates: list[str]
    reservation_url: str
    contiguous: bool          # True if available for 2+ consecutive nights within the search range


@dataclass
class SearchReport:
    query: str
    start: str
    end: str
    results: list[SearchResult]
