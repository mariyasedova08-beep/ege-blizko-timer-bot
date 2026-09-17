"""Hard routing/recovery for the 2026-09-17 anonymous EGE BLIZKO survey.

The bot has many broad text/callback handlers. The anonymous survey must win
before all of them while a student is answering. This module installs dedicated
handlers in a very early PTB group, keeps completed answers intact, and performs
one repair pass for all active linked students after deployment.
"""
from datetime import datetime
import sqlite3

from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import student_anonymous_why_survey as survey

_original_build = None
_installed = False
ROUTING_GROUP = -10000
REPAIR_BATCH = "anonymous_why_repair_2026_09_17_v2"


def ensure_tables():
    survey.ensure_tables()
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS anonymous_why_repair_batches (
                batch_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('sent','failed','skipped')),
                attempted_at TEXT NOT NULL,
                error TEXT,
                PRIMARY KEY(batch_key, telegram_user_id)
            );
            """
        )
        conn.commit()


def _repair_done(user_id):
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM anonymous_why_repair_batches WHERE batch_key=? AND telegram_user_id=?",
            (REPAIR_BATCH, int(user_id)),
        ).fetchone())


def _mark_repair(user_id, status, error=None):
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO anonymous_why_repair_batches
                (batch_key,telegram_user_id,status,attempted_at,error)
            VALUES (?,?,?,?,?)
            """,
            (
                REPAIR_BATCH,
                int(user_id),
                status,
                datetime.now(survey.bot.TIMEZONE).isoformat(),
                error,
            ),
        )
        conn.commit()


def _state_counts():
    with sqlite3.connect(survey.bot.COREAPP_DB_PATH) as conn:
        progress = conn.execute(
            """
            SELECT current_index, count(*)
            FROM anonymous_why_progress
            WHERE survey_key=?
            GROUP BY current_index
            ORDER BY current_index
            """,
            (survey.SURVEY_KEY,),
        ).fetchall()
        completed = conn.execute(
            "SELECT count(*) FROM anonymous_why_completions WHERE survey_key=?",
            (survey.SURVEY_KEY,),
        ).fetchone()[0]
        responses = conn.execute(
            "SELECT count(*) FROM anonymous_why_responses",
        ).fetchone()[0]
    return {int(i): int(n) for i, n in progress}, int(completed), int(responses)


async def priority_callback(update, context):
    query = update.callback_query
    if not query or query.data != "anonwhy:start":
        return
    print("Anonymous survey event: start button", flush=True)
    await survey.student_callback(update, context)


async def priority_text(update, context):
    if not update.message or not update.message.text or update.effective_chat.type != "private":
        return
    uid = int(update.effective_user.id)
    before = survey._progress(uid)
    if not before:
        return
    before_index = int(before["current_index"])
    try:
        await survey.student_text(update, context)
    except ApplicationHandlerStop:
        after = survey._progress(uid)
        if after:
            print(
                f"Anonymous survey event: answer handled index={before_index} next={int(after['current_index'])}",
                flush=True,
            )
        else:
            print(
                f"Anonymous survey event: answer handled index={before_index} completed=yes",
                flush=True,
            )
        raise


async def repair_tick(context):
    """One safe repair pass: continue unfinished; invite not-started; skip completed."""
    ensure_tables()
    sent_continue = 0
    sent_invite = 0
    skipped_completed = 0
    failed = 0

    for uid in survey._recipients():
        uid = int(uid)
        if _repair_done(uid):
            continue
        if survey._completed(uid):
            _mark_repair(uid, "skipped")
            skipped_completed += 1
            continue

        progress = survey._progress(uid)
        try:
            if progress:
                index = int(progress["current_index"])
                if index < 0 or index >= len(survey.QUESTIONS):
                    index = 0
                    survey._advance(uid, 0)
                await context.bot.send_message(
                    chat_id=uid,
                    text=(
                        "💗 Я ещё раз починила опрос. Теперь ответ обрабатывается раньше всех остальных функций бота.\n\n"
                        "Просто ответь текстом на вопрос ниже — следующий вопрос придёт автоматически.\n\n"
                        + survey.QUESTIONS[index]
                    ),
                )
                sent_continue += 1
            else:
                await context.bot.send_message(
                    chat_id=uid,
                    text=(
                        "💗 Опрос полностью починен. Пожалуйста, попробуй ещё раз — для Маши это действительно важно.\n\n"
                        + survey._intro_text()
                    ),
                    reply_markup=survey._intro_markup(),
                )
                sent_invite += 1
            _mark_repair(uid, "sent")
        except Exception as exc:
            _mark_repair(uid, "failed", repr(exc)[:500])
            failed += 1

    progress, completed, responses = _state_counts()
    print(
        "Anonymous survey repair v2: "
        f"continue={sent_continue} invite={sent_invite} completed_skipped={skipped_completed} failed={failed} "
        f"progress={progress} completed={completed} anonymous_responses={responses}",
        flush=True,
    )

    admin_id = survey.bot.get_admin_id()
    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=(
                    "🛠 Анонимный опрос: повторное исправление\n"
                    f"Продолжить опрос отправлено: {sent_continue}\n"
                    f"Новая кнопка отправлена: {sent_invite}\n"
                    f"Уже завершили, не трогала: {skipped_completed}\n"
                    f"Ошибок: {failed}"
                ),
            )
        except Exception:
            pass


def _build_with_priority_survey(self):
    application = _original_build(self)
    application.add_handler(
        CallbackQueryHandler(priority_callback, pattern=r"^anonwhy:start$"),
        group=ROUTING_GROUP,
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, priority_text),
        group=ROUTING_GROUP,
    )
    if application.job_queue is not None:
        application.job_queue.run_once(
            repair_tick,
            when=7,
            name="anonymous_why_masha_2026_09_17_repair_v2",
        )
    return application


def install():
    global _original_build, _installed
    if _installed:
        return
    ensure_tables()
    _original_build = ApplicationBuilder.build
    ApplicationBuilder.build = _build_with_priority_survey
    _installed = True
    print(
        f"Anonymous survey hard routing ready: group={ROUTING_GROUP} repair_v2=enabled",
        flush=True,
    )
