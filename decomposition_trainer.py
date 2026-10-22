"""Telegram-native trainer «Реакции разложения» for the EXISTING ЕГЭ БЛИЗКО bot.

No WebApp, no broadcasts, no automatic assignment, no Kulyochki changes.
Publishing requires separate owner approval because production VPS diverges from GitHub.
"""
import random
import secrets
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import run_bot_live85
from decomposition_trainer_bank import DECOMPOSITION_BANK

live85 = run_bot_live85
live79 = live85.live79
live41 = live79.live41
live7 = live79.live7
bot = live85.bot

KEY = "decomposition_session"
BUTTON = "🧪 Реакции разложения"
CODE = "decomposition"
BY_ID = {q["id"]: q for q in DECOMPOSITION_BANK}
_INSTALLED = False


def validate_bank():
    if len(DECOMPOSITION_BANK) != 50 or len(BY_ID) != 50:
        raise RuntimeError("Exactly 50 distinct decomposition questions required")
    if sum(q["type"] == "НЕ ОВР" for q in DECOMPOSITION_BANK) != 25:
        raise RuntimeError("Need 25 non-redox questions")
    if sum(q["type"] == "ОВР" for q in DECOMPOSITION_BANK) != 25:
        raise RuntimeError("Need 25 redox questions")
    for q in DECOMPOSITION_BANK:
        required = ("id", "type", "reactants", "products", "condition", "explanation", "distractors")
        if not all(q.get(key) for key in required):
            raise RuntimeError("Incomplete decomposition question")
        if len(q["distractors"]) != 3 or len({q["products"], *q["distractors"]}) != 4:
            raise RuntimeError("Four unique options required")


validate_bank()


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS decomposition_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                total INTEGER NOT NULL,
                correct INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS decomposition_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                correct INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(session_id, question_id)
            );
            CREATE TABLE IF NOT EXISTS decomposition_errors (
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                error_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(telegram_user_id, question_id)
            );
            """
        )
        conn.commit()


def _errors(user_id):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT question_id FROM decomposition_errors
            WHERE telegram_user_id=? AND error_count > correct_count
            ORDER BY (error_count - correct_count) DESC, updated_at DESC
            """, (int(user_id),),
        ).fetchall()
    return [row[0] for row in rows if row[0] in BY_ID]


def _select_ids(mode, user_id):
    if mode == "10":
        return random.sample(list(BY_ID), 10)
    if mode == "non":
        ids = [q["id"] for q in DECOMPOSITION_BANK if q["type"] == "НЕ ОВР"]
    elif mode == "redox":
        ids = [q["id"] for q in DECOMPOSITION_BANK if q["type"] == "ОВР"]
    elif mode == "50":
        ids = list(BY_ID)
    elif mode == "errors":
        ids = _errors(user_id)
    else:
        raise ValueError("Unknown trainer mode")
    random.shuffle(ids)
    return ids


def _start_session(context, user, mode):
    ids = _select_ids(mode, user.id)
    if not ids:
        return False
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute(
            """INSERT INTO decomposition_sessions
               (telegram_user_id,mode,total,started_at)
               VALUES(?,?,?,?)""",
            (int(user.id), mode, len(ids), datetime.now(bot.TIMEZONE).isoformat()),
        )
        session_id = cur.lastrowid
        conn.commit()
    context.user_data[KEY] = {
        "token": secrets.token_hex(5),
        "session_id": session_id,
        "ids": ids,
        "index": 0,
        "correct": 0,
        "wrong": [],
        "phase": "new",
    }
    return True


