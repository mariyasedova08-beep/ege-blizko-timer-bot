import html
import json
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live85

live85 = run_bot_live85
live84 = live85.live84
live79 = live85.live79
bot = live85.bot
live23 = live85.live23
live7 = live79.live7


SURVEY_QUESTIONS = (
    {
        "key": "work_format",
        "text": "1/10. В каких форматах вы сейчас преподаёте?\n\nМожно выбрать несколько ответов. Отметьте подходящие варианты и нажмите «Готово».",
        "min_choices": 1,
        "max_choices": 3,
        "options": (
            ("individual", "Индивидуально"),
            ("groups", "В группах"),
            ("institution", "В школе или учебном центре"),
        ),
    },
    {
        "key": "subject",
        "text": "2/10. Какой предмет или направление вы преподаёте?\n\nНапишите ответ одним сообщением.",
        "type": "text",
    },
    {
        "key": "student_count",
        "text": "3/10. Сколько учеников вы ведёте сейчас?",
        "options": (
            ("1_10", "1–10"),
            ("11_30", "11–30"),
            ("31_60", "31–60"),
            ("61_plus", "Больше 60"),
        ),
    },
    {
        "key": "main_system",
        "text": "4/10. Где хранится основная информация об учениках, занятиях и оплатах?",
        "options": (
            ("spreadsheets", "Google Таблицы или Excel"),
            ("notebook", "Блокнот или заметки"),
            ("crm", "CRM или сервис преподавателя"),
            ("many_places", "В нескольких разных местах"),
        ),
    },
    {
        "key": "admin_time",
        "text": "5/10. Сколько времени в неделю уходит на организационные задачи вне уроков?",
        "options": (
            ("under_1", "Меньше часа"),
            ("1_3", "1–3 часа"),
            ("3_5", "3–5 часов"),
            ("over_5", "Больше 5 часов"),
        ),
    },
    {
        "key": "biggest_routine",
        "text": (
            "6/10. Какая повторяющаяся задача отнимает у вас больше всего сил?\n\n"
            "Напишите своими словами. Например: оплаты, переносы занятий, проверка ДЗ или сообщения родителям."
        ),
        "type": "text",
    },
    {
        "key": "priority_function",
        "text": "7/10. Какие задачи вы хотели бы автоматизировать в первую очередь?\n\nВыберите 3 самые актуальные для вас задачи и нажмите «Готово».",
        "min_choices": 3,
        "max_choices": 3,
        "options": (
            ("payments", "Оплаты и долги"),
            ("schedule", "Расписание и переносы"),
            ("homework", "Домашние задания"),
            ("attendance", "Посещаемость"),
            ("reminders", "Напоминания ученикам"),
            ("reports", "Отчёты и результаты"),
        ),
    },
    {
        "key": "reminder_mode",
        "text": "8/10. Как бот должен отправлять сообщения ученикам?",
        "options": (
            ("approval", "Сначала показать мне черновик"),
            ("automatic", "Автоматически по моим правилам"),
            ("manual", "Только после моего нажатия"),
            ("none", "Мне не нужны рассылки"),
        ),
    },
    {
        "key": "monthly_price",
        "text": "9/10. Сколько вы готовы платить в месяц за бота, если он действительно экономит время?",
        "options": (
            ("free", "Только бесплатно"),
            ("up_to_500", "До 500 ₽"),
            ("500_1000", "500–1 000 ₽"),
            ("1000_2000", "1 000–2 000 ₽"),
            ("over_2000", "Больше 2 000 ₽"),
        ),
    },
    {
        "key": "pilot",
        "text": "10/10. Хотели бы вы бесплатно протестировать первую версию и дать обратную связь?",
        "options": (
            ("yes", "Да, хочу участвовать"),
            ("maybe", "Возможно, расскажите подробнее"),
            ("no", "Нет"),
        ),
    },
)
SURVEY_BY_KEY = {question["key"]: question for question in SURVEY_QUESTIONS}


