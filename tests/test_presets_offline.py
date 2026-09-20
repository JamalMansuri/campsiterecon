"""Every preset id must verify against RECORDED RIDB + Rec.gov data.

This is the CI gate for CLAUDE.md invariant 1: adding a facility id to
recon/config.py without refreshing tests/fixtures/presets/directory.json
fails here, and an id whose recorded name/coordinates/type don't match the
preset fails here too. Refresh the fixture with the snippet in docs/verify.md
(it is what `main.py --verify` checks live)."""

import json
from pathlib import Path

from recon.config import LOCATIONS
from recon.verify import verify_presets
from tests.conftest import load_fixture

DIRECTORY = json.loads((Path(__file__).parent / "fixtures" / "presets" / "directory.json").read_text())


class RecordedClient:
    rate_limited = False

    def ridb_facility(self, fid):
        rec = DIRECTORY["ridb"].get(fid)
        return rec if rec and rec.get("FacilityName") else None

    def campground_meta(self, fid):
        return DIRECTORY["recgov_meta"].get(fid)

    def ridb_recarea_name(self, ra):
        return DIRECTORY["recareas"].get(str(ra or ""))

    def campground_month(self, fid, year, month):
        # Only Point Reyes presets carry a loop; its recorded month fixture has every loop name.
        return load_fixture("campground_month_point_reyes_233359.json") if fid == "233359" else {"campsites": {}}


def test_every_preset_id_is_recorded_and_verifies():
    ids = {camp.facility_id for loc in LOCATIONS.values() for camp in loc.camps}
    missing = ids - set(DIRECTORY["ridb"])
    assert not missing, f"preset ids without a recorded RIDB/Rec.gov fixture: {sorted(missing)} — run the capture snippet in docs/verify.md"
    report = verify_presets(RecordedClient(), LOCATIONS)
    assert report.ok, report.problems


def test_recorded_fixture_would_catch_the_original_bug():
    """The April 2026 config had Sky Camp = 234059 (Devils Garden, UT). Prove the gate bites."""
    from recon.config import Camp, Location
    bad = {"point_reyes": Location(name="Point Reyes National Seashore", lat=38.037, lon=-122.803,
                                   camps=(Camp("Sky Camp", "234059", "4675310"),))}
    client = RecordedClient()
    report = verify_presets(client, bad)
    assert not report.ok and "unknown" in report.problems[0]   # not in the recorded directory at all
