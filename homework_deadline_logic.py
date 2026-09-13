"""Deadline-aware homework logistics for EGE BLIZKO.

Rules requested by Maria:
- Sunday-track homework -> next Sunday-track lesson
- Monday homework -> Wednesday lesson
- Wednesday homework -> next Monday lesson

This module is a late production patch. It replaces the old assumption that
homework is always due at the next chronological lesson, which incorrectly
made Sunday homework look overdue on Monday.
"""
import html
import sqlite3
from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90

live79 = live90.live79
live31 = live79.live31
live34 = live79.live34
live23 = live79.live23
live7 = live79.live7
run_bot = live79.run_bot
bot = live90.bot

_INSTALLED = False

# Group message after the lesson. Monday/Wednesday lessons start at 18:30;
# Sunday-track lessons start at 10:00.
GROUP_TIME_WEEKDAY = time(20, 30)
GROUP_TIME_SUNDAY_TRACK = time(13, 0)
PERSONAL_DEADLINE_HOUR = 21


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS homework_deadline_group_reminders (
                source_lesson_number INTEGER PRIMARY KEY,
                source_lesson_date TEXT NOT NULL,
                due_lesson_number INTEGER NOT NULL,
                due_date TEXT NOT NULL,
                sent_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _course_dates():
    return tuple(run_bot.COURSE_LESSON_DATES)


def _is_sunday_track(lesson_date):
    special = set(getattr(run_bot, "SPECIAL_LESSON_DATES", set()) or set())
    return lesson_date.weekday() == 6 or lesson_date in special


def _track(lesson_date):
    if lesson_date.weekday() == 0:
        return "monday"
    if lesson_date.weekday() == 2:
        return "wednesday"
    if _is_sunday_track(lesson_date):
        return "sunday"
    return None


def _same_track(lesson_date, wanted):
    return _track(lesson_date) == wanted


def due_lesson_for_source(source_date):
    """Return (due_date, due_lesson_number), using the three independent tracks."""
    source_track = _track(source_date)
    wanted = {
        "monday": "wednesday",
        "wednesday": "monday",
        "sunday": "sunday",
    }.get(source_track)
    if not wanted:
        return None

    dates = _course_dates()
    for idx, lesson_date in enumerate(dates, 1):
        if lesson_date <= source_date:
            continue
        if _same_track(lesson_date, wanted):
            return lesson_date, idx
    return None


def source_lesson_for_due(due_date):
    """Return (source_date, source_lesson_number) whose homework is due on due_date."""
    due_track = _track(due_date)
    wanted = {
        "monday": "wednesday",
        "wednesday": "monday",
        "sunday": "sunday",
    }.get(due_track)
    if not wanted:
        return None

    dates = _course_dates()
    candidate = None
    for idx, lesson_date in enumerate(dates, 1):
        if lesson_date >= due_date:
            break
        if _same_track(lesson_date, wanted):
            candidate = (lesson_date, idx)
    return candidate


def _lesson_number(lesson_date):
    dates = _course_dates()
    try:
        return dates.index(lesson_date) + 1
    except ValueError:
        return None


def _explicit_match(lesson_id, lesson_name, due_lesson_number, source_lesson_number, source_date):
    """Match both new due numbering and legacy CoreApp naming.

    CoreApp historically may call work from lesson N either `lesson N` or
    `to lesson N+1`. For Sunday/Wednesday streams the pedagogical deadline is no
    longer the next chronological lesson, so we accept the legacy N+1 label too.
    """
    lesson_id_text = live31._norm(lesson_id)
    lesson_name_text = live31._norm(lesson_name)

    import re
    m = re.search(r"к\s+уроку\s*(?:№|#)?\s*(\d+)", lesson_name_text)
    if m:
        number = int(m.group(1))
        if number in {int(due_lesson_number), int(source_lesson_number) + 1}:
            return True

    number = live31._lesson_number_from_name(lesson_name_text)
    if number == int(source_lesson_number):
        return True
    if f"monitoring:lesson:{int(source_lesson_number)}" in lesson_id_text:
        return True
    if any(token in lesson_name_text for token in live31._date_tokens(source_date)):
        return True
    return False


def homework_done_sets(source_date, source_lesson_number, due_date, due_lesson_number, now=None):
    """Return (done_ids, done_emails, assignment_evidence).

    We deliberately do not guess an assignment from the latest arbitrary
    CoreApp lesson_id. Cross-track guessing is exactly what can mix Sunday work
    into Monday debts. If CoreApp has no identifiable record yet, the homework
    is not treated as a debt.
    """
    now = now or datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT received_at, user_id, lower(user_email), lesson_id, lesson_name
            FROM homework_submissions
            """
        ).fetchall()

    chosen = [
        row for row in rows
        if _explicit_match(
            row[3], row[4], due_lesson_number, source_lesson_number, source_date
        )
    ]
    done_ids = {str(row[1] or "").strip() for row in chosen if row[1]}
    done_emails = {live31._norm(row[2]) for row in chosen if row[2]}
    return done_ids, done_emails, bool(chosen)


def _student_rows(conn, linked_only=False):
    linked = " AND telegram_user_id IS NOT NULL" if linked_only else ""
    return conn.execute(
        f"""
        SELECT coreapp_user_id,
               lower(user_email),
               telegram_user_id,
               coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик')
        FROM students
        WHERE active = 1{linked}
        ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
        """
    ).fetchall()


def _is_done(coreapp_user_id, email, done_ids, done_emails):
    return bool(
        (coreapp_user_id and str(coreapp_user_id).strip() in done_ids)
        or (email and live31._norm(email) in done_emails)
    )


def _weekday_ru(d):
    return {
        0: "понедельнику",
        1: "вторнику",
        2: "среде",
        3: "четвергу",
        4: "пятнице",
        5: "субботе",
        6: "воскресенью",
    }[d.weekday()]


def _source_label(d):
    return {
        0: "понедельничного",
        2: "средового",
        6: "воскресного",
    }.get(d.weekday(), "воскресного" if _is_sunday_track(d) else "этого")


def _group_text(source_date, source_lesson_number, due_date, due_lesson_number):
    if _is_sunday_track(source_date):
        rule = (
            "Если сегодня было задано ДЗ, его срок — <b>к следующему воскресному уроку</b>.\n"
            "В понедельник эта работа <b>не считается долгом</b> — на неё есть вся неделя."
        )
    elif source_date.weekday() == 0:
        rule = "Если сегодня было задано ДЗ, его нужно сделать <b>к среде</b>."
    else:
        rule = "Если сегодня было задано ДЗ, его нужно сделать <b>к следующему понедельнику</b>."

    return (
        "📝 <b>Домашняя работа</b> 💗\n\n"
        f"После урока №{source_lesson_number} действует такой срок:\n"
        f"{rule}\n\n"
        f"📅 Дедлайн: <b>{due_date.strftime('%d.%m')}</b> · к уроку №{due_lesson_number}.\n\n"
        "Не копим всё на последний вечер: лучше сделать часть спокойно заранее 🧪"
    )


def _group_already_sent(source_lesson_number):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM homework_deadline_group_reminders WHERE source_lesson_number = ?",
            (int(source_lesson_number),),
        ).fetchone())


def _mark_group_sent(source_lesson_number, source_date, due_lesson_number, due_date, now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO homework_deadline_group_reminders
                (source_lesson_number, source_lesson_date, due_lesson_number, due_date, sent_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(source_lesson_number), source_date.isoformat(),
                int(due_lesson_number), due_date.isoformat(), now.isoformat(),
            ),
        )
        conn.commit()


async def group_deadline_tick(context):
    now = datetime.now(bot.TIMEZONE)
    today = now.date()
    source_lesson_number = _lesson_number(today)
    if not source_lesson_number:
        return
    due = due_lesson_for_source(today)
    if not due:
        return
    due_date, due_lesson_number = due
    send_after = GROUP_TIME_SUNDAY_TRACK if _is_sunday_track(today) else GROUP_TIME_WEEKDAY
    if now.time() < send_after or _group_already_sent(source_lesson_number):
        return

    chat_id = bot.os.getenv("CHAT_ID", "").strip()
    if not chat_id:
        return
    try:
        await context.bot.send_message(
            chat_id=int(chat_id),
            message_thread_id=bot.get_target_thread_id(),
            text=_group_text(today, source_lesson_number, due_date, due_lesson_number),
            parse_mode="HTML",
        )
    except Exception as exc:
        print(f"Homework deadline group reminder failed lesson={source_lesson_number}: {exc}", flush=True)
        return
    _mark_group_sent(source_lesson_number, today, due_lesson_number, due_date, now)
    print(
        f"Homework deadline group reminder sent source={source_lesson_number} due={due_lesson_number}",
        flush=True,
    )


async def legacy_group_homework_noop(context):
    """Disable the old generic 19:00 reminder; deadline-aware tick replaces it."""
    return


def _personal_markup():
    admin_id = bot.get_admin_id()
    if not admin_id:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✉️ Написать Марии Александровне",
            url=f"tg://user?id={int(admin_id)}",
        )
    ]])


async def personal_homework_reminder_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.hour < PERSONAL_DEADLINE_HOUR:
        return

    tomorrow = now.date() + bot.timedelta(days=1)
    if tomorrow not in set(_course_dates()):
        return
    source = source_lesson_for_due(tomorrow)
    if not source:
        return
    source_date, source_lesson_number = source
    due_lesson_number = _lesson_number(tomorrow)
    if not due_lesson_number:
        return

    done_ids, done_emails, evidence = homework_done_sets(
        source_date, source_lesson_number, tomorrow, due_lesson_number, now
    )
    # If CoreApp has no identifiable homework for that source lesson, do not
    # manufacture a debt or nag students about a task that may not exist.
    if not evidence:
        return

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for coreapp_user_id, email, telegram_user_id, _name in _student_rows(conn, linked_only=True):
            telegram_user_id = int(telegram_user_id)
            if _is_done(coreapp_user_id, email, done_ids, done_emails):
                continue
            if live31._already_sent(conn, due_lesson_number, telegram_user_id):
                continue
            try:
                await context.bot.send_message(
                    chat_id=telegram_user_id,
                    text=(
                        "📝 <b>Напоминаю про ДЗ</b> 💗\n\n"
                        f"Это домашняя работа после {_source_label(source_date)} урока "
                        f"{source_date.strftime('%d.%m')}.\n"
                        f"Срок — <b>завтра, {tomorrow.strftime('%d.%m')}</b>, к уроку №{due_lesson_number}.\n\n"
                        "Если ещё не отправил(а) её в CoreApp, постарайся спокойно закрыть сегодня.\n\n"
                        "Если нужна помощь — напиши Марии Александровне 👇"
                    ),
                    parse_mode="HTML",
                    reply_markup=_personal_markup(),
                )
            except Exception as exc:
                print(f"Homework deadline DM failed uid={telegram_user_id}: {exc}", flush=True)
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO personal_homework_reminders
                    (target_lesson_number, telegram_user_id, sent_at)
                VALUES (?, ?, ?)
                """,
                (int(due_lesson_number), telegram_user_id, now.isoformat()),
            )
            conn.commit()


