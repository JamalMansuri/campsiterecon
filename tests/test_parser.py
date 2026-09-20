from datetime import date

from recon.config import Camp
from recon.parser import parse, permit_open_dates, site_url

FRIDAY = date(2026, 10, 9)


def _campground(raw, camp, meta=None):
    return parse({"type": "campground", "data": raw, "meta": meta}, camp, FRIDAY)


def test_loop_filter_restricts_to_one_camp(point_reyes_month):
    sky = _campground(point_reyes_month, Camp("Sky Camp", "233359", loop="Sky"))
    # fixture forces Sky site 1: Reserved/Avail/Avail/Avail/Reserved on Oct 8..12,
    # Sky site 2: Reserved/Reserved/Avail/Reserved/NYR
    assert sky.loop == "Sky"
    assert sky.available_dates == ["2026-10-09", "2026-10-10", "2026-10-11"]
    assert set(sky.sites_by_id) == {sid for sid, s in point_reyes_month["campsites"].items() if s["loop"] == "Sky"}
    assert sky.contiguous is True
    assert sky.permit_required is False
    assert sky.reservation_url == "https://www.recreation.gov/camping/campgrounds/233359"
    for sid, detail in sky.site_details.items():
        assert detail.loop == "Sky"
        assert detail.url == site_url(sid)
        assert detail.site
        assert detail.max_people and detail.campsite_type


def test_loop_filter_is_case_insensitive_and_open_is_not_bookable(point_reyes_month):
    coast = _campground(point_reyes_month, Camp("Coast Camp", "233359", loop="coast"))
    # Coast sites in the fixture are Open/Open/Reserved/Reserved/Closed and all-Reserved
    assert coast.available_dates == []
    assert coast.sites_by_id == {}
    assert coast.contiguous is False
    assert coast.loop_matched is True                       # "coast" matched "Coast" sites (none open)
    # Sky has openings: lower-case filter must find the same sites as the exact one
    lower = _campground(point_reyes_month, Camp("Sky Camp", "233359", loop="  sky "))
    exact = _campground(point_reyes_month, Camp("Sky Camp", "233359", loop="Sky"))
    assert lower.sites_by_id == exact.sites_by_id and lower.sites_by_id


def test_no_loop_aggregates_whole_facility(point_reyes_month):
    whole = _campground(point_reyes_month, Camp("Point Reyes", "233359"))
    assert whole.loop is None
    assert "2026-10-10" in whole.available_dates
    assert len(whole.sites_by_id) >= 2


def test_windows_by_site_only_for_two_night_runs(point_reyes_month):
    sky = _campground(point_reyes_month, Camp("Sky Camp", "233359", loop="Sky"))
    three_night_site = [sid for sid, dates in sky.sites_by_id.items() if len(dates) == 3][0]
    assert sky.windows_by_site_id[three_night_site] == [
        ("2026-10-09", "2026-10-11"),
        ("2026-10-10", "2026-10-12"),
    ]
    single_night_site = [sid for sid, dates in sky.sites_by_id.items() if len(dates) == 1][0]
    assert single_night_site not in sky.windows_by_site_id


def test_official_name_comes_from_meta(point_reyes_month, campground_meta):
    r = _campground(point_reyes_month, Camp("Sky Camp", "233359", loop="Sky"), meta=campground_meta["campground"])
    assert r.official_name == "Point Reyes National Seashore Campground"


def test_hidden_and_day_use_sites_are_ignored(point_reyes_month):
    raw = {"campsites": dict(point_reyes_month["campsites"])}
    sid = next(sid for sid, s in raw["campsites"].items() if s["loop"] == "Sky")
    raw["campsites"][sid] = dict(raw["campsites"][sid], hide_external=True)
    r = _campground(raw, Camp("Sky Camp", "233359", loop="Sky"))
    assert sid not in r.sites_by_id


def test_permit_nested_shape(permit_month_nested):
    opened = permit_open_dates(permit_month_nested)
    # fixture: first date remaining>0, second forced to 0, third remaining>0
    assert len(opened) == 2
    assert all(isinstance(k, date) for k in opened)


