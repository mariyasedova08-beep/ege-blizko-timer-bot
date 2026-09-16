"""Student feedback survey for EGE BLIZKO, scheduled for 2026-10-01.

The survey is sent privately to every active Telegram-linked student. Answers,
progress and delivery status are stored in the CoreApp SQLite database. The
admin cabinet exposes a compact summary and per-student answers.
"""
from datetime import date, datetime, time
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

import run_bot_live90 as live90

bot = live90.bot
live23 = live90.live23

SURVEY_KEY = "student_feedback_2026_10_01"
SURVEY_DATE = date(2026, 10, 1)
SEND_TIME = time(17, 0)
SEND_TIME_TEXT = "17:00"

QUESTIONS = (
    {
        "key": "lesson_clarity",
        "text": "1/6. Насколько тебе сейчас понятны наши уроки?\n\n1 — часто ничего не понимаю\n5 — почти всё понятно",
        "type": "choice",
        "options": (("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5")),
    },
    {
        "key": "hardest_now",
        "text": "2/6. Что сейчас самое сложное в химии или подготовке?\n\nНапиши своими словами — можно совсем коротко.",
        "type": "text",
    },
    {
        "key": "homework_amount",
        "text": "3/6. Как тебе объём домашней работы?",
        "type": "choice",
        "options": (("low", "Хочется больше"), ("ok", "В самый раз"), ("high", "Слишком много")),
    },
    {
        "key": "question_comfort",
        "text": "4/6. Насколько тебе комфортно задавать вопросы на уроке?\n\n1 — совсем некомфортно\n5 — могу спокойно спрашивать",
        "type": "choice",
        "options": (("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5")),
    },
    {
        "key": "progress_feeling",
        "text": "5/6. Как ты сам(а) оцениваешь свой прогресс сейчас?\n\n1 — прогресса почти не чувствую\n5 — вижу большой прогресс",
        "type": "choice",
        "options": (("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5")),
    },
    {
        "key": "change_request",
        "text": "6/6. Что тебе хотелось бы изменить или добавить в занятиях/подготовке?\n\nМожно написать любую мысль. Если всё устраивает — так и напиши 💗",
        "type": "text",
    },
)
QUESTION_BY_KEY = {q["key"]: q for q in QUESTIONS}


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS student_survey_deliveries (
                survey_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                student_name TEXT,
                status TEXT NOT NULL CHECK(status IN ('sent','failed')),
                sent_at TEXT,
                error TEXT,
                PRIMARY KEY(survey_key, telegram_user_id)
            );

            CREATE TABLE IF NOT EXISTS student_survey_sessions (
                survey_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                student_name TEXT,
                current_index INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                PRIMARY KEY(survey_key, telegram_user_id)
            );

            CREATE TABLE IF NOT EXISTS student_survey_answers (
                survey_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                question_key TEXT NOT NULL,
                answer_code TEXT,
                answer_text TEXT,
                answered_at TEXT NOT NULL,
                PRIMARY KEY(survey_key, telegram_user_id, question_key)
            );
            """
        )
        conn.commit()


def _now():
    return datetime.now(bot.TIMEZONE)


def _student_row(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT telegram_user_id,
                   coalesce(nullif(display_name,''), nullif(user_name,''), nullif(user_email,''), 'Ученик') AS student_name
            FROM students
            WHERE active=1 AND telegram_user_id=?
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()


def _recipients():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT telegram_user_id,
                   coalesce(nullif(display_name,''), nullif(user_name,''), nullif(user_email,''), 'Ученик') AS student_name
            FROM students
            WHERE active=1 AND telegram_user_id IS NOT NULL
            ORDER BY lower(coalesce(nullif(display_name,''), nullif(user_name,''), nullif(user_email,''), ''))
            """
        ).fetchall()
    seen = set()
    result = []
    for row in rows:
        uid = int(row["telegram_user_id"])
        if uid in seen:
            continue
        seen.add(uid)
        result.append((uid, row["student_name"] or "Ученик"))
    return result


def _delivery_status(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            "SELECT status FROM student_survey_deliveries WHERE survey_key=? AND telegram_user_id=?",
            (SURVEY_KEY, int(user_id)),
        ).fetchone()


def _record_delivery(user_id, name, status, error=None):
    now = _now().isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO student_survey_deliveries
                (survey_key, telegram_user_id, student_name, status, sent_at, error)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(survey_key, telegram_user_id) DO UPDATE SET
                student_name=excluded.student_name,
                status=excluded.status,
                sent_at=excluded.sent_at,
                error=excluded.error
            """,
            (SURVEY_KEY, int(user_id), name, status, now, error),
        )
        conn.commit()


def _session(user_id):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT * FROM student_survey_sessions
            WHERE survey_key=? AND telegram_user_id=?
            """,
            (SURVEY_KEY, int(user_id)),
        ).fetchone()


