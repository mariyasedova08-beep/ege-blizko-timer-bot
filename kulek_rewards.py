"""Monthly Kulyochki motivation system for EGE BLIZKO.

Rules:
- +1 for each ordinary homework submitted on time.
- +1 for each active final homework with result >=80%.
- +1 per available trainer after >=3 completed sessions in the month.
- +1 for each probnik result strictly above 60.
- +1 manual award for each teacher-marked practical lesson.

Discount draw eligibility excludes subjective practical awards and is limited to
monthly-payment students who completed every objective monthly condition.
Breakthrough candidates are based on improvement relative to self, not absolute rank.
"""
import calendar
import html
import json
import re
import secrets
import sqlite3
from datetime import date, datetime, time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

import run_bot_live90 as live90
import run_bot_live49 as student_cabinet
import homework_deadline_logic as deadlines
import payment_schedule
import payment_name_aliases
import ege_admin_webapp as admin_app

bot = live90.bot
live79 = live90.live79
live34 = live79.live34
live56 = live79.live56

BUTTON = "🐶 Кулёчки"
_INSTALLED = False
_CACHE = {}
_RANKING_CACHE = {"at": 0.0, "key": "", "data": None}

TRAINER_TABLES = {
    "trivial": "trivial_sessions",
    "acid": "acid_sessions",
    "metals": "metals_sessions",
    "oxides": "oxides_sessions",
    "oxideprops": "oxide_properties_sessions",
    "nonmetals": "nonmetals_sessions",
}
MONTH_NAMES = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kulek_practical_lessons (
                month_key TEXT NOT NULL,
                lesson_number INTEGER NOT NULL,
                lesson_date TEXT NOT NULL,
                marked_at TEXT NOT NULL,
                PRIMARY KEY(month_key, lesson_number)
            );

            CREATE TABLE IF NOT EXISTS kulek_practical_awards (
                month_key TEXT NOT NULL,
                lesson_number INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                awarded_at TEXT NOT NULL,
                PRIMARY KEY(month_key, lesson_number, student_id)
            );

            CREATE TABLE IF NOT EXISTS kulek_monthly_draws (
                month_key TEXT PRIMARY KEY,
                winner_student_id INTEGER NOT NULL,
                winner_name TEXT NOT NULL,
                discount_percent INTEGER NOT NULL DEFAULT 5,
                eligible_json TEXT NOT NULL,
                drawn_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kulek_breakthrough_winners (
                month_key TEXT PRIMARY KEY,
                student_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                chosen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kulek_student_month_winners (
                month_key TEXT PRIMARY KEY,
                student_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                score REAL NOT NULL,
                components_json TEXT NOT NULL,
                tied_json TEXT NOT NULL,
                chosen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kulek_discount_draw_pool (
                month_key TEXT NOT NULL,
                participant_number INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                frozen_at TEXT NOT NULL,
                PRIMARY KEY(month_key, student_id),
                UNIQUE(month_key, participant_number)
            );

            CREATE TABLE IF NOT EXISTS kulek_monthly_deliveries (
                month_key TEXT NOT NULL,
                recipient_kind TEXT NOT NULL,
                recipient_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(month_key, recipient_kind, recipient_id)
            );
            """
        )
        conn.commit()


def _month_key(value=None):
    if value is None:
        now = datetime.now(bot.TIMEZONE)
        return f"{now.year:04d}-{now.month:02d}"
    text = str(value)
    if not re.fullmatch(r"\d{4}-\d{2}", text):
        raise ValueError("bad month")
    return text


def _month_bounds(month_key):
    year, month = map(int, month_key.split("-"))
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def month_label(month_key):
    year, month = map(int, month_key.split("-"))
    return f"{MONTH_NAMES[month]} {year}"


def previous_month_key(month_key):
    first, _last = _month_bounds(month_key)
    prev = first - timedelta(days=1)
    return f"{prev.year:04d}-{prev.month:02d}"


SEPTEMBER_DISCOUNT_KEY = "2026-09"
SEPTEMBER_DISCOUNT_CUTOFF = datetime(
    2026, 10, 5, 21, 0, tzinfo=bot.TIMEZONE
)
SEPTEMBER_DISCOUNT_VISIBLE_FROM = date(2026, 10, 1)
SEPTEMBER_DISCOUNT_VISIBLE_UNTIL = date(2026, 10, 7)


def _discount_cutoff(month_key):
    key = _month_key(month_key)
    return SEPTEMBER_DISCOUNT_CUTOFF if key == SEPTEMBER_DISCOUNT_KEY else None


def _discount_late_homework(student, month_key):
    """September homework sourced in September but naturally due in October.

    Earlier September homework keeps its original on-time requirement. Only these
    cross-month assignments receive the special grace window through 05.10 21:00.
    """
    key = _month_key(month_key)
    cutoff = _discount_cutoff(key)
    if not cutoff:
        return []

    first, last = _month_bounds(key)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        submissions = conn.execute(
            """
            SELECT received_at,user_id,lower(user_email),lesson_id,lesson_name
            FROM homework_submissions
            ORDER BY received_at
            """
        ).fetchall()

    items = []
    for source_no, source_date in enumerate(tuple(deadlines._course_dates()), 1):
        if not (first <= source_date <= last):
            continue
        due = deadlines.due_lesson_for_source(source_date)
        if not due:
            continue
        due_date, due_no = due
        if due_date <= last:
            continue

        matching = [
            row for row in submissions
            if deadlines._explicit_match(
                row[3], row[4], due_no, source_no, source_date
            )
            and _student_matches_submission(student, row[1], row[2])
        ]
        submitted = False
        submitted_at = None
        for row in matching:
            dt = _parse_dt(row[0])
            if dt and dt <= cutoff and (submitted_at is None or dt < submitted_at):
                submitted_at = dt
                submitted = True
        items.append({
            "lesson": int(source_no),
            "source_date": source_date.isoformat(),
            "due_date": due_date.isoformat(),
            "done": submitted,
            "submitted_at": submitted_at.isoformat() if submitted_at else "",
        })
    return items


def _discount_trainer_progress(student, month_key):
    """Trainer progress for a month-close discount grace window.

    For September 2026, keep the September trainer set alive through
    05.10 21:00 and count completed sessions from 01.09 up to that cutoff.
    Match historical sessions by current Telegram ID and, when available,
    by stored Telegram username/name so relinks do not erase September credit.
    """
    key = _month_key(month_key)
    row = student_month(int(student[0]), key)
    if not row:
        return {"earned": 0, "total": 0, "items": []}

    base_items = ((row.get("categories") or {}).get("trainers") or {}).get("items") or []
    if key != SEPTEMBER_DISCOUNT_KEY:
        return {
            "earned": sum(1 for x in base_items if x.get("earned")),
            "total": len(base_items),
            "items": list(base_items),
        }

    sid = int(student[0])
    telegram_id = student[5]
    cutoff = _discount_cutoff(key)
    start_dt = datetime(2026, 9, 1, 0, 0, tzinfo=bot.TIMEZONE)
    items = []

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        identity = conn.execute(
            """
            SELECT telegram_username,user_name,display_name
            FROM students
            WHERE id=?
            """,
            (sid,),
        ).fetchone()
        tg_username = str((identity or [None])[0] or "").strip().lstrip("@").casefold()
        user_name = str((identity or [None, None])[1] or "").strip().casefold()
        display_name = str((identity or [None, None, None])[2] or "").strip().casefold()
        name_candidates = {x for x in (user_name, display_name) if x}

        table_names = {
            str(x[0])
            for x in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for item in base_items:
            code = str(item.get("code") or "")
            table = TRAINER_TABLES.get(code, f"{code}_sessions")
            sessions = int(item.get("sessions") or 0)
            if (
                cutoff is not None
                and table in table_names
                and re.fullmatch(r"[A-Za-z0-9_]+", table)
            ):
                try:
                    columns = {
                        str(x[1])
                        for x in conn.execute(f"PRAGMA table_info({table})").fetchall()
                    }
                    identity_clauses = []
                    params = []
                    if telegram_id is not None and "telegram_user_id" in columns:
                        identity_clauses.append("telegram_user_id=?")
                        params.append(int(telegram_id))
                    if tg_username and "telegram_username" in columns:
                        identity_clauses.append(
                            "lower(ltrim(coalesce(telegram_username,''),'@'))=?"
                        )
                        params.append(tg_username)
                    if name_candidates and "telegram_name" in columns:
                        placeholders = ",".join("?" for _ in name_candidates)
                        identity_clauses.append(
                            f"lower(trim(coalesce(telegram_name,''))) IN ({placeholders})"
                        )
                        params.extend(sorted(name_candidates))

                    if identity_clauses:
                        sessions = int(
                            conn.execute(
                                f"""
                                SELECT COUNT(*)
                                FROM {table}
                                WHERE ({' OR '.join(identity_clauses)})
                                  AND finished_at IS NOT NULL
                                  AND finished_at>=?
                                  AND finished_at<=?
                                """,
                                (*params, start_dt.isoformat(), cutoff.isoformat()),
                            ).fetchone()[0]
                            or 0
                        )
                except sqlite3.OperationalError:
                    sessions = int(item.get("sessions") or 0)

            copied = dict(item)
            copied["sessions"] = sessions
            copied["earned"] = sessions >= 3
            copied["remaining"] = max(0, 3 - sessions)
            items.append(copied)

    return {
        "earned": sum(1 for x in items if x.get("earned")),
        "total": len(items),
        "items": items,
    }

def discount_status(student_id, month_key=SEPTEMBER_DISCOUNT_KEY):
    key = _month_key(month_key)
    student = next(
        (row for row in _student_rows() if int(row[0]) == int(student_id)),
        None,
    )
    if not student:
        return None
    row = student_month(int(student_id), key)
    if not row:
        return None

    categories = row["categories"]
    late_hw = _discount_late_homework(student, key)

    hw_fixed_earned = int(categories["homework"]["earned"])
    hw_fixed_total = int(categories["homework"]["total"])
    late_earned = sum(1 for x in late_hw if x["done"])
    late_total = len(late_hw)

    final_earned = int(categories["final"]["earned"])
    final_total = int(categories["final"]["total"])
    discount_trainers = _discount_trainer_progress(student, key)
    trainer_earned = int(discount_trainers["earned"])
    trainer_total = int(discount_trainers["total"])
    probnik_earned = int(categories["probnik"]["earned"])
    probnik_total = int(categories["probnik"]["total"])

    conditions = [
        {
            "code": "homework",
            "label": "ДЗ с сентябрьским сроком — вовремя",
            "earned": hw_fixed_earned,
            "total": hw_fixed_total,
            "done": hw_fixed_earned == hw_fixed_total,
            "missing": [
                f"ДЗ после урока №{x['lesson']} не было сдано вовремя"
                for x in categories["homework"].get("items") or []
                if not x.get("on_time")
            ],
        },
        {
            "code": "late_homework",
            "label": "Последние сентябрьские ДЗ — до 5 октября",
            "earned": late_earned,
            "total": late_total,
            "done": late_earned == late_total,
            "missing": [
                f"ДЗ после урока №{x['lesson']} — закрыть до 5 октября"
                for x in late_hw if not x["done"]
            ],
        },
        {
            "code": "final",
            "label": "Итоговые ДЗ 80%+",
            "earned": final_earned,
            "total": final_total,
            "done": final_earned == final_total,
            "missing": list(
                x for x in row.get("remaining") or []
                if str(x).startswith("Итоговая")
            ),
        },
        {
            "code": "trainers",
            "label": "Тренажёры: норма 3+",
            "earned": trainer_earned,
            "total": trainer_total,
            "done": trainer_earned == trainer_total,
            "missing": [
                f"{x['title']}: ещё {x['remaining']} попыт."
                for x in discount_trainers.get("items") or []
                if not x.get("earned")
            ],
        },
        {
            "code": "probnik",
            "label": "Сентябрьские пробники 61+",
            "earned": probnik_earned,
            "total": probnik_total,
            "done": probnik_earned == probnik_total,
            "missing": [
                (
                    f"{x['event']}: нет результата → нужно 61+"
                    if x.get("score") is None
                    else f"{x['event']}: {x['score']:g} → нужно 61+"
                )
                for x in categories["probnik"].get("items") or []
                if not x.get("earned")
            ],
        },
    ]

    monthly_payment = bool(row.get("monthly_payment"))
    all_done = all(item["done"] for item in conditions)
    cutoff = _discount_cutoff(key)
    now = datetime.now(bot.TIMEZONE)
    data = month_payload(key, with_breakthrough=False)
    draw = data.get("draw")
    winner = bool(draw and int(draw["student_id"]) == int(student_id))

    return {
        "month": key,
        "label": month_label(key),
        "monthly_payment": monthly_payment,
        "eligible": bool(monthly_payment and all_done),
        "remaining_count": sum(1 for item in conditions if not item["done"]),
        "conditions": conditions,
        "cutoff": cutoff.isoformat() if cutoff else "",
        "cutoff_label": "5 октября · 21:00",
        "draw_done": bool(draw),
        "winner": winner,
        "discount_percent": 5,
        "payment_due_label": "7 октября",
        "window_open": bool(cutoff and now < cutoff),
    }


def active_discount_status(student_id):
    today = datetime.now(bot.TIMEZONE).date()
    if SEPTEMBER_DISCOUNT_VISIBLE_FROM <= today <= SEPTEMBER_DISCOUNT_VISIBLE_UNTIL:
        return discount_status(student_id, SEPTEMBER_DISCOUNT_KEY)
    return None


def discount_notice_text(student_id, month_key=SEPTEMBER_DISCOUNT_KEY):
    status = discount_status(student_id, month_key)
    if not status:
        return ""
    if not status["monthly_payment"]:
        return ""

    lines = [
        "🎁 <b>Розыгрыш скидки 5% — 5 октября</b>",
        "",
        "Оплата за октябрь — до 7 октября, поэтому сначала даём время закрыть "
        "две последние сентябрьские домашки, которые переходят на октябрь.",
        "",
        "<b>Чтобы участвовать в розыгрыше:</b>",
    ]
    for item in status["conditions"]:
        icon = "✅" if item["done"] else "🟡"
        if item["total"]:
            lines.append(
                f"{icon} {html.escape(item['label'])}: "
                f"<b>{item['earned']}/{item['total']}</b>"
            )
        else:
            lines.append(f"{icon} {html.escape(item['label'])}: <b>не было в сентябре</b>")

    if status["remaining_count"]:
        lines.extend([
            "",
            f"До допуска осталось условий: <b>{status['remaining_count']}</b>",
        ])
        missing = []
        for item in status["conditions"]:
            missing.extend(item["missing"])
        for item in missing[:8]:
            lines.append(f"• {html.escape(item)}")
    else:
        lines.extend([
            "",
            "✅ <b>Все условия уже выполнены — ты в списке участников.</b>",
        ])

    lines.extend([
        "",
        "⏰ Дедлайн: <b>5 октября, 21:00</b>.",
        "После дедлайна бот зафиксирует список и случайно выберет одного победителя.",
        "",
        "Твой прогресс будет виден в личном кабинете 💗",
    ])
    return "\n".join(lines)


def course_discount_notice_text(month_key=SEPTEMBER_DISCOUNT_KEY):
    return (
        "🎁 <b>РОЗЫГРЫШ СКИДКИ 5% — 5 ОКТЯБРЯ</b>\n\n"
        "Оплата за октябрь — до 7 октября, а две последние сентябрьские домашки "
        "уходят по срокам уже в октябрь. Поэтому список участников фиксируем "
        "<b>5 октября в 21:00</b>.\n\n"
        "Для участия нужно:\n"
        "✅ сентябрьские ДЗ с сентябрьским сроком — сдать вовремя;\n"
        "✅ две последние сентябрьские ДЗ — закрыть до 5 октября;\n"
        "✅ итоговые ДЗ — 80%+;\n"
        "✅ закрыть норму 3+ по каждому сентябрьскому тренажёру;\n"
        "✅ сентябрьские пробники — 61+.\n\n"
        "Розыгрыш — только среди ребят с помесячной оплатой. "
        "В личном кабинете у каждого будет видно, что уже выполнено и что осталось 💗"
    )


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=bot.TIMEZONE)
        else:
            dt = dt.astimezone(bot.TIMEZONE)
        return dt
    except Exception:
        return None


def _student_rows():
    return live34._student_rows()


def _student_identity(student):
    return str(student[4] or "").strip(), live79.live31._norm(student[3])


def _student_matches_submission(student, user_id, email):
    core_id, student_email = _student_identity(student)
    return bool(
        (core_id and str(user_id or "").strip() == core_id)
        or (
            student_email
            and live79.live31._norm(email)
            and live79.live31._norm(email) == student_email
        )
    )


def _payment_cadence_by_student(students):
    result = {int(row[0]): None for row in students}
    try:
        payment_rows = payment_schedule.schedule_rows()
    except Exception:
        return result
    by_key = {
        payment_name_aliases.stable_name_key(row["name"]): row["cadence"]
        for row in payment_rows
    }
    for student in students:
        sid = int(student[0])
        key = payment_name_aliases.stable_name_key(live34._shown_name(student))
        result[sid] = by_key.get(key)
    return result


def _homework_context(month_key, students):
    first, last = _month_bounds(month_key)
    now = datetime.now(bot.TIMEZONE)
    current_month = _month_key()
    as_of = min(last, now.date()) if month_key == current_month else last

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        submissions = conn.execute(
            """
            SELECT received_at,user_id,lower(user_email),lesson_id,lesson_name
            FROM homework_submissions
            ORDER BY received_at
            """
        ).fetchall()
        try:
            lesson_times = {
                int(number): str(event_time or "")
                for number, event_time in conn.execute(
                    """
                    SELECT lesson_number,event_time
                    FROM course_schedule
                    WHERE active=1 AND event_type='lesson' AND lesson_number IS NOT NULL
                    """
                ).fetchall()
            }
        except sqlite3.OperationalError:
            lesson_times = {}

    opportunities = []
    dates = tuple(deadlines._course_dates())
    for source_no, source_date in enumerate(dates, 1):
        due = deadlines.due_lesson_for_source(source_date)
        if not due:
            continue
        due_date, due_no = due
        if not (first <= due_date <= as_of):
            continue

        matching_rows = [
            row for row in submissions
            if deadlines._explicit_match(
                row[3], row[4], due_no, source_no, source_date
            )
        ]
        if not matching_rows:
            continue

        per_student = {}
        for student in students:
            sid = int(student[0])
            student_rows = [
                row for row in matching_rows
                if _student_matches_submission(student, row[1], row[2])
            ]
            earliest = None
            for row in student_rows:
                dt = _parse_dt(row[0])
                if dt and (earliest is None or dt < earliest):
                    earliest = dt
            due_clock = lesson_times.get(int(due_no), "")
            try:
                hh, mm = map(int, due_clock.split(":")[:2])
                deadline_dt = datetime.combine(
                    due_date, time(hh, mm), tzinfo=bot.TIMEZONE
                )
            except Exception:
                deadline_dt = datetime.combine(
                    due_date, time(23, 59, 59), tzinfo=bot.TIMEZONE
                )
            on_time = bool(earliest and earliest <= deadline_dt)
            per_student[sid] = {
                "done": bool(student_rows),
                "on_time": on_time,
                "submitted_at": earliest.isoformat() if earliest else "",
            }
        opportunities.append(
            {
                "lesson": int(source_no),
                "source_date": source_date.isoformat(),
                "due_date": due_date.isoformat(),
                "due_time": lesson_times.get(int(due_no), ""),
                "students": per_student,
            }
        )
    return opportunities


def _final_catalog():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        try:
            rows = conn.execute(
                """
                SELECT lesson_id,title
                FROM final_homework_catalog
                ORDER BY rowid
                """
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
    return [
        {"lesson_id": str(lesson_id), "title": str(title)}
        for lesson_id, title in rows
    ]


def _final_context(month_key, students):
    prefix = month_key
    catalog = _final_catalog()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        submissions = conn.execute(
            """
            SELECT received_at,user_id,lower(user_email),lesson_id,lesson_name,
                   correct_count,total_count
            FROM homework_submissions
            WHERE substr(received_at,1,7)=?
            ORDER BY received_at
            """,
            (prefix,),
        ).fetchall()

    works = []
    for index, item in enumerate(catalog, 1):
        lesson_id = item["lesson_id"]
        title_norm = re.sub(
            r"\s+", " ", item["title"].casefold().replace("ё", "е")
        ).strip()
        rows = []
        for row in submissions:
            sub_id = str(row[3] or "").strip()
            sub_norm = re.sub(
                r"\s+", " ", str(row[4] or "").casefold().replace("ё", "е")
            ).strip()
            if sub_id == lesson_id or (
                title_norm and sub_norm
                and (sub_norm == title_norm or title_norm in sub_norm or sub_norm in title_norm)
            ):
                rows.append(row)
        # A final work becomes a monthly condition when at least one submission
        # proves it was active that month. This avoids requiring future published work.
        if not rows:
            continue

        per_student = {}
        for student in students:
            sid = int(student[0])
            student_rows = [
                row for row in rows
                if _student_matches_submission(student, row[1], row[2])
            ]
            best_result = None
            for row in student_rows:
                try:
                    correct = float(str(row[5]).replace(",", "."))
                    total = float(str(row[6]).replace(",", "."))
                    if total > 0:
                        pct = round(100 * correct / total, 1)
                        best_result = pct if best_result is None else max(best_result, pct)
                except Exception:
                    continue
            per_student[sid] = {
                "submitted": bool(student_rows),
                "result_percent": best_result,
                "earned": bool(best_result is not None and best_result >= 80),
            }
        works.append(
            {
                "index": index,
                "lesson_id": lesson_id,
                "title": item["title"],
                "students": per_student,
            }
        )
    return works


def _trainer_goals(month_key, students):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        try:
            catalog = conn.execute(
                """
                SELECT code,title
                FROM weekly_trainer_catalog
                WHERE active=1
                ORDER BY sort_order,title
                """
            ).fetchall()
        except sqlite3.OperationalError:
            catalog = []

        table_names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        result = []
        for code, title in catalog:
            code = str(code)
            table = TRAINER_TABLES.get(code, f"{code}_sessions")
            if table not in table_names or not re.fullmatch(r"[A-Za-z0-9_]+", table):
                continue

            # Only count a trainer as a monthly condition from the month in
            # which it first actually had a completed session in production.
            first_finished = conn.execute(
                f"SELECT MIN(finished_at) FROM {table} WHERE finished_at IS NOT NULL"
            ).fetchone()[0]
            if not first_finished or str(first_finished)[:7] > month_key:
                continue

            per_student = {}
            for student in students:
                sid = int(student[0])
                telegram_id = student[5]
                sessions = 0
                if telegram_id is not None:
                    sessions = int(
                        conn.execute(
                            f"""
                            SELECT COUNT(*)
                            FROM {table}
                            WHERE telegram_user_id=?
                              AND finished_at IS NOT NULL
                              AND substr(finished_at,1,7)=?
                            """,
                            (int(telegram_id), month_key),
                        ).fetchone()[0]
                        or 0
                    )
                per_student[sid] = {
                    "sessions": sessions,
                    "earned": sessions >= 3,
                    "remaining": max(0, 3 - sessions),
                }
            result.append(
                {
                    "code": code,
                    "title": str(title),
                    "table": table,
                    "students": per_student,
                }
            )
    return result


def _probnik_context(month_key, students):
    year, month = map(int, month_key.split("-"))
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id,student_name,event_name,event_date,secondary_score
            FROM probnik_results
            WHERE secondary_score IS NOT NULL
            ORDER BY id
            """
        ).fetchall()

    filtered = []
    for row in rows:
        event_date = str(row[3] or "")
        parsed = None
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(event_date, fmt).date()
                break
            except Exception:
                continue
        if parsed and parsed.year == year and parsed.month == month:
            filtered.append(row)

    events = {}
    for row in filtered:
        key = (str(row[2] or "Пробник"), str(row[3] or ""))
        events.setdefault(key, []).append(row)

    result = []
    for (event_name, event_date), event_rows in events.items():
        per_student = {}
        for student in students:
            sid = int(student[0])
            scores = []
            for row in event_rows:
                matched = live56.unique_probnik_student_match(row[1], students)
                if matched and int(matched[0]) == sid:
                    try:
                        scores.append(float(row[4]))
                    except Exception:
                        pass
            score = max(scores) if scores else None
            per_student[sid] = {
                "score": score,
                "written": score is not None,
                "earned": bool(score is not None and score > 60),
            }
        result.append(
            {
                "event": event_name,
                "date": event_date,
                "students": per_student,
            }
        )
    return result


def _practical_context(month_key, students):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        lessons = conn.execute(
            """
            SELECT lesson_number,lesson_date
            FROM kulek_practical_lessons
            WHERE month_key=?
            ORDER BY lesson_date,lesson_number
            """,
            (month_key,),
        ).fetchall()
        awards = {
            (int(lesson), int(student_id))
            for lesson, student_id in conn.execute(
                """
                SELECT lesson_number,student_id
                FROM kulek_practical_awards
                WHERE month_key=?
                """,
                (month_key,),
            ).fetchall()
        }
    result = []
    for lesson_number, lesson_date in lessons:
        result.append(
            {
                "lesson": int(lesson_number),
                "date": str(lesson_date),
                "students": {
                    int(student[0]): {
                        "earned": (int(lesson_number), int(student[0])) in awards
                    }
                    for student in students
                },
            }
        )
    return result


def _objective_status(categories):
    required = (
        categories["homework"]["total"]
        + categories["final"]["total"]
        + categories["trainers"]["total"]
        + categories["probnik"]["total"]
    )
    earned = (
        categories["homework"]["earned"]
        + categories["final"]["earned"]
        + categories["trainers"]["earned"]
        + categories["probnik"]["earned"]
    )
    return required, earned, bool(required > 0 and earned == required)


def _build_month_payload(month_key):
    ensure_tables()
    students = _student_rows()
    homework = _homework_context(month_key, students)
    final_works = _final_context(month_key, students)
    trainers = _trainer_goals(month_key, students)
    probniki = _probnik_context(month_key, students)
    practical = _practical_context(month_key, students)
    cadences = _payment_cadence_by_student(students)

    student_cards = []
    for student in students:
        sid = int(student[0])
        name = live34._shown_name(student)

        hw_items = []
        for item in homework:
            state = item["students"][sid]
            hw_items.append(
                {
                    "lesson": item["lesson"],
                    "due_date": item["due_date"],
                    **state,
                }
            )
        final_items = []
        for item in final_works:
            final_items.append(
                {
                    "index": item["index"],
                    "title": item["title"],
                    **item["students"][sid],
                }
            )
        trainer_items = []
        for item in trainers:
            trainer_items.append(
                {
                    "code": item["code"],
                    "title": item["title"],
                    **item["students"][sid],
                }
            )
        probnik_items = []
        for item in probniki:
            probnik_items.append(
                {
                    "event": item["event"],
                    "date": item["date"],
                    **item["students"][sid],
                }
            )
        practical_items = []
        for item in practical:
            practical_items.append(
                {
                    "lesson": item["lesson"],
                    "date": item["date"],
                    **item["students"][sid],
                }
            )

        categories = {
            "homework": {
                "earned": sum(1 for x in hw_items if x["on_time"]),
                "total": len(hw_items),
                "items": hw_items,
            },
            "final": {
                "earned": sum(1 for x in final_items if x["earned"]),
                "total": len(final_items),
                "items": final_items,
            },
            "trainers": {
                "earned": sum(1 for x in trainer_items if x["earned"]),
                "total": len(trainer_items),
                "items": trainer_items,
            },
            "probnik": {
                "earned": sum(1 for x in probnik_items if x["earned"]),
                "total": len(probnik_items),
                "items": probnik_items,
            },
            "practice": {
                "earned": sum(1 for x in practical_items if x["earned"]),
                "total": len(practical_items),
                "items": practical_items,
            },
        }
        objective_total, objective_earned, objective_complete = _objective_status(categories)
        points = sum(cat["earned"] for cat in categories.values())
        possible = sum(cat["total"] for cat in categories.values())

        remaining = []
        for x in hw_items:
            if not x["on_time"]:
                remaining.append(f"ДЗ после урока №{x['lesson']} не закрыто вовремя")
        for x in final_items:
            if not x["earned"]:
                if x["result_percent"] is None:
                    remaining.append(f"Итоговая №{x['index']}: нужен результат 80%+")
                else:
                    remaining.append(f"Итоговая №{x['index']}: {x['result_percent']:g}% → нужно 80%+")
        for x in trainer_items:
            if not x["earned"]:
                remaining.append(
                    f"{x['title']}: ещё {x['remaining']} попыт."
                )
        for x in probnik_items:
            if not x["earned"]:
                score = "нет результата" if x["score"] is None else f"{x['score']:g} бал."
                remaining.append(f"{x['event']}: {score} → нужно 61+")

        cadence = cadences.get(sid)
        monthly_payment = cadence == "monthly"
        draw_eligible = bool(objective_complete and monthly_payment)

        student_cards.append(
            {
                "id": sid,
                "name": name,
                "telegram_id": int(student[5]) if student[5] is not None else None,
                "points": points,
                "possible": possible,
                "percent": round(100 * points / possible) if possible else 0,
                "objective_earned": objective_earned,
                "objective_total": objective_total,
                "objective_complete": objective_complete,
                "cadence": cadence or "",
                "monthly_payment": monthly_payment,
                "draw_eligible": draw_eligible,
                "remaining": remaining,
                "categories": categories,
            }
        )

    student_cards.sort(key=lambda x: x["name"].casefold())

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        draw_row = conn.execute(
            """
            SELECT winner_student_id,winner_name,discount_percent,drawn_at
            FROM kulek_monthly_draws WHERE month_key=?
            """,
            (month_key,),
        ).fetchone()
        breakthrough_row = conn.execute(
            """
            SELECT student_id,student_name,chosen_at
            FROM kulek_breakthrough_winners WHERE month_key=?
            """,
            (month_key,),
        ).fetchone()
        student_month_row = conn.execute(
            """
            SELECT student_id,student_name,score,components_json,tied_json,chosen_at
            FROM kulek_student_month_winners WHERE month_key=?
            """,
            (month_key,),
        ).fetchone()

    return {
        "month": month_key,
        "label": month_label(month_key),
        "previous_month": previous_month_key(month_key),
        "current_month": _month_key(),
        "students": student_cards,
        "student_count": len(student_cards),
        "total_points": sum(x["points"] for x in student_cards),
        "possible_points": sum(x["possible"] for x in student_cards),
        "full_objective_count": sum(1 for x in student_cards if x["objective_complete"]),
        "eligible_draw_count": sum(1 for x in student_cards if x["draw_eligible"]),
        "homework_opportunities": len(homework),
        "final_opportunities": len(final_works),
        "trainer_opportunities": len(trainers),
        "probnik_opportunities": len(probniki),
        "practice_opportunities": len(practical),
        "published_final_count": len(_final_catalog()),
        "draw": (
            {
                "student_id": int(draw_row[0]),
                "winner_name": str(draw_row[1]),
                "discount_percent": int(draw_row[2]),
                "drawn_at": str(draw_row[3]),
            }
            if draw_row else None
        ),
        "breakthrough_winner": (
            {
                "student_id": int(breakthrough_row[0]),
                "student_name": str(breakthrough_row[1]),
                "chosen_at": str(breakthrough_row[2]),
            }
            if breakthrough_row else None
        ),
        "student_of_month_winner": (
            {
                "student_id": int(student_month_row[0]),
                "student_name": str(student_month_row[1]),
                "score": float(student_month_row[2]),
                "components": json.loads(student_month_row[3] or "{}"),
                "tied": json.loads(student_month_row[4] or "[]"),
                "chosen_at": str(student_month_row[5]),
            }
            if student_month_row else None
        ),
    }


def month_payload(month_key=None, force=False, with_breakthrough=True):
    key = _month_key(month_key)
    now = datetime.now(bot.TIMEZONE)
    cached = _CACHE.get(key)
    if not force and cached and (now.timestamp() - cached["at"]) < 20:
        data = cached["data"]
    else:
        data = _build_month_payload(key)
        _CACHE[key] = {"at": now.timestamp(), "data": data}
    # Return a detached structure because callers enrich it.
    result = json.loads(json.dumps(data, ensure_ascii=False))
    if with_breakthrough:
        result["breakthrough_candidates"] = breakthrough_candidates(key)
    return result


def student_month(student_id, month_key=None):
    sid = int(student_id)
    data = month_payload(month_key)
    return next((x for x in data["students"] if int(x["id"]) == sid), None)


def _months_from_course_start(until_key):
    first = date(2026, 9, 1)
    year, month = map(int, until_key.split("-"))
    end = date(year, month, 1)
    result = []
    cur = first
    while cur <= end:
        result.append(f"{cur.year:04d}-{cur.month:02d}")
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)
    return result


def student_year_total(student_id, until_key=None):
    key = _month_key(until_key)
    total = 0
    history = []
    for month in _months_from_course_start(key):
        row = student_month(student_id, month)
        if not row:
            continue
        total += int(row["points"])
        history.append({"month": month, "points": int(row["points"]), "possible": int(row["possible"])})
    return total, history


def student_progress_snapshot(student_id, month_key=None):
    """Compact, student-facing progress snapshot for cabinet and weekly DM."""
    sid = int(student_id)
    key = _month_key(month_key)
    row = student_month(sid, key)
    if not row:
        return None

    cats = row.get("categories") or {}
    homework = cats.get("homework") or {}
    trainers = cats.get("trainers") or {}

    # Mock-exam progress always compares the entrance diagnostic
    # (the first available mock score from the course start) with the latest
    # available mock score up to the selected month.
    all_probnik_scores = []
    for month in _months_from_course_start(key):
        month_row = student_month(sid, month)
        if not month_row:
            continue
        probnik_cat = (month_row.get("categories") or {}).get("probnik") or {}
        for item in (probnik_cat.get("items") or []):
            if item.get("score") is not None:
                all_probnik_scores.append(float(item["score"]))

    probnik_previous = all_probnik_scores[0] if all_probnik_scores else None
    probnik_latest = all_probnik_scores[-1] if all_probnik_scores else None

    hw_earned = int(homework.get("earned") or 0)
    hw_total = int(homework.get("total") or 0)
    hw_percent = round(100 * hw_earned / hw_total) if hw_total else None

    trainer_sessions = sum(
        int(item.get("sessions") or 0)
        for item in (trainers.get("items") or [])
    )

    topics_closed = 0
    topics_total = 0
    final_scores = []
    for month in _months_from_course_start(key):
        month_row = student_month(sid, month)
        if not month_row:
            continue
        final_cat = (month_row.get("categories") or {}).get("final") or {}
        topics_closed += int(final_cat.get("earned") or 0)
        topics_total += int(final_cat.get("total") or 0)
        for item in (final_cat.get("items") or []):
            value = item.get("result_percent")
            if value is not None:
                final_scores.append(float(value))

    final_previous = final_scores[-2] if len(final_scores) >= 2 else None
    final_latest = final_scores[-1] if final_scores else None

    return {
        "month": key,
        "month_label": month_label(key),
        "probnik_previous": round(probnik_previous, 1) if probnik_previous is not None else None,
        "probnik_latest": round(probnik_latest, 1) if probnik_latest is not None else None,
        "probnik_delta": (
            round(probnik_latest - probnik_previous, 1)
            if probnik_previous is not None and probnik_latest is not None
            else None
        ),
        "final_previous": round(final_previous, 1) if final_previous is not None else None,
        "final_latest": round(final_latest, 1) if final_latest is not None else None,
        "final_delta": (
            round(final_latest - final_previous, 1)
            if final_previous is not None and final_latest is not None
            else None
        ),
        "homework_on_time_earned": hw_earned,
        "homework_on_time_total": hw_total,
        "homework_on_time_percent": hw_percent,
        "trainer_sessions": trainer_sessions,
        "topics_closed": topics_closed,
        "topics_total": topics_total,
    }


def _fmt_progress_number(value):
    if value is None:
        return "—"
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _progress_pair_text(previous, latest, unit=""):
    if latest is None:
        return "пока нет результата"
    if previous is None:
        suffix = f" {unit}" if unit else ""
        return f"{_fmt_progress_number(latest)}{suffix}"
    delta = float(latest) - float(previous)
    sign = "+" if delta > 0 else ""
    suffix = f" {unit}" if unit else ""
    return (
        f"{_fmt_progress_number(previous)} → {_fmt_progress_number(latest)} "
        f"({sign}{_fmt_progress_number(delta)}){suffix}"
    )


def student_weekly_progress_text(student_id, month_key=None):
    progress = student_progress_snapshot(student_id, month_key)
    if not progress:
        return None

    probnik_line = _progress_pair_text(
        progress["probnik_previous"], progress["probnik_latest"]
    )
    final_line = _progress_pair_text(
        progress["final_previous"], progress["final_latest"], "%"
    )

    hw_percent = progress["homework_on_time_percent"]
    if hw_percent is None:
        homework_line = "пока нет ДЗ с дедлайном"
    else:
        homework_line = (
            f"{hw_percent}% "
            f"({progress['homework_on_time_earned']} из {progress['homework_on_time_total']})"
        )

    topics = str(progress["topics_closed"])
    if progress["topics_total"]:
        topics += f" из {progress['topics_total']}"

    return (
        f"📈 <b>Твой прогресс · {html.escape(progress['month_label'])}</b>\n\n"
        f"📝 Пробник: <b>{html.escape(probnik_line)}</b>\n"
        f"📚 Итоговые ДЗ: <b>{html.escape(final_line)}</b>\n"
        f"🏠 ДЗ вовремя: <b>{html.escape(homework_line)}</b>\n"
        f"🧪 Тренажёры: <b>{progress['trainer_sessions']} тренировок</b>\n"
        f"✅ Уже закрыто тем: <b>{html.escape(topics)}</b>\n\n"
        "Это не рейтинг с другими — это твой собственный прогресс 💗"
    )


COURSE_RANKING_WEIGHTS = {
    "homework": 20.0,
    "final": 15.0,
    "attendance": 15.0,
    "trainers": 15.0,
    "probnik": 25.0,
    "practice": 10.0,
}

COURSE_RANKING_LABELS = {
    "homework": "🏠 ДЗ вовремя",
    "final": "📚 Итоговые 80%+",
    "attendance": "🎓 Посещаемость",
    "trainers": "🧪 Тренажёры",
    "probnik": "📝 Пробники",
    "practice": "👩‍🏫 Работа на уроках",
}


def _public_student_name(name):
    parts = [x for x in str(name or "").strip().split() if x]
    if not parts:
        return "Ученик"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


def _percent_value(earned, total):
    if not total:
        return None
    return max(0.0, min(100.0, 100.0 * float(earned) / float(total)))


def course_ranking(until_key=None, force=False):
    """Live course leaderboard from Sep 2026 through the selected/current month.

    Overall index uses every major course signal:
    ordinary HW on time 20%, final HW >=80% 15%, attendance 15%,
    trainer norms 15%, mock exams 25%, practical lesson awards 10%.
    Missing course-wide categories have their weight redistributed.
    """
    key = _month_key(until_key)
    now = datetime.now(bot.TIMEZONE)
    cached = _RANKING_CACHE.get("data")
    if (
        not force
        and cached is not None
        and _RANKING_CACHE.get("key") == key
        and now.timestamp() - float(_RANKING_CACHE.get("at") or 0) < 20
    ):
        return json.loads(json.dumps(cached, ensure_ascii=False))

    months = _months_from_course_start(key)
    month_data = {
        month: month_payload(month, with_breakthrough=False)
        for month in months
    }
    students = _student_rows()

    aggregates = {}
    for student in students:
        sid = int(student[0])
        aggregates[sid] = {
            "student_id": sid,
            "name": live34._shown_name(student),
            "public_name": _public_student_name(live34._shown_name(student)),
            "homework_earned": 0,
            "homework_total": 0,
            "final_earned": 0,
            "final_total": 0,
            "trainer_earned": 0,
            "trainer_total": 0,
            "practice_earned": 0,
            "practice_total": 0,
            "attendance_earned": 0,
            "attendance_total": 0,
            "probnik_scores": [],
            "probnik_written": 0,
            "probnik_total": 0,
        }

    for month in months:
        data = month_data[month]
        by_id = {int(x["id"]): x for x in data["students"]}
        for sid, agg in aggregates.items():
            row = by_id.get(sid)
            if not row:
                continue
            cats = row["categories"]
            agg["homework_earned"] += int(cats["homework"]["earned"])
            agg["homework_total"] += int(cats["homework"]["total"])
            agg["final_earned"] += int(cats["final"]["earned"])
            agg["final_total"] += int(cats["final"]["total"])
            agg["trainer_earned"] += int(cats["trainers"]["earned"])
            agg["trainer_total"] += int(cats["trainers"]["total"])
            agg["practice_earned"] += int(cats["practice"]["earned"])
            agg["practice_total"] += int(cats["practice"]["total"])

            pitems = cats["probnik"].get("items") or []
            agg["probnik_total"] += int(cats["probnik"]["total"])
            for item in pitems:
                if item.get("score") is not None:
                    agg["probnik_scores"].append(float(item["score"]))
                    agg["probnik_written"] += 1

            present, total = _attendance_month(sid, month)
            agg["attendance_earned"] += int(present)
            agg["attendance_total"] += int(total)

    items = []
    for sid, agg in aggregates.items():
        components = {
            "homework": _percent_value(
                agg["homework_earned"], agg["homework_total"]
            ),
            "final": _percent_value(
                agg["final_earned"], agg["final_total"]
            ),
            "attendance": _percent_value(
                agg["attendance_earned"], agg["attendance_total"]
            ),
            "trainers": _percent_value(
                agg["trainer_earned"], agg["trainer_total"]
            ),
            "practice": _percent_value(
                agg["practice_earned"], agg["practice_total"]
            ),
        }

        scores = list(agg["probnik_scores"])
        probnik_value = None
        probnik_detail = {
            "written": agg["probnik_written"],
            "total": agg["probnik_total"],
            "average": None,
            "progress": None,
            "participation": _percent_value(
                agg["probnik_written"], agg["probnik_total"]
            ),
        }
        if agg["probnik_total"]:
            participation = probnik_detail["participation"] or 0.0
            if scores:
                average = sum(scores) / len(scores)
                probnik_detail["average"] = round(average, 1)
                if len(scores) >= 2:
                    delta = scores[-1] - scores[0]
                    progress = max(0.0, min(100.0, 50.0 + delta * 2.5))
                    probnik_detail["progress"] = round(delta, 1)
                    probnik_value = (
                        0.50 * average
                        + 0.30 * participation
                        + 0.20 * progress
                    )
                else:
                    probnik_value = 0.70 * average + 0.30 * participation
            else:
                probnik_value = 0.0
        components["probnik"] = (
            max(0.0, min(100.0, probnik_value))
            if probnik_value is not None
            else None
        )

        available = [
            code for code, value in components.items()
            if value is not None
        ]
        available_weight = sum(
            COURSE_RANKING_WEIGHTS[code] for code in available
        )
        score = 0.0
        component_payload = {}
        for code in COURSE_RANKING_WEIGHTS:
            value = components.get(code)
            effective_weight = (
                100.0 * COURSE_RANKING_WEIGHTS[code] / available_weight
                if value is not None and available_weight
                else 0.0
            )
            detail = {}
            if code == "homework":
                detail = {
                    "earned": agg["homework_earned"],
                    "total": agg["homework_total"],
                }
            elif code == "final":
                detail = {
                    "earned": agg["final_earned"],
                    "total": agg["final_total"],
                }
            elif code == "attendance":
                detail = {
                    "earned": agg["attendance_earned"],
                    "total": agg["attendance_total"],
                }
            elif code == "trainers":
                detail = {
                    "earned": agg["trainer_earned"],
                    "total": agg["trainer_total"],
                }
            elif code == "practice":
                detail = {
                    "earned": agg["practice_earned"],
                    "total": agg["practice_total"],
                }
            elif code == "probnik":
                detail = probnik_detail
            component_payload[code] = {
                "label": COURSE_RANKING_LABELS[code],
                "value": round(value, 1) if value is not None else None,
                "base_weight": COURSE_RANKING_WEIGHTS[code],
                "effective_weight": round(effective_weight, 1),
                "detail": detail,
            }
            if value is not None and available_weight:
                score += value * COURSE_RANKING_WEIGHTS[code] / available_weight

        items.append({
            "student_id": sid,
            "name": agg["name"],
            "public_name": agg["public_name"],
            "score": round(score, 1),
            "components": component_payload,
        })

    items.sort(
        key=lambda x: (
            -float(x["score"]),
            -(x["components"]["homework"]["value"] or -1),
            -(x["components"]["probnik"]["value"] or -1),
            x["name"].casefold(),
        )
    )
    for index, item in enumerate(items, 1):
        item["rank"] = index

    for code in COURSE_RANKING_WEIGHTS:
        ranked = sorted(
            [x for x in items if x["components"][code]["value"] is not None],
            key=lambda x: (
                -float(x["components"][code]["value"]),
                -float(x["score"]),
                x["name"].casefold(),
            ),
        )
        for index, item in enumerate(ranked, 1):
            item["components"][code]["rank"] = index
        for item in items:
            item["components"][code].setdefault("rank", None)

    payload = {
        "course_start": "2026-09",
        "through": key,
        "student_count": len(items),
        "weights": [
            {
                "code": code,
                "label": COURSE_RANKING_LABELS[code],
                "weight": weight,
            }
            for code, weight in COURSE_RANKING_WEIGHTS.items()
        ],
        "items": items,
        "leader": items[0] if items else None,
        "generated_at": now.isoformat(),
    }
    _RANKING_CACHE["at"] = now.timestamp()
    _RANKING_CACHE["key"] = key
    _RANKING_CACHE["data"] = payload
    return json.loads(json.dumps(payload, ensure_ascii=False))


def student_course_ranking(student_id, until_key=None):
    sid = int(student_id)
    data = course_ranking(until_key)
    own = next(
        (x for x in data["items"] if int(x["student_id"]) == sid),
        None,
    )
    return {
        "course_start": data["course_start"],
        "through": data["through"],
        "student_count": data["student_count"],
        "weights": data["weights"],
        "leader": (
            {
                "rank": data["leader"]["rank"],
                "public_name": data["leader"]["public_name"],
                "score": data["leader"]["score"],
            }
            if data.get("leader") else None
        ),
        "me": own,
        "items": [
            {
                "rank": x["rank"],
                "student_id": x["student_id"],
                "public_name": x["public_name"],
                "score": x["score"],
            }
            for x in data["items"]
        ],
        "generated_at": data["generated_at"],
    }


def _probnik_scores_for_student(student_id, month_key):
    data = student_month(student_id, month_key)
    if not data:
        return []
    scores = []
    for item in data["categories"]["probnik"]["items"]:
        if item["score"] is not None:
            scores.append(float(item["score"]))
    return scores


def _trainer_half_month_counts(student_id, month_key):
    """Completed trainer sessions in the first vs second half of one month."""
    student = next(
        (row for row in _student_rows() if int(row[0]) == int(student_id)),
        None,
    )
    if not student or student[5] is None:
        return 0, 0

    telegram_id = int(student[5])
    year, month = map(int, _month_key(month_key).split("-"))
    first_start = datetime(year, month, 1, 0, 0, tzinfo=bot.TIMEZONE)
    second_start = datetime(year, month, 16, 0, 0, tzinfo=bot.TIMEZONE)
    if month == 12:
        month_end = datetime(year + 1, 1, 1, 0, 0, tzinfo=bot.TIMEZONE)
    else:
        month_end = datetime(year, month + 1, 1, 0, 0, tzinfo=bot.TIMEZONE)

    first_count = 0
    second_count = 0
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in dict.fromkeys(TRAINER_TABLES.values()):
            if table not in tables or not re.fullmatch(r"[A-Za-z0-9_]+", table):
                continue
            try:
                first_count += int(
                    conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM {table}
                        WHERE telegram_user_id=?
                          AND finished_at IS NOT NULL
                          AND finished_at>=? AND finished_at<?
                        """,
                        (
                            telegram_id,
                            first_start.isoformat(),
                            second_start.isoformat(),
                        ),
                    ).fetchone()[0]
                    or 0
                )
                second_count += int(
                    conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM {table}
                        WHERE telegram_user_id=?
                          AND finished_at IS NOT NULL
                          AND finished_at>=? AND finished_at<?
                        """,
                        (
                            telegram_id,
                            second_start.isoformat(),
                            month_end.isoformat(),
                        ),
                    ).fetchone()[0]
                    or 0
                )
            except sqlite3.OperationalError:
                continue
    return first_count, second_count


