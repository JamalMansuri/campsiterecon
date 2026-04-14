# main.py

CLI entry point. Loads the API key, dispatches to one of two modes, prints JSON to stdout.

[Source](../main.py) · Wiki home: [README.md](README.md)

## Public surface

```
python main.py                                                  # weekend mode, all presets
python main.py --location point_reyes                           # weekend mode, one preset
python main.py --location big_sur --date 2026-05-01             # weekend mode, specific Friday
python main.py --search "Yosemite" --start 2026-07-03 --end 2026-07-05   # search mode
```

Output is JSON on stdout. Exit `1` on a missing API key with a JSON error object explaining how to provide one.

## Mode dispatch

`--search` is the discriminator. If present, search mode runs and exits. Otherwise, weekend mode runs across either all presets or the one named in `--location`.

```
args.search ──► search.search()         ──► SearchReport  ──► JSON
        else ──► _run_location() per loc ──► LocationReport ──► JSON array
```

Weekend mode also calls [weather.md](weather.md) per location. Search mode does not — see [search.md](search.md) for why.

## API key resolution

`_get_api_key()` walks four sources in order and returns the first non-empty match:

1. **macOS Keychain** — `security find-generic-password -s recreation-gov-api`. Only consulted on `darwin`.
2. **Windows Credential Manager** — `advapi32.CredReadW("recreation-gov-api")` via `ctypes`. Only on `win32`. No external deps.
3. **Env var** — `RIDB_API_KEY` or `REC_GOV_API_KEY` (either name).
4. **Hardcoded constant** — `_HARDCODED_API_KEY_FALLBACK` at the top of [main.py](../main.py). Empty by default. Last-resort for non-developers.

Empty string from all four → JSON error to stdout, exit 1. The error message lists all four options. [../SKILL.md](../SKILL.md) has the LLM-facing setup walkthrough.

## Upstream / downstream

- **Called by**: OpenClaw skill (per [SKILL.md](../SKILL.md)), or a cron job from Mode 3.
- **Calls**: [api_client.md](api_client.md) (constructs `RecGovClient`), [config.md](config.md) (presets), [availability.md](availability.md), [parser.md](parser.md), [search.md](search.md), [weather.md](weather.md).
- **Data shapes**: emits `LocationReport[]` (weekend) or `SearchReport` (search). Both defined in [models.md](models.md).

## Gotchas

- Friday for "this weekend" is computed by `_upcoming_friday()` — if today is Friday, it returns *next* Friday, not today. Intentional: the user means the weekend that hasn't started yet.
- The `_HARDCODED_API_KEY_FALLBACK` constant is checked **last**, not first, so an accidentally-committed value won't override a properly stored Keychain key.
- All exceptions from external HTTP are swallowed inside [api_client.md](api_client.md) — main.py never sees a network error. A failed fetch just produces empty results.
