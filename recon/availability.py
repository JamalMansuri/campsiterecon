from datetime import date, timedelta
from .api_client import RecGovClient
from .config import Camp
from .windows import months_spanned

_WEEKEND_DAYS = 3   # Fri, Sat, Sun nights


def _merge_campground_months(raws: list[dict]) -> dict:
    """Union several month responses for one facility into one campsites dict."""
    merged: dict[str, dict] = {}
    for raw in raws:
        for sid, site in (raw.get("campsites") or {}).items():
            if not isinstance(site, dict):
                continue
            if sid not in merged:
                merged[sid] = dict(site)
                merged[sid]["availabilities"] = dict(site.get("availabilities") or {})
                merged[sid]["quantities"] = dict(site.get("quantities") or {}) or None
                continue
            merged[sid]["availabilities"].update(site.get("availabilities") or {})
            if site.get("quantities"):
                merged[sid]["quantities"] = {**(merged[sid].get("quantities") or {}), **site["quantities"]}
    return {"campsites": merged, "count": len(merged)}


def _merge_permit_months(raws: list[dict]) -> dict:
    """Union several permit month responses (division-keyed) into one payload."""
    divisions: dict[str, dict] = {}
    for raw in raws:
        payload = raw.get("payload", raw) if isinstance(raw, dict) else {}
        for key, value in (payload.get("availability") or {}).items():
            if not isinstance(value, dict):
                continue
            if "date_availability" in value:
                div = divisions.setdefault(key, {"division_id": value.get("division_id", key), "date_availability": {}})
                div["date_availability"].update(value.get("date_availability") or {})
            else:                                   # legacy flat shape: key is a date
                divisions.setdefault("_flat", {"division_id": "_flat", "date_availability": {}})
                divisions["_flat"]["date_availability"][key] = value
    return {"payload": {"availability": divisions}}


def fetch_camp_availability(client: RecGovClient, camp: Camp, friday: date) -> dict | None:
    """
    Fetch every month the Fri/Sat/Sun nights touch (a weekend can straddle a
    month boundary — Fri Oct 30 / Sat Oct 31 / Sun Nov 1 needs both months).
    Try the standard campground endpoint first; if it returns no sites and the
    camp has a permit_id, fall back to the wilderness permit endpoint.

    Returns a tagged dict so the parser knows which response shape to expect:
        {"type": "campground", "data": {...}, "meta": {...} | None, "missing_months": ["2026-11"], "empty_months": []}
        {"type": "permit",     "data": {...}, "meta": {...} | None, "missing_months": [...], "empty_months": []}
    `meta` is Rec.gov's facility record (official name etc.), None if unavailable.
    `missing_months` lists months whose fetch FAILED — nights in them were NOT
    checked; `empty_months` lists months Rec.gov answered with no campsites at
    all (checked, nothing listed — usually a seasonal closure). Callers surface
    both as warnings.
    Returns None only if nothing came back at all — callers report that as
    "couldn't check", not as "no availability".
    """
    months = months_spanned(friday, friday + timedelta(_WEEKEND_DAYS - 1))

    raws, missing, empty = [], [], []
    for year, month in months:
        raw = client.campground_month(camp.facility_id, year, month)
        if isinstance(raw, dict) and raw.get("campsites"):
            raws.append(raw)
        elif isinstance(raw, dict):
            empty.append(f"{year}-{month:02d}")
        else:
            missing.append(f"{year}-{month:02d}")
    if raws:
        data = raws[0] if len(raws) == 1 else _merge_campground_months(raws)
        return {"type": "campground", "data": data, "meta": client.campground_meta(camp.facility_id),
                "missing_months": missing, "empty_months": empty}

    if camp.permit_id:
        raws, missing = [], []
        for year, month in months:
            raw = client.permit_month(camp.permit_id, year, month)
            if raw:
                raws.append(raw)
            else:
                missing.append(f"{year}-{month:02d}")
        if raws:
            data = raws[0] if len(raws) == 1 else _merge_permit_months(raws)
            return {"type": "permit", "data": data, "meta": client.campground_meta(camp.facility_id),
                    "missing_months": missing, "empty_months": []}

    if empty:   # Rec.gov answered but lists no campsites: checked, nothing bookable, say why
        return {"type": "campground", "data": {"campsites": {}}, "meta": client.campground_meta(camp.facility_id),
                "missing_months": missing, "empty_months": empty}
    return None
