from recon.models import (
    RawCampgroundResponse,
    RawSiteAvailability,
    is_available,
    is_bookable_site,
)


def test_denylist_treats_open_as_unavailable():
    assert is_available("Available")
    for status in ("Reserved", "Not Available", "Not Reservable", "Not Reservable Management",
                   "Not Available Cutoff", "Lottery", "Open", "NYR", "Closed"):
        assert not is_available(status), status


def test_raw_site_ignores_unknown_fields_and_keeps_new_ones(point_reyes_month):
    resp = RawCampgroundResponse.model_validate(point_reyes_month)
    assert len(resp.campsites) == point_reyes_month["count"]
    site = next(iter(resp.campsites.values()))
    assert site.loop
    assert site.type_of_use == "Overnight"
    assert site.hide_external is False
    assert site.campsite_reserve_type in {"Site-Specific", "Non Site-Specific"}


def test_bookable_site_filters_hidden_and_day_use():
    base = {"availabilities": {}, "loop": "Sky", "site": "001"}
    assert is_bookable_site(RawSiteAvailability.model_validate(base))
    assert not is_bookable_site(RawSiteAvailability.model_validate(base | {"hide_external": True}))
    assert not is_bookable_site(RawSiteAvailability.model_validate(base | {"type_of_use": "Day"}))
    assert is_bookable_site(RawSiteAvailability.model_validate(base | {"type_of_use": "Overnight"}))
