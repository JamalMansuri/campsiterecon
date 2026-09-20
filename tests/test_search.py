from datetime import date

from recon.search import _date_range, _months_spanned, search


class FakeClient:
    """Stands in for RecGovClient. `months` maps facility_id -> raw month payload (or None)."""

    def __init__(self, facilities, total, months, recareas=None):
        self._facilities = facilities
        self._total = total
        self._months = months
        self._recareas = recareas or {}
        self.month_calls = []
        self.last_error = None
        self.rate_limited = False

    def ridb_search_recarea(self, query):
        return None

    def ridb_search_campgrounds(self, query, max_results=150):
        return self._facilities, self._total

    def campground_month(self, facility_id, year, month):
        self.month_calls.append((facility_id, year, month))
        return self._months.get(facility_id)

    def ridb_recarea_name(self, rec_area_id):
        return self._recareas.get(str(rec_area_id))


def _fac(fid, name, parent="2991"):
    return {"FacilityID": fid, "FacilityName": name, "FacilityTypeDescription": "Campground",
            "Reservable": True, "Enabled": True, "ParentRecAreaID": parent,
            "FacilityLatitude": 37.7, "FacilityLongitude": -119.5}


def test_months_spanned_and_date_range():
    assert _months_spanned(date(2026, 12, 30), date(2027, 1, 2)) == [(2026, 12), (2027, 1)]
    assert _months_spanned(date(2026, 7, 4), date(2026, 7, 4)) == [(2026, 7)]
    assert _date_range(date(2026, 7, 4), date(2026, 7, 4)) == {date(2026, 7, 4)}


def test_search_reports_sites_names_and_totals(point_reyes_month):
    client = FakeClient(
        facilities=[_fac("233359", "Point Reyes National Seashore Campground", parent="2864"),
                    _fac("232447", "UPPER PINES CAMPGROUND")],
        total=2,
        months={"233359": point_reyes_month, "232447": None},
        recareas={"2864": "Point Reyes National Seashore", "2991": "Yosemite National Park"},
    )
    report = search(client, "Point Reyes", date(2026, 10, 9), date(2026, 10, 11))
    assert report.facilities_total == 2
    assert report.facilities_scanned == 2
    assert report.unreachable == ["Upper Pines Campground"]
    assert len(report.results) == 1
    r = report.results[0]
    assert r.facility_id == "233359"
    assert r.official_name == "Point Reyes National Seashore Campground"
    assert r.rec_area == "Point Reyes National Seashore"
    assert r.reservation_url == "https://www.recreation.gov/camping/campgrounds/233359"
    assert r.available_dates == ["2026-10-09", "2026-10-10", "2026-10-11"]
    assert r.contiguous is True
    assert r.open_site_count >= 2
    assert r.sample_sites and all(s.url.startswith("https://www.recreation.gov/camping/campsites/") for s in r.sample_sites)
    assert all(s.loop for s in r.sample_sites)


def test_screaming_caps_names_are_title_cased_but_mixed_case_is_kept():
    client = FakeClient(
        facilities=[_fac("1", "LOST CLAIM"), _fac("2", "McCabe Flat Campground")],
        total=2, months={"1": {"campsites": {"a": {"availabilities": {"2026-10-09T00:00:00Z": "Available"}}}},
                         "2": {"campsites": {"b": {"availabilities": {"2026-10-09T00:00:00Z": "Available"}}}}},
    )
    report = search(client, "x", date(2026, 10, 9), date(2026, 10, 9))
    names = {r.facility_id: r.name for r in report.results}
    assert names == {"1": "Lost Claim", "2": "McCabe Flat Campground"}


def test_one_month_call_per_facility_per_month():
    raw = {"campsites": {"a": {"availabilities": {"2026-10-31T00:00:00Z": "Available",
                                                  "2026-11-01T00:00:00Z": "Available"}}}}
    client = FakeClient(facilities=[_fac("9", "X")], total=1, months={"9": raw})
    report = search(client, "x", date(2026, 10, 31), date(2026, 11, 1))
    assert sorted(client.month_calls) == [("9", 2026, 10), ("9", 2026, 11)]
    assert report.results[0].contiguous is True


