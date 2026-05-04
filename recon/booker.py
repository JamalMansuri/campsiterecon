"""Recreation.gov session manager — Phase 1 of the auto-cart MVP.

Two subcommands so far:

  python -m recon.booker login    # headed Chromium; you sign in; session is dumped to disk
  python -m recon.booker health   # loads the saved session, verifies it still authenticates

Session state lives at ~/.campsitescout/rec_gov_session.json. Cookies + localStorage
only — no plaintext password is ever stored. Re-run `login` whenever `health` reports
expired (Phase 1 cron will alert via Telegram once Phase 4 wires it up).

Background and design rationale: docs/auto-cart-mvp-plan.md §4.2 (storage_state).
"""

import argparse
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SESSION_DIR  = Path.home() / ".campsitescout"
SESSION_FILE = SESSION_DIR / "rec_gov_session.json"

LOGIN_URL    = "https://www.recreation.gov/log-in"
PROFILE_URL  = "https://www.recreation.gov/account/profile"


def _ensure_session_dir() -> None:
    SESSION_DIR.mkdir(mode=0o700, exist_ok=True)


def _emit(payload: dict) -> None:
    print(json.dumps(payload))


def login() -> int:
    _ensure_session_dir()

    print("Opening Recreation.gov in a real Chromium window.", file=sys.stderr)
    print("Sign in (solve any captcha). When you can see the logged-in homepage,", file=sys.stderr)
    print("come back to this terminal and press Enter.", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page    = context.new_page()
        page.goto(LOGIN_URL)

        try:
            input()
        except (KeyboardInterrupt, EOFError):
            browser.close()
            _emit({"status": "aborted", "message": "User cancelled before pressing Enter."})
            return 1

        page.goto(PROFILE_URL, wait_until="domcontentloaded")
        final_url = page.url

        if "/log-in" in final_url or "/signin" in final_url:
            browser.close()
            _emit({
                "status": "not_logged_in",
                "message": "Profile page redirected to login. Session NOT saved.",
                "final_url": final_url,
            })
            return 1

        context.storage_state(path=str(SESSION_FILE))
        browser.close()

    os.chmod(SESSION_FILE, 0o600)
    _emit({
        "status": "ok",
        "session_file": str(SESSION_FILE),
        "size_bytes": SESSION_FILE.stat().st_size,
        "verified_url": final_url,
    })
    return 0


def health() -> int:
    if not SESSION_FILE.exists():
        _emit({
            "status": "missing",
            "message": f"No session at {SESSION_FILE}. Run: python -m recon.booker login",
        })
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(SESSION_FILE))
        page    = context.new_page()
        page.goto(PROFILE_URL, wait_until="domcontentloaded")
        final_url = page.url
        browser.close()

    if "/log-in" in final_url or "/signin" in final_url:
        _emit({
            "status": "expired",
            "message": "Session redirected to login. Run: python -m recon.booker login",
            "final_url": final_url,
        })
        return 1

    _emit({"status": "ok", "verified_url": final_url})
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="python -m recon.booker",
        description="Recreation.gov session manager (auto-cart Phase 1).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login",  help="Headed Chromium login; saves storage_state on success")
    sub.add_parser("health", help="Verify the saved session still authenticates")
    args = p.parse_args()

    if args.cmd == "login":
        sys.exit(login())
    if args.cmd == "health":
        sys.exit(health())


if __name__ == "__main__":
    main()
