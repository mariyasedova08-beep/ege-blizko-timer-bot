# Individual probnik results

Scope: Olya and Alina in the existing `individual_students` registry. No conversion into the group `students` table, parent links, group reminders, payment records or group exam analytics. Keep existing trainers; add a private Probniks button and a teacher preview under each individual card. Names of Google Sheets tabs must exactly match the individual display names, case/spacing/ё normalization allowed. Do not guess first-name aliases.

Only explicit `publication_status=опубликовано` is saved for individuals. Dates and finite nonnegative scores are validated before any delegated group writes. Individual results and notices use separate new tables keyed by individual ID and event/date. Their IDs can safely equal group student IDs. A source name or Telegram identity colliding with the group roster stops synchronization. Drafts and tasks without an overall score do not generate notifications. Repeat imports and corrected scores update the result but do not resend a successful notice.

The regular synchronizer commits its transaction before the individual transaction. If the latter fails, the HTTP operation reports failure; a retry is idempotent. Do not claim atomicity across those two transactions. Delivery has the usual crash window between Telegram acceptance and saving sent status.

## Verification

53 isolated tests cover routing, collision refusal, private UI access, admin integration, zero scores, retries, repeated sync, missing Telegram, inactive pupils and student/parent regressions. No real messages were sent during development.

## VPS preflight

Run the pinned installer with `--check` first. It reads the runtime database in read-only mode, prints exact individual display names and link presence, checks for name/Telegram collisions and legacy individual results in group storage, and verifies the live parent/student dispatcher. It never imports the working bot chain or writes data. A different roster, changed dispatcher or legacy common results cause STOP; never bypass the guard.

Before release obtain separate owner approval for installing three code files, setting only INDIVIDUAL_PROBNIK_ENABLED=1, adding the two individual-only tables and restarting ege-blizko.service. Use `--apply` only after approval. The installer preserves local live67 changes, adds only its integration hook, uses a verified dispatcher version, takes a fresh SQLite backup and file/config copies and waits up to 600 seconds for health. It never rewrites Google Apps Script or original exam results.

After release have each individual issue /start and verify the Trainers/Probniks menu. Publish one reviewed row using the exact tab name, synchronize once, verify the individual result, teacher preview and sent status; verify that no ordinary student/parent notice was created for it. Do not mark complete from HTTP health alone.

## Rollback

Automatic rollback on installation failure restores original run_bot_live67.py, probnik_result_notify.py and runtime-vars.json with owner/mode preserved, restarts only the same service and verifies health. The new module remains inert; new result tables are retained. Never copy a snapshot DB over the working DB: other activity may have occurred since backup. For a later rollback, first disable the individual feature and restore those three original files from the exact recorded backup while preserving current file ownership/modes, restart that service and check /health, Telegram and the existing student/parent notifications. Any already sent notification is not recalled.