def breakthrough_candidates(month_key=None):
    key = _month_key(month_key)
    current = month_payload(key, with_breakthrough=False)
    prev_key = previous_month_key(key)
    previous = month_payload(prev_key, with_breakthrough=False)
    prev_by_id = {int(x["id"]): x for x in previous["students"]}

    candidates = []
    for row in current["students"]:
        sid = int(row["id"])
        prev = prev_by_id.get(sid)
        components = []
        reasons = []

        current_scores = [
            float(x["score"]) for x in row["categories"]["probnik"]["items"]
            if x["score"] is not None
        ]
        prev_scores = []
        if prev:
            prev_scores = [
                float(x["score"]) for x in prev["categories"]["probnik"]["items"]
                if x["score"] is not None
            ]
        prob_delta = None
        if len(current_scores) >= 2:
            prob_delta = current_scores[-1] - current_scores[0]
        elif current_scores and prev_scores:
            prob_delta = current_scores[-1] - prev_scores[-1]
        if prob_delta is not None:
            score = max(0.0, min(100.0, prob_delta / 20.0 * 100.0))
            components.append((0.35, score))
            reasons.append(f"пробники: {prob_delta:+.0f} бал.")

        cur_hw = row["categories"]["homework"]
        prev_hw = prev["categories"]["homework"] if prev else None
        hw_delta = None
        if cur_hw["total"] and prev_hw and prev_hw["total"]:
            cur_pct = 100 * cur_hw["earned"] / cur_hw["total"]
            prev_pct = 100 * prev_hw["earned"] / prev_hw["total"]
            hw_delta = cur_pct - prev_pct
        elif cur_hw["total"] >= 2:
            items = cur_hw.get("items") or []
            mid = max(1, len(items) // 2)
            early = items[:mid]
            late = items[mid:]
            if early and late:
                early_pct = 100 * sum(1 for x in early if x.get("on_time")) / len(early)
                late_pct = 100 * sum(1 for x in late if x.get("on_time")) / len(late)
                hw_delta = late_pct - early_pct
        if hw_delta is not None:
            score = max(0.0, min(100.0, hw_delta / 40.0 * 100.0))
            components.append((0.30, score))
            reasons.append(f"ДЗ вовремя: {hw_delta:+.0f} п.п.")

        practice = row["categories"]["practice"]
        if practice["total"]:
            practice_pct = 100 * practice["earned"] / practice["total"]
            components.append((0.20, practice_pct))
            reasons.append(f"практика: {practice['earned']}/{practice['total']} Кулёчков")

        cur_sessions = sum(x["sessions"] for x in row["categories"]["trainers"]["items"])
        if key == "2026-09":
            # September is the first course month, so comparing against August=0
            # would reward mere presence. Compare equal 15-day halves instead.
            first_half_sessions, second_half_sessions = _trainer_half_month_counts(
                sid, key
            )
            if first_half_sessions or second_half_sessions:
                session_delta = second_half_sessions - first_half_sessions
                score = max(0.0, min(100.0, session_delta / 6.0 * 100.0))
                components.append((0.15, score))
                reasons.append(
                    "тренажёры: "
                    f"{first_half_sessions} → {second_half_sessions} "
                    f"({session_delta:+d})"
                )
        else:
            prev_sessions = (
                sum(x["sessions"] for x in prev["categories"]["trainers"]["items"])
                if prev else 0
            )
            if cur_sessions or prev_sessions:
                session_delta = cur_sessions - prev_sessions
                score = max(0.0, min(100.0, session_delta / 6.0 * 100.0))
                components.append((0.15, score))
                reasons.append(f"тренажёры: {session_delta:+d} попыт.")

        if not components:
            indicator = 0.0
        else:
            weight_sum = sum(weight for weight, _score in components)
            indicator = round(
                sum(weight * score for weight, score in components) / weight_sum,
                1,
            )

        candidates.append(
            {
                "student_id": sid,
                "name": row["name"],
                "indicator": indicator,
                "reasons": reasons,
                "points": row["points"],
                "possible": row["possible"],
            }
        )

    candidates.sort(key=lambda x: (-x["indicator"], x["name"].casefold()))
    return candidates[:3]


def student_of_month_candidates(month_key=None):
    """Objective monthly award: discipline + consistency, never absolute scores."""
    key = _month_key(month_key)
    current = month_payload(key, with_breakthrough=False)
    prev_key = previous_month_key(key)
    previous = month_payload(prev_key, with_breakthrough=False)
    prev_by_id = {int(x["id"]): x for x in previous["students"]}

    base_weights = {
        "homework": 30.0,
        "trainers": 25.0,
        "probnik": 25.0,
        "no_debts": 20.0,
    }
    result = []
    for row in current["students"]:
        sid = int(row["id"])
        prev = prev_by_id.get(sid)
        components = {}
        available = []

        hw = row["categories"]["homework"]
        if hw["total"]:
            value = 100.0 * hw["earned"] / hw["total"]
            components["homework"] = {
                "label": "ДЗ вовремя",
                "value": round(value, 1),
                "detail": f"{hw['earned']}/{hw['total']}",
                "weight": base_weights["homework"],
            }
            available.append("homework")

        trainers = row["categories"]["trainers"]
        if trainers["total"]:
            value = 100.0 * trainers["earned"] / trainers["total"]
            components["trainers"] = {
                "label": "Регулярность тренажёров",
                "value": round(value, 1),
                "detail": f"{trainers['earned']}/{trainers['total']} норм закрыто",
                "weight": base_weights["trainers"],
            }
            available.append("trainers")

        probnik = row["categories"]["probnik"]
        if probnik["total"]:
            written = sum(1 for x in probnik["items"] if x.get("written"))
            participation = 100.0 * written / probnik["total"]
            current_scores = [
                float(x["score"]) for x in probnik["items"]
                if x.get("score") is not None
            ]
            prev_scores = []
            if prev:
                prev_scores = [
                    float(x["score"]) for x in prev["categories"]["probnik"]["items"]
                    if x.get("score") is not None
                ]

            delta = None
            if len(current_scores) >= 2:
                delta = current_scores[-1] - current_scores[0]
            elif current_scores and prev_scores:
                delta = current_scores[-1] - prev_scores[-1]

            if delta is None:
                value = participation
                detail = f"участие {written}/{probnik['total']}; динамика пока не измеряется"
            else:
                # No absolute score comparison: 0 change = neutral 50/100,
                # +20 points = full progress score, -20 = 0.
                progress = max(0.0, min(100.0, 50.0 + delta * 2.5))
                value = (participation + progress) / 2.0
                detail = (
                    f"участие {written}/{probnik['total']}; "
                    f"динамика к себе {delta:+.0f} бал."
                )
            components["probnik"] = {
                "label": "Пробники: участие + прогресс",
                "value": round(value, 1),
                "detail": detail,
                "weight": base_weights["probnik"],
            }
            available.append("probnik")

        final = row["categories"]["final"]
        debt_opportunities = int(hw["total"]) + int(final["total"])
        if debt_opportunities:
            hw_clear = all(bool(x.get("done")) for x in hw.get("items") or [])
            final_clear = all(bool(x.get("submitted")) for x in final.get("items") or [])
            debt_free = bool(hw_clear and final_clear)
            components["no_debts"] = {
                "label": "Месяц без долгов",
                "value": 100.0 if debt_free else 0.0,
                "detail": "все обязательные работы закрыты" if debt_free else "есть незакрытые обязательные работы",
                "weight": base_weights["no_debts"],
            }
            available.append("no_debts")

        available_weight = sum(base_weights[name] for name in available)
        if available_weight:
            score = sum(
                components[name]["value"] * base_weights[name]
                for name in available
            ) / available_weight
        else:
            score = 0.0

        # Effective weights after proportional redistribution of unavailable criteria.
        if available_weight:
            for name in available:
                components[name]["effective_weight"] = round(
                    100.0 * base_weights[name] / available_weight, 1
                )

        result.append(
            {
                "student_id": sid,
                "name": row["name"],
                "score": round(score, 1),
                "components": components,
                "available_weight": round(available_weight, 1),
            }
        )

    result.sort(key=lambda x: (-x["score"], x["name"].casefold()))
    return result


def choose_student_of_month(month_key=None):
    """Freeze one objective winner after month close; ties are random."""
    key = _month_key(month_key)
    if key >= _month_key():
        return {"ok": False, "error": "month_not_closed"}

    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        existing = conn.execute(
            """
            SELECT student_id,student_name,score,components_json,tied_json,chosen_at
            FROM kulek_student_month_winners WHERE month_key=?
            """,
            (key,),
        ).fetchone()
    if existing:
        return {
            "ok": True,
            "existing": True,
            "student_id": int(existing[0]),
            "student_name": str(existing[1]),
            "score": float(existing[2]),
            "components": json.loads(existing[3] or "{}"),
            "tied": json.loads(existing[4] or "[]"),
            "chosen_at": str(existing[5]),
        }

    candidates = [x for x in student_of_month_candidates(key) if x["available_weight"] > 0]
    if not candidates:
        return {"ok": False, "error": "no_data"}

    top_score = candidates[0]["score"]
    tied = [x for x in candidates if x["score"] == top_score]
    winner = secrets.choice(tied)
    chosen_at = datetime.now(bot.TIMEZONE).isoformat()
    tied_payload = [
        {"student_id": int(x["student_id"]), "name": x["name"], "score": x["score"]}
        for x in tied
    ]

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO kulek_student_month_winners(
                month_key,student_id,student_name,score,components_json,tied_json,chosen_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                key,
                int(winner["student_id"]),
                str(winner["name"]),
                float(winner["score"]),
                json.dumps(winner["components"], ensure_ascii=False),
                json.dumps(tied_payload, ensure_ascii=False),
                chosen_at,
            ),
        )
        conn.commit()

    _CACHE.pop(key, None)
    return {
        "ok": True,
        "existing": False,
        "student_id": int(winner["student_id"]),
        "student_name": winner["name"],
        "score": winner["score"],
        "components": winner["components"],
        "tied": tied_payload,
        "chosen_at": chosen_at,
    }


