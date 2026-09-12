"""Daily trainer reminders and trainer statistics for individual students.

Installed from run_bot_production after the teacher-survey wiring check and after
all trainer modules are registered. The module only targets rows from
`individual_students`, so group students are never included.
"""
import html
import re
import sqlite3
from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90

live79 = live90.live79
live67 = live79.live67
live41 = live79.live41
live23 = live79.live23
live7 = live79.live7
bot = live90.bot

REMINDER_TIME = time(16, 0)
_INSTALLED = False


def ensure_individual_daily_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS individual_trainer_daily_deliveries (
                day_key TEXT NOT NULL,
                individual_student_id INTEGER NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (day_key, individual_student_id)
            )
            """
        )
        conn.commit()


def _day_key(now=None):
    now = now or datetime.now(bot.TIMEZONE)
    return now.date().isoformat()


def _already_sent(student_id, day_key):
    ensure_individual_daily_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(
            conn.execute(
                """
                SELECT 1
                FROM individual_trainer_daily_deliveries
                WHERE day_key = ? AND individual_student_id = ?
                LIMIT 1
                """,
                (str(day_key), int(student_id)),
            ).fetchone()
        )


def _mark_sent(student_id, telegram_id, now):
    ensure_individual_daily_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO individual_trainer_daily_deliveries
                (day_key, individual_student_id, telegram_user_id, sent_at)
            VALUES (?, ?, ?, ?)
            """,
            (_day_key(now), int(student_id), int(telegram_id), now.isoformat()),
        )
        conn.commit()


def _safe_table_name(code):
    value = str(code or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]+", value):
        return None
    return f"{value}_sessions"


def _table_has_stats_columns(conn, table_name):
    if not table_name:
        return False
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    if not exists:
        return False
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    return {"telegram_user_id", "total", "correct", "finished_at"}.issubset(columns)


