import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live61

live61 = run_bot_live61
live60 = live61.live60
live59 = live61.live59
live58 = live61.live58
live56 = live61.live56
live55 = live61.live55
live54 = live61.live54
live52 = live61.live52
live51 = live61.live51
live50 = live61.live50
live49 = live61.live49
live48 = live61.live48
live46 = live61.live46
live44 = live61.live44
live43 = live61.live43
live41 = live61.live41
live39 = live61.live39
live37 = live61.live37
live35 = live61.live35
live34 = live61.live34
live31 = live61.live31
live24 = live61.live24
live17 = live61.live17
bot = live61.bot
live7 = live34.live7

OXIDES_INTRO_KEY = "intro-oxides-2026-09-11"


def _intro_already_sent():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM oxides_weekly_deliveries WHERE week_key = ?",
            (OXIDES_INTRO_KEY,),
        ).fetchone())


def _mark_intro_sent():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO oxides_weekly_deliveries (week_key, sent_at) VALUES (?, ?)",
            (OXIDES_INTRO_KEY, datetime.now(bot.TIMEZONE).isoformat()),
        )
        conn.commit()


async def send_oxides_intro(context):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False
    me = await context.bot.get_me()
    if not me.username:
        return False

    text = (
        "🧪 <b>Ребята, у нас новый тренажёр — «Классификация оксидов»!</b> 💗\n\n"
        "Я добавила его в ваши <b>личные кабинеты</b> → раздел «Тренажёры».\n\n"
        "Внутри <b>50 разных вопросов</b> на основные, амфотерные, кислотные и несолеобразующие оксиды. "
        "Можно выбрать 10, 20 или пройти сразу все 50 вопросов.\n\n"
        "Если ошибётесь, бот сохранит вопрос в «Мои ошибки», и его можно будет отдельно отработать ещё раз.\n\n"
        "Предлагаю начать с 10 вопросов и проверить, насколько хорошо уже получается классификация 👇"
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🧪 Пройти тренажёр",
            url=f"https://t.me/{me.username}?start=oxides",
        )
    ]])
    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=text,
        parse_mode="HTML",
        reply_markup=markup,
    )
    return True


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_oxides_intro(context):
    try:
        await _previous_tick(context)
    finally:
        if not _intro_already_sent():
            if await send_oxides_intro(context):
                _mark_intro_sent()
                print("Oxides intro announcement sent", flush=True)


live7.friday_trivial_tick = combined_tick_with_oxides_intro


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
    print("Oxides one-time intro ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()

# live62 entrypoint: one-time intro is idempotent via oxides_weekly_deliveries.
