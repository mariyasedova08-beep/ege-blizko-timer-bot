"""Telegram-тренажёр «Качественные реакции» для ЕГЭ БЛИЗКО."""
import json
import random
import secrets
import sqlite3
from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import run_bot_live90 as live90
from qualitative_reactions_bank import QUALITATIVE_BANK, GROUP_TITLES, BY_ID

bot = live90.bot
live7 = live90.live79.live7
live41 = live90.live79.live41
PREFIX = "triv:qual:"
_INSTALLED = False


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS qualitative_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL, mode TEXT NOT NULL,
                total INTEGER NOT NULL, correct INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL, finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS qualitative_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL, question_id TEXT NOT NULL,
                correct INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS qualitative_progress (
                telegram_user_id INTEGER PRIMARY KEY, state_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_qual_attempt_user
                ON qualitative_attempts(telegram_user_id, question_id, id);
        """)


def _now():
    return datetime.now(bot.TIMEZONE).isoformat()


def _error_ids(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """SELECT a.question_id FROM qualitative_attempts a
               WHERE a.telegram_user_id=? AND a.correct=0
                 AND NOT EXISTS (
                   SELECT 1 FROM qualitative_attempts newer
                   WHERE newer.telegram_user_id=a.telegram_user_id
                     AND newer.question_id=a.question_id AND newer.id>a.id
                 ) ORDER BY a.id DESC""", (int(user_id),)
        ).fetchall()
    return [qid for (qid,) in rows if qid in BY_ID]


def _load_state(user_id, conn=None):
    if conn is None:
        with sqlite3.connect(bot.COREAPP_DB_PATH) as db:
            return _load_state(user_id, db)
    row = conn.execute(
        "SELECT state_json FROM qualitative_progress WHERE telegram_user_id=?",
        (int(user_id),)
    ).fetchone()
    return json.loads(row[0]) if row else None


def _save_state(conn, user_id, state):
    conn.execute(
        """INSERT INTO qualitative_progress(telegram_user_id,state_json) VALUES(?,?)
           ON CONFLICT(telegram_user_id) DO UPDATE SET state_json=excluded.state_json""",
        (int(user_id), json.dumps(state, ensure_ascii=False))
    )


def _choices(qid):
    row = BY_ID[qid]
    choices = [row[3], *row[4]]
    random.shuffle(choices)
    return choices


def _new_session(update, mode):
    uid = int(update.effective_user.id)
    if mode in GROUP_TITLES:
        ids = [row[0] for row in QUALITATIVE_BANK if row[1] == mode]
    elif mode == "all":
        ids = [row[0] for row in QUALITATIVE_BANK]
    elif mode == "errors":
        ids = _error_ids(uid)[:20]
    else:
        ids = random.sample([row[0] for row in QUALITATIVE_BANK],
                            min(10, len(QUALITATIVE_BANK)))
    if not ids:
        return False
    random.shuffle(ids)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO qualitative_sessions(telegram_user_id,mode,total,started_at) VALUES(?,?,?,?)",
            (uid, mode, len(ids), _now())
        )
        _save_state(conn, uid, dict(
            id=cur.lastrowid, token=secrets.token_hex(4), ids=ids, index=0,
            correct=0, wrong=[], answered=False, choices=_choices(ids[0])
        ))
    return True


def _stats_text(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        sessions, total, correct = conn.execute(
            """SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
               FROM qualitative_sessions
               WHERE telegram_user_id=? AND finished_at IS NOT NULL""",
            (int(user_id),)
        ).fetchone()
    pct = round(correct * 100 / total) if total else 0
    return ("📊 Качественные реакции — моя статистика\n\n"
            f"Тренировок: {sessions}\nПравильно: {correct}/{total} ({pct}%)\n"
            f"❌ Вопросов на повторение: {len(_error_ids(user_id))}")


def _menu_markup(uid):
    errors = len(_error_ids(uid))
    rows = []
    if _load_state(uid):
        rows.append([InlineKeyboardButton("▶️ Продолжить", callback_data=PREFIX + "resume")])
    rows += [
        [InlineKeyboardButton("⚡ 10 случайных", callback_data=PREFIX + "start:10")],
        [InlineKeyboardButton("🔵 Катионы", callback_data=PREFIX + "start:cations"),
         InlineKeyboardButton("🟣 Анионы", callback_data=PREFIX + "start:anions")],
        [InlineKeyboardButton("👀 Признаки реакций", callback_data=PREFIX + "start:signs")],
        [InlineKeyboardButton("🧪 Подобрать реактив", callback_data=PREFIX + "start:reagents")],
        [InlineKeyboardButton("📚 Все 40 вопросов", callback_data=PREFIX + "start:all")],
        [InlineKeyboardButton(f"❌ Мои ошибки ({errors})", callback_data=PREFIX + "start:errors")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data=PREFIX + "stats")],
    ]
    return InlineKeyboardMarkup(rows)


async def show_menu(update, context, edit=False):
    msg = (
        "💗 ЕГЭ БЛИЗКО | Качественные реакции\n\n"
        "40 вопросов по катионам, анионам, признакам реакций и выбору реактива. "
        "Составлено по шпаргалкам и заданиям из PDF.\n\n"
        "После ответа увидишь объяснение и уравнение реакции. Ошибки можно повторить, "
        "а прогресс сохраняется. Выбирай режим 👇"
    )
    markup = _menu_markup(update.effective_user.id)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=markup)
    else:
        await update.effective_message.reply_text(msg, reply_markup=markup)


def _result_text(state):
    n, correct = len(state["ids"]), state["correct"]
    return (f"💗 Готово! Результат: {correct}/{n} — {round(100 * correct / n)}%\n\n"
            + (f"❌ Ошибок в этой тренировке: {len(set(state['wrong']))}."
               if state["wrong"] else "🔥 Без ошибок!" ))


def _result_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Повторить ошибки", callback_data=PREFIX + "start:errors")],
        [InlineKeyboardButton("⚡ Ещё 10", callback_data=PREFIX + "start:10")],
        [InlineKeyboardButton("📊 Статистика", callback_data=PREFIX + "stats")],
        [InlineKeyboardButton("← В меню", callback_data=PREFIX + "menu")],
    ])


async def _show_question(update, context):
    state = _load_state(update.effective_user.id)
    if not state:
        return await show_menu(update, context, edit=True)
    qid = state["ids"][state["index"]]
    if state["answered"]:
        return await _show_answer(update, state)
    row = BY_ID[qid]
    group = GROUP_TITLES[row[1]]
    msg = f"🧪 Качественные реакции · {group}\nВопрос {state['index'] + 1}/{len(state['ids'])}\n\n{row[2]}"
    rows = [[InlineKeyboardButton(choice, callback_data=f"{PREFIX}a:{state['token']}:{qid}:{i}")]
            for i, choice in enumerate(state["choices"])]
    rows.append([InlineKeyboardButton("← В меню", callback_data=PREFIX + "menu")])
    await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(rows))


async def _show_answer(update, state, finished=False):
    qid = state["ids"][state["index"]]
    row = BY_ID[qid]
    header = "✅ Верно!" if state["last_correct"] else f"❌ Верный ответ: {row[3]}"
    text = header + "\n\n" + row[5]
    if finished:
        text += "\n\n" + _result_text(state)
        markup = _result_markup()
    else:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Дальше ➡️", callback_data=f"{PREFIX}next:{state['token']}:{qid}")],
            [InlineKeyboardButton("← В меню", callback_data=PREFIX + "menu")],
        ])
    await update.callback_query.edit_message_text(text, reply_markup=markup)


async def callback(update, context):
    query = update.callback_query
    if not query or not update.effective_chat or update.effective_chat.type != "private":
        return
    await query.answer()
    uid = int(update.effective_user.id)
    data = str(query.data or "")
    if data == PREFIX + "menu":
        return await show_menu(update, context, edit=True)
    if data == PREFIX + "resume":
        return await _show_question(update, context)
    if data == PREFIX + "stats":
        return await query.edit_message_text(
            _stats_text(uid), reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("← В меню", callback_data=PREFIX + "menu")
            ]]))
    if data.startswith(PREFIX + "start:"):
        mode = data[len(PREFIX + "start:"):]
        if mode not in {"10", "all", "errors", *GROUP_TITLES}:
            return
        if not _new_session(update, mode):
            return await query.edit_message_text(
                "Ошибок на повторение пока нет 💗",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← В меню", callback_data=PREFIX + "menu")
                ]]))
        return await _show_question(update, context)
    if data.startswith(PREFIX + "a:"):
        parts = data.split(":")
        if len(parts) != 6:
            return
        token, qid, raw = parts[3:]
        try:
            index = int(raw)
        except ValueError:
            return
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = _load_state(uid, conn)
            if (not state or state["token"] != token or state["answered"]
                    or state["ids"][state["index"]] != qid
                    or not 0 <= index < len(state["choices"])):
                return
            good = state["choices"][index] == BY_ID[qid][3]
            conn.execute(
                "INSERT INTO qualitative_attempts(telegram_user_id,question_id,correct,created_at) VALUES(?,?,?,?)",
                (uid, qid, int(good), _now())
            )
            state["answered"] = True
            state["last_correct"] = good
            state["correct"] += int(good)
            if not good:
                state["wrong"].append(qid)
            finished = state["index"] == len(state["ids"]) - 1
            if finished:
                conn.execute(
                    """UPDATE qualitative_sessions SET correct=?,finished_at=?
                       WHERE id=? AND telegram_user_id=? AND finished_at IS NULL""",
                    (state["correct"], _now(), state["id"], uid)
                )
                conn.execute("DELETE FROM qualitative_progress WHERE telegram_user_id=?", (uid,))
            else:
                _save_state(conn, uid, state)
        return await _show_answer(update, state, finished=finished)
    if data.startswith(PREFIX + "next:"):
        parts = data.split(":")
        if len(parts) != 5:
            return
        token, qid = parts[3:]
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = _load_state(uid, conn)
            if (not state or state["token"] != token or not state["answered"]
                    or state["ids"][state["index"]] != qid):
                return
            state["index"] += 1
            state["answered"] = False
            state["choices"] = _choices(state["ids"][state["index"]])
            _save_state(conn, uid, state)
        return await _show_question(update, context)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_tables()
    live41.ensure_weekly_report_tables()
    live41.register_weekly_trainer("qualitative", "🧪 Качественные реакции", "qualitative", 70)
    previous_callback = live7.trivial_callback

    async def route_callback(update, context):
        if update.callback_query and str(update.callback_query.data or "").startswith(PREFIX):
            return await callback(update, context)
        return await previous_callback(update, context)

    live7.trivial_callback = route_callback
    previous_start = live7.start_router

    async def route_start(update, context):
        if (update.effective_chat and update.effective_chat.type == "private"
                and context.args and context.args[0].lower() == "qualitative"):
            return await show_menu(update, context)
        return await previous_start(update, context)

    live7.start_router = route_start
    previous_weekly_stats = live41._weekly_trainer_stats

    def with_weekly_qualitative(conn, user_id, now):
        sessions, questions, correct = previous_weekly_stats(conn, user_id, now)
        since = datetime.combine(live41._week_start(now), time.min, tzinfo=bot.TIMEZONE).isoformat()
        row = conn.execute(
            """SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
               FROM qualitative_sessions
               WHERE telegram_user_id=? AND finished_at IS NOT NULL
                 AND finished_at BETWEEN ? AND ?""",
            (int(user_id), since, now.isoformat())
        ).fetchone()
        return sessions + int(row[0] or 0), questions + int(row[1] or 0), correct + int(row[2] or 0)

    live41._weekly_trainer_stats = with_weekly_qualitative
    _INSTALLED = True
    print(f"Qualitative reactions trainer ready: questions={len(QUALITATIVE_BANK)}", flush=True)
