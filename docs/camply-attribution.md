# camply — prior-art attribution

> **TL;DR:** We do **not** depend on [camply](https://github.com/juftin/camply). We read its source to learn the Rec.gov data contract and the unavailable-status denylist, then wrote our own minimal version. This doc credits the project and documents exactly what we borrowed and why.

## What camply is

[juftin/camply](https://github.com/juftin/camply) (584+ stars, MIT-licensed, by [Justin Flannery](https://github.com/juftin)) is a Python framework for searching and notifying on campsite availability across Recreation.gov, ReserveCalifornia, Yellowstone, GoingToCamp, and a few other providers. It's the gold-standard open-source reference for how the undocumented `www.recreation.gov/api/*` endpoints actually behave.

## Why we don't take it as a dependency

| | Take dep on `camply` | Borrow patterns (what we did) |
|---|---|---|
| `pip install camply` | yes | no |
| Pulls in pandas, click, fastapi, multi-provider stack | yes (~30k LOC) | no |
| Survives camply being abandoned | no | yes — it's our code |
| Locked to camply's release cadence | yes | no |
| Total LOC borrowed | ~30k LOC dep | ~30 LOC of typed shapes + one frozenset |

The patterns we borrowed are **research output** (knowledge of an undocumented API), not a library. The right way to honor that is attribution in this doc, not a dependency.

## What we borrowed (concretely)

### 1. The `CampsiteAvailabilityResponse` Pydantic shape

Camply's [`containers/api_responses.py`](https://github.com/juftin/camply/blob/main/camply/containers/api_responses.py) shows that the `/api/camps/availability/campground/{id}/month` response is structured as `Dict[campsite_id, _PerSiteResponse]` — keyed by campsite id, with per-date statuses inside.

Our [recon/models.py](../recon/models.py) mirrors this with two minimal models:
- `RawCampgroundResponse` — top-level wrapper.
- `RawSiteAvailability` — per-site detail (`availabilities`, `loop`, `site`, `campsite_type`).

Both use `model_config = ConfigDict(extra="ignore")` so Rec.gov adding a field doesn't break us. We don't copy any of camply's other 30+ container models — only the two that describe the response we actually parse.

### 2. The `CAMPSITE_UNAVAILABLE_STRINGS` denylist

Before borrowing this, our parser used an *allowlist* of `{"Available", "Open"}`. That had two bugs:
- **`"Open"` is not bookable** — it means the campground is open for the season but the *site* is walk-up only. Treating it as available caused false-positive "openings" in the scout output.
- **Missing statuses** like `"Lottery"` and `"NYR"` (not yet released) got silently treated as available.

Camply's [`config/api_config.py`](https://github.com/juftin/camply/blob/main/camply/config/api_config.py) maintains the canonical denylist. We copied it verbatim into [`recon/models.py`](../recon/models.py) as `_REC_GOV_UNAVAILABLE_STATUSES`, exposed via `is_available(status: str) -> bool`:

```python
_REC_GOV_UNAVAILABLE_STATUSES = frozenset({
    "Reserved", "Not Available", "Not Reservable",
    "Not Reservable Management", "Not Available Cutoff",
    "Lottery", "Open", "NYR", "Closed",
})
```

The original list took camply's maintainers and contributors years to compile by being burned in production. We get to skip that.

### 3. (Future) Set-diff dedup

Not yet implemented. Camply's polling loop computes `new = found.difference(self.campsites_found)` each tick and only notifies on the diff, with optional disk persistence. When watch mode (Mode 3) starts spamming Telegram on the same opening across cron ticks, this is the pattern to copy. Tracked as future work — not part of Phase 0.

## What we explicitly did *not* copy

- **Multi-provider abstraction.** Campsitescout targets only Rec.gov (every major US national park books through it). If we ever add ReserveCalifornia, that's the time to revisit.
- **Pandas-based date consolidation** (`_consolidate_campsites`, `_filter_date_overlap`). Plain Python `groupby` + `sorted(dates)` is enough at our scale.
- **YAML search config / CLI / notification framework.** Mode 3 already does this with shell + jq + Telegram.
- **Camply's RIDB resolver.** We have our own thin one in [recon/api_client.py](../recon/api_client.py) and we don't need camply's auto-search-every-collision behavior — auto-cart needs *one* facility id.

## Where camply is referenced in our code

| File | What was borrowed |
|---|---|
| [recon/models.py](../recon/models.py) | `RawCampgroundResponse` + `RawSiteAvailability` shapes; `_REC_GOV_UNAVAILABLE_STATUSES` denylist; `is_available()` helper |
| [recon/parser.py](../recon/parser.py) | Per-`campsite_id` iteration pattern (fixes the bug where we previously discarded the key) |
| [recon/search.py](../recon/search.py) | Same denylist via `is_available()` |
| [docs/auto-cart-mvp-plan.md](auto-cart-mvp-plan.md) | Architectural cross-references in §3.1 |

## Kudos

Big thanks to [Justin Flannery](https://github.com/juftin) and the camply contributors. If you do anything more than read-only Rec.gov scanning, go give them a star and consider using camply directly — it's a polished, well-maintained project. We borrowed selectively because our shape (single-purpose Mac mini scout + auto-cart) is narrower than what camply solves for, but for general-purpose campsite searching across multiple providers, camply is the right answer.

## License compatibility

camply is MIT-licensed. We have not vendored any of its source files. The denylist constant and the response-shape pattern are facts about Recreation.gov's API, not copyrightable artifacts of camply, but we credit the discovery anyway because the work of reverse-engineering them was real.

## References

- [camply on GitHub](https://github.com/juftin/camply)
- [camply documentation](https://juftin.com/camply/)
- camply source files we read while building Phase 0:
  - `camply/providers/recreation_dot_gov/recdotgov_provider.py`
  - `camply/providers/recreation_dot_gov/recdotgov_camps.py`
  - `camply/containers/api_responses.py`
  - `camply/containers/data_containers.py`
  - `camply/config/api_config.py`
  - `camply/search/base_search.py`
