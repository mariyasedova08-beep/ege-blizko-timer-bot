"""Lesson recordings for EGE BLIZKO.

Teacher:
Cabinet -> 🎥 Записи уроков -> choose lesson -> attach/replace/delete URL.
Only ADMIN_TELEGRAM_ID may modify recordings.

Students:
My cabinet -> 🎥 Записи уроков -> see only lessons with a saved URL.
"""
import re
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90
import run_bot_live49 as student_cabinet

bot = live90.bot
live7 = live90.live7
live23 = live90.live23

TOTAL_LESSONS = int(getattr(bot, "TOTAL_LESSONS", 108) or 108)
ADMIN_PAGE_SIZE = 10
STUDENT_PAGE_SIZE = 10
STATE_KEY = "lesson_recording_edit"
_INSTALLED = False


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lesson_recordings (
                lesson_number INTEGER PRIMARY KEY,
                recording_url TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by INTEGER
            )
            """
        )
        conn.commit()


def _recording(lesson_number):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT lesson_number,recording_url,updated_at,updated_by
            FROM lesson_recordings
            WHERE lesson_number=?
            """,
            (int(lesson_number),),
        ).fetchone()


def _recording_map():
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT lesson_number,recording_url,updated_at
            FROM lesson_recordings
            ORDER BY lesson_number
            """
        ).fetchall()
    return {
        int(lesson_number): {
            "url": str(url),
            "updated_at": updated_at,
        }
        for lesson_number, url, updated_at in rows
    }


def _saved_rows():
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT lesson_number,recording_url,updated_at
            FROM lesson_recordings
            ORDER BY lesson_number DESC
            """
        ).fetchall()


def _valid_lesson(value):
    try:
        n = int(value)
    except Exception:
        return None
    return n if 1 <= n <= TOTAL_LESSONS else None


def _valid_url(text):
    value = str(text or "").strip()
    if len(value) > 2000:
        return None
    if not re.match(r"^https?://[^\s]+$", value, flags=re.I):
        return None
    return value


def _page_bounds(page, page_size, total):
    pages = max(1, (max(0, total) + page_size - 1) // page_size)
    page = max(0, min(int(page), pages - 1))
    start = page * page_size
    return page, pages, start, min(start + page_size, total)


def _admin_home_markup():
    recordings = _recording_map()
    rows = []
    page, pages, start, end = _page_bounds(0, ADMIN_PAGE_SIZE, TOTAL_LESSONS)
    for lesson in range(start + 1, end + 1):
        mark = "✅" if lesson in recordings else "▫️"
        rows.append([
            InlineKeyboardButton(
                f"{mark} Урок {lesson}",
                callback_data=f"cab:recording:{lesson}:p:{page}",
            )
        ])
    if pages > 1:
        rows.append([
            InlineKeyboardButton("Дальше →", callback_data="cab:recordings:p:1")
        ])
    rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return InlineKeyboardMarkup(rows)


def _admin_page_markup(page):
    recordings = _recording_map()
    page, pages, start, end = _page_bounds(page, ADMIN_PAGE_SIZE, TOTAL_LESSONS)
    rows = []
    for lesson in range(start + 1, end + 1):
        mark = "✅" if lesson in recordings else "▫️"
        rows.append([
            InlineKeyboardButton(
                f"{mark} Урок {lesson}",
                callback_data=f"cab:recording:{lesson}:p:{page}",
            )
        ])
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "← Назад",
                callback_data=f"cab:recordings:p:{page - 1}",
            )
        )
    if page + 1 < pages:
        nav.append(
            InlineKeyboardButton(
                "Дальше →",
                callback_data=f"cab:recordings:p:{page + 1}",
            )
        )
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return InlineKeyboardMarkup(rows)