def ensure_teacher_survey_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_survey_sessions (
                telegram_user_id INTEGER PRIMARY KEY,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                current_question TEXT,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_survey_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                question_key TEXT NOT NULL,
                answer_code TEXT,
                answer_text TEXT,
                answered_at TEXT NOT NULL,
                UNIQUE(telegram_user_id, question_key)
            )
            """
        )
        conn.commit()


def _survey_now():
    return datetime.now(bot.TIMEZONE).isoformat()


def _start_survey(user_id):
    ensure_teacher_survey_tables()
    now = _survey_now()
    first_key = SURVEY_QUESTIONS[0]["key"]
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("DELETE FROM teacher_survey_answers WHERE telegram_user_id = ?", (int(user_id),))
        conn.execute(
            """
            INSERT INTO teacher_survey_sessions
                (telegram_user_id, started_at, updated_at, current_question, completed_at)
            VALUES (?, ?, ?, ?, NULL)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                started_at = excluded.started_at,
                updated_at = excluded.updated_at,
                current_question = excluded.current_question,
                completed_at = NULL
            """,
            (int(user_id), now, now, first_key),
        )
        conn.commit()


def _survey_session(user_id):
    ensure_teacher_survey_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT current_question, completed_at
            FROM teacher_survey_sessions
            WHERE telegram_user_id = ?
            """,
            (int(user_id),),
        ).fetchone()


def _next_question_key(current_key):
    for index, question in enumerate(SURVEY_QUESTIONS):
        if question["key"] == current_key:
            if index + 1 < len(SURVEY_QUESTIONS):
                return SURVEY_QUESTIONS[index + 1]["key"]
            return None
    return SURVEY_QUESTIONS[0]["key"]


