from recon.config import Camp, Location
from recon.verify import verify_presets


class FakeClient:
    def __init__(self, ridb, meta, months):
        self._ridb, self._meta, self._months = ridb, meta, months

    def ridb_facility(self, fid):
        return self._ridb.get(fid)

    def campground_meta(self, fid):
        return self._meta.get(fid)

    def campground_month(self, fid, year, month):
        return self._months.get(fid)

    def ridb_recarea_name(self, ra):
        return {"2864": "Point Reyes National Seashore", "2573": "Arches National Park"}.get(str(ra))


def _ridb(name, lat, lon, ftype="Campground", parent="2864"):
    return {"FacilityName": name, "FacilityTypeDescription": ftype, "FacilityLatitude": lat,
            "FacilityLongitude": lon, "ParentRecAreaID": parent, "Reservable": True, "Enabled": True}


def test_verify_flags_far_away_facility_and_missing_loop(point_reyes_month):
    locations = {
        "point_reyes": Location(
            name="Point Reyes", lat=38.037, lon=-122.803,
            camps=(
                Camp("Sky Camp", "233359", loop="Sky"),
                Camp("Bogus", "234059", loop="Sky"),          # Devils Garden, Utah
                Camp("Ghost Loop", "233359", loop="Nope"),
                Camp("Gone", "10149046"),
            ),
        )
    }
    client = FakeClient(
        ridb={"233359": _ridb("Point Reyes National Seashore Campground", 38.04, -122.80),
              "234059": _ridb("DEVILS GARDEN CAMPGROUND", 38.78, -109.59, parent="2573")},
        meta={"233359": {"facility_name": "Point Reyes National Seashore Campground"},
              "234059": {"facility_name": "DEVILS GARDEN CAMPGROUND"}},
        months={"233359": point_reyes_month, "234059": point_reyes_month},
    )
    report = verify_presets(client, locations)
    by_name = {c.name: c for c in report.camps}
    assert by_name["Sky Camp"].ok
    assert by_name["Sky Camp"].loops_found and "Sky" in by_name["Sky Camp"].loops_found
    assert not by_name["Bogus"].ok and "km" in by_name["Bogus"].problem
    assert not by_name["Ghost Loop"].ok and "loop" in by_name["Ghost Loop"].problem.lower()
    assert not by_name["Gone"].ok
    assert report.ok is False
    assert len(report.problems) == 3


def test_throttled_loop_check_is_reported_as_fetch_failure_not_missing_loop():
    locations = {"pr": Location(name="Point Reyes", lat=38.037, lon=-122.803,
                                camps=(Camp("Sky Camp", "233359", loop="Sky"),))}
    client = FakeClient(
        ridb={"233359": _ridb("Point Reyes National Seashore Campground", 38.04, -122.80)},
        meta={"233359": {"facility_name": "Point Reyes National Seashore Campground"}},
        months={},                                   # availability fetch returns None
    )
    client.rate_limited = True
    report = verify_presets(client, locations)
    assert not report.ok
    assert "429" in report.camps[0].problem and "loop 'Sky' not found" not in report.camps[0].problem


def test_verify_name_mismatch_and_missing_coordinates():
    locations = {"big_sur": Location(name="Big Sur", lat=35.97, lon=-121.46, camps=(
        Camp("Kirk Creek", "233116"),          # right
        Camp("Plaskett Creek", "233118"),      # id belongs to Ponderosa, 8 km away → name check catches it
        Camp("Ponderosa", "999"),              # no coordinates anywhere
    ))}
    client = FakeClient(
        ridb={"233116": _ridb("KIRK CREEK CAMPGROUND", 35.99, -121.49, parent="1067"),
              "233118": _ridb("PONDEROSA CAMPGROUND", 36.005, -121.376, parent="1067"),
              "999": _ridb("PONDEROSA CAMPGROUND", 0, "", parent="1067")},
        meta={"233116": {"facility_name": "KIRK CREEK CAMPGROUND"}, "233118": {"facility_name": "PONDEROSA CAMPGROUND"},
              "999": {"facility_name": "PONDEROSA CAMPGROUND"}},
        months={},
    )
    report = verify_presets(client, locations)
    by = {c.name: c for c in report.camps}
    assert by["Kirk Creek"].ok
    assert not by["Plaskett Creek"].ok and "name mismatch" in by["Plaskett Creek"].problem
    assert not by["Ponderosa"].ok and "no coordinates" in by["Ponderosa"].problem


def test_verify_warns_when_ridb_is_unreachable_but_still_checks_recgov():
    locations = {"big_sur": Location(name="Big Sur", lat=35.97, lon=-121.46, camps=(Camp("Kirk Creek", "233116"),))}
    client = FakeClient(ridb={}, months={},
                        meta={"233116": {"facility_name": "KIRK CREEK CAMPGROUND",
                                         "facility_latitude": 35.99, "facility_longitude": -121.49}})
    client.last_error = 401
    report = verify_presets(client, locations)
    assert report.ok and report.camps[0].distance_km is not None
    assert len(report.warnings) == 1 and "401" in report.warnings[0] and "revoked" in report.warnings[0]
