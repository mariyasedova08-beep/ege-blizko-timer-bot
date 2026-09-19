"""Private student WebApp for EGE BLIZKO.

Read-only personal cabinet. Access is granted only through a short-lived signed
link generated for the currently linked Telegram student.
"""

import hashlib
import hmac
import json
import os
import sqlite3
import time
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90
import run_bot_live49 as student_cabinet
import student_homework_all_debts
import payment_student_ui
import payment_schedule
import lesson_recordings
import kulek_rewards

bot = live90.bot
live79 = live90.live79
live41 = live79.live41
live43 = live79.live43
live17 = live79.live17
live48 = live79.live48

PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
STUDENT_WEBAPP_URL = os.getenv(
    "EGE_STUDENT_WEBAPP_URL",
    f"https://{PUBLIC_DOMAIN}/student-app" if PUBLIC_DOMAIN else "",
).strip()
STUDENT_WEBAPP_BUILD = "20260919-1"
HTML_PATH = Path(__file__).with_name("ege_student_webapp.html")
_INSTALLED = False
_previous_get = None
_previous_post = None
_previous_markup = None
_previous_callback = None
_previous_show = None
_previous_admin_markup = None
_previous_admin_callback = None


def _launch_token(telegram_user_id, ttl=6 * 60 * 60):
    uid = int(telegram_user_id)
    expires = int(time.time()) + int(ttl)
    payload = f"{uid}.{expires}"
    secret = os.getenv("BOT_TOKEN", "")
    signature = hmac.new(
        secret.encode("utf-8"),
        ("ege-student-webapp:" + payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def _validate_launch_token(token):
    try:
        uid_text, exp_text, signature = str(token or "").split(".", 2)
        uid = int(uid_text)
        expires = int(exp_text)
        if expires < int(time.time()):
            return None
        payload = f"{uid}.{expires}"
        secret = os.getenv("BOT_TOKEN", "")
        expected = hmac.new(
            secret.encode("utf-8"),
            ("ege-student-webapp:" + payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        return uid if student_cabinet._student_by_telegram(uid) else None
    except Exception:
        return None


def _fmt_number(value):
    if value is None:
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else round(number, 1)
    except Exception:
        return value


def _week_summary(student, now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        att_present, att_total = live41._weekly_attendance(conn, int(student[0]), now)
        hw_done, hw_total = live41._weekly_homework(conn, student, now)
        try:
            sessions, questions, correct = live41._weekly_trainer_stats(
                conn, int(student[5]), now
            )
        except sqlite3.OperationalError:
            sessions, questions, correct = 0, 0, 0
    return {
        "attendance_present": int(att_present or 0),
        "attendance_total": int(att_total or 0),
        "homework_done": int(hw_done or 0),
        "homework_total": int(hw_total or 0),
        "trainer_sessions": int(sessions or 0),
        "trainer_questions": int(questions or 0),
        "trainer_correct": int(correct or 0),
        "trainer_accuracy": round(100 * correct / questions) if questions else None,
    }


def _attendance(student):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT s.lesson_number,s.lesson_date,ar.status
            FROM attendance_records ar
            JOIN attendance_sessions s ON s.lesson_number=ar.lesson_number
            WHERE ar.student_id=? AND s.finalized=1
            ORDER BY s.lesson_date DESC
            LIMIT 12
            """,
            (int(student[0]),),
        ).fetchall()
    return [
        {
            "lesson": int(lesson),
            "date": str(day or ""),
            "status": str(status or ""),
        }
        for lesson, day, status in rows
    ]


def _homework(student):
    items = student_homework_all_debts._all_assignments(student)
    return [
        {
            "source_no": int(item["source_no"]),
            "source_date": item["source_date"].isoformat(),
            "due_no": int(item["due_no"]),
            "due_date": item["due_date"].isoformat(),
            "done": bool(item["done"]),
            "overdue": bool(item["overdue"]),
            "due_today": bool(item["due_today"]),
            "active": bool(item["active"]),
        }
        for item in items
    ]


def _probniki(student):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT student_name,event_name,event_date,primary_score,secondary_score,tasks_json
            FROM probnik_results
            WHERE secondary_score IS NOT NULL OR primary_score IS NOT NULL
            ORDER BY id DESC
            """
        ).fetchall()
    result = []
    for row in rows:
        if not live43._match_student(row[0], [student]):
            continue
        try:
            tasks = json.loads(row[5] or "{}")
        except Exception:
            tasks = {}
        zero_tasks = live43._zero_tasks(row[5])
        result.append(
            {
                "event": str(row[1] or "Пробник"),
                "date": str(row[2] or ""),
                "primary": _fmt_number(row[3]),
                "secondary": _fmt_number(row[4]),
                "zero_tasks": [str(x) for x in zero_tasks[:12]],
                "tasks_count": len(tasks) if isinstance(tasks, dict) else 0,
            }
        )
        if len(result) >= 6:
            break
    return result


def _trainer_rows(student):
    uid = int(student[5])
    now = datetime.now(bot.TIMEZONE)
    prefix = f"{now.year:04d}-{now.month:02d}%"
    catalog = [
        ("Тривиальные названия", "trivial_sessions"),
        ("Кислоты и остатки", "acid_sessions"),
        ("Металлы", "metals_sessions"),
        ("Оксиды", "oxides_sessions"),
        ("Свойства оксидов", "oxide_properties_sessions"),
        ("Неметаллы", "nonmetals_sessions"),
    ]
    rows = []
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        existing = {
            str(name)
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for title, table in catalog:
            if table not in existing:
                continue
            sessions, total, correct = conn.execute(
                f"""
                SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
                FROM {table}
                WHERE telegram_user_id=? AND finished_at IS NOT NULL
                  AND finished_at LIKE ?
                """,
                (uid, prefix),
            ).fetchone()
            sessions = int(sessions or 0)
            total = int(total or 0)
            correct = int(correct or 0)
            rows.append(
                {
                    "title": title,
                    "sessions": sessions,
                    "questions": total,
                    "correct": correct,
                    "accuracy": round(100 * correct / total) if total else 0,
                }
            )
    return rows


def _kulek(student):
    row = kulek_rewards.student_month(int(student[0]))
    if not row:
        return None
    total_year, history = kulek_rewards.student_year_total(int(student[0]))
    return {
        "points": int(row.get("points") or 0),
        "possible": int(row.get("possible") or 0),
        "objective_complete": bool(row.get("objective_complete")),
        "draw_eligible": bool(row.get("draw_eligible")),
        "remaining": [str(x) for x in (row.get("remaining") or [])[:8]],
        "categories": row.get("categories") or {},
        "year_total": int(total_year or 0),
        "history": [
            {
                "month": str(item.get("month") or ""),
                "points": int(item.get("points") or 0),
                "possible": int(item.get("possible") or 0),
            }
            for item in history[-6:]
        ],
    }


def _payment(telegram_user_id):
    row = payment_student_ui._row_for_telegram_user(int(telegram_user_id))
    if not row:
        return {"connected": False}
    item = row.get("next_invoice")
    paid_label = payment_student_ui._paid_period_label(row)
    payload = {
        "connected": True,
        "cadence": str(row.get("cadence") or ""),
        "cadence_label": payment_schedule.CADENCE_LABELS.get(
            row.get("cadence"), str(row.get("cadence") or "")
        ),
        "paid_label": str(paid_label or ""),
        "fully_paid": bool(row.get("cadence") == "prepaid" or not item),
    }
    if item:
        payload["next"] = {
            "label": str(item.get("label") or ""),
            "amount": payment_schedule.money(int(item.get("remaining_cents") or 0)),
            "due_date": item["due_date"].isoformat() if item.get("due_date") else "",
            "status": str(item.get("status") or ""),
        }
    return payload


def _recordings():
    saved = lesson_recordings._recording_map()
    if not saved:
        return []
    topics = {}
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        try:
            for number, topic, event_date in conn.execute(
                """
                SELECT lesson_number,topic,event_date
                FROM course_schedule
                WHERE active=1 AND lesson_number IS NOT NULL
                """
            ).fetchall():
                topics[int(number)] = {
                    "topic": str(topic or ""),
                    "date": str(event_date or ""),
                }
        except Exception:
            pass
    result = []
    for lesson in sorted(saved, reverse=True):
        meta = topics.get(int(lesson), {})
        result.append(
            {
                "lesson": int(lesson),
                "url": str(saved[lesson].get("url") or ""),
                "topic": str(meta.get("topic") or ""),
                "date": str(meta.get("date") or ""),
            }
        )
        if len(result) >= 20:
            break
    return result


def _payload(telegram_user_id):
    student = student_cabinet._student_by_telegram(int(telegram_user_id))
    if not student:
        return None
    now = datetime.now(bot.TIMEZONE)
    monthly = student_cabinet._monthly_metrics(student, now)
    probniki = _probniki(student)
    course_lesson = bot.get_course_lesson_number(now.date())
    weak = probniki[0]["zero_tasks"] if probniki else []
    return {
        "student": {
            "id": int(student[0]),
            "name": str(student[1] or "Ученик"),
            "first_name": student_cabinet._first_name(student),
            "course": student_cabinet.COURSE_NAME,
        },
        "today": now.date().isoformat(),
        "month_label": f"{student_cabinet.live15.MONTH_NAMES[now.month]} {now.year}",
        "course": {
            "days_left": int(bot.days_left()),
            "lesson_number": int(course_lesson),
            "total_lessons": int(bot.TOTAL_LESSONS),
        },
        "week": _week_summary(student, now),
        "month": {
            "probnik_count": int(monthly.get("probnik_count") or 0),
            "probnik_avg": _fmt_number(monthly.get("probnik_avg")),
            "probnik_best": _fmt_number(monthly.get("probnik_best")),
            "homework_count": int(monthly.get("homework_count") or 0),
            "homework_accuracy": _fmt_number(monthly.get("homework_accuracy")),
            "attendance_present": int(monthly.get("attendance_present") or 0),
            "attendance_total": int(monthly.get("attendance_total") or 0),
            "trainer_sessions": int(monthly.get("trainer_sessions") or 0),
            "trainer_total": int(monthly.get("trainer_total") or 0),
            "trainer_correct": int(monthly.get("trainer_correct") or 0),
        },
        "attendance": _attendance(student),
        "homework": _homework(student),
        "probniki": probniki,
        "trainers": _trainer_rows(student),
        "kulek": _kulek(student),
        "payment": _payment(telegram_user_id),
        "recordings": _recordings(),
        "weak_tasks": weak,
    }


def _http_get(self):
    parsed = urlparse(self.path)
    if parsed.path != "/student-app":
        return _previous_get(self)
    try:
        body = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
    except Exception as exc:
        print(f"EGE student WebApp html error: {type(exc).__name__}: {exc}", flush=True)
        self._send_json(500, {"ok": False, "error": "webapp_unavailable"})


def _http_post(self):
    parsed = urlparse(self.path)
    if parsed.path not in {"/student-app/api", "/student-app/client-error"}:
        return _previous_post(self)
    try:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 30000:
            raise ValueError("bad length")
        request = json.loads(self.rfile.read(length).decode("utf-8"))

        if parsed.path == "/student-app/client-error":
            print(
                "EGE STUDENT WEBAPP CLIENT ERROR "
                f"where={str(request.get('where') or '')[:100]} "
                f"message={str(request.get('message') or '')[:500]}",
                flush=True,
            )
            self._send_json(200, {"ok": True})
            return

        uid = _validate_launch_token(request.get("launch"))
        if not uid:
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return
        data = _payload(uid)
        if not data:
            self._send_json(404, {"ok": False, "error": "student_not_found"})
            return
        print(
            f"EGE student WebApp request student_id={data['student']['id']}",
            flush=True,
        )
        self._send_json(200, {"ok": True, "data": data})
    except Exception as exc:
        print(
            f"EGE student WebApp api error: {type(exc).__name__}: {exc}\n"
            + traceback.format_exc(),
            flush=True,
        )
        self._send_json(400, {"ok": False, "error": "bad_request"})


def _launcher_url(telegram_user_id):
    sep = "&" if "?" in STUDENT_WEBAPP_URL else "?"
    return (
        f"{STUDENT_WEBAPP_URL}{sep}launch={_launch_token(telegram_user_id)}"
        f"&v={STUDENT_WEBAPP_BUILD}"
    )


def _patch_student_cabinet():
    global _previous_markup, _previous_callback, _previous_show
    _previous_markup = student_cabinet._student_home_markup
    _previous_callback = student_cabinet.student_cabinet_callback
    _previous_show = student_cabinet.show_student_cabinet

    def home_markup():
        # Fallback markup used by older code paths. A live student opening the
        # cabinet gets a signed direct URL from show_student_cabinet_with_webapp.
        return _previous_markup()

    def markup_for(uid):
        base = _previous_markup()
        rows = [list(row) for row in base.inline_keyboard]
        rows = [
            [
                button for button in row
                if getattr(button, "callback_data", "") != "triv:studentcab:webapp"
            ]
            for row in rows
        ]
        rows = [row for row in rows if row]
        rows.insert(
            0,
            [InlineKeyboardButton(
                "💗 Открыть приложение",
                url=_launcher_url(uid),
            )],
        )
        return InlineKeyboardMarkup(rows)

    async def show_student_cabinet_with_webapp(update, context, student=None, edit=False):
        student = student or student_cabinet._student_by_telegram(update.effective_user.id)
        if not student:
            return await _previous_show(update, context, student=student, edit=edit)
        text = student_cabinet._student_home_text(student)
        markup = markup_for(update.effective_user.id)
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        else:
            await update.effective_message.reply_text(text, reply_markup=markup)

    async def callback(update, context):
        query = update.callback_query
        data = str(query.data or "") if query else ""
        if data != "triv:studentcab:webapp":
            return await _previous_callback(update, context)

        # Legacy callback from the first WebApp build. Keep old messages useful.
        await query.answer()
        student = student_cabinet._student_by_telegram(update.effective_user.id)
        if not student:
            await query.edit_message_text(
                "Сначала нужно привязать Telegram к ученику через /link."
            )
            return
        await query.message.reply_text(
            "💗 <b>ЕГЭ БЛИЗКО — твой личный кабинет</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "💗 Открыть приложение",
                    url=_launcher_url(update.effective_user.id),
                )
            ]]),
        )

    student_cabinet._student_home_markup = home_markup
    student_cabinet.show_student_cabinet = show_student_cabinet_with_webapp
    student_cabinet.student_cabinet_callback = callback



def _patch_admin_preview():
    """Let Maria open the exact live cabinet of any linked student."""
    global _previous_admin_markup, _previous_admin_callback
    live23 = live79.live23
    _previous_admin_markup = live23.cabinet_markup
    _previous_admin_callback = live23.cabinet_callback

    def cabinet_markup():
        base = _previous_admin_markup()
        rows = [list(row) for row in base.inline_keyboard]
        if not any(
            getattr(button, "callback_data", "") == "cab:studentapp"
            for row in rows for button in row
        ):
            insert_at = 1 if rows else 0
            rows.insert(
                insert_at,
                [InlineKeyboardButton(
                    "👀 Посмотреть кабинет ученика",
                    callback_data="cab:studentapp",
                )],
            )
        return InlineKeyboardMarkup(rows)

    async def cabinet_callback(update, context):
        query = update.callback_query
        data = str(query.data or "") if query else ""
        if not data.startswith("cab:studentapp"):
            return await _previous_admin_callback(update, context)

        if not live23._admin_private(update):
            await query.answer("Только для преподавателя")
            return

        if data == "cab:studentapp":
            await query.answer()
            with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                students = conn.execute(
                    """
                    SELECT id,
                           coalesce(nullif(display_name,''),nullif(user_name,''),user_email,'Ученик'),
                           telegram_user_id
                    FROM students
                    WHERE active=1 AND telegram_user_id IS NOT NULL
                    ORDER BY 2 COLLATE NOCASE
                    """
                ).fetchall()
            rows = [
                [InlineKeyboardButton(
                    str(name),
                    callback_data=f"cab:studentapp:{int(student_id)}",
                )]
                for student_id, name, telegram_id in students
            ]
            rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
            await query.edit_message_text(
                "👀 <b>Посмотреть кабинет ученика</b>\n\n"
                "Выбери ребёнка — откроется ровно тот же личный кабинет, "
                "который видит он.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(rows),
            )
            return

        try:
            student_id = int(data.rsplit(":", 1)[1])
        except Exception:
            await query.answer("Не удалось определить ученика")
            return

        student = student_cabinet._student_by_id(student_id)
        if not student or student[5] is None:
            await query.answer("У ученика не привязан Telegram", show_alert=True)
            return

        await query.answer()
        await query.message.reply_text(
            f"👀 <b>{student[1]} — личный кабинет</b>\n\n"
            "Это живая версия с теми же данными, которые видит ученик.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "💗 Открыть кабинет ученика",
                    url=_launcher_url(int(student[5])),
                )
            ], [
                InlineKeyboardButton(
                    "← Выбрать другого",
                    callback_data="cab:studentapp",
                )
            ]]),
        )

    live23.cabinet_markup = cabinet_markup
    live23.cabinet_callback = cabinet_callback

def install():
    global _INSTALLED, _previous_get, _previous_post
    if _INSTALLED:
        return
    _INSTALLED = True

    _previous_get = bot.CoreAppWebhookHandler.do_GET
    _previous_post = bot.CoreAppWebhookHandler.do_POST
    bot.CoreAppWebhookHandler.do_GET = _http_get
    bot.CoreAppWebhookHandler.do_POST = _http_post
    _patch_student_cabinet()
    _patch_admin_preview()

    ok = 0
    linked = []
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        linked = [
            int(row[0])
            for row in conn.execute(
                """
                SELECT telegram_user_id FROM students
                WHERE active=1 AND telegram_user_id IS NOT NULL
                """
            ).fetchall()
        ]
    for uid in linked:
        try:
            data = _payload(uid)
            if data and data.get("student"):
                ok += 1
        except Exception as exc:
            print(
                f"EGE student WebApp audit failed uid={uid} "
                f"error={type(exc).__name__}: {exc}",
                flush=True,
            )
    print(
        f"EGE student WebApp ready: url={STUDENT_WEBAPP_URL or 'missing'} "
        f"linked={len(linked)} payloads={ok}",
        flush=True,
    )