def mark_practical_lesson(lesson_number):
    lesson_number = int(lesson_number)
    dates = tuple(deadlines._course_dates())
    if lesson_number < 1 or lesson_number > len(dates):
        raise ValueError("lesson not found")
    lesson_date = dates[lesson_number - 1]
    month_key = f"{lesson_date.year:04d}-{lesson_date.month:02d}"
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO kulek_practical_lessons(
                month_key,lesson_number,lesson_date,marked_at
            ) VALUES(?,?,?,?)
            """,
            (
                month_key,
                lesson_number,
                lesson_date.isoformat(),
                datetime.now(bot.TIMEZONE).isoformat(),
            ),
        )
        conn.commit()
    _CACHE.pop(month_key, None)
    return month_key, lesson_date


def toggle_practical_award(lesson_number, student_id):
    month_key, _lesson_date = mark_practical_lesson(lesson_number)
    sid = int(student_id)
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM kulek_practical_awards
            WHERE month_key=? AND lesson_number=? AND student_id=?
            """,
            (month_key, int(lesson_number), sid),
        ).fetchone()
        if row:
            conn.execute(
                """
                DELETE FROM kulek_practical_awards
                WHERE month_key=? AND lesson_number=? AND student_id=?
                """,
                (month_key, int(lesson_number), sid),
            )
            awarded = False
        else:
            conn.execute(
                """
                INSERT INTO kulek_practical_awards(
                    month_key,lesson_number,student_id,awarded_at
                ) VALUES(?,?,?,?)
                """,
                (
                    month_key,
                    int(lesson_number),
                    sid,
                    datetime.now(bot.TIMEZONE).isoformat(),
                ),
            )
            awarded = True
        conn.commit()
    _CACHE.pop(month_key, None)
    return awarded


