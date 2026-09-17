"""Routing, recovery and one-time resend for the 2026-09-17 anonymous survey.

The monthly survey and anonymous survey originally registered broad text
handlers in the same PTB handler group (-31). PTB runs only the first matching
handler in a group, so the monthly handler swallowed anonymous free-text answers.
This module gives the anonymous in-progress survey its own earlier group,
re-prompts already-started students once after the fix, and performs one explicit
one-time resend to all active students requested by Maria on 2026-09-17.
"""
from datetime import datetime
import sqlite3

from telegram.ext import ApplicationBuilder, MessageHandler, filters

import student_anonymous_why_survey as survey

_original_build = None
_installed = False
RESEND_BATCH = "anonymous_why_all_resend_2026_09_17_after_fix_v1"


def ensure_tables():
    survey.ensure_tables()
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS anonymous_why_recovery_sent (
                survey_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(survey_key, telegram_user_id)
            );

            CREATE TABLE IF NOT EXISTS anonymous_why_resend_batches (
                batch_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('sent','failed')),
                attempted_at TEXT NOT NULL,
                error TEXT,
                PRIMARY KEY(batch_key, telegram_user_id)
            );
            """
        )
        conn.commit()


def _pending_recovery():
    ensure_tables()
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT p.telegram_user_id, p.current_index
            FROM anonymous_why_progress p
            LEFT JOIN anonymous_why_recovery_sent r
              ON r.survey_key=p.survey_key
             AND r.telegram_user_id=p.telegram_user_id
            WHERE p.survey_key=?
              AND r.telegram_user_id IS NULL
            ORDER BY p.telegram_user_id
            """,
            (survey.SURVEY_KEY,),
        ).fetchall()


def _mark_recovery_sent(user_id):
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO anonymous_why_recovery_sent
                (survey_key,telegram_user_id,sent_at)
            VALUES (?,?,?)
            """,
            (survey.SURVEY_KEY, int(user_id), datetime.now(survey.bot.TIMEZONE).isoformat()),
        )
        conn.commit()


def _resend_already_attempted(user_id):
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM anonymous_why_resend_batches WHERE batch_key=? AND telegram_user_id=?",
            (RESEND_BATCH, int(user_id)),
        ).fetchone()
    return bool(row)


def _mark_resend(user_id, status, error=None):
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO anonymous_why_resend_batches
                (batch_key,telegram_user_id,status,attempted_at,error)
            VALUES (?,?,?,?,?)
            """,
            (
                RESEND_BATCH,
                int(user_id),
                status,
                datetime.now(survey.bot.TIMEZONE).isoformat(),
                error,
            ),
        )
        conn.commit()


async def recovery_tick(context):
    # Recovery is only for the one-time survey day. Do not revive it later.
    if datetime.now(survey.bot.TIMEZONE).date() != survey.SURVEY_DATE:
        return

    sent = 0
    failed = 0
    for row in _pending_recovery():
        uid = int(row["telegram_user_id"])
        index = int(row["current_index"])
        if index < 0 or index >= len(survey.QUESTIONS):
            continue

        if index == 0:
            prefix = (
                "💗 В опросе был технический сбой: твой первый текстовый ответ мог не сохраниться. "
                "Я всё исправила. Пожалуйста, ответь на этот вопрос ещё раз — дальше опрос продолжится автоматически.\n\n"
            )
        else:
            prefix = (
                "💗 Опрос снова работает. Продолжим с того места, где ты остановился(ась).\n\n"
            )
        try:
            await context.bot.send_message(uid, prefix + survey.QUESTIONS[index])
            _mark_recovery_sent(uid)
            sent += 1
        except Exception:
            failed += 1

    if sent or failed:
        print(
            f"Anonymous survey recovery: sent={sent} failed={failed}",
            flush=True,
        )


async def resend_all_tick(context):
    """Resend the original survey invitation once to every active linked student."""
    ensure_tables()
    sent = 0
    failed = 0
    skipped = 0

    for uid in survey._recipients():
        if _resend_already_attempted(uid):
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=(
                    "💗 Отправляю опрос ещё раз — сейчас он работает корректно.\n\n"
                    + survey._intro_text()
                ),
                reply_markup=survey._intro_markup(),
            )
            _mark_resend(uid, "sent")
            sent += 1
        except Exception as exc:
            _mark_resend(uid, "failed", repr(exc)[:500])
            failed += 1

    print(
        f"Anonymous survey resend all: sent={sent} failed={failed} skipped={skipped}",
        flush=True,
    )

    admin_id = survey.bot.get_admin_id()
    if admin_id and (sent or failed):
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=(
                    "🕵️ Повторная рассылка анонимного опроса\n"
                    f"✅ Отправлено: {sent}\n"
                    f"⚠️ Не доставлено: {failed}"
                ),
            )
        except Exception:
            pass


def _build_with_fixed_anonymous_routing(self):
    application = _original_build(self)
    # Dedicated group. It runs before the monthly survey (-31). When there is no
    # active anonymous progress, survey.student_text returns normally and later
    # groups continue processing the message as before.
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, survey.student_text),
        group=-32,
    )
    if application.job_queue is not None:
        application.job_queue.run_repeating(
            recovery_tick,
            interval=60,
            first=5,
            name="anonymous_why_masha_2026_09_17_recovery",
        )
        application.job_queue.run_once(
            resend_all_tick,
            when=8,
            name="anonymous_why_masha_2026_09_17_resend_all_v1",
        )
    return application


def install():
    global _original_build, _installed
    if _installed:
        return
    ensure_tables()
    _original_build = ApplicationBuilder.build
    ApplicationBuilder.build = _build_with_fixed_anonymous_routing
    _installed = True
    print(
        "Anonymous survey routing fix ready: anonymous_text_group=-32 monthly_text_group=-31 recovery=enabled resend_all=enabled",
        flush=True,
    )