def _assignment_records_due_by(today):
    records = []
    for source_no, source_date in enumerate(_course_dates(), 1):
        if source_date > today:
            break
        due = due_lesson_for_source(source_date)
        if not due:
            continue
        due_date, due_no = due
        if due_date <= today:
            records.append((source_no, source_date, due_no, due_date))
    return records


def _homework_metric(conn, student_row, today):
    # Use the last HOMEWORK_LOOKBACK *actual, evidenced* assignments whose own
    # deadline has arrived. Sunday work does not enter this list on Monday.
    student_id, _display, _user_name, email, coreapp_user_id, _telegram_id = student_row
    evidenced = []
    now = datetime.combine(today, time.max, tzinfo=bot.TIMEZONE)
    for source_no, source_date, due_no, due_date in _assignment_records_due_by(today):
        done_ids, done_emails, evidence = homework_done_sets(
            source_date, source_no, due_date, due_no, now
        )
        if evidence:
            evidenced.append((source_no, source_date, due_no, due_date, done_ids, done_emails))
    expected = evidenced[-live34.HOMEWORK_LOOKBACK:]
    if len(expected) < 2:
        return None

    missing = 0
    for _source_no, _source_date, _due_no, _due_date, done_ids, done_emails in expected:
        if not _is_done(coreapp_user_id, email, done_ids, done_emails):
            missing += 1
    if missing < live34.HOMEWORK_MISSING_THRESHOLD:
        return None
    return {
        "key": "homework",
        "value": missing,
        "label": f"ДЗ: не закрыто {missing} из {len(expected)} последних работ с наступившим сроком",
    }


