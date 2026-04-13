import json
import ssl
import certifi
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class RecGovClient:
    _AVAIL_BASE = "https://www.recreation.gov/api"
    _HEADERS    = {"User-Agent": "CampsiteRecon/1.0", "Accept": "application/json"}

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._ssl     = ssl.create_default_context(cafile=certifi.where())

    def _get(self, url: str) -> dict | None:
        try:
            with urlopen(Request(url, headers=self._HEADERS), context=self._ssl, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError):
            return None

    def campground_month(self, facility_id: str, year: int, month: int) -> dict | None:
        url = (
            f"{self._AVAIL_BASE}/camps/availability/campground/{facility_id}/month"
            f"?start_date={year}-{month:02d}-01T00%3A00%3A00.000Z"
        )
        return self._get(url)

    def permit_month(self, permit_id: str, year: int, month: int) -> dict | None:
        url = (
            f"{self._AVAIL_BASE}/permits/{permit_id}/availability/month"
            f"?start_date={year}-{month:02d}-01T00%3A00%3A00.000Z&commercial_acct=false"
        )
        return self._get(url)
