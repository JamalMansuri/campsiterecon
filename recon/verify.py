"""Preset verification (`python main.py --verify`).

Every wrong booking link this project has ever produced came from a wrong
facility id in config.py or a reference doc. This module makes that class of
bug loud: for each preset camp it asks RIDB and Rec.gov what the id really is,
checks the facility sits near the preset's coordinates, checks the type
matches (Campground vs Permit), and — when the camp is one loop of a larger
facility — checks that loop name exists in the live availability response.
"""

from datetime import date

from .config import LOCATIONS, Location
from .geo import haversine_km
from .models import VerifiedCamp, VerifyReport

_MAX_DISTANCE_KM = 150.0


def _loops_in(raw: dict | None) -> list[str]:
    sites = (raw or {}).get("campsites") or {}
    return sorted({(s.get("loop") or "").strip() for s in sites.values() if isinstance(s, dict)} - {""})


def _coord(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f != 0.0 else None


def _name_token(name: str) -> str | None:
    """First word of the preset label worth matching ("Kirk", "Plaskett", "Cold")."""
    for word in name.replace("-", " ").split():
        w = "".join(c for c in word if c.isalnum())
        if len(w) >= 4:
            return w.lower()
    return None


def verify_presets(client, locations: dict[str, Location] | None = None, today: date | None = None) -> VerifyReport:
    locations = LOCATIONS if locations is None else locations
    today = today or date.today()
    camps: list[VerifiedCamp] = []
    problems: list[str] = []
    ridb_missing: list[str] = []

    for key, loc in locations.items():
        for camp in loc.camps:
            ridb = client.ridb_facility(camp.facility_id) or {}
            meta = client.campground_meta(camp.facility_id) or {}
            problem: str | None = None
            distance: float | None = None
            loops_found: list[str] = []

            ridb_name   = (ridb.get("FacilityName") or "").strip() or None
            ridb_type   = (ridb.get("FacilityTypeDescription") or "").strip() or None
            rec_area    = client.ridb_recarea_name(ridb.get("ParentRecAreaID"))
            recgov_name = (meta.get("facility_name") or "").strip() or None

            if meta and not ridb:
                ridb_missing.append(camp.facility_id)
            if not ridb and not meta:
                problem = "facility id unknown to both RIDB and Rec.gov"
            else:
                lat = _coord(ridb.get("FacilityLatitude")) or _coord(meta.get("facility_latitude"))
                lon = _coord(ridb.get("FacilityLongitude")) or _coord(meta.get("facility_longitude"))
                if lat is None or lon is None:
                    problem = "no coordinates on RIDB or Rec.gov — cannot verify the facility is where the preset says"
                else:
                    distance = round(haversine_km(loc.lat, loc.lon, lat, lon), 1)
                    if distance > _MAX_DISTANCE_KM:
                        problem = f"facility is {distance:.0f} km from the {loc.name} preset (RIDB calls it {ridb_name!r})"
                expected = "Permit" if camp.permit_id else "Campground"
                if problem is None and ridb_type and ridb_type != expected:
                    problem = f"RIDB type is {ridb_type!r}, expected {expected!r}"
                if problem is None and camp.loop is None:
                    # Name check: the preset label's key word must appear in the official name.
                    token = _name_token(camp.name)
                    official = f"{ridb_name or ''} {recgov_name or ''}".lower()
                    if token and token not in official:
                        problem = f"name mismatch: preset {camp.name!r} but Rec.gov/RIDB call {camp.facility_id} {ridb_name or recgov_name!r}"
                if problem is None and camp.loop is not None:
                    raw = client.campground_month(camp.facility_id, today.year, today.month)
                    if raw is None:
                        # Distinguish "Rec.gov didn't answer" from "loop isn't there":
                        # the former is usually the 429 throttle, not a config bug.
                        why = "HTTP 429 rate limit" if getattr(client, "rate_limited", False) else "fetch failed"
                        problem = f"could not fetch availability to check loop {camp.loop!r} ({why}) — rerun in a few minutes"
                    else:
                        loops_found = _loops_in(raw)
                        if camp.loop.strip().lower() not in {l.lower() for l in loops_found}:
                            problem = f"loop {camp.loop!r} not found in live response; loops present: {loops_found}"

            ok = problem is None
            camps.append(VerifiedCamp(
                location_key=key, name=camp.name, facility_id=camp.facility_id, loop=camp.loop,
                permit_id=camp.permit_id, ridb_name=ridb_name, ridb_type=ridb_type, ridb_rec_area=rec_area,
                recgov_name=recgov_name, distance_km=distance, loops_found=loops_found, ok=ok, problem=problem,
            ))
            if not ok:
                problems.append(f"[{key}] {camp.name} ({camp.facility_id}): {problem}")

    warnings: list[str] = []
    if ridb_missing:
        # last_error only reflects the most recent fetch; the per-URL error log keeps the RIDB reason.
        reasons = [r for url, r in getattr(client, "errors", {}).items() if "ridb.recreation.gov" in url]
        status = getattr(client, "last_error", None)
        why = reasons[-1] if reasons else (f"HTTP {status}" if status else "no answer")
        hint = " — the RIDB API key is missing or revoked" if ("401" in why or "403" in why) else ""
        warnings.append(f"RIDB did not answer for {len(set(ridb_missing))} facility id(s) ({why}){hint}; "
                        "names and coordinates were checked against Rec.gov only and the Campground/Permit type check was skipped.")
    return VerifyReport(ok=not problems, camps=camps, problems=problems, warnings=warnings)