def _ensure_session(user_id, fallback_name):
    existing = _session(user_id)
    if existing:
        return existing
    row = _student_row(user_id)
    name = (row["student_name"] if row else None) or fallback_name or "Ученик"
    now = _now().isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO student_survey_sessions
                (survey_key, telegram_user_id, student_name, current_index, started_at, updated_at, completed_at)
            VALUES (?, ?, ?, 0, ?, ?, NULL)
            """,
            (SURVEY_KEY, int(user_id), name, now, now),
        )
        conn.commit()
    return _session(user_id)


def _save_answer(user_id, question, answer_code=None, answer_text=None):
    now = _now().isoformat()
    session = _session(user_id)
    if not session or session["completed_at"]:
        return None
    index = int(session["current_index"])
    if index >= len(QUESTIONS) or QUESTIONS[index]["key"] != question["key"]:
        return None
    next_index = index + 1
    completed = now if next_index >= len(QUESTIONS) else None
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO student_survey_answers
                (survey_key, telegram_user_id, question_key, answer_code, answer_text, answered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(survey_key, telegram_user_id, question_key) DO UPDATE SET
                answer_code=excluded.answer_code,
                answer_text=excluded.answer_text,
                answered_at=excluded.answered_at
            """,
            (SURVEY_KEY, int(user_id), question["key"], answer_code, answer_text, now),
        )
        conn.execute(
            """
            UPDATE student_survey_sessions
            SET current_index=?, updated_at=?, completed_at=?
            WHERE survey_key=? AND telegram_user_id=?
            """,
            (next_index, now, completed, SURVEY_KEY, int(user_id)),
        )
        conn.commit()
    return next_index, bool(completed)


def _question_markup(question):
    if question["type"] != "choice":
        return None
    options = list(question["options"])
    if all(code.isdigit() for code, _ in options) and len(options) == 5:
        return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"spoll:a:{question['key']}:{code}") for code, label in options]])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"spoll:a:{question['key']}:{code}")]
        for code, label in options
    ])


async def _send_question(target, user_id, edit=False):
    session = _session(user_id)
    if not session:
        return
    if session["completed_at"] or int(session["current_index"]) >= len(QUESTIONS):
        text = "Спасибо 💗 Я всё сохранила. Твои ответы помогут сделать занятия удобнее и полезнее."
        if edit:
            await target.edit_message_text(text)
        else:
            await target.reply_text(text)
        return
    question = QUESTIONS[int(session["current_index"])]
    markup = _question_markup(question)
    if edit:
        await target.edit_message_text(question["text"], reply_markup=markup)
    else:
        await target.reply_text(question["text"], reply_markup=markup)


async def student_callback(update, context):
    query = update.callback_query
    if not query or not query.data.startswith("spoll:"):
        return
    await query.answer()
    uid = int(update.effective_user.id)
    data = query.data
    if data == f"spoll:start:{SURVEY_KEY}":
        _ensure_session(uid, update.effective_user.full_name or "Ученик")
        await _send_question(query, uid, edit=True)
        raise ApplicationHandlerStop

    if data.startswith("spoll:a:"):
        parts = data.split(":", 3)
        if len(parts) != 4:
            raise ApplicationHandlerStop
        _, _, question_key, code = parts
        question = QUESTION_BY_KEY.get(question_key)
        session = _session(uid)
        if not question or not session or session["completed_at"]:
            await query.edit_message_text("Этот опрос уже завершён 💗")
            raise ApplicationHandlerStop
        index = int(session["current_index"])
        if index >= len(QUESTIONS) or QUESTIONS[index]["key"] != question_key:
            await _send_question(query, uid, edit=True)
            raise ApplicationHandlerStop
        valid_codes = {c for c, _ in question.get("options", ())}
        if code not in valid_codes:
            raise ApplicationHandlerStop
        saved = _save_answer(uid, question, answer_code=code)
        if not saved:
            raise ApplicationHandlerStop
        _next_index, completed = saved
        if completed:
            await query.edit_message_text("Спасибо 💗 Я всё сохранила. Твои ответы помогут сделать занятия удобнее и полезнее.")
            await _notify_admin_completed(context, uid)
        else:
            await _send_question(query, uid, edit=True)
        raise ApplicationHandlerStop


