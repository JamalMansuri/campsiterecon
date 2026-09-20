from recon.api_client import RecGovClient


class StubClient(RecGovClient):
    """Replaces the network layer with canned responses keyed by URL substring."""

    def __init__(self, pages):
        super().__init__(api_key="k", cooldown_file=None)
        self._pages = pages
        self.urls = []

    def _fetch(self, url):
        self.urls.append(url)
        for key, payload in self._pages:
            if key in url:
                return payload
        return None


def _rec(fid, name, ftype="Campground", reservable=True, enabled=True):
    return {"FacilityID": fid, "FacilityName": name, "FacilityTypeDescription": ftype,
            "Reservable": reservable, "Enabled": enabled}


def test_ridb_search_paginates_and_filters_types():
    page1 = {"RECDATA": [_rec("1", "A"), _rec("2", "Permits", ftype="Permit"), _rec("3", "VC", ftype="Visitor Center", reservable=False)],
             "METADATA": {"RESULTS": {"CURRENT_COUNT": 3, "TOTAL_COUNT": 5}}}
    page2 = {"RECDATA": [_rec("4", "B"), _rec("5", "Disabled", enabled=False)],
             "METADATA": {"RESULTS": {"CURRENT_COUNT": 2, "TOTAL_COUNT": 5}}}
    client = StubClient([("offset=0", page1), ("offset=3", page2)])
    facilities, total = client.ridb_search_campgrounds("x")
    assert total == 5
    assert [f["FacilityID"] for f in facilities] == ["1", "4"]
    assert len(client.urls) == 2


def test_ridb_search_respects_max_results():
    page = {"RECDATA": [_rec(str(i), f"F{i}") for i in range(50)],
            "METADATA": {"RESULTS": {"CURRENT_COUNT": 50, "TOTAL_COUNT": 500}}}
    client = StubClient([("offset=0", page), ("offset=50", page)])
    facilities, total = client.ridb_search_campgrounds("x", max_results=60)
    assert total == 500
    assert len(facilities) == 60


def test_get_is_cached_per_client():
    client = StubClient([("campground/233359/month", {"campsites": {}})])
    a = client.campground_month("233359", 2026, 10)
    b = client.campground_month("233359", 2026, 10)
    assert a == b == {"campsites": {}}
    assert len(client.urls) == 1


def test_campground_meta_unwraps_envelope(campground_meta):
    client = StubClient([("camps/campgrounds/233359", campground_meta)])
    meta = client.campground_meta("233359")
    assert meta["facility_name"] == "Point Reyes National Seashore Campground"


class RateLimitedClient(RecGovClient):
    """Every availability fetch fails with 429; metadata fetches succeed."""

    def __init__(self, cooldown_file=None):
        super().__init__(api_key="k", cooldown_file=cooldown_file)
        self._PACE_SECONDS = 0.0
        self.fetches = 0

    def _fetch(self, url):
        self.fetches += 1
        if "/availability/" in url:
            self.last_error = 429
            return None
        return {"campground": {"facility_name": "X"}}


def test_429_trips_breaker_and_stops_further_availability_requests():
    client = RateLimitedClient()
    assert client.campground_month("1", 2026, 10) is None
    assert client.rate_limited is True
    assert client.campground_month("2", 2026, 10) is None
    assert client.permit_month("3", 2026, 10) is None
    assert client.fetches == 1                       # breaker short-circuited the rest
    assert client.campground_meta("1")["facility_name"] == "X"   # non-availability calls still go out
    assert client.fetches == 2


def test_recarea_anchor_requires_every_query_word_in_the_name_and_coordinates():
    page = {"RECDATA": [
        {"RecAreaID": "13374", "RecAreaName": "Cottonwood Point Wilderness", "Enabled": True,
         "RecAreaLatitude": 36.98, "RecAreaLongitude": -112.9},
        {"RecAreaID": "13824", "RecAreaName": "Route 1 - Pinnacles Coast", "Enabled": True,
         "RecAreaLatitude": 0, "RecAreaLongitude": 0},
        {"RecAreaID": "2893", "RecAreaName": "Pinnacles National Park", "Enabled": True,
         "RecAreaLatitude": 36.490292, "RecAreaLongitude": -121.181361},
    ]}
    client = StubClient([("recareas?query=Pinnacles", page)])
    anchor = client.ridb_search_recarea("Pinnacles")
    assert anchor == {"id": "2893", "name": "Pinnacles National Park", "lat": 36.490292, "lon": -121.181361}
    assert client.ridb_search_recarea("Nowhere Special") is None


