import html
import re
import secrets
import sqlite3
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import run_bot_live90 as live90

live79 = live90.live79
live23 = live79.live23
live7 = live79.live7
bot = live90.bot

NO_DATE = "9999-12-31"

KIND_LABELS = {
    "task": "📋 Работа",
    "content": "💡 Контент",
    "tech": "🛠 Техническое",
}

PREFIXES = {
    "работа": "task",
    "рабочее": "task",
    "задача": "task",
    "контент": "content",
    "тех": "tech",
    "техническое": "tech",
    "техническая": "tech",
    "технические": "tech",
}

MONTHS = {
    "января": 1,
    "январь": 1,
    "февраля": 2,
    "февраль": 2,
    "марта": 3,
    "март": 3,
    "апреля": 4,
    "апрель": 4,
    "мая": 5,
    "май": 5,
    "июня": 6,
    "июнь": 6,
    "июля": 7,
    "июль": 7,
    "августа": 8,
    "август": 8,
    "сентября": 9,
    "сентябрь": 9,
    "октября": 10,
    "октябрь": 10,
    "ноября": 11,
    "ноябрь": 11,
    "декабря": 12,
    "декабрь": 12,
}

SEEDED_CONTENT_KEYS = (
    "content-reels-bot-implementation-2026-09-15",
    "content-travel-work-dog-2026-09-15",
    "content-reels-chat-sasha-2026-09-15",
    "content-post-connection-students-2026-09-15",
)


def _admin_private(update):
    return (
        update.effective_chat
        and update.effective_chat.type == "private"
        and bot.user_is_admin(update)
    )


def _parse_prefix(text):
    match = re.match(
        r"^\s*(контент|работа|рабочее|задача|тех|техническое|техническая|технические)\s*(?:[:\-—–]\s*)?(.+?)\s*$",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None, str(text or "").strip()
    return PREFIXES.get(match.group(1).lower()), match.group(2).strip()


def _clean_spaces(text):
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"^[\s,;:—–\-]+|[\s,;:—–\-]+$", "", value)
    return value.strip()


def _extract_schedule(text):
    now = datetime.now(bot.TIMEZONE)
    work = str(text or "").strip()
    due_date = None
    due_time = None

    relative_patterns = (
        (r"\bпослезавтра\b", 2),
        (r"\bзавтра\b", 1),
        (r"\bсегодня\b", 0),
    )
    for pattern, days in relative_patterns:
        if re.search(pattern, work, flags=re.IGNORECASE):
            due_date = now.date() + timedelta(days=days)
            work = re.sub(pattern, " ", work, count=1, flags=re.IGNORECASE)
            break

    if due_date is None:
        m = re.search(r"\b([0-3]?\d)[./]([01]?\d)(?:[./](\d{2,4}))?\b", work)
        if m:
            day = int(m.group(1))
            month = int(m.group(2))
            year_text = m.group(3)
            year = now.year
            if year_text:
                year = int(year_text)
                if year < 100:
                    year += 2000
            try:
                candidate = now.date().replace(year=year, month=month, day=day)
                if not year_text and candidate < now.date():
                    candidate = candidate.replace(year=year + 1)
                due_date = candidate
                work = (work[: m.start()] + " " + work[m.end() :]).strip()
            except ValueError:
                pass

    if due_date is None:
        month_names = "|".join(MONTHS)
        m = re.search(
            rf"\b([0-3]?\d)\s+({month_names})(?:\s+(\d{{4}}))?\b",
            work,
            flags=re.IGNORECASE,
        )
        if m:
            day = int(m.group(1))
            month = MONTHS[m.group(2).lower()]
            year = int(m.group(3)) if m.group(3) else now.year
            try:
                candidate = now.date().replace(year=year, month=month, day=day)
                if not m.group(3) and candidate < now.date():
                    candidate = candidate.replace(year=year + 1)
                due_date = candidate
                work = (work[: m.start()] + " " + work[m.end() :]).strip()
            except ValueError:
                pass

    time_match = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", work)
    if time_match:
        due_time = f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
        work = (work[: time_match.start()] + " " + work[time_match.end() :]).strip()
    else:
        time_match = re.search(
            r"\bв\s+([01]?\d|2[0-3])\b(?!\s*(?:класс|классе|класса|классу))",
            work,
            flags=re.IGNORECASE,
        )
        if time_match:
            due_time = f"{int(time_match.group(1)):02d}:00"
            work = (work[: time_match.start()] + " " + work[time_match.end() :]).strip()

    if due_time and due_date is None:
        hour, minute = map(int, due_time.split(":"))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        due_date = candidate.date()

    if due_date is not None and due_time is None:
        due_time = "10:00"

    title = _clean_spaces(work)
    if due_date is None:
        return title, NO_DATE, "10:00"
    return title, due_date.isoformat(), due_time or "10:00"