def discount_draw_pool(month_key=SEPTEMBER_DISCOUNT_KEY):
    key = _month_key(month_key)
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT participant_number,student_id,student_name,frozen_at
            FROM kulek_discount_draw_pool
            WHERE month_key=?
            ORDER BY participant_number
            """,
            (key,),
        ).fetchall()
    return [
        {
            "number": int(number),
            "id": int(student_id),
            "name": str(name),
            "frozen_at": str(frozen_at),
        }
        for number, student_id, name, frozen_at in rows
    ]


def freeze_discount_pool(month_key=SEPTEMBER_DISCOUNT_KEY):
    key = _month_key(month_key)
    cutoff = _discount_cutoff(key)
    if cutoff and datetime.now(bot.TIMEZONE) < cutoff:
        return {
            "ok": False,
            "error": "draw_window_open",
            "cutoff": cutoff.isoformat(),
        }

    existing = discount_draw_pool(key)
    if existing:
        return {"ok": True, "existing": True, "participants": existing}

    data = month_payload(key, force=True, with_breakthrough=False)
    eligible = []
    for row in data["students"]:
        status = discount_status(int(row["id"]), key)
        if status and status["eligible"]:
            eligible.append({"id": int(row["id"]), "name": str(row["name"])})

    if not eligible:
        return {"ok": False, "error": "no_eligible"}

    # Numbers are deliberately neutral: alphabetical order only.
    eligible.sort(key=lambda x: x["name"].casefold())
    frozen_at = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for number, item in enumerate(eligible, 1):
            conn.execute(
                """
                INSERT INTO kulek_discount_draw_pool(
                    month_key,participant_number,student_id,student_name,frozen_at
                ) VALUES(?,?,?,?,?)
                """,
                (key, number, item["id"], item["name"], frozen_at),
            )
        conn.commit()

    participants = discount_draw_pool(key)
    return {"ok": True, "existing": False, "participants": participants}


def discount_pool_text(month_key=SEPTEMBER_DISCOUNT_KEY):
    key = _month_key(month_key)
    result = freeze_discount_pool(key)
    if not result.get("ok"):
        if result.get("error") == "draw_window_open":
            return "🎁 Список участников будет зафиксирован 5 октября в 21:00."
        return "🎁 После дедлайна нет участников, выполнивших все условия."
    participants = result["participants"]
    lines = [
        "🎟 <b>Участники розыгрыша скидки 5%</b>",
        "",
        "Список зафиксирован. Номерки присвоены по алфавиту и не влияют на шанс:",
        "",
    ]
    for item in participants:
        lines.append(
            f"<b>№{item['number']}</b> — {html.escape(item['name'])}"
        )
    lines.extend([
        "",
        f"Всего участников: <b>{len(participants)}</b>.",
        "🎲 Победитель будет выбран случайно из этого зафиксированного списка.",
    ])
    return "\n".join(lines)


def draw_discount(month_key=None):
    key = _month_key(month_key)
    current = _month_key()
    if key >= current:
        return {"ok": False, "error": "month_not_closed"}

    cutoff = _discount_cutoff(key)
    if cutoff and datetime.now(bot.TIMEZONE) < cutoff:
        return {
            "ok": False,
            "error": "draw_window_open",
            "cutoff": cutoff.isoformat(),
        }

    data = month_payload(key, force=True, with_breakthrough=False)
    existing = data.get("draw")
    if existing:
        pool = discount_draw_pool(key)
        winner_number = next(
            (x["number"] for x in pool if int(x["id"]) == int(existing["student_id"])),
            None,
        )
        return {
            "ok": True,
            "existing": True,
            **existing,
            "winner_number": winner_number,
            "eligible": pool,
            "eligible_count": len(pool),
        }

    frozen = freeze_discount_pool(key)
    if not frozen.get("ok"):
        return frozen
    pool = frozen["participants"]
    if not pool:
        return {"ok": False, "error": "no_eligible"}

    winner = secrets.choice(pool)
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO kulek_monthly_draws(
                month_key,winner_student_id,winner_name,discount_percent,
                eligible_json,drawn_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                key,
                int(winner["id"]),
                str(winner["name"]),
                5,
                json.dumps(pool, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()
    _CACHE.pop(key, None)
    return {
        "ok": True,
        "existing": False,
        "student_id": int(winner["id"]),
        "winner_name": winner["name"],
        "winner_number": int(winner["number"]),
        "discount_percent": 5,
        "eligible_count": len(pool),
        "eligible": pool,
    }


def choose_breakthrough(month_key, student_id):
    key = _month_key(month_key)
    sid = int(student_id)
    student = next((x for x in _student_rows() if int(x[0]) == sid), None)
    if not student:
        return {"ok": False, "error": "student_not_found"}
    name = live34._shown_name(student)
    now = datetime.now(bot.TIMEZONE).isoformat()
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO kulek_breakthrough_winners(
                month_key,student_id,student_name,chosen_at
            ) VALUES(?,?,?,?)
            ON CONFLICT(month_key) DO UPDATE SET
                student_id=excluded.student_id,
                student_name=excluded.student_name,
                chosen_at=excluded.chosen_at
            """,
            (key, sid, name, now),
        )
        conn.commit()
    _CACHE.pop(key, None)
    return {"ok": True, "student_id": sid, "student_name": name}


