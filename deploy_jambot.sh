#!/bin/bash
# Deploy campsitescout to the JamBot Mac mini. Run ON THE MAC MINI as user jambot:
#     bash ~/.openclaw/workspace/campsiterecon/deploy_jambot.sh
# Normally you never run it by hand: deploy/auto_deploy.sh (a LaunchAgent) calls it whenever
# origin/main moves and CI is green. First-time bootstrap is in docs/deploy.md.
#
# What it does, in order — every step is idempotent:
#   1. Saves the box's uncommitted edits to a patch file + stash (nothing is lost).
#   2. Fast-forwards the clone to origin/main. Refuses (and says so) if it cannot fast-forward.
#   3. Creates/updates the repo's own .venv and installs requirements (pydantic is required now).
#   4. Runs the offline tests (they include the preset-id gate). On failure it ROLLS BACK to the
#      commit that was running before and exits 1 — a bad commit never stays deployed.
#   5. Installs the repo SKILL.md as the OpenClaw skill with <REPO> substituted, and removes the
#      stale packaged skill zips / fabricated reference table OpenClaw could still load.
#   6. Runs `main.py --verify` live. Advisory only: a Rec.gov 429 or RIDB outage must not block a
#      deploy that already passed the offline gate. Result: /tmp/campsitescout-verify.json
#
# It does NOT restart the OpenClaw gateway (auto_deploy.sh does). By hand:
#     launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
set -euo pipefail

REPO="${REPO:-$HOME/.openclaw/workspace/campsiterecon}"
SKILL_DIR="${SKILL_DIR:-$HOME/.openclaw/workspace/skills/campsite-recon}"
STAMP="$(date +%Y%m%d-%H%M%S)"

cd "$REPO"
PREV="$(git rev-parse HEAD)"

echo "== 1/6 preserving local edits"
if ! git diff --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git diff > "$HOME/campsiterecon-local-$STAMP.patch"
  git ls-files --others --exclude-standard | tar -czf "$HOME/campsiterecon-untracked-$STAMP.tgz" -T - 2>/dev/null || true
  echo "   saved: $HOME/campsiterecon-local-$STAMP.patch (+ untracked tgz); also in 'git stash list'"
  git stash push --include-untracked -m "pre-deploy $STAMP" >/dev/null
fi

echo "== 2/6 fast-forwarding to origin/main"
git fetch origin
git merge --ff-only origin/main

echo "== 3/6 python environment"
[ -x .venv/bin/python ] || python3 -m venv .venv
./.venv/bin/pip install -q -r requirements.txt

echo "== 4/6 offline tests (rollback on failure)"
if ! ./.venv/bin/python -m pytest -q tests; then
  echo "   tests FAILED on $(git rev-parse --short HEAD) — rolling back to ${PREV:0:7}"
  git reset --hard "$PREV"          # safe: step 1 already saved and stashed every local edit
  exit 1
fi

echo "== 5/6 installing SKILL.md for OpenClaw at $SKILL_DIR"
mkdir -p "$SKILL_DIR"
sed "s#<REPO>#$REPO#g" SKILL.md > "$SKILL_DIR/SKILL.md"
rm -rf "$SKILL_DIR/references"                       # the old copy shipped a fabricated id table
find "$HOME/.openclaw/workspace" -maxdepth 3 -name '*.skill' -print -delete 2>/dev/null || true
echo "   $(grep -c "$REPO" "$SKILL_DIR/SKILL.md") commands now point at $REPO"

echo "== 6/6 live preset verification (advisory)"
if ./.venv/bin/python main.py --verify > /tmp/campsitescout-verify.json 2>/dev/null; then
  echo "   --verify ok"
else
  echo "   WARNING: --verify did not pass — see /tmp/campsitescout-verify.json"
  echo "   ('could not fetch' = Rec.gov 429 throttle, rerun in 10 min; 'No RIDB API key' = add the key, see docs/deploy.md)"
fi
echo "Deployed $(git rev-parse --short HEAD). Restart the gateway to load the new SKILL.md."
