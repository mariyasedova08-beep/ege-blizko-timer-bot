import json
import sqlite3
from datetime import datetime, timedelta

import run_bot_live42

live42 = run_bot_live42
live41 = live42.live41
live40 = live42.live40
live39 = live42.live39
live37 = live42.live37
live35 = live42.live35
live34 = live42.live34
live31 = live42.live31
live24 = live42.live24
live17 = live42.live17
live7 = live34.live7
bot = live42.bot

PROBNIK_ANALYSIS_SETTLE_MINUTES = 10


def ensure_probnik_analysis_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probnik_analysis_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                enabled INTEGER NOT NULL DEFAULT 0,
                enabled_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO probnik_analysis_settings (id, enabled) VALUES (1, 0)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probnik_analysis_events (
                event_name TEXT NOT NULL,
                event_date TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                student_reports_sent INTEGER NOT NULL DEFAULT 0,
                student_reports_unmatched INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (event_name, event_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probnik_analysis_deliveries (
                event_name TEXT NOT NULL,
                event_date TEXT NOT NULL,
                result_student_name TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (event_name, event_date, result_student_name)
            )
            """
        )
        conn.commit()


def _analysis_settings():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT enabled, enabled_at FROM probnik_analysis_settings WHERE id = 1"
        ).fetchone()
    return (bool(row[0]), row[1]) if row else (False, None)


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def _score_text(value):
    if value is None:
        return "—"
    try:
        number = float(value)
    except Exception:
        return str(value)
    return str(int(number)) if number.is_integer() else str(round(number, 1)).replace(".", ",")


def _event_rows(event_name, event_date):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT student_name, primary_score, secondary_score, tasks_json, synced_at
            FROM probnik_results
            WHERE event_name = ? AND event_date = ?
            ORDER BY student_name
            """,
            (event_name, event_date),
        ).fetchall()


def _latest_event():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT event_name, event_date, MAX(synced_at)
            FROM probnik_results
            GROUP BY event_name, event_date
            ORDER BY MAX(synced_at) DESC
            LIMIT 1
            """
        ).fetchone()


def _zero_tasks(tasks_json):
    try:
        tasks = json.loads(tasks_json or "{}")
    except Exception:
        tasks = {}
    zeros = []
    for task, value in tasks.items():
        score = _num(value)
        if score is None:
            continue
        try:
            number = int(str(task).strip())
        except Exception:
            continue
        if 1 <= number <= 34 and score == 0:
            zeros.append(number)
    return sorted(set(zeros))


def _first_name(name):
    text = str(name or "").strip()
    return text.split()[0] if text else ""


def student_probnik_analysis_text(student_name, event_name, event_date, secondary_score, tasks_json):
    first_name = _first_name(student_name)
    greeting = f"Привет, {first_name}! 💗" if first_name else "Привет! 💗"
    weak = _zero_tasks(tasks_json)
    lines = [
        greeting,
        "",
        f"🧠 Разбор пробника — {event_name}",
        f"📅 {event_date}",
        f"📊 Результат: {_score_text(secondary_score)} баллов",
        "",
    ]
    if weak:
        shown = weak[:8]
        lines.append("❌ Задания, где пока не набраны баллы: " + ", ".join(f"№{n}" for n in shown))
        if len(weak) > len(shown):
            lines.append(f"И ещё {len(weak) - len(shown)} заданий.")
        focus = shown[:3]
        lines.extend([
            "",
            "🎯 Фокус на ближайшую отработку: " + ", ".join(f"№{n}" for n in focus) + ".",
            "Не пытайся закрыть всё сразу: сначала разберись с 2–3 номерами, затем переходи к следующим.",
        ])
    else:
        lines.extend([
            "✅ В таблице этого пробника нет заданий с 0 баллов.",
            "",
            "🎯 Продолжай закреплять темы и обращай внимание на задания, где балл был набран не полностью.",
        ])
    lines.extend([
        "",
        "Ниже оставляю доступные тренажёры для короткой отработки 👇",
    ])
    return "\n".join(lines)


def group_probnik_analysis_text(event_name, event_date, rows, sent=None, unmatched=None):
    task_stats = {i: [0, 0] for i in range(1, 35)}  # zero, answered
    scores = []
    for _student_name, _primary, secondary, tasks_json, _synced_at in rows:
        if secondary is not None:
            try:
                scores.append(float(secondary))
            except Exception:
                pass
        try:
            tasks = json.loads(tasks_json or "{}")
        except Exception:
            tasks = {}
        for task, value in tasks.items():
            try:
                number = int(str(task).strip())
            except Exception:
                continue
            if number not in task_stats:
                continue
            score = _num(value)
            if score is None:
                continue
            task_stats[number][1] += 1
            if score == 0:
                task_stats[number][0] += 1

    ranked = []
    for task, (zeros, answered) in task_stats.items():
        if answered:
            pct = round(zeros * 100 / answered)
            ranked.append((pct, zeros, answered, task))
    ranked.sort(key=lambda x: (-x[0], -x[1], x[3]))

    avg = round(sum(scores) / len(scores), 1) if scores else None
    lines = [
        "🧠 Разбор слабых мест группы",
        "",
        f"📝 {event_name}",
        f"📅 {event_date}",
        f"Написали: {len(rows)}",
        f"Средний вторичный балл: {_score_text(avg)}",
    ]
    if ranked:
        lines.extend(["", "🚨 Самые слабые номера по этому пробнику:"])
        for pct, zeros, answered, task in ranked[:8]:
            lines.append(f"• №{task} — 0 баллов у {zeros} из {answered} ({pct}%)")
    else:
        lines.extend(["", "Пока недостаточно данных по отдельным заданиям."])
    if sent is not None:
        lines.extend([
            "",
            f"📨 Персональных разборов отправлено: {int(sent)}",
            f"🔗 Не удалось автоматически сопоставить/доставить: {int(unmatched or 0)}",
        ])
    return "\n".join(lines)


def _normalized_student_candidates(student_row):
    values = [student_row[1], student_row[2]]
    return {live34._norm_name(v) for v in values if live34._norm_name(v)}


def _match_student(result_name, student_rows):
    target = live34._norm_name(result_name)
    if not target:
        return None
    exact = [row for row in student_rows if target in _normalized_student_candidates(row)]
    if len(exact) == 1:
        return exact[0]
    return None


def _event_processed(event_name, event_date):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM probnik_analysis_events WHERE event_name = ? AND event_date = ? LIMIT 1",
            (event_name, event_date),
        ).fetchone())


def _eligible_unprocessed_events(enabled_at, now):
    if not enabled_at:
        return []
    cutoff = now - timedelta(minutes=PROBNIK_ANALYSIS_SETTLE_MINUTES)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT event_name, event_date, MAX(synced_at) AS last_sync
            FROM probnik_results
            WHERE synced_at >= ?
            GROUP BY event_name, event_date
            HAVING MAX(synced_at) <= ?
               AND NOT EXISTS (
                    SELECT 1 FROM probnik_analysis_events e
                    WHERE e.event_name = probnik_results.event_name
                      AND e.event_date = probnik_results.event_date
               )
            ORDER BY MAX(synced_at)
            """,
            (enabled_at, cutoff.isoformat()),
        ).fetchall()


