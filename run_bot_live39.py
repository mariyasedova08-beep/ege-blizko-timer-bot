import sqlite3
from datetime import date, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ExtBot

import run_bot_live38

live38 = run_bot_live38
live37 = live38.live37
live36 = live38.live36
live35 = live38.live35
live34 = live38.live34
live31 = live38.live31
live24 = live38.live24
live17 = live38.live17
bot = live34.bot
run_bot = live34.run_bot

COURSE_NAME = "Годовой курс подготовки к ЕГЭ по Химии"
PROBNIK_RETURN_TASK_KEY = "reenable-probnik-messages-2027-01-28"
PROBNIK_RETURN_TASK_DATE = date(2027, 1, 28)
PROBNIK_RETURN_TASK_TEXT = "Включить обратно сообщения про пробники в боте"


def seed_probnik_return_task():
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO admin_tasks
                (task_key, task_text, start_date, reminder_time, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                PROBNIK_RETURN_TASK_KEY,
                PROBNIK_RETURN_TASK_TEXT,
                PROBNIK_RETURN_TASK_DATE.isoformat(),
                "10:00",
                now,
            ),
        )
        conn.commit()


# Пока пробники полностью исключены из зоны внимания.
def _probnik_metric_paused(conn, student_row):
    return None


live34._probnik_metric = _probnik_metric_paused


def _child_alert_text(name, metrics):
    lines = [
        f"🚨 {name}, ты попал(а) в мою зону внимания 💗",
        "",
        "Сейчас есть несколько вещей, которые нужно подтянуть:",
    ]
    lines.extend(f"• {m['label']}" for m in metrics if m.get("key") != "probnik")
    lines.extend([
        "",
        "В ближайшие 3 дня постарайся исправить ситуацию. Если есть несданное ДЗ — обязательно закрой его.",
        "Тренажёры полезны, но их прохождение само по себе не считается исправлением ситуации.",
        "Через 3 дня я проверю динамику. Если ситуация не исправится, бот сообщит родителю.",
        "",
        "Если есть причина или нужна помощь — напиши Марии Александровне 💗",
    ])
    return "\n".join(lines)


def _parent_alert_text(student_name, unchanged_metrics):
    metrics = [m for m in unchanged_metrics if m.get("key") != "probnik"]
    lines = [
        f"👨‍👩‍👧 <b>{COURSE_NAME}</b>",
        "",
        "<b>Уведомление по учебной работе</b>",
        "",
        f"Три дня назад {student_name} получил(а) личное напоминание по учебной работе.",
        "Сейчас по-прежнему есть основания обратить внимание на ситуацию:",
    ]
    lines.extend(f"• {m['label']}" for m in metrics)
    lines.extend([
        "",
        "Пожалуйста, обратите на это внимание. Это не итоговая оценка, а сигнал о текущей работе на курсе.",
        "",
        "Если есть причина или нужна помощь — напишите Марии Александровне 💗",
    ])
    return "\n".join(lines)


live34._child_alert_text = _child_alert_text
live34._parent_alert_text = _parent_alert_text


def _metric_not_improved_homework_only(old_metric, new_snapshot):
    key = old_metric.get("key")

    # Пробники временно вообще не участвуют в контроле.
    if key == "probnik":
        return False

    # Единственное изменение, которое снимает контроль автоматически, — закрытое ДЗ.
    if key == "homework":
        if key not in new_snapshot:
            return False
        try:
            return float(new_snapshot[key].get("value")) >= float(old_metric.get("value"))
        except Exception:
            return True

    # Посещаемость и тренажёры остаются сигналами внимания; прохождение тренажёров
    # само по себе не считается исправлением ситуации.
    return True


live34._metric_not_improved = _metric_not_improved_homework_only


def _demo_metrics_without_probnik():
    return [
        {"key": "attendance", "value": 2, "label": "посещаемость: 2 пропуска из 4 последних уроков"},
        {"key": "homework", "value": 2, "label": "ДЗ: не закрыто 2 из 3 последних обязательных работ"},
        {"key": "trainer", "value": 1, "label": "тренажёры: 1 за последние 7 дней"},
    ]


live35._demo_metrics = _demo_metrics_without_probnik


def _contact_teacher_markup():
    admin_id = bot.get_admin_id()
    if not admin_id:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✉️ Написать Марии Александровне",
            url=f"tg://user?id={int(admin_id)}",
        )]
    ])


_previous_send_message = ExtBot.send_message


async def send_message_with_attention_contact(self, *args, **kwargs):
    text = kwargs.get("text")
    is_attention_child = isinstance(text, str) and "ты попал(а) в мою зону внимания" in text
    is_attention_parent = isinstance(text, str) and COURSE_NAME in text and "Уведомление по учебной работе" in text
    if (is_attention_child or is_attention_parent) and not kwargs.get("reply_markup"):
        markup = _contact_teacher_markup()
        if markup:
            kwargs["reply_markup"] = markup
    return await _previous_send_message(self, *args, **kwargs)


ExtBot.send_message = send_message_with_attention_contact


# Все автоматические сообщения/опросы по пробникам ставим на паузу.
async def _probnik_paused_job(context):
    return


async def _probnik_paused_nonresponders(context, now):
    return


async def _probnik_paused_command(update, context):
    if update.effective_chat.type == "private" and bot.user_is_admin(update):
        await update.message.reply_text(
            "⏸ Сообщения про пробники временно отключены. "
            "28.01.2027 я напомню включить их обратно."
        )


run_bot.probnik_daily_reminder = _probnik_paused_job
live24.probnik_poll_evening_summary = _probnik_paused_job
live24.live2.probnik_saturday_reminder = _probnik_paused_job
live31.live28._remind_probnik_nonresponders = _probnik_paused_nonresponders

# Даже тестовые команды пока не отправляют ничего детям/в группу случайно.
run_bot.test_probnik_thursday = _probnik_paused_command
run_bot.test_probnik_friday = _probnik_paused_command
live24.live2.test_probnik_saturday = _probnik_paused_command
live24.test_probnik_poll = _probnik_paused_command


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
    seed_probnik_return_task()
    live24.main()