async def student_text(update, context):
    if not update.message or not update.message.text or update.effective_chat.type != "private":
        return
    uid = int(update.effective_user.id)
    session = _session(uid)
    if not session or session["completed_at"]:
        return
    index = int(session["current_index"])
    if index >= len(QUESTIONS):
        return
    question = QUESTIONS[index]
    if question["type"] != "text":
        await update.message.reply_text("Здесь нужно выбрать вариант кнопкой под вопросом 💗")
        raise ApplicationHandlerStop
    answer = " ".join(update.message.text.split()).strip()
    if not answer:
        await update.message.reply_text("Напиши хотя бы пару слов 💗")
        raise ApplicationHandlerStop
    saved = _save_answer(uid, question, answer_text=answer[:1500])
    if not saved:
        raise ApplicationHandlerStop
    _next_index, completed = saved
    if completed:
        await update.message.reply_text("Спасибо 💗 Я всё сохранила. Твои ответы помогут сделать занятия удобнее и полезнее.")
        await _notify_admin_completed(context, uid)
    else:
        await _send_question(update.message, uid, edit=False)
    raise ApplicationHandlerStop


async def _notify_admin_completed(context, user_id):
    admin_id = bot.get_admin_id()
    if not admin_id:
        return
    session = _session(user_id)
    name = session["student_name"] if session else str(user_id)
    try:
        await context.bot.send_message(
            chat_id=int(admin_id),
            text=f"📊 {name} завершил(а) опрос учеников 1 октября. Ответы уже сохранены в кабинете.",
        )
    except Exception:
        pass


def _intro_markup():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Пройти опрос", callback_data=f"spoll:start:{SURVEY_KEY}")
    ]])


def _intro_text():
    return (
        "Привет 💗 Хочу коротко спросить, как тебе сейчас учится.\n\n"
        "Всего 6 вопросов — примерно на 2 минуты. Здесь нет правильных ответов: мне важно понять, что уже хорошо, а что можно сделать удобнее.\n\n"
        "Ответы увижу я, Маша, и буду использовать их только для улучшения занятий."
    )


async def delivery_tick(context):
    ensure_tables()
    now = _now()
    if now.date() != SURVEY_DATE or now.time().replace(tzinfo=None) < SEND_TIME:
        return
    sent = []
    failed = []
    for uid, name in _recipients():
        existing = _delivery_status(uid)
        if existing and existing[0] == "sent":
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=_intro_text(),
                reply_markup=_intro_markup(),
            )
            _record_delivery(uid, name, "sent")
            sent.append(name)
        except Exception as exc:
            _record_delivery(uid, name, "failed", repr(exc)[:500])
            failed.append(name)

    if sent or failed:
        admin_id = bot.get_admin_id()
        if admin_id:
            lines = ["📊 Опрос учеников 1 октября"]
            if sent:
                lines.append(f"✅ Доставлено: {len(sent)}")
            if failed:
                lines.append(f"⚠️ Не доставлено: {len(failed)} — " + ", ".join(failed))
            try:
                await context.bot.send_message(chat_id=int(admin_id), text="\n".join(lines))
            except Exception:
                pass


def _answer_label(question_key, answer_code, answer_text):
    if answer_text:
        return answer_text
    question = QUESTION_BY_KEY.get(question_key)
    if not question:
        return answer_code or "—"
    return dict(question.get("options", ())).get(answer_code, answer_code or "—")


def _admin_summary():
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        delivered = conn.execute(
            "SELECT count(*) c FROM student_survey_deliveries WHERE survey_key=? AND status='sent'",
            (SURVEY_KEY,),
        ).fetchone()["c"]
        failed = conn.execute(
            "SELECT count(*) c FROM student_survey_deliveries WHERE survey_key=? AND status='failed'",
            (SURVEY_KEY,),
        ).fetchone()["c"]
        started = conn.execute(
            "SELECT count(*) c FROM student_survey_sessions WHERE survey_key=?",
            (SURVEY_KEY,),
        ).fetchone()["c"]
        completed = conn.execute(
            "SELECT count(*) c FROM student_survey_sessions WHERE survey_key=? AND completed_at IS NOT NULL",
            (SURVEY_KEY,),
        ).fetchone()["c"]
        answers = conn.execute(
            "SELECT question_key, answer_code FROM student_survey_answers WHERE survey_key=? AND answer_code IS NOT NULL",
            (SURVEY_KEY,),
        ).fetchall()

    numeric = {"lesson_clarity": [], "question_comfort": [], "progress_feeling": []}
    hw = {"low": 0, "ok": 0, "high": 0}
    for row in answers:
        key = row["question_key"]
        code = row["answer_code"]
        if key in numeric and str(code).isdigit():
            numeric[key].append(int(code))
        if key == "homework_amount" and code in hw:
            hw[code] += 1

    def avg(key):
        values = numeric[key]
        return "—" if not values else f"{sum(values) / len(values):.1f}/5"

    return (
        "📊 Опрос учеников • 01.10.2026\n\n"
        f"Доставлено: {delivered}\n"
        f"Не доставлено: {failed}\n"
        f"Начали: {started}\n"
        f"Завершили: {completed}\n\n"
        f"Понятность уроков: {avg('lesson_clarity')}\n"
        f"Комфорт задавать вопросы: {avg('question_comfort')}\n"
        f"Ощущение прогресса: {avg('progress_feeling')}\n\n"
        "Домашняя работа:\n"
        f"• хочется больше — {hw['low']}\n"
        f"• в самый раз — {hw['ok']}\n"
        f"• слишком много — {hw['high']}"
    )


