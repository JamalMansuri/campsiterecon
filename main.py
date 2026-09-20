import argparse
import getpass
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from recon.api_client import RecGovClient
from recon.availability import fetch_camp_availability
from recon.config import LOCATIONS, Location
from recon.models import LocationReport
from recon.parser import parse
from recon.search import rate_limit_warning, search
from recon.verify import verify_presets
from recon.weather import fetch_weekend_weather

# Fallback API key for users who edit the script directly. Not recommended.
_HARDCODED_API_KEY_FALLBACK = " "

_KEYCHAIN_SERVICES = ("recreation-gov-api", "recreation_gov_api", "recreation_gov_api_key")

# Written on the Mac mini by deploy/fetch_ridb_key.sh from 1Password (the source of truth there).
# `op` is deliberately NOT called from here: on that box it hangs instead of failing and a cold
# read takes up to a minute, so the fetch happens off the request path and we only read its cache.
_KEY_FILE = Path(os.environ.get("CAMPSITESCOUT_KEY_FILE", "~/.campsitescout/ridb_api_key")).expanduser()


def _key_file() -> str:
    try:
        return _KEY_FILE.read_text().strip()
    except OSError:
        return ""


def _keychain_macos() -> str:
    # cron/launchd don't set $USER; getpass falls back to the passwd database.
    # The production Mac mini stored the item under an underscored name.
    user = os.environ.get("USER") or getpass.getuser()
    for service in _KEYCHAIN_SERVICES:
        try:
            key = subprocess.check_output(
                ["security", "find-generic-password", "-a", user, "-s", service, "-w"],
                text=True, stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            continue
        if key:
            return key
    return ""


def _credential_manager_windows() -> str:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return ""

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    except Exception:
        return ""

    CredReadW = advapi32.CredReadW
    CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                          ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
    CredReadW.restype = wintypes.BOOL
    CredFree = advapi32.CredFree
    CredFree.argtypes = [ctypes.c_void_p]

    cred_ptr = ctypes.POINTER(CREDENTIAL)()
    if not CredReadW("recreation-gov-api", 1, 0, ctypes.byref(cred_ptr)):
        return ""
    try:
        cred = cred_ptr.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        try:
            return blob.decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            return blob.decode("utf-8", errors="ignore").rstrip("\x00")
    finally:
        CredFree(cred_ptr)


def _get_api_key() -> str:
    key = _key_file()          # first: a 1Password-synced cache beats a possibly stale Keychain item
    if key:
        return key
    if sys.platform == "darwin":
        key = _keychain_macos()
        if key:
            return key
    elif sys.platform == "win32":
        key = _credential_manager_windows()
        if key:
            return key

    for var in ("RIDB_API_KEY", "REC_GOV_API_KEY"):
        env = os.environ.get(var, "").strip()
        if env:
            return env

    return _HARDCODED_API_KEY_FALLBACK.strip()


def _upcoming_friday() -> date:
    today = date.today()
    days  = (4 - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


def _json_error(message: str) -> None:
    print(json.dumps({"error": message}))
    sys.exit(1)


def _parse_iso(value: str, flag: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        _json_error(f"{flag} must be a date in YYYY-MM-DD form, got {value!r}")
        raise  # unreachable; keeps type checkers happy


def _resolve_friday(value: str | None) -> tuple[date, list[str]]:
    """--date is the weekend's Friday. A Sat/Sun snaps back to that weekend's
    Friday; Mon–Thu snaps forward to the coming one. Either way the shift is
    reported so the LLM says which weekend was checked."""
    if not value:
        return _upcoming_friday(), []
    d = _parse_iso(value, "--date")
    if d.weekday() == 4:
        friday = d
    elif d.weekday() in (5, 6):
        friday = d - timedelta(days=d.weekday() - 4)
    else:
        friday = d + timedelta(days=4 - d.weekday())
    if friday < date.today() - timedelta(days=2):      # the weekend is "current" through Sunday night
        _json_error(f"--date {value} is in the past (weekend starting {friday.isoformat()})")
    notes = [] if friday == d else [
        f"--date {d.isoformat()} is a {d.strftime('%A')}; checked the weekend starting Friday {friday.isoformat()}"]
    return friday, notes


def _failure_note(client: RecGovClient, camp) -> str | None:
    reason = client.error_for(camp.facility_id) or (client.error_for(camp.permit_id) if camp.permit_id else None)
    if not reason or reason.startswith("HTTP 429"):
        return None                                   # covered by rate_limit_warning
    if reason.startswith("HTTP 404"):
        return f"{camp.name}: Rec.gov returned 404 for facility id {camp.facility_id} — the id is wrong; run `main.py --verify`"
    if reason.startswith("HTTP 400"):
        return f"{camp.name}: Rec.gov rejected the request (HTTP 400) — dates must be within the next two years"
    return f"{camp.name}: could not fetch availability ({reason})"


def _run_location(loc: Location, client: RecGovClient, friday: date, notes: list[str]) -> LocationReport:
    sites, unreachable, warnings = [], [], list(notes)
    for camp in loc.camps:
        raw = fetch_camp_availability(client, camp, friday)
        if raw:
            result = parse(raw, camp, friday)
            sites.append(result)
            if raw.get("missing_months"):
                warnings.append(f"{camp.name}: no data for {', '.join(raw['missing_months'])} — "
                                "nights in that month were not checked")
            if raw.get("empty_months"):
                warnings.append(f"{camp.name}: Rec.gov lists no campsites at all for {', '.join(raw['empty_months'])} "
                                "(closed for the season?) — nothing was bookable, not 'unchecked'")
            if result.loop_matched is False:
                warnings.append(f"{camp.name}: loop {camp.loop!r} matched no campsite in facility {camp.facility_id} — "
                                "the preset is wrong or Rec.gov renamed the loop; run `main.py --verify`")
            if result.skipped_sites:
                warnings.append(f"{camp.name}: {result.skipped_sites} campsite record(s) with an unrecognised shape were skipped")
        else:
            unreachable.append(camp.name)
            note = _failure_note(client, camp)
            if note:
                warnings.append(note)

    return LocationReport(
        location      = loc.name,
        weekend_start = friday.isoformat(),
        weekend_end   = (friday + timedelta(2)).isoformat(),
        nights        = [(friday + timedelta(i)).isoformat() for i in range(3)],
        available     = any(s.available_dates for s in sites),
        sites         = sites,
        unreachable   = unreachable,
        warnings      = warnings + rate_limit_warning(client, len(unreachable)),
        weather       = fetch_weekend_weather(loc.lat, loc.lon, friday),
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Campsite availability checker")
    p.add_argument("--location", choices=list(LOCATIONS), help="Preset location key")
    p.add_argument("--date", help="Friday date YYYY-MM-DD (default: next Friday)")
    p.add_argument("--search", help="Free-text location query (e.g. 'Yosemite')")
    p.add_argument("--start",  help="Search start date YYYY-MM-DD")
    p.add_argument("--end",    help="Search end date YYYY-MM-DD")
    p.add_argument("--all-site-types", action="store_true",
                   help="Search mode: also count group and boat-in campsites (skipped by default)")
    p.add_argument("--verify", action="store_true",
                   help="Check every preset facility id against RIDB + Rec.gov and exit 1 on any mismatch")
    p.add_argument("--debug",  action="store_true", help="Print swallowed HTTP errors to stderr")
    args = p.parse_args()

    # Only RIDB (search + verify) needs the key; the Rec.gov availability
    # endpoints used by weekend mode are unauthenticated.
    api_key = _get_api_key()
    if (args.search or args.verify) and not api_key:
        print(json.dumps({"error": (
            "No RIDB API key found. Provide it one of these ways: "
            "(0) on the Mac mini, run deploy/fetch_ridb_key.sh to cache it from 1Password; "
            "(1) macOS Keychain — security add-generic-password -a $USER -s recreation-gov-api -w <KEY>; "
            "(2) Windows Credential Manager — cmdkey /generic:recreation-gov-api /user:rec /pass:<KEY>; "
            "(3) env var RIDB_API_KEY or REC_GOV_API_KEY; "
            "(4) edit _HARDCODED_API_KEY_FALLBACK in main.py. "
            "Get a key at ridb.recreation.gov/profile."
        )}))
        sys.exit(1)

    client = RecGovClient(api_key or None, debug=True if args.debug else None)

    if args.verify:
        report = verify_presets(client)
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        sys.exit(0 if report.ok else 1)

    if args.search:
        if not (args.start and args.end):
            print(json.dumps({"error": "--search requires --start and --end"}))
            sys.exit(1)
        start  = _parse_iso(args.start, "--start")
        end    = _parse_iso(args.end, "--end")
        if end < start:
            _json_error(f"--end {args.end} is before --start {args.start}")
        report = search(client, args.search, start, end, include_all_site_types=args.all_site_types)
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return

    friday, notes = _resolve_friday(args.date)
    locations = [LOCATIONS[args.location]] if args.location else list(LOCATIONS.values())
    reports   = [_run_location(loc, client, friday, notes).model_dump(mode="json") for loc in locations]

    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
