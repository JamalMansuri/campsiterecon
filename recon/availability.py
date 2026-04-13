from datetime import date
from .api_client import RecGovClient
from .config import Camp


def fetch_camp_availability(client: RecGovClient, camp: Camp, friday: date) -> dict | None:
    """
    Try the standard campground endpoint first.
    If it returns no sites (common for permit-only camps like Point Reyes),
    fall back to the wilderness permit endpoint.

    Returns a tagged dict so the parser knows which response shape to expect:
        {"type": "campground", "data": {...}}
        {"type": "permit",     "data": {...}}
    Returns None if both endpoints fail or return empty.
    """
    raw = client.campground_month(camp.facility_id, friday.year, friday.month)
    if raw and raw.get("campsites"):
        return {"type": "campground", "data": raw}

    if camp.permit_id:
        raw = client.permit_month(camp.permit_id, friday.year, friday.month)
        if raw:
            return {"type": "permit", "data": raw}

    return None