class AnchoredClient(FakeClient):
    def __init__(self, *args, anchor=None, ridb_error=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._anchor = anchor
        self.last_error = ridb_error
        self.rate_limited = False

    def ridb_search_recarea(self, query):
        return self._anchor


def _open(day):
    return {"campsites": {"a": {"loop": "L", "site": "1", "campsite_type": "STANDARD NONELECTRIC",
                                "availabilities": {f"2026-10-{day:02d}T00:00:00Z": "Available"}}}}


def test_far_keyword_matches_are_skipped_and_results_sorted_by_distance():
    near = dict(_fac("1", "Near Camp"), FacilityLatitude=37.75, FacilityLongitude=-119.6)
    nearer = dict(_fac("2", "Nearer Camp"), FacilityLatitude=37.85, FacilityLongitude=-119.56)
    far = dict(_fac("3", "Camp 4 Group Campground (Shasta)"), FacilityLatitude=41.2, FacilityLongitude=-122.3)
    nocoords = dict(_fac("4", "Mystery"), FacilityLatitude=0, FacilityLongitude=0)
    client = AnchoredClient([near, nearer, far, nocoords], 4,
                            months={"1": _open(9), "2": _open(9), "3": _open(9), "4": _open(9)},
                            anchor={"id": "2991", "name": "Yosemite National Park", "lat": 37.848833, "lon": -119.557187})
    report = search(client, "Yosemite", date(2026, 10, 9), date(2026, 10, 9))
    assert report.anchor == "Yosemite National Park"
    assert report.skipped_far == ["Camp 4 Group Campground (Shasta)"]
    assert report.facilities_scanned == 3
    assert ("3", 2026, 10) not in client.month_calls          # far facility never fetched
    assert [r.facility_id for r in report.results] == ["2", "1", "4"]   # by distance, coordless last
    assert report.results[0].distance_km < report.results[1].distance_km
    assert report.results[2].distance_km is None


def test_no_anchor_means_no_distance_filtering():
    far = dict(_fac("3", "Far"), FacilityLatitude=41.2, FacilityLongitude=-122.3)
    client = AnchoredClient([far], 1, months={"3": _open(9)}, anchor=None)
    report = search(client, "Big Sur", date(2026, 10, 9), date(2026, 10, 9))
    assert report.anchor is None and report.skipped_far == [] and len(report.results) == 1


def test_partial_month_is_reported():
    client = AnchoredClient([_fac("9", "X")], 1, months={"9": _open(31)})   # only October answers
    # FakeClient returns the same payload for every month; make November fail explicitly
    client._months = {"9": _open(31)}
    orig = client.campground_month
    client.campground_month = lambda fid, y, m: orig(fid, y, m) if m == 10 else None
    report = search(client, "x", date(2026, 10, 31), date(2026, 11, 1))
    assert report.partial == ["X (2026-11 not checked)"]
    assert report.unreachable == []
    assert report.results[0].available_dates == ["2026-10-31"]


def test_ridb_failure_is_a_warning_not_an_empty_success():
    client = AnchoredClient([], 0, months={}, ridb_error=403)
    report = search(client, "x", date(2026, 10, 9), date(2026, 10, 9))
    assert report.results == []
    assert any("RIDB" in w and "403" in w for w in report.warnings)


def test_contiguous_is_per_site_in_search_too():
    raw = {"campsites": {
        "a": {"loop": "L", "site": "A", "availabilities": {"2026-10-09T00:00:00Z": "Available", "2026-10-10T00:00:00Z": "Reserved"}},
        "b": {"loop": "L", "site": "B", "availabilities": {"2026-10-09T00:00:00Z": "Reserved", "2026-10-10T00:00:00Z": "Available"}},
    }}
    client = AnchoredClient([_fac("9", "X")], 1, months={"9": raw})
    report = search(client, "x", date(2026, 10, 9), date(2026, 10, 10))
    assert report.results[0].available_dates == ["2026-10-09", "2026-10-10"]
    assert report.results[0].contiguous is False
    assert report.results[0].sample_sites[0].campsite_type is None


def test_contiguous_site_leads_sample_sites():
    raw = {"campsites": {}}
    # 6 sites with 1 open night each, then one site "z" with two consecutive nights
    for i in range(6):
        raw["campsites"][f"s{i}"] = {"loop": "L", "site": str(i), "availabilities": {"2026-10-09T00:00:00Z": "Available"}}
    raw["campsites"]["z"] = {"loop": "L", "site": "Z", "availabilities": {"2026-10-10T00:00:00Z": "Available",
                                                                            "2026-10-11T00:00:00Z": "Available"}}
    client = AnchoredClient([_fac("9", "X")], 1, months={"9": raw})
    report = search(client, "x", date(2026, 10, 9), date(2026, 10, 11))
    r = report.results[0]
    assert r.contiguous is True
    assert r.sample_sites[0].campsite_id == "z" and len(r.sample_sites) == 5


def test_rate_limit_warning_names_the_time():
    from datetime import datetime, timezone
    from recon.search import rate_limit_warning

    class C:
        rate_limited = True
        rate_limited_until = datetime(2026, 9, 20, 11, 0, tzinfo=timezone.utc)
    (w,) = rate_limit_warning(C(), 3)
    assert "3 facilities" in w and "until about" in w and "extends the block" in w
    C.rate_limited = False
    assert rate_limit_warning(C(), 3) == []


def test_ridb_truncation_and_skipped_sites_are_warned():
    raw = {"campsites": {"a": {"availabilities": {"2026-10-09T00:00:00Z": "Available"}}, "junk": None}}
    client = AnchoredClient([_fac("9", "X")], 40, months={"9": raw})
    client.ridb_pages_failed = 1
    report = search(client, "x", date(2026, 10, 9), date(2026, 10, 9))
    assert any("RIDB stopped answering after 1 of 40" in w for w in report.warnings)
    assert any("unrecognised shape" in w for w in report.warnings)
    assert report.results[0].skipped_sites == 1


def _site(kind, label, *days):
    return {"loop": "L", "site": label, "campsite_type": kind,
            "availabilities": {f"2026-10-{d:02d}T00:00:00Z": "Available" for d in days}}


def _mixed():
    return {"campsites": {
        "std":   _site("HIKE TO", "003", 9),                                    # one night only
        "grp":   _site("GROUP HIKE TO", "008 GROUP", 9, 10, 11),                # the only 2-night window is a group site
        "boat":  _site("BOAT IN", "BOAT A, 1-6 people", 9, 10),
        "beach": _site("GROUP TENT ONLY AREA NONELECTRIC", "TOMALES BEACH GROUP, BOAT ONLY", 10),
    }}


def test_group_and_boat_sites_are_skipped_by_default():
    client = AnchoredClient([_fac("9", "Point Reyes National Seashore Campground")], 1, months={"9": _mixed()})
    report = search(client, "x", date(2026, 10, 9), date(2026, 10, 11))
    assert report.site_types == "standard"
    r = report.results[0]
    assert r.open_site_count == 1 and [s.campsite_id for s in r.sample_sites] == ["std"]
    assert r.available_dates == ["2026-10-09"]                   # group/boat nights are not counted
    assert r.contiguous is False                                 # the 2-night window was a group site
    assert r.excluded_open_sites == {"boat_in": 2, "group": 1}   # ...but nothing vanished silently (the boat-only group beach is boat_in)
    assert r.special_open_sites == {} and all(x.category is None for x in r.sample_sites)
    assert report.group_or_boat_only == []


def test_all_site_types_flag_brings_them_back():
    client = AnchoredClient([_fac("9", "X")], 1, months={"9": _mixed()})
    report = search(client, "x", date(2026, 10, 9), date(2026, 10, 11), include_all_site_types=True)
    r = report.results[0]
    assert report.site_types == "all"
    assert r.open_site_count == 4 and r.contiguous is True and r.excluded_open_sites == {}
    assert r.available_dates == ["2026-10-09", "2026-10-10", "2026-10-11"]
    assert r.sample_sites[0].campsite_id == "grp"


def test_facility_open_only_at_group_or_boat_sites_is_listed_not_returned():
    only = {"campsites": {"g": _site("GROUP STANDARD NONELECTRIC", "G1", 9, 10), "b": _site("BOAT IN", "B1", 9)}}
    client = AnchoredClient([_fac("1", "PINES GROUP STANISLAUS"), _fac("2", "Normal Camp")], 2,
                            months={"1": only, "2": {"campsites": {"s": _site("STANDARD NONELECTRIC", "001", 9)}}})
    report = search(client, "x", date(2026, 10, 9), date(2026, 10, 10))
    assert [r.facility_id for r in report.results] == ["2"]      # so the Mode 3 jq gate can't fire on group-only openings
    assert report.group_or_boat_only == ["Pines Group Stanislaus (1 boat-in + 1 group sites only)"]
    assert report.unreachable == []


def test_all_mode_names_the_special_sites_without_displacing_the_window_site():
    raw = {"campsites": {f"s{i}": _site("STANDARD NONELECTRIC", f"{i:03d}", 9, 10, 11) for i in range(6)}}
    raw["campsites"]["grp"] = _site("GROUP STANDARD NONELECTRIC", "G1", 10)          # 1 night: ranks last
    raw["campsites"]["boat"] = _site("BOAT IN", "BOAT A", 10)
    client = AnchoredClient([_fac("9", "X")], 1, months={"9": raw})
    r = search(client, "x", date(2026, 10, 9), date(2026, 10, 11), include_all_site_types=True).results[0]
    assert r.open_site_count == 8 and r.excluded_open_sites == {}
    assert r.special_open_sites == {"boat_in": 1, "group": 1}
    assert len(r.sample_sites) == 5
    assert r.sample_sites[0].campsite_id == "s0" and r.sample_sites[0].category is None   # still the 2-night site to link
    assert {x.category for x in r.sample_sites} == {None, "group", "boat_in"}             # each category is visible
    # ...and the default run of the same facility never shows them
    d = search(client, "x", date(2026, 10, 9), date(2026, 10, 11)).results[0]
    assert d.open_site_count == 6 and d.excluded_open_sites == {"boat_in": 1, "group": 1}
    assert all(x.category is None for x in d.sample_sites)


def test_group_only_facility_with_a_missing_month_is_partial_and_listed():
    only = {"campsites": {"g": _m("GROUP HIKE TO", "008 GROUP", "2026-10-31")}}
    client = AnchoredClient([_fac("9", "X")], 1, months={})
    client.campground_month = lambda fid, y, m: only if m == 10 else None
    report = search(client, "x", date(2026, 10, 31), date(2026, 11, 1))
    assert report.results == []                                   # the cron gate stays shut
    assert report.partial == ["X (2026-11 not checked)"]          # both statements are true, both are reported
    assert report.group_or_boat_only == ["X (1 group site only)"] # singular wording
    assert report.unreachable == []


def _m(kind, label, iso, status="Available"):
    return {"loop": "L", "site": label, "campsite_type": kind, "availabilities": {f"{iso}T00:00:00Z": status}}


def test_excluded_counts_are_per_site_across_months_and_only_open_sites():
    october = {"campsites": {"grp": _m("GROUP STANDARD NONELECTRIC", "G1", "2026-10-31"),
                             "full": _m("GROUP STANDARD NONELECTRIC", "G2", "2026-10-31", "Reserved"),
                             "std": _m("STANDARD NONELECTRIC", "001", "2026-10-31")}}
    november = {"campsites": {"grp": _m("GROUP STANDARD NONELECTRIC", "G1", "2026-11-01"),
                              "std": _m("STANDARD NONELECTRIC", "001", "2026-11-01")}}
    client = AnchoredClient([_fac("9", "X")], 1, months={})
    client.campground_month = lambda fid, y, m: october if m == 10 else november
    r = search(client, "x", date(2026, 10, 31), date(2026, 11, 1)).results[0]
    assert r.excluded_open_sites == {"group": 1}                  # one site open in two months is ONE site; Reserved ones don't count
    assert r.open_site_count == 1 and r.contiguous is True


def test_mixed_case_and_padded_types_are_filtered_through_the_full_path():
    raw = {"campsites": {"a": _site("  group   hike to ", "G", 9), "b": _site("Boat In", "B", 9), "c": _site(" mooring ", "M", 9),
                         "d": _site("Standard Nonelectric", "001", 9)}}
    client = AnchoredClient([_fac("9", "X")], 1, months={"9": raw})
    r = search(client, "x", date(2026, 10, 9), date(2026, 10, 9)).results[0]
    assert [x.campsite_id for x in r.sample_sites] == ["d"]
    assert r.excluded_open_sites == {"boat_in": 2, "group": 1}
