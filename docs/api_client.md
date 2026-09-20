# recon/api_client.py

The only module in the program that talks HTTP. Wraps Recreation.gov and RIDB behind a single class. Knows nothing about campsites, dates, or business logic — that's all in callers.

[Source](../recon/api_client.py) · Wiki home: [README.md](README.md)

## Public surface

```python
class RecGovClient:
    def __init__(self, api_key: str | None, debug: bool | None = None, cooldown_file=~/.campsitescout/rate_limit.json)
    rate_limited: bool                      # True after a 429 this run, or while a recent run's cooldown is active
    rate_limited_until: datetime | None
    errors: dict[str, str]                  # redacted url -> "HTTP 404" / "TimeoutError: ..." for every failed fetch
    def error_for(facility_or_permit_id) -> str | None
    def campground_month(facility_id, year, month) -> dict | None
    def permit_month(permit_id, year, month) -> dict | None
    def campground_meta(facility_id) -> dict | None            # /api/camps/campgrounds/{id}
    def ridb_facility(facility_id) -> dict | None              # RIDB /facilities/{id}
    def ridb_recarea_name(rec_area_id) -> str | None           # RIDB /recareas/{id}
    def ridb_search_campgrounds(query, max_results=150) -> tuple[list[dict], int]
```

Every method returns `None` / `[]` on any HTTPError, URLError, or JSON decode failure. Callers must handle empty results, never network errors — but they must *report* them (`unreachable[]`, `warnings[]`).

## Endpoints

| Method | Host | Auth | Used by |
|---|---|---|---|
| `campground_month` | `recreation.gov/api/camps/availability/campground/{id}/month` | User-Agent only | [availability.md](availability.md), [search.md](search.md), [verify.md](verify.md) |
| `permit_month` | `recreation.gov/api/permits/{id}/availability/month` | User-Agent only | [availability.md](availability.md) |
| `campground_meta` | `recreation.gov/api/camps/campgrounds/{id}` | User-Agent only | availability + search (official names, `facility_rules` → `stay_rules`), verify |
| `ridb_facility`, `ridb_recarea_name`, `ridb_search_campgrounds` | `ridb.recreation.gov/api/v1/...` | `apikey` query param | search, verify |

## Caching

Responses are memoised per client instance by URL. Point Reyes' four loop presets fetch one month once; search mode's rec-area lookups cost one request per distinct rec area; `--verify` doesn't refetch what the run already has. A rate-limited skip is *not* cached so the next run retries.

## Rate limiting (HTTP 429)

Rec.gov's availability endpoints answer `429` from CloudFront (empty body, no `Retry-After`) when polled in a burst. Measured 2026-09-20: the block is **per-IP**, lasts about six minutes of complete silence, and every request made while blocked restarts the clock — so retrying is always wrong. The client:

1. paces availability requests (`_PACE_SECONDS = 0.6`);
2. on the **first** 429 sets `rate_limited = True`, returns `None` for every further availability request this run without touching the network, and writes `{"blocked_until": <now+10 min>}` to `~/.campsitescout/rate_limit.json`;
3. a later client (next cron tick, the LLM "trying again") reads that file at construction and starts already `rate_limited` until the timestamp passes.

Metadata and RIDB calls are unaffected by the breaker. Callers turn `rate_limited` / `rate_limited_until` into a `warnings[]` line via `search.rate_limit_warning()`, which names the time before which retrying is pointless.

## Failure visibility

`_fetch` catches `HTTPError`, `OSError` (URLError, timeouts, resets), `http.client.HTTPException` (truncated bodies) and `ValueError` (bad JSON / bad UTF-8) — a read-phase timeout used to escape and kill the whole run — and rejects non-object JSON bodies. Site-level validation in [parser.md](parser.md) (`validate_campground`) skips and counts malformed campsite records instead of raising. The cooldown file is read inside a try (a naive timestamp is treated as UTC; anything unreadable means no cooldown) and its directory is created `0700`. Every failure is recorded in `errors` and `error_for(id)` lets callers say *why* a facility is unreachable (`HTTP 404` → the id is wrong; `HTTP 400` → date out of range). `debug=True` (or `--debug`, or `CAMPSITESCOUT_DEBUG=1`) also prints them to stderr as `[api_client] HTTP 429 <url-without-key>`.

## Pagination + filtering in `ridb_search_campgrounds`

RIDB pages at 50 and `facilitytype=Campground` is only a hint (Permit / Timed Entry / Visitor Center records still come back). The method walks `offset` until `METADATA.RESULTS.TOTAL_COUNT` (capped at `max_results`), keeping only `FacilityTypeDescription == "Campground"` and `Reservable` and `Enabled`. Returns `(records, total_count)`.

## Gotchas

- `start_date` must be ISO-8601 with `T00%3A00%3A00.000Z` (colons encoded) and the day pinned to `01`.
- `User-Agent` is required on `recreation.gov/api/...`; a `python-requests/*` UA gets a CloudFront 403 HTML page. Ours is `CampsiteRecon/1.0` — don't rotate it (invariant 7), and it wouldn't help with 429 anyway (the block is IP-keyed).
- RIDB `/facilities/{id}` for an unknown id returns 200 with every field empty; `ridb_facility` normalises that to `None`.
- Uses `certifi.where()` for the trust store, the only reason `certifi` is in [../requirements.txt](../requirements.txt).