def _save_survey_answer(user_id, question_key, answer_code=None, answer_text=None):
    ensure_teacher_survey_tables()
    if question_key not in SURVEY_BY_KEY:
        return None
    next_key = _next_question_key(question_key)
    now = _survey_now()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO teacher_survey_answers
                (telegram_user_id, question_key, answer_code, answer_text, answered_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id, question_key) DO UPDATE SET
                answer_code = excluded.answer_code,
                answer_text = excluded.answer_text,
                answered_at = excluded.answered_at
            """,
            (int(user_id), question_key, answer_code, answer_text, now),
        )
        conn.execute(
            """
            UPDATE teacher_survey_sessions
            SET updated_at = ?, current_question = ?, completed_at = ?
            WHERE telegram_user_id = ?
            """,
            (now, next_key, now if next_key is None else None, int(user_id)),
        )
        conn.commit()
    return next_key


MULTI_STATE_KEY = "teacher_survey_multi_choices"
PREVIEW_MULTI_STATE_KEY = "teacher_survey_preview_multi_choices"


def _answer_codes(question_key, stored):
    """Read new multi-choice values and existing single-choice answers."""
    if not stored:
        return []
    try:
        decoded = json.loads(stored)
    except (ValueError, TypeError):
        decoded = stored
    codes = decoded if isinstance(decoded, list) else [decoded]
    result = []
    for code in codes:
        if not isinstance(code, str):
            continue
        items = ["individual", "groups"] if question_key == "work_format" and code == "mixed" else [code]
        for item in items:
            if item not in result:
                result.append(item)
    return result


def _multi_selected(context, question, preview=False):
    state_key = PREVIEW_MULTI_STATE_KEY if preview else MULTI_STATE_KEY
    state = context.user_data.get(state_key, {}) if context else {}
    return list(state.get(question["key"], []))


def _multi_action(question, action, selected):
    """Explicit set/unset actions make repeated Telegram deliveries idempotent."""
    ordered = [code for code, _label in question["options"]]
    chosen = set(selected) & set(ordered)
    if action == "done":
        if not question["min_choices"] <= len(chosen) <= question["max_choices"]:
            required = question["min_choices"]
            return selected, False, ("Выберите 3 самые актуальные задачи" if required == 3 else "Выберите хотя бы один вариант")
        return [code for code in ordered if code in chosen], True, None
    if action.startswith("set_"):
        code, add = action[4:], True
    elif action.startswith("unset_"):
        code, add = action[6:], False
    else:
        code, add = action, True  # Buttons sent before the upgrade.
    if question["key"] == "work_format" and code == "mixed":
        chosen.update(("individual", "groups"))
    elif code not in ordered:
        return selected, False, "Этот вариант недоступен"
    elif add:
        chosen.add(code)
    else:
        chosen.discard(code)
    if len(chosen) > question["max_choices"]:
        return selected, False, "Можно выбрать только 3 задачи. Снимите отметку с одной из выбранных."
    return [code for code in ordered if code in chosen], False, None


async def _handle_multi_choice(query, context, question, action, preview=False):
    selected = _multi_selected(context, question, preview)
    updated, done, error = _multi_action(question, action, selected)
    if error:
        await query.answer(error, show_alert=True)
        return None
    if done:
        state_key = PREVIEW_MULTI_STATE_KEY if preview else MULTI_STATE_KEY
        context.user_data.get(state_key, {}).pop(question["key"], None)
        return updated
    await query.answer("Выбор обновлён" if updated != selected else "Выбор уже отмечен")
    if updated != selected:
        state_key = PREVIEW_MULTI_STATE_KEY if preview else MULTI_STATE_KEY
        context.user_data.setdefault(state_key, {})[question["key"]] = updated
        if preview:
            await _send_preview_question(query, context, edit=True)
        else:
            await query.edit_message_text(question["text"], reply_markup=_survey_question_markup(question, selected=updated))
    return None


def _survey_question_markup(question, callback_prefix="cab:sv:a", selected=None):
    if question.get("min_choices"):
        selected = set(selected or [])
        rows = []
        for code, label in question["options"]:
            checked = code in selected
            action = ("unset_" if checked else "set_") + code
            rows.append([InlineKeyboardButton(
                ("✅ " if checked else "⬜️ ") + label,
                callback_data=f"{callback_prefix}:{question['key']}:{action}",
            )])
        count = f"{len(selected)}/3" if question["min_choices"] == 3 else str(len(selected))
        rows.append([InlineKeyboardButton(f"Готово ({count})", callback_data=f"{callback_prefix}:{question['key']}:done")])
        return InlineKeyboardMarkup(rows)
    rows = [
        [InlineKeyboardButton(label, callback_data=f"{callback_prefix}:{question['key']}:{code}")]
        for code, label in question.get("options", ())
    ]
    return InlineKeyboardMarkup(rows) if rows else None


async def _send_survey_question(message, user_id, edit=False, context=None):
    session = _survey_session(user_id)
    if not session or session[1]:
        text = (
            "Спасибо! Ответы уже сохранены 💗\n\n"
            "Если вы захотите пройти опрос заново, снова откройте исходную ссылку."
        )
        if edit:
            await message.edit_message_text(text)
        else:
            await message.reply_text(text)
        return
    question = SURVEY_BY_KEY.get(session[0])
    if not question:
        return
    markup = _survey_question_markup(question, selected=_multi_selected(context, question))
    if edit:
        await message.edit_message_text(question["text"], reply_markup=markup)
    else:
        await message.reply_text(question["text"], reply_markup=markup)


def _welcome_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Начать опрос", callback_data="cab:sv:start")]
    ])


def _welcome_text():
    return (
        "🧑‍🏫 <b>Опрос для преподавателей</b>\n\n"
        "Мы создаём Telegram-бота, который сможет взять на себя часть организационной рутины преподавателя. "
        "Нам важно опираться на реальные задачи, а не на догадки.\n\n"
        "Опрос состоит из 10 коротких вопросов и займёт около 3 минут. "
        "В сводке отображаются ответы без имени и Telegram ID. Отдельных сообщений без вашего согласия не будет."
    )


def _answer_label(question_key, answer_code):
    question = SURVEY_BY_KEY.get(question_key, {})
    return next((label for code, label in question.get("options", ()) if code == answer_code), answer_code)


def survey_admin_text():
    ensure_teacher_survey_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        started, completed = conn.execute(
            """
            SELECT COUNT(*), SUM(CASE WHEN completed_at IS NOT NULL THEN 1 ELSE 0 END)
            FROM teacher_survey_sessions
            """
        ).fetchone()
        counts = conn.execute(
            """
            SELECT a.question_key, a.answer_code, COUNT(*)
            FROM teacher_survey_answers a
            JOIN teacher_survey_sessions s ON s.telegram_user_id = a.telegram_user_id
            WHERE s.completed_at IS NOT NULL AND a.answer_code IS NOT NULL
            GROUP BY a.question_key, a.answer_code
            ORDER BY a.question_key, COUNT(*) DESC
            """
        ).fetchall()
    grouped = {}
    for question_key, answer_code, count in counts:
        for code in _answer_codes(question_key, answer_code):
            totals = grouped.setdefault(question_key, {})
            totals[code] = totals.get(code, 0) + int(count)
    lines = [
        "🧑‍🏫 <b>Опрос преподавателей</b>",
        "",
        f"Начали: <b>{int(started or 0)}</b>",
        f"Завершили: <b>{int(completed or 0)}</b>",
    ]
    report_keys = ("work_format", "student_count", "admin_time", "priority_function", "reminder_mode", "monthly_price", "pilot")
    for key in report_keys:
        question = SURVEY_BY_KEY[key]
        lines.extend(["", f"<b>{html.escape(question['text'].split('.', 1)[-1].strip())}</b>"])
        answers = sorted(grouped.get(key, {}).items(), key=lambda item: -item[1])
        if not answers:
            lines.append("Пока нет ответов")
        else:
            lines.extend(
                f"• {html.escape(str(_answer_label(key, code)))} — {count}"
                for code, count in answers
            )
    return "\n".join(lines)


def survey_admin_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧪 Пройти самой — тест", callback_data="cab:svtest:welcome")],
        [InlineKeyboardButton("🔗 Ссылка для рассылки", callback_data="cab:surveyadmin:link")],
        [InlineKeyboardButton("💬 Ответы о рутине", callback_data="cab:surveyadmin:routines")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="cab:surveyadmin")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def survey_routines_text():
    ensure_teacher_survey_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT a.answer_text
            FROM teacher_survey_answers a
            JOIN teacher_survey_sessions s ON s.telegram_user_id = a.telegram_user_id
            WHERE s.completed_at IS NOT NULL
              AND a.question_key = 'biggest_routine'
              AND trim(coalesce(a.answer_text, '')) <> ''
            ORDER BY a.answered_at DESC
            LIMIT 10
            """
        ).fetchall()
    lines = ["💬 <b>Что отнимает больше всего сил</b>", ""]
    if not rows:
        lines.append("Пока нет завершённых ответов.")
    else:
        for index, (answer,) in enumerate(rows, 1):
            cleaned = " ".join(str(answer or "").split())
            if len(cleaned) > 250:
                cleaned = cleaned[:247] + "…"
            lines.append(f"{index}. {html.escape(cleaned)}")
    return "\n\n".join(lines)


