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


def _get_api_key() -> str:
    user = os.environ.get("USER", "")
    try:
        return subprocess.check_output(
            ["security", "find-generic-password", "-a", user, "-s", "recreation-gov-api", "-w"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return os.environ.get("RIDB_API_KEY", "")


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
        print(json.dumps({"error": "No API key — store it in Keychain under 'recreation-gov-api'"}))
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
