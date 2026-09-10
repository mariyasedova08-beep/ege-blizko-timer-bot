from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live31

live31 = run_bot_live31
bot = live31.bot
run_bot = live31.run_bot

_original_homeworkstatus = bot.homeworkstatus


async def homeworkstatus_with_test(update, context):
    if context.args and context.args[0].strip().lower() in {"test", "тест"}:
        if update.effective_chat.type != "private" or not bot.user_is_admin(update):
            return

        today = bot.today_moscow()
        target_date = next((d for d in run_bot.COURSE_LESSON_DATES if d > today), None)
        if target_date is None:
            await update.message.reply_text("Ближайшего урока в расписании не найдено.")
            return

        lesson_number = run_bot.COURSE_LESSON_DATES.index(target_date) + 1
        admin_id = bot.get_admin_id()
        reply_markup = None
        if admin_id:
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✉️ Написать Марии Александровне",
                    url=f"tg://user?id={int(admin_id)}",
                )]
            ])

        await update.message.reply_text(
            "🧪 ТЕСТ — это сообщение видишь только ты. Ученикам ничего не отправлено.\n\n"
            f"📝 ДЗ к уроку №{lesson_number} ещё не сдано 💗\n\n"
            "Завтра у нас урок, поэтому постарайся закончить домашнюю работу сегодня.\n\n"
            "Когда планируешь сделать ДЗ? Напиши, пожалуйста, Марии Александровне в личные сообщения 👇",
            reply_markup=reply_markup,
        )
        return

    await _original_homeworkstatus(update, context)


# live24.main регистрирует bot.homeworkstatus, поэтому сохраняем обычную команду
# и добавляем безопасный тест через аргумент "test".
bot.homeworkstatus = homeworkstatus_with_test


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live31.live24.main()
