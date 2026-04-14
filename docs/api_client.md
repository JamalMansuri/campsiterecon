# recon/api_client.py

The only module in the program that talks HTTP. Wraps three Recreation.gov endpoints behind a single class. Knows nothing about campsites, dates, or business logic — that's all in callers.

[Source](../recon/api_client.py) · Wiki home: [README.md](README.md)

## Public surface

```python
class RecGovClient:
    def __init__(self, api_key: str)
    def campground_month(facility_id, year, month) -> dict | None
    def permit_month(permit_id, year, month) -> dict | None
    def ridb_search_campgrounds(query, limit=50) -> list[dict]
```

All three methods return `None` / `[]` on any HTTPError, URLError, or JSON decode failure. Callers must handle empty results, never network errors.

## The three endpoints

| Method | Host | Auth | Used by |
|---|---|---|---|
| `campground_month` | `recreation.gov/api/camps/availability/campground/{id}/month` | None (User-Agent header only) | [availability.md](availability.md), [search.md](search.md) |
| `permit_month` | `recreation.gov/api/permits/{id}/availability/month` | None (User-Agent header only) | [availability.md](availability.md) |
| `ridb_search_campgrounds` | `ridb.recreation.gov/api/v1/facilities` | API key in querystring | [search.md](search.md) |

## Why two different APIs

Recreation.gov runs two separate systems:

- **RIDB** (`ridb.recreation.gov`) is the public facility *directory*. Stable, search-friendly, rate-limited, requires an API key. Used to resolve a free-text name → facility ID. No availability data.
- **Rec.gov** (`recreation.gov/api/...`) is the live booking engine. Returns per-day availability. No key required, but expects a real `User-Agent` (we send `CampsiteRecon/1.0`). Internal API; can change without notice.

Search mode needs both: RIDB to find facilities by name, Rec.gov to check if any of them are bookable. Weekend mode skips RIDB because preset facility IDs are hardcoded in [config.md](config.md).

## Failure model

Every method wraps `urlopen` in a try/except over `(HTTPError, URLError, JSONDecodeError)` and returns the empty case. This is deliberate:

- A missing facility (`404`) is functionally the same as "no campsites available" from the caller's perspective.
- A network blip during a multi-month scan in [search.md](search.md) shouldn't kill the entire search — that one facility just contributes nothing.
- The CLI is one-shot; there's no retry loop. If the result is empty, the user re-runs.

The cost is that genuine bugs (bad URL construction, wrong header) look identical to "no results." When debugging, drop a `print(e)` into `_get`.

## SSL

Uses `certifi.where()` for the trust store, not the system default — avoids macOS python3 SSL flakiness on fresh installs. This is the only reason `certifi` is in [../requirements.txt](../requirements.txt).

## Gotchas

- The `start_date` query param must be ISO-8601 with `T00:00:00.000Z` and the day pinned to `01`. Other formats silently return empty.
- `User-Agent` is required on `recreation.gov/api/...` — without it you get a Cloudflare challenge page that decodes as garbage and trips the JSON parser.
- The `apikey` query param is RIDB-only. Passing it to `recreation.gov/api/...` is harmless but wastes a key.
