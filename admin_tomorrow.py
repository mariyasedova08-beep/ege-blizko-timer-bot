"""Tomorrow plan for the EGE BLIZKO admin cabinet."""

import html
import sqlite3
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90

bot = live90.bot
live79 = live90.live79
live23 = live79.live23
live73 = live79.live73
live72 = live73.live72

WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)

_INSTALLED = False
_previous_markup = None
_previous_callback = None


def _esc(value):
    return html.escape(str(value or ""))


def _tomorrow(now=None):
    now = now or datetime.now(bot.TIMEZONE)
    return now.date() + timedelta(days=1)


def _events(day):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT event_type, lesson_number, event_time, topic
            FROM course_schedule
            WHERE active = 1 AND event_date = ?
            ORDER BY event_time
            """,
            (day.isoformat(),),
        ).fetchall()


def _tasks(day):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, task_text, start_date, reminder_time
            FROM admin_tasks
            WHERE completed_at IS NULL AND start_date <= ?
            ORDER BY start_date, reminder_time, id
            """,
            (day.isoformat(),),
        ).fetchall()


def _short(text, width=28):
    value = str(text or "Задача").replace("\n", " ").strip()
    return value if len(value) <= width else value[: width - 1] + "…"


def _start_label(start_date, day):
    if str(start_date) == day.isoformat():
        return ""
    try:
        shown = datetime.strptime(str(start_date), "%Y-%m-%d").strftime("%d.%m")
    except Exception:
        shown = str(start_date or "")
    return f" <i>(с {_esc(shown)})</i>"


def tomorrow_text(now=None):
    day = _tomorrow(now)
    events = _events(day)
    tasks = _tasks(day)

    lines = [
        "🌅 <b>Завтра</b>",
        f"{day.strftime('%d.%m.%Y')} · {WEEKDAYS[day.weekday()]}",
        "",
        "📅 <b>Расписание</b>",
    ]

    if events:
        for event_type, lesson_number, event_time, topic in events:
            if event_type == "lesson":
                lines.extend(
                    [
                        f"🎓 <b>{_esc(event_time)} — урок №{lesson_number}</b>",
                        f"Тема: {_esc(topic)}",
                    ]
                )
            elif event_type == "probnik":
                lines.append(f"📝 <b>{_esc(event_time)} — {_esc(topic)}</b>")
            else:
                lines.append(f"• {_esc(event_time)} — {_esc(topic)}")
    else:
        lines.append("• По расписанию ЕГЭ БЛИЗКО событий нет.")

    lines.extend(["", "🗒 <b>Твои задачи на завтра</b>"])
    if tasks:
        for _task_id, task_text, start_date, reminder_time in tasks:
            lines.append(
                f"• {_esc(reminder_time or '10:00')} — {_esc(task_text)}"
                f"{_start_label(start_date, day)}"
            )
    else:
        lines.append("✅ Активных задач на завтра нет.")

    return "\n".join(lines)


def tomorrow_markup(now=None):
    day = _tomorrow(now)
    rows = [[InlineKeyboardButton("🔄 Обновить", callback_data="cab:tomorrow")]]

    for task_id, task_text, _start_date, _reminder_time in _tasks(day)[:6]:
        rows.append(
            [
                InlineKeyboardButton(
                    f"✅ {_short(task_text)}",
                    callback_data=f"cab:tomorrowtaskdone:{int(task_id)}",
                )
            ]
        )

    rows.extend(
        [
            [
                InlineKeyboardButton("📍 Сегодня", callback_data="cab:today"),
                InlineKeyboardButton("🗒 Задачи", callback_data="cab:tasks"),
            ],
            [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
        ]
    )
    return InlineKeyboardMarkup(rows)


def cabinet_markup_with_tomorrow():
    base = _previous_markup()
    rows = [list(row) for row in base.inline_keyboard]

    if any(
        getattr(button, "callback_data", None) == "cab:tomorrow"
        for row in rows
        for button in row
    ):
        return InlineKeyboardMarkup(rows)

    tomorrow_button = InlineKeyboardButton("🌅 Завтра", callback_data="cab:tomorrow")
    for index, row in enumerate(rows):
        if any(getattr(button, "callback_data", None) == "cab:today" for button in row):
            if len(row) < 2:
                row.append(tomorrow_button)
            else:
                rows.insert(index + 1, [tomorrow_button])
            break
    else:
        rows.insert(
            0,
            [
                InlineKeyboardButton("📍 Сегодня", callback_data="cab:today"),
                tomorrow_button,
            ],
        )

    return InlineKeyboardMarkup(rows)


async def cabinet_callback_with_tomorrow(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return await _previous_callback(update, context)

    data = str(query.data or "")

    if data == "cab:tomorrow":
        await query.answer()
        await query.edit_message_text(
            tomorrow_text(),
            parse_mode="HTML",
            reply_markup=tomorrow_markup(),
        )
        return

    if data.startswith("cab:tomorrowtaskdone:"):
        try:
            task_id = int(data.rsplit(":", 1)[1])
        except Exception:
            await query.answer("Не получилось определить задачу")
            return

        task_text = live72._complete_task(task_id)
        await query.answer("Задача выполнена ✅" if task_text else "Задача не найдена")
        await query.edit_message_text(
            tomorrow_text(),
            parse_mode="HTML",
            reply_markup=tomorrow_markup(),
        )
        try:
            await live73._refresh_task_list(context)
        except Exception:
            pass
        try:
            await live73._refresh_today(context)
        except Exception:
            pass
        return

    return await _previous_callback(update, context)


def install():
    global _INSTALLED, _previous_markup, _previous_callback
    if _INSTALLED:
        return

    _previous_markup = live23.cabinet_markup
    _previous_callback = live23.cabinet_callback
    live23.cabinet_markup = cabinet_markup_with_tomorrow
    live23.cabinet_callback = cabinet_callback_with_tomorrow
    _INSTALLED = True
    print("Tomorrow dashboard ready: schedule + tasks", flush=True)
