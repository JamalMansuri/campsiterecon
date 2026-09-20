# main.py

CLI entry point. Loads the API key, dispatches to one of two modes, prints JSON to stdout.

[Source](../main.py) · Wiki home: [README.md](README.md)

## Public surface

```
python main.py                                                  # weekend mode, all presets
python main.py --location point_reyes                           # weekend mode, one preset
python main.py --location big_sur --date 2026-05-01             # weekend mode, specific Friday
python main.py --search "Yosemite" --start 2026-07-03 --end 2026-07-05   # search mode
python main.py --verify                                         # check every preset id; exit 1 on mismatch
python main.py --debug --location big_sur                       # print swallowed HTTP errors to stderr
```

Output is JSON on stdout. Exit `1` with a JSON error object on a missing API key (only `--search` / `--verify` need one — weekend mode is keyless), on an unparseable or past `--date`, or on `--end` before `--start`.

## Mode dispatch

`--verify` wins, then `--search`, else weekend mode across either all presets or the one named in `--location`.

```
args.verify ──► verify.verify_presets() ──► VerifyReport   ──► JSON, exit 1 unless ok
args.search ──► search.search()         ──► SearchReport   ──► JSON
        else ──► _run_location() per loc ──► LocationReport ──► JSON array
```

`_run_location` records camps whose fetch returned `None` in `unreachable[]` and attaches `warnings[]` (rate limiting) — a failed fetch is reported, not silently treated as "no availability".

Weekend mode also calls [weather.md](weather.md) per location. Search mode does not — see [search.md](search.md) for why.

## API key resolution

`_get_api_key()` walks these sources in order and returns the first non-empty match:

0. **1Password-synced cache** — `~/.campsitescout/ridb_api_key` (or `CAMPSITESCOUT_KEY_FILE`). Only exists on the Mac mini, where [deploy/fetch_ridb_key.sh](../deploy/fetch_ridb_key.sh) writes it from 1Password and the auto-deploy LaunchAgent refreshes it when RIDB rejects it. It goes first so a stale Keychain item can never shadow a rotated key. `main.py` never calls `op` itself — see [deploy.md](deploy.md) for why.
1. **macOS Keychain** — `security find-generic-password -s recreation-gov-api` (then the underscored `recreation_gov_api` / `recreation_gov_api_key` names the Mac mini used). The account comes from `$USER` or `getpass.getuser()`, so it works under cron. Only consulted on `darwin`.
2. **Windows Credential Manager** — `advapi32.CredReadW("recreation-gov-api")` via `ctypes`. Only on `win32`. No external deps.
3. **Env var** — `RIDB_API_KEY` or `REC_GOV_API_KEY` (either name).
4. **Hardcoded constant** — `_HARDCODED_API_KEY_FALLBACK` at the top of [main.py](../main.py). Empty by default. Last-resort for non-developers.

Empty string from all four → JSON error to stdout, exit 1, but only when the mode needs RIDB. The error message lists all four options. [../SKILL.md](../SKILL.md) has the LLM-facing setup walkthrough.

## Upstream / downstream

- **Called by**: OpenClaw skill (per [SKILL.md](../SKILL.md)), or a cron job from Mode 3.
- **Calls**: [api_client.md](api_client.md) (constructs `RecGovClient`), [config.md](config.md) (presets), [availability.md](availability.md), [parser.md](parser.md), [search.md](search.md), [verify.md](verify.md), [weather.md](weather.md).
- **Data shapes**: emits `LocationReport[]` (weekend) or `SearchReport` (search). Both defined in [models.md](models.md).

## Gotchas

- Friday for "this weekend" is computed by `_upcoming_friday()` — if today is Friday, it returns *next* Friday, not today. Intentional: the user means the weekend that hasn't started yet. An explicit `--date` that is a Sat/Sun snaps back to its Friday, Mon–Thu snaps forward, and the shift is reported in `warnings[]`; a weekend older than two days ago is rejected.
- The `_HARDCODED_API_KEY_FALLBACK` constant is checked **last**, not first, so an accidentally-committed value won't override a properly stored Keychain key.
- All exceptions from external HTTP are swallowed inside [api_client.md](api_client.md) — main.py never sees a network error. A failed fetch lands in `unreachable[]`; pass `--debug` to see why.
