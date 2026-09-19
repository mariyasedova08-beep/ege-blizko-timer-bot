"""Show every evidenced unfinished CoreApp homework in student/parent cabinet."""
import sqlite3
from datetime import datetime

import run_bot_live90 as live90
import run_bot_live49 as student_cabinet
import homework_deadline_logic as deadlines

bot = live90.bot
live31 = live90.live79.live31

_INSTALLED = False


def _student_identity(student):
    return str(student[4] or "").strip(), live31._norm(student[3])


def _all_assignments(student, today=None):
    today = today or datetime.now(bot.TIMEZONE).date()
    now = datetime.now(bot.TIMEZONE)
    user_id, email = _student_identity(student)
    items = []

    for source_no, source_date in enumerate(deadlines._course_dates(), 1):
        if source_date > today:
            break
        due = deadlines.due_lesson_for_source(source_date)
        if not due:
            continue
        due_date, due_no = due

        done_ids, done_emails, evidence = deadlines.homework_done_sets(
            source_date, source_no, due_date, due_no, now
        )
        if not evidence:
            # Do not manufacture a task when Core has never shown evidence
            # that homework exists for this source lesson.
            continue

        is_done = deadlines._is_done(user_id, email, done_ids, done_emails)
        items.append(
            {
                "source_no": int(source_no),
                "source_date": source_date,
                "due_no": int(due_no),
                "due_date": due_date,
                "done": bool(is_done),
                "overdue": bool(not is_done and due_date < today),
                "due_today": bool(not is_done and due_date == today),
                "active": bool(not is_done and due_date > today),
            }
        )
    return items


def homework_text_all_debts(student):
    today = datetime.now(bot.TIMEZONE).date()
    items = _all_assignments(student, today)
    unfinished = [x for x in items if not x["done"]]
    overdue = [x for x in unfinished if x["overdue"]]
    active = [x for x in unfinished if not x["overdue"]]
    completed = [x for x in items if x["done"]]

    lines = [
        "🏠 Домашние работы",
        "",
        f"⏳ Не выполнено: {len(unfinished)}",
        f"🔴 Просрочено: {len(overdue)}",
        f"✅ Закрыто: {len(completed)}",
    ]

    if not unfinished:
        lines.extend(["", "Все домашние работы с известными заданиями закрыты 💗"])
    else:
        if overdue:
            lines.extend(["", "🔴 Долги:"])
            for item in overdue:
                lines.append(
                    f"• ДЗ после урока №{item['source_no']} · "
                    f"срок был {item['due_date'].strftime('%d.%m')}"
                )
        if active:
            lines.extend(["", "⏳ Ещё не выполнено, но срок не прошёл:"])
            for item in active:
                state = "срок сегодня" if item["due_today"] else "до"
                lines.append(
                    f"• ДЗ после урока №{item['source_no']} · "
                    f"{state} {item['due_date'].strftime('%d.%m')}"
                )

    if completed:
        lines.extend(["", "✅ Последние закрытые:"])
        for item in completed[-6:][::-1]:
            lines.append(f"• ДЗ после урока №{item['source_no']}")

    lines.extend([
        "",
        "Здесь показываются все известные CoreApp работы — старые долги больше не скрываются.",
    ])
    return "\n".join(lines)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    student_cabinet._homework_text = homework_text_all_debts

    try:
        students = []
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            students = conn.execute(
                """
                SELECT id,
                       coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                       user_name,user_email,coreapp_user_id,telegram_user_id
                FROM students
                WHERE active=1
                """
            ).fetchall()
        unfinished_total = 0
        students_with_debt = 0
        for student in students:
            missing = [x for x in _all_assignments(student) if not x["done"]]
            unfinished_total += len(missing)
            if missing:
                students_with_debt += 1
        print(
            "Student homework all-debts ready: "
            f"students={len(students)} students_with_unfinished={students_with_debt} "
            f"unfinished_total={unfinished_total}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"Student homework all-debts audit failed: {type(exc).__name__}: {exc}",
            flush=True,
        )