def student_text(student_id, month_key=None):
    key = _month_key(month_key)
    row = student_month(student_id, key)
    if not row:
        return "🐶 Кулёчки пока не найдены."
    total_year, _history = student_year_total(student_id, key)
    c = row["categories"]
    lines = [
        f"🐶 <b>Мои Кулёчки — {month_label(key)}</b>",
        "",
        f"Собрано: <b>{row['points']} из {row['possible']}</b> 🐶",
        f"За учебный год: <b>{total_year}</b> 🐶",
        "",
        f"🏠 ДЗ вовремя: <b>{c['homework']['earned']}/{c['homework']['total']}</b>",
        f"📚 Итоговые 80%+: <b>{c['final']['earned']}/{c['final']['total']}</b>",
        f"🧪 Тренажёры 3+ попытки: <b>{c['trainers']['earned']}/{c['trainers']['total']}</b>",
        f"📝 Пробники 61+: <b>{c['probnik']['earned']}/{c['probnik']['total']}</b>",
        f"👩‍🏫 Практика: <b>{c['practice']['earned']}/{c['practice']['total']}</b>",
    ]
    month_score = next(
        (
            item for item in student_of_month_candidates(key)
            if int(item["student_id"]) == int(student_id)
        ),
        None,
    )
    if month_score and month_score["available_weight"] > 0:
        lines.extend([
            "",
            f"🏆 Индекс «Ученик месяца»: <b>{month_score['score']:g}/100</b>",
            "Он считается только по твоей стабильности: ДЗ, тренажёры, "
            "пробники и отсутствие долгов. Общего рейтинга детей нет.",
        ])
    if row["objective_complete"]:
        lines.extend(["", "🌟 <b>Все объективные условия месяца выполнены!</b>"])
        if row["monthly_payment"]:
            if key == SEPTEMBER_DISCOUNT_KEY:
                status = discount_status(int(student_id), key)
                if status and status["eligible"]:
                    lines.append("🎁 Все условия для розыгрыша 5 октября выполнены.")
                else:
                    lines.append("🎁 Розыгрыш скидки — 5 октября. Прогресс смотри в личном кабинете.")
            else:
                lines.append("🎁 Ты проходишь в розыгрыш скидки 5% на следующий месяц.")
        else:
            lines.append("🐶 Отличный полный месяц. Розыгрыш скидки проводится только среди помесячной оплаты.")
    elif row["remaining"]:
        lines.extend(["", "До полного месяца осталось:"])
        for item in row["remaining"][:8]:
            lines.append(f"• {html.escape(item)}")

    data = month_payload(key, with_breakthrough=False)
    if data.get("draw") and int(data["draw"]["student_id"]) == int(student_id):
        lines.extend(["", "🎁 <b>Ты выиграл(а) скидку 5% на следующий месяц!</b>"])
    if data.get("breakthrough_winner") and int(data["breakthrough_winner"]["student_id"]) == int(student_id):
        lines.extend(["", "🚀 <b>Ты — «Прорыв месяца»!</b>"])
    if data.get("student_of_month_winner") and int(data["student_of_month_winner"]["student_id"]) == int(student_id):
        lines.extend([
            "",
            "🏆 <b>Ты — «Ученик месяца»!</b>",
            "Тебя ждёт отдельный подарок от Маши 💗",
        ])
    if _history:
        lines.extend(["", "📅 <b>История</b>"])
        for item in _history[-4:]:
            lines.append(
                f"• {month_label(item['month'])}: {item['points']}/{item['possible']} 🐶"
            )
    return "\n".join(lines)


