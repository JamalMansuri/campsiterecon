from datetime import date

from recon.windows import consecutive_nights


def d(s: str) -> date:
    return date.fromisoformat(s)


def test_empty_and_bad_nights():
    assert consecutive_nights(set(), 2) == []
    assert consecutive_nights({d("2026-10-09")}, 0) == []


def test_single_run_enumerates_all_starts():
    avail = {d("2026-10-09"), d("2026-10-10"), d("2026-10-11")}
    assert consecutive_nights(avail, 2) == [
        (d("2026-10-09"), d("2026-10-11")),
        (d("2026-10-10"), d("2026-10-12")),
    ]
    assert consecutive_nights(avail, 3) == [(d("2026-10-09"), d("2026-10-12"))]
    assert consecutive_nights(avail, 4) == []


def test_gap_breaks_run():
    avail = {d("2026-10-09"), d("2026-10-11")}
    assert consecutive_nights(avail, 2) == []
    assert len(consecutive_nights(avail, 1)) == 2
