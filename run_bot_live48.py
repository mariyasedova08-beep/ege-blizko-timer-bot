import random
import secrets
import sqlite3
from datetime import date, datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live47

live47 = run_bot_live47
live46 = live47.live46
live45 = live47.live45
live44 = live47.live44
live43 = live47.live43
live41 = live47.live41
live39 = live47.live39
live37 = live47.live37
live35 = live47.live35
live34 = live47.live34
live31 = live47.live31
live24 = live47.live24
live17 = live47.live17
live7 = live34.live7
live23 = live24.live23
bot = live46.bot
run_bot = live34.run_bot
live15 = live46.live15

from metals_trainer_bank import METALS_BANK

METALS_CAMPAIGN_START = date(2026, 9, 22)
METALS_CAMPAIGN_END = date(2026, 9, 27)
METALS_CAMPAIGN_TIME = time(18, 0)
METALS_BY_ID = {item[0]: item for item in METALS_BANK}


def ensure_metals_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metals_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                telegram_username TEXT,
                telegram_name TEXT,
                mode TEXT NOT NULL,
                total INTEGER NOT NULL,
                correct INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metals_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                correct INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metals_errors (
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                error_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (telegram_user_id, question_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metals_campaign_deliveries (
                day_key TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL
            )
        """)
        conn.commit()


def _unresolved_error_ids(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute("""
            SELECT question_id, error_count - correct_count AS debt
            FROM metals_errors
            WHERE telegram_user_id = ? AND error_count > correct_count
            ORDER BY debt DESC, updated_at DESC
        """, (int(user_id),)).fetchall()
    return [qid for qid, _ in rows if qid in METALS_BY_ID]


def _create_session(user, mode, question_ids):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute("""
            INSERT INTO metals_sessions
                (telegram_user_id, telegram_username, telegram_name, mode, total, correct, started_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (user.id, user.username or "", user.full_name or "", mode, len(question_ids), now))
        conn.commit()
        return cur.lastrowid


def _record_attempt(user_id, question_id, is_correct):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT INTO metals_attempts (telegram_user_id, question_id, correct, created_at) VALUES (?, ?, ?, ?)",
            (int(user_id), question_id, 1 if is_correct else 0, now),
        )
        conn.execute("""
            INSERT INTO metals_errors
                (telegram_user_id, question_id, error_count, correct_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id, question_id) DO UPDATE SET
                error_count = error_count + excluded.error_count,
                correct_count = correct_count + excluded.correct_count,
                updated_at = excluded.updated_at
        """, (int(user_id), question_id, 0 if is_correct else 1, 1 if is_correct else 0, now))
        conn.commit()


def _finish_session(session_id, correct):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "UPDATE metals_sessions SET correct = ?, finished_at = ? WHERE id = ?",
            (int(correct), datetime.now(bot.TIMEZONE).isoformat(), int(session_id)),
        )
        conn.commit()


def _question_ids(mode, user_id):
    all_ids = [item[0] for item in METALS_BANK]
    if mode == "10":
        return random.sample(all_ids, 10)
    if mode == "20":
        return random.sample(all_ids, 20)
    if mode == "100":
        result = list(all_ids)
        random.shuffle(result)
        return result
    if mode == "errors":
        ids = _unresolved_error_ids(user_id)
        if not ids:
            return []
        random.shuffle(ids)
        return ids[:10]
    return random.sample(all_ids, 10)