PREVIEW_STATE_KEY = "teacher_survey_preview_question"


def _preview_welcome_text():
    return (
        "🧪 <b>Тестовый проход для Маши</b>\n\n"
        "Ты увидишь те же 10 вопросов, что и преподаватели. "
        "Пробные ответы не записываются в общие результаты. "
        "Тест можно пройти несколько раз.\n\n"
        + _welcome_text()
    )


def _preview_welcome_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Начать тест", callback_data="cab:svtest:start")],
        [InlineKeyboardButton("← К результатам", callback_data="cab:svtest:exit")],
    ])


async def _send_preview_question(message, context, edit=False):
    index = context.user_data.get(PREVIEW_STATE_KEY)
    if index is None:
        text = "Тест не запущен или уже завершён. Нажми «Начать тест»."
        markup = _preview_welcome_markup()
    elif index >= len(SURVEY_QUESTIONS):
        context.user_data.pop(PREVIEW_STATE_KEY, None)
        context.user_data.pop(PREVIEW_MULTI_STATE_KEY, None)
        text = (
            "Тест завершён 💗\n\n"
            "Все 10 вопросов пройдены. Пробные ответы не записаны в результаты преподавателей.\n\n"
            "Можно повторить тест или вернуться к опросу."
        )
        markup = _preview_welcome_markup()
    else:
        question = SURVEY_QUESTIONS[index]
        text = "🧪 Тестовый проход\n\n" + question["text"]
        choices = _survey_question_markup(question, "cab:svtest:a", _multi_selected(context, question, preview=True))
        rows = [list(row) for row in choices.inline_keyboard] if choices else []
        rows.append([InlineKeyboardButton("← Завершить тест", callback_data="cab:svtest:exit")])
        markup = InlineKeyboardMarkup(rows)
    if edit:
        await message.edit_message_text(text, reply_markup=markup)
    else:
        await message.reply_text(text, reply_markup=markup)


