# recon/verify.py

Preset self-check behind `python main.py --verify`. Exists because the only serious bug this project has shipped — months of booking links to campgrounds in the wrong state — was invisible at runtime: a wrong facility id returns a perfectly well-formed availability response.

[Source](../recon/verify.py) · Wiki home: [README.md](README.md)

## Public surface

```python
def verify_presets(client, locations=None, today=None) -> VerifyReport
```

`main.py --verify` prints the report as JSON and exits `1` if any camp fails.

## What it checks, per camp

| Check | Fails when | Catches |
|---|---|---|
| RIDB `/facilities/{id}` or Rec.gov `/api/camps/campgrounds/{id}` resolves | both empty | ids that don't exist (Limekiln's old id) |
| Facility has coordinates and they are within 150 km of the `Location` lat/lon | missing/0 or further | ids for the wrong campground (Devils Garden UT filed as Sky Camp); a facility we cannot place |
| RIDB type is `Campground` (or `Permit` when `permit_id` is set) | mismatch | permit ids in the facility slot and vice versa |
| Key word of the preset label appears in the RIDB / Rec.gov name (non-loop camps) | absent | two nearby ids swapped between presets |
| `camp.loop` exists in this month's live availability response (loop camps) | absent | typos in loop names, Rec.gov renaming a loop |

A throttled availability fetch is reported as "could not fetch … (HTTP 429 rate limit)", not as a missing loop.

Each `VerifiedCamp` also carries the RIDB name, Rec.gov name, rec area, distance and the loops found, so a human can eyeball the table even when everything passes.

## When to run it

- After any edit to [config.md](config.md).
- When output looks wrong in a way that survives `--debug` (e.g. a camp reports sites that don't match its size).
- It costs ~3 requests per camp (RIDB, Rec.gov meta, and one availability month for loop camps). The availability call is subject to Rec.gov's 429 throttle; a `loop ... not found; loops present: []` result during a throttle is the throttle, not a config bug — rerun in a few minutes.

## Upstream / downstream

- **Called by**: [main.md](main.md) (`--verify`)
- **Calls**: [api_client.md](api_client.md) (`ridb_facility`, `campground_meta`, `ridb_recarea_name`, `campground_month`)
- **Outputs**: `VerifyReport` from [models.md](models.md)

## The offline gate

`tests/test_presets_offline.py` runs `verify_presets` against `tests/fixtures/presets/directory.json` — recorded RIDB `/facilities/{id}`, Rec.gov `/api/camps/campgrounds/{id}` and rec-area names for every preset id. A new id without a recorded entry fails the suite, and so does an id whose recorded name/coordinates/type contradict the preset. Refresh the fixture after editing config.py:

```bash
KEY=$(security find-generic-password -a "$USER" -s recreation-gov-api -w)
.venv/bin/python - "$KEY" <<'PY'
import json, ssl, certifi, sys, time
from urllib.request import Request, urlopen
sys.path.insert(0, ".")
from recon.config import LOCATIONS
key = sys.argv[1]; ctx = ssl.create_default_context(cafile=certifi.where()); H = {"User-Agent": "CampsiteRecon/1.0"}
get = lambda u: json.load(urlopen(Request(u, headers=H), context=ctx, timeout=25))
ridb, meta, recareas = {}, {}, {}
for loc in LOCATIONS.values():
    for camp in loc.camps:
        fid = camp.facility_id
        if fid in ridb: continue
        r = get(f"https://ridb.recreation.gov/api/v1/facilities/{fid}?apikey={key}")
        ridb[fid] = {k: r.get(k) for k in ("FacilityID","FacilityName","FacilityTypeDescription","FacilityLatitude","FacilityLongitude","ParentRecAreaID","Reservable","Enabled")}
        m = get(f"https://www.recreation.gov/api/camps/campgrounds/{fid}")["campground"]
        meta[fid] = {k: m.get(k) for k in ("facility_id","facility_name","facility_latitude","facility_longitude","parent_asset_id","is_deactivated")}
        ra = str(ridb[fid]["ParentRecAreaID"] or "")
        if ra and ra not in recareas: recareas[ra] = get(f"https://ridb.recreation.gov/api/v1/recareas/{ra}?apikey={key}").get("RecAreaName")
        time.sleep(0.25)
json.dump({"captured": "<today>", "ridb": ridb, "recgov_meta": meta, "recareas": recareas}, open("tests/fixtures/presets/directory.json", "w"), indent=1, sort_keys=True)
PY
```
