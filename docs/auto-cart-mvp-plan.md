# Auto-Cart MVP — Implementation Plan

> **Status:** Planned. Not yet implemented.
> **Date:** 2026-04-22
> **Owner:** Jamal
> **Target host:** Mac mini (24/7)

## 1. Goal

Extend campsitescout from read-only availability scanning into **automated cart placement** on Recreation.gov. When the scanner detects a matching opening at a pre-configured target campsite, a Playwright-driven headless Chromium — running under the user's authenticated Rec.gov session — navigates to the site, clicks through the booking flow, and places the site in the user's cart within the 15-minute hold window. A Telegram push delivers the cart URL so the user can finish checkout manually.

This matches the functional behavior of the commercial iOS app **Campsite Tonight**.

---

## 2. How we got here

- The feature started as a trip-planner brainstorm (multi-stop itinerary → availability search per stop).
- User pivoted after learning about Campsite Tonight's auto-cart behavior, which provides materially more utility than multi-stop search — especially for heavily-booked campsites where cancellations appear for seconds before another user grabs them.
- Initial question was whether the public **RIDB API** (`ridb.recreation.gov`) exposes reservation endpoints. **Answer: no.** RIDB is read-only metadata. Recreation.gov's website and mobile app instead run on an undocumented internal API at `www.recreation.gov/api/*`, which is what the existing scanner already queries for availability GETs — and is also where the cart POST lives.

---

## 3. Market research summary

### 3.1 Existing open-source prior art (revised 2026-05-03 after deeper dive)