def _save_task(kind, text):
    live79.live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    title, start_date, reminder_time = _extract_schedule(text)
    if not title:
        raise ValueError("empty task")
    now = datetime.now(bot.TIMEZONE)
    task_key = f"quick-{kind}-{now.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO admin_tasks
                (task_key, task_text, start_date, reminder_time, created_at, task_kind)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_key,
                title,
                start_date,
                reminder_time,
                now.isoformat(),
                kind,
            ),
        )
        conn.commit()
    return title, start_date, reminder_time


def _schedule_text(start_date, reminder_time):
    if start_date == NO_DATE:
        return "без даты и напоминания"
    try:
        shown = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        shown = start_date
    return f"{shown} в {reminder_time}"


def _after_save_markup():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Добавить ещё", callback_data="cab:qtask:new")],
            [InlineKeyboardButton("🗒 Открыть задачи", callback_data="cab:tasks")],
        ]
    )


async def _send_saved(message, kind, text):
    title, start_date, reminder_time = _save_task(kind, text)
    await message.reply_text(
        f"✅ Добавила в {KIND_LABELS[kind]}\n\n"
        f"• {title}\n"
        f"⏰ {_schedule_text(start_date, reminder_time)}",
        reply_markup=_after_save_markup(),
    )


def _choose_kind_markup():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📋 Работа", callback_data="cab:qtask:choose:task"),
                InlineKeyboardButton("💡 Контент", callback_data="cab:qtask:choose:content"),
            ],
            [InlineKeyboardButton("🛠 Техническое", callback_data="cab:qtask:choose:tech")],
            [InlineKeyboardButton("✖️ Отмена", callback_data="cab:qtask:cancel")],
        ]
    )


def _prompt_markup():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✖️ Отмена", callback_data="cab:qtask:cancel")]]
    )


async def _start_quick_task(message, context, fixed_kind=None):
    context.user_data["quick_task_state"] = {
        "awaiting_text": True,
        "fixed_kind": fixed_kind,
    }
    if fixed_kind:
        label = KIND_LABELS[fixed_kind]
        text = (
            f"{label}\n\n"
            "Напиши задачу одним сообщением.\n"
            "Можно сразу добавить дату и время.\n\n"
            "Например:\n"
            "Снять рилс про поездку завтра в 18:00\n\n"
            "Если дату не укажешь — просто сохраню идею без напоминания."
        )
    else:
        text = (
            "➕ Быстрая задача\n\n"
            "Напиши всё одним сообщением, начиная с раздела:\n\n"
            "• контент — снять рилс про поездку\n"
            "• работа — проверить домашки завтра\n"
            "• тех — проверить уведомления 20 сентября в 18:00\n\n"
            "Если дату не укажешь — задача сохранится без напоминания."
        )
    await message.reply_text(text, reply_markup=_prompt_markup())


_original_text_router = live7.student_text_router


