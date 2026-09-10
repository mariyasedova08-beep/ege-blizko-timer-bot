import run_bot_live41

live41 = run_bot_live41
live40 = live41.live40
live39 = live41.live39
live37 = live41.live37
live35 = live41.live35
live34 = live41.live34
live31 = live41.live31
live24 = live41.live24
live17 = live41.live17
bot = live41.bot

_original_test = bot.test


async def test_with_weekly_preview(update, context):
    is_weekly = bool(context.args) and context.args[0].lower() in {"weekly", "week", "неделя"}
    if is_weekly:
        if update.effective_chat.type != "private" or not bot.user_is_admin(update):
            return
        markup = await live41._weekly_report_markup(context)
        await update.message.reply_text(
            "🧪 ТЕСТ — это сообщение видишь только ты. Ученикам ничего не отправлено.\n\n"
            "Привет, Маша! 💗\n\n"
            "📊 Твои итоги недели\n\n"
            "🎓 Посещаемость: 3 из 3 уроков\n"
            "🏠 ДЗ: 3 из 3 закрыто\n"
            "🧪 Тренажёры: 4 тренировки\n"
            "📈 Результат: 34 из 40 верно · 85%\n\n"
            "💡 Хороший темп 💗 Продолжай так же и выбери тренажёр для короткого повторения на следующей неделе.\n\n"
            "Все доступные тренажёры — кнопками ниже. Выбирай любой 👇",
            reply_markup=markup,
        )
        return
    await _original_test(update, context)


bot.test = test_with_weekly_preview


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
    live24.main()
