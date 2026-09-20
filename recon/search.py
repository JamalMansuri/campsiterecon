from datetime import date, timedelta
from .api_client import RecGovClient
from .geo import haversine_km
from .models import RawSiteAvailability, SearchResult, SearchReport, SearchSite
from .parser import campground_url, collect_open_sites, site_url, stay_rules_from_meta, validate_campground
from .windows import consecutive_nights, months_spanned as _months_spanned

_SEARCH_NIGHTS   = 2
_SAMPLE_SITES    = 5       # per facility; the ones with the most open nights
_MAX_DISTANCE_KM = 150.0   # keyword matches farther than this from the query's rec area are noise


def _date_range(start: date, end: date) -> set[date]:
    days = (end - start).days
    return {start + timedelta(i) for i in range(days + 1)}


def _display_name(raw_name: str | None) -> str:
    """RIDB shouts some names ("LOST CLAIM") and cases others properly
    ("McCabe Flat Campground"). Only title-case the shouted ones."""
    name = (raw_name or "").strip()
    return name.title() if name.isupper() else name


def _coord(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f != 0.0 else None


def rate_limit_warning(client, unchecked: int) -> list[str]:
    """One-line warning for the LLM when Rec.gov throttled us (this run or a recent one)."""
    if not getattr(client, "rate_limited", False):
        return []
    until = getattr(client, "rate_limited_until", None)
    when = f" until about {until.astimezone().strftime('%H:%M')}" if until else " for about 10 minutes"
    return [f"Recreation.gov is rate-limiting this IP (HTTP 429){when}: {unchecked} facilit{'y was' if unchecked == 1 else 'ies were'} "
            "not checked. Treat them as unknown, not full. Do not retry before then — every early request extends the block."]


def _site_has_window(dates: set[date]) -> bool:
    return bool(consecutive_nights(dates, _SEARCH_NIGHTS))


def search(client: RecGovClient, query: str, start: date, end: date,
           max_results: int = 150, max_distance_km: float = _MAX_DISTANCE_KM) -> SearchReport:
    facilities, total = client.ridb_search_campgrounds(query, max_results=max_results)
    ridb_error = getattr(client, "last_error", None) if not facilities else None
    anchor  = client.ridb_search_recarea(query)
    targets = _date_range(start, end)
    months  = _months_spanned(start, end)

    results:     list[SearchResult] = []
    skipped_far: list[str]          = []
    unreachable: list[str]          = []
    partial:     list[str]          = []
    warnings:    list[str]          = []
    scanned = 0

    if ridb_error:
        warnings.append(f"RIDB facility search failed (HTTP {ridb_error}) — nothing was scanned; check the API key.")
    elif getattr(client, "ridb_pages_failed", 0) and facilities:
        warnings.append(f"RIDB stopped answering after {len(facilities)} of {total} matching facilities — "
                        "the rest were not considered.")
    skipped_total, skipped_facilities = 0, 0

    for f in facilities:
        facility_id = str(f.get("FacilityID") or "")
        if not facility_id:
            continue
        name = _display_name(f.get("FacilityName"))
        lat, lon = _coord(f.get("FacilityLatitude")), _coord(f.get("FacilityLongitude"))

        distance: float | None = None
        if anchor and lat is not None and lon is not None:
            distance = round(haversine_km(anchor["lat"], anchor["lon"], lat, lon), 1)
            if distance > max_distance_km:
                skipped_far.append(name)
                continue
        scanned += 1

        opened: dict[str, tuple[RawSiteAvailability, set[date]]] = {}
        missing: list[str] = []
        skipped = 0
        for year, month in months:
            raw = client.campground_month(facility_id, year, month)
            if not isinstance(raw, dict):
                missing.append(f"{year}-{month:02d}")
                continue
            if not raw.get("campsites"):
                continue
            response, bad = validate_campground(raw)
            skipped += bad
            for sid, (site, dates) in collect_open_sites(response, targets).items():
                if sid in opened:
                    opened[sid][1].update(dates)
                else:
                    opened[sid] = (site, set(dates))

        if len(missing) == len(months):
            reason = client.error_for(facility_id) if hasattr(client, "error_for") else None
            unreachable.append(f"{name} ({reason})" if reason else name)
            continue
        if missing:
            partial.append(f"{name} ({', '.join(missing)} not checked)")
        if skipped:
            skipped_total += skipped
            skipped_facilities += 1
        if not opened:
            continue

        flat: set[date] = set().union(*(dates for _, dates in opened.values()))
        # Any site that hosts a 2-night window comes first, so `contiguous: true`
        # is always backed by a named, linkable site in sample_sites.
        best = sorted(opened.items(),
                      key=lambda kv: (not _site_has_window(kv[1][1]), -len(kv[1][1]), kv[0]))[:_SAMPLE_SITES]

        results.append(SearchResult(
            name            = name,
            official_name   = (f.get("FacilityName") or "").strip() or None,
            facility_id     = facility_id,
            rec_area        = client.ridb_recarea_name(f.get("ParentRecAreaID")),
            latitude        = lat,
            longitude       = lon,
            distance_km     = distance,
            available_dates = sorted(d.isoformat() for d in flat),
            open_site_count = len(opened),
            skipped_sites   = skipped,
            sample_sites    = [
                SearchSite(campsite_id=sid, site=site.site, loop=site.loop, campsite_type=site.campsite_type,
                           min_people=site.min_num_people, max_people=site.max_num_people,
                           dates=sorted(d.isoformat() for d in dates), url=site_url(sid))
                for sid, (site, dates) in best
            ],
            stay_rules      = stay_rules_from_meta(client.campground_meta(facility_id)) if hasattr(client, "campground_meta") else None,
            reservation_url = campground_url(facility_id),
            # per-site, never the union across sites (see parser.py)
            contiguous      = any(_site_has_window(dates) for _, dates in opened.values()),
        ))

    results.sort(key=lambda r: (r.distance_km is None, r.distance_km or 0.0, r.name))
    if skipped_total:
        warnings.append(f"{skipped_total} campsite record{'s' if skipped_total != 1 else ''} with an unrecognised shape "
                        f"across {skipped_facilities} facilit{'ies' if skipped_facilities != 1 else 'y'} were skipped.")

    return SearchReport(
        query              = query,
        start              = start.isoformat(),
        end                = end.isoformat(),
        anchor             = anchor["name"] if anchor else None,
        facilities_total   = total,
        facilities_scanned = scanned,
        skipped_far        = skipped_far,
        unreachable        = unreachable,
        partial            = partial,
        warnings           = warnings + rate_limit_warning(client, len(unreachable)),
        results            = results,
    )