def _attendance_month(student_id, month_key):
    first, last = _month_bounds(month_key)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        try:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN ar.status='present' THEN 1 ELSE 0 END),
                    COUNT(*)
                FROM attendance_records ar
                JOIN attendance_sessions s ON s.lesson_number=ar.lesson_number
                WHERE ar.student_id=?
                  AND s.finalized=1
                  AND s.lesson_date BETWEEN ? AND ?
                """,
                (int(student_id), first.isoformat(), last.isoformat()),
            ).fetchone()
        except sqlite3.OperationalError:
            row = (0, 0)
    return int((row or (0, 0))[0] or 0), int((row or (0, 0))[1] or 0)


def _probnik_month_stats(row):
    scores = [
        float(item["score"])
        for item in row["categories"]["probnik"]["items"]
        if item.get("score") is not None
    ]
    if not scores:
        return 0, None, None
    return len(scores), round(sum(scores) / len(scores), 1), round(max(scores), 1)


def _month_debt_free(row):
    hw = row["categories"]["homework"]
    final = row["categories"]["final"]
    hw_clear = all(bool(x.get("done")) for x in (hw.get("items") or []))
    final_clear = all(bool(x.get("submitted")) for x in (final.get("items") or []))
    return bool(hw_clear and final_clear)


def student_monthly_report_text(student_id, month_key=None):
    key = _month_key(month_key)
    row = student_month(student_id, key)
    if not row:
        return f"💗 <b>Итоги {month_label(key)}</b>\n\nПока недостаточно данных для отчёта."

    attendance_present, attendance_total = _attendance_month(student_id, key)
    probnik_count, probnik_avg, probnik_best = _probnik_month_stats(row)
    c = row["categories"]
    trainers = sum(int(x.get("sessions") or 0) for x in c["trainers"].get("items") or [])
    winner = month_payload(key, with_breakthrough=False).get("student_of_month_winner")
    is_winner = bool(winner and int(winner["student_id"]) == int(student_id))

    lines = [
        f"💗 <b>Твои итоги — {month_label(key)}</b>",
        "",
        f"🏠 ДЗ вовремя: <b>{c['homework']['earned']}/{c['homework']['total']}</b>",
        f"📚 Итоговые 80%+: <b>{c['final']['earned']}/{c['final']['total']}</b>",
        (
            f"🎓 Посещаемость: <b>{attendance_present}/{attendance_total}</b>"
            if attendance_total else
            "🎓 Посещаемость: пока нет сохранённых отметок"
        ),
        (
            f"📝 Пробники: <b>{probnik_count}</b> · средний <b>{probnik_avg:g}</b> · лучший <b>{probnik_best:g}</b>"
            if probnik_count else
            "📝 Пробники: в этом месяце нет результата"
        ),
        f"🧪 Тренажёры: <b>{trainers}</b> завершённых тренировок",
        f"🐶 Кулёчки: <b>{row['points']}/{row['possible']}</b>",
        f"✅ Долги к концу месяца: <b>{'нет' if _month_debt_free(row) else 'остались'}</b>",
    ]
    if is_winner:
        lines.extend([
            "",
            f"🏆 <b>Ты — Ученик месяца · {month_label(key)}!</b>",
            "Тебя ждёт отдельный подарок от Маши 💗",
        ])
    lines.extend([
        "",
        "В новом месяце не начинаем заново — продолжаем наращивать результат. ЕГЭ БЛИЗКО 💗",
    ])
    return "\n".join(lines)


def parent_monthly_report_text(student_id, month_key=None):
    key = _month_key(month_key)
    row = student_month(student_id, key)
    if not row:
        return f"💗 <b>Итоги {month_label(key)}</b>\n\nПока недостаточно данных для отчёта."

    attendance_present, attendance_total = _attendance_month(student_id, key)
    probnik_count, probnik_avg, probnik_best = _probnik_month_stats(row)
    c = row["categories"]
    trainers = sum(int(x.get("sessions") or 0) for x in c["trainers"].get("items") or [])
    winner = month_payload(key, with_breakthrough=False).get("student_of_month_winner")
    is_winner = bool(winner and int(winner["student_id"]) == int(student_id))

    strengths = []
    attention = []
    if c["homework"]["total"]:
        pct = 100 * c["homework"]["earned"] / c["homework"]["total"]
        (strengths if pct >= 80 else attention).append(
            f"домашние работы вовремя — {c['homework']['earned']}/{c['homework']['total']}"
        )
    if attendance_total:
        pct = 100 * attendance_present / attendance_total
        (strengths if pct >= 90 else attention).append(
            f"посещаемость — {attendance_present}/{attendance_total}"
        )
    if probnik_count:
        strengths.append(f"пробники — средний {probnik_avg:g}, лучший {probnik_best:g}")
    if trainers:
        strengths.append(f"тренажёры — {trainers} завершённых тренировок")
    if not _month_debt_free(row):
        attention.append("к концу месяца остались незакрытые обязательные работы")

    lines = [
        f"💗 <b>Итоги {month_label(key)} — {html.escape(row['name'])}</b>",
        "",
        f"🏠 ДЗ вовремя: <b>{c['homework']['earned']}/{c['homework']['total']}</b>",
        f"📚 Итоговые 80%+: <b>{c['final']['earned']}/{c['final']['total']}</b>",
        (
            f"🎓 Посещаемость: <b>{attendance_present}/{attendance_total}</b>"
            if attendance_total else
            "🎓 Посещаемость: сохранённых отметок пока нет"
        ),
        (
            f"📝 Пробники: <b>{probnik_count}</b> · средний <b>{probnik_avg:g}</b> · лучший <b>{probnik_best:g}</b>"
            if probnik_count else
            "📝 Пробники: в этом месяце результата нет"
        ),
        f"🧪 Тренажёры: <b>{trainers}</b>",
        f"🐶 Кулёчки: <b>{row['points']}/{row['possible']}</b>",
    ]
    if strengths:
        lines.extend(["", "🌟 <b>Что получилось хорошо</b>"])
        lines.extend(f"• {html.escape(x)}" for x in strengths[:4])
    if attention:
        lines.extend(["", "🎯 <b>На что обратить внимание в новом месяце</b>"])
        lines.extend(f"• {html.escape(x)}" for x in attention[:4])
    if is_winner:
        lines.extend([
            "",
            f"🏆 <b>{html.escape(row['name'])} — Ученик месяца · {month_label(key)}</b>",
            "Награда определяется по объективной системе стабильной работы.",
        ])
    lines.extend([
        "",
        "Я вижу эту динамику и учитываю её при дальнейшей подготовке.\nМария Александровна 💗",
    ])
    return "\n".join(lines)


def course_monthly_report_text(month_key=None):
    key = _month_key(month_key)
    data = month_payload(key, force=True, with_breakthrough=False)
    students = data["students"]
    att_present = att_total = hw_earned = hw_total = trainer_sessions = 0
    scores = []
    debt_free = 0

    for row in students:
        sid = int(row["id"])
        p, t = _attendance_month(sid, key)
        att_present += p
        att_total += t
        hw_earned += int(row["categories"]["homework"]["earned"])
        hw_total += int(row["categories"]["homework"]["total"])
        trainer_sessions += sum(
            int(x.get("sessions") or 0)
            for x in row["categories"]["trainers"].get("items") or []
        )
        scores.extend(
            float(x["score"])
            for x in row["categories"]["probnik"].get("items") or []
            if x.get("score") is not None
        )
        if _month_debt_free(row):
            debt_free += 1

    winner = data.get("student_of_month_winner")
    lines = [
        f"💗 <b>ЕГЭ БЛИЗКО — итоги {month_label(key)}</b>",
        "",
        f"👥 В системе: <b>{data['student_count']}</b> учеников",
        (
            f"🎓 Общая посещаемость: <b>{round(100 * att_present / att_total)}%</b> · {att_present}/{att_total}"
            if att_total else
            "🎓 Посещаемость: пока недостаточно сохранённых отметок"
        ),
        (
            f"🏠 ДЗ вовремя: <b>{round(100 * hw_earned / hw_total)}%</b> · {hw_earned}/{hw_total}"
            if hw_total else
            "🏠 ДЗ: пока недостаточно данных"
        ),
        f"🧪 Завершено тренировок: <b>{trainer_sessions}</b>",
        (
            f"📝 Средний результат пробников по всем написанным работам: <b>{round(sum(scores)/len(scores),1):g}</b>"
            if scores else
            "📝 Пробники: результатов за месяц пока нет"
        ),
        f"✅ Закончили месяц без обязательных долгов: <b>{debt_free}/{data['student_count']}</b>",
        f"🐶 Собрано Кулёчков: <b>{data['total_points']}</b>",
    ]
    if winner:
        lines.extend([
            "",
            f"🏆 <b>Ученик месяца — {html.escape(winner['student_name'])}</b>",
            "Награда — за стабильность: ДЗ, регулярную практику, пробники и отсутствие долгов.",
        ])
    next_line = (
        "Сентябрь был только стартом. В октябре продолжаем играть в долгую 💗"
        if key == "2026-09"
        else "Продолжаем играть в долгую — следующий месяц строим на результате этого 💗"
    )
    lines.extend([
        "",
        next_line,
        "<b>ЕГЭ БЛИЗКО</b>",
    ])
    return "\n".join(lines)


def _parent_links_for_month():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        try:
            return [
                (int(parent_id), int(student_id))
                for parent_id, student_id in conn.execute(
                    """
                    SELECT parent_telegram_user_id,student_id
                    FROM parent_links
                    WHERE active=1
                    ORDER BY parent_telegram_user_id,student_id
                    """
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            return []


def admin_text(month_key=None):
    key = _month_key(month_key)
    data = month_payload(key)
    lines = [
        f"🐶 <b>Кулёчки — {data['label']}</b>",
        "",
        f"Выдано: <b>{data['total_points']}</b> Кулёчков",
        f"Все объективные условия закрыли: <b>{data['full_objective_count']}/{data['student_count']}</b>",
        f"Допущены к скидке 5% (помесячно): <b>{data['eligible_draw_count']}</b>",
        "",
        "Условия месяца:",
        f"🏠 обычные ДЗ: {data['homework_opportunities']}",
        f"📚 активные итоговые: {data['final_opportunities']} "
        f"(в Core опубликовано {data['published_final_count']})",
        f"🧪 тренажёры: {data['trainer_opportunities']}",
        f"📝 пробники: {data['probnik_opportunities']}",
        f"👩‍🏫 практические уроки: {data['practice_opportunities']}",
        "",
        "👥 <b>По детям</b>",
    ]
    for row in data["students"]:
        draw = " · 🎁 допущен(а)" if row["draw_eligible"] else ""
        lines.append(
            f"• {html.escape(row['name'])}: <b>{row['points']}/{row['possible']} 🐶</b>{draw}"
        )

    candidates = data.get("breakthrough_candidates") or []
    if candidates:
        lines.extend(["", "🚀 <b>Кандидаты на «Прорыв месяца»</b>"])
        for item in candidates:
            why = "; ".join(item["reasons"][:3]) or "пока мало данных"
            lines.append(f"• {html.escape(item['name'])} — {html.escape(why)}")

    month_candidates = student_of_month_candidates(key)
    if month_candidates:
        lines.extend([
            "",
            "📊 <b>Топ-3 по индексу стабильности</b>",
            "<i>Это кандидаты для расчёта, а не три «Ученика месяца».</i>",
        ])
        for item in month_candidates[:3]:
            lines.append(
                f"• {html.escape(item['name'])} — <b>{item['score']:g}/100</b>"
            )

    if data.get("draw"):
        lines.extend([
            "",
            f"🎁 Скидка 5%: <b>{html.escape(data['draw']['winner_name'])}</b>",
        ])
    if data.get("breakthrough_winner"):
        lines.extend([
            f"🚀 Прорыв месяца: <b>{html.escape(data['breakthrough_winner']['student_name'])}</b>",
        ])
    if data.get("student_of_month_winner"):
        lines.extend([
            f"🏆 Ученик месяца: <b>{html.escape(data['student_of_month_winner']['student_name'])}</b> "
            f"({data['student_of_month_winner']['score']:g}/100)",
        ])
    return "\n".join(lines)


def _admin_markup(month_key=None):
    key = _month_key(month_key)
    rows = [
        [InlineKeyboardButton("➕ Выдать за прошлый урок", callback_data="cab:kulek:practice")],
        [InlineKeyboardButton("🚀 Прорыв месяца", callback_data=f"cab:kulek:breakthrough:{key}")],
        [InlineKeyboardButton("🏆 Ученик месяца", callback_data=f"cab:kulek:studentmonth:{key}")],
    ]
    if key < _month_key():
        rows.append([InlineKeyboardButton("🎲 Рандомайзер скидки 5%", callback_data=f"cab:kulek:draw:{key}")])
    else:
        rows.append([InlineKeyboardButton("🎁 Кто сейчас проходит в розыгрыш", callback_data=f"cab:kulek:eligible:{key}")])
    prev = previous_month_key(key)
    rows.append([
        InlineKeyboardButton("← месяц", callback_data=f"cab:kulek:month:{prev}"),
        InlineKeyboardButton("текущий", callback_data=f"cab:kulek:month:{_month_key()}"),
    ])
    return InlineKeyboardMarkup(rows)


def _attendance_snapshot(lesson_number):
    """Read saved attendance for one lesson without changing attendance state."""
    live79.live31.live30.live3.ensure_attendance_tables()
    students = _student_rows()
    active_ids = {int(student[0]) for student in students}

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        session = conn.execute(
            "SELECT finalized FROM attendance_sessions WHERE lesson_number=?",
            (int(lesson_number),),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT student_id,status
            FROM attendance_records
            WHERE lesson_number=?
            """,
            (int(lesson_number),),
        ).fetchall()

    records = {
        int(student_id): str(status)
        for student_id, status in rows
        if int(student_id) in active_ids
    }
    finalized = bool(session and session[0])
    present = sum(1 for status in records.values() if status == "present")
    absent = sum(1 for status in records.values() if status == "absent")
    total = len(active_ids)
    return {
        "finalized": finalized,
        "records": records,
        "present": present,
        "absent": absent,
        "total": total,
    }


def _attendance_lesson_suffix(lesson_number):
    attendance = _attendance_snapshot(lesson_number)
    if attendance["finalized"]:
        return f" · 👥 {attendance['present']}/{attendance['total']}"
    if attendance["records"]:
        return " · 📝 посещение не сохранено"
    return " · ⚪ нет посещения"


def _recent_lessons_markup():
    dates = tuple(deadlines._course_dates())
    today = datetime.now(bot.TIMEZONE).date()

    # Filter past lessons first, then take the most recent ones.
    past_lessons = [
        (lesson_no, lesson_date)
        for lesson_no, lesson_date in enumerate(dates, 1)
        if lesson_date <= today
    ]

    rows = []
    for lesson_no, lesson_date in past_lessons[-8:]:
        rows.append([
            InlineKeyboardButton(
                (
                    f"Урок №{lesson_no} · {lesson_date:%d.%m}"
                    f"{_attendance_lesson_suffix(lesson_no)}"
                ),
                callback_data=f"cab:kulek:practice:{lesson_no}",
            )
        ])
    rows.append([InlineKeyboardButton("← К Кулёчкам", callback_data="cab:kulek")])
    return InlineKeyboardMarkup(rows)


def _practice_lesson_text(lesson_number, lesson_date):
    attendance = _attendance_snapshot(lesson_number)
    if attendance["finalized"]:
        attendance_text = (
            f"👥 Посещение сохранено: "
            f"<b>{attendance['present']}/{attendance['total']}</b> были на уроке, "
            f"<b>{attendance['absent']}</b> отсутствовали."
        )
        legend = "✅ был(а) · ❌ отсутствовал(а)"
    elif attendance["records"]:
        attendance_text = (
            "📝 Посещаемость по этому уроку есть только в черновике и ещё не сохранена. "
            "До сохранения я не считаю её фактическим посещением."
        )
        legend = "❔ посещение ещё не подтверждено"
    else:
        attendance_text = "⚪ По этому уроку посещаемость ещё не сохранена."
        legend = "❔ посещение ещё не подтверждено"

    return (
        f"🐶 <b>Урок №{lesson_number} · {lesson_date:%d.%m}</b>\n\n"
        f"{attendance_text}\n\n"
        f"{legend}\n"
        "🐶 Кулёчек выдан · ○ не выдан\n\n"
        "Нажми на ребёнка — Кулёчек сразу сохранится. "
        "Повторное нажатие снимет награду."
    )


def _practice_students_markup(lesson_number):
    month_key, _lesson_date = mark_practical_lesson(lesson_number)
    attendance = _attendance_snapshot(lesson_number)

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        awarded = {
            int(row[0])
            for row in conn.execute(
                """
                SELECT student_id FROM kulek_practical_awards
                WHERE month_key=? AND lesson_number=?
                """,
                (month_key, int(lesson_number)),
            ).fetchall()
        }

    rows = []
    for student in _student_rows():
        sid = int(student[0])
        reward_icon = "🐶" if sid in awarded else "○"

        if attendance["finalized"]:
            status = attendance["records"].get(sid)
            if status == "present":
                attendance_icon = "✅"
            elif status == "absent":
                attendance_icon = "❌"
            else:
                attendance_icon = "❔"
        else:
            attendance_icon = "❔"

        rows.append([
            InlineKeyboardButton(
                f"{attendance_icon} {reward_icon} {live34._shown_name(student)}",
                callback_data=f"cab:kulek:p:{int(lesson_number)}:{sid}",
            )
        ])
    rows.append([InlineKeyboardButton("✅ Готово", callback_data="cab:kulek")])
    return InlineKeyboardMarkup(rows)

def _eligible_text(month_key):
    data = month_payload(month_key, force=True)
    if _month_key(month_key) == SEPTEMBER_DISCOUNT_KEY:
        eligible = [
            x for x in data["students"]
            if (discount_status(int(x["id"]), month_key) or {}).get("eligible")
        ]
    else:
        eligible = [x for x in data["students"] if x["draw_eligible"]]
    lines = [
        f"🎁 <b>Розыгрыш скидки 5% — {data['label']}</b>",
        "",
        "В розыгрыш проходят только дети с помесячной оплатой, "
        "у которых закрыты все объективные условия.",
        "",
    ]
    if eligible:
        lines.extend(html.escape(x["name"]) for x in eligible)
    else:
        lines.append("Пока никто не выполнил все условия.")
    return "\n".join(lines)


