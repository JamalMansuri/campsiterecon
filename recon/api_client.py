import json
import ssl
import certifi
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class RecGovClient:
    _AVAIL_BASE = "https://www.recreation.gov/api"
    _RIDB_BASE  = "https://ridb.recreation.gov/api/v1"
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

    def ridb_search_campgrounds(self, query: str, limit: int = 50) -> list[dict]:
        url = (
            f"{self._RIDB_BASE}/facilities"
            f"?query={quote(query)}&facilitytype=Campground&limit={limit}"
            f"&apikey={self._api_key}"
        )
        raw = self._get(url)
        if not raw:
            return []
        return [f for f in raw.get("RECDATA", []) if f.get("Reservable")]
