"""Telegram-only тренажёр «Реакции разложения» — без WebApp и сайта.

Установка только явным вызовом install() в run_bot_production.main().
Не отправляет сообщения автоматически и не меняет другие тренажёры.
"""
import random
import secrets
import sqlite3
from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import run_bot_live90 as live90
from decomposition_trainer_bank import (
    DECOMPOSITION_BANK,
    DECOMPOSITION_GROUPS,
    DECOMPOSITION_EXPLANATIONS,
)

bot = live90.bot
live7 = live90.live79.live7
live41 = live90.live79.live41
PREFIX = "triv:decomp:"
SESSION_KEY = "decomposition_session"
BY_ID = {q[0]: q for q in DECOMPOSITION_BANK}
_INSTALLED = False


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.executescript("""
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
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                correct INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decomposition_errors (
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                error_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (telegram_user_id, question_id)
            );
            CREATE INDEX IF NOT EXISTS idx_decomp_attempt_user
                ON decomposition_attempts (telegram_user_id, created_at);
        """)


def _now():
    return datetime.now(bot.TIMEZONE).isoformat()


def _error_ids(user_id):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """SELECT question_id FROM decomposition_errors
               WHERE telegram_user_id=? AND error_count>correct_count
               ORDER BY error_count-correct_count DESC, updated_at DESC""",
            (int(user_id),),
        ).fetchall()
    return [qid for (qid,) in rows if qid in BY_ID]


def _record_answer(user_id, qid, is_correct):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        now = _now()
        conn.execute(
            "INSERT INTO decomposition_attempts"
            "(telegram_user_id,question_id,correct,created_at) VALUES(?,?,?,?)",
            (int(user_id), qid, int(is_correct), now),
        )
        conn.execute(
            """INSERT INTO decomposition_errors
               (telegram_user_id, question_id, error_count, correct_count, updated_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(telegram_user_id,question_id) DO UPDATE SET
                  error_count=error_count+excluded.error_count,
                  correct_count=correct_count+excluded.correct_count,
                  updated_at=excluded.updated_at""",
            (int(user_id), qid, 0 if is_correct else 1, 1 if is_correct else 0, now),
        )


def _new_session(update, context, mode):
    uid = int(update.effective_user.id)
    if mode == "non_ovr":
        ids = [qid for qid in BY_ID if DECOMPOSITION_GROUPS[qid] == "non_ovr"]
    elif mode == "ovr":
        ids = [qid for qid in BY_ID if DECOMPOSITION_GROUPS[qid] == "ovr"]
    elif mode == "all":
        ids = list(BY_ID)
    elif mode == "errors":
        ids = _error_ids(uid)[:20]
    else:
        ids = random.sample(list(BY_ID), 10)
    if not ids:
        return False
    random.shuffle(ids)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cursor = conn.execute(
            "INSERT INTO decomposition_sessions"
            "(telegram_user_id, mode, total, started_at) VALUES(?,?,?,?)",
            (uid, mode, len(ids), _now()),
        )
        sid = cursor.lastrowid
    context.user_data[SESSION_KEY] = dict(
        id=sid, token=secrets.token_hex(4), ids=ids,
        index=0, correct=0, wrong=[], answered=False, choices=[],
    )
    return True


def _stats_text(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        sessions, count, correct = conn.execute(
            """SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
               FROM decomposition_sessions
               WHERE telegram_user_id=? AND finished_at IS NOT NULL""",
            (int(user_id),),
        ).fetchone()
    percent = round(100 * correct / count) if count else 0
    return (
        "📊 Реакции разложения — моя статистика\n\n"
        f"Тренировок: {sessions}\nПравильно: {correct}/{count} ({percent}%)\n"
        f"❌ Вопросов на повторение: {len(_error_ids(user_id))}"
    )


def _menu_markup(uid):
    errors = len(_error_ids(uid))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ 10 случайных", callback_data=PREFIX + "start:10")],
        [
            InlineKeyboardButton("НЕ ОВР · 25", callback_data=PREFIX + "start:non_ovr"),
            InlineKeyboardButton("ОВР · 25", callback_data=PREFIX + "start:ovr"),
        ],
        [InlineKeyboardButton("🧪 Все 50", callback_data=PREFIX + "start:all")],
        [InlineKeyboardButton(f"❌ Мои ошибки ({errors})", callback_data=PREFIX + "start:errors")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data=PREFIX + "stats")],
    ])


async def show_menu(update, context, edit=False):
    msg = (
        "💗 ЕГЭ БЛИЗКО | Реакции разложения\n\n"
        "50 вопросов: 25 НЕ ОВР и 25 ОВР.\n"
        "Выбирай продукты разложения из 4 вариантов ответа.\n"
        "После ответа увидишь полное уравнение и пояснение.\n"
        "Ошибки можно повторить отдельно.\n\nВыбирай режим 👇"
    )
    markup = _menu_markup(update.effective_user.id)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=markup)
    else:
        await update.effective_message.reply_text(msg, reply_markup=markup)


