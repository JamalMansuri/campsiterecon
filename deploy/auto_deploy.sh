#!/bin/bash
# Pull-based auto-deploy for the JamBot Mac mini. Run by the LaunchAgent in this folder
# every 15 minutes. Outbound HTTPS only — nothing on the home network is exposed.
#
#   1. git fetch; stop if origin/main has not moved past what is checked out.
#   2. Ask GitHub whether that commit's CI checks are all green; stop if pending or failed.
#   3. Run deploy_jambot.sh (saves local edits, fast-forwards, installs deps, runs the tests
#      and rolls back on failure, installs SKILL.md for OpenClaw).
#   4. Restart the OpenClaw gateway so it loads the new SKILL.md.
#
# Log: ~/.openclaw/logs/campsitescout-autodeploy.log
set -uo pipefail

REPO="${REPO:-$HOME/.openclaw/workspace/campsiterecon}"
GATEWAY_LABEL="${GATEWAY_LABEL:-ai.openclaw.gateway}"
export REPO
cd "$REPO" || { echo "$(date '+%F %T') repo not found at $REPO"; exit 1; }

log() { echo "$(date '+%F %T') $*"; }

# --- RIDB key health (before the "nothing new" exit, so a key rotated in 1Password is picked up
# within one tick). One cheap RIDB call; `op` is only spawned when the cached key is missing or
# rejected, and at most once an hour if 1Password itself is unreachable.
FETCH="$REPO/deploy/fetch_ridb_key.sh"; FAIL_MARK="$HOME/.campsitescout/ridb_key_fetch_failed"
if [ -x "$FETCH" ] && ! bash "$FETCH" --check; then
  if [ -n "$(find "$FAIL_MARK" -mmin -60 2>/dev/null)" ]; then
    :   # tried within the hour; stay quiet
  elif bash "$FETCH"; then
    rm -f "$FAIL_MARK"; log "RIDB key refreshed from 1Password"
  else
    mkdir -p "$(dirname "$FAIL_MARK")"; touch "$FAIL_MARK"
    log "WARNING: RIDB key is missing/rejected and 1Password fetch failed — --search and --verify will report HTTP 401 until fixed"
  fi
fi

git fetch --quiet origin main || { log "git fetch failed"; exit 1; }
LOCAL="$(git rev-parse HEAD)"; REMOTE="$(git rev-parse origin/main)"
[ "$LOCAL" = "$REMOTE" ] && exit 0                                  # nothing new; stay quiet
if ! git merge-base --is-ancestor "$LOCAL" "$REMOTE"; then
  log "HEAD $LOCAL is not an ancestor of origin/main $REMOTE — refusing to deploy; fix by hand"; exit 1
fi

# owner/repo from the origin URL (https or ssh form)
SLUG="$(git remote get-url origin | sed -E 's#(git@github\.com:|https://github\.com/)##; s#\.git$##')"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
STATE="$(curl -fsS -H 'Accept: application/vnd.github+json' "https://api.github.com/repos/$SLUG/commits/$REMOTE/check-runs" | "$PY" -c '
import json, sys
runs = json.load(sys.stdin).get("check_runs", [])
if not runs: print("none")
elif any(r["status"] != "completed" for r in runs): print("pending")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs): print("green")
else: print("red")' 2>/dev/null || echo "unknown")"

case "$STATE" in
  green)   log "deploying $REMOTE (CI green)";;
  pending) log "CI still running for $REMOTE; will retry"; exit 0;;
  none)    log "no CI checks reported yet for $REMOTE; will retry"; exit 0;;
  red)     log "CI FAILED for $REMOTE — not deploying"; exit 1;;
  *)       log "could not read CI status for $REMOTE ($STATE); will retry"; exit 0;;
esac

if bash "$REPO/deploy_jambot.sh"; then
  launchctl kickstart -k "gui/$(id -u)/$GATEWAY_LABEL" && log "gateway restarted" || log "WARNING: could not restart $GATEWAY_LABEL"
  log "deployed $(git rev-parse --short HEAD)"
else
  log "deploy_jambot.sh FAILED — still on $(git rev-parse --short HEAD)"; exit 1
fi
