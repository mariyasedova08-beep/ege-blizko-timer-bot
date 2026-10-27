# Cabinet loading timeout: request-scoped schedule snapshots

Production evidence on 27 October: admin POST returned 504 after 60 seconds;
local authenticated POST also timed out after 25 seconds. Unauthenticated POST
returned 401 in milliseconds, both directly and through HTTPS. Three py-spy
snapshots of authenticated traffic showed multiple request threads repeatedly in
October `conditions -> due_lesson_for_source -> _effective_track ->
_effective_dates -> SQLite`. This confirms repeated schedule work; it does not
prove that deletion of files caused the incident.

The fix memoizes immutable schedule date/track/deadline results within a single
read-only view/report, including nested reports. Each concurrent request has its
own ContextVar dictionary. The dictionary is reset in a finally block; the next
request reads the database again immediately. No TTL or shared result cache.
Calls outside read scopes are unchanged. Transfer operations are not wrapped.
Transfer functions are found lazily because their installation follows rewards
installation. The new module never writes to the database or sends messages.

The source files of private VPS modules are not included. Only a pure scoped
hook into the pinned, previously reviewed October module is added. The helper
owns exactly `october_2026_close.py` and the new `cabinet_schedule_snapshot.py`.
No replacement of private rewards, assignments, lesson transfer, WebApp, Lab,
PrepAdmin or entrypoint source files. October dates, lottery rules and campaign
queue are unchanged.

## Validation

16 unit tests: nested and concurrent requests, immediate freshness, cleanup on
failure, lazy installation, idempotence, exact hook, authenticated release checks,
source conflict refusal, permissions and rollback preserving new payments.
Existing October tests must also pass. A local replay using the actual private
deadline/track function bodies with 103 course dates and 13 students produced
identical deadlines, reducing schedule reads from 5317 to 1. Local replay timing
is not a production response-time guarantee. The test functions are not copied
into the public repository.

## Controlled release

No deployment on push or merge. First merge the reviewed SHA, then install the
fixed root-owned helper using `bootstrap_cabinet_snapshot.sh <reviewed SHA>`.
Bootstrap only installs two literal sudo commands and does not restart the bot.
Use the manual `cabinet-snapshot-controlled-release.yml` workflow on main;
owner-only actor, protected `ege-lab-production`, pinned SSH host and existing
restricted deployment account. The helper serializes with other bot releases.

Preflight refuses changed October source, unexpected destination, old backup,
wrong service account or unverified database path. Creates an online SQLite
backup with integrity_check, code and ownership/mode backup, then atomically
installs the two files and restarts only ege-blizko. Success requires health and
startup markers from the current invocation, then authenticated HTTP 200/ok for
the teacher and two linked active course students, each within ten seconds.
Tokens and response bodies are not logged. Those tests are read-only views.

Expected success: `CABINET_SNAPSHOT_RELEASE_OK_BACKUP_ADMIN_AND_TWO_STUDENTS_VERIFIED`.
Also manually open teacher home, student home and stats; check fresh lesson
transfer display and that the October reminder queue was not recreated.

On failed startup/API verification, restore only the backed-up October source,
remove the exact new module and restart. Never restore the database or change
the announcement queue. Manual rollback uses the workflow's `rollback` action;
refuses subsequent code changes. It restores the previously installed October
exception, including Nov 5 results and Nov 4 cutoff, rather than pre-October code.
An existing completed backup directory is deliberately not reused after rollback;
an operator must review a new attempt.

## Remaining uncertainty

Production response time and student UI remain unverified until release. The
snapshot removes the measured schedule-query amplification; unrelated expensive
homework matching may require further profiling if authenticated checks fail.
The helper automatically rolls back instead of relaxing API checks.

## Recovery after the first protected release

Run 40492951863 failed at startup: the initial module incorrectly required both
cabinet modules to be imported during the October rewards hook. Journal showed
CABINET_SNAPSHOT_REQUIRED_MODULE_MISSING; the release automatically restored the
October exception without restoring the database. The corrected installer requires
only the rewards module at that stage and binds optional cabinet read functions
lazily when they are present. Two regressions cover absent and partially initialized
cabinet modules. The v2 helper uses a new root-only backup directory
`/var/lib/ege-cabinet-snapshot-20261027-v2`, preserving the first attempt's backup.
It still requires the pinned restored October source and absence of the new module,
and creates a fresh database backup. No retry reuses a stale database backup.
Failure logs now include only stage and exception type before automatic rollback.
The bootstrap accepts only the originally reviewed or corrected helper hash.
