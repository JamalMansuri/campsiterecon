from datetime import date

from recon.availability import fetch_camp_availability
from recon.config import Camp


class FakeClient:
    def __init__(self, months, permits=None):
        self._months, self._permits = months, permits or {}
        self.calls = []

    def campground_month(self, fid, year, month):
        self.calls.append(("camp", fid, year, month))
        return self._months.get((fid, year, month))

    def permit_month(self, pid, year, month):
        self.calls.append(("permit", pid, year, month))
        return self._permits.get((pid, year, month))

    def campground_meta(self, fid):
        return {"facility_name": "X"}


def _month(**sites):
    return {"campsites": {sid: {"loop": "A", "site": sid, "availabilities": av} for sid, av in sites.items()}}


def test_weekend_straddling_month_boundary_fetches_both_months():
    oct = _month(s1={"2026-10-30T00:00:00Z": "Available", "2026-10-31T00:00:00Z": "Available"})
    nov = _month(s1={"2026-11-01T00:00:00Z": "Available"})
    client = FakeClient({("9", 2026, 10): oct, ("9", 2026, 11): nov})
    out = fetch_camp_availability(client, Camp("X", "9"), date(2026, 10, 30))
    assert out["type"] == "campground"
    assert out["missing_months"] == []
    assert set(out["data"]["campsites"]["s1"]["availabilities"]) == {
        "2026-10-30T00:00:00Z", "2026-10-31T00:00:00Z", "2026-11-01T00:00:00Z"}
    assert [c[2:] for c in client.calls] == [(2026, 10), (2026, 11)]


def test_missing_second_month_is_reported_not_silently_dropped():
    oct = _month(s1={"2026-10-30T00:00:00Z": "Available"})
    client = FakeClient({("9", 2026, 10): oct})            # November fetch returns None
    out = fetch_camp_availability(client, Camp("X", "9"), date(2026, 10, 30))
    assert out["missing_months"] == ["2026-11"]


def test_mid_month_weekend_fetches_one_month():
    client = FakeClient({("9", 2026, 10): _month(s1={})})
    out = fetch_camp_availability(client, Camp("X", "9"), date(2026, 10, 9))
    assert out and [c[2:] for c in client.calls] == [(2026, 10)]


def test_permit_fallback_merges_divisions_across_months():
    p_oct = {"payload": {"availability": {"d1": {"division_id": "d1", "date_availability": {
        "2026-10-31T00:00:00Z": {"remaining": 1, "total": 1}}}}}}
    p_nov = {"payload": {"availability": {"d1": {"division_id": "d1", "date_availability": {
        "2026-11-01T00:00:00Z": {"remaining": 2, "total": 2}}}}}}
    client = FakeClient({}, permits={("p", 2026, 10): p_oct, ("p", 2026, 11): p_nov})
    out = fetch_camp_availability(client, Camp("X", "9", permit_id="p"), date(2026, 10, 30))
    assert out["type"] == "permit"
    assert set(out["data"]["payload"]["availability"]["d1"]["date_availability"]) == {
        "2026-10-31T00:00:00Z", "2026-11-01T00:00:00Z"}


def test_nothing_at_all_returns_none():
    client = FakeClient({})
    assert fetch_camp_availability(client, Camp("X", "9"), date(2026, 10, 9)) is None


def test_answered_but_empty_month_is_reported_not_unreachable():
    client = FakeClient({("9", 2026, 10): {"campsites": {}}})
    out = fetch_camp_availability(client, Camp("X", "9"), date(2026, 10, 9))
    assert out is not None and out["type"] == "campground"
    assert out["empty_months"] == ["2026-10"] and out["data"]["campsites"] == {}


def test_null_site_in_merge_is_ignored():
    oct = {"campsites": {"s1": {"availabilities": {"2026-10-31T00:00:00Z": "Available"}}, "junk": None}}
    nov = {"campsites": {"s1": {"availabilities": {"2026-11-01T00:00:00Z": "Available"}}}}
    client = FakeClient({("9", 2026, 10): oct, ("9", 2026, 11): nov})
    out = fetch_camp_availability(client, Camp("X", "9"), date(2026, 10, 30))
    assert set(out["data"]["campsites"]) == {"s1"}