def _status_for_assignment(source_no, source_date, due_no, due_date, now):
    done_ids, done_emails, evidence = homework_done_sets(
        source_date, source_no, due_date, due_no, now
    )
    if not evidence:
        return None
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        students = _student_rows(conn, linked_only=False)
    done = []
    missing = []
    for coreapp_user_id, email, _telegram_id, name in students:
        (done if _is_done(coreapp_user_id, email, done_ids, done_emails) else missing).append(str(name))
    return done, missing


def homework_summary_text():
    now = datetime.now(bot.TIMEZONE)
    today = now.date()
    records = []
    # Show recent/active homework streams, not merely the chronologically latest lesson.
    for source_no, source_date in enumerate(_course_dates(), 1):
        if source_date > today:
            break
        due = due_lesson_for_source(source_date)
        if not due:
            continue
        due_date, due_no = due
        # Keep the most relevant window: deadlines no older than 7 days, plus future active ones.
        if (today - due_date).days <= 7:
            records.append((source_no, source_date, due_no, due_date))
    records = records[-5:]

    lines = [
        "🏠 <b>ДЗ / CoreApp — по реальным дедлайнам</b>",
        "",
        "Правило: <b>Вс→Вс · Пн→Ср · Ср→Пн</b>.",
        "До своего дедлайна работа долгом не считается.",
    ]
    if not records:
        lines.extend(["", "Пока нет домашних работ в актуальном окне."])
        return "\n".join(lines)

    for source_no, source_date, due_no, due_date in records:
        status = _status_for_assignment(source_no, source_date, due_no, due_date, now)
        source_name = {0: "Пн", 2: "Ср", 6: "Вс"}.get(source_date.weekday(), "Вс" if _is_sunday_track(source_date) else "Урок")
        if due_date > today:
            deadline_state = f"⏳ до {due_date.strftime('%d.%m')} — ещё не долг"
        elif due_date == today:
            deadline_state = f"🟡 срок сегодня {due_date.strftime('%d.%m')}"
        else:
            deadline_state = f"🔴 срок был {due_date.strftime('%d.%m')}"
        lines.extend([
            "",
            f"<b>{source_name} {source_date.strftime('%d.%m')} · урок №{source_no}</b>",
            f"→ {deadline_state} · урок №{due_no}",
        ])
        if status is None:
            lines.append("CoreApp пока не дал подтверждения, что по этому уроку есть ДЗ — в долг не считаю.")
            continue
        done, missing = status
        lines.append(f"✅ Закрыли: {len(done)} · ⏳ Не закрыли: {len(missing)}")
        if missing and due_date <= today:
            lines.append("Долг сейчас:")
            lines.extend(f"• {html.escape(name)}" for name in missing)
        elif missing:
            lines.append("До дедлайна осталось закрыть:")
            lines.extend(f"• {html.escape(name)}" for name in missing)
    return "\n".join(lines)


