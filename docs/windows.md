# recon/windows.py

Pure date-math primitive. Given a set of available dates and a stay length N, return every viable (start, checkout) window of N consecutive nights.

[Source](../recon/windows.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def consecutive_nights(available: set[date], nights: int) -> list[tuple[date, date]]
```

- `available` — set of `date` objects, any prefiltering done by the caller.
- `nights` — desired stay length. `< 1` returns `[]`.
- Returns `(start, checkout)` tuples. `checkout` is `start + nights` — the morning the guest leaves, matching Rec.gov booking-UI semantics.

A run of length L produces `L - nights + 1` start positions. A 5-night run with `nights=2` yields 4 valid starts, not 1.

## Why a separate module

Two callers want this primitive in slightly different shapes:

- [parser.md](parser.md) (weekend mode) calls it per-site to populate `windows_by_site_id`, *and* on the flat union to set the `contiguous` flag on `CampsiteResult`.
- [search.md](search.md) (search mode) calls it on the merged facility-level date set for the `contiguous` flag.
- The Phase 3 auto-cart matcher (see [auto-cart-mvp-plan.md](auto-cart-mvp-plan.md)) will call it with arbitrary `nights` from `targets.json` rules.

Three callers, one primitive, no parser/search interdependency.

## How the algorithm works

1. Sort the input ordinals (`date.toordinal()`).
2. `groupby(ordinals, key=lambda x: x - next(counter))` — by subtracting a running counter, consecutive dates share a key while gaps shift it. Each group is one contiguous run.
3. For each run of length ≥ `nights`, enumerate every valid start: `range(len(run) - nights + 1)`.
4. Convert ordinals back to `date` objects; checkout is `last_night + 1`.

Algorithm credited to banool/recreation-gov-campsite-checker — see [banool-attribution.md](banool-attribution.md). The port operates on native `date` objects rather than ISO strings, with explicit empty-set and `nights<1` guards.

## What this module does NOT do

- **No date filtering.** The caller pre-filters to whichever window matters (Fri/Sat/Sun in weekend mode, the `--start..--end` range in search mode). This module only does run-detection.
- **No status filtering.** Availability statuses are normalized via `is_available()` in [models.md](models.md) before reaching this module.
- **No campsite-id awareness.** It operates on a flat `set[date]`. The caller decides whether to call once per site (preserving per-site granularity, what weekend mode does for `windows_by_site_id`) or once on a union (what search mode does for its single `contiguous` bool).

## Upstream / downstream

- **Called by**: [parser.md](parser.md), [search.md](search.md), and (future) the Phase 3 auto-cart matcher.
- **Calls**: nothing — pure stdlib (`datetime`, `itertools`).
- **Output consumed by**: `CampsiteResult.windows_by_site_id`, `CampsiteResult.contiguous`, `SearchResult.contiguous`.

## Examples

```python
from datetime import date
from recon.windows import consecutive_nights

avail = {date(2026,7,1), date(2026,7,2), date(2026,7,3),
         date(2026,7,8), date(2026,7,9)}

consecutive_nights(avail, nights=2)
# [(2026-07-01, 2026-07-03),   # nights of 7/1, 7/2 — checkout 7/3
#  (2026-07-02, 2026-07-04),   # nights of 7/2, 7/3 — checkout 7/4
#  (2026-07-08, 2026-07-10)]   # nights of 7/8, 7/9 — checkout 7/10

consecutive_nights(avail, nights=3)
# [(2026-07-01, 2026-07-04)]   # only the 7/1–7/3 run is long enough

consecutive_nights(avail, nights=4)
# []                            # no run is 4+ nights
```
