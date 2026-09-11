import run_bot_live54

live54 = run_bot_live54
live53 = live54.live53
live52 = live54.live52
live51 = live54.live51
live50 = live54.live50
live49 = live54.live49
live48 = live54.live48
live47 = live54.live47
live46 = live54.live46
live45 = live54.live45
live44 = live54.live44
live43 = live54.live43
live41 = live54.live41
live39 = live54.live39
live37 = live54.live37
live35 = live54.live35
live34 = live54.live34
live31 = live54.live31
live24 = live54.live24
live17 = live54.live17
bot = live54.bot

# Важно: старый базовый /test без распознанного аргумента отправляет тест таймера
# в учебную группу. Поэтому регистрируем отдельный безопасный роутер для /test:
# неизвестные/пустые тесты НИЧЕГО не отправляют в группу.
_test_chain = bot.test

_SAFE_TEST_NAMES = {
    "weekly", "week", "report", "неделя",
    "probnik", "пробник",
    "monthly", "month", "месяц",
    "metals", "metal", "металлы",
    "studentcabinet", "cabinet", "lk", "лк",
    "schedule", "расписание", "timetable",
}


async def safe_test_command(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return

    arg = str(context.args[0]).lower().strip() if context.args else ""

    if arg in {"linkannounce", "cabinetannounce", "кабинеты"}:
        await update.message.reply_text(
            "🧪 ПРЕДПРОСМОТР — это сообщение видишь только ты. В группу ничего не отправлено.\n\n"
            + live54._cabinet_announcement_text(),
            parse_mode="HTML",
            reply_markup=await live54._cabinet_announcement_markup(context),
        )
        return

    if arg in _SAFE_TEST_NAMES:
        await _test_chain(update, context)
        return

    await update.message.reply_text(
        "🛡 Безопасный режим: этот тест не распознан, поэтому в группу ничего не отправлено.\n\n"
        "Для предпросмотра сообщения о личных кабинетах используй: /test linkannounce"
    )


# run_bot_live24.main() создаёт CommandHandler во время запуска.
# Подменяем callback именно в момент регистрации, чтобы никакая старая ссылка
# на bot.test не могла отправить таймер в группу по /test linkannounce.
_PreviousCommandHandler = bot.CommandHandler


def _safe_command_handler(command, callback, *args, **kwargs):
    commands = {command} if isinstance(command, str) else set(command or [])
    if "test" in commands:
        callback = safe_test_command
    return _PreviousCommandHandler(command, callback, *args, **kwargs)


bot.CommandHandler = _safe_command_handler


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