| Repo | Stars | Stack | What it does | Relevance to *current* rec.gov campsite cart |
|---|---|---|---|---|
| [juftin/camply](https://github.com/juftin/camply) | 584 | Python, pure API | Read-only availability scan + notify | Gold-standard reference for Rec.gov availability endpoints + status denylist. **No carting.** Borrowed patterns documented in [camply-attribution.md](camply-attribution.md). |
| [banool/recreation-gov-campsite-checker](https://github.com/banool/recreation-gov-campsite-checker) | 358 | Python, pure API | Availability scan only | `consecutive_nights` algorithm ported into [recon/windows.py](../recon/windows.py). See [banool-attribution.md](banool-attribution.md). |
| **[krosenfeld7/rec_gov_bot](https://github.com/krosenfeld7/rec_gov_bot)** | ~0 | Python + Selenium | **Carts current rec.gov campsites end-to-end** | **Highest-signal prior art.** Only OSS repo targeting current-DOM campsite cart flow (May 2023). Concrete selectors are our Phase 2 starting set — see §11. |
| [webrender/campsite-checker](https://github.com/webrender/campsite-checker) | 115 | Python 2 + Selenium + Firefox | Carted *legacy* rec.gov (pre-2018 ReserveAmerica DOM). Dormant since 2018. | **Useless.** URL templates use `campsiteDetails.do?contractCode=NRSO` — that DOM no longer exists. Originally listed here as "closest architectural match"; that was wrong. |
| [rmccrystal/recreation-gov-bot](https://github.com/rmccrystal/recreation-gov-bot) | 23 | Python + Selenium | State machine `LOGGED_OUT → RESERVING → PURCHASING` for **timed-entry tickets** (Glacier NP Iceberg Lake) | **Not campsites.** Targets `/timed-entry/{id}/ticket/{id}` — different DOM, different flow. State-machine pattern + `EC.any_of()` race-the-outcomes idea are still worth borrowing; selectors are not. |
| [congdnguyen/recreation-gov-reservation-bot](https://github.com/congdnguyen/recreation-gov-reservation-bot) | low | Python + Selenium | Near-duplicate of rmccrystal | No new signal. Skip. |
| [RookieITSec/recreation.gov-Reservation-help](https://github.com/RookieITSec/recreation.gov-Reservation-help) | 12 | AutoHotkey | Pre-loads N browser windows, pixel-clicks at coordinates at the lottery moment | Not real automation. The *strategy* is informative — pre-warm the page well before T-0 so Akamai sensor JS has finished its initial cycle. We adopt this. |
| [iamjaekim/recreation-gov-fetcher](https://github.com/iamjaekim/recreation-gov-fetcher) | low | Node, Docker | Recent (Apr 2026) availability monitor + Telegram. **No carting.** | Confirms the OSS gap: availability scrapers are still being built; nobody is shipping carting. |

**No working public Playwright-based Rec.gov auto-cart repo exists** as of May 2026. Confirmed via repeat searches. The OSS field is: notify-only scrapers in Python, krosenfeld7 (Selenium, current campsite DOM), and the rest are either timed-entry tickets or pre-2018 legacy.

### 3.1.1 Technical reverse-engineering references

These aren't repos to borrow code from — they're writeups that document specific facts about rec.gov / Akamai we'd otherwise have to rediscover ourselves:

| Source | What it gives us |
|---|---|
| [Edioff/akamai-analysis](https://github.com/Edioff/akamai-analysis) | Akamai Bot Manager v2 cookie lifecycle: `_abck` state-pattern reading (`~0~` = no sensor, `~-1~` = challenge required, valid hash = trusted), `bm_sz` session ID, `ak_bmsc` metadata. Sensor JS (~512KB), POSTs to `/_sec/cp_challenge/verify`, server-side validates timing realism + TLS fingerprint + signal consistency. **Directly actionable** for `booker.py health` enhancements. |
| Joyce Lin, ["How to book a campsite in Yosemite valley"](https://medium.com/swlh/how-to-book-a-campsite-in-yosemite-valley-fe18ad5d4d63) | Documents the actual cart endpoint: `POST /multi` with Bearer token + JSON body. **Critical finding: replaying the captured POST from Postman fails** even with the bearer token — server-side session correlation goes beyond auth header. This is the empirical evidence that we must stay in Playwright end-to-end and cannot drop to `requests` after login. |
| Farid Zakaria, ["Building a scraper for recreation.gov"](https://fzakaria.com/old_blog/2018-06-20-building-a-scraper-for-recreation-gov.html) | Methodology pointer (Charles MITM proxy + Wireshark) for capturing the cart POST today. Pre-rewrite content otherwise stale. |
| HN thread [21625160](https://news.ycombinator.com/item?id=21625160) | Bot-defense practitioner commentary: rate limits and captchas raise costs without preventing determined botters; matching legit user behavior + browser metrics + network reputation lets bots "squeak by." Multiple OSS bot operators self-identify in-thread. Useful for calibrating risk. |

### 3.2 Commercial services comparison

| Service | Auto-cart? | Stores Rec.gov credentials? |
|---|---|---|
| **Campsite Tonight** | **Yes** | **Yes** (per their privacy policy) |
| Schnerp | No — notify only | No |
| Campnab | No — notify only | No |

**Key finding:** Only Campsite Tonight claims auto-cart, and only Campsite Tonight stores user credentials. That is dispositive — auto-cart requires stored credentials plus a maintained authenticated session. No secret API.

### 3.3 How Campsite Tonight actually works (investigation)

Initial hypothesis: Campsite Tonight targets a separate, less-protected **mobile app API**, bypassing the Akamai Bot Manager protection on the web.

**Investigation result: hypothesis refuted.** Specifically:
- Recreation.gov does have an official mobile app (iOS `id1440487780`, Android `com.bah.r1smobile`, built by Booz Allen Hamilton).
- No public reverse-engineering evidence of a distinct `api.recreation.gov` or `mobile.recreation.gov` host. The mobile app almost certainly calls the same `www.recreation.gov/api/*` microservices.
- Every OSS project that books uses browser automation (Selenium/AutoHotkey) — nobody has cracked a pure-API booking path, even though the cart endpoint is publicly observable.
- Campsite Tonight's privacy policy explicitly collects Rec.gov credentials.

**What is actually happening (best inference):**
1. User hands over their Rec.gov credentials at signup.
2. Campsite Tonight runs a **persistent warm logged-in session** per user — likely a headless browser (Playwright/Puppeteer with stealth) holding valid Akamai sensor cookies.
3. When availability appears, they POST to `/api/cart/items` (or equivalent) from that warm session. The cart POST is protected *behaviorally* by Akamai Bot Manager, not unconditionally. A warm session with valid cookies, reasonable timing, and a residential-or-residential-proxy IP passes through.

**The critical asymmetry this exposes:**
- **Login is heavily captcha'd** — fresh logins from datacenter IPs reliably hit hCaptcha.
- **Availability GETs are lightly protected** — rate limiting only.
- **Cart POSTs are protected by behavioral scoring**, not by forcing captcha on every action. A session that's been "living" on the site for hours passes through; a brand-new session making a cart POST within seconds of login probably does not.

**Implication for this MVP:** Log in interactively once (human solves captcha). Persist cookies. ~~Keep the session warm with occasional low-cost navigations.~~ When the scanner fires, reuse the saved session for the cart click. The "warm with periodic navigations" piece is **deferred** — see §4.3 for the revised stance.

**Additional findings from the deeper dive (2026-05-03):**
- **Polling cadence ceiling:** Campsite Tonight publicly markets "every 18 seconds" on popular campgrounds. That's the upper bound rec.gov tolerates from a paid commercial product. Our cancellation-catching use case should sit well under this — 60–90s is plenty and gives a wider behavioral margin.
- **The cart endpoint is `POST /multi`** (per Joyce Lin's writeup), not `/api/cart/items` as previously guessed. Body is JSON, requires Bearer token in `authorization` header.
- **API replay outside the browser fails** even with valid bearer token. Server-side session correlation enforces the request to come from the same browser context that fetched the page. This is *evidence-grade* support for staying in Playwright end-to-end — no `requests`-based shortcuts after login.

---

## 4. Design decisions & rationale

### 4.1 Playwright over Selenium

Selenium dominates OSS prior art, but Playwright is the better choice in 2026:
- **Better stealth defaults out of the box** — fewer obvious automation fingerprints than Selenium/WebDriver.
- **`storage_state` is a first-class primitive** for session persistence (cookies + localStorage to a JSON file, reloadable across runs).
- **Chrome DevTools Protocol** instead of WebDriver — faster, fewer detection tells.
- **Auto-waiting** eliminates most flaky-selector bugs.
- **`codegen`** records interactions and emits code — fast path to initial selector coverage.
- Active development, better docs, modern API.

### 4.2 `storage_state` session persistence

Login is the heavily-captcha'd step. Once solved, the session (cookies + localStorage) can be dumped to disk and reused for weeks. This is Playwright's documented session-persistence pattern, not a workaround. Re-login only when the session legitimately expires.

Session file: `~/.campsitescout/rec_gov_session.json`. Protected by macOS filesystem ACLs under the user's home directory. Rec.gov password itself is not stored — only post-login cookies.

### 4.3 Warm-session maintenance — DEFERRED pending evidence (revised 2026-05-03)

**Original plan:** run a lightweight background heartbeat every ~30 min to keep Akamai sensor cookies fresh and the session looking "lived in."

**Revised stance:** deferred until empirical data justifies it. Two competing arguments:

- *For heartbeat:* `_abck` / `bm_sz` cookies have TTLs and are refreshed by the in-page Akamai sensor JS. A session sleeping for days wakes up with stale cookies and gets re-challenged on its next request. Periodic re-engagement keeps them fresh.
- *Against heartbeat:* a real Recreation.gov user is bursty — plans a trip, browses for an hour, vanishes for weeks. A session that pings the site every 30 min for 14 days straight produces a periodic-request fingerprint that is itself a textbook bot signal. We could be lowering our trust score by trying to raise it.

**Decision:** start without heartbeat. Use a UI-driven cart flow in Phase 2 (navigate → wait → click → click) so each cart attempt naturally looks like a fresh session doing the actual booking flow a human would do — that gives sensor JS time to attach cookies organically per attempt. Run `booker.py health` from cron (Phase 4) to detect session expiry and alert via Telegram so the user can re-login. Re-login validated as captcha-free from a residential IP, so this is cheap.

**Re-evaluate if:** cron-`health` shows sessions expiring faster than ~24 hrs, or Phase 2 cart attempts get unexpectedly captcha-challenged on a fresh-headed-then-headless session. At that point we'd have data justifying either heartbeat or some narrower cookie-refresh pattern.

OSS prior art doesn't actually validate the heartbeat assumption — camply and banool are read-only, webrender/campsite-checker runs on a schedule with no warm session, and Campsite Tonight's behavior was inferred not observed. We're not contradicting prior art by deferring; we're just declining to add complexity we can't yet justify.

### 4.4 Sync Playwright API over async

The existing codebase is entirely synchronous (`urllib`, no `asyncio`). Sync Playwright integrates cleanly. Async would unlock parallel multi-target carting, which is out of scope for MVP.

### 4.5 Shell orchestration over Python invocation

Matches the existing Mode 3 pattern (`main.py` emits JSON → `jq` gate → `osascript`/Telegram). The booker will be a separate CLI entrypoint invoked by the shell wrapper, not called from Python. Benefits:
- Scanner stays pure/read-only.
- Booker is testable independently.
- Shell layer is the natural home for the `jq`-match → invoke-booker pipe.

### 4.6 Headless Chromium on the Mac mini

- Mac mini is 24/7 and uses a residential home IP — both big trust factors with Akamai.
- No need for residential proxies, VPNs, or cloud hosting.
- Single-user install (one Chromium, one session, one target at a time) is exactly the scale commercial services operate at for individual users. Well inside Rec.gov's stated enforcement bar of "large-scale bot attacks or bots seeking to capture multiple reservations."

---

## 5. Critical finding: parser discards `campsite_id`

Investigation of [recon/parser.py:29](../recon/parser.py) revealed that `_parse_campground()` iterates `raw["campsites"].values()` and **flattens all per-site availability into a facility-level `available_dates` set**. The `campsite_id` is discarded.

**Consequence for booker:** The booker needs the specific `campsite_id` to click the correct site in the UI grid — "facility has availability on date X" is not enough.

**Fix:** Extend [CampsiteResult](../recon/models.py) with a new field capturing per-site detail, e.g.:
```python
sites_by_id: dict[str, list[str]]  # {campsite_id: [available_dates]}
```
Update [_parse_campground](../recon/parser.py) to populate it alongside the existing flattened `available_dates` (which remains for backward compatibility with the existing JSON consumers — the new field is additive). This is Phase 0 work.

---

## 6. MVP scope

### In scope

- One-time interactive login → `storage_state.json`.
- Session-health checker with Telegram "re-auth needed" alert.
- Warm-session heartbeat (benign navigation every ~30 min).
- `booker.py cart --facility X --site Y --start DATE --nights N` — core cart flow.
- hCaptcha detection → screenshot to disk + Telegram push with cart URL.
- `targets.json` matching policy (which facilities/sites/dates to auto-cart on).
- Shell wiring: scanner → match → booker → Telegram alert.
- Parser change to preserve `campsite_id`.

### Out of scope (future work)

- Auto-solving captchas.
- Waiting-room / queue-system handling (big-release days).
- Payment completion (user finishes via the cart URL).
- Multiple concurrent cart targets.
- Cross-campground search / flexible-date matching logic.
- Cart success analytics / history.
- Retries beyond first attempt.
- Trip planner (deferred indefinitely — lower utility than auto-cart).

---

## 7. Implementation phases

### Phase 0 — Foundations (~2 hrs)

- ~~Add `playwright>=1.40` to `requirements.txt`.~~ (deferred to Phase 1 start)
- ~~`playwright install chromium`.~~ (deferred to Phase 1 start)
- ✅ **Added `pydantic>=2.5` to `requirements.txt`** — boundary validation for the Rec.gov response.
- ✅ **Rewrote [recon/models.py](../recon/models.py) as Pydantic models.** Added `RawCampgroundResponse` + `RawSiteAvailability` for boundary validation, and `is_available()` denylist helper.
- ✅ **Extended [CampsiteResult](../recon/models.py) with `sites_by_id: dict[str, list[str]]`.**
- ✅ **Updated [_parse_campground](../recon/parser.py)** to validate via `RawCampgroundResponse.model_validate(raw)`, preserve `campsite_id` as the outer key, and populate `sites_by_id`.
- ✅ **Switched [recon/parser.py](../recon/parser.py) and [recon/search.py](../recon/search.py)** from `_OPEN = {"Available", "Open"}` allowlist to `is_available()` denylist. Closes a real bug — `"Open"` was incorrectly counted as bookable.
- ✅ **Updated [main.py](../main.py)** to serialize via `model_dump(mode="json")` instead of `dataclasses.asdict()`.
- ✅ **Smoke-tested** end-to-end against `--location pinnacles`: `sites_by_id` populated with real campsite IDs, JSON shape unchanged for existing consumers.
- ✅ **Wrote [docs/camply-attribution.md](camply-attribution.md)** crediting camply for the response-shape pattern and unavailable-status denylist (no runtime dependency taken).
- ✅ **Ported `consecutive_nights` from banool/recreation-gov-campsite-checker** into a new [recon/windows.py](../recon/windows.py). Function generalizes to arbitrary `nights` (the matcher in Phase 3 will call it with `targets.json`-supplied values). Refactored [recon/parser.py](../recon/parser.py) and [recon/search.py](../recon/search.py) to use it instead of the prior bespoke `_is_contiguous` / `_has_contiguous` helpers — both `contiguous` flags now share one primitive.
- ✅ **Added `CampsiteResult.windows_by_site_id`** — `{campsite_id: [(start_iso, checkout_iso), ...]}` for viable 2-night stays per campsite. Empty for sites with only single-night availability. Smoke-tested against `--location big_sur --date 2026-06-12` (Plaskett Creek), got correct `[['2026-06-12','2026-06-14'], ['2026-06-13','2026-06-15']]` shape from a 3-night run. Additive — existing JSON consumers unaffected.
- ✅ **Wrote [docs/banool-attribution.md](banool-attribution.md)** and [docs/windows.md](windows.md) wiki page.

### Phase 1 — Session management (~1 day)

**Do this completely before Phase 2.** If session handling isn't reliable, nothing downstream matters.

- ✅ **`recon/booker.py login`** — validated live 2026-05-03 against Jamal's account from the residential IP. Headed Chromium, human logs in, Playwright dumps `storage_state` to `~/.campsitescout/rec_gov_session.json` (10 KB on first save). Verifies the saved session by hitting `/account/profile` and checking the URL didn't bounce back to `/log-in`. **No captcha served** on the fresh login — confirms the §3.3 trust hypothesis for residential-IP auto-cart.
- ✅ **`recon/booker.py health`** — validated live 2026-05-03. Fresh headless context loads the saved `storage_state` and gets authenticated access to `/account/profile` without re-login. Emits JSON status (`ok` / `expired` / `missing` / `not_logged_in`). Exit 0/1 for cron-friendliness.
- 🟡 **`recon/booker.py heartbeat`** — **deferred (2026-05-03)**. See §4.3 for the revised rationale. Phase 1 is treated as closed without it; Phase 2 builds a UI-driven cart flow that lets sensor cookies attach organically per attempt rather than via a periodic pre-warmer. Will revisit only if cron-`health` data shows sessions don't last long enough on their own.
- ⏳ Cron: `booker.py health` every 6 hrs (alert wiring lands in Phase 4). Doubles as the empirical probe for "how long does a saved session actually stay valid" — we need that data before reconsidering heartbeat.

Open question 3 from §9 settled: `/account/profile` is the session-live probe. Validates via URL inspection — unauthenticated requests redirect to `/log-in`. Will revisit only if Akamai trust scoring penalizes that URL specifically.

**Phase 1 status:** closed pending heartbeat reconsideration. `login` + `health` validated live 2026-05-03; that's enough surface for Phase 2 to build on.

### Phase 2 — Core booker (~2–3 days, the meaty phase)

- `recon/booker.py cart --facility X --site Y --start DATE --nights N` — sync Playwright, headless Chromium, loads session, navigates to `/camping/campgrounds/{id}/availability`, selects date range, clicks the specific site, clicks Add to Cart, reads back the cart URL + 15-min timer.
- Draft selectors with `playwright codegen https://www.recreation.gov/camping/campgrounds/{known_facility_id}`.
- Harden with `get_by_role` / `get_by_text` / ARIA lookups, not raw CSS paths, to survive UI tweaks.
- **hCaptcha detection**: if a captcha iframe appears on the booking page, take a full-page screenshot to `/tmp/campsitescout-captcha-{timestamp}.png` and emit JSON:
  ```json
  {"status":"captcha","screenshot":"/tmp/...","cart_url":"...","facility":"...","site":"..."}
  ```
  Shell wrapper pushes both the image and the URL to Telegram so user can solve in a browser.
- Structured output for all exit paths: `success`, `captcha`, `already_reserved`, `session_expired`, `ui_changed`, `error`.

### Phase 3 — Targets config + orchestration (~half day)

- `targets.json` schema:
  ```json
  {
    "auto_cart_rules": [
      {
        "facility_id": "234061",
        "site_ids": ["234061_a", "234061_b"],
        "date_window": {"start": "2026-05-01", "end": "2026-05-31"},
        "nights": 2,
        "priority": 1
      }
    ]
  }
  ```
  (`site_ids` optional — if omitted, any site in the facility.)
- Thin matcher (could be a shell script using `jq`, or a small Python helper) that reads scanner JSON + `targets.json` → emits `booker cart ...` invocations. For arbitrary `nights` values, the matcher calls [`recon/windows.consecutive_nights`](../recon/windows.py) directly against `sites_by_id` — the default-2 case is already pre-computed in `windows_by_site_id`.

### Phase 4 — Shell wiring + Telegram (~half day)

- Update Mode 3 wrapper: scanner → `jq` match against targets → `booker.py cart ...` → Telegram with result.
- Three Telegram alert shapes:
  - **Success**: cart URL, facility/site/dates, 15-min countdown.
  - **Captcha**: screenshot attachment + cart URL.
  - **Failure**: error code + facility context.

### Phase 5 — Hardening (~half day)

- `--dry-run` flag on booker: navigate + find site, but don't click final Add to Cart. Returns "would-have-clicked" confirmation for testing.
- First live test on a low-stakes site with known availability.
- `--verbose` flag for debugging click-flow regressions.
- Document the re-login runbook in `docs/booker.md`.

### Total effort

~4–5 focused days, ~1 week calendar.

---

## 8. Decisions locked

1. **Stack:** Python + Playwright (sync API) + Chromium, headless for cart ops, headed for initial login.
2. **Session persistence:** Playwright `storage_state` at `~/.campsitescout/rec_gov_session.json`. No plaintext password storage.
3. **Host:** Mac mini at home. 24/7, residential IP. No cloud, no VPS, no proxies.
4. **Captcha strategy:** Detect, screenshot, Telegram push the image + cart URL. Human solves. No auto-solve.
5. **Orchestration:** Shell wrapper invokes booker. Scanner stays read-only.
6. **Session warming:** ~~Continuous background heartbeat every ~30 min.~~ Revised 2026-05-03 — no heartbeat. Sessions stay dormant; cart flow is UI-driven per attempt; cron-`health` detects expiry. Full reasoning in §4.3.
7. **Targets config:** Separate `targets.json`, not extending [recon/config.py](../recon/config.py) (different concerns, different lifecycles).
8. **Re-auth UX (MVP):** Manual — user SSHes into Mac mini and runs `booker.py login`. Remote-trigger is future work.
9. **Concurrency:** One active cart at a time. Rec.gov's 15-min hold is per-account-exclusive anyway.
10. **Parser change:** Extend `CampsiteResult` additively; do not break existing JSON consumers.

---

## 9. Open questions

1. ~~**Exact Rec.gov cart URL/flow:**~~ Substantially answered 2026-05-03 by the krosenfeld7 deep dive — concrete selectors lifted into §11. Cart endpoint is `POST /multi`. Still need `playwright codegen` against a live booking to confirm selectors stayed valid since krosenfeld7's last commit (May 2023) and to harden per-facility quirks (date-grid layout varies). Treat the §11 selectors as starting set, not ground truth.
2. **Does the cart POST return a clean success vs. "already taken" signal we can parse?** Joyce Lin's writeup documents the endpoint exists but not the response shape. krosenfeld7 doesn't parse — just trusts the click and detaches the browser. Phase 2 spike with `page.expect_response()` against `/multi` will tell us. Fallback if response is opaque: race success-element vs failure-toast in DOM (the `EC.any_of()` pattern from rmccrystal).
3. ~~**Is `/account/profile` the right "is-session-live" endpoint?**~~ Settled 2026-05-03 — yes. Live test: unauthenticated requests redirect to `/log-in`; saved-session requests reach the profile page. Will revisit only if a future Akamai change penalizes that URL.
4. **Telegram bot reuse:** Does the existing OpenClaw Telegram integration expose a bot token we can reuse, or do we provision a new one? Needs a 10-min check of OpenClaw config.

---

## 10. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Session goes stale; next match is missed | Unknown — needs empirical data; previously rated High based on heartbeat-required assumption | Cron `booker.py health` every 6 hrs + Telegram "re-auth needed" alert (Phase 4). Re-login is captcha-free from the residential IP, so the cost of a stale session is one human action, not a missed match. Heartbeat deferred — see §4.3. |
| `storage_state` file leaks (filesystem access) | Low (single-user Mac mini) | macOS user-home ACLs + `chmod 600` (already enforced by `booker.py login`). Not stored in the git repo. |
| Rec.gov changes login flow / UI, breaking selectors | Medium | Use ARIA selectors, not CSS paths. `--dry-run` for fast regression testing. Expect quarterly maintenance. |
| hCaptcha fires on cart action specifically | Low (cart is behavior-protected, not unconditionally captcha'd) | Screenshot + Telegram fallback. Users finish manually. |
| Rec.gov account banned for automation | Low (enforcement targets commercial resale, not single-user) | Keep scale tiny. Residential IP. Human-like timing (small jitter). Don't run during well-known drop-day releases (use for cancellation-catching only). |
| Playwright selector flakiness | Medium | `get_by_role`/`get_by_text` over CSS. Retry budget of 1 on transient errors. |
| Cart flow varies between campground types (standard vs permit) | Medium | Phase 2 covers standard campgrounds only. Permit flows deferred to a v2. |

---

## 11. Phase 2 design notes (added 2026-05-03)

Captured from the prior-art deep dive. These are the patterns Phase 2 should adopt or avoid; reference material when writing `booker.py cart`.

### 11.1 Concrete selectors — starting set from krosenfeld7

These target the current rec.gov campsite cart flow (May 2023). Treat as **starting set**, not ground truth — re-verify with `playwright codegen https://www.recreation.gov/camping/campgrounds/233115` (Plaskett Creek, known to have multi-night availability) before committing to them.

| Step | Selector | Notes |
|---|---|---|
| Login link | `#ga-global-nav-log-in-link` | Same selector confirmed by both rmccrystal and krosenfeld7 — high stability. |
| Login email | `#email` | |
| Login password | `#rec-acct-sign-in-password` | |
| Login submit | `//button[contains(@class, 'rec-acct-sign-in-btn') and (@type='submit')]` | |
| Modal close (post-load popups) | `//button[@aria-label='Close modal']` | Campground page often opens with a modal. |
| Start-date picker | `#campground-start-date-calendar` | |
| End-date picker | `#campground-end-date-calendar` | "Finicky" per krosenfeld7 — loop until `value` is non-empty. |
| Date entry pattern | Ctrl-A → type new date → Tab | Plain `.fill()` may not stick. |
| In-page refresh button | `//span[contains(text(), 'Refresh Table')]` → walk to parent `<button>` | **Use this to re-poll, never `page.reload()`.** Full reload re-triggers Akamai sensor cycle and burns validation state. |
| Filter: site types | `#filter-menu-site-types` | |
| Filter: equipment | `#filter-menu-equipment` | Generic dropdown handler clicks dropdown → finds children with class `filter-menu-checkbox-item` → clicks matching checkbox. |
| Available date cell | `class="available"` → child `class="rec-availability-date"` | Read `aria-label` to verify date string before clicking. |
| Date cell click | Hover → click (not direct click) | Defeats invisible overlay elements. Playwright equivalent: `locator(...).hover()` then `.click()`, or `.click(force=True)`. |
| Cart button (campsites) | `//span[contains(text(), 'Add to Cart')]` → parent `<button>` | Branch on reservation type. |
| Cart button (permits) | `//span[contains(text(), 'Book Now')]` → parent `<button>` | Different literal text. |

### 11.2 Patterns to borrow

1. **In-page "Refresh Table" loop, never full-page reload.** This is the single most important pattern — preserves Akamai sensor validation across polling cycles.
2. **Pre-warm the cart page well before T-0.** Land on the campground page, sleep ~5–10s for sensor JS to complete its initial collection, *then* enter the polling loop. Cold-loading at the lottery moment fights Akamai validation timing.
3. **Race two outcomes after the cart click.** Wait for either a success indicator OR a "site unavailable" / "already taken" toast — whichever fires first. Adapted from rmccrystal's `EC.any_of(success_clickable, failure_present)`. In Playwright: `page.expect_response()` on `/multi` paired with a `locator.wait_for()` for known DOM error states.
4. **Stay in Playwright end-to-end for the cart click.** Joyce Lin's finding that POST `/multi` cannot be replayed outside the browser context (even with valid bearer token) is the empirical evidence. No `requests`-based shortcuts.
5. **Branch on reservation type** for the cart-button selector. Campsites = "Add to Cart"; permits = "Book Now". Read `Camp.permit_id` from [config.py](../recon/config.py) and pick.
6. **Polling cadence ceiling = 18s** (Campsite Tonight's commercial pace). Sit well under — 60–90s for cancellation-catching. Wider behavioral margin, no real downside for our use case.
7. **Verify date selection by re-reading `aria-label` on the calendar's `.start` and `.end` classes** before clicking Add to Cart. Catches the "selected date didn't actually stick" failure mode silently.
8. **Always read selector targets via `aria-label` or text content, never DOM index or absolute XPath.** Survives cosmetic UI tweaks. (rmccrystal's `/html/body/div[6]/...` is the anti-pattern.)
9. **Detach browser, hand to human at checkout.** Universal design across all prior art including paid Campsite Tonight. Don't try to automate payment.

### 11.3 Patterns to avoid

1. **Don't multi-thread N parallel browsers from one IP.** rmccrystal recommends 4; that's residential-IP suicide and accelerates account-ban risk. One browser, one account, one IP.
2. **Don't full-page reload between polls.** Re-triggers Akamai sensor JS and burns validation state. Use the in-page "Refresh Table" button.
3. **Don't replay POST `/multi` from `requests` or `urllib`.** Joyce Lin proved it fails. Stay in Playwright.
4. **Don't rely on `playwright-stealth` as primary defense.** Detectable against Akamai-tier protection per Scrapfly/ZenRows consensus. Our real Chromium + residential IP + real session does the actual work; stealth-plugin probably doesn't hurt but don't lean on it.
5. **Don't auto-solve hCaptcha.** Every OSS bot defers; our screenshot-to-Telegram-for-human plan matches the de facto standard. Auto-solving is a different project.
6. **Don't trust absolute XPaths** (`/html/body/div[6]/...`). Attribute-based locators only.
7. **Don't run during well-known drop-day releases.** Concentrated bot-detection scrutiny; our value prop is cancellation-catching, not lottery-day racing. Skip 8 AM ET on release Wednesdays.

### 11.4 `_abck` cookie state — candidate health-check enhancement

Edioff/akamai-analysis documents the `_abck` cookie value patterns:
- `~0~` → no sensor data submitted yet (fresh session)
- `~-1~` → server is requesting a challenge (sensor data rejected)
- `~0~-1~` → sensor received, not yet validated
- valid hash pattern → trusted

Current `booker.py health` checks only that `/account/profile` doesn't redirect to `/log-in`. A stronger check would also parse `_abck` and alarm on `~0~` or `~-1~` patterns — catches "session present but Akamai unhappy" before a cart attempt would fail for opaque reasons. ~10 LOC enhancement, deferred until Phase 2 needs it.

### 11.5 What we still don't know

- **POST `/multi` response shape on success / "already taken" / session expired.** Phase 2 spike with `page.expect_response("**/multi")` will surface this. Until then, plan for DOM-state-based success detection as fallback.
- **Whether krosenfeld7's selectors survived to May 2026.** The repo's last commit was May 2023. UI redesigns are common; expect at least minor selector drift. `playwright codegen` against a live booking is the empirical check.
- **Real session expiry duration.** We saved a session today and `health` returned `ok`. We don't yet know if that session lasts 6 hours or 6 weeks. Cron-`health` data over the next 1–2 weeks will tell us, and that's what gates the heartbeat-revisit decision (§4.3).

---

## 12. References

### Internal
- [recon/parser.py](../recon/parser.py) — the file with the `campsite_id` loss (fixed in Phase 0).
- [recon/models.py](../recon/models.py) — where `CampsiteResult`, `sites_by_id`, and `windows_by_site_id` live.
- [recon/windows.py](../recon/windows.py) — `consecutive_nights` primitive the matcher will call.
- [recon/api_client.py](../recon/api_client.py) — existing Rec.gov client.
- [main.py](../main.py) — mode dispatcher; a `--plan`-like auto-cart mode *could* live here, but current plan keeps booker as a separate entrypoint.
- [SKILL.md](../SKILL.md) — Mode 3 shell orchestration pattern to extend.
- [docs/camply-attribution.md](camply-attribution.md), [docs/banool-attribution.md](banool-attribution.md) — prior-art credits for code patterns adopted into the repo.

### External — most useful repos
- [krosenfeld7/rec_gov_bot](https://github.com/krosenfeld7/rec_gov_bot) — **Phase 2 selector starting set.** Only OSS repo carting current-DOM rec.gov campsites.
- [juftin/camply](https://github.com/juftin/camply) — API reference for availability endpoints + status denylist (already borrowed).
- [banool/recreation-gov-campsite-checker](https://github.com/banool/recreation-gov-campsite-checker) — `consecutive_nights` algorithm (already ported).
- [rmccrystal/recreation-gov-bot](https://github.com/rmccrystal/recreation-gov-bot) — state-machine + `EC.any_of()` race-the-outcomes pattern. Targets timed-entry tickets, not campsites — selectors don't apply.
- ~~[webrender/campsite-checker](https://github.com/webrender/campsite-checker)~~ — pre-2018 legacy DOM. Useless for current rec.gov.

### External — investigation sources
- [Edioff/akamai-analysis](https://github.com/Edioff/akamai-analysis) — Akamai Bot Manager v2 cookie lifecycle, sensor JS internals.
- [Joyce Lin, "How to book a campsite in Yosemite valley"](https://medium.com/swlh/how-to-book-a-campsite-in-yosemite-valley-fe18ad5d4d63) — `POST /multi` cart endpoint + the empirical proof that API replay fails outside the browser context.
- [Farid Zakaria, "Building a scraper for recreation.gov"](https://fzakaria.com/old_blog/2018-06-20-building-a-scraper-for-recreation-gov.html) — methodology pointer (Charles MITM for capturing the cart POST).
- [HN thread 21625160](https://news.ycombinator.com/item?id=21625160) — bot-defense practitioner commentary; multiple operators self-identify.
- [Campsite Tonight privacy policy](https://www.campsitetonight.app/privacy-policy) — confirms credential storage; marketing pages confirm 18s polling cadence.
- [Schnerp FAQ](https://www.schnerp.com/faq) — confirms notify-only (no cart).
- [Booz Allen Recreation.gov writeup](https://www.boozallen.com/s/insight/thought-leadership/reinventing-the-recreation-gov-customer-experience.html) — architectural context.
- [Recreation.gov iOS app](https://apps.apple.com/us/app/recreation-gov/id1440487780).
- [RIDB API docs](https://ridb.recreation.gov/docs) — read-only, no booking endpoints.

### Tooling
- [Playwright Python docs](https://playwright.dev/python/)
- [Playwright `storage_state`](https://playwright.dev/python/docs/auth#reuse-signed-in-state)
- [Playwright `codegen`](https://playwright.dev/python/docs/codegen)
