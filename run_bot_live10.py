import json
import os
import sqlite3
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import run_bot_live9

live9 = run_bot_live9
live8 = live9.live8
live7 = live9.live7
live6 = live7.live6
live4 = live7.live4
live3 = live7.live3
live2 = live7.live2
run_bot = live7.run_bot
bot = live7.bot

STATS_SHEET_TITLES = {"СТАТИСТИКА"}


def ensure_probnik_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probnik_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                event_name TEXT NOT NULL,
                event_date TEXT NOT NULL,
                primary_score REAL,
                secondary_score REAL,
                tasks_json TEXT NOT NULL,
                source_sheet TEXT,
                synced_at TEXT NOT NULL,
                UNIQUE(student_name, event_name, event_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS probnik_sync_status (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                last_synced_at TEXT,
                last_rows INTEGER NOT NULL DEFAULT 0,
                last_students INTEGER NOT NULL DEFAULT 0,
                source_title TEXT
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO probnik_sync_status (id, last_rows, last_students) VALUES (1, 0, 0)"
        )
        conn.commit()


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def save_probnik_sync(payload):
    sheets = payload.get("sheets") or []
    source_title = str(payload.get("spreadsheet_title") or "Google Sheets")
    now = datetime.now(bot.TIMEZONE).isoformat()
    rows_saved = 0
    students = set()

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for sheet in sheets:
            student_name = str(sheet.get("student_name") or sheet.get("sheet_name") or "").strip()
            sheet_name = str(sheet.get("sheet_name") or student_name).strip()
            if not student_name or student_name.upper() in STATS_SHEET_TITLES:
                continue
            results = sheet.get("results") or []
            for result in results:
                event_name = str(result.get("event_name") or "").strip()
                event_date = str(result.get("event_date") or "").strip()
                if not event_name or not event_date:
                    continue
                tasks = result.get("tasks") or {}
                primary = _num(result.get("primary_score"))
                secondary = _num(result.get("secondary_score"))
                if primary is None and secondary is None and not any(v not in (None, "") for v in tasks.values()):
                    continue
                conn.execute(
                    """
                    INSERT INTO probnik_results (
                        student_name, event_name, event_date, primary_score, secondary_score,
                        tasks_json, source_sheet, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(student_name, event_name, event_date) DO UPDATE SET
                        primary_score = excluded.primary_score,
                        secondary_score = excluded.secondary_score,
                        tasks_json = excluded.tasks_json,
                        source_sheet = excluded.source_sheet,
                        synced_at = excluded.synced_at
                    """,
                    (
                        student_name,
                        event_name,
                        event_date,
                        primary,
                        secondary,
                        json.dumps(tasks, ensure_ascii=False),
                        sheet_name,
                        now,
                    ),
                )
                rows_saved += 1
                students.add(student_name)

        conn.execute(
            """
            UPDATE probnik_sync_status
            SET last_synced_at = ?, last_rows = ?, last_students = ?, source_title = ?
            WHERE id = 1
            """,
            (now, rows_saved, len(students), source_title),
        )
        conn.commit()
    return rows_saved, len(students)


_original_do_post = bot.CoreAppWebhookHandler.do_POST


def _sheets_do_post(self):
    parsed = urlparse(self.path)
    if parsed.path != "/sheets/probnik-sync":
        return _original_do_post(self)

    expected_secret = os.getenv("SHEETS_SYNC_SECRET", "")
    supplied_secret = parse_qs(parsed.query).get("secret", [""])[0]
    if not expected_secret or supplied_secret != expected_secret:
        self._send_json(401, {"ok": False, "error": "unauthorized"})
        return

    try:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_body or "{}")
    except Exception:
        self._send_json(400, {"ok": False, "error": "invalid_json"})
        return

    try:
        rows_saved, students = save_probnik_sync(payload)
    except Exception as exc:
        print("Google Sheets probnik sync error:", repr(exc))
        self._send_json(500, {"ok": False, "error": "storage_error"})
        return

    print("Google Sheets probnik sync:", rows_saved, "rows,", students, "students")
    self._send_json(200, {"ok": True, "rows_saved": rows_saved, "students": students})


