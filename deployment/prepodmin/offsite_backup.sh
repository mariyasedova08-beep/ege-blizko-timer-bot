#!/usr/bin/env bash
# Root-owned installed copy only. No bot restarts or Nginx changes.
# One encrypted Restic snapshot: consistent PREPODMIN SQLite + attachments.
set -Eeuo pipefail
set +x
umask 077
ulimit -c 0 2>/dev/null || true
[[ "$EUID" == 0 ]] || { echo 'PREPODMIN_OFFSITE_BACKUP_REFUSED=root_only'; exit 2; }
BINDIR=/usr/local/lib/prepodmin-offsite
CONFIG=/etc/prepodmin/restic
ENVFILE="$CONFIG/s3.env"
PASSFILE="$CONFIG/repository.password"
DB=/opt/bots/prepodmin/data/teacher_product.sqlite3
FILES=/opt/bots/prepodmin/data/homework_uploads
DESTROOT=/var/backups/prepodmin/offsite-staging
EXPECTED_REPO='s3:https://s3.twcstorage.ru/prepodmin-backups-2026'
check_root_file() {
  [[ -f "$1" && ! -L "$1" && "$(stat -c '%U:%G:%a' "$1")" == root:root:600 ]]
}
check_root_file "$ENVFILE" && check_root_file "$PASSFILE" || {
  echo 'PREPODMIN_OFFSITE_BACKUP_REFUSED=private_secrets_missing'; exit 2;
}
[[ -d "$CONFIG" && ! -L "$CONFIG" && "$(stat -c '%U:%G:%a' "$CONFIG")" == root:root:700 ]] || exit 2
[[ -d "$DESTROOT" && ! -L "$DESTROOT" && "$(stat -c '%U:%G:%a' "$DESTROOT")" == root:root:700 ]] || exit 2
[[ -f "$BINDIR/prepare_offsite_bundle.py" && ! -L "$BINDIR/prepare_offsite_bundle.py" ]] || exit 2
[[ -f "$DB" && ! -L "$DB" && -d "$FILES" && ! -L "$FILES" ]] || exit 2
systemctl is-active --quiet prepodmin && systemctl is-active --quiet ege-blizko || exit 2
exec 9>"$DESTROOT/.offsite.lock"
flock -n 9 || { echo 'PREPODMIN_OFFSITE_BACKUP_SKIPPED=already_running'; exit 0; }
# shellcheck disable=SC1090
source "$ENVFILE"
[[ "$RESTIC_REPOSITORY" == "$EXPECTED_REPO" ]] || {
  echo 'PREPODMIN_OFFSITE_BACKUP_REFUSED=unexpected_repository'; exit 2;
}
STAGE="$(mktemp -d "$DESTROOT/.run.XXXXXXXX")"
cleanup() {
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
  if [[ -n "$STAGE" && "$STAGE" == "$DESTROOT"/.run.???????? && -d "$STAGE" && ! -L "$STAGE" ]]; then
    rm -rf -- "$STAGE"
  fi
}
trap cleanup EXIT
python3 "$BINDIR/prepare_offsite_bundle.py" prepare --db "$DB" --attachments "$FILES" --bundle "$STAGE/bundle" || exit 2
restic --password-file "$PASSFILE" backup --quiet --tag prepodmin-offsite "$STAGE/bundle" >"$STAGE/restic.stdout" 2>"$STAGE/restic.stderr" || {
  echo 'PREPODMIN_OFFSITE_BACKUP_FAILED=restic'; exit 2;
}
restic --password-file "$PASSFILE" snapshots --latest 1 --tag prepodmin-offsite >"$STAGE/verify.stdout" 2>"$STAGE/verify.stderr" || {
  echo 'PREPODMIN_OFFSITE_BACKUP_FAILED=remote_snapshot_unverifiable'; exit 2;
}
echo 'PREPODMIN_OFFSITE_BACKUP_OK'
echo 'PREPODMIN_OFFSITE_RESTORE_TEST_STILL_REQUIRED'