async def _preview_callback(update, context):
    query = update.callback_query
    if not live23._admin_private(update):
        await query.answer("Тестовый режим доступен только администратору")
        return
    data = str(query.data or "")
    if data == "cab:svtest:welcome":
        context.user_data.pop(PREVIEW_STATE_KEY, None)
        context.user_data.pop(PREVIEW_MULTI_STATE_KEY, None)
        await query.answer()
        await query.edit_message_text(
            _preview_welcome_text(), parse_mode="HTML", reply_markup=_preview_welcome_markup()
        )
        return
    if data == "cab:svtest:start":
        if context.user_data.get(PREVIEW_STATE_KEY) == 0:
            await query.answer("Тест уже открыт")
            return
        context.user_data[PREVIEW_STATE_KEY] = 0
        context.user_data.pop(PREVIEW_MULTI_STATE_KEY, None)
        await query.answer()
        await _send_preview_question(query, context, edit=True)
        return
    if data == "cab:svtest:exit":
        context.user_data.pop(PREVIEW_STATE_KEY, None)
        context.user_data.pop(PREVIEW_MULTI_STATE_KEY, None)
        await query.answer("Тест закрыт")
        await query.edit_message_text(
            survey_admin_text(), parse_mode="HTML", reply_markup=survey_admin_markup()
        )
        return
    parts = data.split(":", 4)
    index = context.user_data.get(PREVIEW_STATE_KEY)
    question = SURVEY_QUESTIONS[index] if isinstance(index, int) and 0 <= index < len(SURVEY_QUESTIONS) else None
    allowed = {code for code, _label in question.get("options", ())} if question else set()
    if (
        len(parts) != 5 or parts[2] != "a" or not question
        or parts[3] != question["key"]
        or (not question.get("min_choices") and parts[4] not in allowed)
    ):
        await query.answer("Этот вопрос уже закрыт или тест не запущен")
        if index is None:
            await _send_preview_question(query, context, edit=True)
        return
    if question.get("min_choices"):
        selected = await _handle_multi_choice(query, context, question, parts[4], preview=True)
        if selected is None:
            return
    context.user_data[PREVIEW_STATE_KEY] = index + 1
    await query.answer("Ответ принят в тесте")
    await _send_preview_question(query, context, edit=True)


_previous_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_teacher_survey():
    base = _previous_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:surveyadmin"
        for row in rows
        for button in row
    ):
        rows.insert(max(0, len(rows) - 1), [
            InlineKeyboardButton("🧑‍🏫 Опрос преподавателей", callback_data="cab:surveyadmin")
        ])
    return InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_teacher_survey

