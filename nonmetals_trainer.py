"""Тренажёр «Неметаллы» по уроку №8 ЕГЭ БЛИЗКО.

Устанавливается после verify_teacher_survey_wiring(), чтобы не ломать строгую
проверку маршрутов опроса преподавателей в run_bot_live90.
"""
import random
import secrets
import sqlite3
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder

import run_bot_live85
from nonmetals_trainer_bank import NONMETALS_BANK

live85 = run_bot_live85
live79 = live85.live79
live60 = live79.live60
live49 = live60.live49
live41 = live79.live41
live34 = live79.live34
live15 = live79.live15
live23 = live79.live23
live7 = live79.live7
bot = live85.bot

NONMETALS_BY_ID = {item[0]: item for item in NONMETALS_BANK}
NONMETALS_BUTTON = "⚛️ Неметаллы"
_INSTALLED = False


def _validate_bank():
    if len(NONMETALS_BANK) != 50:
        raise RuntimeError(f"Nonmetals bank must contain 50 questions, got {len(NONMETALS_BANK)}")
    if len(NONMETALS_BY_ID) != len(NONMETALS_BANK):
        raise RuntimeError("Duplicate ids in nonmetals bank")
    for qid, prompt, correct, distractors in NONMETALS_BANK:
        if not qid or not prompt or not correct or len(distractors) != 3:
            raise RuntimeError(f"Invalid nonmetals question: {qid}")
        choices = [correct, *distractors]
        if len(set(choices)) != 4:
            raise RuntimeError(f"Duplicate choices in nonmetals question: {qid}")


_validate_bank()


