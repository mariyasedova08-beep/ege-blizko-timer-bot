"""Интерактивный тренажёр «Свойства оксидов» для ЕГЭ БЛИЗКО."""
import random
import secrets
import sqlite3
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import run_bot_live85
from oxide_properties_trainer_bank import OXIDE_PROPERTIES_BANK

live85 = run_bot_live85
live79 = live85.live79
live41 = live79.live41
live34 = live79.live34
live7 = live79.live7
bot = live85.bot

BANK_BY_ID = {item[0]: item for item in OXIDE_PROPERTIES_BANK}
BUTTON = "🧪 Свойства оксидов"
_INSTALLED = False


def _validate_bank():
    if len(OXIDE_PROPERTIES_BANK) != 80:
        raise RuntimeError(
            f"Oxide properties bank must contain 80 questions, got {len(OXIDE_PROPERTIES_BANK)}"
        )
    if len(BANK_BY_ID) != len(OXIDE_PROPERTIES_BANK):
        raise RuntimeError("Duplicate ids in oxide properties bank")
    for qid, prompt, correct, distractors in OXIDE_PROPERTIES_BANK:
        if not qid or not prompt or not correct or len(distractors) != 3:
            raise RuntimeError(f"Invalid oxide properties question: {qid}")
        choices = [correct, *distractors]
        if len(set(choices)) != 4:
            raise RuntimeError(f"Duplicate choices in oxide properties question: {qid}")
        for option in choices:
            if len([x for x in option.split(" · ") if x.strip()]) != 3:
                raise RuntimeError(
                    f"Every option must contain exactly 3 substances: {qid}"
                )


_validate_bank()


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS oxide_properties_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                telegram_username TEXT,
                telegram_name TEXT,
                mode TEXT NOT NULL,
                total INTEGER NOT NULL,
                correct INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS oxide_properties_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                correct INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS oxide_properties_errors (
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                error_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (telegram_user_id, question_id)
            );
            """
        )
        conn.commit()


def _unresolved_error_ids(user_id):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT question_id, error_count - correct_count AS debt
            FROM oxide_properties_errors
            WHERE telegram_user_id=? AND error_count>correct_count
            ORDER BY debt DESC,updated_at DESC
            """,
            (int(user_id),),
        ).fetchall()
    return [qid for qid, _debt in rows if qid in BANK_BY_ID]


def _create_session(user, mode, question_ids):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO oxide_properties_sessions(
                telegram_user_id,telegram_username,telegram_name,
                mode,total,correct,started_at
            ) VALUES(?,?,?,?,?,0,?)
            """,
            (
                int(user.id),
                user.username or "",
                user.full_name or "",
                str(mode),
                len(question_ids),
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _record_attempt(user_id, question_id, is_correct):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO oxide_properties_attempts(
                telegram_user_id,question_id,correct,created_at
            ) VALUES(?,?,?,?)
            """,
            (int(user_id), str(question_id), 1 if is_correct else 0, now),
        )
        conn.execute(
            """
            INSERT INTO oxide_properties_errors(
                telegram_user_id,question_id,error_count,correct_count,updated_at
            ) VALUES(?,?,?,?,?)
            ON CONFLICT(telegram_user_id,question_id) DO UPDATE SET
                error_count=error_count+excluded.error_count,
                correct_count=correct_count+excluded.correct_count,
                updated_at=excluded.updated_at
            """,
            (
                int(user_id),
                str(question_id),
                0 if is_correct else 1,
                1 if is_correct else 0,
                now,
            ),
        )
        conn.commit()


