"""Anonymous 3-question student survey for EGE BLIZKO on 2026-09-17.

Students are invited privately. Delivery/completion are tracked only to avoid
repeated invitations, while completed answer sets are stored without Telegram
IDs or student names. The temporary user->response link is deleted immediately
when the survey is completed.
"""
from datetime import date, datetime, time
import sqlite3
import uuid

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

SURVEY_KEY = "anonymous_why_masha_2026_09_17"
SURVEY_DATE = date(2026, 9, 17)
SEND_TIME = time(20, 0)
SEND_TIME_TEXT = "20:00"

QUESTIONS = (
    "1/3. Вспомни момент, когда ты выбирал(а), с кем готовиться к ЕГЭ по химии. Почему в итоге решил(а) заниматься именно со мной?\n\nМожно написать всё, что повлияло: соцсети, стиль общения, отзывы, результаты учеников, подача материала, рекомендации, первое впечатление — или что-то совсем другое.",
    "2/3. Что во мне или в моём подходе показалось тебе отличающимся от других преподавателей, которых ты рассматривал(а)?\n\nДаже если это была какая-то мелочь — мне особенно важны твои собственные формулировки.",
    "3/3. Если бы твой друг сейчас выбирал преподавателя по химии и спросил: «Почему стоит пойти именно к Маше?», что бы ты ему ответил(а)?\n\nНапиши так, как сказал(а) бы это другу — без правильных и красивых формулировок.",
)


def _now():
    return datetime.now(bot.TIMEZONE)


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS anonymous_why_deliveries (
                survey_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('sent','failed')),
                sent_date TEXT NOT NULL,
                error TEXT,
                PRIMARY KEY(survey_key, telegram_user_id)
            );

            CREATE TABLE IF NOT EXISTS anonymous_why_progress (
                survey_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                response_id TEXT NOT NULL,
                current_index INTEGER NOT NULL DEFAULT 0,
                started_date TEXT NOT NULL,
                PRIMARY KEY(survey_key, telegram_user_id)
            );

            CREATE TABLE IF NOT EXISTS anonymous_why_drafts (
                response_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                answer_text TEXT NOT NULL,
                PRIMARY KEY(response_id, question_index)
            );

            CREATE TABLE IF NOT EXISTS anonymous_why_responses (
                response_id TEXT PRIMARY KEY,
                answer_1 TEXT NOT NULL,
                answer_2 TEXT NOT NULL,
                answer_3 TEXT NOT NULL,
                submitted_date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS anonymous_why_completions (
                survey_key TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                completed_date TEXT NOT NULL,
                PRIMARY KEY(survey_key, telegram_user_id)
            );
            """
        )
        conn.commit()


def _active_student(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM students WHERE active=1 AND telegram_user_id=? LIMIT 1",
            (int(user_id),),
        ).fetchone()
    return bool(row)


def _recipients():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT telegram_user_id
            FROM students
            WHERE active=1 AND telegram_user_id IS NOT NULL
            ORDER BY telegram_user_id
            """
        ).fetchall()
    return [int(row[0]) for row in rows]


def _delivery_status(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            "SELECT status FROM anonymous_why_deliveries WHERE survey_key=? AND telegram_user_id=?",
            (SURVEY_KEY, int(user_id)),
        ).fetchone()


def _record_delivery(user_id, status, error=None):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO anonymous_why_deliveries
                (survey_key, telegram_user_id, status, sent_date, error)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(survey_key, telegram_user_id) DO UPDATE SET
                status=excluded.status,
                sent_date=excluded.sent_date,
                error=excluded.error
            """,
            (SURVEY_KEY, int(user_id), status, _now().date().isoformat(), error),
        )
        conn.commit()


def _completed(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM anonymous_why_completions WHERE survey_key=? AND telegram_user_id=?",
            (SURVEY_KEY, int(user_id)),
        ).fetchone()
    return bool(row)


def _progress(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT response_id, current_index
            FROM anonymous_why_progress
            WHERE survey_key=? AND telegram_user_id=?
            """,
            (SURVEY_KEY, int(user_id)),
        ).fetchone()


def _ensure_progress(user_id):
    existing = _progress(user_id)
    if existing:
        return existing
    response_id = uuid.uuid4().hex
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO anonymous_why_progress
                (survey_key, telegram_user_id, response_id, current_index, started_date)
            VALUES (?, ?, ?, 0, ?)
            """,
            (SURVEY_KEY, int(user_id), response_id, _now().date().isoformat()),
        )
        conn.commit()
    return _progress(user_id)


def _save_draft(response_id, question_index, answer_text):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO anonymous_why_drafts(response_id, question_index, answer_text)
            VALUES (?, ?, ?)
            ON CONFLICT(response_id, question_index) DO UPDATE SET
                answer_text=excluded.answer_text
            """,
            (response_id, int(question_index), answer_text),
        )
        conn.commit()


