from telegram.ext import ExtBot

import run_bot_live32

live32 = run_bot_live32
live31 = live32.live31
bot = live31.bot

_original_send_message = ExtBot.send_message
_HOMEWORK_QUESTION = "Когда планируешь сделать ДЗ? Напиши, пожалуйста, Марии Александровне в личные сообщения 👇"
_HOMEWORK_FOOTER = "Она ждет! И будет сильно ругаться, если не напишешь!"


async def send_message_with_homework_footer(self, *args, **kwargs):
    text = kwargs.get("text")
    if isinstance(text, str) and _HOMEWORK_QUESTION in text and _HOMEWORK_FOOTER not in text:
        kwargs["text"] = text + "\n\n" + _HOMEWORK_FOOTER
    return await _original_send_message(self, *args, **kwargs)


ExtBot.send_message = send_message_with_homework_footer


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live31.live24.main()
