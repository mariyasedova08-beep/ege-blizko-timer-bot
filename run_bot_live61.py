from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live60

live60 = run_bot_live60
live59 = live60.live59
live58 = live60.live58
live56 = live60.live56
live55 = live60.live55
live54 = live60.live54
live52 = live60.live52
live51 = live60.live51
live50 = live60.live50
live49 = live60.live49
live48 = live60.live48
live46 = live60.live46
live44 = live60.live44
live43 = live60.live43
live41 = live60.live41
live39 = live60.live39
live37 = live60.live37
live35 = live60.live35
live34 = live60.live34
live31 = live60.live31
live24 = live60.live24
live17 = live60.live17
bot = live60.bot

_previous_safe_test_command = live55.safe_test_command


async def safe_test_command_with_oxides(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return

    arg = str(context.args[0]).lower().strip() if context.args else ""
    if arg in {"oxide", "oxides", "оксид", "оксиды"}:
        me = await context.bot.get_me()
        await update.message.reply_text(
            "🧪 ТЕСТ — это видишь только ты. В группу и ученикам ничего не отправлено.\n\n"
            "Тренажёр «Классификация оксидов»\n"
            "50 вопросов: основные, амфотерные, кислотные и несолеобразующие оксиды.\n\n"
            "Кнопка ниже открывает настоящий тренажёр.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧪 Открыть тренажёр", url=f"https://t.me/{me.username}?start=oxides")]
            ]),
        )
        return

    await _previous_safe_test_command(update, context)


# live55 защищает /test от случайной отправки таймера в группу. Новые тесты,
# добавленные после live55, нужно включать в тот же безопасный роутер.
live55.safe_test_command = safe_test_command_with_oxides

# Регистрируем /test через исходный CommandHandler напрямую, чтобы поздние
# тесты не потерялись в старом списке безопасных тестов live55.
_BaseCommandHandler = live55._PreviousCommandHandler


def _safe_command_handler_v2(command, callback, *args, **kwargs):
    commands = {command} if isinstance(command, str) else set(command or [])
    if "test" in commands:
        callback = safe_test_command_with_oxides
    return _BaseCommandHandler(command, callback, *args, **kwargs)


bot.CommandHandler = _safe_command_handler_v2


if __name__ == "__main__":
    live59.ensure_coreapp_webhook_audit_table()
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
    live60.ensure_oxides_tables()
    live60.register_oxides_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live56.log_probnik_cabinet_audit()
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00")
    print("Safe /test oxides route ready")
    print("CoreApp live sync receiver v2 ready")
    live24.main()