def _breakthrough_markup(month_key):
    candidates = breakthrough_candidates(month_key)
    rows = []
    for item in candidates:
        rows.append([
            InlineKeyboardButton(
                f"🚀 {item['name']}",
                callback_data=f"cab:kulek:breakthroughconfirm:{month_key}:{item['student_id']}",
            )
        ])
    rows.append([InlineKeyboardButton("← К Кулёчкам", callback_data=f"cab:kulek:month:{month_key}")])
    return InlineKeyboardMarkup(rows)


def _breakthrough_confirm_text(month_key, student_id):
    candidate = next(
        (
            item for item in breakthrough_candidates(month_key)
            if int(item["student_id"]) == int(student_id)
        ),
        None,
    )
    if not candidate:
        return "Не удалось найти кандидата."
    lines = [
        f"🚀 <b>Подтвердить «Прорыв месяца» — {month_label(month_key)}</b>",
        "",
        f"<b>{html.escape(candidate['name'])}</b>",
    ]
    for reason in candidate.get("reasons") or []:
        lines.append(f"• {html.escape(reason)}")
    lines.extend([
        "",
        "После подтверждения выбор сохранится в боте.",
    ])
    return "\n".join(lines)


def _breakthrough_confirm_markup(month_key, student_id):
    candidate = next(
        (
            item for item in breakthrough_candidates(month_key)
            if int(item["student_id"]) == int(student_id)
        ),
        None,
    )
    name = candidate["name"] if candidate else "ученика"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"✅ Выбрать {name}",
                callback_data=f"cab:kulek:breakthroughpick:{month_key}:{int(student_id)}",
            )
        ],
        [
            InlineKeyboardButton(
                "← Назад к кандидатам",
                callback_data=f"cab:kulek:breakthrough:{month_key}",
            )
        ],
    ])


def _breakthrough_text(month_key):
    candidates = breakthrough_candidates(month_key)
    lines = [
        f"🚀 <b>Прорыв месяца — {month_label(month_key)}</b>",
        "",
        "Это не рейтинг по абсолютному баллу. Система смотрит на рост ребёнка "
        "относительно самого себя: пробники, изменение ДЗ, регулярность тренажёров "
        "и твои Кулёчки за практику.",
        "",
    ]
    for item in candidates:
        lines.append(f"<b>{html.escape(item['name'])}</b>")
        if item["reasons"]:
            for reason in item["reasons"]:
                lines.append(f"• {html.escape(reason)}")
        else:
            lines.append("• пока мало данных для динамики")
        lines.append("")
    lines.append("Финальное решение остаётся за тобой — выбери ребёнка кнопкой.")
    return "\n".join(lines)


def _student_month_text(month_key):
    data = month_payload(month_key, force=True, with_breakthrough=False)
    candidates = student_of_month_candidates(month_key)
    winner = data.get("student_of_month_winner")
    lines = [
        f"🏆 <b>Ученик месяца — {month_label(month_key)}</b>",
        "",
        "Награда считается только по объективным данным, без ручной оценки.",
        "",
        "Если все категории доступны:",
        "• 🏠 ДЗ вовремя — 30%",
        "• 🧪 тренажёры — 25%",
        "• 📝 пробники: участие + прогресс относительно себя — 25%",
        "• ✅ месяц без долгов — 20%",
        "",
        "Лишние попытки тренажёров не дают преимущества: по каждому тренажёру "
        "важно только закрыть норму 3+.",
        "Если в месяце какой-то категории объективно не было, её вес "
        "пропорционально перераспределяется между остальными.",
        "Абсолютные баллы пробника между детьми не сравниваются.",
        "",
    ]
    if winner:
        lines.extend([
            f"🏆 Победитель: <b>{html.escape(winner['student_name'])}</b>",
            f"Индекс: <b>{winner['score']:g}/100</b>",
        ])
        tied = winner.get("tied") or []
        if len(tied) > 1:
            lines.append(
                f"При равном результате было {len(tied)} лидера — победитель выбран случайно."
            )
    elif month_key < _month_key():
        lines.append("Месяц закрыт, победитель ещё не зафиксирован.")
    else:
        lines.append("Текущий предварительный расчёт:")
    if candidates:
        lines.append("")
        for item in candidates:
            lines.append(f"<b>{html.escape(item['name'])}</b> — {item['score']:g}/100")
            for component in item["components"].values():
                weight = component.get("effective_weight", component.get("weight", 0))
                lines.append(
                    f"• {html.escape(component['label'])}: "
                    f"{component['value']:g}/100 · вес {weight:g}% · "
                    f"{html.escape(component['detail'])}"
                )
            lines.append("")
    return "\n".join(lines).strip()


def _student_month_markup(month_key):
    data = month_payload(month_key, force=True, with_breakthrough=False)
    rows = []
    if month_key < _month_key() and not data.get("student_of_month_winner"):
        rows.append([
            InlineKeyboardButton(
                "🏆 Определить по системе",
                callback_data=f"cab:kulek:studentmonthpick:{month_key}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            "← К Кулёчкам",
            callback_data=f"cab:kulek:month:{month_key}",
        )
    ])
    return InlineKeyboardMarkup(rows)


def _patch_admin_keyboard():
    current = getattr(live79.live23, "ADMIN_KEYBOARD", None)
    rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []

    # Keep the root reply keyboard compact: Kulechki and Final HW are available
    # from the teacher's "👤 Мой кабинет" inline menu only.
    hidden_root_buttons = {BUTTON, "📚 Итоговые ДЗ"}
    rows = [
        [
            button for button in row
            if getattr(button, "text", button) not in hidden_root_buttons
        ]
        for row in rows
    ]
    rows = [row for row in rows if row]
    live79.live23.ADMIN_KEYBOARD = ReplyKeyboardMarkup(
        rows, resize_keyboard=True, is_persistent=True
    )


def _patch_student_cabinet():
    previous_markup = student_cabinet._student_home_markup
    previous_home_text = student_cabinet._student_home_text
    previous_callback = student_cabinet.student_cabinet_callback

    def home_markup():
        base = previous_markup()
        rows = [list(row) for row in base.inline_keyboard]
        if not any(
            getattr(button, "callback_data", "") == "triv:studentcab:kulek"
            for row in rows for button in row
        ):
            rows.insert(
                max(0, len(rows) - 1),
                [InlineKeyboardButton("🐶 Мои Кулёчки", callback_data="triv:studentcab:kulek")],
            )
        return InlineKeyboardMarkup(rows)

    def home_text(student):
        text = previous_home_text(student)
        try:
            row = student_month(int(student[0]))
            if row:
                text += (
                    f"\n\n🐶 Кулёчки за месяц: "
                    f"{row['points']}/{row['possible']}"
                )
            with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                award = conn.execute(
                    """
                    SELECT month_key
                    FROM kulek_student_month_winners
                    WHERE student_id=?
                    ORDER BY month_key DESC
                    LIMIT 1
                    """,
                    (int(student[0]),),
                ).fetchone()
            if award:
                text += f"\n🏆 Ученик месяца · {month_label(str(award[0]))}"
            discount = active_discount_status(int(student[0]))
            if discount and discount.get("monthly_payment"):
                if discount.get("draw_done"):
                    text += (
                        "\n🎁 Скидка 5%: "
                        + ("выиграна 💗" if discount.get("winner") else "розыгрыш завершён")
                    )
                elif discount.get("remaining_count") == 0:
                    text += "\n🎁 Скидка 5%: все условия выполнены ✅"
                else:
                    text += (
                        f"\n🎁 До розыгрыша скидки: "
                        f"{discount['remaining_count']} усл. осталось"
                    )
        except Exception as exc:
            print(f"Kulek student home line failed: {type(exc).__name__}", flush=True)
        return text

    async def callback(update, context):
        query = update.callback_query
        data = str(query.data or "") if query else ""
        if data == "triv:studentcab:kulek":
            await query.answer()
            student = student_cabinet._student_by_telegram(update.effective_user.id)
            if not student:
                await query.edit_message_text("Сначала нужно привязать Telegram к ученику через /link.")
                return
            await query.edit_message_text(
                student_text(int(student[0])),
                parse_mode="HTML",
                reply_markup=student_cabinet._back_markup(),
            )
            return
        await previous_callback(update, context)

    student_cabinet._student_home_markup = home_markup
    student_cabinet._student_home_text = home_text
    student_cabinet.student_cabinet_callback = callback