def test_permit_legacy_flat_shape():
    raw = {"payload": {"availability": {
        "2026-10-09T00:00:00Z": {"remaining": 2, "total": 8},
        "2026-10-10T00:00:00Z": {"remaining": 0, "total": 8},
    }}}
    assert permit_open_dates(raw) == {date(2026, 10, 9): 2}


def test_permit_result_uses_permit_url(permit_month_nested):
    dates = sorted(permit_open_dates(permit_month_nested))
    friday = dates[0]
    camp = Camp("Some Permit", "445859", permit_id="445859")
    r = parse({"type": "permit", "data": permit_month_nested}, camp, friday)
    assert r.permit_required is True
    assert r.reservation_url == "https://www.recreation.gov/permits/445859"
    assert friday.isoformat() in r.available_dates


def test_contiguous_requires_two_nights_at_one_site():
    # Fri open at site A, Sat open at site B: two one-night trips, not a weekend.
    raw = {"campsites": {
        "a": {"loop": "L", "site": "A", "availabilities": {"2026-10-09T00:00:00Z": "Available",
                                                            "2026-10-10T00:00:00Z": "Reserved"}},
        "b": {"loop": "L", "site": "B", "availabilities": {"2026-10-09T00:00:00Z": "Reserved",
                                                            "2026-10-10T00:00:00Z": "Available"}},
    }}
    r = _campground(raw, Camp("X", "1"))
    assert r.available_dates == ["2026-10-09", "2026-10-10"]
    assert r.contiguous is False
    assert r.windows_by_site_id == {}


def test_stay_rules_parsed_from_facility_rules():
    from recon.parser import stay_rules_from_meta
    meta = {"facility_name": "KIRK CREEK CAMPGROUND", "facility_rules": {
        "maxConsecutiveStay": {"value": 14, "units": ""},
        "minConsecutiveStay": {"value": 2, "units": "consecutive nights", "secondary_value": "softAny"},
        "minHolidayWeekendStay": {"value": 3, "secondary_value": "strict"},
        "minWeekendStay": {"value": 2, "secondary_value": "soft"},
        "reservationCutOff": {"value": 3},
        "hasTaxes": {"value": 1},
    }}
    rules = stay_rules_from_meta(meta)
    assert rules.min_nights == 2 and rules.min_weekend_nights == 2
    assert rules.min_holiday_weekend_nights == 3 and rules.max_nights == 14
    assert stay_rules_from_meta({"facility_name": "X"}) is None
    assert stay_rules_from_meta({"facility_rules": {"minConsecutiveStay": {"value": 0}}}) is None
    assert stay_rules_from_meta(None) is None


def test_one_malformed_site_is_skipped_not_fatal(point_reyes_month):
    from recon.parser import validate_campground
    raw = {"campsites": dict(point_reyes_month["campsites"])}
    raw["campsites"]["bad1"] = {"loop": "Sky", "availabilities": None, "hide_external": None, "min_num_people": ""}
    raw["campsites"]["bad2"] = None                                     # null site object
    raw["campsites"]["bad3"] = {"loop": 5, "availabilities": {"2026-10-09T00:00:00Z": None, "2026-10-10T00:00:00Z": "Available"},
                                "quantities": {"2026-10-10T00:00:00Z": None}, "max_num_people": "8"}
    response, skipped = validate_campground(raw)
    assert skipped == 1                                                 # only the null object is unrecoverable
    assert response.campsites["bad1"].availabilities == {} and response.campsites["bad1"].hide_external is False
    assert response.campsites["bad3"].loop == "5" and response.campsites["bad3"].max_num_people == 8
    assert response.campsites["bad3"].availabilities == {"2026-10-10T00:00:00Z": "Available"}
    r = _campground(raw, Camp("Sky Camp", "233359", loop="Sky"))
    assert r.skipped_sites == 1 and r.loop_matched is True
    assert "2026-10-10" in r.available_dates                            # the good sites still report
    assert validate_campground([1, 2])[0].campsites == {}


def test_loop_matched_false_when_loop_absent(point_reyes_month):
    r = _campground(point_reyes_month, Camp("Ghost", "233359", loop="Nope"))
    assert r.loop_matched is False and r.available_dates == []
    assert _campground(point_reyes_month, Camp("All", "233359")).loop_matched is None


