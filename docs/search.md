# recon/search.py

Free-text location search. Turns "Yosemite, July 3–5" into a list of bookable campgrounds with their open dates. The whole of Mode 2 lives here.

[Source](../recon/search.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def search(client: RecGovClient, query: str, start: date, end: date, limit: int = 25) -> SearchReport
```

Returns a `SearchReport` (see [models.md](models.md)) with a `results[]` array. Each result is one facility that has at least one open date in the requested range.

## Flow

1. **RIDB lookup** — `client.ridb_search_campgrounds(query)` returns up to `limit` reservable facilities matching the query.
2. **Compute the calendar months spanned** — `_months_spanned(start, end)` walks year/month from start to end. Cross-month ranges (e.g. `2026-07-30` → `2026-08-02`) yield `[(2026, 7), (2026, 8)]`.
3. **Per facility, per month**: call `client.campground_month()`. Merge open dates from each month's response.
4. **Filter to the target date set** — `_open_dates_in_range()` keeps only dates that fall inside `start..end` and have status `Available` or `Open`.
5. **Drop facilities with zero open dates.** Empty results don't pollute the output.
6. **Emit a `SearchResult` per surviving facility** with the merged dates, a reservation URL, and a `contiguous` flag.

## `contiguous` is looser than weekend mode

```python
def _has_contiguous(dates):
    return any((d + timedelta(1)) in dates for d in dates)
```

Any two consecutive days anywhere in the open set counts. Weekend mode (in [parser.md](parser.md)) is stricter — it specifically wants Fri+Sat or Sat+Sun. The looser definition makes sense for search because the user is planning around their own date range, not the calendar weekend.

## What search mode deliberately does NOT do

- **No weather.** Open-Meteo's free forecast only goes 14 days out, and search mode is designed for trips months ahead. Calling [weather.md](weather.md) would just return empty for most queries. Skipping it also keeps Mode 2 fast.
- **No permit endpoint.** Permit-only camps (Point Reyes pattern) won't appear in results. By design — search mode trusts that the user knows to use a preset for those, and [SKILL.md](../SKILL.md) routes them accordingly.
- **No facility deduping.** RIDB sometimes returns the same facility under multiple records with different IDs. We trust RIDB's output and let dupes through; in practice this is rare.

## Upstream / downstream

- **Called by**: [main.md](main.md) when `--search` is present
- **Calls**: [api_client.md](api_client.md) (RIDB + campground endpoints)
- **Outputs**: `SearchReport` from [models.md](models.md)

## Limit

Default is 25 facilities. Each facility costs `len(months_spanned)` HTTP calls, so a 3-month range with 25 facilities is 75 requests. Don't crank `limit` without thinking about that.