def ensure_nonmetals_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nonmetals_sessions (
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
            CREATE TABLE IF NOT EXISTS nonmetals_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                correct INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nonmetals_errors (
                telegram_user_id INTEGER NOT NULL,
                question_id TEXT NOT NULL,
                error_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (telegram_user_id, question_id)
            )
        """)
        conn.commit()


def _unresolved_error_ids(user_id):
    ensure_nonmetals_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute("""
            SELECT question_id, error_count - correct_count AS debt
            FROM nonmetals_errors
            WHERE telegram_user_id = ? AND error_count > correct_count
            ORDER BY debt DESC, updated_at DESC
        """, (int(user_id),)).fetchall()
    return [qid for qid, _debt in rows if qid in NONMETALS_BY_ID]


def _create_session(user, mode, question_ids):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute("""
            INSERT INTO nonmetals_sessions
                (telegram_user_id, telegram_username, telegram_name, mode, total, correct, started_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
        """, (user.id, user.username or "", user.full_name or "", mode, len(question_ids), now))
        conn.commit()
        return cur.lastrowid


def _record_attempt(user_id, question_id, is_correct):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT INTO nonmetals_attempts (telegram_user_id, question_id, correct, created_at) VALUES (?, ?, ?, ?)",
            (int(user_id), question_id, 1 if is_correct else 0, now),
        )
        conn.execute("""
            INSERT INTO nonmetals_errors
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
            "UPDATE nonmetals_sessions SET correct = ?, finished_at = ? WHERE id = ?",
            (int(correct), datetime.now(bot.TIMEZONE).isoformat(), int(session_id)),
        )
        conn.commit()


def _question_ids(mode, user_id):
    all_ids = [item[0] for item in NONMETALS_BANK]
    if mode == "10":
        return random.sample(all_ids, 10)
    if mode == "20":
        return random.sample(all_ids, 20)
    if mode == "50":
        result = list(all_ids)
        random.shuffle(result)
        return result
    if mode == "errors":
        ids = _unresolved_error_ids(user_id)
        random.shuffle(ids)
        return ids[:10]
    return random.sample(all_ids, 10)


def _start_session(context, user, mode):
    ids = _question_ids(mode, user.id)
    if not ids:
        return False
    context.user_data["nonmetals_session"] = {
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
    ensure_nonmetals_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        sessions, total, correct = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM nonmetals_sessions
            WHERE telegram_user_id = ? AND finished_at IS NOT NULL
        """, (int(user_id),)).fetchone()
    pct = round(correct * 100 / total) if total else 0
    return (
        "📊 Неметаллы — моя статистика\n\n"
        f"Тренировок: {int(sessions or 0)}\n"
        f"Ответов: {int(correct or 0)}/{int(total or 0)}\n"
        f"Точность: {pct}%\n"
        f"❌ Вопросов на повторение: {len(_unresolved_error_ids(user_id))}"
    )


def _menu_markup(user_id):
    err = len(_unresolved_error_ids(user_id))
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ 10 вопросов", callback_data="triv:nonmetals:start:10"),
            InlineKeyboardButton("🧠 20 вопросов", callback_data="triv:nonmetals:start:20"),
        ],
        [InlineKeyboardButton("⚛️ Все 50 вопросов", callback_data="triv:nonmetals:start:50")],
        [InlineKeyboardButton(f"❌ Мои ошибки ({err})", callback_data="triv:nonmetals:start:errors")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="triv:nonmetals:stats")],
    ])


async def show_nonmetals_menu(update, context, edit=False):
    text = (
        "⚛️ Тренажёр «Неметаллы»\n\n"
        "50 вопросов по уроку №8: физические свойства, строение, электроотрицательность, "
        "степени окисления, реакции с простыми и сложными веществами, кислоты, щёлочи "
        "и способы получения неметаллов.\n\n"
        "Выбирай режим 👇"
    )
    markup = _menu_markup(update.effective_user.id)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def _send_current_question(update, context, edit=False):
    session = context.user_data.get("nonmetals_session")
    if not session:
        await show_nonmetals_menu(update, context, edit=edit)
        return
    if session["index"] >= len(session["ids"]):
        await _finish_nonmetals_session(update, context, edit=edit)
        return

    qid = session["ids"][session["index"]]
    _qid, prompt, correct, distractors = NONMETALS_BY_ID[qid]
    choices = list(distractors) + [correct]
    random.shuffle(choices)
    session["choices"] = choices
    session["correct_index"] = choices.index(correct)
    context.user_data["nonmetals_session"] = session

    text = f"⚛️ Неметаллы\n\nВопрос {session['index'] + 1}/{len(session['ids'])}\n\n{prompt}"
    rows = [
        [InlineKeyboardButton(choice, callback_data=f"triv:nonmetals:a:{session['token']}:{i}")]
        for i, choice in enumerate(choices)
    ]
    rows.append([InlineKeyboardButton("← В меню", callback_data="triv:nonmetals:menu")])
    markup = InlineKeyboardMarkup(rows)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def _finish_nonmetals_session(update, context, edit=False):
    session = context.user_data.get("nonmetals_session")
    if not session:
        return
    total = len(session["ids"])
    correct = int(session["correct"])
    _finish_session(session["session_id"], correct)
    pct = round(correct * 100 / total) if total else 0
    lines = ["💗 Готово!", "", f"Результат: {correct}/{total} — {pct}%"]
    if session["wrong"]:
        lines += ["", f"❌ Вопросов, которые стоит повторить: {len(set(session['wrong']))}"]
    else:
        lines += ["", "🔥 Без ошибок! Отличная работа."]
    context.user_data.pop("nonmetals_session", None)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Повторить ошибки", callback_data="triv:nonmetals:start:errors")],
        [InlineKeyboardButton("⚡ Ещё 10 вопросов", callback_data="triv:nonmetals:start:10")],
        [InlineKeyboardButton("📊 Статистика", callback_data="triv:nonmetals:stats")],
    ])
    if edit and update.callback_query:
        await update.callback_query.edit_message_text("\n".join(lines), reply_markup=markup)
    else:
        await update.effective_message.reply_text("\n".join(lines), reply_markup=markup)


async def nonmetals_callback(update, context):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = str(query.data or "")

    if data == "triv:nonmetals:menu":
        context.user_data.pop("nonmetals_session", None)
        await show_nonmetals_menu(update, context, edit=True)
        return

    if data == "triv:nonmetals:stats":
        await query.edit_message_text(
            _stats_text(update.effective_user.id),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("← В меню", callback_data="triv:nonmetals:menu")]
            ]),
        )
        return

    if data.startswith("triv:nonmetals:start:"):
        mode = data.rsplit(":", 1)[-1]
        if mode not in {"10", "20", "50", "errors"}:
            return
        if not _start_session(context, update.effective_user, mode):
            await query.edit_message_text(
                "❌ Ошибок для повторения пока нет. Отличная работа 💗",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚡ 10 вопросов", callback_data="triv:nonmetals:start:10"),
                    InlineKeyboardButton("← В меню", callback_data="triv:nonmetals:menu"),
                ]]),
            )
            return
        await _send_current_question(update, context, edit=True)
        return

    if data.startswith("triv:nonmetals:a:"):
        parts = data.split(":")
        if len(parts) != 5:
            return
        token, choice_text = parts[3], parts[4]
        session = context.user_data.get("nonmetals_session")
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
        correct_answer = NONMETALS_BY_ID[qid][2]
        is_correct = choice_index == correct_index
        _record_attempt(update.effective_user.id, qid, is_correct)
        if is_correct:
            session["correct"] += 1
            result = "✅ Верно!"
        else:
            session["wrong"].append(qid)
            result = f"❌ Не совсем.\n\nПравильный ответ: {correct_answer}"
        session["index"] += 1
        context.user_data["nonmetals_session"] = session
        await query.edit_message_text(
            result,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Дальше ➡️", callback_data=f"triv:nonmetals:next:{session['token']}")
            ]]),
        )
        return

    if data.startswith("triv:nonmetals:next:"):
        token = data.rsplit(":", 1)[-1]
        session = context.user_data.get("nonmetals_session")
        if not session or session.get("token") != token:
            await show_nonmetals_menu(update, context, edit=True)
            return
        await _send_current_question(update, context, edit=True)


def register_nonmetals_trainer():
    live41.register_weekly_trainer("nonmetals", "⚛️ Неметаллы", "nonmetals", 50)


def nonmetals_month_text(year, month):
    ensure_nonmetals_tables()
    prefix = f"{year:04d}-{month:02d}%"
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = conn.execute("""
            SELECT coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                   telegram_user_id
            FROM students
            WHERE active = 1
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
                FROM nonmetals_sessions
                WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at LIKE ?
            """, (int(tid), prefix)).fetchone()
            s, q, c = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
            total_sessions += s
            total_q += q
            total_correct += c
            pct = round(c * 100 / q) if q else 0
            blocks.append(f"👩‍🎓 {name}\n⚛️ {s} трен. · {pct}%")
    group_pct = round(total_correct * 100 / total_q) if total_q else 0
    return (
        f"⚛️ Неметаллы — {live15.MONTH_NAMES[month].lower()} {year}\n"
        f"Всего тренировок: {total_sessions} · точность группы: {group_pct}%\n\n"
        + "\n\n".join(blocks)
    )


def _patch_student_keyboard():
    current = getattr(live7, "STUDENT_KEYBOARD", None)
    rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []
    if not any(NONMETALS_BUTTON in row for row in rows):
        insert_at = len(rows)
        for idx, row in enumerate(rows):
            if "💳 Оплата" in row:
                insert_at = idx
                break
        rows.insert(insert_at, [NONMETALS_BUTTON])
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

    ensure_nonmetals_tables()
    live41.ensure_weekly_report_tables()
    register_nonmetals_trainer()
    _patch_student_keyboard()

    previous_trivial_callback = live7.trivial_callback

    async def combined_trivial_callback_with_nonmetals(update, context):
        if update.callback_query and str(update.callback_query.data or "").startswith("triv:nonmetals:"):
            await nonmetals_callback(update, context)
            return
        await previous_trivial_callback(update, context)

    live7.trivial_callback = combined_trivial_callback_with_nonmetals

    previous_start_router = live7.start_router

    async def combined_start_router_with_nonmetals(update, context):
        if (
            update.effective_chat.type == "private"
            and context.args
            and context.args[0].lower() in {"nonmetal", "nonmetals", "неметаллы"}
        ):
            await update.message.reply_text(
                "⚛️ Тренажёр «Неметаллы» открыт 💗",
                reply_markup=live7.STUDENT_KEYBOARD,
            )
            await show_nonmetals_menu(update, context)
            return
        await previous_start_router(update, context)

    live7.start_router = combined_start_router_with_nonmetals

    previous_text_router = live7.student_text_router

    async def combined_text_router_with_nonmetals(update, context):
        if (
            update.effective_chat.type == "private"
            and update.message
            and update.message.text
            and update.message.text.strip() == NONMETALS_BUTTON
        ):
            await show_nonmetals_menu(update, context)
            return
        await previous_text_router(update, context)

    live7.student_text_router = combined_text_router_with_nonmetals

    original_weekly_stats = live41._weekly_trainer_stats

    def weekly_trainer_stats_with_nonmetals(conn, telegram_id, now):
        sessions, questions, correct = original_weekly_stats(conn, telegram_id, now)
        since = datetime.combine(live41._week_start(now), time.min, tzinfo=bot.TIMEZONE).isoformat()
        until = now.isoformat()
        row = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM nonmetals_sessions
            WHERE telegram_user_id = ? AND finished_at IS NOT NULL
              AND finished_at >= ? AND finished_at <= ?
        """, (int(telegram_id), since, until)).fetchone()
        return (
            sessions + int(row[0] or 0),
            questions + int(row[1] or 0),
            correct + int(row[2] or 0),
        )

    live41._weekly_trainer_stats = weekly_trainer_stats_with_nonmetals

    original_trainer_metric = live34._trainer_metric

    def trainer_metric_with_nonmetals(conn, student_row, now):
        metric = original_trainer_metric(conn, student_row, now)
        if metric is None:
            return None
        telegram_id = student_row[5]
        if telegram_id is None or metric.get("key") != "trainer":
            return metric
        since = (now - timedelta(days=live34.TRAINER_LOOKBACK_DAYS)).isoformat()
        extra = conn.execute("""
            SELECT COUNT(*)
            FROM nonmetals_sessions
            WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at >= ?
        """, (int(telegram_id), since)).fetchone()[0]
        sessions = int(metric.get("value") or 0) + int(extra or 0)
        if sessions >= live34.TRAINER_MIN_SESSIONS:
            return None
        return {
            "key": "trainer",
            "value": sessions,
            "label": f"тренажёры: {sessions} за последние {live34.TRAINER_LOOKBACK_DAYS} дней",
        }

    live34._trainer_metric = trainer_metric_with_nonmetals

    original_month_metrics = live15._student_month_metrics

    def student_month_metrics_with_nonmetals(conn, student, year, month, probnik_names):
        metrics = original_month_metrics(conn, student, year, month, probnik_names)
        telegram_user_id = student[4]
        if telegram_user_id is None:
            return metrics
        prefix = f"{year:04d}-{month:02d}%"
        row = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM nonmetals_sessions
            WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at LIKE ?
        """, (int(telegram_user_id), prefix)).fetchone()
        metrics["trainer_sessions"] += int(row[0] or 0)
        metrics["trainer_total"] += int(row[1] or 0)
        metrics["trainer_correct"] += int(row[2] or 0)
        return metrics

    live15._student_month_metrics = student_month_metrics_with_nonmetals

    original_student_stats = live49._trainer_stats_text

    def student_trainer_stats_text_with_nonmetals(student):
        text = original_student_stats(student)
        uid = student[5]
        if uid is None:
            return text
        now = datetime.now(bot.TIMEZONE)
        prefix = f"{now.year:04d}-{now.month:02d}%"
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            sessions, total, correct = conn.execute("""
                SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
                FROM nonmetals_sessions
                WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at LIKE ?
            """, (int(uid), prefix)).fetchone()
        sessions, total, correct = int(sessions or 0), int(total or 0), int(correct or 0)
        pct = round(correct * 100 / total) if total else 0
        return text + f"\n⚛️ Неметаллы: {sessions} трен. · {pct}%"

    live49._trainer_stats_text = student_trainer_stats_text_with_nonmetals

    original_weak_text = live49._weak_text

    def weak_text_with_nonmetals(student):
        text = original_weak_text(student)
        uid = student[5]
        if uid is None:
            return text
        return text + f"\n• Неметаллы: {len(_unresolved_error_ids(int(uid)))}"

    live49._weak_text = weak_text_with_nonmetals

    previous_cabinet_callback = live23.cabinet_callback

    async def cabinet_callback_with_nonmetals(update, context):
        query = update.callback_query
        if query and update.effective_chat.type == "private" and bot.user_is_admin(update):
            data = str(query.data or "")
            if data == "cab:trainmenu":
                await query.answer()
                await query.edit_message_text(
                    "🧪 <b>Тренажёры</b>\n\nВыбирай статистику:",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("🧪 Кислоты", callback_data="cab:acid"),
                            InlineKeyboardButton("🧫 Тривиальные", callback_data="cab:trivial"),
                        ],
                        [
                            InlineKeyboardButton("⚙️ Металлы", callback_data="cab:metals"),
                            InlineKeyboardButton("🧪 Оксиды", callback_data="cab:oxides"),
                        ],
                        [InlineKeyboardButton("⚛️ Неметаллы", callback_data="cab:nonmetals")],
                        [InlineKeyboardButton("🏆 Рейтинг тривиальных", callback_data="cab:trivtop")],
                        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
                    ]),
                )
                return
            if data == "cab:nonmetals":
                await query.answer()
                now = datetime.now(bot.TIMEZONE)
                await query.message.reply_text(nonmetals_month_text(now.year, now.month))
                return
        await previous_cabinet_callback(update, context)

    live23.cabinet_callback = cabinet_callback_with_nonmetals

    previous_test = bot.test

    async def test_with_nonmetals_preview(update, context):
        is_nonmetals = bool(context.args) and context.args[0].lower() in {
            "nonmetal", "nonmetals", "неметаллы"
        }
        if not is_nonmetals:
            await previous_test(update, context)
            return
        if update.effective_chat.type != "private" or not bot.user_is_admin(update):
            return
        await update.message.reply_text(
            "🧪 ТЕСТ — это видишь только ты. В группу и ученикам ничего не отправлено."
        )
        me = await context.bot.get_me()
        await update.message.reply_text(
            "⚛️ Тренажёр «Неметаллы»\n\n"
            "В банке 50 вопросов по уроку №8. Кнопка ниже открывает настоящий тренажёр.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "⚛️ Открыть тренажёр",
                    url=f"https://t.me/{me.username}?start=nonmetals",
                )
            ]]),
        )

    bot.test = test_with_nonmetals_preview

    print(f"Nonmetals trainer installed: questions={len(NONMETALS_BANK)}", flush=True)


_original_build = ApplicationBuilder.build


def build_with_nonmetals(self):
    # run_bot_live90 verifies the teacher-survey router identities before the
    # application is built. Install our wrappers only here, after that check,
    # but before main() registers Telegram handlers.
    install()
    return _original_build(self)


ApplicationBuilder.build = build_with_nonmetals
print("Nonmetals trainer build hook ready", flush=True)
