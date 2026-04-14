import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import date, timedelta

from recon.api_client import RecGovClient
from recon.availability import fetch_camp_availability
from recon.config import LOCATIONS, Location
from recon.models import LocationReport
from recon.parser import parse
from recon.search import search
from recon.weather import fetch_weekend_weather


# Last-resort fallback for users who can't (or don't want to) use OS secret storage.
# Paste your RIDB key between the quotes. Leave empty otherwise — Keychain / Credential
# Manager / RIDB_API_KEY env var are all checked first.
_HARDCODED_API_KEY_FALLBACK = ""


def _keychain_macos() -> str:
    user = os.environ.get("USER", "")
    try:
        return subprocess.check_output(
            ["security", "find-generic-password", "-a", user, "-s", "recreation-gov-api", "-w"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
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


def _run_location(loc: Location, client: RecGovClient, friday: date) -> LocationReport:
    sites = []
    for camp in loc.camps:
        raw = fetch_camp_availability(client, camp, friday)
        if raw:
            sites.append(parse(raw, camp, friday))

    return LocationReport(
        location      = loc.name,
        weekend_start = friday.isoformat(),
        weekend_end   = (friday + timedelta(2)).isoformat(),
        available     = any(s.available_dates for s in sites),
        sites         = sites,
        weather       = fetch_weekend_weather(loc.lat, loc.lon, friday),
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Campsite availability checker")
    p.add_argument("--location", choices=list(LOCATIONS), help="Preset location key")
    p.add_argument("--date", help="Friday date YYYY-MM-DD (default: next Friday)")
    p.add_argument("--search", help="Free-text location query (e.g. 'Yosemite')")
    p.add_argument("--start",  help="Search start date YYYY-MM-DD")
    p.add_argument("--end",    help="Search end date YYYY-MM-DD")
    args = p.parse_args()

    api_key = _get_api_key()
    if not api_key:
        print(json.dumps({"error": (
            "No RIDB API key found. Provide it one of three ways: "
            "(1) macOS Keychain — security add-generic-password -a $USER -s recreation-gov-api -w <KEY>; "
            "(2) Windows Credential Manager — cmdkey /generic:recreation-gov-api /user:rec /pass:<KEY>; "
            "(3) env var RIDB_API_KEY or REC_GOV_API_KEY; "
            "(4) edit _HARDCODED_API_KEY_FALLBACK in main.py. "
            "Get a key at ridb.recreation.gov/profile."
        )}))
        sys.exit(1)

    client = RecGovClient(api_key)

    if args.search:
        if not (args.start and args.end):
            print(json.dumps({"error": "--search requires --start and --end"}))
            sys.exit(1)
        start  = date.fromisoformat(args.start)
        end    = date.fromisoformat(args.end)
        report = search(client, args.search, start, end)
        print(json.dumps(asdict(report), indent=2))
        return

    friday    = date.fromisoformat(args.date) if args.date else _upcoming_friday()
    locations = [LOCATIONS[args.location]] if args.location else list(LOCATIONS.values())
    reports   = [asdict(_run_location(loc, client, friday)) for loc in locations]

    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
