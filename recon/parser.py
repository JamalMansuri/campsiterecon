from datetime import date, timedelta
from pydantic import ValidationError
from .config import Camp
from .models import (
    CampsiteResult, RawCampgroundResponse, RawSiteAvailability, SiteDetail, StayRules,
    is_available, is_bookable_site,
)
from .windows import consecutive_nights

_REC_BASE = "https://www.recreation.gov"
_WEEKEND_NIGHTS = 2


# ---------------------------------------------------------------------------
# URL builders — the ONLY place booking URLs are constructed. The LLM consuming
# the JSON must use these verbatim, never build its own.
# ---------------------------------------------------------------------------

def campground_url(facility_id: str) -> str:
    return f"{_REC_BASE}/camping/campgrounds/{facility_id}"


def site_url(campsite_id: str) -> str:
    return f"{_REC_BASE}/camping/campsites/{campsite_id}"


def permit_url(permit_id: str) -> str:
    return f"{_REC_BASE}/permits/{permit_id}"


def _reservation_url(camp: Camp) -> str:
    """Keyed off camp.permit_id, not the endpoint that answered: a permit-system
    camp books through /permits/ even if availability came from elsewhere."""
    if camp.permit_id:
        return permit_url(camp.permit_id)
    return campground_url(camp.facility_id)


# ---------------------------------------------------------------------------
# Campground responses
# ---------------------------------------------------------------------------

def _weekend_dates(friday: date) -> set[date]:
    return {friday, friday + timedelta(1), friday + timedelta(2)}


def _serialize_windows(windows: list[tuple[date, date]]) -> list[tuple[str, str]]:
    return [(s.isoformat(), e.isoformat()) for s, e in windows]


def _loop_matches(site: RawSiteAvailability, loop: str | None) -> bool:
    if loop is None:
        return True
    return (site.loop or "").strip().lower() == loop.strip().lower()


def validate_campground(raw: object) -> tuple[RawCampgroundResponse, int]:
    """Validate a month payload ONE SITE AT A TIME so a single malformed record
    is skipped (and counted) instead of aborting the run. Returns
    (response, skipped_count). Non-dict payloads validate to an empty response."""
    sites: dict[str, RawSiteAvailability] = {}
    skipped = 0
    campsites = raw.get("campsites") if isinstance(raw, dict) else None
    for sid, site in (campsites.items() if isinstance(campsites, dict) else ()):
        if not isinstance(site, dict):
            skipped += 1
            continue
        try:
            sites[str(sid)] = RawSiteAvailability.model_validate(site)
        except ValidationError:
            skipped += 1
    return RawCampgroundResponse(campsites=sites, count=len(sites)), skipped


def loops_in(response: RawCampgroundResponse) -> list[str]:
    return sorted({(s.loop or "").strip() for s in response.campsites.values()} - {""})


def collect_open_sites(
    response: RawCampgroundResponse,
    targets: set[date],
    loop: str | None = None,
) -> dict[str, tuple[RawSiteAvailability, set[date]]]:
    """campsite_id -> (site, open target dates) for every bookable site with at
    least one bookable night inside `targets`. Shared by weekend + search mode."""
    out: dict[str, tuple[RawSiteAvailability, set[date]]] = {}
    for campsite_id, site in response.campsites.items():
        if not is_bookable_site(site) or not _loop_matches(site, loop):
            continue
        open_dates: set[date] = set()
        for dt_str, status in site.availabilities.items():
            if not is_available(status):
                continue
            try:
                d = date.fromisoformat(dt_str[:10])
            except ValueError:
                continue
            if d in targets:
                open_dates.add(d)
        if open_dates:
            out[campsite_id] = (site, open_dates)
    return out


def _official_name(meta: dict | None) -> str | None:
    if not isinstance(meta, dict):
        return None
    return (meta.get("facility_name") or "").strip() or None


_RULE_KEYS = {
    "minConsecutiveStay":    "min_nights",
    "minWeekendStay":        "min_weekend_nights",
    "minHolidayWeekendStay": "min_holiday_weekend_nights",
    "maxConsecutiveStay":    "max_nights",
}


_POLICY_FIELD = {
    "min_nights":                 "min_nights_policy",
    "min_weekend_nights":         "min_weekend_policy",
    "min_holiday_weekend_nights": "min_holiday_weekend_policy",
}


def stay_rules_from_meta(meta: dict | None) -> StayRules | None:
    """Pull min/max-stay rules out of /api/camps/campgrounds/{id} facility_rules.
    Each rule is {"value": int, "secondary_value": "soft"|"strict"|"softAny", ...};
    a value of 0 means no rule. The qualifier is kept — a "soft" minimum is not
    a hard "not bookable"."""
    rules = (meta or {}).get("facility_rules") if isinstance(meta, dict) else None
    if not isinstance(rules, dict):
        return None
    found: dict[str, object] = {}
    for api_key, field in _RULE_KEYS.items():
        rule = rules.get(api_key)
        value = rule.get("value") if isinstance(rule, dict) else None
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            found[field] = value
            policy = (rule.get("secondary_value") or "").strip() if isinstance(rule, dict) else ""
            if field in _POLICY_FIELD and policy:
                found[_POLICY_FIELD[field]] = policy
    return StayRules(**found) if found else None


