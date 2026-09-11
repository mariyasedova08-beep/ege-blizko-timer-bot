import run_bot_live53

live53 = run_bot_live53
live52 = live53.live52
live51 = live52.live51
live50 = live52.live50
live49 = live52.live49
live48 = live52.live48
live47 = live52.live47
live46 = live52.live46
live45 = live52.live45
live44 = live52.live44
live43 = live52.live43
live41 = live52.live41
live39 = live52.live39
live37 = live52.live37
live35 = live52.live35
live34 = live52.live34
live31 = live52.live31
live24 = live52.live24
live20 = live24.live20
live17 = live52.live17
bot = live52.bot


def _cabinet_announcement_text():
    return (
        "👤 <b>Подключаем личные кабинеты в боте «ЕГЭ БЛИЗКО»</b> 💗\n\n"
        "В личном кабинете можно посмотреть:\n"
        "📅 расписание и тему ближайшего урока\n"
        "📊 статистику за неделю и месяц\n"
        "🏠 домашние работы\n"
        "🎓 посещаемость\n"
        "📝 результаты пробников\n"
        "🧪 тренажёры\n"
        "🧠 темы и задания, которые стоит повторить\n\n"
        "Чтобы подключить кабинет, нажмите кнопку ниже, откройте бота и отправьте "
        "e-mail, который используете в CoreApp.\n\n"
        "Важно: нужен именно тот e-mail, на который зарегистрирован ваш аккаунт курса 💗"
    )


async def _cabinet_announcement_markup(context):
    me = await context.bot.get_me()
    return live20.live7.InlineKeyboardMarkup([
        [live20.live7.InlineKeyboardButton(
            "👤 Подключить личный кабинет",
            url=f"https://t.me/{me.username}?start=link",
        )]
    ])


async def student_cabinet_link_announce(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        await update.message.reply_text("Не удалось отправить: CHAT_ID не настроен.")
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=_cabinet_announcement_text(),
        parse_mode="HTML",
        reply_markup=await _cabinet_announcement_markup(context),
    )
    await update.message.reply_text(
        "✅ Личные кабинеты: новое сообщение отправлено ребятам в группу."
    )


# Патчим исходную функцию как первый уровень защиты.
live20.link_announce_command = student_cabinet_link_announce

# И дополнительно перехватываем саму регистрацию CommandHandler в старом main().
# Это исключает возврат к историческому тексту «Подключаем статистику тренажёров».
_OriginalCommandHandler = bot.CommandHandler


def _fixed_command_handler(command, callback, *args, **kwargs):
    commands = {command} if isinstance(command, str) else set(command or [])
    if "linkannounce" in commands:
        callback = student_cabinet_link_announce
    return _OriginalCommandHandler(command, callback, *args, **kwargs)


bot.CommandHandler = _fixed_command_handler

# Безопасный предпросмотр: /test linkannounce — только Марии, без отправки в группу.
_previous_test = bot.test


async def test_with_linkannounce_preview(update, context):
    is_preview = bool(context.args) and context.args[0].lower() in {
        "linkannounce", "cabinetannounce", "кабинеты"
    }
    if not is_preview:
        await _previous_test(update, context)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    await update.message.reply_text(
        "🧪 ПРЕДПРОСМОТР — это сообщение видишь только ты. В группу ничего не отправлено.\n\n"
        + _cabinet_announcement_text(),
        parse_mode="HTML",
        reply_markup=await _cabinet_announcement_markup(context),
    )


bot.test = test_with_linkannounce_preview


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
