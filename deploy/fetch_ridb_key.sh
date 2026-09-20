#!/bin/bash
# Fetch the RIDB API key from 1Password ON THE MAC MINI and cache it where main.py reads it
# (~/.campsitescout/ridb_api_key, mode 600). 1Password is the source of truth; rotating the key
# there is all you ever do — deploy/auto_deploy.sh runs `--check` every 15 minutes and re-fetches
# when RIDB starts rejecting the cached key.
#
#   fetch_ridb_key.sh            fetch from 1Password, validate against RIDB, write the cache
#   fetch_ridb_key.sh --check    exit 0 if the cached key still gets HTTP 200 from RIDB, else 1
#
# Why a cache instead of calling `op` from main.py: on this box `op` hangs instead of failing, a
# cold read has taken ~60 s, and leaked `op daemon` processes caused the 2026 gateway outage. So
# `op` is kept off the request path and wrapped the way openclaw-gateway-wrapper.sh wraps it:
# full path, OP_CACHE=false, stdout to a file (never a pipe), a kill -9 watchdog (op is a Go binary
# and ignores SIGALRM), and daemon reaping on the timeout path.
# `op read` only works from a logged-in GUI (Aqua) session — i.e. from the LaunchAgent or a
# Terminal on the Mini, NOT over bare SSH.
#
# The key is never printed, never passed in argv, and never logged.
set -uo pipefail

OP_BIN="${OP_BIN:-/opt/homebrew/bin/op}"
OP_ENV_HELPER="${OP_ENV_HELPER:-$HOME/.openclaw/workspace/.1password.sh}"
# Tried in order; the first one RIDB accepts wins (the vault has two near-duplicate items).
OP_REFS="${OP_REFS:-op://openclaw_macmini/recreation_gov_api/credential op://openclaw_macmini/recreation_gov_api_key/credential op://openclaw_macmini/recreation_gov_api/password}"
KEY_FILE="${CAMPSITESCOUT_KEY_FILE:-$HOME/.campsitescout/ridb_api_key}"
OP_TIMEOUT="${OP_TIMEOUT:-120}"
RIDB_CHECK_URL="${RIDB_CHECK_URL:-https://ridb.recreation.gov/api/v1/facilities/233359}"

log() { echo "$(date '+%F %T') fetch_ridb_key: $*" >&2; }

ridb_status() {   # $1 = key. Sent as a header via curl's stdin config so it never appears in argv/ps.
  printf 'header = "apikey: %s"\n' "$1" | curl -s -o /dev/null -w '%{http_code}' --max-time 20 --config - "$RIDB_CHECK_URL" 2>/dev/null || echo "000"
}

reap_op_daemons() {   # exact-match pattern on purpose: a loose pkill -f matches this very pipeline
  local pids
  pids="$(ps -ax -o pid=,command= | grep -E '^[[:space:]]*[0-9]+ op daemon --background$' | awk '{print $1}')"
  [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null
  return 0
}

if [ "${1:-}" = "--check" ]; then
  [ -s "$KEY_FILE" ] || exit 1
  [ "$(ridb_status "$(tr -d '\r\n' < "$KEY_FILE")")" = "200" ]
  exit $?
fi

if [ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ] && [ -f "$OP_ENV_HELPER" ]; then
  # shellcheck disable=SC1090
  . "$OP_ENV_HELPER"
fi
if [ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ]; then   # the helper fails open: it exports an empty token silently
  log "no OP_SERVICE_ACCOUNT_TOKEN — $OP_ENV_HELPER exported nothing (login keychain locked, or not a GUI session?)"
  exit 2
fi
export OP_SERVICE_ACCOUNT_TOKEN
[ -x "$OP_BIN" ] || { log "1Password CLI not found at $OP_BIN"; exit 2; }

TMP="$(mktemp "${TMPDIR:-/tmp}/ridbkey.XXXXXX")" || exit 2
chmod 600 "$TMP"
trap 'rm -f "$TMP"' EXIT

for ref in $OP_REFS; do
  : > "$TMP"
  OP_CACHE=false "$OP_BIN" read "$ref" > "$TMP" 2>/dev/null &
  pid=$!; waited=0; timed_out=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge "$OP_TIMEOUT" ]; then
      kill -9 "$pid" 2>/dev/null; reap_op_daemons; timed_out=1
      log "op read hung for ${OP_TIMEOUT}s on $ref — killed (see openclaw-config GOTCHA 3: check for a 0-byte op-daemon.pid)"
      break
    fi
    sleep 1; waited=$((waited + 1))
  done
  wait "$pid" 2>/dev/null
  [ "$timed_out" = 1 ] && exit 3            # a hang is not item-specific; don't spawn more op processes
  key="$(tr -d '\r\n' < "$TMP")"
  if [ -z "$key" ]; then log "$ref: nothing returned"; continue; fi
  status="$(ridb_status "$key")"
  if [ "$status" = "200" ]; then
    umask 077
    mkdir -p "$(dirname "$KEY_FILE")" && chmod 700 "$(dirname "$KEY_FILE")"
    printf '%s' "$key" > "$KEY_FILE.tmp" && mv -f "$KEY_FILE.tmp" "$KEY_FILE"
    log "key from $ref accepted by RIDB (HTTP 200); cached at $KEY_FILE"
    exit 0
  fi
  log "$ref: RIDB answered HTTP $status with that value — not using it"
done
log "no 1Password item produced a key RIDB accepts"
exit 1