def test_429_cooldown_persists_across_client_instances(tmp_path):
    f = tmp_path / "rl.json"
    first = RateLimitedClient(cooldown_file=f)
    assert first.campground_month("1", 2026, 10) is None
    assert first.rate_limited and f.exists()
    second = RateLimitedClient(cooldown_file=f)          # a later run on the same IP
    assert second.rate_limited is True and second.rate_limited_until is not None
    assert second.campground_month("1", 2026, 10) is None
    assert second.fetches == 0                          # never touched the network
    assert second.campground_meta("1")["facility_name"] == "X"   # metadata still allowed


def test_read_phase_errors_never_escape(monkeypatch):
    import http.client
    import recon.api_client as mod

    class Boom:
        def __init__(self, exc): self.exc = exc
        def __enter__(self): raise self.exc
        def __exit__(self, *a): return False

    for exc in (TimeoutError("timed out"), ConnectionResetError(), http.client.IncompleteRead(b"x"),
                ValueError("bad json")):
        monkeypatch.setattr(mod, "urlopen", lambda *a, exc=exc, **k: Boom(exc))
        client = RecGovClient("k", cooldown_file=None)
        client._RETRY_WAIT = 0.0
        client._PACE_SECONDS = 0.0
        assert client.campground_month("1", 2026, 10) is None
        assert client.error_for("1")
        assert client.rate_limited is False


def test_error_for_reports_404_for_a_wrong_facility_id():
    class NotFound(RecGovClient):
        def _fetch(self, url):
            self.last_error = 404
            self.errors[self._redact(url)] = "HTTP 404"
            return None
    client = NotFound("k", cooldown_file=None)
    client._PACE_SECONDS = 0.0
    assert client.campground_month("10149046", 2026, 10) is None
    assert client.error_for("10149046") == "HTTP 404"
    assert client.error_for("233116") is None


def test_cooldown_file_with_naive_or_garbage_timestamp_never_raises(tmp_path):
    f = tmp_path / "rl.json"
    f.write_text('{"blocked_until": "2099-01-01T00:00:00"}')          # naive → treated as UTC, still in the future
    assert RecGovClient("k", cooldown_file=f).rate_limited is True
    f.write_text('{"blocked_until": "2000-01-01"}')                    # expired
    assert RecGovClient("k", cooldown_file=f).rate_limited is False
    for garbage in ("not json", '{"blocked_until": 12}', '{"nope": 1}', '{"blocked_until": null}'):
        f.write_text(garbage)
        assert RecGovClient("k", cooldown_file=f).rate_limited is False


def test_real_429_path_trips_breaker_and_writes_cooldown(monkeypatch, tmp_path):
    import io
    from urllib.error import HTTPError
    import recon.api_client as mod

    def fake_urlopen(req, **kw):
        raise HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))
    monkeypatch.setattr(mod, "urlopen", fake_urlopen)
    f = tmp_path / "rl.json"
    client = RecGovClient("k", cooldown_file=f)
    client._PACE_SECONDS = 0.0
    assert client.campground_month("1", 2026, 10) is None
    assert client.rate_limited and client.last_error == 429 and f.exists()
    assert client.error_for("1") == "HTTP 429"
    assert client.campground_month("2", 2026, 10) is None and client.error_for("2") is None   # skipped, not fetched


def test_non_object_body_is_an_error_not_a_crash(monkeypatch):
    import io
    import recon.api_client as mod

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(mod, "urlopen", lambda *a, **k: R(b"[1, 2, 3]"))
    client = RecGovClient("k", cooldown_file=None)
    client._PACE_SECONDS = 0.0
    assert client.campground_month("1", 2026, 10) is None
    assert "non-object" in client.error_for("1")


def test_failed_later_ridb_page_is_counted():
    page1 = {"RECDATA": [_rec("1", "A")], "METADATA": {"RESULTS": {"CURRENT_COUNT": 1, "TOTAL_COUNT": 80}}}
    client = StubClient([("offset=0", page1)])                        # offset=1 page → None
    facilities, total = client.ridb_search_campgrounds("x")
    assert [f["FacilityID"] for f in facilities] == ["1"] and total == 80
    assert client.ridb_pages_failed == 1