def _trainer_rows(conn):
    try:
        rows = conn.execute(
            """
            SELECT code, title
            FROM weekly_trainer_catalog
            WHERE active = 1
            ORDER BY sort_order, title
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return rows


def _trainer_breakdown(telegram_id):
    if telegram_id is None:
        return []
    result = []
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for code, title in _trainer_rows(conn):
            table_name = _safe_table_name(code)
            if not _table_has_stats_columns(conn, table_name):
                continue
            row = conn.execute(
                f"""
                SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0), MAX(finished_at)
                FROM {table_name}
                WHERE telegram_user_id = ? AND finished_at IS NOT NULL
                """,
                (int(telegram_id),),
            ).fetchone()
            sessions = int(row[0] or 0)
            total = int(row[1] or 0)
            correct = int(row[2] or 0)
            last_at = row[3]
            result.append(
                {
                    "code": str(code),
                    "title": str(title),
                    "sessions": sessions,
                    "total": total,
                    "correct": correct,
                    "last_at": last_at,
                }
            )
    return result


def _overall_stats(telegram_id):
    rows = _trainer_breakdown(telegram_id)
    sessions = sum(row["sessions"] for row in rows)
    total = sum(row["total"] for row in rows)
    correct = sum(row["correct"] for row in rows)
    last_values = [row["last_at"] for row in rows if row["last_at"]]
    last_at = max(last_values) if last_values else None
    accuracy = round(correct * 100 / total) if total else None
    return {
        "rows": rows,
        "sessions": sessions,
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "last_at": last_at,
    }


def _today_stats(telegram_id, now=None):
    if telegram_id is None:
        return {"sessions": 0, "total": 0, "correct": 0, "accuracy": None}
    now = now or datetime.now(bot.TIMEZONE)
    key = _day_key(now)
    sessions = total = correct = 0
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for code, _title in _trainer_rows(conn):
            table_name = _safe_table_name(code)
            if not _table_has_stats_columns(conn, table_name):
                continue
            row = conn.execute(
                f"""
                SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
                FROM {table_name}
                WHERE telegram_user_id = ?
                  AND finished_at IS NOT NULL
                  AND substr(finished_at, 1, 10) = ?
                """,
                (int(telegram_id), key),
            ).fetchone()
            sessions += int(row[0] or 0)
            total += int(row[1] or 0)
            correct += int(row[2] or 0)
    accuracy = round(correct * 100 / total) if total else None
    return {"sessions": sessions, "total": total, "correct": correct, "accuracy": accuracy}


def _format_last(value):
    if not value:
        return "ещё не тренировалась"
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=bot.TIMEZONE)
        dt = dt.astimezone(bot.TIMEZONE)
        return dt.strftime("%d.%m в %H:%M")
    except Exception:
        return str(value)[:16].replace("T", " ")


def _individuals_overview_text():
    rows = live67._individual_rows()
    linked = sum(1 for row in rows if row[2] is not None)
    trained_today = sum(1 for row in rows if row[2] is not None and _today_stats(row[2])["sessions"] > 0)
    return (
        "👤 <b>Индивидуальные ученики</b>\n\n"
        f"Всего: {len(rows)} · Telegram подключён: {linked}\n"
        f"Сегодня тренировались: {trained_today}/{linked}\n\n"
        "В 16:00 им автоматически приходит напоминание пройти тренажёр."
    )


def _individuals_overview_markup():
    rows = []
    for student_id, name, telegram_id, _username in live67._individual_rows():
        label = name if len(name) <= 24 else name[:21] + "…"
        if telegram_id is None:
            icon = "🔗"
        else:
            icon = "✅" if _today_stats(telegram_id)["sessions"] > 0 else "⏳"
        rows.append([
            InlineKeyboardButton(f"{icon} {label}", callback_data=f"cab:individual:{int(student_id)}")
        ])
    rows.append([InlineKeyboardButton("➕ Добавить ученика", callback_data="cab:individual:add")])
    rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="cab:individuals")])
    rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return InlineKeyboardMarkup(rows)


def _individual_detail_text(row):
    _student_id, name, telegram_id, username, _code = row
    status = "✅ Telegram подключён" if telegram_id else "🔗 Telegram ещё не подключён"
    if username:
        status += f" · @{html.escape(str(username))}"
    if telegram_id:
        today = _today_stats(telegram_id)
        overall = _overall_stats(telegram_id)
        today_text = (
            f"{today['sessions']} трен. · {today['total']} вопросов"
            + (f" · {today['accuracy']}%" if today["accuracy"] is not None else "")
        ) if today["sessions"] else "ещё не тренировалась"
        stats_text = (
            f"\n\n🧪 Сегодня: {today_text}"
            f"\n📊 Всего: {overall['sessions']} трен. · {overall['total']} вопросов"
            + (f" · {overall['accuracy']}%" if overall["accuracy"] is not None else "")
            + f"\n🕓 Последний раз: {_format_last(overall['last_at'])}"
        )
    else:
        stats_text = "\n\nСтатистика появится после подключения Telegram."
    return f"👤 <b>{html.escape(str(name))}</b>\n\n{status}{stats_text}"


def _individual_detail_markup(student_id, telegram_id):
    rows = []
    if telegram_id:
        rows.append([InlineKeyboardButton("📊 Статистика тренажёров", callback_data=f"cab:individual:stats:{int(student_id)}")])
        rows.append([InlineKeyboardButton("🧪 Отправить тренажёры сейчас", callback_data=f"cab:individual:send:{int(student_id)}")])
    rows.append([InlineKeyboardButton("🔗 Ссылка подключения", callback_data=f"cab:individual:link:{int(student_id)}")])
    rows.append([InlineKeyboardButton("← К списку", callback_data="cab:individuals")])
    return InlineKeyboardMarkup(rows)


def _stats_text(row):
    _student_id, name, telegram_id, _username, _code = row
    if telegram_id is None:
        return f"📊 <b>{html.escape(str(name))}</b>\n\nTelegram ещё не подключён."
    overall = _overall_stats(telegram_id)
    today = _today_stats(telegram_id)
    lines = [f"📊 <b>Тренажёры — {html.escape(str(name))}</b>", ""]
    if today["sessions"]:
        lines.append(
            f"Сегодня: {today['sessions']} трен. · {today['correct']}/{today['total']} верно · {today['accuracy']}%"
        )
    else:
        lines.append("Сегодня: тренировок пока нет")
    if overall["sessions"]:
        lines.extend([
            f"Всего: {overall['sessions']} тренировок",
            f"Ответы: {overall['correct']}/{overall['total']} верно",
            f"Точность: {overall['accuracy']}%",
            f"Последняя тренировка: {_format_last(overall['last_at'])}",
            "",
            "<b>По тренажёрам:</b>",
        ])
        for item in overall["rows"]:
            if item["sessions"] <= 0:
                continue
            pct = round(item["correct"] * 100 / item["total"]) if item["total"] else 0
            lines.append(
                f"• {html.escape(item['title'])}: {item['sessions']} трен. · {item['correct']}/{item['total']} · {pct}%"
            )
    else:
        lines.extend(["Всего: тренировок пока нет", "", "Как только ученица закончит первую тренировку, результаты появятся здесь."])
    return "\n".join(lines)


async def individual_daily_trainer_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.time() < REMINDER_TIME:
        return
    day_key = _day_key(now)
    markup = await live67._trainer_markup(context)
    for student_id, name, telegram_id, _username in live67._individual_rows():
        if telegram_id is None or _already_sent(student_id, day_key):
            continue
        first_name = str(name or "").strip().split()[0] if str(name or "").strip() else ""
        greeting = f"Привет, {first_name}! 💗" if first_name else "Привет! 💗"
        text = (
            greeting
            + "\n\n🧪 Время короткой тренировки. Выбирай любой тренажёр и пройди хотя бы 10 вопросов."
            + "\n\nНам важна регулярность: понемногу, но каждый день — играем в долгую 💗"
        )
        try:
            await context.bot.send_message(chat_id=int(telegram_id), text=text, reply_markup=markup)
        except Exception as exc:
            print(f"Individual trainer reminder failed student={student_id}: {exc}", flush=True)
            continue
        _mark_sent(student_id, telegram_id, now)
        print(f"Individual trainer reminder sent student={student_id}", flush=True)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_individual_daily_tables()

    previous_tick = live7.friday_trivial_tick

    async def combined_tick(context):
        try:
            await previous_tick(context)
        finally:
            await individual_daily_trainer_tick(context)

    live7.friday_trivial_tick = combined_tick

    previous_callback = live23.cabinet_callback

    async def cabinet_callback_with_individual_stats(update, context):
        query = update.callback_query
        if not query or not live23._admin_private(update):
            return await previous_callback(update, context)
        data = str(query.data or "")

        if data == "cab:individuals":
            await query.answer()
            await query.edit_message_text(
                _individuals_overview_text(),
                parse_mode="HTML",
                reply_markup=_individuals_overview_markup(),
            )
            return

        if data.startswith("cab:individual:stats:"):
            try:
                student_id = int(data.rsplit(":", 1)[1])
            except Exception:
                return
            row = live67._individual_by_id(student_id)
            if not row:
                await query.answer("Ученица не найдена")
                return
            await query.answer()
            await query.edit_message_text(
                _stats_text(row),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Обновить", callback_data=f"cab:individual:stats:{student_id}")],
                    [InlineKeyboardButton("← К ученице", callback_data=f"cab:individual:{student_id}")],
                ]),
            )
            return

        if re.fullmatch(r"cab:individual:\d+", data):
            student_id = int(data.rsplit(":", 1)[1])
            row = live67._individual_by_id(student_id)
            if not row:
                await query.answer("Ученица не найдена")
                return
            await query.answer()
            await query.edit_message_text(
                _individual_detail_text(row),
                parse_mode="HTML",
                reply_markup=_individual_detail_markup(student_id, row[2]),
            )
            return

        return await previous_callback(update, context)

    live23.cabinet_callback = cabinet_callback_with_individual_stats
    _INSTALLED = True
    print("Individual daily trainer reminders ready: every day 16:00", flush=True)
    print("Individual trainer admin statistics ready", flush=True)