def _admin_page_text(page):
    recordings = _recording_map()
    page, pages, start, end = _page_bounds(page, ADMIN_PAGE_SIZE, TOTAL_LESSONS)
    saved = len(recordings)
    return (
        "🎥 <b>Записи уроков</b>\n\n"
        f"Прикреплено записей: <b>{saved}/{TOTAL_LESSONS}</b>\n"
        "✅ — ссылка уже есть\n"
        "▫️ — ссылки ещё нет\n\n"
        f"Уроки {start + 1}–{end} · страница {page + 1}/{pages}\n\n"
        "Выбери урок. Ссылки добавляешь и меняешь только ты."
    )


def _admin_lesson_markup(lesson, page):
    row = _recording(lesson)
    buttons = []
    if row:
        buttons.append([
            InlineKeyboardButton("▶️ Открыть запись", url=str(row[1]))
        ])
        buttons.append([
            InlineKeyboardButton(
                "✏️ Заменить ссылку",
                callback_data=f"cab:recordingedit:{lesson}:p:{page}",
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                "🗑 Удалить ссылку",
                callback_data=f"cab:recordingdelete:{lesson}:p:{page}",
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                "➕ Прикрепить ссылку",
                callback_data=f"cab:recordingedit:{lesson}:p:{page}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            "← К записям",
            callback_data=f"cab:recordings:p:{page}",
        )
    ])
    return InlineKeyboardMarkup(buttons)


def _admin_lesson_text(lesson):
    row = _recording(lesson)
    if not row:
        return (
            f"🎥 <b>Урок {lesson}</b>\n\n"
            "▫️ Запись ещё не прикреплена.\n\n"
            "Нажми «Прикрепить ссылку», затем пришли ссылку одним сообщением."
        )
    try:
        updated = datetime.fromisoformat(str(row[2])).astimezone(bot.TIMEZONE)
        updated_text = updated.strftime("%d.%m.%Y %H:%M")
    except Exception:
        updated_text = str(row[2] or "")
    return (
        f"🎥 <b>Урок {lesson}</b>\n\n"
        "✅ Запись прикреплена.\n"
        f"Обновлено: {updated_text}\n\n"
        "Можно открыть запись, заменить ссылку или удалить её."
    )


def _student_page(page):
    rows = _saved_rows()
    total = len(rows)
    page, pages, start, end = _page_bounds(page, STUDENT_PAGE_SIZE, total)
    visible = rows[start:end]
    buttons = [
        [InlineKeyboardButton(f"🎥 Урок {int(lesson)}", url=str(url))]
        for lesson, url, _updated_at in visible
    ]
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "← Новее",
                callback_data=f"triv:studentcab:recordings:p:{page - 1}",
            )
        )
    if page + 1 < pages:
        nav.append(
            InlineKeyboardButton(
                "Старше →",
                callback_data=f"triv:studentcab:recordings:p:{page + 1}",
            )
        )
    if nav:
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton(
            "← В мой кабинет",
            callback_data="triv:studentcab:home",
        )
    ])
    text = (
        "🎥 Записи уроков\n\n"
        f"Доступно записей: {total}\n\n"
        "Нажми на нужный урок — запись откроется по прикреплённой ссылке."
        if total else
        "🎥 Записи уроков\n\n"
        "Пока записей нет. Когда Мария Александровна прикрепит ссылку, она появится здесь."
    )
    return text, InlineKeyboardMarkup(buttons)


def _patch_admin_markup():
    previous = live23.cabinet_markup

    def cabinet_markup_with_recordings():
        markup = previous()
        rows = [list(row) for row in getattr(markup, "inline_keyboard", ())]
        if not any(
            getattr(button, "callback_data", None) == "cab:recordings"
            for row in rows for button in row
        ):
            insert_at = max(0, len(rows) - 1)
            rows.insert(
                insert_at,
                [InlineKeyboardButton("🎥 Записи уроков", callback_data="cab:recordings")],
            )
        return InlineKeyboardMarkup(rows)

    live23.cabinet_markup = cabinet_markup_with_recordings


