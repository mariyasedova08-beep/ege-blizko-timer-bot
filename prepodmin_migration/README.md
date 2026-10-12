# PREPADMIN → Timeweb: migration runbook (preparation only)

Date: 2026-10-12. The live bot is **@prepodmin_bot**.
This directory contains migration-only tooling; it must **not** be merged or deployed as an application change.

## Scope and safety

- Source: Railway service `teacher-admin-pilot`; SQLite on its own mounted `/data/teacher_product.sqlite3`.
- Code: existing `teacher_product_*.py` in `mariyasedova08-beep/ege-blizko-timer-bot`, entry point `python teacher_product_runner.py`.
- Destination: existing Timeweb VPS, but in **separate** OS account, directory, Python venv, SQLite data directory, web host and systemd service.
- The running `ЕГЭ БЛИЗКО` app and `sedova-pill-tracker-bot` must remain untouched.
- The bot uses Telegram **long polling**: **never run two live copies with the same token at once**.
- Do not store tokens, .env files or copied SQLite databases in GitHub or chats.
- This branch does not access Railway data or start a bot.

## Preflight (before anything changes)

1. Confirm that the authenticated Railway account actually has access to `teacher-admin-pilot`, its **production environment** and the mounted `/data` volume. Confirmed via Railway connector: PREPADMIN is a separate service inside the Railway project named `sedova-pill-tracker-bot`. This does NOT make it the medical bot; services and volumes are distinct.
2. In Railway service's Volume → Backups, create a **manual backup** and record its time. A Railway backup is rollback insurance, not the portable snapshot.
3. Confirm whether any other files are stored in `/data` besides the SQLite DB. Include necessary uploads/assets in the transfer.
4. Record counts for teachers, students, groups, homework, homework statuses, tasks, payments, reminders and invitation records from the source using safe aggregate queries.
5. Confirm Timeweb has RAM/disk headroom, available private port, systemd, HTTPS proxy and an independent deployment directory. Never overwrite the `ege-blizko` service or its database.

## Portable consistent SQLite snapshot

A direct file copy of a busy SQLite DB may omit transactions in WAL. Instead, use
`prepodmin_sqlite_snapshot.py`, which runs SQLite's **online backup** on the
read-only source and verifies `PRAGMA integrity_check`.

Example commands, from a trusted terminal with **Railway CLI** logged in and the
correct project/environment selected (adjust volume ID):

```bash
# Railway: choose the correct project and service before running:
railway volume list
railway volume files --volume <PREPADMIN_VOLUME_ID> upload ./prepodmin_migration/prepodmin_sqlite_snapshot.py /prepodmin_sqlite_snapshot.py

# Create a snapshot INSIDE Railway /data; does not modify the live source DB:
railway ssh --service teacher-admin-pilot -- python /data/prepodmin_sqlite_snapshot.py --source /data/teacher_product.sqlite3 --dest /data/prepodmin-export-initial.sqlite3

# Download securely into a PRIVATE folder outside your Git repository:
railway volume files --volume <PREPADMIN_VOLUME_ID> download /prepodmin-export-initial.sqlite3 ./private/prepodmin-export-initial.sqlite3
```

Review printed SHA-256, integrity check and row counts; independently validate
the downloaded copy on the target with SQLite. Restrict DB file permissions to
owner only, transfer over an authenticated encrypted channel.

**The initial snapshot is for rehearsal only.** Final snapshot must be made
after write activity has been stopped/quiesced on the old service to avoid
dropping new work submitted during the migration.

## Standalone Timeweb instance (staging, NO BOT TOKEN)

- Deploy the tested source files and exact `requirements.txt` under a
  separate path, for example `/opt/prepodmin`.
- Create a separate non-root Unix service user and its private writable data
  directory, e.g. `/var/lib/prepodmin`.
