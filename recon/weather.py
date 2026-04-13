import json
import ssl
import certifi
from urllib.request import urlopen
from urllib.error import URLError
from datetime import date, timedelta
from .models import WeatherDay

_WMO: dict[int, str] = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Showers", 81: "Showers", 82: "Heavy showers",
    95: "Thunderstorm", 96: "Thunderstorm + hail", 99: "Thunderstorm + hail",
}

_LABELS = {0: "friday", 1: "saturday", 2: "sunday"}


def fetch_weekend_weather(lat: float, lon: float, friday: date) -> dict[str, WeatherDay]:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max"
        f"&temperature_unit=celsius&wind_speed_unit=kmh&precipitation_unit=mm"
        f"&timezone=auto&forecast_days=14"
    )
    try:
        ctx = ssl.create_default_context(cafile=certifi.where())
        with urlopen(url, context=ctx, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError):
        return {}

    daily   = data.get("daily", {})
    times   = daily.get("time", [])
    targets = {(friday + timedelta(i)).isoformat(): _LABELS[i] for i in range(3)}
    result: dict[str, WeatherDay] = {}

    for i, t in enumerate(times):
        label = targets.get(t)
        if not label:
            continue
        result[label] = WeatherDay(
            date      = t,
            high_c    = round(daily["temperature_2m_max"][i], 1),
            low_c     = round(daily["temperature_2m_min"][i], 1),
            rain_mm   = round(daily["precipitation_sum"][i] or 0.0, 1),
            wind_kph  = round(daily["windspeed_10m_max"][i], 1),
            condition = _WMO.get(daily["weathercode"][i], "Unknown"),
        )

    return result