def _patch_student_markup():
    previous = student_cabinet._student_home_markup

    def student_home_markup_with_recordings():
        markup = previous()
        rows = [list(row) for row in getattr(markup, "inline_keyboard", ())]
        if not any(
            getattr(button, "callback_data", None) == "triv:studentcab:recordings:p:0"
            for row in rows for button in row
        ):
            contact_index = len(rows)
            for idx, row in enumerate(rows):
                if any(
                    str(getattr(button, "url", "") or "").startswith("tg://user")
                    for button in row
                ):
                    contact_index = idx
                    break
            rows.insert(
                contact_index,
                [
                    InlineKeyboardButton(
                        "🎥 Записи уроков",
                        callback_data="triv:studentcab:recordings:p:0",
                    )
                ],
            )
        return InlineKeyboardMarkup(rows)

    student_cabinet._student_home_markup = student_home_markup_with_recordings


def _parse_admin_page(data):
    parts = str(data or "").split(":")
    try:
        if "p" in parts:
            idx = parts.index("p")
            return max(0, int(parts[idx + 1]))
    except Exception:
        pass
    return 0


def _patch_admin_callback():
    previous = live23.cabinet_callback

    async def cabinet_callback_with_recordings(update, context):
        query = update.callback_query
        if not query:
            return await previous(update, context)
        data = str(query.data or "")
        if not data.startswith("cab:recording"):
            return await previous(update, context)
        if not (
            update.effective_chat.type == "private"
            and bot.user_is_admin(update)
        ):
            await query.answer("Недоступно", show_alert=True)
            return

        if data == "cab:recordings":
            await query.answer()
            await query.edit_message_text(
                _admin_page_text(0),
                parse_mode="HTML",
                reply_markup=_admin_page_markup(0),
            )
            return

        if data.startswith("cab:recordings:p:"):
            await query.answer()
            try:
                page = int(data.rsplit(":", 1)[-1])
            except Exception:
                page = 0
            await query.edit_message_text(
                _admin_page_text(page),
                parse_mode="HTML",
                reply_markup=_admin_page_markup(page),
            )
            return

        if data.startswith("cab:recordingedit:"):
            parts = data.split(":")
            lesson = _valid_lesson(parts[2] if len(parts) > 2 else None)
            page = _parse_admin_page(data)
            if not lesson:
                await query.answer("Урок не найден", show_alert=True)
                return
            context.user_data[STATE_KEY] = {
                "lesson": lesson,
                "page": page,
            }
            await query.answer()
            await query.edit_message_text(
                f"🎥 <b>Урок {lesson}</b>\n\n"
                "Пришли ссылку на запись <b>одним сообщением</b>.\n"
                "Подойдут ссылки, начинающиеся с http:// или https://.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "❌ Отмена",
                        callback_data=f"cab:recordingcancel:{lesson}:p:{page}",
                    )
                ]]),
            )
            return

        if data.startswith("cab:recordingcancel:"):
            context.user_data.pop(STATE_KEY, None)
            parts = data.split(":")
            lesson = _valid_lesson(parts[2] if len(parts) > 2 else None)
            page = _parse_admin_page(data)
            await query.answer("Отменено")
            if lesson:
                await query.edit_message_text(
                    _admin_lesson_text(lesson),
                    parse_mode="HTML",
                    reply_markup=_admin_lesson_markup(lesson, page),
                )
            return

        if data.startswith("cab:recordingdeleteconfirm:"):
            parts = data.split(":")
            lesson = _valid_lesson(parts[2] if len(parts) > 2 else None)
            page = _parse_admin_page(data)
            if not lesson:
                await query.answer("Урок не найден", show_alert=True)
                return
            with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                conn.execute(
                    "DELETE FROM lesson_recordings WHERE lesson_number=?",
                    (lesson,),
                )
                conn.commit()
            context.user_data.pop(STATE_KEY, None)
            await query.answer("Ссылка удалена")
            await query.edit_message_text(
                _admin_lesson_text(lesson),
                parse_mode="HTML",
                reply_markup=_admin_lesson_markup(lesson, page),
            )
            return

        if data.startswith("cab:recordingdelete:"):
            parts = data.split(":")
            lesson = _valid_lesson(parts[2] if len(parts) > 2 else None)
            page = _parse_admin_page(data)
            if not lesson:
                await query.answer("Урок не найден", show_alert=True)
                return
            await query.answer()
            await query.edit_message_text(
                f"🗑 Удалить ссылку на запись урока {lesson}?\n\n"
                "У учеников она сразу исчезнет из раздела записей.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🗑 Да, удалить",
                            callback_data=f"cab:recordingdeleteconfirm:{lesson}:p:{page}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "← Не удалять",
                            callback_data=f"cab:recording:{lesson}:p:{page}",
                        )
                    ],
                ]),
            )
            return

        if data.startswith("cab:recording:"):
            parts = data.split(":")
            lesson = _valid_lesson(parts[2] if len(parts) > 2 else None)
            page = _parse_admin_page(data)
            if not lesson:
                await query.answer("Урок не найден", show_alert=True)
                return
            await query.answer()
            await query.edit_message_text(
                _admin_lesson_text(lesson),
                parse_mode="HTML",
                reply_markup=_admin_lesson_markup(lesson, page),
            )
            return

        return await previous(update, context)

    live23.cabinet_callback = cabinet_callback_with_recordings


