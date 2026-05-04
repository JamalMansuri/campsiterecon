from datetime import date, timedelta
from .api_client import RecGovClient
from .models import RawCampgroundResponse, SearchResult, SearchReport, is_available
from .windows import consecutive_nights

_REC_BASE = "https://www.recreation.gov"
_SEARCH_NIGHTS = 2


def _date_range(start: date, end: date) -> set[date]:
    days = (end - start).days
    return {start + timedelta(i) for i in range(days + 1)}


def _months_spanned(start: date, end: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _open_dates_in_range(raw: dict, targets: set[date]) -> set[date]:
    response = RawCampgroundResponse.model_validate(raw)
    hits: set[date] = set()
    for site in response.campsites.values():
        for dt_str, status in site.availabilities.items():
            if not is_available(status):
                continue
            try:
                d = date.fromisoformat(dt_str[:10])
            except ValueError:
                continue
            if d in targets:
                hits.add(d)
    return hits


def search(client: RecGovClient, query: str, start: date, end: date, limit: int = 25) -> SearchReport:
    facilities = client.ridb_search_campgrounds(query, limit=limit)
    targets    = _date_range(start, end)
    months     = _months_spanned(start, end)
    results: list[SearchResult] = []

    for f in facilities:
        facility_id = str(f.get("FacilityID", ""))
        if not facility_id:
            continue

        open_dates: set[date] = set()
        for year, month in months:
            raw = client.campground_month(facility_id, year, month)
            if raw and raw.get("campsites"):
                open_dates |= _open_dates_in_range(raw, targets)

        if not open_dates:
            continue

        results.append(SearchResult(
            name            = f.get("FacilityName", "").title(),
            facility_id     = facility_id,
            available_dates = sorted(d.isoformat() for d in open_dates),
            reservation_url = f"{_REC_BASE}/camping/campgrounds/{facility_id}",
            contiguous      = bool(consecutive_nights(open_dates, _SEARCH_NIGHTS)),
        ))

    return SearchReport(
        query   = query,
        start   = start.isoformat(),
        end     = end.isoformat(),
        results = results,
    )
