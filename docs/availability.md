# recon/availability.py

Weekend-mode endpoint dispatcher. One function: pick which Rec.gov endpoint to ask, and tag the result so the parser knows which response shape to expect.

[Source](../recon/availability.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def fetch_camp_availability(client: RecGovClient, camp: Camp, friday: date) -> dict | None
```

Returns one of three things:

```python
{"type": "campground", "data": {...}}   # raw campground response
{"type": "permit",     "data": {...}}   # raw permit response
None                                    # both endpoints empty
```

## Logic

1. Try `campground_month()` first.
2. If it returns data with non-empty `campsites`, tag it `campground` and return.
3. Otherwise, if `camp.permit_id` is set, try `permit_month()` and tag it `permit`.
4. If both fail, return `None`.

## Why the fallback exists

Some camps (Point Reyes wilderness sites) historically only existed on the permit endpoint. In 2026 Rec.gov started populating them on the *campground* endpoint too — but the bookings still flow through `/permits/`. The fallback handles both worlds:

- If the campground endpoint returns nothing for a permit-system camp (old behavior), fall through to the permit endpoint.
- If it returns *something* (new behavior), use it — but the URL the user actually books at is still `/permits/{permit_id}`. That URL decision lives in [parser.md](parser.md), keyed off `camp.permit_id`, not the response type.

This split — "fetch via whichever endpoint works, but always book via the permit URL when there's a permit_id" — is the one piece of business logic that's non-obvious from reading individual files.

## Upstream / downstream

- **Called by**: [main.md](main.md) (`_run_location` loop, weekend mode only)
- **Calls**: [api_client.md](api_client.md) (`campground_month`, `permit_month`)
- **Output consumed by**: [parser.md](parser.md) — the `type` tag tells the parser whether to dispatch to `_parse_campground` or `_parse_permit`

## Not used by search mode

[search.md](search.md) only hits the campground endpoint directly. Permit-only facilities are invisible to search mode by design — for those, the user is routed back to a preset (per [SKILL.md](../SKILL.md) Mode 2 rules).