_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_teacher_survey(update, context):
    query = update.callback_query
    if not query:
        return
    data = str(query.data or "")

    if data.startswith("cab:svtest:"):
        await _preview_callback(update, context)
        return
    if data.startswith("cab:"):
        context.user_data.pop(PREVIEW_STATE_KEY, None)
        context.user_data.pop(PREVIEW_MULTI_STATE_KEY, None)

    if data == "cab:sv:start" and update.effective_chat.type == "private":
        context.user_data.pop(MULTI_STATE_KEY, None)
        _start_survey(update.effective_user.id)
        await query.answer()
        await _send_survey_question(query, update.effective_user.id, edit=True, context=context)
        return

    if data.startswith("cab:sv:a:") and update.effective_chat.type == "private":
        parts = data.split(":", 4)
        if len(parts) != 5:
            await query.answer("Не получилось сохранить ответ")
            return
        question_key, answer_code = parts[3], parts[4]
        session = _survey_session(update.effective_user.id)
        question = SURVEY_BY_KEY.get(question_key)
        allowed = {code for code, _label in question.get("options", ())} if question else set()
        if not session or session[1] or not question or session[0] != question_key:
            await query.answer("Этот вопрос уже закрыт")
            return
        if question.get("min_choices"):
            selected = await _handle_multi_choice(query, context, question, answer_code)
            if selected is None:
                return
            answer_code = json.dumps(selected, ensure_ascii=False)
        elif answer_code not in allowed:
            await query.answer("Этот вариант недоступен")
            return
        next_key = _save_survey_answer(update.effective_user.id, question_key, answer_code=answer_code)
        await query.answer("Ответ сохранён")
        if next_key is None:
            await query.edit_message_text(
                "Спасибо! Опрос завершён 💗\n\n"
                "Ваши ответы помогут сделать действительно полезного помощника для преподавателей."
            )
        else:
            await _send_survey_question(query, update.effective_user.id, edit=True, context=context)
        return

    if data.startswith("cab:surveyadmin"):
        if not live23._admin_private(update):
            return
        if data == "cab:surveyadmin":
            await query.answer()
            await query.edit_message_text(
                survey_admin_text(), parse_mode="HTML", reply_markup=survey_admin_markup()
            )
            return
        if data == "cab:surveyadmin:link":
            me = await context.bot.get_me()
            await query.answer("Ссылка готова")
            await query.message.reply_text(
                "🔗 <b>Ссылка на опрос</b>\n\n"
                f"https://t.me/{me.username}?start=teacher_survey",
                parse_mode="HTML",
            )
            return
        if data == "cab:surveyadmin:routines":
            await query.answer()
            await query.edit_message_text(
                survey_routines_text(),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← К результатам", callback_data="cab:surveyadmin")]
                ]),
            )
            return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_teacher_survey

_previous_start_router = live7.start_router


async def start_router_with_teacher_survey(update, context):
    context.user_data.pop(PREVIEW_STATE_KEY, None)
    context.user_data.pop(PREVIEW_MULTI_STATE_KEY, None)
    if context.args and str(context.args[0] or "").strip().lower() == "teacher_survey_test":
        if not live23._admin_private(update):
            await update.message.reply_text("Тестовый режим доступен только администратору в личном чате.")
            return
        await update.message.reply_text(
            _preview_welcome_text(), parse_mode="HTML", reply_markup=_preview_welcome_markup()
        )
        return
    if (
        update.effective_chat.type == "private"
        and context.args
        and str(context.args[0] or "").strip().lower() == "teacher_survey"
    ):
        await update.message.reply_text(
            _welcome_text(), parse_mode="HTML", reply_markup=_welcome_markup()
        )
        return
    await _previous_start_router(update, context)


live7.start_router = start_router_with_teacher_survey

_previous_text_router = live7.student_text_router


async def text_router_with_teacher_survey(update, context):
    if PREVIEW_STATE_KEY in context.user_data:
        if not live23._admin_private(update):
            context.user_data.pop(PREVIEW_STATE_KEY, None)
            context.user_data.pop(PREVIEW_MULTI_STATE_KEY, None)
        elif update.message and update.message.text:
            answer = " ".join(update.message.text.split()).strip()
            if answer == "👩‍🏫 Кабинет Маши":
                context.user_data.pop(PREVIEW_STATE_KEY, None)
                context.user_data.pop(PREVIEW_MULTI_STATE_KEY, None)
                await _previous_text_router(update, context)
                return
            index = context.user_data[PREVIEW_STATE_KEY]
            question = SURVEY_QUESTIONS[index]
            if question.get("type") != "text":
                await update.message.reply_text("Выбери вариант кнопкой под вопросом.")
                return
            if len(answer) < 2:
                await update.message.reply_text("Напишите, пожалуйста, чуть подробнее.")
                return
            if len(answer) > 1000:
                await update.message.reply_text("Ответ слишком длинный. Сократите его до 1000 символов.")
                return
            context.user_data[PREVIEW_STATE_KEY] = index + 1
            await _send_preview_question(update.message, context)
            return
    if update.effective_chat.type == "private" and update.message and update.message.text:
        session = _survey_session(update.effective_user.id)
        if session and not session[1]:
            question = SURVEY_BY_KEY.get(session[0])
            if question and question.get("type") == "text":
                answer = " ".join(str(update.message.text or "").split()).strip()
                if len(answer) < 2:
                    await update.message.reply_text("Напишите, пожалуйста, чуть подробнее.")
                    return
                if len(answer) > 1000:
                    await update.message.reply_text("Ответ слишком длинный. Сократите его до 1000 символов.")
                    return
                next_key = _save_survey_answer(
                    update.effective_user.id, question["key"], answer_text=answer
                )
                if next_key is None:
                    await update.message.reply_text("Спасибо! Опрос завершён 💗")
                else:
                    await _send_survey_question(update.message, update.effective_user.id, context=context)
                return
    await _previous_text_router(update, context)