def _record_answer(session, user_id, question_id, is_correct):
    """Atomic per-question insert: repeated callbacks must never double-count."""
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO decomposition_attempts
               (session_id,telegram_user_id,question_id,correct,created_at)
               VALUES(?,?,?,?,?)""",
            (int(session["session_id"]), int(user_id), question_id,
             int(bool(is_correct)), now),
        )
        if cur.rowcount != 1:
            return False
        conn.execute(
            """INSERT INTO decomposition_errors
               (telegram_user_id,question_id,error_count,correct_count,updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(telegram_user_id,question_id) DO UPDATE SET
                   error_count=error_count+excluded.error_count,
                   correct_count=correct_count+excluded.correct_count,
                   updated_at=excluded.updated_at""",
            (int(user_id), question_id, 0 if is_correct else 1,
             1 if is_correct else 0, now),
        )
        conn.commit()
    return True


def _finish_session(session):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """UPDATE decomposition_sessions
               SET correct=?,finished_at=?
               WHERE id=? AND finished_at IS NULL""",
            (session["correct"], datetime.now(bot.TIMEZONE).isoformat(),
             session["session_id"]),
        )
        conn.commit()


def _stats_text(user_id):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
               FROM decomposition_sessions
               WHERE telegram_user_id=? AND finished_at IS NOT NULL""",
            (int(user_id),),
        ).fetchone()
    sessions, total, correct = map(int, row)
    pct = round(correct * 100 / total) if total else 0
    return (
        "📊 Реакции разложения — моя статистика\n\n"
        f"Тренировок: {sessions}\nОтветов: {correct}/{total}\n"
        f"Точность: {pct}%\n"
        f"❌ На повторение: {len(_errors(user_id))}"
    )


def _menu_keyboard(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ 10 случайных", callback_data="dec:start:10")],
        [InlineKeyboardButton("◻️ 25 НЕ ОВР", callback_data="dec:start:non"),
         InlineKeyboardButton("💗 25 ОВР", callback_data="dec:start:redox")],
        [InlineKeyboardButton("🧪 Все 50", callback_data="dec:start:50")],
        [InlineKeyboardButton(f"❌ Мои ошибки ({len(_errors(user_id))})",
                              callback_data="dec:start:errors")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="dec:stats")],
    ])


async def show_menu(update, context, edit=False):
    context.user_data.pop(KEY, None)
    message = (
        "🧪 Реакции разложения\n\n"
        "50 вопросов: 25 НЕ ОВР и 25 ОВР.\n"
        "Выбирай продукты реакции при указанных условиях.\n"
        "После ответа покажу уравнение, тип и пояснение.\n\n"
        "Выбери режим 👇"
    )
    markup = _menu_keyboard(update.effective_user.id)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=markup)
    else:
        await update.effective_message.reply_text(message, reply_markup=markup)


