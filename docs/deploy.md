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
  deploy/auto_deploy.sh: fetch → is origin/main new? → are its CI checks green?
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

The RIDB key must be readable on the box for `--search` / `--verify` (weekend mode is keyless). Any one of:

```bash
security add-generic-password -U -a "$USER" -s recreation-gov-api -w     # prompts; nothing lands in shell history
```

or an existing `recreation_gov_api` / `recreation_gov_api_key` Keychain item, or `RIDB_API_KEY` in the gateway's environment.

## Checking on it

```bash
tail -20 ~/.openclaw/logs/campsitescout-autodeploy.log     # "deployed abc1234", "CI still running", "CI FAILED …"
cd ~/.openclaw/workspace/campsiterecon && git log --oneline -1
cat /tmp/campsitescout-verify.json | head -5               # last live preset check
launchctl print gui/$(id -u)/ai.campsitescout.autodeploy | grep -E "state|last exit"
```

The agent is silent when there is nothing new. It refuses to deploy when the box's HEAD is not an ancestor of `origin/main` (someone committed on the box) — fix that by hand.

## Things that are not automated

- **Rec.gov's 429 budget is per IP and both Macs share it.** Don't run scans on the main Mac while the box is running a watch.
- **The org-synced Claude skill `campsite-scout`** is a separate, pre-CLI artifact; nothing here updates or removes it.
- **Local edits on the box** are saved to `~/campsiterecon-local-<stamp>.patch` and `git stash` on every deploy, never reapplied. Anything worth keeping belongs in a commit.
