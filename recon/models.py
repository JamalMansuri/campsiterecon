from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Raw Rec.gov response shapes (boundary validation, extra fields ignored)
# ---------------------------------------------------------------------------

class RawSiteAvailability(BaseModel):
    """One campsite's per-date status, mirroring the Rec.gov API shape.

    The endpoint is undocumented and its serializer emits nulls for keys that
    are dicts elsewhere, so every field is coerced leniently: a bad value
    degrades to its default instead of raising and taking the whole run down."""
    model_config = ConfigDict(extra="ignore")

    availabilities: dict[str, str] = Field(default_factory=dict)
    quantities: dict[str, int | None] | None = None
    campsite_id: str | None = None
    loop: str | None = None
    site: str | None = None
    campsite_type: str | None = None
    campsite_reserve_type: str | None = None
    type_of_use: str | None = None        # "Overnight" or "Day"
    hide_external: bool = False           # True = not shown on the public site
    min_num_people: int | None = None
    max_num_people: int | None = None

    @field_validator("loop", "site", "campsite_type", "campsite_reserve_type", "type_of_use", "campsite_id", mode="before")
    @classmethod
    def _str_or_none(cls, v):
        if v is None or v == "":
            return None
        return v if isinstance(v, str) else str(v)

    @field_validator("min_num_people", "max_num_people", mode="before")
    @classmethod
    def _int_or_none(cls, v):
        if v is None or v == "" or isinstance(v, bool):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @field_validator("hide_external", mode="before")
    @classmethod
    def _bool(cls, v):
        if v is None:
            return False
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return bool(v)

    @field_validator("availabilities", mode="before")
    @classmethod
    def _availabilities(cls, v):
        if not isinstance(v, dict):
            return {}
        return {str(k): str(status) for k, status in v.items() if isinstance(status, str)}

    @field_validator("quantities", mode="before")
    @classmethod
    def _quantities(cls, v):
        if not isinstance(v, dict):
            return None
        return {str(k): (q if isinstance(q, int) and not isinstance(q, bool) else None) for k, q in v.items()}


class RawCampgroundResponse(BaseModel):
    """Top-level shape of /api/camps/availability/campground/{id}/month."""
    model_config = ConfigDict(extra="ignore")

    campsites: dict[str, RawSiteAvailability] = Field(default_factory=dict)
    count: int | None = None


class RawPermitDate(BaseModel):
    """One entry date inside a permit division's date_availability."""
    model_config = ConfigDict(extra="ignore")

    total: int | None = None
    remaining: int | None = None
    show_walkup: bool = False
    is_secret_quota: bool = False


class RawPermitDivision(BaseModel):
    """One division (entry point / zone) of /api/permits/{id}/availability/month."""
    model_config = ConfigDict(extra="ignore")

    division_id: str | None = None
    date_availability: dict[str, RawPermitDate] = Field(default_factory=dict)


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


def is_bookable_site(site: RawSiteAvailability) -> bool:
    """Sites that can never be reserved online: hidden from the public site,
    or day-use only. Filtered before any date is counted."""
    if site.hide_external:
        return False
    if site.type_of_use and site.type_of_use.strip().lower() == "day":
        return False
    return True


# ---------------------------------------------------------------------------
# Emitted JSON shapes
# ---------------------------------------------------------------------------

class SiteDetail(BaseModel):
    """Human-readable identity + deep link for one open campsite."""
    site: str | None = None            # Rec.gov's label, e.g. "003" or "BOAT A, 1-6 people"
    loop: str | None = None
    campsite_type: str | None = None   # "STANDARD NONELECTRIC", "GROUP HIKE TO", "BOAT IN", ... — group/boat sites are not ordinary campsites
    min_people: int | None = None
    max_people: int | None = None
    url: str                           # https://www.recreation.gov/camping/campsites/{campsite_id}


class StayRules(BaseModel):
    """Booking rules from Rec.gov's facility_rules. Each minimum carries
    Rec.gov's qualifier: "strict" = enforced at checkout; "soft"/"softAny" =
    an orphan night shorter than the minimum may still be bookable (Rec.gov
    decides at checkout). Say the qualifier, don't declare a soft minimum
    unbookable."""
    min_nights: int | None = None                 # minConsecutiveStay
    min_nights_policy: str | None = None          # "strict" | "soft" | "softAny"
    min_weekend_nights: int | None = None         # minWeekendStay
    min_weekend_policy: str | None = None
    min_holiday_weekend_nights: int | None = None # minHolidayWeekendStay
    min_holiday_weekend_policy: str | None = None
    max_nights: int | None = None                 # maxConsecutiveStay