bot.CoreAppWebhookHandler.do_POST = _sheets_do_post


def _admin_private(update):
    return update.effective_chat.type == "private" and bot.user_is_admin(update)


def _score_text(value):
    if value is None:
        return "—"
    return str(int(value)) if float(value).is_integer() else str(round(value, 1)).replace(".", ",")


def get_events():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT event_name, event_date, COUNT(*), AVG(secondary_score)
            FROM probnik_results
            WHERE secondary_score IS NOT NULL
            GROUP BY event_name, event_date
            ORDER BY substr(event_date, 7, 4), substr(event_date, 4, 2), substr(event_date, 1, 2)
            """
        ).fetchall()


def probnik_stats_text(event_name=None):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        if event_name:
            row = conn.execute(
                """
                SELECT event_name, event_date
                FROM probnik_results
                WHERE lower(event_name) = lower(?)
                ORDER BY synced_at DESC LIMIT 1
                """,
                (event_name,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT event_name, event_date
                FROM probnik_results
                WHERE secondary_score IS NOT NULL
                ORDER BY substr(event_date, 7, 4) DESC, substr(event_date, 4, 2) DESC,
                         substr(event_date, 1, 2) DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return "📝 Результатов пробников пока нет. Сначала синхронизируй Google-таблицу."
        name, date_text = row
        results = conn.execute(
            """
            SELECT student_name, primary_score, secondary_score, tasks_json
            FROM probnik_results
            WHERE event_name = ? AND event_date = ? AND secondary_score IS NOT NULL
            ORDER BY secondary_score DESC, student_name
            """,
            (name, date_text),
        ).fetchall()

    scores = [r[2] for r in results if r[2] is not None]
    avg = round(sum(scores) / len(scores), 1) if scores else 0
    lines = [
        f"📝 {name}",
        f"📅 {date_text}",
        "",
        f"Написали: {len(results)}",
        f"Средний вторичный балл: {_score_text(avg)}",
    ]
    if results:
        lines.append(f"Лучший результат: {results[0][0]} — {_score_text(results[0][2])}")

    task_totals = {str(i): [0.0, 0.0] for i in range(1, 35)}
    for _, _, _, tasks_json in results:
        try:
            tasks = json.loads(tasks_json or "{}")
        except Exception:
            tasks = {}
        for task, value in tasks.items():
            if task not in task_totals:
                continue
            score = _num(value)
            if score is None:
                continue
            # Максимальный балл берём из фактически встречавшихся значений: минимум 1.
            task_totals[task][0] += score
            task_totals[task][1] += max(1.0, score)

    weak = []
    for task, (got, possible_proxy) in task_totals.items():
        if possible_proxy <= 0:
            continue
        # Для группового приоритета достаточно доли набранных баллов относительно 1 балла на ученика;
        # задания на 2 балла всё равно корректно ранжируются по среднему фактическому баллу.
        pct = round(got * 100 / max(1, len(results)), 0)
        weak.append((pct, int(task)))
    weak.sort()
    if weak:
        lines.extend(["", "🧪 Самые проблемные задания:"])
        for pct, task in weak[:5]:
            lines.append(f"• №{task} — в среднем {int(pct)}% от 1 балла на ученика")
    return "\n".join(lines)


def student_card_text(query_name):
    query_name = query_name.strip()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        names = [r[0] for r in conn.execute("SELECT DISTINCT student_name FROM probnik_results ORDER BY student_name").fetchall()]
        exact = next((n for n in names if n.lower() == query_name.lower()), None)
        if exact is None:
            matches = [n for n in names if query_name.lower() in n.lower()]
            if len(matches) == 1:
                exact = matches[0]
        if exact is None:
            return "Не нашла ученика. Напиши имя как на вкладке Google-таблицы."
        rows = conn.execute(
            """
            SELECT event_name, event_date, primary_score, secondary_score, tasks_json
            FROM probnik_results
            WHERE student_name = ?
            ORDER BY substr(event_date, 7, 4), substr(event_date, 4, 2), substr(event_date, 1, 2)
            """,
            (exact,),
        ).fetchall()

    lines = [f"👩‍🎓 {exact}", ""]
    secondary_scores = []
    task_misses = {str(i): 0 for i in range(1, 35)}
    for event_name, date_text, primary, secondary, tasks_json in rows:
        lines.append(f"• {event_name} ({date_text}) — {_score_text(secondary)} баллов [перв. {_score_text(primary)}]")
        if secondary is not None:
            secondary_scores.append(secondary)
        try:
            tasks = json.loads(tasks_json or "{}")
        except Exception:
            tasks = {}
        for task, value in tasks.items():
            score = _num(value)
            if task in task_misses and score == 0:
                task_misses[task] += 1

    if len(secondary_scores) >= 2:
        delta = secondary_scores[-1] - secondary_scores[0]
        sign = "+" if delta > 0 else ""
        lines.extend(["", f"📈 Динамика с первого результата: {sign}{_score_text(delta)}"])

    common_misses = [(count, int(task)) for task, count in task_misses.items() if count > 0]
    common_misses.sort(reverse=True)
    if common_misses:
        lines.extend(["", "❌ Чаще всего теряет баллы:"])
        for count, task in common_misses[:5]:
            lines.append(f"• №{task} — {count} раз(а)")
    return "\n".join(lines)


def weak_group_text():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute("SELECT tasks_json FROM probnik_results").fetchall()
    if not rows:
        return "🧪 Пока нет данных для анализа слабых заданий."
    stats = {str(i): [0.0, 0] for i in range(1, 35)}
    for (tasks_json,) in rows:
        try:
            tasks = json.loads(tasks_json or "{}")
        except Exception:
            continue
        for task, value in tasks.items():
            if task not in stats:
                continue
            score = _num(value)
            if score is None:
                continue
            stats[task][0] += score
            stats[task][1] += 1
    ranked = []
    for task, (total, n) in stats.items():
        if n:
            avg = total / n
            ranked.append((avg, int(task), n))
    ranked.sort()
    lines = ["🧪 Что повторить группе", ""]
    for avg, task, n in ranked[:8]:
        lines.append(f"• №{task} — средний балл {avg:.2f} по {n} результатам".replace(".", ","))
    return "\n".join(lines)


async def probnikstats_command(update, context):
    if not _admin_private(update):
        return
    event_name = " ".join(context.args).strip() if context.args else None
    await update.message.reply_text(probnik_stats_text(event_name))


async def student_command(update, context):
    if not _admin_private(update):
        return
    if not context.args:
        await update.message.reply_text("Например: /student НАСТЯ")
        return
    await update.message.reply_text(student_card_text(" ".join(context.args)))


async def weak_command(update, context):
    if not _admin_private(update):
        return
    await update.message.reply_text(weak_group_text())


async def sheetsstatus_command(update, context):
    if not _admin_private(update):
        return
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT last_synced_at, last_rows, last_students, source_title FROM probnik_sync_status WHERE id = 1"
        ).fetchone()
    if not row or not row[0]:
        await update.message.reply_text("🔄 Google Sheets ещё не синхронизировалась с ботом.")
        return
    synced_at, rows_count, students, title = row
    try:
        stamp = datetime.fromisoformat(synced_at).astimezone(bot.TIMEZONE).strftime("%d.%m.%Y %H:%M")
    except Exception:
        stamp = synced_at
    await update.message.reply_text(
        f"✅ Google Sheets синхронизирована\n\n{title or 'Таблица'}\nПоследняя синхронизация: {stamp}\nРезультатов: {rows_count}\nУчеников: {students}"
    )


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    run_bot.ensure_probnik_assets_table()
    live3.ensure_attendance_tables()
    live4.ensure_display_name_column()
    live6.ensure_tutor_tables()
    live7.ensure_trivial_tables()
    ensure_probnik_tables()
    application = bot.Application.builder().token(token).build()

    application.add_handler(bot.CommandHandler("start", live7.start_router))
    application.add_handler(bot.CommandHandler("ege", bot.ege))
    application.add_handler(bot.CommandHandler("weeks", bot.weeks))
    application.add_handler(bot.CommandHandler("progress", bot.progress))
    application.add_handler(bot.CommandHandler("chatid", bot.chatid))
    application.add_handler(bot.CommandHandler("threadid", bot.threadid))
    application.add_handler(bot.CommandHandler("myid", bot.myid))
    application.add_handler(bot.CommandHandler("link", bot.link))
    application.add_handler(bot.CommandHandler("corestatus", bot.corestatus))
    application.add_handler(bot.CommandHandler("homeworkstatus", bot.homeworkstatus))
    application.add_handler(bot.CommandHandler("attendance", live3.show_attendance))
    application.add_handler(bot.CommandHandler("attendancestats", live4.attendance_stats))
    application.add_handler(bot.CommandHandler("rename", live6.rename_command_wrapper))

    application.add_handler(bot.CommandHandler("tutorinvite", live6.tutor_invite))
    application.add_handler(bot.CommandHandler("tutorlink", live6.tutor_link))
    application.add_handler(bot.CommandHandler("tutorstatus", live6.tutor_status))
    application.add_handler(bot.CommandHandler("tutorreminder", live6.tutor_reminder_command))
    application.add_handler(bot.CommandHandler("tutorreminders", live6.tutor_reminders_list))
    application.add_handler(bot.CommandHandler("tutordel", live6.tutor_delete))
    application.add_handler(bot.CommandHandler("tutortest", live6.tutor_test))
    application.add_handler(bot.CommandHandler("tutorcancel", live6.tutor_cancel))

    application.add_handler(bot.CommandHandler("trivial", live7.trivial_command))
    application.add_handler(bot.CommandHandler("trivial10", live7.trivial_command))
    application.add_handler(bot.CommandHandler("trivialmistakes", live7.trivial_command))
    application.add_handler(bot.CommandHandler("trivialstats", live7.trivial_stats_command))
    application.add_handler(bot.CommandHandler("trivialtop", live7.trivial_top_command))
    application.add_handler(bot.CommandHandler("trivialannounce", live7.trivial_announce_command))
    application.add_handler(bot.CommandHandler("trivialtime", live7.set_trivial_time))
    application.add_handler(bot.CommandHandler("trivialfriday", live7.trivial_friday_status))

    application.add_handler(bot.CommandHandler("probnikstats", probnikstats_command))
    application.add_handler(bot.CommandHandler("student", student_command))
    application.add_handler(bot.CommandHandler("weak", weak_command))
    application.add_handler(bot.CommandHandler("sheetsstatus", sheetsstatus_command))

    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", live2.set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", live2.test_probnik_saturday))

    application.add_handler(live7.CallbackQueryHandler(live7.trivial_callback, pattern=r"^triv:"))
    application.add_handler(live7.CallbackQueryHandler(live3.attendance_callback, pattern=r"^att:"))
    application.add_handler(live7.CallbackQueryHandler(live4.rename_callback, pattern=r"^ren:"))

    application.add_handler(
        bot.MessageHandler(
            bot.filters.PHOTO | bot.filters.Document.IMAGE | bot.filters.Document.PDF,
            run_bot.save_probnik_asset_from_message,
        )
    )
    application.add_handler(bot.MessageHandler(bot.filters.Document.ALL, bot.import_students_document))
    application.add_handler(bot.MessageHandler(bot.filters.TEXT & ~bot.filters.COMMAND, live7.student_text_router))

    application.job_queue.run_daily(
        bot.daily_countdown,
        time=datetime.strptime("09:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )
    application.job_queue.run_daily(
        bot.daily_homework_reminder,
        time=datetime.strptime("19:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 2, 6),
    )
    application.job_queue.run_daily(
        run_bot.send_lesson_reminder,
        time=datetime.strptime("18:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(1, 3),
    )
    application.job_queue.run_daily(
        run_bot.send_lesson_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 6),
    )
    application.job_queue.run_daily(
        run_bot.probnik_daily_reminder,
        time=datetime.strptime("10:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )
    application.job_queue.run_daily(
        live2.probnik_saturday_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(6,),
    )
    application.job_queue.run_repeating(live6.tutor_reminder_tick, interval=30, first=10)
    application.job_queue.run_repeating(live7.friday_trivial_tick, interval=30, first=15)

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
