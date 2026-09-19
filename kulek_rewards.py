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
import kulechek_mascot

bot = live90.bot
live79 = live90.live79
live34 = live79.live34
live56 = live79.live56

BUTTON = "🐶 Кулёчки"
_INSTALLED = False
_CACHE = {}

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


async def _send_mascot_photo(context, chat_id):
    """Show Maria's approved Kulechek visual when the Kulechki section opens."""
    try:
        await context.bot.send_photo(
            chat_id=int(chat_id),
            photo=kulechek_mascot.image_file(),
        )
    except Exception as exc:
        print(f"Kulechek mascot send failed: {type(exc).__name__}: {exc}", flush=True)


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


def _probnik_scores_for_student(student_id, month_key):
    data = student_month(student_id, month_key)
    if not data:
        return []
    scores = []
    for item in data["categories"]["probnik"]["items"]:
        if item["score"] is not None:
            scores.append(float(item["score"]))
    return scores


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


def draw_discount(month_key=None):
    key = _month_key(month_key)
    current = _month_key()
    if key >= current:
        return {"ok": False, "error": "month_not_closed"}
    data = month_payload(key, force=True, with_breakthrough=False)
    existing = data.get("draw")
    if existing:
        return {"ok": True, "existing": True, **existing}
    eligible = [x for x in data["students"] if x["draw_eligible"]]
    if not eligible:
        return {"ok": False, "error": "no_eligible"}
    winner = secrets.choice(eligible)
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
                json.dumps(
                    [{"id": int(x["id"]), "name": x["name"]} for x in eligible],
                    ensure_ascii=False,
                ),
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
        "discount_percent": 5,
        "eligible_count": len(eligible),
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
    if row["objective_complete"]:
        lines.extend(["", "🌟 <b>Все объективные условия месяца выполнены!</b>"])
        if row["monthly_payment"]:
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
    if _history:
        lines.extend(["", "📅 <b>История</b>"])
        for item in _history[-4:]:
            lines.append(
                f"• {month_label(item['month'])}: {item['points']}/{item['possible']} 🐶"
            )
    return "\n".join(lines)


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

    if data.get("draw"):
        lines.extend([
            "",
            f"🎁 Скидка 5%: <b>{html.escape(data['draw']['winner_name'])}</b>",
        ])
    if data.get("breakthrough_winner"):
        lines.extend([
            f"🚀 Прорыв месяца: <b>{html.escape(data['breakthrough_winner']['student_name'])}</b>",
        ])
    return "\n".join(lines)


def _admin_markup(month_key=None):
    key = _month_key(month_key)
    rows = [
        [InlineKeyboardButton("➕ Выдать за прошлый урок", callback_data="cab:kulek:practice")],
        [InlineKeyboardButton("🚀 Прорыв месяца", callback_data=f"cab:kulek:breakthrough:{key}")],
    ]
    if key < _month_key():
        rows.append([InlineKeyboardButton("🎁 Разыграть скидку 5%", callback_data=f"cab:kulek:draw:{key}")])
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
                callback_data=f"cab:kulek:breakthroughpick:{month_key}:{item['student_id']}",
            )
        ])
    rows.append([InlineKeyboardButton("← К Кулёчкам", callback_data=f"cab:kulek:month:{month_key}")])
    return InlineKeyboardMarkup(rows)


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
            await _send_mascot_photo(context, update.effective_chat.id)
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


async def monthly_close_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.day != 1 or now.time() < time(12, 0):
        return
    key = previous_month_key(_month_key())
    admin_id = bot.get_admin_id()
    if admin_id and not _delivered(key, "admin", int(admin_id)):
        try:
            await _send_mascot_photo(context, int(admin_id))
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
            await _send_mascot_photo(context, int(telegram_id))
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=student_text(sid, key),
                parse_mode="HTML",
            )
            _mark_delivery(key, "student", int(telegram_id))
        except Exception as exc:
            print(
                f"Kulek monthly student delivery failed sid={sid} error={type(exc).__name__}",
                flush=True,
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
            await _send_mascot_photo(context, update.effective_chat.id)
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
            await _send_mascot_photo(context, update.effective_chat.id)
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
                msg = (
                    "Месяц ещё не закрыт."
                    if result["error"] == "month_not_closed"
                    else "Нет детей, которые одновременно выполнили все условия и имеют помесячную оплату."
                )
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
                                f"Ты выиграл(а) скидку <b>5%</b> на следующий месяц "
                                f"в розыгрыше за {month_label(key)} 💗"
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
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
            await monthly_close_tick(context)

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