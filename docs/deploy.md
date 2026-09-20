# Deployment — getting a change onto the Mac mini

Production is not the checkout you edit. It is a separate clone on the JamBot Mac mini (`/Users/jambot/.openclaw/workspace/campsiterecon`) plus the copy of `SKILL.md` that OpenClaw loads (`~/.openclaw/workspace/skills/campsite-recon/SKILL.md`). Until both are updated and the gateway restarts, Telegram keeps getting the old behaviour.

Wiki home: [README.md](README.md)

## The pipeline

```
git push / merge PR → main
        │
        ▼
GitHub Actions  (.github/workflows/ci.yml, GitHub-hosted runner)
  offline pytest suite — includes the preset-id gate
        │  green
        ▼
Mac mini LaunchAgent  ai.campsitescout.autodeploy  (every 15 min, outbound HTTPS only)
  deploy/auto_deploy.sh: RIDB key still accepted? (else re-fetch from 1Password)
                         → fetch → is origin/main new? → are its CI checks green?
        │  yes
        ▼
deploy_jambot.sh: save local edits → fast-forward → pip install → pytest (rollback on fail)
                  → install SKILL.md with <REPO> substituted → remove stale .skill zips → --verify (advisory)
        │
        ▼
launchctl kickstart ai.openclaw.gateway   → OpenClaw loads the new SKILL.md
```

So "deploying" is: get the commit onto `main` with green CI. The box picks it up within 15 minutes.

## Why pull-based, and not a GitHub Actions deploy job

- **GitHub-hosted runners cannot reach the Mac mini.** It sits behind home NAT on a residential IP; there is no inbound path, and opening one (port-forwarded SSH, a tunnel) would expose the machine that holds the Rec.gov session cookies and the 1Password service-account token.
- **A self-hosted runner on the Mac mini would work, but this repo is public.** Any fork can open a pull request whose workflow says `runs-on: self-hosted`; GitHub's own guidance is not to attach self-hosted runners to public repositories for exactly that reason. "Require approval for outside contributors" reduces the risk to one mis-click.
- Polling needs nothing inbound and no secrets in GitHub, and the box decides for itself what to run. GitHub Actions still does the part it is good at: gating `main`.

If the repo ever goes private, a self-hosted runner becomes reasonable: register it on the box, then add a `deploy` job with `needs: test`, `if: github.ref == 'refs/heads/main'`, `runs-on: [self-hosted, macOS]` that runs `bash deploy_jambot.sh && launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`, and remove the LaunchAgent.

## One-time setup on the Mac mini (as `jambot`)

```bash
cd ~/.openclaw/workspace/campsiterecon
git fetch origin
git show origin/main:deploy_jambot.sh > /tmp/deploy_jambot.sh     # the old clone doesn't have the script yet
bash /tmp/deploy_jambot.sh                                         # first deploy; saves the box's local edits first
mkdir -p ~/.openclaw/logs
cp deploy/ai.campsitescout.autodeploy.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.campsitescout.autodeploy.plist
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```

## The RIDB key comes from 1Password

On the box, 1Password is the source of truth: item `recreation_gov_api` (field `credential`) in vault `openclaw_macmini`. **To rotate the key, update that item and do nothing else** — within 15 minutes the LaunchAgent notices RIDB rejecting the cached key and re-fetches.

[deploy/fetch_ridb_key.sh](../deploy/fetch_ridb_key.sh) does the fetch: it sources `~/.openclaw/workspace/.1password.sh` for the service-account token, runs `op read`, **validates the value against RIDB (HTTP 200)**, and caches it at `~/.campsitescout/ridb_api_key` (mode 600, directory 700 — the same place the Rec.gov session cookies live). `main.py` reads that file first, ahead of Keychain and env. It tries `recreation_gov_api/credential`, then the near-duplicate item `recreation_gov_api_key/credential`, then `recreation_gov_api/password`, and keeps the first one RIDB accepts, so it does not matter which of the two items you updated. The key is never printed, logged, or passed in argv.

`main.py` deliberately does **not** call `op` itself. On this box `op` hangs instead of failing, a cold read has taken ~60 s, and leaked `op daemon` processes caused the 2026 gateway outage — so the fetch is off the request path and wrapped like the gateway wrapper's: full path, `OP_CACHE=false`, stdout to a file, a `kill -9` watchdog, daemon reaping on timeout, and at most one attempt per hour when 1Password is unreachable.

`op read` only works from a logged-in GUI session. Over bare SSH it hangs, so `deploy_jambot.sh` skips the fetch when it sees `SSH_CONNECTION` and leaves it to the LaunchAgent. To force it from a Terminal on the Mini:

```bash
bash ~/.openclaw/workspace/campsiterecon/deploy/fetch_ridb_key.sh && echo fetched
```

Weekend mode is keyless, so it keeps working whatever state the key is in. On the main Mac (no `op` CLI) the key lives in Keychain: `security add-generic-password -U -a "$USER" -s recreation-gov-api -w` prompts for it.

## Checking on it

```bash
tail -20 ~/.openclaw/logs/campsitescout-autodeploy.log     # "deployed abc1234", "CI still running", "RIDB key refreshed from 1Password", …
bash deploy/fetch_ridb_key.sh --check && echo "cached RIDB key is accepted"
cd ~/.openclaw/workspace/campsiterecon && git log --oneline -1
cat /tmp/campsitescout-verify.json | head -5               # last live preset check
launchctl print gui/$(id -u)/ai.campsitescout.autodeploy | grep -E "state|last exit"
```

The agent is silent when there is nothing new. It refuses to deploy when the box's HEAD is not an ancestor of `origin/main` (someone committed on the box) — fix that by hand.

## Things that are not automated

- **Rec.gov's 429 budget is per IP and both Macs share it.** Don't run scans on the main Mac while the box is running a watch.
- **The org-synced Claude skill `campsite-scout`** is a separate, pre-CLI artifact; nothing here updates or removes it.
- **Local edits on the box** are saved to `~/campsiterecon-local-<stamp>.patch` and `git stash` on every deploy, never reapplied. Anything worth keeping belongs in a commit.
