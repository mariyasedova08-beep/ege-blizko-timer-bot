import sqlite3

import run_bot_live51

live51 = run_bot_live51
live50 = live51.live50
live49 = live51.live49
live48 = live51.live48
live47 = live51.live47
live46 = live51.live46
live45 = live51.live45
live44 = live51.live44
live43 = live51.live43
live41 = live51.live41
live39 = live51.live39
live37 = live51.live37
live35 = live51.live35
live34 = live51.live34
live31 = live51.live31
live24 = live51.live24
live17 = live51.live17
bot = live51.bot

# Повторно закрепляем последние версии функций личного кабинета,
# чтобы и реальный кабинет, и /test cabinet использовали расписание.
live49._student_home_markup = live51.student_home_markup_with_schedule
live49._student_home_text = live51.student_home_text_with_next_lesson

_previous_test = bot.test


async def test_with_fixed_cabinet_preview(update, context):
    is_cabinet = bool(context.args) and context.args[0].lower() in {
        "studentcabinet", "cabinet", "lk", "лк"
    }
    if not is_cabinet:
        await _previous_test(update, context)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                   user_name, user_email, coreapp_user_id, telegram_user_id
            FROM students
            WHERE active = 1 AND telegram_user_id IS NOT NULL
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()

    if not row:
        await update.message.reply_text(
            "🧪 ТЕСТ: пока нет привязанного ученика для предпросмотра."
        )
        return

    await update.message.reply_text(
        "🧪 ТЕСТ ЛИЧНОГО КАБИНЕТА — это видишь только ты. Ученику ничего не отправлено.\n\n"
        + live51.student_home_text_with_next_lesson(row),
        reply_markup=live51.student_home_markup_with_schedule(),
    )


bot.test = test_with_fixed_cabinet_preview


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
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live24.main()