def _advance(user_id, new_index):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE anonymous_why_progress
            SET current_index=?
            WHERE survey_key=? AND telegram_user_id=?
            """,
            (int(new_index), SURVEY_KEY, int(user_id)),
        )
        conn.commit()


def _finalize(user_id, response_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT question_index, answer_text
            FROM anonymous_why_drafts
            WHERE response_id=?
            ORDER BY question_index
            """,
            (response_id,),
        ).fetchall()
        answers = {int(index): text for index, text in rows}
        if any(index not in answers for index in range(3)):
            return False

        # Final answer set contains no Telegram ID, name or precise timestamp.
        conn.execute(
            """
            INSERT OR REPLACE INTO anonymous_why_responses
                (response_id, answer_1, answer_2, answer_3, submitted_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (response_id, answers[0], answers[1], answers[2], _now().date().isoformat()),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO anonymous_why_completions
                (survey_key, telegram_user_id, completed_date)
            VALUES (?, ?, ?)
            """,
            (SURVEY_KEY, int(user_id), _now().date().isoformat()),
        )
        # Destroy the only persistent mapping between this student and response_id.
        conn.execute(
            "DELETE FROM anonymous_why_progress WHERE survey_key=? AND telegram_user_id=?",
            (SURVEY_KEY, int(user_id)),
        )
        conn.execute("DELETE FROM anonymous_why_drafts WHERE response_id=?", (response_id,))
        conn.commit()
    return True


def _intro_text():
    return (
        "Ребята, я очень прошу вас пройти этот короткий опрос 💗\n\n"
        "Для меня это правда очень важно. Я хочу лучше понять, почему вы когда-то решили готовиться к ЕГЭ именно со мной — не для оценки вас, а чтобы понять, что в моей работе действительно ценно для учеников.\n\n"
        "Здесь всего 3 развернутых вопроса. Пожалуйста, отвечайте максимально честно и своими словами — мне не нужны красивые или правильные ответы.\n\n"
        "🔒 Опрос анонимный. После завершения я не увижу, кто написал конкретный ответ."
    )


def _intro_markup():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Пройти анонимный опрос", callback_data="anonwhy:start")
    ]])


async def student_callback(update, context):
    query = update.callback_query
    if not query or query.data != "anonwhy:start":
        return
    await query.answer()
    uid = int(update.effective_user.id)
    if not _active_student(uid):
        await query.edit_message_text("Этот опрос доступен ученикам ЕГЭ БЛИЗКО.")
        raise ApplicationHandlerStop
    if _completed(uid):
        await query.edit_message_text("Спасибо 💗 Ты уже прошёл(а) этот анонимный опрос.")
        raise ApplicationHandlerStop
    progress = _ensure_progress(uid)
    index = int(progress["current_index"])
    await query.edit_message_text(QUESTIONS[index])
    raise ApplicationHandlerStop


async def student_text(update, context):
    if not update.message or not update.message.text or update.effective_chat.type != "private":
        return
    uid = int(update.effective_user.id)
    progress = _progress(uid)
    if not progress:
        return
    index = int(progress["current_index"])
    if index < 0 or index >= len(QUESTIONS):
        return
    answer = " ".join(update.message.text.split()).strip()
    if len(answer) < 3:
        await update.message.reply_text("Напиши, пожалуйста, чуть подробнее — хотя бы несколько слов 💗")
        raise ApplicationHandlerStop

    response_id = progress["response_id"]
    _save_draft(response_id, index, answer[:3000])
    next_index = index + 1
    if next_index < len(QUESTIONS):
        _advance(uid, next_index)
        await update.message.reply_text(QUESTIONS[next_index])
        raise ApplicationHandlerStop

    if not _finalize(uid, response_id):
        await update.message.reply_text("Не получилось сохранить ответ. Нажми кнопку опроса ещё раз, пожалуйста.")
        raise ApplicationHandlerStop

    await update.message.reply_text(
        "Спасибо большое 💗 Для меня это действительно важно.\n\n"
        "Ответ сохранён анонимно: в результатах не будет твоего имени или Telegram-аккаунта."
    )
    raise ApplicationHandlerStop


