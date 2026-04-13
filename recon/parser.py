from datetime import date, timedelta
from .config import Camp
from .models import CampsiteResult

_OPEN     = {"Available", "Open"}
_REC_BASE = "https://www.recreation.gov"


def _reservation_url(camp: Camp) -> str:
    """Permit-system camps always book through /permits/, even when the
    campground endpoint returns data for them (Rec.gov started populating
    Point Reyes through that endpoint in 2026 — URL must still be /permits/)."""
    if camp.permit_id:
        return f"{_REC_BASE}/permits/{camp.permit_id}"
    return f"{_REC_BASE}/camping/campgrounds/{camp.facility_id}"


def _weekend_dates(friday: date) -> set[date]:
    return {friday, friday + timedelta(1), friday + timedelta(2)}


def _is_contiguous(available: set[date], friday: date) -> bool:
    """True if available for at least 2 consecutive nights of the weekend."""
    sat = friday + timedelta(1)
    sun = friday + timedelta(2)
    return (friday in available and sat in available) or (sat in available and sun in available)


def _parse_campground(raw: dict, camp: Camp, friday: date) -> CampsiteResult:
    targets   = _weekend_dates(friday)
    available: set[date] = set()

    for site in raw.get("campsites", {}).values():
        for dt_str, status in site.get("availabilities", {}).items():
            if status not in _OPEN:
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
        permit_required = camp.permit_id is not None,
        reservation_url = _reservation_url(camp),
        contiguous      = _is_contiguous(available, friday),
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
        contiguous      = _is_contiguous(available, friday),
    )


def parse(response: dict, camp: Camp, friday: date) -> CampsiteResult:
    if response["type"] == "permit":
        return _parse_permit(response["data"], camp, friday)
    return _parse_campground(response["data"], camp, friday)
