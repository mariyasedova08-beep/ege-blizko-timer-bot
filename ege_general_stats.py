"""Teacher-only combined statistics dashboard for EGE BLIZKO."""
import html
import sqlite3
from collections import Counter
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90
import run_bot_live49 as student_cabinet
import student_homework_all_debts
import payment_schedule
import kulek_rewards

bot = live90.bot
live23 = live90.live79.live23
live15 = live90.live79.live60.live15

_INSTALLED = False
_previous_markup = None
_previous_callback = None


def _students():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name,''),nullif(user_name,''),user_email,'Ученик'),
                   user_name,user_email,coreapp_user_id,telegram_user_id
            FROM students
            WHERE active=1
            ORDER BY lower(coalesce(nullif(display_name,''),nullif(user_name,''),user_email,'Ученик'))
            """
        ).fetchall()


def _homework_summary(students):
    total = done = unfinished = overdue = 0
    by_student = {}
    today = datetime.now(bot.TIMEZONE).date()
    for student in students:
        items = student_homework_all_debts._all_assignments(student, today=today)
        d = sum(1 for x in items if x["done"])
        u = sum(1 for x in items if not x["done"])
        o = sum(1 for x in items if not x["done"] and x["overdue"])
        total += len(items)
        done += d
        unfinished += u
        overdue += o
        if u:
            by_student[int(student[0])] = {"unfinished": u, "overdue": o}
    return {
        "total": total,
        "done": done,
        "unfinished": unfinished,
        "overdue": overdue,
        "students_with_unfinished": len(by_student),
        "by_student": by_student,
    }


def _attendance_summary(students, year, month):
    prefix = f"{year:04d}-{month:02d}%"
    active_ids = {int(s[0]) for s in students}
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        lessons = int(conn.execute(
            """
            SELECT COUNT(*) FROM attendance_sessions
            WHERE finalized=1 AND lesson_date LIKE ?
            """,
            (prefix,),
        ).fetchone()[0] or 0)
        rows = conn.execute(
            """
            SELECT ar.student_id,ar.status
            FROM attendance_records ar
            JOIN attendance_sessions sess ON sess.lesson_number=ar.lesson_number
            WHERE sess.finalized=1 AND sess.lesson_date LIKE ?
            """,
            (prefix,),
        ).fetchall()
    present = sum(1 for sid, status in rows if int(sid) in active_ids and status == "present")
    absent = sum(1 for sid, status in rows if int(sid) in active_ids and status == "absent")
    recorded = present + absent
    return {
        "lessons": lessons,
        "present": present,
        "absent": absent,
        "recorded": recorded,
        "percent": round(100 * present / recorded) if recorded else None,
    }


def _kulek_summary(students, year, month):
    key = f"{year:04d}-{month:02d}"
    data = kulek_rewards.month_payload(key, force=True, with_breakthrough=False)
    cards = data.get("students") or []

    prob_scores = []
    prob_students = 0
    trainer_sessions = 0
    trainer_students = 0
    trainer_earned = 0
    trainer_total = 0
    for row in cards:
        scores = [
            float(x["score"])
            for x in row["categories"]["probnik"]["items"]
            if x.get("score") is not None
        ]
        if scores:
            prob_students += 1
            prob_scores.extend(scores)

        sessions = sum(
            int(x.get("sessions") or 0)
            for x in row["categories"]["trainers"]["items"]
        )
        if sessions:
            trainer_students += 1
        trainer_sessions += sessions
        trainer_earned += int(row["categories"]["trainers"]["earned"])
        trainer_total += int(row["categories"]["trainers"]["total"])

    month_candidates = kulek_rewards.student_of_month_candidates(key)
    indexed = [x for x in month_candidates if float(x.get("available_weight") or 0) > 0]
    winner = data.get("student_of_month_winner")

    return {
        "data": data,
        "probnik_results": len(prob_scores),
        "probnik_students": prob_students,
        "probnik_avg": round(sum(prob_scores) / len(prob_scores), 1) if prob_scores else None,
        "trainer_sessions": trainer_sessions,
        "trainer_students": trainer_students,
        "trainer_earned": trainer_earned,
        "trainer_total": trainer_total,
        "student_month_avg": (
            round(sum(float(x["score"]) for x in indexed) / len(indexed), 1)
            if indexed else None
        ),
        "student_month_max": max((float(x["score"]) for x in indexed), default=None),
        "student_month_winner": winner,
    }


def _payment_summary(student_count):
    try:
        rows = payment_schedule.schedule_rows()
    except Exception:
        rows = []
    counts = Counter(row.get("cadence") for row in rows)
    overdue = [row for row in rows if int(row.get("overdue_cents") or 0) > 0]
    return {
        "connected": len(rows),
        "missing": max(0, int(student_count) - len(rows)),
        "monthly": counts["monthly"],
        "quarterly": counts["quarterly"],
        "prepaid": counts["prepaid"],
        "review": counts["review"],
        "overdue_students": len(overdue),
        "overdue_cents": sum(int(row.get("overdue_cents") or 0) for row in overdue),
    }


def _attention(students, homework, kulek):
    cards = {int(x["id"]): x for x in (kulek["data"].get("students") or [])}
    items = []
    for student in students:
        sid = int(student[0])
        reasons = []
        hw = homework["by_student"].get(sid)
        if hw:
            if hw["overdue"]:
                reasons.append(f"ДЗ: {hw['overdue']} просроч.")
            elif hw["unfinished"]:
                reasons.append(f"ДЗ: {hw['unfinished']} не закрыто")

        card = cards.get(sid)
        if card:
            trainer_sessions = sum(
                int(x.get("sessions") or 0)
                for x in card["categories"]["trainers"]["items"]
            )
            if card["categories"]["trainers"]["total"] and trainer_sessions == 0:
                reasons.append("нет тренажёров")
            if card["categories"]["probnik"]["total"] and not any(
                x.get("score") is not None
                for x in card["categories"]["probnik"]["items"]
            ):
                reasons.append("нет пробника")
        if reasons:
            items.append((str(student[1]), reasons))
    return items


def general_stats_text():
    now = datetime.now(bot.TIMEZONE)
    year, month = now.year, now.month
    students = _students()
    total_students = len(students)
    linked = sum(1 for s in students if s[5] is not None)

    homework = _homework_summary(students)
    attendance = _attendance_summary(students, year, month)
    kulek = _kulek_summary(students, year, month)
    payment = _payment_summary(total_students)
    attention = _attention(students, homework, kulek)

    kdata = kulek["data"]
    month_name = live15.MONTH_NAMES[month].lower()
    lines = [
        f"📊 <b>Общая статистика — {month_name} {year}</b>",
        "",
        "👥 <b>Ученики</b>",
        f"• активных: <b>{total_students}</b>",
        f"• Telegram привязан: <b>{linked}/{total_students}</b>",
        "",
        "🏠 <b>Домашние работы</b>",
        f"• известных работ по детям: <b>{homework['total']}</b>",
        f"• закрыто: <b>{homework['done']}</b>",
        f"• не выполнено сейчас: <b>{homework['unfinished']}</b> "
        f"у <b>{homework['students_with_unfinished']}</b> учеников",
        f"• из них просрочено: <b>{homework['overdue']}</b>",
    ]

    if attendance["recorded"]:
        lines.extend([
            "",
            "🎓 <b>Посещение</b>",
            f"• сохранено занятий за месяц: <b>{attendance['lessons']}</b>",
            f"• присутствий: <b>{attendance['present']}</b> · "
            f"пропусков: <b>{attendance['absent']}</b>",
            f"• посещаемость группы: <b>{attendance['percent']}%</b>",
        ])
    else:
        lines.extend(["", "🎓 <b>Посещение</b>", "• за месяц пока нет сохранённых отметок"])

    lines.extend([
        "",
        "📝 <b>Пробники</b>",
        f"• результатов за месяц: <b>{kulek['probnik_results']}</b>",
        f"• с результатом: <b>{kulek['probnik_students']}/{total_students}</b> учеников",
        (
            f"• средний результат группы: <b>{kulek['probnik_avg']:g}</b>"
            if kulek["probnik_avg"] is not None
            else "• среднего результата пока нет"
        ),
        "",
        "🧪 <b>Тренажёры</b>",
        f"• выполнено тренировок: <b>{kulek['trainer_sessions']}</b>",
        f"• тренировались: <b>{kulek['trainer_students']}/{total_students}</b> учеников",
        f"• норм 3+ закрыто: <b>{kulek['trainer_earned']}/{kulek['trainer_total']}</b>",
        "",
        "🐶 <b>Кулёчки</b>",
        f"• выдано за месяц: <b>{kdata['total_points']}</b>",
        f"• все объективные условия закрыли: "
        f"<b>{kdata['full_objective_count']}/{total_students}</b>",
        f"• в розыгрыше скидки 5% сейчас: "
        f"<b>{kdata['eligible_draw_count']}</b>",
    ])

    if kulek["student_month_winner"]:
        winner = kulek["student_month_winner"]
        lines.append(
            f"• 🏆 Ученик месяца: <b>{html.escape(winner['student_name'])}</b> "
            f"({float(winner['score']):g}/100)"
        )
    elif kulek["student_month_avg"] is not None:
        lines.append(
            f"• 🏆 средний индекс «Ученик месяца»: "
            f"<b>{kulek['student_month_avg']:g}/100</b>"
        )

    lines.extend([
        "",
        "💳 <b>Оплаты</b>",
        f"• подключено: <b>{payment['connected']}/{total_students}</b>",
        f"• помесячно: <b>{payment['monthly']}</b> · "
        f"раз в 3 месяца: <b>{payment['quarterly']}</b> · "
        f"курс оплачен: <b>{payment['prepaid']}</b>",
    ])
    if payment["review"]:
        lines.append(f"• ⚠️ график нужно уточнить: <b>{payment['review']}</b>")
    if payment["missing"]:
        lines.append(f"• без платёжной записи: <b>{payment['missing']}</b>")
    if payment["overdue_students"]:
        lines.append(
            f"• 🔴 просрочка: <b>{payment['overdue_students']}</b> учеников · "
            f"<b>{payment_schedule.money(payment['overdue_cents'])}</b>"
        )
    else:
        lines.append("• 🔴 просроченных оплат сейчас нет")

    lines.extend([
        "",
        f"⚠️ <b>Зона внимания: {len(attention)}</b>",
    ])
    if attention:
        for name, reasons in attention:
            lines.append(
                f"• {html.escape(name)} — {html.escape('; '.join(reasons))}"
            )
    else:
        lines.append("• сейчас никого")

    lines.extend([
        "",
        "Обновляется из фактических данных CoreApp, пробников, тренажёров, "
        "Кулёчков и оплат.",
    ])
    return "\n".join(lines)


def _stats_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="cab:generalstats")],
        [
            InlineKeyboardButton("🐶 Кулёчки", callback_data="cab:kulek"),
            InlineKeyboardButton("💳 Оплаты", callback_data="cab:payments"),
        ],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def install():
    global _INSTALLED, _previous_markup, _previous_callback
    if _INSTALLED:
        return
    _INSTALLED = True

    _previous_markup = live23.cabinet_markup
    _previous_callback = live23.cabinet_callback

    def cabinet_markup():
        base = _previous_markup()
        rows = [list(row) for row in base.inline_keyboard]
        rows = [
            [
                button for button in row
                if getattr(button, "callback_data", "") != "cab:generalstats"
            ]
            for row in rows
        ]
        rows = [row for row in rows if row]
        insert_at = 1 if rows else 0
        rows.insert(
            insert_at,
            [InlineKeyboardButton(
                "📊 Общая статистика",
                callback_data="cab:generalstats",
            )],
        )
        return InlineKeyboardMarkup(rows)

    async def cabinet_callback(update, context):
        query = update.callback_query
        data = str(query.data or "") if query else ""
        if data != "cab:generalstats":
            return await _previous_callback(update, context)
        if not live23._admin_private(update):
            await query.answer("Только для преподавателя")
            return
        await query.answer("Обновляю статистику")
        text = general_stats_text()
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=_stats_markup(),
        )

    live23.cabinet_markup = cabinet_markup
    live23.cabinet_callback = cabinet_callback

    # Production audit without logging student names or other personal data.
    try:
        students = _students()
        hw = _homework_summary(students)
        now = datetime.now(bot.TIMEZONE)
        attendance = _attendance_summary(students, now.year, now.month)
        k = _kulek_summary(students, now.year, now.month)
        print(
            "EGE general stats ready: "
            f"students={len(students)} linked={sum(1 for s in students if s[5] is not None)} "
            f"hw_unfinished={hw['unfinished']} hw_overdue={hw['overdue']} "
            f"attendance_lessons={attendance['lessons']} "
            f"probnik_results={k['probnik_results']} trainer_sessions={k['trainer_sessions']}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"EGE general stats audit failed: {type(exc).__name__}: {exc}",
            flush=True,
        )