live7.student_text_router = text_router_with_teacher_survey


def verify_teacher_survey_wiring():
    """Fail startup if the survey is missing from the actual menu or routers."""
    callbacks = [
        button.callback_data
        for row in live23.cabinet_markup().inline_keyboard
        for button in row
    ]
    checks = (
        callbacks.count("cab:surveyadmin") == 1,
        live23.cabinet_callback is cabinet_callback_with_teacher_survey,
        live7.start_router is start_router_with_teacher_survey,
        live7.student_text_router is text_router_with_teacher_survey,
        any(
            button.callback_data == "cab:svtest:welcome"
            for row in survey_admin_markup().inline_keyboard for button in row
        ),
    )
    if not all(checks):
        raise RuntimeError("Teacher survey menu/router wiring check failed")
    print("LIVE89: survey and preview verified; Q1 multiple answers, Q7 exactly three", flush=True)


if __name__ == "__main__":
    verify_teacher_survey_wiring()
    live79.live71.ensure_molar_access_tables()
    live79.live70.ensure_health_tables()
    live79.live59.ensure_coreapp_webhook_audit_table()
    live79.live31.live25.ensure_lesson_day_before_table()
    live79.live31.live24.ensure_probnik_poll_tables()
    live79.live28.ensure_unanswered_reminder_tables()
    live79.live31.live30.live3.ensure_attendance_tables()
    live79.live31.live30.ensure_auto_attendance_table()
    live79.live31.ensure_personal_homework_reminder_table()
    live79.live17.ensure_acid_tables()
    live79.live24.live18.ensure_acid_reminder_table()
    live79.live34.ensure_attention_tables()
    live79.live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    live79.live73.ensure_admin_task_view_state()
    live79.live35.seed_monday_task()
    live79.live37.update_monday_task_text()
    live79.live39.seed_probnik_return_task()
    live79.live41.ensure_weekly_report_tables()
    live79.live41.seed_current_trainers()
    live79.live48.ensure_metals_tables()
    live79.live48.register_metals_trainer()
    live79.live60.ensure_oxides_tables()
    live79.live60.register_oxides_trainer()
    live79.live43.ensure_probnik_analysis_tables()
    live79.live44.enable_probnik_analysis_now()
    live79.live46.ensure_monthly_auto_report_table()
    live79.live50.seed_molar_mass_task()
    live79.live51.ensure_course_schedule_table()
    live79.live66.seed_zlata_accounting_task()
    live79.live67.ensure_individual_students_table()
    live79.live71.complete_molar_mass_task()
    live79.live74.ensure_notification_catchup_tables()
    live79.live77.ensure_lesson_feedback_tables()
    live79.live78.seed_priority_tasks()
    live84.seed_teacher_product_tasks()
    live85.ensure_payment_tables()
    ensure_teacher_survey_tables()
    live79.live56.log_probnik_cabinet_audit()
    print("Teacher survey ready: 10 questions, anonymous admin summary", flush=True)
    print("Payment tracking ready: grade 11 Excel import, admin preview only", flush=True)
    print("Teacher product first five tasks seeded", flush=True)
    print("Admin tasks separated: active / completed / content / technical", flush=True)
    print("Admin current-task table shows first seven tasks", flush=True)
    print("Completed admin tasks stay completed after restart", flush=True)
    print("Lesson feedback ready: Mon/Wed 20:30, Sun 13:00; summary +1.5h", flush=True)
    print("Group traffic light ready", flush=True)
    print("Restart-safe notification catch-up enabled", flush=True)
    print("Admin task views auto-refresh after completion", flush=True)
    print("Today dashboard ready", flush=True)
    print("Molar mass calculator ready for admin and tutor", flush=True)
    print("Health monitoring and Telegram admin alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live79.live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live79.live24.main()