def _finish_session(session_id, correct):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE oxide_properties_sessions
            SET correct=?,finished_at=?
            WHERE id=?
            """,
            (
                int(correct),
                datetime.now(bot.TIMEZONE).isoformat(),
                int(session_id),
            ),
        )
        conn.commit()


def _question_ids(mode, user_id):
    ids = [item[0] for item in OXIDE_PROPERTIES_BANK]
    if mode in {"10", "20", "40"}:
        return random.sample(ids, int(mode))
    if mode == "80":
        result = list(ids)
        random.shuffle(result)
        return result
    if mode == "errors":
        result = _unresolved_error_ids(user_id)
        random.shuffle(result)
        return result[:20]
    return random.sample(ids, 10)


def _start_session(context, user, mode):
    ids = _question_ids(mode, user.id)
    if not ids:
        return False
    context.user_data["oxide_properties_session"] = {
        "token": secrets.token_hex(2),
        "session_id": _create_session(user, mode, ids),
        "mode": mode,
        "ids": ids,
        "index": 0,
        "correct": 0,
        "wrong": [],
        "choices": [],
        "correct_index": None,
    }
    return True


def _stats_text(user_id):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        sessions, total, correct = conn.execute(
            """
            SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
            FROM oxide_properties_sessions
            WHERE telegram_user_id=? AND finished_at IS NOT NULL
            """,
            (int(user_id),),
        ).fetchone()
    total = int(total or 0)
    correct = int(correct or 0)
    pct = round(correct * 100 / total) if total else 0
    return (
        "📊 Свойства оксидов — моя статистика\n\n"
        f"Тренировок: {int(sessions or 0)}\n"
        f"Ответов: {correct}/{total}\n"
        f"Точность: {pct}%\n"
        f"❌ Вопросов на повторение: {len(_unresolved_error_ids(user_id))}"
    )


def _menu_markup(user_id):
    errors = len(_unresolved_error_ids(user_id))
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⚡ 10 вопросов",
                    callback_data="triv:oxideprops:start:10",
                ),
                InlineKeyboardButton(
                    "🧠 20 вопросов",
                    callback_data="triv:oxideprops:start:20",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔥 40 вопросов",
                    callback_data="triv:oxideprops:start:40",
                )
            ],
            [
                InlineKeyboardButton(
                    "🧪 Все 80 вопросов",
                    callback_data="triv:oxideprops:start:80",
                )
            ],
            [
                InlineKeyboardButton(
                    f"❌ Мои ошибки ({errors})",
                    callback_data="triv:oxideprops:start:errors",
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 Моя статистика",
                    callback_data="triv:oxideprops:stats",
                )
            ],
        ]
    )


async def show_menu(update, context, edit=False):
    text = (
        "🧪 Тренажёр «Свойства оксидов»\n\n"
        "80 вопросов на химические свойства оксидов.\n"
        "В каждом вопросе рассматривается один оксид, а в каждом варианте ответа — "
        "ровно три вещества. Нужно выбрать набор, в котором с оксидом реагируют все три.\n\n"
        "Важные оксиды повторяются несколько раз с разными реагентами — "
        "так тема действительно закрепляется.\n\n"
        "Выбирай режим 👇"
    )
    markup = _menu_markup(update.effective_user.id)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def _send_current_question(update, context, edit=False):
    session = context.user_data.get("oxide_properties_session")
    if not session:
        await show_menu(update, context, edit=edit)
        return
    if session["index"] >= len(session["ids"]):
        await _finish(update, context, edit=edit)
        return

    qid = session["ids"][session["index"]]
    _qid, prompt, correct, distractors = BANK_BY_ID[qid]
    choices = list(distractors) + [correct]
    random.shuffle(choices)
    session["choices"] = choices
    session["correct_index"] = choices.index(correct)
    context.user_data["oxide_properties_session"] = session

    text = (
        "🧪 Свойства оксидов\n\n"
        f"Вопрос {session['index'] + 1}/{len(session['ids'])}\n\n"
        f"{prompt}"
    )
    rows = [
        [
            InlineKeyboardButton(
                choice,
                callback_data=f"triv:oxideprops:a:{session['token']}:{i}",
            )
        ]
        for i, choice in enumerate(choices)
    ]
    rows.append(
        [InlineKeyboardButton("← В меню", callback_data="triv:oxideprops:menu")]
    )
    markup = InlineKeyboardMarkup(rows)

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def _finish(update, context, edit=False):
    session = context.user_data.get("oxide_properties_session")
    if not session:
        return
    total = len(session["ids"])
    correct = int(session["correct"])
    _finish_session(session["session_id"], correct)
    pct = round(correct * 100 / total) if total else 0
    lines = ["💗 Готово!", "", f"Результат: {correct}/{total} — {pct}%"]
    if session["wrong"]:
        lines += [
            "",
            f"❌ Вопросов, которые стоит повторить: {len(set(session['wrong']))}",
        ]
    else:
        lines += ["", "🔥 Без ошибок! Отличная работа."]
    context.user_data.pop("oxide_properties_session", None)

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "❌ Повторить ошибки",
                    callback_data="triv:oxideprops:start:errors",
                )
            ],
            [
                InlineKeyboardButton(
                    "⚡ Ещё 10 вопросов",
                    callback_data="triv:oxideprops:start:10",
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 Статистика",
                    callback_data="triv:oxideprops:stats",
                )
            ],
        ]
    )
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            "\n".join(lines),
            reply_markup=markup,
        )
    else:
        await update.effective_message.reply_text(
            "\n".join(lines),
            reply_markup=markup,
        )


async def callback(update, context):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = str(query.data or "")

    if data == "triv:oxideprops:menu":
        context.user_data.pop("oxide_properties_session", None)
        await show_menu(update, context, edit=True)
        return

    if data == "triv:oxideprops:stats":
        await query.edit_message_text(
            _stats_text(update.effective_user.id),
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(
                        "← В меню",
                        callback_data="triv:oxideprops:menu",
                    )
                ]]
            ),
        )
        return

    if data.startswith("triv:oxideprops:start:"):
        mode = data.rsplit(":", 1)[-1]
        if mode not in {"10", "20", "40", "80", "errors"}:
            return
        if not _start_session(context, update.effective_user, mode):
            await query.edit_message_text(
                "❌ Ошибок для повторения пока нет. Отличная работа 💗",
                reply_markup=InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton(
                            "⚡ 10 вопросов",
                            callback_data="triv:oxideprops:start:10",
                        ),
                        InlineKeyboardButton(
                            "← В меню",
                            callback_data="triv:oxideprops:menu",
                        ),
                    ]]
                ),
            )
            return
        await _send_current_question(update, context, edit=True)
        return

    if data.startswith("triv:oxideprops:a:"):
        parts = data.split(":")
        if len(parts) != 5:
            return
        token, choice_text = parts[3], parts[4]
        session = context.user_data.get("oxide_properties_session")
        if not session or session.get("token") != token:
            await query.edit_message_text(
                "Эта тренировка уже закончилась. Открой новую через меню тренажёра."
            )
            return
        try:
            choice_index = int(choice_text)
        except ValueError:
            return
        choices = session.get("choices") or []
        correct_index = session.get("correct_index")
        if not (0 <= choice_index < len(choices)) or correct_index is None:
            return

        qid = session["ids"][session["index"]]
        correct_answer = BANK_BY_ID[qid][2]
        is_correct = choice_index == correct_index
        _record_attempt(update.effective_user.id, qid, is_correct)

        if is_correct:
            session["correct"] += 1
            result = "✅ Верно!"
        else:
            session["wrong"].append(qid)
            result = (
                "❌ Не совсем.\n\n"
                f"Правильный набор: {correct_answer}"
            )

        session["index"] += 1
        context.user_data["oxide_properties_session"] = session
        await query.edit_message_text(
            result,
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(
                        "Дальше ➡️",
                        callback_data=f"triv:oxideprops:next:{session['token']}",
                    )
                ]]
            ),
        )
        return

    if data.startswith("triv:oxideprops:next:"):
        token = data.rsplit(":", 1)[-1]
        session = context.user_data.get("oxide_properties_session")
        if not session or session.get("token") != token:
            await show_menu(update, context, edit=True)
            return
        await _send_current_question(update, context, edit=True)


def register_trainer():
    live41.register_weekly_trainer(
        "oxideprops",
        "🧪 Свойства оксидов",
        "oxideproperties",
        45,
    )


def _patch_student_keyboard():
    current = getattr(live7, "STUDENT_KEYBOARD", None)
    rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []
    if not any(BUTTON in row for row in rows):
        insert_at = len(rows)
        for idx, row in enumerate(rows):
            if "💳 Оплата" in row:
                insert_at = idx
                break
        rows.insert(insert_at, [BUTTON])
    live7.STUDENT_KEYBOARD = ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    ensure_tables()
    live41.ensure_weekly_report_tables()
    register_trainer()
    _patch_student_keyboard()

    previous_callback = live7.trivial_callback

    async def combined_callback(update, context):
        if (
            update.callback_query
            and str(update.callback_query.data or "").startswith("triv:oxideprops:")
        ):
            await callback(update, context)
            return
        await previous_callback(update, context)

    live7.trivial_callback = combined_callback

    previous_start_router = live7.start_router

    async def combined_start_router(update, context):
        if (
            update.effective_chat.type == "private"
            and context.args
            and context.args[0].lower()
            in {
                "oxideproperties",
                "oxideprops",
                "свойстваоксидов",
            }
        ):
            await update.message.reply_text(
                "🧪 Тренажёр «Свойства оксидов» открыт 💗",
                reply_markup=live7.STUDENT_KEYBOARD,
            )
            await show_menu(update, context)
            return
        await previous_start_router(update, context)

    live7.start_router = combined_start_router

    previous_text_router = live7.student_text_router

    async def combined_text_router(update, context):
        if (
            update.effective_chat.type == "private"
            and update.message
            and update.message.text
            and update.message.text.strip() == BUTTON
        ):
            await show_menu(update, context)
            return
        await previous_text_router(update, context)

    live7.student_text_router = combined_text_router

    original_weekly_stats = live41._weekly_trainer_stats

    def weekly_stats_with_oxide_properties(conn, telegram_id, now):
        sessions, questions, correct = original_weekly_stats(
            conn, telegram_id, now
        )
        since = datetime.combine(
            live41._week_start(now),
            time.min,
            tzinfo=bot.TIMEZONE,
        ).isoformat()
        until = now.isoformat()
        row = conn.execute(
            """
            SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
            FROM oxide_properties_sessions
            WHERE telegram_user_id=?
              AND finished_at IS NOT NULL
              AND finished_at>=?
              AND finished_at<=?
            """,
            (int(telegram_id), since, until),
        ).fetchone()
        return (
            sessions + int(row[0] or 0),
            questions + int(row[1] or 0),
            correct + int(row[2] or 0),
        )

    live41._weekly_trainer_stats = weekly_stats_with_oxide_properties

    original_metric = live34._trainer_metric

    def trainer_metric_with_oxide_properties(conn, student_row, now):
        metric = original_metric(conn, student_row, now)
        if metric is None:
            return None
        telegram_id = student_row[5]
        if telegram_id is None or metric.get("key") != "trainer":
            return metric
        since = (
            now - timedelta(days=live34.TRAINER_LOOKBACK_DAYS)
        ).isoformat()
        extra = conn.execute(
            """
            SELECT COUNT(*)
            FROM oxide_properties_sessions
            WHERE telegram_user_id=?
              AND finished_at IS NOT NULL
              AND finished_at>=?
            """,
            (int(telegram_id), since),
        ).fetchone()[0]
        sessions = int(metric.get("value") or 0) + int(extra or 0)
        if sessions >= live34.TRAINER_MIN_SESSIONS:
            return None
        return {
            "key": "trainer",
            "value": sessions,
            "label": (
                f"тренажёры: {sessions} за последние "
                f"{live34.TRAINER_LOOKBACK_DAYS} дней"
            ),
        }

    live34._trainer_metric = trainer_metric_with_oxide_properties

    print(
        f"Oxide properties trainer installed: questions={len(OXIDE_PROPERTIES_BANK)}",
        flush=True,
    )
