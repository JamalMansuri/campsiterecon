import io
import json
from datetime import date

import recon.weather as weather


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _payload(days):
    keys = ("time", "weathercode", "temperature_2m_max", "temperature_2m_min", "precipitation_sum", "windspeed_10m_max")
    return json.dumps({"daily": {k: [d[i] for d in days] for i, k in enumerate(keys)}}).encode()


def test_null_days_are_skipped_not_crashed(monkeypatch):
    days = [
        ["2026-10-09", 3, 16.1, 8.0, 0.0, 12.0],
        ["2026-10-10", None, None, None, None, None],     # Open-Meteo pads the horizon with nulls
        ["2026-10-11", 61, 13.0, 9.0, None, 30.0],
    ]
    monkeypatch.setattr(weather, "urlopen", lambda *a, **k: FakeResponse(_payload(days)))
    out = weather.fetch_weekend_weather(38.0, -122.8, date(2026, 10, 9))
    assert set(out) == {"friday", "sunday"}
    assert out["sunday"].rain_mm == 0.0 and out["sunday"].condition == "Light rain"


def test_any_failure_returns_empty(monkeypatch):
    def boom(*a, **k): raise TimeoutError("slow")
    monkeypatch.setattr(weather, "urlopen", boom)
    assert weather.fetch_weekend_weather(38.0, -122.8, date(2026, 10, 9)) == {}