async def delivery_tick(context):
    ensure_tables()
    now = _now()
    if now.date() != SURVEY_DATE or now.time().replace(tzinfo=None) < SEND_TIME:
        return

    sent = 0
    failed = 0
    for uid in _recipients():
        if _delivery_status(uid):
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=_intro_text(),
                reply_markup=_intro_markup(),
            )
            _record_delivery(uid, "sent")
            sent += 1
        except Exception as exc:
            _record_delivery(uid, "failed", repr(exc)[:500])
            failed += 1

    if sent or failed:
        admin_id = bot.get_admin_id()
        if admin_id:
            try:
                await context.bot.send_message(
                    chat_id=int(admin_id),
                    text=(
                        "🕵️ Анонимный опрос «Почему выбрали меня»\n"
                        f"✅ Доставлено: {sent}\n"
                        f"⚠️ Не доставлено: {failed}"
                    ),
                )
            except Exception:
                pass


def _response_rows():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT rowid AS response_no, response_id
            FROM anonymous_why_responses
            ORDER BY rowid
            """
        ).fetchall()


def _admin_summary():
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        delivered = conn.execute(
            "SELECT count(*) FROM anonymous_why_deliveries WHERE survey_key=? AND status='sent'",
            (SURVEY_KEY,),
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT count(*) FROM anonymous_why_deliveries WHERE survey_key=? AND status='failed'",
            (SURVEY_KEY,),
        ).fetchone()[0]
        completed = conn.execute(
            "SELECT count(*) FROM anonymous_why_completions WHERE survey_key=?",
            (SURVEY_KEY,),
        ).fetchone()[0]
        responses = conn.execute("SELECT count(*) FROM anonymous_why_responses").fetchone()[0]
    return (
        "🕵️ Анонимный опрос • Почему выбрали меня\n"
        "17.09.2026 • 20:00 по Москве\n\n"
        f"Доставлено: {delivered}\n"
        f"Не доставлено: {failed}\n"
        f"Завершили: {completed}\n"
        f"Анонимных ответов: {responses}\n\n"
        "Имена учеников с ответами не сохраняются."
    )


def _admin_markup():
    rows = []
    for row in _response_rows()[:50]:
        rows.append([InlineKeyboardButton(
            f"💬 Ответ #{row['response_no']}",
            callback_data=f"cab:anonwhy:{int(row['response_no'])}",
        )])
    rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="cab:anonwhy")])
    rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return InlineKeyboardMarkup(rows)


def _response_detail(response_no):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT answer_1, answer_2, answer_3
            FROM anonymous_why_responses
            WHERE rowid=?
            """,
            (int(response_no),),
        ).fetchone()
    if not row:
        return "Ответ не найден."
    return (
        f"💬 Анонимный ответ #{response_no}\n\n"
        f"1. Почему выбрал(а) меня:\n{row['answer_1']}\n\n"
        f"2. Что отличает мой подход:\n{row['answer_2']}\n\n"
        f"3. Что сказал(а) бы другу:\n{row['answer_3']}"
    )


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

    def cabinet_markup_with_anonymous_survey():
        base_markup = _previous_cabinet_markup()
        rows = [list(row) for row in base_markup.inline_keyboard]
        if not any(
            getattr(button, "callback_data", None) == "cab:anonwhy"
            for row in rows for button in row
        ):
            rows.insert(max(0, len(rows) - 1), [
                InlineKeyboardButton("🕵️ Анонимный опрос 17.09", callback_data="cab:anonwhy")
            ])
        return InlineKeyboardMarkup(rows)

    async def cabinet_callback_with_anonymous_survey(update, context):
        query = update.callback_query
        if query and query.data == "cab:anonwhy":
            await query.answer()
            await query.edit_message_text(_admin_summary(), reply_markup=_admin_markup())
            return
        if query and query.data.startswith("cab:anonwhy:"):
            await query.answer()
            try:
                response_no = int(query.data.rsplit(":", 1)[1])
            except ValueError:
                return
            await query.edit_message_text(
                _response_detail(response_no),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← К ответам", callback_data="cab:anonwhy")],
                    [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
                ]),
            )
            return
        await _previous_cabinet_callback(update, context)

    live23.cabinet_markup = cabinet_markup_with_anonymous_survey
    live23.cabinet_callback = cabinet_callback_with_anonymous_survey


def _build_with_anonymous_survey(self):
    application = _original_build(self)
    application.add_handler(CallbackQueryHandler(student_callback, pattern=r"^anonwhy:start$"), group=-31)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, student_text), group=-31)
    application.job_queue.run_repeating(
        delivery_tick,
        interval=60,
        first=20,
        name="anonymous_why_masha_2026_09_17_delivery",
    )
    return application


def install():
    global _original_build, _installed
    if _installed:
        return
    ensure_tables()
    _patch_admin_cabinet()
    _original_build = ApplicationBuilder.build
    ApplicationBuilder.build = _build_with_anonymous_survey
    _installed = True
    print(
        f"Anonymous why-Masha survey ready: date={SURVEY_DATE.isoformat()} time={SEND_TIME_TEXT} questions={len(QUESTIONS)}",
        flush=True,
    )
