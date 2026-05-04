from datetime import date, timedelta
from .config import Camp
from .models import CampsiteResult, RawCampgroundResponse, is_available
from .windows import consecutive_nights

_REC_BASE = "https://www.recreation.gov"
_WEEKEND_NIGHTS = 2


def _reservation_url(camp: Camp) -> str:
    """Permit-system camps always book through /permits/, even when the
    campground endpoint returns data for them (Rec.gov started populating
    Point Reyes through that endpoint in 2026 — URL must still be /permits/)."""
    if camp.permit_id:
        return f"{_REC_BASE}/permits/{camp.permit_id}"
    return f"{_REC_BASE}/camping/campgrounds/{camp.facility_id}"


def _weekend_dates(friday: date) -> set[date]:
    return {friday, friday + timedelta(1), friday + timedelta(2)}


def _serialize_windows(windows: list[tuple[date, date]]) -> list[tuple[str, str]]:
    return [(s.isoformat(), e.isoformat()) for s, e in windows]


def _parse_campground(raw: dict, camp: Camp, friday: date) -> CampsiteResult:
    response                       = RawCampgroundResponse.model_validate(raw)
    targets                        = _weekend_dates(friday)
    flat:    set[date]             = set()
    by_site: dict[str, set[date]]  = {}

    for campsite_id, site in response.campsites.items():
        for dt_str, status in site.availabilities.items():
            if not is_available(status):
                continue
            try:
                d = date.fromisoformat(dt_str[:10])
            except ValueError:
                continue
            if d not in targets:
                continue
            flat.add(d)
            by_site.setdefault(campsite_id, set()).add(d)

    windows_by_site = {
        sid: _serialize_windows(consecutive_nights(dates, _WEEKEND_NIGHTS))
        for sid, dates in by_site.items()
    }
    windows_by_site = {sid: ws for sid, ws in windows_by_site.items() if ws}

    return CampsiteResult(
        name               = camp.name,
        facility_id        = camp.facility_id,
        available_dates    = sorted(d.isoformat() for d in flat),
        sites_by_id        = {sid: sorted(d.isoformat() for d in dates) for sid, dates in by_site.items()},
        windows_by_site_id = windows_by_site,
        permit_required    = camp.permit_id is not None,
        reservation_url    = _reservation_url(camp),
        contiguous         = bool(consecutive_nights(flat, _WEEKEND_NIGHTS)),
    )


def _parse_permit(raw: dict, camp: Camp, friday: date) -> CampsiteResult:
    targets   = _weekend_dates(friday)
    available: set[date] = set()
    payload   = raw.get("payload", raw)

    for dt_str, info in payload.get("availability", {}).items():
        remaining = info.get("remaining")
        if not isinstance(remaining, int) or remaining <= 0:
            continue
        try:
            d = date.fromisoformat(dt_str[:10])
        except ValueError:
            continue
        if d in targets:
            available.add(d)

    sorted_dates = sorted(d.isoformat() for d in available)
    return CampsiteResult(
        name            = camp.name,
        facility_id     = camp.facility_id,
        available_dates = sorted_dates,
        permit_required = True,
        reservation_url = _reservation_url(camp),
        contiguous      = bool(consecutive_nights(available, _WEEKEND_NIGHTS)),
    )


def parse(response: dict, camp: Camp, friday: date) -> CampsiteResult:
    if response["type"] == "permit":
        return _parse_permit(response["data"], camp, friday)
    return _parse_campground(response["data"], camp, friday)