def _verify_rules():
    # Concrete first-week checks make accidental regression obvious at startup.
    from datetime import date
    checks = {
        date(2026, 9, 13): date(2026, 9, 20),  # Sunday -> Sunday
        date(2026, 9, 14): date(2026, 9, 16),  # Monday -> Wednesday
        date(2026, 9, 16): date(2026, 9, 21),  # Wednesday -> Monday
    }
    for source, expected_due in checks.items():
        result = due_lesson_for_source(source)
        if not result or result[0] != expected_due:
            raise RuntimeError(f"Homework deadline rule failed: {source} -> {result}, expected {expected_due}")


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_tables()
    _verify_rules()

    # Replace generic scheduled job before live24.main registers it.
    bot.daily_homework_reminder = legacy_group_homework_noop

    # The existing periodic wrapper calls this global name dynamically.
    live31.personal_homework_reminder_tick = personal_homework_reminder_tick

    # Zone-of-attention debt metric now respects actual deadlines.
    live34._homework_metric = _homework_metric

    # Admin cabinet also explains active deadlines instead of showing Sunday as a Monday debt.
    live23.homework_summary_text = homework_summary_text

    previous_tick = live7.friday_trivial_tick

    async def combined_tick(context):
        try:
            await previous_tick(context)
        finally:
            await group_deadline_tick(context)

    live7.friday_trivial_tick = combined_tick
    _INSTALLED = True
    print("Homework deadline logistics ready: Sun->Sun, Mon->Wed, Wed->Mon", flush=True)
    print("Homework debts now start only when their own deadline arrives", flush=True)
    print("Homework group reminders: Sunday-track 13:00; Mon/Wed 20:30", flush=True)
