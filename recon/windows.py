"""Consecutive-night window enumeration.

Given a set of available dates and a desired stay length N, return every
viable (start, checkout) pair where the campsite is open for N consecutive
nights. `start` is the first night booked; `checkout` is the morning the
guest leaves (start + N days) — the shape Recreation.gov's booking UI
expects as `start_date` / `end_date`.

Algorithm credited to Daniel Porteous (banool) and the contributors of
banool/recreation-gov-campsite-checker. See docs/banool-attribution.md
for what was borrowed and why we did not take a runtime dependency.
"""

from datetime import date
from itertools import count, groupby


def consecutive_nights(available: set[date], nights: int) -> list[tuple[date, date]]:
    """Return all (start, checkout) windows of `nights` consecutive nights.

    Empty result if `nights < 1`, `available` is empty, or no run is long
    enough. A run of length L produces `L - nights + 1` start positions —
    a 5-night run with `nights=2` gives 4 valid starts.
    """
    if nights < 1 or not available:
        return []

    ordinals = sorted(d.toordinal() for d in available)
    counter  = count()
    runs     = [list(g) for _, g in groupby(ordinals, key=lambda x: x - next(counter))]

    out: list[tuple[date, date]] = []
    for run in runs:
        if len(run) < nights:
            continue
        for i in range(len(run) - nights + 1):
            start    = date.fromordinal(run[i])
            checkout = date.fromordinal(run[i + nights - 1] + 1)
            out.append((start, checkout))
    return out
