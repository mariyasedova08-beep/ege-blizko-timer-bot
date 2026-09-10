from datetime import datetime

import run_bot_live25

live25 = run_bot_live25
live24 = live25.live24
run_bot = live25.run_bot
bot = live25.bot


async def test_day_before_lesson(update, context):
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return

    today = bot.today_moscow()
    next_lesson = next((d for d in run_bot.COURSE_LESSON_DATES if d > today), None)
    if not next_lesson:
        await update.message.reply_text("Ближайших уроков в расписании больше нет.")
        return

    lesson_number, lesson_time = live25._lesson_info_for_date(next_lesson)
    text = live25._lesson_message(lesson_number, next_lesson, lesson_time)
    if text is None:
        await update.message.reply_text("Не настроена ссылка Zoom для уроков.")
        return

    chat_id = bot.os.getenv("CHAT_ID", "").strip()
    if not chat_id:
        await update.message.reply_text("CHAT_ID не настроен.")
        return

    target_chat_id = int(chat_id)
    thread_id = bot.get_target_thread_id()

    await context.bot.send_message(
        chat_id=target_chat_id,
        message_thread_id=thread_id,
        text="🧪 <b>ТЕСТОВОЕ НАПОМИНАНИЕ</b>\n\n" + text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await context.bot.send_poll(
        chat_id=target_chat_id,
        message_thread_id=thread_id,
        question=(
            f"🧪 ТЕСТ: будешь на уроке №{lesson_number} "
            f"{next_lesson.strftime('%d.%m')} в {lesson_time}?"
        ),
        options=list(live25.LESSON_POLL_OPTIONS),
        is_anonymous=False,
        allows_multiple_answers=False,
        is_closed=False,
    )
    await update.message.reply_text(
        f"✅ Тест отправлен в группу для урока №{lesson_number} ({next_lesson.strftime('%d.%m')} в {lesson_time}).\n"
        "Он тестовый и не мешает автоматическому напоминанию за день до урока."
    )


# В текущем main команда /testlesson уже регистрируется из run_bot,
# поэтому подменяем только её обработчик, не затрагивая остальную логику.
run_bot.test_lesson_reminder = test_day_before_lesson


if __name__ == "__main__":
    live25.ensure_lesson_day_before_table()
    live24.main()