def _session_rows():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT telegram_user_id, student_name, current_index, completed_at
            FROM student_survey_sessions
            WHERE survey_key=?
            ORDER BY completed_at IS NULL, lower(student_name)
            """,
            (SURVEY_KEY,),
        ).fetchall()


def _admin_markup():
    rows = []
    for row in _session_rows()[:35]:
        status = "✅" if row["completed_at"] else f"⏳ {row['current_index']}/6"
        rows.append([InlineKeyboardButton(
            f"{status} {row['student_name']}",
            callback_data=f"cab:studentsurveydetail:{int(row['telegram_user_id'])}",
        )])
    rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="cab:studentsurvey")])
    rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return InlineKeyboardMarkup(rows)


def _student_detail(user_id):
    session = _session(user_id)
    if not session:
        return "Ответы ученика не найдены."
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT question_key, answer_code, answer_text
            FROM student_survey_answers
            WHERE survey_key=? AND telegram_user_id=?
            """,
            (SURVEY_KEY, int(user_id)),
        ).fetchall()
    by_key = {row["question_key"]: row for row in rows}
    lines = [f"📊 {session['student_name']}", ""]
    for index, question in enumerate(QUESTIONS, 1):
        row = by_key.get(question["key"])
        value = "—" if not row else _answer_label(question["key"], row["answer_code"], row["answer_text"])
        short_question = {
            "lesson_clarity": "Понятность уроков",
            "hardest_now": "Самое сложное сейчас",
            "homework_amount": "Объём ДЗ",
            "question_comfort": "Комфорт задавать вопросы",
            "progress_feeling": "Ощущение прогресса",
            "change_request": "Что изменить/добавить",
        }[question["key"]]
        lines.append(f"{index}. {short_question}: {value}")
    lines.append("")
    lines.append("✅ Завершён" if session["completed_at"] else f"⏳ Пройдено {session['current_index']}/6")
    return "\n".join(lines)


_previous_cabinet_markup = None
_previous_cabinet_callback = None
_original_build = None
_installed = False


def _patch_admin_cabinet():
    global _previous_cabinet_markup, _previous_cabinet_callback
    if _previous_cabinet_markup is not None:
        return
    _previous_cabinet_markup = live23.cabinet_markup
    _previous_cabinet_callback = live23.cabinet_callback

    def cabinet_markup_with_student_survey():
        base_markup = _previous_cabinet_markup()
        rows = [list(row) for row in base_markup.inline_keyboard]
        if not any(
            getattr(button, "callback_data", None) == "cab:studentsurvey"
            for row in rows for button in row
        ):
            rows.insert(max(0, len(rows) - 1), [
                InlineKeyboardButton("📊 Опрос учеников 01.10", callback_data="cab:studentsurvey")
            ])
        return InlineKeyboardMarkup(rows)

    async def cabinet_callback_with_student_survey(update, context):
        query = update.callback_query
        if query and query.data == "cab:studentsurvey":
            await query.answer()
            await query.edit_message_text(_admin_summary(), reply_markup=_admin_markup())
            return
        if query and query.data.startswith("cab:studentsurveydetail:"):
            await query.answer()
            try:
                uid = int(query.data.rsplit(":", 1)[1])
            except ValueError:
                return
            await query.edit_message_text(
                _student_detail(uid),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← К результатам", callback_data="cab:studentsurvey")],
                    [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
                ]),
            )
            return
        await _previous_cabinet_callback(update, context)

    live23.cabinet_markup = cabinet_markup_with_student_survey
    live23.cabinet_callback = cabinet_callback_with_student_survey


def _build_with_student_survey(self):
    application = _original_build(self)
    application.add_handler(CallbackQueryHandler(student_callback, pattern=r"^spoll:"), group=-30)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, student_text), group=-30)
    application.job_queue.run_repeating(
        delivery_tick,
        interval=60,
        first=20,
        name="student_feedback_2026_10_01_delivery",
    )
    return application


def install():
    global _original_build, _installed
    if _installed:
        return
    ensure_tables()
    _patch_admin_cabinet()
    _original_build = ApplicationBuilder.build
    ApplicationBuilder.build = _build_with_student_survey
    _installed = True
    print(
        f"Student survey ready: date={SURVEY_DATE.isoformat()} time={SEND_TIME_TEXT} questions={len(QUESTIONS)}",
        flush=True,
    )
