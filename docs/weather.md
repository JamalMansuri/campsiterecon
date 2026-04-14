# recon/weather.py

Fetches a 3-day Fri/Sat/Sun forecast from Open-Meteo. Used only by weekend mode.

[Source](../recon/weather.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def fetch_weekend_weather(lat: float, lon: float, friday: date) -> dict[str, WeatherDay]
```

Returns a dict keyed by day label:

```python
{"friday": WeatherDay(...), "saturday": WeatherDay(...), "sunday": WeatherDay(...)}
```

`WeatherDay` is defined in [models.md](models.md). Returns `{}` on any network or parse failure — main.py treats empty as "no weather data" without erroring.

## API

- **Endpoint**: `api.open-meteo.com/v1/forecast`
- **Auth**: none. Free, no registration.
- **Forecast horizon**: 14 days. Anything beyond that is empty.
- **Units**: hardcoded to °C / km/h / mm. Conversion to F/mph/inch happens at the presentation layer (the LLM in [SKILL.md](../SKILL.md)).

The function fetches a flat 14-day forecast and then filters to exactly the three target dates. This is wasteful but cheap (~2 KB response) and avoids per-day requests.

## WMO weather codes

Open-Meteo encodes conditions as integer WMO codes. The `_WMO` table at the top of the module maps them to human-readable strings:

| Range | Meaning |
|---|---|
| 0–3 | Clear → Overcast |
| 45, 48 | Fog |
| 51–55 | Drizzle |
| 61–65 | Rain |
| 71–77 | Snow |
| 80–82 | Showers |
| 95–99 | Thunderstorms |

Unknown codes resolve to `"Unknown"`. The emoji mapping (used by the Telegram reply) lives in [SKILL.md](../SKILL.md), not here — this module only emits string labels.

## Why weekend mode only

- Search mode (Mode 2) often spans dates months out, well past Open-Meteo's 14-day horizon.
- Watch mode (Mode 3) is just cron'd search mode.

Calling weather from either would produce mostly-empty data with no value. [search.md](search.md) deliberately doesn't import this module.

## SSL note

Same `certifi.where()` trust store as [api_client.md](api_client.md), for the same reason — bypasses macOS python3 SSL flakiness.