def test_stay_rules_keep_policy_qualifier():
    from recon.parser import stay_rules_from_meta
    rules = stay_rules_from_meta({"facility_rules": {
        "minConsecutiveStay": {"value": 2, "secondary_value": "softAny"},
        "minHolidayWeekendStay": {"value": 3, "secondary_value": "strict"},
        "minWeekendStay": {"value": 2, "secondary_value": ""},
    }})
    assert rules.min_nights_policy == "softAny" and rules.min_holiday_weekend_policy == "strict"
    assert rules.min_weekend_nights == 2 and rules.min_weekend_policy is None


def test_site_category_vocabulary():
    from recon.models import RawSiteAvailability as S
    from recon.parser import site_category
    cases = {
        "STANDARD NONELECTRIC": None, "HIKE TO": None, "WALK TO": None, "TENT ONLY NONELECTRIC": None,
        "RV ELECTRIC": None, "CABIN NONELECTRIC": None, "EQUESTRIAN NONELECTRIC": None,
        "GROUP HIKE TO": "group", "GROUP STANDARD ELECTRIC": "group", "GROUP TENT ONLY AREA NONELECTRIC": "group",
        "group walk to": "group", "GROUP EQUESTRIAN": "group",
        "BOAT IN": "boat_in", "boat in": "boat_in", "MOORING": "boat_in", "ANCHORAGE": "boat_in",
    }
    for kind, expected in cases.items():
        assert site_category(S(campsite_type=kind)) == expected, kind
    # type missing → fall back to the label; a label never overrides a real type
    assert site_category(S(site="008 GROUP")) == "group"
    assert site_category(S(site="BOAT A, 1-6 people")) == "boat_in"
    assert site_category(S(site="GROUPER COVE 12")) is None
    assert site_category(S(campsite_type="STANDARD NONELECTRIC", site="GROUP OVERFLOW")) is None
    assert site_category(S()) is None
    # boat wins over group — on the type path, the label path, and when the label refines a GROUP type
    assert site_category(S(campsite_type="GROUP BOAT IN")) == "boat_in"
    assert site_category(S(site="TOMALES BEACH GROUP, BOAT ONLY, 15-25 people")) == "boat_in"
    assert site_category(S(campsite_type="GROUP TENT ONLY AREA NONELECTRIC",
                           site="TOMALES BEACH GROUP, BOAT ONLY, 15-25 people")) == "boat_in"
    assert site_category(S(campsite_type="GROUP TENT ONLY AREA NONELECTRIC", site="MARSHALL BEACH GROUP, 15-25 people")) == "group"
    # a label never promotes an ordinarily-typed site, even to boat_in
    assert site_category(S(campsite_type="HIKE TO", site="BOAT LAUNCH VIEW 4")) is None
    # label fallback: case-insensitive, comma-tolerant; types: whitespace-tolerant
    assert site_category(S(site="Group Site 2")) == "group"
    assert site_category(S(site="MARSHALL BEACH GROUP, 15-25 people")) == "group"
    assert site_category(S(campsite_type=" MOORING ")) == "boat_in"
    assert site_category(S(campsite_type="  group   walk to ")) == "group"
    assert site_category(S(campsite_type="   ", site="008 GROUP")) == "group"      # whitespace-only type counts as missing


def test_weekend_mode_keeps_group_and_boat_sites(point_reyes_month):
    """Weekend mode never filters by type: sites_by_id / site_details are durable for the auto-cart matcher."""
    whole = _campground(point_reyes_month, Camp("Point Reyes", "233359"))
    kinds = {sid: d.campsite_type for sid, d in whole.site_details.items()}
    fixture_open = {sid for sid, s in point_reyes_month["campsites"].items()
                    if any(st == "Available" and dt[:10] in ("2026-10-09", "2026-10-10", "2026-10-11")
                           for dt, st in s["availabilities"].items())}
    assert set(whole.sites_by_id) == fixture_open                       # nothing dropped, whatever its type
    special_open = [sid for sid in fixture_open
                    if "GROUP" in (point_reyes_month["campsites"][sid]["campsite_type"] or "")
                    or "BOAT" in (point_reyes_month["campsites"][sid]["campsite_type"] or "")]
    assert special_open, "fixture should contain at least one open group/boat-in site for this test to mean anything"
    assert all(sid in kinds for sid in special_open)