def _start_session(context, user, mode):
    ids = _question_ids(mode, user.id)
    if not ids:
        return False
    session_id = _create_session(user, mode, ids)
    context.user_data["metals_session"] = {
        "token": secrets.token_hex(2),
        "session_id": session_id,
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
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        sessions, total, correct = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM metals_sessions
            WHERE telegram_user_id = ? AND finished_at IS NOT NULL
        """, (int(user_id),)).fetchone()
    pct = round(correct * 100 / total) if total else 0
    return (
        "📊 Металлы — моя статистика\n\n"
        f"Тренировок: {int(sessions or 0)}\n"
        f"Ответов: {int(correct or 0)}/{int(total or 0)}\n"
        f"Точность: {pct}%\n"
        f"❌ Вопросов на повторение: {len(_unresolved_error_ids(user_id))}"
    )


def _menu_markup(user_id):
    err = len(_unresolved_error_ids(user_id))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ 10 вопросов", callback_data="triv:metals:start:10"), InlineKeyboardButton("🧠 20 вопросов", callback_data="triv:metals:start:20")],
        [InlineKeyboardButton("💯 Все 100 вопросов", callback_data="triv:metals:start:100")],
        [InlineKeyboardButton(f"❌ Мои ошибки ({err})", callback_data="triv:metals:start:errors")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="triv:metals:stats")],
    ])


async def show_metals_menu(update, context, edit=False):
    text = (
        "⚙️ Тренажёр «Металлы»\n\n"
        "100 разных вопросов по уроку №7: свойства металлов, реакции с простыми и сложными веществами, "
        "ряд напряжений, кислоты, вода, соли, щёлочи и способы получения.\n\n"
        "Выбирай режим 👇"
    )
    markup = _menu_markup(update.effective_user.id)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def _send_current_question(update, context, edit=False):
    session = context.user_data.get("metals_session")
    if not session:
        await show_metals_menu(update, context, edit=edit)
        return
    if session["index"] >= len(session["ids"]):
        await _finish_metals_session(update, context, edit=edit)
        return
    qid = session["ids"][session["index"]]
    _qid, prompt, correct, distractors = METALS_BY_ID[qid]
    choices = list(distractors) + [correct]
    random.shuffle(choices)
    correct_index = choices.index(correct)
    session["choices"] = choices
    session["correct_index"] = correct_index
    context.user_data["metals_session"] = session
    text = f"⚙️ Металлы\n\nВопрос {session['index'] + 1}/{len(session['ids'])}\n\n{prompt}"
    rows = [[InlineKeyboardButton(choice, callback_data=f"triv:metals:a:{session['token']}:{i}")] for i, choice in enumerate(choices)]
    rows.append([InlineKeyboardButton("← В меню", callback_data="triv:metals:menu")])
    markup = InlineKeyboardMarkup(rows)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def _finish_metals_session(update, context, edit=False):
    session = context.user_data.get("metals_session")
    if not session:
        return
    total = len(session["ids"])
    correct = int(session["correct"])
    _finish_session(session["session_id"], correct)
    pct = round(correct * 100 / total) if total else 0
    lines = ["💗 Готово!", "", f"Результат: {correct}/{total} — {pct}%"]
    if session["wrong"]:
        lines.extend(["", f"❌ Вопросов, которые стоит повторить: {len(set(session['wrong']))}"])
    else:
        lines.extend(["", "🔥 Без ошибок! Отличная работа."])
    context.user_data.pop("metals_session", None)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Повторить ошибки", callback_data="triv:metals:start:errors")],
        [InlineKeyboardButton("⚡ Ещё 10 вопросов", callback_data="triv:metals:start:10")],
        [InlineKeyboardButton("📊 Статистика", callback_data="triv:metals:stats")],
    ])
    if edit and update.callback_query:
        await update.callback_query.edit_message_text("\n".join(lines), reply_markup=markup)
    else:
        await update.effective_message.reply_text("\n".join(lines), reply_markup=markup)


async def metals_callback(update, context):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = str(query.data or "")
    if data == "triv:metals:menu":
        context.user_data.pop("metals_session", None)
        await show_metals_menu(update, context, edit=True)
        return
    if data == "triv:metals:stats":
        await query.edit_message_text(
            _stats_text(update.effective_user.id),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← В меню", callback_data="triv:metals:menu")]]),
        )
        return
    if data.startswith("triv:metals:start:"):
        mode = data.rsplit(":", 1)[-1]
        if mode not in {"10", "20", "100", "errors"}:
            return
        if not _start_session(context, update.effective_user, mode):
            await query.edit_message_text(
                "❌ Ошибок для повторения пока нет. Отличная работа 💗",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ 10 вопросов", callback_data="triv:metals:start:10"), InlineKeyboardButton("← В меню", callback_data="triv:metals:menu")]]),
            )
            return
        await _send_current_question(update, context, edit=True)
        return
    if data.startswith("triv:metals:a:"):
        parts = data.split(":")
        if len(parts) != 5:
            return
        token, choice_text = parts[3], parts[4]
        session = context.user_data.get("metals_session")
        if not session or session.get("token") != token:
            await query.edit_message_text("Эта тренировка уже закончилась. Открой новую через меню тренажёра.")
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
        correct_answer = METALS_BY_ID[qid][2]
        is_correct = choice_index == correct_index
        _record_attempt(update.effective_user.id, qid, is_correct)
        if is_correct:
            session["correct"] += 1
            result = "✅ Верно!"
        else:
            session["wrong"].append(qid)
            result = f"❌ Не совсем.\n\nПравильный ответ: {correct_answer}"
        session["index"] += 1
        context.user_data["metals_session"] = session
        await query.edit_message_text(
            result,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Дальше ➡️", callback_data=f"triv:metals:next:{session['token']}")]]),
        )
        return
    if data.startswith("triv:metals:next:"):
        token = data.rsplit(":", 1)[-1]
        session = context.user_data.get("metals_session")
        if not session or session.get("token") != token:
            await show_metals_menu(update, context, edit=True)
            return
        await _send_current_question(update, context, edit=True)


_previous_trivial_callback = live7.trivial_callback


async def combined_trivial_callback_with_metals(update, context):
    if update.callback_query and str(update.callback_query.data or "").startswith("triv:metals:"):
        await metals_callback(update, context)
        return
    await _previous_trivial_callback(update, context)


live7.trivial_callback = combined_trivial_callback_with_metals

_previous_start_router = live7.start_router


async def combined_start_router_with_metals(update, context):
    if update.effective_chat.type == "private" and context.args and context.args[0].lower() in {"metal", "metals", "металлы"}:
        await update.message.reply_text("⚙️ Тренажёр «Металлы» открыт 💗")
        await show_metals_menu(update, context)
        return
    await _previous_start_router(update, context)


live7.start_router = combined_start_router_with_metals

_previous_text_router = live7.student_text_router


async def combined_text_router_with_metals(update, context):
    if update.effective_chat.type == "private" and update.message and update.message.text == "⚙️ Металлы":
        await show_metals_menu(update, context)
        return
    await _previous_text_router(update, context)


live7.student_text_router = combined_text_router_with_metals


def _campaign_already_sent(day_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute("SELECT 1 FROM metals_campaign_deliveries WHERE day_key = ?", (day_key,)).fetchone())


def _mark_campaign_sent(day_key):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO metals_campaign_deliveries (day_key, sent_at) VALUES (?, ?)",
            (day_key, datetime.now(bot.TIMEZONE).isoformat()),
        )
        conn.commit()


async def send_metals_announcement(context, day=None):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False
    me = await context.bot.get_me()
    day = day or bot.today_moscow()
    number = (day - METALS_CAMPAIGN_START).days + 1 if METALS_CAMPAIGN_START <= day <= METALS_CAMPAIGN_END else None
    prefix = f"День {number}/6. " if number else ""
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Открыть тренажёр «Металлы»", url=f"https://t.me/{me.username}?start=metals")]])
    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=(
            "⚙️ <b>Тренажёр «Металлы»</b>\n\n"
            f"{prefix}В банке <b>100 разных вопросов</b> по уроку №7.\n"
            "Есть режимы на 10, 20 и все 100 вопросов, а ошибки сохраняются для повторения.\n\n"
            "Выбирай режим и закрепляй реакции 💗"
        ),
        parse_mode="HTML",
        reply_markup=markup,
    )
    return True


async def metals_campaign_tick(context):
    now = datetime.now(bot.TIMEZONE)
    today = now.date()
    if not (METALS_CAMPAIGN_START <= today <= METALS_CAMPAIGN_END):
        return
    if now.time() < METALS_CAMPAIGN_TIME:
        return
    key = today.isoformat()
    if _campaign_already_sent(key):
        return
    if await send_metals_announcement(context, today):
        _mark_campaign_sent(key)


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_metals(context):
    try:
        await _previous_tick(context)
    finally:
        await metals_campaign_tick(context)


live7.friday_trivial_tick = combined_tick_with_metals


def register_metals_trainer():
    live41.register_weekly_trainer("metals", "⚙️ Металлы", "metals", 30)


_original_weekly_trainer_stats = live41._weekly_trainer_stats


def weekly_trainer_stats_with_metals(conn, telegram_id, now):
    sessions, questions, correct = _original_weekly_trainer_stats(conn, telegram_id, now)
    since = datetime.combine(live41._week_start(now), time.min, tzinfo=bot.TIMEZONE).isoformat()
    until = now.isoformat()
    row = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
        FROM metals_sessions
        WHERE telegram_user_id = ? AND finished_at IS NOT NULL
          AND finished_at >= ? AND finished_at <= ?
    """, (int(telegram_id), since, until)).fetchone()
    return sessions + int(row[0] or 0), questions + int(row[1] or 0), correct + int(row[2] or 0)


