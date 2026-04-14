# recon/parser.py

Weekend-mode response normalizer. Turns raw Rec.gov JSON into a flat `CampsiteResult` for one camp + one weekend. Search mode has its own equivalent inline in [search.md](search.md).

[Source](../recon/parser.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def parse(response: dict, camp: Camp, friday: date) -> CampsiteResult
```

`response` is the tagged dict from [availability.md](availability.md). `parse` dispatches on `response["type"]` to one of two private parsers.

## The two response shapes

Rec.gov returns campground availability and permit availability in completely different JSON shapes. The parser handles both:

| Endpoint | Path through JSON | Open value |
|---|---|---|
| Campground | `campsites[*].availabilities[date]` | `"Available"` or `"Open"` |
| Permit | `payload.availability[date].remaining` | integer `> 0` |

The output `CampsiteResult` is identical for both.

## The permit URL gotcha

`_reservation_url(camp)` decides the booking URL based on `camp.permit_id`, **not** the response type:

```python
if camp.permit_id:
    return f".../permits/{camp.permit_id}"
return f".../camping/campgrounds/{camp.facility_id}"
```

This matters because Rec.gov sometimes serves Point Reyes data through the campground endpoint now (see [availability.md](availability.md)). If we keyed the URL off the response type, those camps would get a `/camping/` URL — which would 404 the user. By keying off `permit_id`, the URL stays correct regardless of which endpoint the data came from.

This is the one rule a future LLM is most likely to break when refactoring. Don't.

## Contiguous detection

`_is_contiguous(available, friday)` returns `True` if the camp has at least 2 consecutive nights of the weekend open — Fri+Sat **or** Sat+Sun. Sat+Sun counts because most weekenders care about getting two nights, not which two.

Search mode has a looser definition (any two consecutive days in the date range, not just weekend pairs). See [search.md](search.md).

## Upstream / downstream

- **Called by**: [main.md](main.md) (`_run_location`)
- **Input from**: [availability.md](availability.md)
- **Outputs**: `CampsiteResult` from [models.md](models.md), wrapped into a `LocationReport` by main.py

## Filtering rules

Dates outside the Fri/Sat/Sun window are dropped silently. A camp with zero open dates still produces a `CampsiteResult` (with empty `available_dates` and `contiguous=False`) — main.py decides whether to mark the location as available based on `any(s.available_dates ...)`.
