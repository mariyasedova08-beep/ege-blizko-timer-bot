import sqlite3
from datetime import date, datetime, timedelta

import run_bot_live44

live44 = run_bot_live44
live43 = live44.live43
live42 = live44.live42
live41 = live44.live41
live40 = live44.live40
live39 = live44.live39
live37 = live44.live37
live35 = live44.live35
live34 = live44.live34
live31 = live44.live31
live24 = live44.live24
live17 = live44.live17
live7 = live34.live7
run_bot = live34.run_bot
bot = live44.bot
live2 = live24.live2
live28 = live31.live28

PROBNIK_ORG_PAUSE_FROM = date(2027, 1, 1)


def _probnik_org_enabled(today=None):
    today = today or bot.today_moscow()
    return today < PROBNIK_ORG_PAUSE_FROM


async def probnik_daily_reminder_until_january(context):
    today = bot.today_moscow()
    if not _probnik_org_enabled(today):
        return
    for probnik_date in run_bot.PROBNIK_DATES:
        if today == probnik_date - timedelta(days=2):
            await run_bot.send_probnik_bundle(context, probnik_date, "thursday")
            return
        if today == probnik_date - timedelta(days=1):
            await run_bot.send_probnik_bundle(context, probnik_date, "friday")
            return


async def probnik_poll_evening_summary_until_january(context):
    today = bot.today_moscow()
    if not _probnik_org_enabled(today):
        return
    probnik_date = next((d for d in run_bot.PROBNIK_DATES if today == d - timedelta(days=1)), None)
    if not probnik_date:
        return

    text, poll_id = live24.probnik_poll_summary_text(probnik_date)
    if not text or not poll_id:
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT summary_sent FROM probnik_polls WHERE poll_id = ?",
            (poll_id,),
        ).fetchone()
        if row and row[0]:
            return

    admin_id = bot.get_admin_id()
    if not admin_id:
        return

    await context.bot.send_message(chat_id=int(admin_id), text=text)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("UPDATE probnik_polls SET summary_sent = 1 WHERE poll_id = ?", (poll_id,))
        conn.commit()


async def probnik_saturday_reminder_until_january(context):
    today = bot.today_moscow()
    if not _probnik_org_enabled(today):
        return
    if today in run_bot.PROBNIK_DATES:
        await live2.send_probnik_saturday_reminder(context, today)


async def remind_probnik_nonresponders_until_january(context, now):
    if not _probnik_org_enabled(now.date()):
        return

    probnik_date = now.date()
    if probnik_date not in run_bot.PROBNIK_DATES:
        return

    event_dt = live28._event_datetime(probnik_date, "10:00")
    if not live28._within_reminder_window(now, event_dt):
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        poll_row = conn.execute(
            """
            SELECT poll_id, probnik_number
            FROM probnik_polls
            WHERE probnik_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (probnik_date.isoformat(),),
        ).fetchone()
        if not poll_row:
            return

        poll_id, probnik_number = poll_row
        answered_ids = {
            int(row[0])
            for row in conn.execute(
                "SELECT telegram_user_id FROM probnik_poll_answers WHERE poll_id = ?",
                (poll_id,),
            ).fetchall()
        }
        students = live28._active_linked_students(conn)

        for telegram_user_id, _name in students:
            telegram_user_id = int(telegram_user_id)
            if telegram_user_id in answered_ids:
                continue
            event_key = probnik_date.isoformat()
            if live28._already_reminded(conn, "probnik", event_key, telegram_user_id):
                continue
            try:
                await context.bot.send_message(
                    chat_id=telegram_user_id,
                    text=(
                        f"📝 Ты ещё не отметился(ась) на пробник №{probnik_number} сегодня в 10:00.\n\n"
                        "Зайди, пожалуйста, в группу курса и выбери в опросе «✅ Буду» или «❌ Не буду»."
                    ),
                )
            except Exception as exc:
                print(f"Could not send mock-exam poll reminder to {telegram_user_id}: {exc}")
                continue
            live28._mark_reminded(conn, "probnik", event_key, telegram_user_id)
            conn.commit()


async def _paused_test_message(update):
    if update.effective_chat.type == "private" and bot.user_is_admin(update):
        await update.message.reply_text(
            "⏸ Организационные напоминания и опросы про пробники выключены с 01.01.2027. "
            "28.01.2027 в задачах будет напоминание включить их обратно."
        )


async def test_probnik_thursday_until_january(update, context):
    if not _probnik_org_enabled():
        await _paused_test_message(update)
        return
    if not bot.user_is_admin(update):
        return
    target = run_bot.upcoming_probnik()
    ok, error = await run_bot.send_probnik_bundle(context, target, "thursday")
    await update.message.reply_text("✅ Тест четвергового напоминания отправлен в группу курса." if ok else error)


async def test_probnik_friday_until_january(update, context):
    if not _probnik_org_enabled():
        await _paused_test_message(update)
        return
    if not bot.user_is_admin(update):
        return
    target = run_bot.upcoming_probnik()
    ok, error = await run_bot.send_probnik_bundle(context, target, "friday")
    await update.message.reply_text("✅ Тест пятничного напоминания отправлен в группу курса." if ok else error)


async def test_probnik_saturday_until_january(update, context):
    if not _probnik_org_enabled():
        await _paused_test_message(update)
        return
    if not bot.user_is_admin(update):
        return
    target = run_bot.upcoming_probnik()
    ok, error = await live2.send_probnik_saturday_reminder(context, target)
    await update.message.reply_text("✅ Тест субботнего напоминания отправлен в группу курса." if ok else error)


async def test_probnik_poll_until_january(update, context):
    if not _probnik_org_enabled():
        await _paused_test_message(update)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    target = run_bot.upcoming_probnik()
    ok = await live24.send_probnik_attendance_poll(context, target, force=True)
    await update.message.reply_text(
        "✅ Тестовый опрос отправлен в группу." if ok else "Не удалось отправить: CHAT_ID не настроен."
    )


# Организационная часть пробников работает до 31.12.2026 включительно.
# С 01.01.2027 она автоматически замолкает; статистика и разбор слабых мест не затрагиваются.
run_bot.probnik_daily_reminder = probnik_daily_reminder_until_january
live24.probnik_poll_evening_summary = probnik_poll_evening_summary_until_january
live2.probnik_saturday_reminder = probnik_saturday_reminder_until_january
live28._remind_probnik_nonresponders = remind_probnik_nonresponders_until_january
run_bot.test_probnik_thursday = test_probnik_thursday_until_january
run_bot.test_probnik_friday = test_probnik_friday_until_january
live2.test_probnik_saturday = test_probnik_saturday_until_january
live24.test_probnik_poll = test_probnik_poll_until_january


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live24.main()