def _patch_student_callback():
    previous = student_cabinet.student_cabinet_callback

    async def student_cabinet_callback_with_recordings(update, context):
        query = update.callback_query
        if (
            query
            and str(query.data or "").startswith("triv:studentcab:recordings")
        ):
            student = student_cabinet._student_by_telegram(
                update.effective_user.id
            )
            if not student:
                await query.answer("Сначала привяжи Telegram", show_alert=True)
                return
            await query.answer()
            try:
                page = int(str(query.data).rsplit(":", 1)[-1])
            except Exception:
                page = 0
            text, markup = _student_page(page)
            await query.edit_message_text(text, reply_markup=markup)
            return
        return await previous(update, context)

    student_cabinet.student_cabinet_callback = (
        student_cabinet_callback_with_recordings
    )


def _patch_text_router():
    previous = live7.student_text_router

    async def student_text_router_with_recordings(update, context):
        state = context.user_data.get(STATE_KEY)
        if (
            state
            and update.effective_chat.type == "private"
            and bot.user_is_admin(update)
            and update.message
            and update.message.text
        ):
            lesson = _valid_lesson(state.get("lesson"))
            page = int(state.get("page") or 0)
            if not lesson:
                context.user_data.pop(STATE_KEY, None)
                return await previous(update, context)

            url = _valid_url(update.message.text)
            if not url:
                await update.message.reply_text(
                    "Не похоже на ссылку. Пришли полный адрес, начинающийся с "
                    "http:// или https://\n\n"
                    "Чтобы выйти без сохранения, снова открой кабинет и раздел записей."
                )
                return

            now = datetime.now(bot.TIMEZONE).isoformat()
            with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO lesson_recordings(
                        lesson_number,recording_url,updated_at,updated_by
                    ) VALUES(?,?,?,?)
                    ON CONFLICT(lesson_number) DO UPDATE SET
                        recording_url=excluded.recording_url,
                        updated_at=excluded.updated_at,
                        updated_by=excluded.updated_by
                    """,
                    (
                        lesson,
                        url,
                        now,
                        int(update.effective_user.id),
                    ),
                )
                conn.commit()
            context.user_data.pop(STATE_KEY, None)
            await update.message.reply_text(
                f"✅ Запись урока {lesson} сохранена.\n"
                "У учеников она уже появилась в «🎥 Записи уроков».",
                reply_markup=_admin_lesson_markup(lesson, page),
            )
            print(
                f"LESSON_RECORDING saved lesson={lesson} admin={int(update.effective_user.id)}",
                flush=True,
            )
            return

        return await previous(update, context)

    live7.student_text_router = student_text_router_with_recordings


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    ensure_tables()
    _patch_admin_markup()
    _patch_student_markup()
    _patch_admin_callback()
    _patch_student_callback()
    _patch_text_router()
    print(
        f"Lesson recordings ready: teacher edit + student read-only; lessons={TOTAL_LESSONS}",
        flush=True,
    )
