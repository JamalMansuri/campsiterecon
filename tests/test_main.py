import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import main as cli

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
ENV = dict(os.environ, RIDB_API_KEY="test-key-not-real")   # argument validation must not depend on the Keychain


def test_resolve_friday_snaps_and_reports():
    today = date.today()
    fri = today + timedelta(days=(4 - today.weekday()) % 7 or 7)
    assert cli._resolve_friday(fri.isoformat()) == (fri, [])
    sat = fri + timedelta(days=1)
    f2, notes = cli._resolve_friday(sat.isoformat())
    assert f2 == fri and "Saturday" in notes[0] and fri.isoformat() in notes[0]
    wed = fri + timedelta(days=5)                                  # Wednesday after → next Friday
    f3, notes = cli._resolve_friday(wed.isoformat())
    assert f3 == fri + timedelta(days=7) and notes


def test_bad_or_past_dates_are_json_errors_not_tracebacks():
    out = subprocess.run([PY, "main.py", "--location", "pinnacles", "--date", "2026-13-45"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 1 and json.loads(out.stdout)["error"].startswith("--date must be")
    out = subprocess.run([PY, "main.py", "--search", "x", "--start", "2026-10-09", "--end", "2026-10-01"],
                         cwd=ROOT, capture_output=True, text=True, env=ENV)
    assert out.returncode == 1 and "before --start" in json.loads(out.stdout)["error"]
    out = subprocess.run([PY, "main.py", "--location", "pinnacles", "--date", "2020-01-03"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 1 and "in the past" in json.loads(out.stdout)["error"]


def test_failure_note_explains_404_but_defers_429_to_rate_limit_warning():
    from recon.config import Camp

    class C:
        def __init__(self, reason): self._r = reason
        def error_for(self, fid): return self._r
    assert "run `main.py --verify`" in cli._failure_note(C("HTTP 404"), Camp("Gone", "10149046"))
    assert cli._failure_note(C("HTTP 429"), Camp("X", "1")) is None
    assert cli._failure_note(C(None), Camp("X", "1")) is None
    assert "TimeoutError" in cli._failure_note(C("TimeoutError: timed out"), Camp("X", "1"))


def test_sunday_of_the_current_weekend_is_not_in_the_past(monkeypatch):
    import main as m
    class FakeDate(date):
        @classmethod
        def today(cls): return date(2026, 9, 20)          # a Sunday
    monkeypatch.setattr(m, "date", FakeDate)
    friday, notes = m._resolve_friday("2026-09-20")
    assert friday == date(2026, 9, 18) and notes


def test_run_location_surfaces_loop_mismatch_empty_month_and_rate_limit(monkeypatch):
    import main as m
    from recon.config import Camp, Location

    class C:
        rate_limited = True
        rate_limited_until = None
        def error_for(self, fid): return None
    calls = {"n": 0}
    def fake_fetch(client, camp, friday):
        calls["n"] += 1
        if camp.name == "Ghost":
            return {"type": "campground", "data": {"campsites": {"a": {"loop": "Sky", "availabilities": {}}}},
                    "meta": None, "missing_months": [], "empty_months": []}
        if camp.name == "Closed":
            return {"type": "campground", "data": {"campsites": {}}, "meta": None, "missing_months": [], "empty_months": ["2026-10"]}
        return None
    monkeypatch.setattr(m, "fetch_camp_availability", fake_fetch)
    monkeypatch.setattr(m, "fetch_weekend_weather", lambda *a, **k: {})
    loc = Location(name="T", lat=0, lon=0, camps=(Camp("Ghost", "1", loop="Nope"), Camp("Closed", "2"), Camp("Down", "3")))
    report = m._run_location(loc, C(), date(2026, 10, 9), ["note"])
    assert report.unreachable == ["Down"]
    assert report.warnings[0] == "note"
    assert any("loop 'Nope' matched no campsite" in w for w in report.warnings)
    assert any("lists no campsites" in w for w in report.warnings)
    assert any("rate-limiting" in w for w in report.warnings)