async def _send_question(update, context):
    state = context.user_data.get(KEY)
    if not state:
        await show_menu(update, context, edit=bool(update.callback_query))
        return
    if state["index"] >= len(state["ids"]):
        await _finish(update, context)
        return
    q = BY_ID[state["ids"][state["index"]]]
    options = [q["products"], *q["distractors"]]
    random.shuffle(options)
    state["choices"] = options
    state["nonce"] = secrets.token_hex(4)
    state["phase"] = "question"
    context.user_data[KEY] = state
    text = (
        "🧪 Реакции разложения\n\n"
        f"Вопрос {state['index'] + 1}/{len(state['ids'])}\n"
        f"Тип блока: {q['type']}\n\n"
        f"Каковы продукты разложения {q['reactants']}?\n"
        f"Условия: {q['condition']}"
    )
    rows = [
        [InlineKeyboardButton(
            option, callback_data=f"dec:a:{state['token']}:{state['nonce']}:{i}"
        )] for i, option in enumerate(options)
    ]
    rows.append([InlineKeyboardButton("← В меню", callback_data="dec:menu")])
    markup = InlineKeyboardMarkup(rows)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def _finish(update, context):
    state = context.user_data.get(KEY)
    if not state:
        return
    _finish_session(state)
    total, correct = len(state["ids"]), int(state["correct"])
    text = (
        f"💗 Тренировка завершена!\n\n"
        f"Результат: {correct}/{total} — {round(100*correct/total)}%\n"
        f"❌ Ошибок: {len(state['wrong'])}\n"
        "Хочешь повторить сложные реакции?"
    )
    context.user_data.pop(KEY, None)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Повторить ошибки", callback_data="dec:start:errors")],
        [InlineKeyboardButton("⚡ Ещё 10", callback_data="dec:start:10")],
        [InlineKeyboardButton("📊 Статистика", callback_data="dec:stats")],
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def callback(update, context):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = str(query.data or "")
    if data == "dec:menu":
        await show_menu(update, context, edit=True)
        return
    if data == "dec:stats":
        await query.edit_message_text(
            _stats_text(update.effective_user.id),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("← В меню", callback_data="dec:menu")
            ]]),
        )
        return
    if data.startswith("dec:start:"):
        mode = data.rsplit(":", 1)[-1]
        if mode not in {"10", "non", "redox", "50", "errors"}:
            return
        if not _start_session(context, update.effective_user, mode):
            await query.edit_message_text(
                "Ошибок для повторения пока нет 💗",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← В меню", callback_data="dec:menu")
                ]]),
            )
            return
        await _send_question(update, context)
        return
    if data.startswith("dec:a:"):
        parts = data.split(":")
        if len(parts) != 5:
            return
        _, _, token, nonce, idx = parts
        state = context.user_data.get(KEY)
        if (not state or state.get("token") != token
                or state.get("nonce") != nonce
                or state.get("phase") != "question"):
            return
        try:
            choice_idx = int(idx)
        except ValueError:
            return
        choices = state.get("choices") or []
        if choice_idx not in range(len(choices)):
            return
        q = BY_ID[state["ids"][state["index"]]]
        is_correct = choices[choice_idx] == q["products"]
        # Guard against duplicate/old callbacks before any await/UI edits.
        state["phase"] = "answered"
        if not _record_answer(state, update.effective_user.id, q["id"], is_correct):
            return
        if is_correct:
            state["correct"] += 1
        else:
            state["wrong"].append(q["id"])
        state["index"] += 1
        state["next_nonce"] = secrets.token_hex(4)
        context.user_data[KEY] = state
        feedback = (
            ("✅ Верно!" if is_correct else "❌ Пока не совсем.") + "\n\n"
            f"Правильное уравнение:\n{q['reactants']} → {q['products']}\n\n"
            f"Тип: {q['type']}\n"
            f"Почему: {q['explanation']}"
        )
        await query.edit_message_text(
            feedback, reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Дальше ➡️",
                    callback_data=f"dec:next:{state['token']}:{state['next_nonce']}"
                )
            ]]),
        )
        return
    if data.startswith("dec:next:"):
        parts = data.split(":")
        if len(parts) != 4:
            return
        _, _, token, nonce = parts
        state = context.user_data.get(KEY)
        if (not state or state.get("token") != token
                or state.get("next_nonce") != nonce
                or state.get("phase") != "answered"):
            return
        state["phase"] = "advancing"
        context.user_data[KEY] = state
        await _send_question(update, context)


def _register_catalog_unassigned():
    """Allow later opt-in; never make new trainer obligatory or public by default."""
    live41.ensure_weekly_report_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO weekly_trainer_catalog
               (code,title,start_param,sort_order,active)
               VALUES(?,?,?,?,0)""",
            (CODE, BUTTON, "decomposition", 65),
        )
        conn.commit()


def _patch_student_keyboard():
    current = getattr(live7, "STUDENT_KEYBOARD", None)
    rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []
    if not any(BUTTON in row for row in rows):
        index = next((i for i, row in enumerate(rows) if "💳 Оплата" in row), len(rows))
        rows.insert(index, [BUTTON])
    live7.STUDENT_KEYBOARD = ReplyKeyboardMarkup(
        rows, resize_keyboard=True, is_persistent=True,
    )


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_tables()
    _register_catalog_unassigned()
    _patch_student_keyboard()

    previous_callback = live7.trivial_callback

    async def combined_callback(update, context):
        if (update.callback_query and
                str(update.callback_query.data or "").startswith("dec:")):
            await callback(update, context)
            return
        await previous_callback(update, context)

    live7.trivial_callback = combined_callback

    previous_start_router = live7.start_router

    async def combined_start_router(update, context):
        if (update.effective_chat.type == "private" and context.args
                and context.args[0].lower() in
                {"decomposition", "razlozhenie", "разложение"}):
            await show_menu(update, context)
            return
        await previous_start_router(update, context)

    live7.start_router = combined_start_router

    previous_text_router = live7.student_text_router

    async def combined_text_router(update, context):
        if (update.effective_chat.type == "private"
                and update.message and update.message.text
                and update.message.text.strip() == BUTTON):
            await show_menu(update, context)
            return
        await previous_text_router(update, context)

    live7.student_text_router = combined_text_router
    _INSTALLED = True
    print("Decomposition trainer prepared: 50 questions (25 redox + 25 non-redox)", flush=True)