async def student_text_router_with_quick_tasks(update, context):
    if not update.message or not update.message.text:
        return await _original_text_router(update, context)

    if not _admin_private(update):
        return await _original_text_router(update, context)

    text = update.message.text.strip()
    if text == "➕ Быстрая задача":
        await _start_quick_task(update.message, context)
        return

    state = context.user_data.get("quick_task_state")
    if not state or not state.get("awaiting_text"):
        return await _original_text_router(update, context)

    if text.lower() in {"отмена", "отменить", "✖️ отмена"}:
        context.user_data.pop("quick_task_state", None)
        await update.message.reply_text("Отменила.")
        return

    fixed_kind = state.get("fixed_kind")
    if fixed_kind:
        context.user_data.pop("quick_task_state", None)
        try:
            await _send_saved(update.message, fixed_kind, text)
        except ValueError:
            await update.message.reply_text("Не вижу текста задачи. Напиши её ещё раз.")
        return

    kind, body = _parse_prefix(text)
    if kind:
        context.user_data.pop("quick_task_state", None)
        try:
            await _send_saved(update.message, kind, body)
        except ValueError:
            await update.message.reply_text("Не вижу текста задачи. Напиши её ещё раз.")
        return

    title, start_date, reminder_time = _extract_schedule(text)
    if not title:
        await update.message.reply_text("Не вижу текста задачи. Напиши её ещё раз.")
        return

    context.user_data.pop("quick_task_state", None)
    context.user_data["quick_task_pending"] = {
        "title": title,
        "start_date": start_date,
        "reminder_time": reminder_time,
    }
    await update.message.reply_text(
        "Куда сохранить эту задачу?",
        reply_markup=_choose_kind_markup(),
    )


live7.student_text_router = student_text_router_with_quick_tasks


_original_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_quick_tasks(update, context):
    query = update.callback_query
    if not query or not _admin_private(update):
        return await _original_cabinet_callback(update, context)

    data = str(query.data or "")

    if data == "cab:qtask:new":
        await query.answer()
        await _start_quick_task(query.message, context)
        return

    if data.startswith("cab:qtask:add:"):
        kind = data.rsplit(":", 1)[1]
        if kind not in KIND_LABELS:
            await query.answer("Не получилось определить раздел")
            return
        await query.answer()
        await _start_quick_task(query.message, context, fixed_kind=kind)
        return

    if data.startswith("cab:qtask:choose:"):
        kind = data.rsplit(":", 1)[1]
        pending = context.user_data.pop("quick_task_pending", None)
        if kind not in KIND_LABELS or not pending:
            await query.answer("Задача уже не ожидает сохранения")
            return
        await query.answer()
        now = datetime.now(bot.TIMEZONE)
        task_key = f"quick-{kind}-{now.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO admin_tasks
                    (task_key, task_text, start_date, reminder_time, created_at, task_kind)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_key,
                    pending["title"],
                    pending["start_date"],
                    pending["reminder_time"],
                    now.isoformat(),
                    kind,
                ),
            )
            conn.commit()
        await query.edit_message_text(
            f"✅ Добавила в {KIND_LABELS[kind]}\n\n"
            f"• {pending['title']}\n"
            f"⏰ {_schedule_text(pending['start_date'], pending['reminder_time'])}",
            reply_markup=_after_save_markup(),
        )
        return

    if data == "cab:qtask:cancel":
        context.user_data.pop("quick_task_state", None)
        context.user_data.pop("quick_task_pending", None)
        await query.answer("Отменила")
        try:
            await query.edit_message_text("✖️ Добавление задачи отменено.")
        except Exception:
            pass
        return

    return await _original_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_quick_tasks


_original_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_quick_task():
    base = _original_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        button.callback_data == "cab:qtask:new"
        for row in rows
        for button in row
        if getattr(button, "callback_data", None)
    ):
        rows.insert(0, [InlineKeyboardButton("➕ Быстрая задача", callback_data="cab:qtask:new")])
    return InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_quick_task


_original_tasks_menu_markup = live79._tasks_menu_markup


