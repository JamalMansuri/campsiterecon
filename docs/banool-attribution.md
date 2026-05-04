# banool — prior-art attribution

> **TL;DR:** We do **not** depend on [banool/recreation-gov-campsite-checker](https://github.com/banool/recreation-gov-campsite-checker). We read its source, lifted one specific algorithm — `consecutive_nights` — and reimplemented it in our own module. This doc credits the project and documents exactly what we borrowed and why.

## What banool is

[banool/recreation-gov-campsite-checker](https://github.com/banool/recreation-gov-campsite-checker) (358+ stars, by [Daniel Porteous](https://github.com/banool)) is a Python availability checker for Recreation.gov. It pre-dates camply, has cleaner code at the algorithmic core, and is explicitly cross-referenced from the auto-cart MVP plan ([docs/auto-cart-mvp-plan.md](auto-cart-mvp-plan.md) §3.1) as the "cleanest code for the availability query."

We previously did not borrow from it because [camply](camply-attribution.md) covered the response shape and the unavailable-status denylist. But banool's `consecutive_nights` function does something neither camply nor our own code does well: it enumerates **every viable N-night start position** within a run of available dates, returning `(start_date, checkout_date)` tuples in the exact format Recreation.gov's booking UI consumes.

## Why we don't take it as a dependency

| | Take dep on banool's repo | Borrow the algorithm (what we did) |
|---|---|---|
| `pip install` | not packaged | n/a |
| Total LOC borrowed | ~600 LOC | ~25 LOC of one focused function |
| Survives the upstream repo being archived | no | yes — it's our code |
| Locked to upstream behavior | yes | no |

banool is single-file utility code, not a library. The right way to honor it is attribution + a clean port, not a vendor copy.

## What we borrowed (concretely)

### `consecutive_nights(available, nights)`

Banool's [`camping.py`](https://github.com/banool/recreation-gov-campsite-checker/blob/master/camping.py) defines a function that returns every viable N-night booking window from a set of available dates. The clever bit is the run-detection idiom:

```python
c = count()
runs = [list(g) for _, g in groupby(ordinal_dates, lambda x: x - next(c))]
```

By subtracting a running counter from each ordinal date, consecutive dates produce the **same key** (each side increases by 1 in lockstep) while gaps shift the key. `groupby` then splits at key changes — yielding the sorted list of contiguous runs in one pass. For each run of length ≥ N, the function enumerates every valid start window:

```python
for start_index in range(0, len(r) - nights + 1):
    start    = r[start_index]
    checkout = r[start_index + nights - 1] + 1   # +1 = checkout day
```

Our port lives at [`recon/windows.py`](../recon/windows.py) and operates on `set[date]` directly (no string round-tripping), with empty-set and `nights<1` guards. Same algorithm, native types.

### Why this is a better primitive than what we had

Before: two different one-shot helpers — `_is_contiguous(available, friday)` in [parser.py](../recon/parser.py) and `_has_contiguous(dates)` in [search.py](../recon/search.py). Both returned `bool`. Both were hardcoded to 2 nights. Neither told the caller *which* dates were the start of a viable stay.

After: a single `consecutive_nights(set[date], nights: int) -> list[tuple[date, date]]` powers both modes' `contiguous` flag and feeds [`CampsiteResult.windows_by_site_id`](../recon/models.py) — the per-site (start, checkout) listing the auto-cart booker needs to actually click a date range in the Rec.gov UI. The function generalizes to arbitrary `nights`, so when `targets.json` rules in Phase 3 specify `"nights": N`, the matcher can call this function directly with no further refactor.

## What we explicitly did *not* copy from banool

- **`requests` HTTP client.** We use stdlib `urllib` to keep the dep tree minimal.
- **`user_agent.generate_user_agent()` randomized UA.** Would actively *hurt* in the auto-cart context — Akamai treats UA flips on a held session as bot-like. We send a fixed `CampsiteRecon/1.0`.
- **Allowlist filter (`if availability_value != "Available"`).** banool has the bug our Phase 0 fixed by adopting camply's denylist — `"Open"` looks bookable but means walk-up-only at most parks. We use [`is_available()`](../recon/models.py).
- **`raise RuntimeError` on non-200.** Our [api_client.py](../recon/api_client.py) silently returns `None`; one bad request shouldn't kill a multi-facility scan.
- **Twitter `notifier.py` md5-hash + delay-file dedup.** Hacky. camply's set-diff dedup pattern (tracked as future work in [camply-attribution.md](camply-attribution.md)) is the better answer when Mode 3 starts spamming.
- **`dateutil.rrule` for month iteration.** Adds a dep to replace our 8-line `_months_spanned` in [search.py](../recon/search.py). Not worth it.

## Where banool is referenced in our code

| File | What was borrowed |
|---|---|
| [recon/windows.py](../recon/windows.py) | `consecutive_nights` algorithm — the `groupby(x - next(count()))` run-detection idiom and the (start, checkout) window enumeration |
| [recon/parser.py](../recon/parser.py) | Calls `consecutive_nights` for the `contiguous` flag and to populate `windows_by_site_id` per campsite |
| [recon/search.py](../recon/search.py) | Calls `consecutive_nights` for the facility-level `contiguous` flag |
| [recon/models.py](../recon/models.py) | New `CampsiteResult.windows_by_site_id` field surfaces banool-style windows in Mode 1 output |

## Kudos

Big thanks to [Daniel Porteous](https://github.com/banool) and contributors. The `groupby(x - next(c))` idiom is the kind of clean Python that's easy to admire and hard to rederive under time pressure. If you want a no-frills Rec.gov availability scanner with Twitter notifications, banool's repo still ships and works.

## License compatibility

banool is MIT-licensed. We have not vendored any source files. The algorithm itself is a standard run-length-encoding pattern adapted for date arithmetic — not a copyrightable artifact — but we credit the discovery anyway because seeing the idiom applied to this exact problem saved us the work.

## References

- [banool/recreation-gov-campsite-checker on GitHub](https://github.com/banool/recreation-gov-campsite-checker)
- banool source files we read while porting:
  - `camping.py` — `consecutive_nights`, `get_park_information`, `get_num_available_sites`
  - `clients/recreation_client.py` — for comparison with our [api_client.py](../recon/api_client.py)
  - `utils/camping_argparser.py` — for the `--nights`, `--weekends-only`, `--exclusion-file`, `--campsite-type` flag designs (deferred to Phase 3 of the auto-cart plan)
