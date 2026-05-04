# recon/booker.py

Recreation.gov session manager. Phase 1 of the auto-cart MVP — see [auto-cart-mvp-plan.md](auto-cart-mvp-plan.md).

[Source](../recon/booker.py) · Wiki home: [README.md](README.md)

## Public surface

```
python -m recon.booker login     # headed Chromium; human signs in; session saved
python -m recon.booker health    # loads saved session; verifies it still authenticates
```

Both subcommands emit a single JSON object to stdout and exit `0` on success, `1` on any failure shape. JSON keys: `status` plus context fields. Statuses:

| `status` | Meaning | Recommended action |
|---|---|---|
| `ok` | Session is valid | none |
| `missing` | No session file on disk | run `login` |
| `expired` | Session loaded but profile page redirected to login | run `login` |
| `not_logged_in` | After login attempt, profile page still redirects | retry `login`; check captcha was actually solved |
| `aborted` | User pressed Ctrl-C / EOF before pressing Enter | none |

## Session file

Path: `~/.campsitescout/rec_gov_session.json`. Created on first successful `login`, dir is `0700`, file is `0600`. Contents are Playwright `storage_state` (cookies + localStorage). No password is ever written here — Recreation.gov never sends the password back to the client after auth.

Delete the file (`rm ~/.campsitescout/rec_gov_session.json`) to force a re-login; nothing else depends on it.

## Login flow

1. Launches **headed** Chromium (you watch the window).
2. Navigates to `https://www.recreation.gov/log-in`.
3. Prompts you in the terminal. You type credentials, solve any captcha, click through to the logged-in homepage.
4. You press Enter in the terminal.
5. Booker navigates to `/account/profile` and inspects `page.url`. If it lands on the profile page, session is saved. If it bounced to `/log-in`, the session is treated as not-actually-authenticated and **not** saved.
6. Browser closes.

The "press Enter when you're done" approach is deliberate: hCaptcha can take 5s or 5min, and any URL-watching heuristic that tries to detect "login complete" automatically would either race the captcha or false-positive on intermediate redirects. Human in the loop is correct here.

## Health flow

1. Launches **headless** Chromium.
2. Loads `storage_state` from disk.
3. Navigates to `/account/profile` and inspects `page.url`.
4. If still on profile, status `ok`. If bounced to login, status `expired`.

Cheap probe — single page load, no clicks. Phase 4 wires this into a 6-hourly cron with a Telegram alert on `expired`.

## Design choices locked in this module

- **`storage_state(path=...)` over persistent context.** Single auditable JSON file, easy to delete, matches plan §4.2.
- **`/account/profile` as the session-live probe.** Per plan §9 open question — picked, validated to redirect to `/log-in` when unauthenticated, will revisit only if Akamai starts costing us trust signals on this URL specifically.
- **No retry inside the module.** A single attempt; the shell wrapper or cron handles retry policy. This keeps `login` blocking-on-human and `health` truly stateless.
- **JSON-on-stdout, status-strings.** Same pattern as [main.py](../main.py). Makes the Phase 4 Telegram wrapper trivial: read JSON, format the message, push.

## Not in this module yet

- **`cart`** — Phase 2. Next thing to build. Will share a small helper for "load context with storage_state" but otherwise live as its own subcommand with its own selectors, retry shape, and captcha-detection branch. UI-driven (navigate → wait → click) rather than an API-POST shortcut, so each cart attempt naturally produces fresh sensor cookies.
- **`heartbeat`** — warm-session background process. **Deferred** (2026-05-03). The original plan argued this was needed to keep Akamai sensor cookies fresh; on review, a periodic 30-min navigation cadence is itself a behavioral fingerprint that real Recreation.gov users don't produce, and the OSS prior art doesn't actually validate the heartbeat assumption. We start without it, gather data via cron-`health`, and revisit only if sessions expire faster than re-login can comfortably handle. Full reasoning: [auto-cart-mvp-plan.md §4.3](auto-cart-mvp-plan.md).

## Upstream / downstream

- **Called by**: human (during initial `login`); cron (`health` every 6 hrs once Phase 4 wires it).
- **Calls**: Playwright sync API → Chromium → Recreation.gov.
- **Reads/writes**: `~/.campsitescout/rec_gov_session.json`.