async def automatic_probnik_analysis_tick(context):
    now = datetime.now(bot.TIMEZONE)
    enabled, enabled_at = _analysis_settings()
    if not enabled:
        return

    students = live34._student_rows()
    markup = await live41._weekly_report_markup(context)
    admin_id = bot.get_admin_id()

    for event_name, event_date, _last_sync in _eligible_unprocessed_events(enabled_at, now):
        rows = _event_rows(event_name, event_date)
        if not rows:
            continue
        sent = 0
        unmatched = 0
        for result_name, _primary, secondary, tasks_json, _synced_at in rows:
            student_row = _match_student(result_name, students)
            if not student_row or student_row[5] is None:
                unmatched += 1
                continue
            telegram_id = int(student_row[5])
            try:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=student_probnik_analysis_text(
                        student_row[1], event_name, event_date, secondary, tasks_json
                    ),
                    reply_markup=markup,
                )
            except Exception as exc:
                print(f"Could not send probnik analysis to student {telegram_id}: {exc}")
                unmatched += 1
                continue
            sent += 1
            with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO probnik_analysis_deliveries
                        (event_name, event_date, result_student_name, telegram_user_id, sent_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (event_name, event_date, result_name, telegram_id, now.isoformat()),
                )
                conn.commit()

        if admin_id:
            try:
                await context.bot.send_message(
                    chat_id=int(admin_id),
                    text=group_probnik_analysis_text(
                        event_name, event_date, rows, sent=sent, unmatched=unmatched
                    ),
                )
            except Exception as exc:
                print(f"Could not send group probnik analysis to admin: {exc}")

        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO probnik_analysis_events
                    (event_name, event_date, processed_at, student_reports_sent, student_reports_unmatched)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_name, event_date, now.isoformat(), sent, unmatched),
            )
            conn.commit()


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_probnik_analysis(context):
    try:
        await _previous_tick(context)
    finally:
        await automatic_probnik_analysis_tick(context)


live7.friday_trivial_tick = combined_tick_with_probnik_analysis


_previous_test = bot.test


async def test_with_probnik_analysis(update, context):
    is_probnik = bool(context.args) and context.args[0].lower() in {"probnik", "analysis", "пробник"}
    if not is_probnik:
        await _previous_test(update, context)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return

    latest = _latest_event()
    if not latest:
        await update.message.reply_text(
            "🧪 ТЕСТ: пока нет синхронизированных результатов пробника."
        )
        return
    event_name, event_date, _last_sync = latest
    rows = _event_rows(event_name, event_date)
    await update.message.reply_text(
        "🧪 ТЕСТ — это видишь только ты. Ученикам ничего не отправлено.\n\n"
        + group_probnik_analysis_text(event_name, event_date, rows)
    )
    if rows:
        result_name, _primary, secondary, tasks_json, _synced_at = rows[0]
        markup = await live41._weekly_report_markup(context)
        await update.message.reply_text(
            "🧪 ТЕСТ персонального сообщения. Оно тоже отправлено только тебе.\n\n"
            + student_probnik_analysis_text(
                result_name, event_name, event_date, secondary, tasks_json
            ),
            reply_markup=markup,
        )


bot.test = test_with_probnik_analysis


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
    ensure_probnik_analysis_tables()
    live24.main()
