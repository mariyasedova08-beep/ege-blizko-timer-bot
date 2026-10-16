# ЕГЭ БЛИЗКО · staging LMS (NOT the Telegram bot)

This directory contains only the independent FastAPI staging LMS runtime and a Dockerfile. It is deployed from the branch `staging/ege-blizko-lms-standalone-20261016` and must **never** be merged into the Telegram bot's `main` or deployed into its production service. This is a temporary staging source; a dedicated LMS repository is the intended long-term home.

## Deployment configuration
- Create an entirely separate hosting project/service for the standalone LMS.
- Source: `mariyasedova08-beep/ege-blizko-timer-bot`; branch: `staging/ege-blizko-lms-standalone-20261016`; service root directory: `/standalone_lms_staging`.
- Dockerfile in this directory, listening on `0.0.0.0:$PORT`.
- Mount a persistent **private** disk at `/data` (1 replica only for SQLite).
- Variables: `EGE_LMS_DB=/data/ege_blizko_staging.sqlite3`; `EGE_LMS_HTTPS=1`; `EGE_LMS_PUBLIC_ORIGIN=https://<actual-hostname>`;
  `EGE_LMS_STAGING_USER=<random-username>`, `EGE_LMS_STAGING_PASSWORD=<long-random-secret>`.
- Healthcheck: `/health`; do not set up access from either Telegram bot, PREPODMIN, or their databases.
- All data on staging must be fictional test accounts only; email delivery, password recovery, regulatory compliance, rate limiting, and external security testing are not yet ready for real students.

## Verification
1. Confirm deployment status is terminal SUCCESS and `GET /health` returns JSON status ok.
2. Confirm `GET /` returns 401 without HTTP Basic credentials and 200 with them.
3. Teacher registration and email/password sessions, invite-based student registration, creating and publishing two questions, submission, review, student progress, and refresh-persistence; verify 2/2 points.
4. Confirm unauthorized teacher cannot access another teacher's results and student's API doesn't reveal answer keys.
5. Confirm records persist across deployment restart using the same mounted disk.

**Blocking status as of 2026-10-16:** An attempt to create an isolated Railway project was rejected: `Your trial has expired. Please select a plan to continue using Railway.` No public deployment was performed; no production service was modified.
