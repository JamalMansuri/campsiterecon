import http.client
import json
import os
import ssl
import sys
import time
import certifi
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

_COOLDOWN_FILE = Path.home() / ".campsitescout" / "rate_limit.json"


class RecGovClient:
    """The only module that talks HTTP. Every method returns None / [] on any
    network or decode error — deliberate for cron (one bad request must not
    kill a multi-facility scan). Set CAMPSITESCOUT_DEBUG=1 (or debug=True) to
    see the swallowed errors on stderr.

    Responses are memoised per client instance, so asking for the same month
    of the same facility twice (Point Reyes: four loops, one facility) costs
    one request.

    Rec.gov's availability endpoints answer HTTP 429 (CloudFront, no
    Retry-After) when polled too fast; the block is per-IP and lasts several
    minutes, and every further request extends it. So: availability calls are
    paced, the FIRST 429 trips `rate_limited` for the rest of the run, and a
    cooldown timestamp is written to ~/.campsitescout/rate_limit.json so the
    next run (cron tick, or the LLM "trying again") does not re-hit the block.
    Callers surface `rate_limited` / `rate_limited_until` as a warning so
    "unchecked" is never reported as "full".
    """

    _AVAIL_BASE = "https://www.recreation.gov/api"
    _RIDB_BASE  = "https://ridb.recreation.gov/api/v1"
    _HEADERS    = {"User-Agent": "CampsiteRecon/1.0", "Accept": "application/json"}
    _RIDB_PAGE  = 50                          # RIDB's maximum page size
    _RETRY_ON   = frozenset({500, 502, 503, 504})   # 429 is never retried: it only extends the block
    _RETRY_WAIT = 1.5
    _PACE_SECONDS    = 0.6                    # minimum gap between availability requests
    _COOLDOWN_MINUTES = 10                    # how long a 429 keeps availability calls off across runs

    def __init__(self, api_key: str | None, debug: bool | None = None,
                 cooldown_file: Path | None = _COOLDOWN_FILE) -> None:
        self._api_key = api_key or ""
        self._ssl     = ssl.create_default_context(cafile=certifi.where())
        self._cache: dict[str, dict | None] = {}
        self._debug = bool(os.environ.get("CAMPSITESCOUT_DEBUG")) if debug is None else debug
        self._cooldown_file = cooldown_file
        self.rate_limited_until: datetime | None = self._read_cooldown()
        self.rate_limited = self.rate_limited_until is not None   # True from the start if a recent run was throttled
        self.last_error: int | None = None    # HTTP status of the most recent failed fetch
        self.errors: dict[str, str] = {}      # redacted url -> reason, for every failed fetch this run
        self.ridb_pages_failed = 0            # RIDB search pages that failed after the first (list truncated)
        self._last_request = 0.0
        if self.rate_limited:
            self._log(f"availability calls skipped: rate-limit cooldown until {self.rate_limited_until.isoformat()}")

    # -- cross-run 429 cooldown ----------------------------------------------

    def _read_cooldown(self) -> datetime | None:
        """Never raises: a missing, corrupt, naive or expired file means 'no cooldown'."""
        if not self._cooldown_file:
            return None
        try:
            until = datetime.fromisoformat(json.loads(self._cooldown_file.read_text())["blocked_until"])
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            return until if until > datetime.now(timezone.utc) else None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    def _write_cooldown(self) -> None:
        self.rate_limited_until = datetime.now(timezone.utc) + timedelta(minutes=self._COOLDOWN_MINUTES)
        if not self._cooldown_file:
            return
        try:
            self._cooldown_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)   # shares a dir with the booker's session file
            self._cooldown_file.write_text(json.dumps({"blocked_until": self.rate_limited_until.isoformat()}))
        except OSError as e:
            self._log(f"could not write cooldown file: {e}")

    def error_for(self, facility_or_permit_id: str) -> str | None:
        """Reason the most recent availability fetch for this id failed, if any."""
        needle = (f"/campground/{facility_or_permit_id}/", f"/permits/{facility_or_permit_id}/")
        for url, reason in reversed(list(self.errors.items())):
            if any(n in url for n in needle):
                return reason
        return None

    # -- transport ----------------------------------------------------------

    def _log(self, message: str) -> None:
        if self._debug:
            print(f"[api_client] {message}", file=sys.stderr)

    @staticmethod
    def _redact(url: str) -> str:
        return url.split("&apikey=")[0].split("?apikey=")[0]

    def _fetch(self, url: str) -> dict | None:
        """One GET, one retry on transient failures (5xx / connection). Never raises:
        OSError covers URLError, timeouts and resets; HTTPException covers truncated
        bodies; ValueError covers bad JSON and bad UTF-8."""
        self.last_error = None
        key = self._redact(url)
        for attempt in (1, 2):
            try:
                with urlopen(Request(url, headers=self._HEADERS), context=self._ssl, timeout=15) as r:
                    body = json.loads(r.read().decode("utf-8", errors="replace"))
                if not isinstance(body, dict):          # every endpoint we use answers an object
                    self.errors[key] = f"non-object body ({type(body).__name__})"
                    self._log(f"{self.errors[key]} {key}")
                    return None
                return body
            except HTTPError as e:
                self._log(f"HTTP {e.code} {key}")
                self.last_error = e.code
                self.errors[key] = f"HTTP {e.code}"
                if e.code not in self._RETRY_ON or attempt == 2:
                    return None
            except (OSError, http.client.HTTPException, ValueError) as e:
                reason = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
                self._log(f"{reason} {key}")
                self.errors[key] = reason
                if attempt == 2 or isinstance(e, ValueError):
                    return None
            time.sleep(self._RETRY_WAIT)
        return None

    def _pace(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._PACE_SECONDS:
            time.sleep(self._PACE_SECONDS - elapsed)
        self._last_request = time.monotonic()

    def _get(self, url: str, *, availability: bool = False) -> dict | None:
        if url in self._cache:
            return self._cache[url]
        if availability and self.rate_limited:
            self._log(f"skipped, rate limited this run: {self._redact(url)}")
            return None                        # not cached: a later run should try again
        if availability:
            self._pace()
        result = self._fetch(url)
        if availability and result is None and self.last_error == 429:
            self.rate_limited = True
            self._write_cooldown()
            self._log(f"HTTP 429 — no further availability requests until {self.rate_limited_until.isoformat()}")
        self._cache[url] = result
        return result

    # -- Rec.gov availability (no key) ---------------------------------------

    def campground_month(self, facility_id: str, year: int, month: int) -> dict | None:
        url = (
            f"{self._AVAIL_BASE}/camps/availability/campground/{facility_id}/month"
            f"?start_date={year}-{month:02d}-01T00%3A00%3A00.000Z"
        )
        return self._get(url, availability=True)

    def permit_month(self, permit_id: str, year: int, month: int) -> dict | None:
        url = (
            f"{self._AVAIL_BASE}/permits/{permit_id}/availability/month"
            f"?start_date={year}-{month:02d}-01T00%3A00%3A00.000Z&commercial_acct=false"
        )
        return self._get(url, availability=True)

    def campground_meta(self, facility_id: str) -> dict | None:
        """Rec.gov's own record for a facility: facility_name, lat/lon, parent
        asset. Used for official names in output and by --verify."""
        raw = self._get(f"{self._AVAIL_BASE}/camps/campgrounds/{facility_id}")
        if not isinstance(raw, dict):
            return None
        inner = raw.get("campground", raw)
        return inner if isinstance(inner, dict) and inner.get("facility_name") else None

    # -- RIDB directory (key required) ----------------------------------------

    def ridb_facility(self, facility_id: str) -> dict | None:
        raw = self._get(f"{self._RIDB_BASE}/facilities/{facility_id}?apikey={self._api_key}")
        # RIDB answers 200 with an all-empty record for unknown ids.
        return raw if isinstance(raw, dict) and raw.get("FacilityName") else None

    def ridb_recarea_name(self, rec_area_id: str | int | None) -> str | None:
        if not rec_area_id:
            return None
        raw = self._get(f"{self._RIDB_BASE}/recareas/{rec_area_id}?apikey={self._api_key}")
        return (raw or {}).get("RecAreaName") or None

    def ridb_search_recarea(self, query: str) -> dict | None:
        """Resolve a free-text query to ONE rec area with coordinates, used as
        the relevance anchor for search mode. RIDB's first hit is often junk
        ("Pinnacles" -> a Utah wilderness), so a record only qualifies when
        every word of the query appears in its name and it has coordinates.
        Returns {"id", "name", "lat", "lon"} or None (no filtering then)."""
        tokens = [t for t in "".join(c.lower() if c.isalnum() else " " for c in query).split() if len(t) >= 3]
        if not tokens:
            return None
        raw = self._get(f"{self._RIDB_BASE}/recareas?query={quote(query)}&limit=25&apikey={self._api_key}")
        for rec in (raw or {}).get("RECDATA") or []:
            name = (rec.get("RecAreaName") or "").lower()
            lat, lon = rec.get("RecAreaLatitude"), rec.get("RecAreaLongitude")
            if rec.get("Enabled", True) is False or not (lat and lon):
                continue
            if all(t in name for t in tokens):
                return {"id": str(rec.get("RecAreaID") or ""), "name": rec.get("RecAreaName"),
                        "lat": float(lat), "lon": float(lon)}
        return None

    @staticmethod
    def _is_bookable_campground(record: dict) -> bool:
        return (
            bool(record.get("Reservable"))
            and record.get("Enabled", True) is not False
            and record.get("FacilityTypeDescription") == "Campground"
        )

    def ridb_search_campgrounds(self, query: str, max_results: int = 150) -> tuple[list[dict], int]:
        """Free-text facility search, paginated to RIDB's TOTAL_COUNT (capped at
        max_results). Returns (campground records, total matches for the query).

        `facilitytype=Campground` is only a hint to RIDB — Permit, Timed Entry
        and Visitor Center records still come back, so we filter on the record.
        """
        out: list[dict] = []
        offset, total = 0, 0
        while len(out) < max_results:
            url = (
                f"{self._RIDB_BASE}/facilities"
                f"?query={quote(query)}&facilitytype=Campground"
                f"&limit={self._RIDB_PAGE}&offset={offset}&apikey={self._api_key}"
            )
            raw = self._get(url)
            if not raw:
                if offset:
                    self.ridb_pages_failed += 1
                break
            records = raw.get("RECDATA") or []
            meta_total = ((raw.get("METADATA") or {}).get("RESULTS") or {}).get("TOTAL_COUNT")
            if isinstance(meta_total, int):
                total = meta_total
            out.extend(r for r in records if self._is_bookable_campground(r))
            offset += len(records)
            if not records or offset >= total:
                break
        return out[:max_results], total