- Copy the verified snapshot to `/var/lib/prepodmin/teacher_product.sqlite3`.
- Do not start Telegram polling yet. In test mode keep
  `TEACHER_PRODUCT_BOT_TOKEN` unset, and use an isolated staging DB copy.
- Set the final environment values at cutover:
  `TEACHER_PRODUCT_DB_PATH=/var/lib/prepodmin/teacher_product.sqlite3`,
  `PORT=<DEDICATED_PORT>`,
  `TEACHER_PRODUCT_BOT_USERNAME=prepodmin_bot`,
  `TEACHER_PRODUCT_WEBAPP_URL=https://<PREPADMIN_HOST>/webapp`, and
  `TEACHER_PRODUCT_STUDENT_WEBAPP_URL=https://<PREPADMIN_HOST>/student`.
  Read all additional required variables from the current Railway service
  **without exposing their values** in chat or public repositories.
- Configure HTTPS reverse proxy for `/health`, `/webapp`, `/student`
  and the associated `/api` routes as implemented by the service. Do not
  repoint EGE BLIZKO URLs.
- Python entry point: `python teacher_product_runner.py` (NOT the shared
  repo's `Procfile` / `bot.py`). Use an independent systemd unit.
- Beware: startup runs schema checks, an internal persistence probe, and
  boot tests. Test on a **copy** of the DB before using production data.

## Cutover (separate explicit checkpoint)

1. Confirm Railway backup and a working dry-run on Timeweb.
2. Agree on a brief maintenance window; stop/mute old Railway polling and
   writes before making the **final** consistent SQLite snapshot.
3. Transfer final snapshot and compare checksums and table counts.
4. Set the Telegram token in the **private** Timeweb environment (do not paste
   it into chat). If token rotation is required, do it in BotFather at cutover,
   understanding old signed WebApp launch links may expire.
5. Start **only** the Timeweb PREPADMIN systemd service; verify `/health`,
   logs, `/webapp` and `/student` over HTTPS, plus /start, onboarding,
   teacher cabinet, groups, invitations, lessons, payments, tasks,
   notifications, homework, webapp link and student cabinet.
6. Confirm no `Conflict: terminated by other getUpdates request` errors
   (which would indicate duplicate polling).
7. Leave Railway's volume and manual backup intact until functionality and
   data consistency have been independently verified and the user approves
   final decommissioning.

## Rollback

If validation fails: stop Timeweb polling **first**, restore access to the
old Railway deployment and its original volume, then retest the Telegram bot.
Do not allow writes to two independent copies of the SQLite database.

## Current state

- GitHub source audit: done; confirmed `teacher_product_runner.py`,
  `teacher_product_mvp.py`, `TEACHER_PRODUCT_DB_PATH`, teacher and student
  WebApp environment variables.
- Dedicated migration branch and safe snapshot utility: prepared.
- Railway service access: **CONFIRMED**. Project `sedova-pill-tracker-bot` UUID `2cc2c543-bbc0-49ae-b5f1-1642e1ccee5a`, service `teacher-admin-pilot` UUID `119fc219-f4cd-4f8a-9d09-16d5586d6da3`, production volume `60b7d67c-ec68-4840-b48b-3fce015d50ee` (500 MB, mounted `/data`).
- Latest reported PREPADMIN Railway deployment `81760d92-fe44-4e1d-9efe-46bc871691da` is **FAILED** (Railpack build daemon / grpc server issue); latest previous deployment is REMOVED. Treat service as potentially down; verify before any migration.
- Railway variables are accessible by *names only* through OAuth; values are redacted.
- Railway connector currently has **no volume file download/backup or SSH execution action**. A secure CLI or terminal transfer is needed for actual DB export.
- There is one unrelated staged change for EGE BLIZKO in the shared Railway project. DO NOT `accept_deploy`: that would apply unrelated staged changes.
- Snapshot from Railway: NOT TAKEN.
- VPS staging, SSH deployment, Telegram switch: NOT STARTED.
