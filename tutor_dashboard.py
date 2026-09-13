import html
import sqlite3
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90
import run_bot_live94  # noqa: F401

bot = live90.bot
live23 = live90.live23
live6 = live90.live79.live24.live6


def _active_reminders():
    live6.ensure_tutor_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, reminder_text, schedule_kind, run_date, run_time,
                   weekdays, last_sent_key
            FROM tutor_reminders
            WHERE active = 1
            ORDER BY run_time, id
            """
        ).fetchall()


def _applies_on(row, target_date):
    _rid, _text, kind, run_date, _run_time, weekdays, _last_sent = row
    if kind == "once":
        return run_date == target_date.isoformat()
    if kind == "daily":
        return True
    if kind == "weekly":
        allowed = {
            int(value)
            for value in str(weekdays or "").split(",")
            if str(value).strip().isdigit()
        }
        return target_date.weekday() in allowed
    return False


def _short(text, width=80):
    value = " ".join(str(text or "").split())
    return value if len(value) <= width else value[: width - 1] + "…"


def _day_block(target_date, reminders):
    day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    rows = [row for row in reminders if _applies_on(row, target_date)]
    title = f"{day_names[target_date.weekday()]} {target_date.strftime('%d.%m')}"
    if not rows:
        return f"<b>{title}</b>\n— уведомлений нет"

    today_key = datetime.now(bot.TIMEZONE).date().isoformat()
    lines = [f"<b>{title}</b>"]
    for _rid, text, _kind, _run_date, run_time, _weekdays, last_sent_key in rows:
        sent = (
            target_date.isoformat() == today_key
            and str(last_sent_key or "").startswith(f"{today_key} {run_time}")
        )
        marker = "✅" if sent else "🔔"
        lines.append(f"{marker} {html.escape(str(run_time))} — {html.escape(_short(text))}")
    return "\n".join(lines)


def _status_text():
    row = live6.get_tutor_settings()
    reminders = _active_reminders()
    if row and row[0]:
        name = str(row[2] or row[1] or "Тьютор").strip()
        status = f"✅ Подключён: <b>{html.escape(name)}</b>"
    else:
        status = "⚠️ Тьютор не подключён"
    today = datetime.now(bot.TIMEZONE).date()
    today_count = sum(1 for row in reminders if _applies_on(row, today))
    return (
        "👩‍🏫 <b>Тьютор</b>\n\n"
        f"{status}\n"
        f"Активных уведомлений: <b>{len(reminders)}</b>\n"
        f"На сегодня: <b>{today_count}</b>\n\n"
        "Здесь отображается фактическое расписание из базы tutor_reminders."
    )


def _menu_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📍 Сегодня", callback_data="cab:tutor:today"),
            InlineKeyboardButton("📅 7 дней", callback_data="cab:tutor:week"),
        ],
        [InlineKeyboardButton("📋 Все активные", callback_data="cab:tutor:all")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def _today_text():
    today = datetime.now(bot.TIMEZONE).date()
    return "👩‍🏫 <b>Уведомления тьютора сегодня</b>\n\n" + _day_block(today, _active_reminders())


def _week_text():
    today = datetime.now(bot.TIMEZONE).date()
    reminders = _active_reminders()
    blocks = [_day_block(today + timedelta(days=offset), reminders) for offset in range(7)]
    return "👩‍🏫 <b>Уведомления тьютора — 7 дней</b>\n\n" + "\n\n".join(blocks)


def _all_text():
    reminders = _active_reminders()
    if not reminders:
        return "👩‍🏫 <b>Все активные уведомления</b>\n\nАктивных уведомлений сейчас нет."
    lines = ["👩‍🏫 <b>Все активные уведомления</b>", ""]
    for reminder_id, text, kind, run_date, run_time, weekdays, last_sent_key in reminders:
        if kind == "once":
            schedule = f"{run_date} {run_time}"
        elif kind == "daily":
            schedule = f"каждый день {run_time}"
        else:
            names = {0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"}
            days = [
                names.get(int(value), str(value))
                for value in str(weekdays or "").split(",")
                if str(value).strip().isdigit()
            ]
            schedule = f"{', '.join(days)} {run_time}"
        lines.append(f"<b>#{reminder_id}</b> · {html.escape(schedule)}")
        lines.append(html.escape(_short(text, 160)))
        if last_sent_key:
            lines.append(f"Последняя отправка: {html.escape(str(last_sent_key))}")
        lines.append("")
    return "\n".join(lines).rstrip()


_previous_markup = live23.cabinet_markup


def cabinet_markup_with_tutor():
    base = _previous_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:tutor"
        for row in rows for button in row
    ):
        insert_at = max(0, len(rows) - 1)
        rows.insert(insert_at, [InlineKeyboardButton("👩‍🏫 Тьютор", callback_data="cab:tutor")])
    return InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_tutor

_previous_callback = live23.cabinet_callback


async def cabinet_callback_with_tutor(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")
    if data == "cab:tutor":
        await query.answer()
        await query.edit_message_text(_status_text(), parse_mode="HTML", reply_markup=_menu_markup())
        return
    if data == "cab:tutor:today":
        await query.answer()
        await query.edit_message_text(_today_text(), parse_mode="HTML", reply_markup=_menu_markup())
        return
    if data == "cab:tutor:week":
        await query.answer()
        await query.edit_message_text(_week_text(), parse_mode="HTML", reply_markup=_menu_markup())
        return
    if data == "cab:tutor:all":
        await query.answer()
        await query.edit_message_text(_all_text(), parse_mode="HTML", reply_markup=_menu_markup())
        return
    return await _previous_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_tutor

print("Tutor reminders dashboard ready", flush=True)
