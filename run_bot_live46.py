import sqlite3
from datetime import datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live45
import run_bot_live15 as live15

live45 = run_bot_live45
live44 = live45.live44
live43 = live45.live43
live42 = live45.live42
live41 = live45.live41
live40 = live45.live40
live39 = live45.live39
live37 = live45.live37
live35 = live45.live35
live34 = live45.live34
live31 = live45.live31
live24 = live45.live24
live17 = live45.live17
live7 = live34.live7
bot = live45.bot

MONTHLY_REPORT_AFTER = time(21, 30)
COURSE_NAME = "Годовой курс подготовки к ЕГЭ по Химии"


def ensure_monthly_auto_report_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_auto_report_deliveries (
                month_key TEXT NOT NULL,
                recipient_type TEXT NOT NULL,
                recipient_telegram_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL DEFAULT 0,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (month_key, recipient_type, recipient_telegram_id, student_id)
            )
            """
        )
        conn.commit()


def _month_key(year, month):
    return f"{year:04d}-{month:02d}"


def _is_last_day(now):
    return (now.date() + timedelta(days=1)).month != now.month


def _sent(month_key, recipient_type, recipient_telegram_id, student_id=0):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            """
            SELECT 1 FROM monthly_auto_report_deliveries
            WHERE month_key = ? AND recipient_type = ?
              AND recipient_telegram_id = ? AND student_id = ?
            LIMIT 1
            """,
            (month_key, recipient_type, int(recipient_telegram_id), int(student_id)),
        ).fetchone())


def _mark_sent(month_key, recipient_type, recipient_telegram_id, student_id=0):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO monthly_auto_report_deliveries
                (month_key, recipient_type, recipient_telegram_id, student_id, sent_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                month_key,
                recipient_type,
                int(recipient_telegram_id),
                int(student_id),
                datetime.now(bot.TIMEZONE).isoformat(),
            ),
        )
        conn.commit()


def _parent_ids(student_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return [int(row[0]) for row in conn.execute(
            """
            SELECT telegram_user_id
            FROM parent_links
            WHERE student_id = ? AND active = 1
            ORDER BY id
            """,
            (int(student_id),),
        ).fetchall()]


def _contact_markup():
    admin_id = bot.get_admin_id()
    if not admin_id:
        return None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✉️ Написать Марии Александровне",
            url=f"tg://user?id={int(admin_id)}",
        )]
    ])


# Старый месячный отчёт учитывал только тренажёр тривиальных названий.
# Добавляем к нему тренажёр кислот и кислотных остатков, чтобы месячная статистика
# соответствовала недельному отчёту и реальной активности ученика.
_original_student_month_metrics = live15._student_month_metrics


def _student_month_metrics_all_trainers(conn, student, year, month, probnik_names):
    metrics = _original_student_month_metrics(conn, student, year, month, probnik_names)
    telegram_user_id = student[4]
    if telegram_user_id is None:
        return metrics
    iso_prefix = f"{year:04d}-{month:02d}"
    acid_sessions, acid_total, acid_correct = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
        FROM acid_sessions
        WHERE telegram_user_id = ?
          AND finished_at IS NOT NULL
          AND finished_at LIKE ?
        """,
        (int(telegram_user_id), iso_prefix + "%"),
    ).fetchone()
    metrics["trainer_sessions"] += int(acid_sessions or 0)
    metrics["trainer_total"] += int(acid_total or 0)
    metrics["trainer_correct"] += int(acid_correct or 0)
    return metrics


live15._student_month_metrics = _student_month_metrics_all_trainers


def _student_metrics(student, year, month):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        names = live15._probnik_names_for_month(conn, year, month)
        return live15._student_month_metrics(conn, student, year, month, names)


def _student_text(student, year, month):
    metrics = _student_metrics(student, year, month)
    shown_name = str(student[1] or "").strip()
    first_name = shown_name.split()[0] if shown_name else ""
    greeting = f"Привет, {first_name}! 💗" if first_name else "Привет! 💗"
    lines = [
        greeting,
        "",
        f"📅 Твои итоги месяца: {live15.MONTH_NAMES[month]} {year}",
        f"🎓 {COURSE_NAME}",
        "",
    ]
    lines.extend(live15._metrics_lines(metrics))
    lines.extend([
        "",
        "Это твоя статистика за месяц. Если хочешь что-то обсудить — напиши Марии Александровне 💗",
    ])
    return "\n".join(lines)