class CampsiteResult(BaseModel):
    name: str                          # preset label from config.py
    facility_id: str
    official_name: str | None = None   # Rec.gov's own facility name; qualifies `name`, does not replace it
    loop: str | None = None            # set when the preset is one loop of a larger facility (Point Reyes)
    loop_matched: bool | None = None   # False = the loop filter matched NO campsite of any status (preset is wrong)
    skipped_sites: int = 0             # campsite records with an unrecognised shape, ignored
    available_dates: list[str]
    sites_by_id: dict[str, list[str]] = Field(default_factory=dict)
    windows_by_site_id: dict[str, list[tuple[str, str]]] = Field(default_factory=dict)
    site_details: dict[str, SiteDetail] = Field(default_factory=dict)
    stay_rules: StayRules | None = None
    permit_required: bool
    reservation_url: str
    contiguous: bool                   # some ONE site has 2 consecutive open nights; always False for permits


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
    nights: list[str] = Field(default_factory=list)      # the nights that were checked (Fri, Sat, Sun)
    available: bool
    sites: list[CampsiteResult]
    unreachable: list[str] = Field(default_factory=list)  # camps whose fetch failed — NOT the same as "full"
    warnings: list[str] = Field(default_factory=list)     # e.g. Rec.gov rate-limited this run
    weather: dict[str, WeatherDay]


class SearchSite(BaseModel):
    campsite_id: str
    site: str | None = None
    loop: str | None = None
    campsite_type: str | None = None   # e.g. "STANDARD NONELECTRIC", "GROUP HIKE TO" — say when it's group-only
    category: str | None = None        # "group" | "boat_in" | None (ordinary). Only ever non-null with --all-site-types
    min_people: int | None = None
    max_people: int | None = None
    dates: list[str]
    url: str


class SearchResult(BaseModel):
    name: str                          # display name (title-cased when RIDB shouts)
    official_name: str | None = None   # RIDB FacilityName verbatim
    facility_id: str
    rec_area: str | None = None        # parent rec area, e.g. "Stanislaus National Forest" — say this, the query is fuzzy
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None   # from the query's rec area (`anchor`), when one was resolved
    available_dates: list[str]
    open_site_count: int = 0           # sites counted toward this result (group / boat-in excluded unless asked for)
    excluded_open_sites: dict[str, int] = Field(default_factory=dict)  # {"group": n, "boat_in": m} open but not counted
    special_open_sites: dict[str, int] = Field(default_factory=dict)   # --all-site-types only: group / boat-in sites that ARE counted
    skipped_sites: int = 0             # campsite records with an unrecognised shape, ignored
    sample_sites: list[SearchSite] = Field(default_factory=list)  # up to 5: any site with a 2-night window first, then most open nights
    stay_rules: StayRules | None = None
    reservation_url: str
    contiguous: bool


class SearchReport(BaseModel):
    query: str
    start: str
    end: str
    site_types: str = "standard"       # "standard" = group + boat-in sites skipped (default); "all" = --all-site-types
    anchor: str | None = None          # rec area the query resolved to; distances/filtering are relative to it
    facilities_total: int = 0          # RIDB TOTAL_COUNT for the query
    facilities_scanned: int = 0        # how many of those we actually checked
    skipped_far: list[str] = Field(default_factory=list)  # matched the keyword but > 150 km from the anchor; not checked
    unreachable: list[str] = Field(default_factory=list)  # facilities whose availability fetch failed
    partial: list[str] = Field(default_factory=list)      # facilities with one or more months unchecked
    group_or_boat_only: list[str] = Field(default_factory=list)  # open, but only at group / boat-in sites — not in results
    warnings: list[str] = Field(default_factory=list)     # e.g. Rec.gov rate-limited this run
    results: list[SearchResult]


class VerifiedCamp(BaseModel):
    location_key: str
    name: str
    facility_id: str
    loop: str | None = None
    permit_id: str | None = None
    ridb_name: str | None = None
    ridb_type: str | None = None
    ridb_rec_area: str | None = None
    recgov_name: str | None = None
    distance_km: float | None = None   # preset lat/lon → facility lat/lon
    loops_found: list[str] = Field(default_factory=list)
    ok: bool
    problem: str | None = None


class VerifyReport(BaseModel):
    ok: bool
    camps: list[VerifiedCamp]
    problems: list[str]
    warnings: list[str] = Field(default_factory=list)   # e.g. RIDB unreachable, so the type check was skipped