def _mark_delivery(month_key, kind, recipient_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO kulek_monthly_deliveries(
                month_key,recipient_kind,recipient_id,sent_at
            ) VALUES(?,?,?,?)
            """,
            (
                month_key, kind, int(recipient_id),
                datetime.now(bot.TIMEZONE).isoformat(),
            ),
        )
        conn.commit()


def _delivered(month_key, kind, recipient_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            """
            SELECT 1 FROM kulek_monthly_deliveries
            WHERE month_key=? AND recipient_kind=? AND recipient_id=?
            """,
            (month_key, kind, int(recipient_id)),
        ).fetchone())


async def breakthrough_prompt_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.day != 1 or now.time() < time(9, 0):
        return
    key = previous_month_key(_month_key())

    data = month_payload(key, force=True)
    if data.get("breakthrough_winner"):
        return

    admin_id = bot.get_admin_id()
    if not admin_id or _delivered(key, "breakthrough_admin_prompt", int(admin_id)):
        return

    candidates = breakthrough_candidates(key)
    if not candidates:
        return

    try:
        await context.bot.send_message(
            chat_id=int(admin_id),
            text=(
                f"🚀 <b>Выбери «Прорыв месяца» — {month_label(key)}</b>\n\n"
                "Я собрала 3 кандидатов по росту относительно самих себя. "
                "Нажми на имя → посмотри причины → подтверди выбор."
            ),
            parse_mode="HTML",
            reply_markup=_breakthrough_markup(key),
        )
        _mark_delivery(key, "breakthrough_admin_prompt", int(admin_id))
    except Exception as exc:
        print(
            f"Breakthrough admin prompt failed: {type(exc).__name__}",
            flush=True,
        )


async def announce_breakthrough_course(context, month_key):
    key = _month_key(month_key)
    data = month_payload(key, force=True, with_breakthrough=False)
    winner = data.get("breakthrough_winner")
    if not winner:
        print(
            f"Breakthrough course announce waiting: month={key} winner=none",
            flush=True,
        )
        return False

    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        print(
            f"Breakthrough course announce skipped: month={key} CHAT_ID missing",
            flush=True,
        )
        return False

    chat_id_int = int(chat_id)
    kind = "breakthrough_course"
    if _delivered(key, kind, chat_id_int):
        return True

    name = html.escape(str(winner["student_name"]))
    text_value = (
        f"🚀 <b>ПРОРЫВ {MONTH_NAMES[int(key.split('-')[1])].upper()} — {name}</b> 💗\n\n"
        "Эта награда не за самый высокий балл, а за самый заметный рост "
        "относительно самого себя за месяц: по пробникам, домашним работам, "
        "тренажёрам и работе на уроках.\n\n"
        "Поздравляем! Сентябрь — только начало. <b>ЕГЭ БЛИЗКО</b> 💗"
    )
    kwargs = {
        "chat_id": chat_id_int,
        "text": text_value,
        "parse_mode": "HTML",
    }
    thread_id = bot.get_target_thread_id()
    if thread_id:
        kwargs["message_thread_id"] = int(thread_id)

    await context.bot.send_message(**kwargs)
    _mark_delivery(key, kind, chat_id_int)
    print(
        f"Breakthrough course announced: month={key} "
        f"student_id={winner['student_id']} name={winner['student_name']}",
        flush=True,
    )
    return True


async def breakthrough_course_announce_tick(context):
    # One-off September announcement requested by Maria; delivery table prevents duplicates.
    if datetime.now(bot.TIMEZONE).date() >= date(2026, 10, 1):
        try:
            await announce_breakthrough_course(context, "2026-09")
        except Exception as exc:
            print(
                f"Breakthrough course announce failed: {type(exc).__name__}: {exc}",
                flush=True,
            )


async def monthly_close_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.day != 1 or now.time() < time(9, 0):
        return
    key = previous_month_key(_month_key())

    # Freeze the objective monthly award before sending month-close summaries.
    try:
        result = choose_student_of_month(key)
        if result.get("ok") and not result.get("existing"):
            print(
                f"Student of month frozen: month={key} "
                f"student_id={result['student_id']} score={result['score']}",
                flush=True,
            )
    except Exception as exc:
        print(
            f"Student of month close failed: {type(exc).__name__}: {exc}",
            flush=True,
        )

    admin_id = bot.get_admin_id()
    if admin_id and not _delivered(key, "admin", int(admin_id)):
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=admin_text(key),
                parse_mode="HTML",
                reply_markup=_admin_markup(key),
            )
            _mark_delivery(key, "admin", int(admin_id))
        except Exception as exc:
            print(f"Kulek monthly admin delivery failed: {type(exc).__name__}", flush=True)

    data = month_payload(key)
    by_id = {int(x["id"]): x for x in data["students"]}
    for student in _student_rows():
        sid = int(student[0])
        telegram_id = student[5]
        if telegram_id is None or sid not in by_id:
            continue
        if _delivered(key, "student", int(telegram_id)):
            continue
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=student_monthly_report_text(sid, key),
                parse_mode="HTML",
            )
            _mark_delivery(key, "student", int(telegram_id))
        except Exception as exc:
            print(
                f"Kulek monthly student delivery failed sid={sid} error={type(exc).__name__}",
                flush=True,
            )

        if key == SEPTEMBER_DISCOUNT_KEY:
            notice = discount_notice_text(sid, key)
            notice_kind = "discount_notice"
            if notice and not _delivered(key, notice_kind, int(telegram_id)):
                try:
                    await context.bot.send_message(
                        chat_id=int(telegram_id),
                        text=notice,
                        parse_mode="HTML",
                    )
                    _mark_delivery(key, notice_kind, int(telegram_id))
                except Exception as exc:
                    print(
                        f"September discount notice failed sid={sid} "
                        f"error={type(exc).__name__}",
                        flush=True,
                    )


    # One common course summary in the main course chat/thread.
    chat_id = bot.os.getenv("CHAT_ID")
    if chat_id:
        try:
            chat_id_int = int(chat_id)
            if not _delivered(key, "course", chat_id_int):
                kwargs = {
                    "chat_id": chat_id_int,
                    "text": course_monthly_report_text(key),
                    "parse_mode": "HTML",
                }
                thread_id = bot.get_target_thread_id()
                if thread_id:
                    kwargs["message_thread_id"] = int(thread_id)
                await context.bot.send_message(**kwargs)
                _mark_delivery(key, "course", chat_id_int)

            if key == SEPTEMBER_DISCOUNT_KEY and not _delivered(
                key, "discount_course_notice", chat_id_int
            ):
                notice_kwargs = {
                    "chat_id": chat_id_int,
                    "text": course_discount_notice_text(key),
                    "parse_mode": "HTML",
                }
                thread_id = bot.get_target_thread_id()
                if thread_id:
                    notice_kwargs["message_thread_id"] = int(thread_id)
                await context.bot.send_message(**notice_kwargs)
                _mark_delivery(key, "discount_course_notice", chat_id_int)
        except Exception as exc:
            print(
                f"Kulek monthly course delivery failed: {type(exc).__name__}",
                flush=True,
            )

    # Personal parent summary for every active parent-child link.
    for parent_id, student_id in _parent_links_for_month():
        kind = f"parent:{int(student_id)}"
        if _delivered(key, kind, int(parent_id)):
            continue
        try:
            await context.bot.send_message(
                chat_id=int(parent_id),
                text=parent_monthly_report_text(student_id, key),
                parse_mode="HTML",
            )
            _mark_delivery(key, kind, int(parent_id))
        except Exception as exc:
            print(
                f"Kulek monthly parent delivery failed parent={parent_id} "
                f"student={student_id} error={type(exc).__name__}",
                flush=True,
            )


async def weekly_progress_tick(context):
    """Send each linked student a month-to-date progress card every Sunday at 19:00."""
    now = datetime.now(bot.TIMEZONE)
    if now.weekday() != 6 or now.time() < time(19, 0):
        return

    month_key = _month_key()
    week_key = now.strftime("%G-W%V")
    kind = f"weekly_progress:{week_key}"

    for student in _student_rows():
        sid = int(student[0])
        telegram_id = student[5]
        if telegram_id is None or _delivered(month_key, kind, int(telegram_id)):
            continue
        text_value = student_weekly_progress_text(sid, month_key)
        if not text_value:
            continue
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=text_value,
                parse_mode="HTML",
            )
            _mark_delivery(month_key, kind, int(telegram_id))
        except Exception as exc:
            print(
                f"Weekly progress delivery failed sid={sid} "
                f"error={type(exc).__name__}: {exc}",
                flush=True,
            )


async def discount_draw_tick(context):
    """At 21:00 freeze and publish the pool; Maria starts the random draw manually."""
    now = datetime.now(bot.TIMEZONE)
    if now.date() != date(2026, 10, 5) or now.time() < time(21, 0):
        return

    admin_id = bot.get_admin_id()
    delivery_id = int(admin_id or 0)
    if delivery_id and _delivered(
        SEPTEMBER_DISCOUNT_KEY, "discount_pool_frozen", delivery_id
    ):
        return

    result = freeze_discount_pool(SEPTEMBER_DISCOUNT_KEY)
    if not result.get("ok"):
        if result.get("error") == "draw_window_open":
            return
        text_value = (
            "🎁 <b>Розыгрыш скидки 5% — сентябрь</b>\n\n"
            "После дедлайна нет учеников, которые одновременно "
            "выполнили все условия и имеют помесячную оплату."
        )
    else:
        text_value = discount_pool_text(SEPTEMBER_DISCOUNT_KEY)

    if admin_id:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=(
                    text_value
                    + "\n\nНажми в <b>Кулёчки → Сентябрь → 🎲 Рандомайзер скидки 5%</b>, "
                    "когда будешь готова провести розыгрыш."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass

    chat_id = bot.os.getenv("CHAT_ID")
    if chat_id:
        try:
            kwargs = {
                "chat_id": int(chat_id),
                "text": text_value,
                "parse_mode": "HTML",
            }
            thread_id = bot.get_target_thread_id()
            if thread_id:
                kwargs["message_thread_id"] = int(thread_id)
            await context.bot.send_message(**kwargs)
        except Exception:
            pass

    if delivery_id:
        _mark_delivery(
            SEPTEMBER_DISCOUNT_KEY, "discount_pool_frozen", delivery_id
        )


def _patch_admin_cabinet_buttons():
    previous_markup = live79.live23.cabinet_markup

    def markup():
        base = previous_markup()
        rows = [list(row) for row in base.inline_keyboard]
        rows = [
            [
                button for button in row
                if getattr(button, "callback_data", "") not in {"cab:finalhw", "cab:kulek"}
            ]
            for row in rows
        ]
        rows = [row for row in rows if row]

        # Keep the beautiful-app launcher at the top when it is present, then
        # place the two everyday teacher controls immediately under it.
        insert_at = 1 if rows else 0
        rows.insert(
            insert_at,
            [
                InlineKeyboardButton("📚 Итоговые ДЗ", callback_data="cab:finalhw"),
                InlineKeyboardButton("🐶 Кулёчки", callback_data="cab:kulek"),
            ],
        )
        return InlineKeyboardMarkup(rows)

    live79.live23.cabinet_markup = markup


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    ensure_tables()
    _patch_admin_keyboard()
    _patch_admin_cabinet_buttons()
    _patch_student_cabinet()

    # Admin bot text button.
    previous_text_router = live79.live7.student_text_router

    async def text_router(update, context):
        if (
            update.effective_chat
            and update.effective_chat.type == "private"
            and bot.user_is_admin(update)
            and update.message
            and update.message.text == BUTTON
        ):
            await update.message.reply_text(
                admin_text(),
                parse_mode="HTML",
                reply_markup=_admin_markup(),
            )
            return
        await previous_text_router(update, context)

    live79.live7.student_text_router = text_router

    # Admin inline callbacks.
    previous_cabinet_callback = live79.live23.cabinet_callback

    async def cabinet_callback(update, context):
        query = update.callback_query
        data = str(query.data or "") if query else ""
        if data == "cab:finalhw":
            if not live79.live23._admin_private(update):
                await query.answer("Только для преподавателя")
                return
            await query.answer()
            text = admin_app._final_homework_bot_text()
            # This report can grow as more final works appear, so split safely.
            rest = str(text or "")
            while rest:
                if len(rest) <= 3800:
                    await query.message.reply_text(rest, parse_mode="HTML")
                    break
                split_at = rest.rfind("\n", 0, 3800)
                if split_at < 1:
                    split_at = 3800
                await query.message.reply_text(rest[:split_at], parse_mode="HTML")
                rest = rest[split_at:].lstrip("\n")
            return

        if not data.startswith("cab:kulek"):
            await previous_cabinet_callback(update, context)
            return
        if not live79.live23._admin_private(update):
            await query.answer("Только для преподавателя")
            return

        if data == "cab:kulek":
            await query.answer()
            await query.edit_message_text(
                admin_text(), parse_mode="HTML", reply_markup=_admin_markup()
            )
            return

        if data == "cab:kulek:practice":
            await query.answer()
            await query.edit_message_text(
                "🐶 <b>Кулёчки за прошлый урок</b>\n\n"
                "Выбери уже прошедший практический урок. После этого просто нажми "
                "на тех детей, которым хочешь выдать Кулёчка. Повторное нажатие снимет награду.",
                parse_mode="HTML",
                reply_markup=_recent_lessons_markup(),
            )
            return

        if data.startswith("cab:kulek:practice:"):
            try:
                lesson = int(data.rsplit(":", 1)[1])
            except Exception:
                await query.answer("Не удалось определить урок")
                return
            month_key, lesson_date = mark_practical_lesson(lesson)
            await query.answer("Практический урок отмечен")
            await query.edit_message_text(
                _practice_lesson_text(lesson, lesson_date),
                parse_mode="HTML",
                reply_markup=_practice_students_markup(lesson),
            )
            return

        if data.startswith("cab:kulek:p:"):
            try:
                _prefix, _k, _p, lesson_text, sid_text = data.split(":")
                lesson = int(lesson_text)
                sid = int(sid_text)
            except Exception:
                await query.answer("Не удалось определить ученика")
                return
            awarded = toggle_practical_award(lesson, sid)
            await query.answer("🐶 Кулёчек выдан" if awarded else "Кулёчек снят")
            dates = tuple(deadlines._course_dates())
            lesson_date = dates[lesson - 1]
            await query.edit_message_text(
                _practice_lesson_text(lesson, lesson_date),
                parse_mode="HTML",
                reply_markup=_practice_students_markup(lesson),
            )
            return

        if data.startswith("cab:kulek:month:"):
            key = data.rsplit(":", 1)[1]
            await query.answer()
            await query.edit_message_text(
                admin_text(key), parse_mode="HTML", reply_markup=_admin_markup(key)
            )
            return

        if data.startswith("cab:kulek:eligible:"):
            key = data.rsplit(":", 1)[1]
            await query.answer()
            await query.edit_message_text(
                _eligible_text(key),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← К Кулёчкам", callback_data=f"cab:kulek:month:{key}")]
                ]),
            )
            return

        if data.startswith("cab:kulek:draw:"):
            key = data.rsplit(":", 1)[1]
            result = draw_discount(key)
            if not result["ok"]:
                if result["error"] == "month_not_closed":
                    msg = "Месяц ещё не закрыт."
                elif result["error"] == "draw_window_open":
                    msg = "Список участников фиксируем 5 октября в 21:00."
                else:
                    msg = "Нет детей, которые выполнили все условия и имеют помесячную оплату."
                await query.answer(msg, show_alert=True)
                return
            await query.answer("Розыгрыш проведён 🎁")
            text = admin_text(key)
            await query.edit_message_text(
                text, parse_mode="HTML", reply_markup=_admin_markup(key)
            )
            if not result.get("existing"):
                student = next(
                    (x for x in _student_rows() if int(x[0]) == int(result["student_id"])),
                    None,
                )
                if student and student[5] is not None:
                    try:
                        await context.bot.send_message(
                            chat_id=int(student[5]),
                            text=(
                                "🎁 <b>Поздравляю!</b>\n\n"
                                f"Твой номер — <b>№{result.get('winner_number')}</b>.\n"
                                f"Ты выиграл(а) скидку <b>5%</b> на октябрь 💗"
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

                chat_id = bot.os.getenv("CHAT_ID")
                if chat_id:
                    try:
                        kwargs = {
                            "chat_id": int(chat_id),
                            "text": (
                                "🎲 <b>РАНДОМАЙЗЕР ОСТАНОВЛЕН!</b>\n\n"
                                f"Выпал номер <b>№{result.get('winner_number')}</b> 🎉\n"
                                f"Победитель — <b>{html.escape(result['winner_name'])}</b> 💗\n\n"
                                "Скидка <b>5%</b> применяется к октябрьской оплате."
                            ),
                            "parse_mode": "HTML",
                        }
                        thread_id = bot.get_target_thread_id()
                        if thread_id:
                            kwargs["message_thread_id"] = int(thread_id)
                        await context.bot.send_message(**kwargs)
                    except Exception:
                        pass
            return

        if data.startswith("cab:kulek:studentmonthpick:"):
            key = data.rsplit(":", 1)[1]
            result = choose_student_of_month(key)
            if not result.get("ok"):
                msg = (
                    "Месяц ещё не закрыт."
                    if result.get("error") == "month_not_closed"
                    else "Пока недостаточно данных для определения победителя."
                )
                await query.answer(msg, show_alert=True)
                return
            await query.answer("Ученик месяца определён 🏆")
            await query.edit_message_text(
                _student_month_text(key),
                parse_mode="HTML",
                reply_markup=_student_month_markup(key),
            )
            if not result.get("existing"):
                student = next(
                    (x for x in _student_rows() if int(x[0]) == int(result["student_id"])),
                    None,
                )
                if student and student[5] is not None:
                    try:
                        await context.bot.send_message(
                            chat_id=int(student[5]),
                            text=(
                                "🏆 <b>Ты — «Ученик месяца»!</b>\n\n"
                                f"За {month_label(key)} у тебя самый высокий объективный "
                                "индекс стабильной работы. Тебя ждёт отдельный подарок от Маши 💗"
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
            return

        if data.startswith("cab:kulek:studentmonth:"):
            key = data.rsplit(":", 1)[1]
            await query.answer()
            await query.edit_message_text(
                _student_month_text(key),
                parse_mode="HTML",
                reply_markup=_student_month_markup(key),
            )
            return

        if data.startswith("cab:kulek:breakthroughconfirm:"):
            try:
                parts = data.split(":")
                key = parts[3]
                sid = int(parts[4])
            except Exception:
                await query.answer("Не удалось открыть кандидата")
                return
            await query.answer()
            await query.edit_message_text(
                _breakthrough_confirm_text(key, sid),
                parse_mode="HTML",
                reply_markup=_breakthrough_confirm_markup(key, sid),
            )
            return

        if data.startswith("cab:kulek:breakthroughpick:"):
            try:
                parts = data.split(":")
                key = parts[3]
                sid = int(parts[4])
            except Exception:
                await query.answer("Не удалось выбрать")
                return
            result = choose_breakthrough(key, sid)
            await query.answer("Прорыв месяца сохранён 🚀")
            await query.edit_message_text(
                admin_text(key), parse_mode="HTML", reply_markup=_admin_markup(key)
            )
            try:
                await announce_breakthrough_course(context, key)
            except Exception as exc:
                print(
                    f"Breakthrough immediate course announce failed: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
            return

        if data.startswith("cab:kulek:breakthrough:"):
            key = data.rsplit(":", 1)[1]
            await query.answer()
            await query.edit_message_text(
                _breakthrough_text(key),
                parse_mode="HTML",
                reply_markup=_breakthrough_markup(key),
            )
            return

        await previous_cabinet_callback(update, context)

    live79.live23.cabinet_callback = cabinet_callback

    # Monthly close delivery piggybacks on the existing 30-second scheduler.
    previous_tick = live79.live7.friday_trivial_tick

    async def tick(context):
        try:
            await previous_tick(context)
        finally:
            # On the 1st, freeze and publish Student of Month first at 09:00,
            # then ask Maria to choose Breakthrough of Month.
            await monthly_close_tick(context)
            await breakthrough_prompt_tick(context)
            await breakthrough_course_announce_tick(context)
            await weekly_progress_tick(context)
            await discount_draw_tick(context)

    live79.live7.friday_trivial_tick = tick


    current = month_payload(_month_key(), force=True)
    print(
        "Kulek rewards ready: "
        f"month={current['month']} students={current['student_count']} "
        f"hw={current['homework_opportunities']} final={current['final_opportunities']} "
        f"trainers={current['trainer_opportunities']} probniki={current['probnik_opportunities']} "
        f"practice={current['practice_opportunities']}",
        flush=True,
    )