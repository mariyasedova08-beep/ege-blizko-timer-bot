# EGE BLIZKO: approval-gated automatic Timeweb deployments

This is for the *existing production* Timeweb service only:
- Project: /opt/bots/ege-blizko
- Systemd: ege-blizko
- Current service entry: timeweb_runner.py
- SQLite DB: /opt/bots/ege-blizko/data/coreapp_webhooks.db

This does NOT manage PREPODMIN, the pill tracker, or any Railway service.

## Control model

- Work branches: assistant prepares changes, tests and opens PR.
- Production-approved branch: release/ege-blizko-prod.
- Only after the owner says to publish and merges the approved PR does the
  Timeweb timer notice the new release, within approximately 2–3 minutes.
- No SSH keys or bot tokens need to be put in GitHub. No push to feature
  branches, main, or the old hotfix branch automatically changes production.
- The polling agent runs on Timeweb and fetches only the dedicated release
  branch without switching the live Git branch or altering .git working HEAD.

## One-time installation (on SSH Timeweb as root)

Only after reading the installation script in GitHub:

cd /opt/bots/ege-blizko
git fetch --no-tags origin refs/heads/ops/ege-timeweb-autodeploy-20261012:refs/remotes/origin/ops/ege-timeweb-autodeploy-20261012
git show refs/remotes/origin/ops/ege-timeweb-autodeploy-20261012:deploy/install_timeweb_deploy.sh > /tmp/ege-install-timeweb-deploy.sh
bash -n /tmp/ege-install-timeweb-deploy.sh
bash /tmp/ege-install-timeweb-deploy.sh

Expected: "EGE BLIZKO AUTO-DEPLOY READY" and an active timer.
The installer does not restart the bot, edit its source, or send messages.
It verifies live Git HEAD matches the initial release branch and aborts
rather than guessing if the relationship is wrong.

## Release sequence

1. Assistant prepares a feature branch and checks the changed files.
2. Pull request targets release/ege-blizko-prod.
3. Owner explicitly approves publication and assistant merges PR.
4. Server timer checks branch within approx 2–3 minutes.
5. Puller checks that release is a fast-forward, rejects deletes/renames,
   forbids data/, .venv/, secrets, timeweb_runner.py, ege_lab_webapp.py,
   and stops if any touched live file has unsaved local changes.
6. SQLite online backup with integrity_check goes into a timestamped private
   /var/backups/ege-blizko-deploy subdirectory.
7. Only approved source files are copied atomically; Python syntax checked.
8. The ege-blizko systemd unit restarts only if source files changed. Checks
   it remains active over a short window.
9. New commit marker recorded only on success; otherwise code is rolled back
   and service restarted, and database snapshot remains available.

NOTES: This is an initial conservative release agent. It does not automatically
apply DB schema migrations, switch entire directories or delete files.
Protection intentionally blocks dangerous changes pending manual review.
Service being active does not prove full application correctness; functional
smoke tests /health, student cabinet, lab, notifications should be used for
significant releases. The deployer agent itself is installed out of the
production branch and is NOT auto-updated.

## Useful read-only commands

systemctl status ege-blizko-poll.timer --no-pager
systemctl list-timers --all | grep ege-blizko-poll
journalctl -u ege-blizko-poll.service -n 30 --no-pager
cat /var/lib/ege-blizko-deploy/deployed_commit
systemctl status ege-blizko --no-pager

## Pause automatic updates

systemctl disable --now ege-blizko-poll.timer

This only stops polling and does NOT stop EGE BLIZKO.

## Rollback

On script failure, prior source bytes are restored and service restart
attempted. The private SQLite snapshot is NOT automatically put back as that
would discard newer student activity.
If a release is logically bad but service starts, a new corrective release
must be approved; do not force-push the release branch. For emergency pause,
disable timer above and inspect the log.

## Initial state, 2026-10-12

- A manual version of oge9_trainer_notifications.py already exists on Timeweb.
- The production run_bot_production.py already imports and installs this module.
- This setup only adds a future release channel and does not send Telegram messages.
- The initial approved release branch matches the original Timeweb hotfix Git
  branch and intentionally has no new changes. The OGE9 feature branch can be
  promoted after initial setup; the deployer tolerates files that are already
  identical to the approved release without overwriting them.
- The local chemistry laboratory edits are intentionally excluded and retained.