live41._weekly_trainer_stats = weekly_trainer_stats_with_metals


def trainer_metric_with_metals(conn, student_row, now):
    telegram_id = student_row[5]
    if telegram_id is None:
        return None
    if (now.date() - run_bot.COURSE_START_DATE).days < live34.TRAINER_LOOKBACK_DAYS:
        return None
    since = (now - timedelta(days=live34.TRAINER_LOOKBACK_DAYS)).isoformat()
    counts = []
    for table in ("trivial_sessions", "acid_sessions", "metals_sessions"):
        counts.append(conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at >= ?",
            (int(telegram_id), since),
        ).fetchone()[0])
    sessions = sum(int(x or 0) for x in counts)
    if sessions >= live34.TRAINER_MIN_SESSIONS:
        return None
    return {
        "key": "trainer",
        "value": sessions,
        "label": f"тренажёры: {sessions} за последние {live34.TRAINER_LOOKBACK_DAYS} дней",
    }


live34._trainer_metric = trainer_metric_with_metals

_original_month_metrics = live15._student_month_metrics


def student_month_metrics_with_metals(conn, student, year, month, probnik_names):
    metrics = _original_month_metrics(conn, student, year, month, probnik_names)
    telegram_user_id = student[4]
    if telegram_user_id is None:
        return metrics
    prefix = f"{year:04d}-{month:02d}%"
    row = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
        FROM metals_sessions
        WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at LIKE ?
    """, (int(telegram_user_id), prefix)).fetchone()
    metrics["trainer_sessions"] += int(row[0] or 0)
    metrics["trainer_total"] += int(row[1] or 0)
    metrics["trainer_correct"] += int(row[2] or 0)
    return metrics


live15._student_month_metrics = student_month_metrics_with_metals


def metals_month_text(year, month):
    prefix = f"{year:04d}-{month:02d}%"
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute("""
            SELECT coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'), telegram_user_id
            FROM students WHERE active = 1
            ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
        """).fetchall()
        blocks = []
        total_sessions = total_q = total_correct = 0
        for name, tid in students:
            if tid is None:
                blocks.append(f"👩‍🎓 {name}\n🔗 Telegram не привязан")
                continue
            row = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
                FROM metals_sessions
                WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at LIKE ?
            """, (int(tid), prefix)).fetchone()
            s, q, c = (int(row[0] or 0), int(row[1] or 0), int(row[2] or 0))
            total_sessions += s
            total_q += q
            total_correct += c
            pct = round(c * 100 / q) if q else 0
            blocks.append(f"👩‍🎓 {name}\n⚙️ {s} трен. · {pct}%")
    group_pct = round(total_correct * 100 / total_q) if total_q else 0
    return (
        f"⚙️ Металлы — {live15.MONTH_NAMES[month].lower()} {year}\n"
        f"Всего тренировок: {total_sessions} · точность группы: {group_pct}%\n\n"
        + "\n\n".join(blocks)
    )