def tasks_menu_markup_with_quick_task():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Быстрая задача", callback_data="cab:qtask:new")],
            [
                InlineKeyboardButton("📋 Работа", callback_data="cab:tasks:active"),
                InlineKeyboardButton("✅ Выполненные", callback_data="cab:tasks:done"),
            ],
            [
                InlineKeyboardButton("💡 Контент", callback_data="cab:tasks:content"),
                InlineKeyboardButton("🛠 Техническое", callback_data="cab:tasks:tech"),
            ],
            [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
        ]
    )


live79._tasks_menu_markup = tasks_menu_markup_with_quick_task


_original_active_markup = live79._active_markup


def active_markup_with_add(rows, kind):
    base = _original_active_markup(rows, kind)
    buttons = [list(row) for row in base.inline_keyboard]
    label = {
        "task": "➕ Добавить работу",
        "content": "➕ Добавить идею",
        "tech": "➕ Добавить техническую",
    }.get(kind, "➕ Добавить сюда")
    insert_at = max(0, len(buttons) - 1)
    buttons.insert(
        insert_at,
        [InlineKeyboardButton(label, callback_data=f"cab:qtask:add:{kind}")],
    )
    return InlineKeyboardMarkup(buttons)


live79._active_markup = active_markup_with_add


_original_task_rows = live79._task_rows


def task_rows_no_date_first(kind="task", completed=False, limit=None):
    if completed:
        return _original_task_rows(kind, completed=True, limit=limit)
    live79.ensure_task_sections()
    sql = """
        SELECT id, task_text, start_date, reminder_time, completed_at
        FROM admin_tasks
        WHERE task_kind = ? AND completed_at IS NULL
        ORDER BY
            CASE WHEN start_date = ? THEN 0 ELSE 1 END,
            start_date,
            reminder_time,
            id DESC
    """
    params = [str(kind), NO_DATE]
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(sql, params).fetchall()


live79._task_rows = task_rows_no_date_first


def table_text_with_no_date(kind, title):
    all_rows = live79._task_rows(kind)

    # Content is a capture inbox: Maria needs to see and complete every idea
    # from the same screen. Other task sections keep the compact first-page view.
    rows = all_rows if kind == "content" else all_rows[: live79.TASK_PAGE_SIZE]
    if not rows:
        return f"<b>{title}</b>\n\n✅ Здесь пока пусто.", rows

    table = ["№ | Задача                   | Дата  | Время", "--+--------------------------+-------+------"]
    for idx, (_task_id, task_text, start_date, reminder_time, _completed_at) in enumerate(rows, 1):
        task_col = live79._short(task_text, 24).ljust(24)
        if start_date == NO_DATE:
            date_col = "—"
            time_col = "—"
        else:
            date_col = live79._date_short(start_date)
            time_col = str(reminder_time or "10:00")[:5]
        table.append(f"{idx} | {task_col} | {date_col:5} | {time_col:5}")

    extra = len(all_rows) - len(rows)
    text = f"<b>{title}</b>\n\n<pre>{html.escape(chr(10).join(table))}</pre>"
    if kind == "content":
        text += f"\nПоказаны все активные идеи: {len(rows)}."
    elif extra > 0:
        text += f"\nЕщё задач: {extra}. Сейчас показываю первые {live79.TASK_PAGE_SIZE}."
    text += "\n\nНажми кнопку с номером выполненной задачи — она сразу перейдёт в «✅ Выполненные»."
    return text, rows


live79._table_text = table_text_with_no_date


def install():
    live79.live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()

    placeholders = ",".join("?" for _ in SEEDED_CONTENT_KEYS)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            f"""
            UPDATE admin_tasks
            SET start_date = ?, reminder_time = '10:00'
            WHERE task_key IN ({placeholders})
              AND completed_at IS NULL
            """,
            (NO_DATE, *SEEDED_CONTENT_KEYS),
        )
        conn.commit()

    live23.ADMIN_KEYBOARD = ReplyKeyboardMarkup(
        [["👩‍🏫 Кабинет Маши", "➕ Быстрая задача"]],
        resize_keyboard=True,
        is_persistent=True,
    )

    print("Admin quick tasks ready: one tap -> category -> task; dates parsed without AI", flush=True)