async def _show_question(update, context):
    state = context.user_data.get(SESSION_KEY)
    if not state:
        return await show_menu(update, context, edit=True)
    if state["index"] >= len(state["ids"]):
        return await _finish(update, context)
    qid = state["ids"][state["index"]]
    _, prompt, correct, wrong = BY_ID[qid]
    choices = [correct, *wrong]
    random.shuffle(choices)
    state["choices"] = choices
    state["answered"] = False
    mode = "ОВР" if DECOMPOSITION_GROUPS[qid] == "ovr" else "НЕ ОВР"
    msg = (
        f"🧪 Разложение | {mode}\n"
        f"Вопрос {state['index'] + 1}/{len(state['ids'])}\n\n{prompt}"
    )
    rows = [
        [InlineKeyboardButton(choice, callback_data=f"{PREFIX}a:{state['token']}:{i}")]
        for i, choice in enumerate(choices)
    ]
    rows.append([InlineKeyboardButton("← В меню", callback_data=PREFIX + "menu")])
    await update.callback_query.edit_message_text(
        msg, reply_markup=InlineKeyboardMarkup(rows),
    )


async def _finish(update, context):
    state = context.user_data.get(SESSION_KEY)
    if not state:
        return await show_menu(update, context, edit=True)
    count, correct = len(state["ids"]), state["correct"]
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "UPDATE decomposition_sessions SET correct=?,finished_at=? WHERE id=?",
            (correct, _now(), state["id"]),
        )
    context.user_data.pop(SESSION_KEY, None)
    percent = round(correct * 100 / count)
    msg = (
        f"💗 Готово! Результат: {correct}/{count} — {percent}%\n\n"
        + (
            f"❌ На повторение: {len(set(state['wrong']))} вопросов."
            if state["wrong"] else "🔥 Без ошибок!"
        )
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Повторить ошибки", callback_data=PREFIX + "start:errors")],
        [InlineKeyboardButton("⚡ Ещё 10", callback_data=PREFIX + "start:10")],
        [InlineKeyboardButton("📊 Статистика", callback_data=PREFIX + "stats")],
    ])
    await update.callback_query.edit_message_text(msg, reply_markup=kb)


async def callback(update, context):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = str(query.data or "")
    if data == PREFIX + "menu":
        context.user_data.pop(SESSION_KEY, None)
        return await show_menu(update, context, edit=True)
    if data == PREFIX + "stats":
        return await query.edit_message_text(
            _stats_text(update.effective_user.id),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("← В меню", callback_data=PREFIX + "menu")
            ]]),
        )
    if data.startswith(PREFIX + "start:"):
        mode = data[len(PREFIX + "start:"):]
        if mode not in {"10", "non_ovr", "ovr", "all", "errors"}:
            return
        if not _new_session(update, context, mode):
            return await query.edit_message_text(
                "Ошибок на повторение пока нет 💗",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← В меню", callback_data=PREFIX + "menu")
                ]]),
            )
        return await _show_question(update, context)
    if data.startswith(PREFIX + "a:"):
        parts = data.split(":")
        if len(parts) != 5:
            return
        token, raw_index = parts[3:]
        state = context.user_data.get(SESSION_KEY)
        if not state or state["token"] != token or state["answered"]:
            return
        try:
            index = int(raw_index)
        except ValueError:
            return
        if not (0 <= index < len(state["choices"])):
            return
        state["answered"] = True
        qid = state["ids"][state["index"]]
        correct_text = BY_ID[qid][2]
        good = state["choices"][index] == correct_text
        _record_answer(update.effective_user.id, qid, good)
        state["correct"] += int(good)
        if not good:
            state["wrong"].append(qid)
        state["index"] += 1
        header = "✅ Верно!" if good else f"❌ Верный ответ: {correct_text}"
        return await query.edit_message_text(
            header + "\n\n" + DECOMPOSITION_EXPLANATIONS[qid],
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Дальше ➡️", callback_data=f"{PREFIX}next:{state['token']}"
                )
            ]]),
        )
    if data.startswith(PREFIX + "next:"):
        state = context.user_data.get(SESSION_KEY)
        if state and state["answered"] and data == PREFIX + "next:" + state["token"]:
            return await _show_question(update, context)


def install():
    """Register the Telegram trainer with existing student/public trainer routers."""
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_tables()
    live41.register_weekly_trainer(
        "decomposition", "🧪 Реакции разложения", "decomposition", 65,
    )
    previous_callback = live7.trivial_callback

    async def route_callback(update, context):
        if (update.callback_query and
                str(update.callback_query.data or "").startswith(PREFIX)):
            return await callback(update, context)
        return await previous_callback(update, context)

    live7.trivial_callback = route_callback
    previous_start = live7.start_router

    async def route_start(update, context):
        if (
            update.effective_chat.type == "private"
            and context.args
            and context.args[0].lower() in {"decomposition", "разложение"}
        ):
            return await show_menu(update, context)
        return await previous_start(update, context)

    live7.start_router = route_start

    previous_weekly_stats = live41._weekly_trainer_stats

    def with_weekly_decomposition(conn, user_id, now):
        sessions, questions, correct = previous_weekly_stats(conn, user_id, now)
        since = datetime.combine(
            live41._week_start(now), time.min, tzinfo=bot.TIMEZONE
        ).isoformat()
        row = conn.execute(
            """SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
               FROM decomposition_sessions
               WHERE telegram_user_id=? AND finished_at IS NOT NULL
               AND finished_at BETWEEN ? AND ?""",
            (int(user_id), since, now.isoformat()),
        ).fetchone()
        return (
            sessions + int(row[0] or 0),
            questions + int(row[1] or 0),
            correct + int(row[2] or 0),
        )

    live41._weekly_trainer_stats = with_weekly_decomposition
    _INSTALLED = True
    print("Decomposition Telegram trainer: 50 questions ready", flush=True)