def _parse_campground(raw: dict, camp: Camp, friday: date, meta: dict | None) -> CampsiteResult:
    response, skipped = validate_campground(raw)
    opened   = collect_open_sites(response, _weekend_dates(friday), camp.loop)
    loop_matched = None if camp.loop is None else any(_loop_matches(s, camp.loop) for s in response.campsites.values())
    flat: set[date] = set().union(*(dates for _, dates in opened.values())) if opened else set()

    windows_by_site = {
        sid: _serialize_windows(consecutive_nights(dates, _WEEKEND_NIGHTS))
        for sid, (_, dates) in opened.items()
    }
    windows_by_site = {sid: ws for sid, ws in windows_by_site.items() if ws}

    return CampsiteResult(
        name               = camp.name,
        facility_id        = camp.facility_id,
        official_name      = _official_name(meta),
        loop               = camp.loop,
        loop_matched       = loop_matched,
        skipped_sites      = skipped,
        available_dates    = sorted(d.isoformat() for d in flat),
        sites_by_id        = {sid: sorted(d.isoformat() for d in dates) for sid, (_, dates) in opened.items()},
        windows_by_site_id = windows_by_site,
        site_details       = {
            sid: SiteDetail(site=site.site, loop=site.loop, campsite_type=site.campsite_type,
                            min_people=site.min_num_people, max_people=site.max_num_people, url=site_url(sid))
            for sid, (site, _) in opened.items()
        },
        stay_rules         = stay_rules_from_meta(meta),
        permit_required    = camp.permit_id is not None,
        reservation_url    = _reservation_url(camp),
        # A 2-night stay has to be at ONE site. Fri open at site A + Sat open at
        # site B is two one-night trips, not a weekend — so this is per-site,
        # never the union across sites.
        contiguous         = bool(windows_by_site),
    )


# ---------------------------------------------------------------------------
# Permit responses
# ---------------------------------------------------------------------------

def _add_remaining(out: dict[date, int], dt_str: str, info: object) -> None:
    remaining = info.get("remaining") if isinstance(info, dict) else None
    if not isinstance(remaining, int) or remaining <= 0:
        return
    try:
        d = date.fromisoformat(str(dt_str)[:10])
    except ValueError:
        return
    out[d] = out.get(d, 0) + remaining


def permit_open_dates(raw: dict) -> dict[date, int]:
    """date -> permits remaining (summed across divisions) for
    /api/permits/{id}/availability/month.

    Handles the live shape and, defensively, a flat one:
      live:      payload.availability[division_id].date_availability[date].remaining
      defensive: payload.availability[date].remaining  (never observed live; cheap to keep)
    Validated only against lottery/day-use style permits (e.g. 4675311, Half
    Dome 234652). NPS wilderness permits such as Yosemite 445859 are NOT served
    by this endpoint at all (HTTP 404) — see references/api-response-shapes.md.
    """
    payload = raw.get("payload", raw) if isinstance(raw, dict) else {}
    availability = payload.get("availability") if isinstance(payload, dict) else None
    out: dict[date, int] = {}
    for key, value in (availability or {}).items():
        if not isinstance(value, dict):
            continue
        if "date_availability" in value:
            inner = value.get("date_availability")
            for dt_str, info in (inner.items() if isinstance(inner, dict) else ()):
                _add_remaining(out, dt_str, info)
        elif "remaining" in value:
            _add_remaining(out, key, value)
    return out


def _parse_permit(raw: dict, camp: Camp, friday: date, meta: dict | None) -> CampsiteResult:
    targets   = _weekend_dates(friday)
    available = {d for d in permit_open_dates(raw) if d in targets}
    return CampsiteResult(
        name            = camp.name,
        facility_id     = camp.facility_id,
        official_name   = _official_name(meta),
        loop            = camp.loop,
        available_dates = sorted(d.isoformat() for d in available),
        permit_required = True,
        reservation_url = _reservation_url(camp),
        # Permit dates are trip START dates with quota remaining, not nights at
        # a site — "two consecutive dates" means nothing for a permit.
        contiguous      = False,
    )


def parse(response: dict, camp: Camp, friday: date) -> CampsiteResult:
    meta = response.get("meta")
    if response["type"] == "permit":
        return _parse_permit(response["data"], camp, friday, meta)
    return _parse_campground(response["data"], camp, friday, meta)