_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_metals(update, context):
    query = update.callback_query
    if query and update.effective_chat.type == "private" and bot.user_is_admin(update):
        data = str(query.data or "")
        if data == "cab:trainmenu":
            await query.answer()
            await query.edit_message_text(
                "🧪 <b>Тренажёры</b>\n\nВыбирай статистику:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🧪 Кислоты", callback_data="cab:acid"), InlineKeyboardButton("🧫 Тривиальные", callback_data="cab:trivial")],
                    [InlineKeyboardButton("⚙️ Металлы", callback_data="cab:metals")],
                    [InlineKeyboardButton("🏆 Рейтинг тривиальных", callback_data="cab:trivtop")],
                    [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
                ]),
            )
            return
        if data == "cab:metals":
            await query.answer()
            now = datetime.now(bot.TIMEZONE)
            await query.message.reply_text(metals_month_text(now.year, now.month))
            return
    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_metals

_previous_test = bot.test


async def test_with_metals_preview(update, context):
    is_metals = bool(context.args) and context.args[0].lower() in {"metal", "metals", "металлы"}
    if not is_metals:
        await _previous_test(update, context)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    await update.message.reply_text("🧪 ТЕСТ — это видишь только ты. В группу и ученикам ничего не отправлено.")
    me = await context.bot.get_me()
    await update.message.reply_text(
        "⚙️ Тренажёр «Металлы»\n\nВ банке 100 разных вопросов по уроку №7.\nКнопка ниже открывает настоящий тренажёр.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Открыть тренажёр", url=f"https://t.me/{me.username}?start=metals")]]),
    )


bot.test = test_with_metals_preview


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    ensure_metals_tables()
    register_metals_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live24.main()
