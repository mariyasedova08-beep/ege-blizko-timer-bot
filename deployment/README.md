# Timeweb manual deploy — EGE BLIZKO

**Status as of 2026-10-12: configuration prepared, not activated.** Live EGE BLIZKO is already on Timeweb and OGE9 chat module is active there. Never modify PREPODMIN or the medical bot.

**SECURITY HOLD (2026-10-12):** Service `ege-blizko` currently has blank `User=` and `Group=` in systemd, therefore runs as root. The live database is owned by root and was observed mode `0644`, while its parent directory is `0755` (other local users could read it). Do not grant deploy sudo or activate this workflow yet. The reviewed helper now refuses execution while the service runs as root. First audit all write paths, move only the EGE BLIZKO service to a dedicated unprivileged account with private data permissions, test health/UI/bot/lab and preserve rollback. The helper installed on Timeweb predates this security hold and must be replaced after review; no deploy sudo rule has been authorized.

## First-time server setup (as root, review commands)
1. SSH to Timeweb. Do NOT `git pull`, `git reset`, or `git checkout` in the live checkout; `ege_lab_webapp.py` has unsaved local modifications.
2. Fetch the deployment branch into a *remote tracking ref* and verify syntax:
   ```bash
   cd /opt/bots/ege-blizko
   git fetch origin refs/heads/feature/timeweb-safe-deploy-20261012:refs/remotes/origin/feature/timeweb-safe-deploy-20261012
   git show origin/feature/timeweb-safe-deploy-20261012:deployment/timeweb_safe_deploy.sh > /tmp/ege-blizko-deploy-reviewed.sh
   bash -n /tmp/ege-blizko-deploy-reviewed.sh && echo "DEPLOY HELPER SYNTAX OK"
   ```
3. After review, install the **root-owned fixed helper** and grant narrowly specified sudo access for **one executable, with no arguments**:
   ```bash
   install -o root -g root -m 0755 /tmp/ege-blizko-deploy-reviewed.sh /usr/local/sbin/ege-blizko-deploy
   install -d -o ege-deploy -g ege-deploy -m 0700 /home/ege-deploy/ege-blizko-staging
   printf '%s\n' 'ege-deploy ALL=(root) NOPASSWD: /usr/local/sbin/ege-blizko-deploy ""' > /etc/sudoers.d/ege-blizko-deploy
   chmod 0440 /etc/sudoers.d/ege-blizko-deploy
   visudo -cf /etc/sudoers.d/ege-blizko-deploy
   ```
4. The `ege-deploy` user has already been created. Owner generated an Ed25519 key on Windows and added its **public key** to `/home/ege-deploy/.ssh/authorized_keys`. Confirmed `ssh -i ... ege-deploy@77.233.212.200 whoami` works without password.
5. Pin the **SSH host public key**, not just `ssh-keyscan` without verification. On server: `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. Compare with a locally obtained key before storing `TIMEWEB_KNOWN_HOSTS`.
6. In GitHub create environment `timeweb-production`, configure required manual reviewers and branch restrictions *before* storing production secrets. Workflow is manual-only. Create environment secrets **without sharing values in chat**:
   - `TIMEWEB_DEPLOY_KEY`: complete contents of user's locally generated **private** Ed25519 key (entered directly into GitHub Secrets UI);
   - `TIMEWEB_KNOWN_HOSTS`: verified OpenSSH known_hosts server public key entry;
   - `TIMEWEB_HOST`: Timeweb SSH hostname or IP;
   - `TIMEWEB_USER`: `ege-deploy`.
7. The manual workflow file is registered on default `main` because `workflow_dispatch` requires being on the repository default branch. Select release ref `feature/timeweb-safe-deploy-20261012` when manually running it. Otherwise its branch validation will stop.
8. Test on nonproduction copy first if possible. Verify `systemctl status ege-blizko`, production `/health`, Telegram `/cabinet`, OGE chat only, and existing lab. OGE group ID should remain set in local DB, and individual student notifications should not be triggered by deployment.

## Guarantees and limits

- The fixed helper only copies `oge9_trainer_notifications.py` and `run_bot_production.py`. Other files including `ege_lab_webapp.py` and `data/` are not overwritten.
- SQLite online backup is created before restart; failure restores the two code files and restarts. Database changes are **not** blindly rolled back, to avoid erasing new student activity.
- Production `ege-blizko` service currently runs as **root**. Thus deploying arbitrary Python files, even through a helper with restricted sudo, can be equivalent to executing root-level code. This is a *partial* isolation, not complete privilege separation. Improving this requires migrating the bot runtime to a dedicated unprivileged Unix user after an additional permissions/DB/socket audit.
- Does not enable automatic push-triggered deploy. Explicit user approval per release is retained.
- Future code beyond these two files requires a deliberately reviewed allowlist update, not silent access to all filesystem paths.