def _parent_text(student, year, month):
    metrics = _student_metrics(student, year, month)
    shown_name = str(student[1] or "Ученик").strip()
    lines = [
        "Здравствуйте!",
        "",
        f"👨‍👩‍👧 Итоги месяца по курсу «{COURSE_NAME}»",
        f"📅 {live15.MONTH_NAMES[month]} {year}",
        f"👩‍🎓 Ученик: {shown_name}",
        "",
    ]
    lines.extend(live15._metrics_lines(metrics))
    lines.extend([
        "",
        "Это текущая учебная статистика за месяц.",
        "Если есть вопросы или нужно что-то уточнить — напишите Марии Александровне 💗",
    ])
    return "\n".join(lines)


async def _send_long(context, chat_id, text):
    remaining = text
    while remaining:
        if len(remaining) <= 3800:
            await context.bot.send_message(chat_id=int(chat_id), text=remaining)
            return
        split_at = remaining.rfind("\n\n", 0, 3800)
        if split_at < 1:
            split_at = remaining.rfind("\n", 0, 3800)
        if split_at < 1:
            split_at = 3800
        await context.bot.send_message(chat_id=int(chat_id), text=remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")


async def automatic_monthly_report_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if not _is_last_day(now) or now.time() < MONTHLY_REPORT_AFTER:
        return

    year, month = now.year, now.month
    key = _month_key(year, month)
    admin_id = bot.get_admin_id()

    # Маше — полная статистика по всей группе.
    if admin_id and not _sent(key, "admin", admin_id, 0):
        try:
            text = "📅 АВТОМАТИЧЕСКИЙ ИТОГ МЕСЯЦА\n\n" + live15.monthly_report_text(year, month)
            await _send_long(context, admin_id, text)
        except Exception as exc:
            print(f"Could not send monthly group report to admin: {exc}")
        else:
            _mark_sent(key, "admin", admin_id, 0)

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = live15._active_students(conn)

    markup = _contact_markup()
    for student in students:
        student_id = int(student[0])
        telegram_id = student[4]

        # Ученику — только его персональная статистика.
        if telegram_id is not None and not _sent(key, "student", telegram_id, student_id):
            try:
                await context.bot.send_message(
                    chat_id=int(telegram_id),
                    text=_student_text(student, year, month),
                    reply_markup=markup,
                )
            except Exception as exc:
                print(f"Could not send monthly student report to {telegram_id}: {exc}")
            else:
                _mark_sent(key, "student", telegram_id, student_id)

        # Каждому подключённому родителю — статистика только его ребёнка.
        for parent_id in _parent_ids(student_id):
            if _sent(key, "parent", parent_id, student_id):
                continue
            try:
                await context.bot.send_message(
                    chat_id=int(parent_id),
                    text=_parent_text(student, year, month),
                    reply_markup=markup,
                )
            except Exception as exc:
                print(f"Could not send monthly parent report to {parent_id}: {exc}")
            else:
                _mark_sent(key, "parent", parent_id, student_id)


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_monthly_reports(context):
    try:
        await _previous_tick(context)
    finally:
        await automatic_monthly_report_tick(context)


live7.friday_trivial_tick = combined_tick_with_monthly_reports


_previous_test = bot.test


async def test_with_monthly_preview(update, context):
    is_monthly = bool(context.args) and context.args[0].lower() in {"monthly", "month", "месяц"}
    if not is_monthly:
        await _previous_test(update, context)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return

    now = datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = live15._active_students(conn)

    await update.message.reply_text(
        "🧪 ТЕСТ — всё ниже видишь только ты. Ученикам и родителям ничего не отправлено."
    )
    await _send_long(
        context,
        update.effective_chat.id,
        "📅 ПРИМЕР ОТЧЁТА ДЛЯ ТЕБЯ\n\n" + live15.monthly_report_text(now.year, now.month),
    )
    if not students:
        return
    sample = students[0]
    await update.message.reply_text(
        "🧪 ПРИМЕР СООБЩЕНИЯ УЧЕНИКУ\n\n" + _student_text(sample, now.year, now.month),
        reply_markup=_contact_markup(),
    )
    await update.message.reply_text(
        "🧪 ПРИМЕР СООБЩЕНИЯ РОДИТЕЛЮ\n\n" + _parent_text(sample, now.year, now.month),
        reply_markup=_contact_markup(),
    )


bot.test = test_with_monthly_preview


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
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    ensure_monthly_auto_report_table()
    live24.main()
