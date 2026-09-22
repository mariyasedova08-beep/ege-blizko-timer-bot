"""Pink-beige Telegram WebApp home screen for PREPODMIN."""
import hashlib
import hmac
import json
import os
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_today as today
import teacher_product_learning as learning
import teacher_product_payments as payments
import teacher_product_groups as groups
import teacher_product_slots as slots
import teacher_product_tasks as tasks
import teacher_product_reports as reports
import teacher_product_student_webapp as student_webapp

PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
WEBAPP_URL = os.getenv(
    "TEACHER_PRODUCT_WEBAPP_URL",
    f"https://{PUBLIC_DOMAIN}/webapp" if PUBLIC_DOMAIN else "",
).strip()
MAX_AUTH_AGE = 24 * 60 * 60
WEBAPP_BUILD = "20260919-5"
HTML_PATH = Path(__file__).with_name("teacher_product_webapp.html")
_INSTALLED = False


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _safe_count(conn, sql, params=()):
    try:
        return int(conn.execute(sql, params).fetchone()[0] or 0)
    except Exception:
        return 0


def _dashboard(uid):
    row = base.teacher(uid)
    if not row or not row["onboarding_completed_at"]:
        return None

    now = datetime.now(schedule.tz(uid))
    day = now.date()
    events = today._individual_today(uid, day) + today._group_today(uid, day)
    events.sort(key=lambda e: (str(e["time"]), e["kind"], str(e["name"]).lower()))

    with base.db() as conn:
        task_rows = conn.execute(
            """
            SELECT id,title,due_date,due_time
            FROM teacher_tasks
            WHERE teacher_telegram_user_id=? AND completed=0
              AND due_date<=?
            ORDER BY due_date,
                     CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,
                     due_time,id
            LIMIT 6
            """,
            (int(uid), day.isoformat()),
        ).fetchall()

        hw_overdue = _safe_count(
            conn,
            """
            SELECT COUNT(*)
            FROM teacher_homework_status hs
            JOIN teacher_homework h ON h.id=hs.assignment_id
            WHERE h.teacher_telegram_user_id=?
              AND h.active=1
              AND hs.status='pending'
              AND h.due_date<?
            """,
            (int(uid), day.isoformat()),
        )
        hw_today = _safe_count(
            conn,
            """
            SELECT COUNT(*)
            FROM teacher_homework_status hs
            JOIN teacher_homework h ON h.id=hs.assignment_id
            WHERE h.teacher_telegram_user_id=?
              AND h.active=1
              AND hs.status='pending'
              AND h.due_date=?
            """,
            (int(uid), day.isoformat()),
        )
        payment_due = _safe_count(
            conn,
            """
            SELECT COUNT(*)
            FROM student_payment_plans p
            JOIN students s ON s.id=p.student_id
            WHERE p.teacher_telegram_user_id=?
              AND p.active=1 AND s.active=1
              AND p.next_due_date<=?
            """,
            (int(uid), day.isoformat()),
        )

    attention = reports.attention_rows(uid)

    return {
        "teacher": {
            "name": row["name"] or "коллега",
            "subject": row["subject"] or "",
        },
        "date": day.strftime("%d.%m.%Y"),
        "weekday": (
            "понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье"
        )[day.weekday()],
        "counts": {
            "lessons": len(events),
            "homework": hw_overdue + hw_today,
            "homework_overdue": hw_overdue,
            "payments": payment_due,
            "attention": len(attention),
        },
        "events": [
            {
                "time": e["time"],
                "name": e["name"],
                "kind": "Группа" if e["kind"] == "group" else "Ученик",
                "moved": bool(e.get("moved")),
            }
            for e in events[:5]
        ],
        "tasks": [
            {
                "id": int(r["id"]),
                "title": r["title"],
                "due_date": r["due_date"],
                "due_time": r["due_time"] or "",
                "overdue": r["due_date"] < day.isoformat(),
            }
            for r in task_rows
        ],
        "attention": [
            {"name": name, "scope": scope, "reasons": reasons}
            for name, scope, reasons, _callback in attention[:4]
        ],
    }


def _students_view(uid):
    students = base.list_students(uid)
    group_rows = groups.groups(uid)
    return {
        "title": "Ученики и группы",
        "students": [
            {"id": int(s["id"]), "name": s["name"], "contact": s["contact"] or ""}
            for s in students
        ],
        "groups": [
            {"id": int(g["id"]), "name": g["name"]}
            for g in group_rows
        ],
    }


def _schedule_view(uid):
    now = datetime.now(schedule.tz(uid))
    days = []
    for offset in range(7):
        day = now.date() + __import__("datetime").timedelta(days=offset)
        events = today._individual_today(uid, day) + today._group_today(uid, day)
        events.sort(key=lambda e: (str(e["time"]), e["kind"], str(e["name"]).lower()))
        days.append({
            "date": day.strftime("%d.%m"),
            "weekday": ("Пн","Вт","Ср","Чт","Пт","Сб","Вс")[day.weekday()],
            "is_today": offset == 0,
            "events": [
                {
                    "time": e["time"],
                    "name": e["name"],
                    "kind": "Группа" if e["kind"] == "group" else "Ученик",
                    "moved": bool(e.get("moved")),
                }
                for e in events
            ],
        })
    return {"title": "Расписание", "days": days}


def _homework_view(uid):
    now = datetime.now(schedule.tz(uid)).date()
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT h.id,h.homework_text,h.due_date,h.target_kind,h.target_id,
                   COUNT(*) AS total,
                   SUM(CASE WHEN hs.status='done' THEN 1 ELSE 0 END) AS done
            FROM teacher_homework h
            LEFT JOIN teacher_homework_status hs ON hs.assignment_id=h.id
            WHERE h.teacher_telegram_user_id=? AND h.active=1
            GROUP BY h.id,h.homework_text,h.due_date,h.target_kind,h.target_id
            ORDER BY h.due_date,h.id
            LIMIT 60
            """,
            (int(uid),),
        ).fetchall()
        group_map = {
            int(r["id"]): r["name"]
            for r in conn.execute(
                "SELECT id,name FROM teacher_groups WHERE teacher_telegram_user_id=?",
                (int(uid),),
            ).fetchall()
        }
        student_map = {
            int(r["id"]): r["name"]
            for r in conn.execute(
                "SELECT id,name FROM students WHERE teacher_telegram_user_id=?",
                (int(uid),),
            ).fetchall()
        }
    items = []
    for r in rows:
        target = (
            group_map.get(int(r["target_id"]), "Группа")
            if r["target_kind"] == "group"
            else student_map.get(int(r["target_id"]), "Ученик")
        )
        due = r["due_date"]
        items.append({
            "text": r["homework_text"],
            "due": due,
            "target": target,
            "done": int(r["done"] or 0),
            "total": int(r["total"] or 0),
            "overdue": due < now.isoformat() and int(r["done"] or 0) < int(r["total"] or 0),
        })
    return {"title": "Домашние задания", "items": items}


def _payments_view(uid):
    now = datetime.now(schedule.tz(uid)).date()
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT s.name,p.payment_type,p.amount_rub,p.next_due_date,p.active,
                   p.lessons_total,p.lessons_remaining
            FROM students s
            LEFT JOIN student_payment_plans p
              ON p.student_id=s.id
             AND p.teacher_telegram_user_id=s.teacher_telegram_user_id
            WHERE s.teacher_telegram_user_id=? AND s.active=1
            ORDER BY CASE WHEN p.next_due_date IS NULL THEN 1 ELSE 0 END,
                     p.next_due_date,lower(s.name)
            """,
            (int(uid),),
        ).fetchall()
    items = []
    for r in rows:
        status = "Не настроено"
        level = "muted"
        if r["payment_type"] and int(r["active"] or 0):
            if r["payment_type"] == "package":
                left = int(r["lessons_remaining"] or 0)
                total = int(r["lessons_total"] or 0)
                status = f"Осталось {left}/{total} занятий"
                level = "bad" if left <= 0 else "ok"
            else:
                due = r["next_due_date"]
                if due:
                    if due < now.isoformat():
                        status = "Просрочено"
                        level = "bad"
                    elif due == now.isoformat():
                        status = "Оплата сегодня"
                        level = "warn"
                    else:
                        status = "До " + datetime.fromisoformat(due).strftime("%d.%m")
                        level = "ok"
        items.append({
            "name": r["name"],
            "amount": int(r["amount_rub"] or 0),
            "status": status,
            "level": level,
        })
    return {"title": "Оплаты", "items": items}


def _attention_view(uid):
    rows = reports.attention_rows(uid)
    return {
        "title": "Зона внимания",
        "items": [
            {"name": name, "scope": scope, "reasons": reasons}
            for name, scope, reasons, _cb in rows
        ],
    }


def _tasks_view(uid):
    today_date = datetime.now(schedule.tz(uid)).date()
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT id,title,due_date,due_time,task_kind
            FROM teacher_tasks
            WHERE teacher_telegram_user_id=? AND completed=0
            ORDER BY due_date,
                     CASE WHEN due_time IS NULL THEN 1 ELSE 0 END,
                     due_time,id
            LIMIT 80
            """,
            (int(uid),),
        ).fetchall()
    return {
        "title": "Задачи",
        "items": [
            {
                "id": int(r["id"]),
                "title": r["title"],
                "due_date": r["due_date"],
                "due_time": r["due_time"] or "",
                "kind": r["task_kind"] or "work",
                "overdue": r["due_date"] < today_date.isoformat(),
            }
            for r in rows
        ],
    }


def _teacher_action(uid, payload):
    action_name = str(payload.get("action") or "")
    if action_name != "task_done":
        return {"ok": False, "error": "unknown_action"}

    try:
        task_id = int(payload.get("task_id"))
    except Exception:
        return {"ok": False, "error": "bad_task_id"}

    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT id,title,completed
            FROM teacher_tasks
            WHERE id=? AND teacher_telegram_user_id=?
            """,
            (task_id, int(uid)),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        if int(row["completed"] or 0):
            return {"ok": True, "already_done": True, "task_id": task_id}

        conn.execute(
            """
            UPDATE teacher_tasks
            SET completed=1,completed_at=?
            WHERE id=? AND teacher_telegram_user_id=? AND completed=0
            """,
            (now, task_id, int(uid)),
        )
        conn.commit()

    print(
        f"PREPODMIN WebApp task completed uid={int(uid)} task_id={task_id}",
        flush=True,
    )
    return {
        "ok": True,
        "task_id": task_id,
        "title": row["title"],
    }


def _attendance_view(uid):
    start, end = reports._range(uid, 30)
    indiv, members = reports._all_subjects(uid)
    a = reports._aggregate(uid, indiv, members, start, end)
    total = a["present"] + a["absent"]
    pct = None if not total else round(100 * a["present"] / total)
    return {
        "title": "Посещаемость",
        "period": f"{start.strftime('%d.%m')}–{end.strftime('%d.%m')}",
        "present": a["present"],
        "absent": a["absent"],
        "percent": pct,
    }


def _reports_view(uid):
    start, end = reports._range(uid, 30)
    indiv, members = reports._all_subjects(uid)
    a = reports._aggregate(uid, indiv, members, start, end)
    attendance_total = a["present"] + a["absent"]
    return {
        "title": "Отчёты",
        "period": f"{start.strftime('%d.%m')}–{end.strftime('%d.%m')}",
        "learners": a["learners"],
        "attendance": None if not attendance_total else round(100 * a["present"] / attendance_total),
        "homework": None if not a["hw_total"] else round(100 * a["done"] / a["hw_total"]),
        "overdue_homework": a["overdue"],
        "payment_issues": a["payment_issues"],
        "attention": len(reports.attention_rows(uid)),
    }


def _slots_view(uid):
    now = datetime.now(schedule.tz(uid))
    day = now.date()
    events = today._individual_today(uid, day) + today._group_today(uid, day)
    events.sort(key=lambda e: str(e["time"]))
    with base.db() as conn:
        blocks = conn.execute(
            """
            SELECT start_time,end_time,label
            FROM teacher_slot_blocks
            WHERE teacher_telegram_user_id=? AND block_date=?
            ORDER BY start_time
            """,
            (int(uid), day.isoformat()),
        ).fetchall()
    return {
        "title": "Свободные окна",
        "date": day.strftime("%d.%m.%Y"),
        "busy": [{"time": e["time"], "name": e["name"]} for e in events],
        "blocks": [
            {"start": r["start_time"], "end": r["end_time"], "label": r["label"] or "Закрыто"}
            for r in blocks
        ],
    }


def _view(uid, name):
    builders = {
        "home": _dashboard,
        "students": _students_view,
        "schedule": _schedule_view,
        "homework": _homework_view,
        "payments": _payments_view,
        "attention": _attention_view,
        "tasks": _tasks_view,
        "attendance": _attendance_view,
        "reports": _reports_view,
        "slots": _slots_view,
    }
    builder = builders.get(name)
    return builder(uid) if builder else None


def _launch_token(uid, ttl=24 * 60 * 60):
    expires = int(time.time()) + int(ttl)
    payload = f"{int(uid)}.{expires}"
    signature = hmac.new(
        base.BOT_TOKEN.encode("utf-8"),
        ("prepodmin-webapp:" + payload).encode("utf-8"),
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
        expected = hmac.new(
            base.BOT_TOKEN.encode("utf-8"),
            ("prepodmin-webapp:" + payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        return uid
    except Exception:
        return None


def _validate_init_data(init_data):
    if not base.BOT_TOKEN or not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        supplied_hash = pairs.pop("hash", "")
        if not supplied_hash:
            return None
        check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
        secret = hmac.new(
            b"WebAppData",
            base.BOT_TOKEN.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected = hmac.new(
            secret,
            check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, supplied_hash):
            return None
        auth_date = int(pairs.get("auth_date", "0") or 0)
        if not auth_date or abs(int(time.time()) - auth_date) > MAX_AUTH_AGE:
            return None
        user = json.loads(pairs.get("user", "{}"))
        return int(user.get("id"))
    except Exception:
        return None


class WebAppHandler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send(200, _json_bytes({
                "ok": True,
                "service": "teacher-product-mvp",
                "webapp": True,
                "quick_setup": True,
                "build": "2026-09-22-onboarding-2",
            }))
            return
        if path in {"/", "/webapp"}:
            try:
                self._send(200, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            except Exception as exc:
                print(f"PREPODMIN WebApp html error: {type(exc).__name__}: {exc}", flush=True)
                self._send(500, b"WebApp unavailable", "text/plain; charset=utf-8")
            return
        if path == "/student":
            try:
                self._send(200, student_webapp.HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            except Exception as exc:
                print(f"PREPODMIN student WebApp html error: {type(exc).__name__}: {exc}", flush=True)
                self._send(500, b"Student WebApp unavailable", "text/plain; charset=utf-8")
            return
        self._send(404, _json_bytes({"ok": False, "error": "not_found"}))

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in {"/api/dashboard", "/api/teacher/action", "/api/student", "/api/student/action", "/api/client-error"}:
            self._send(404, _json_bytes({"ok": False, "error": "not_found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 20000:
                raise ValueError("bad length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))

            if path == "/api/client-error":
                print(
                    "PREPODMIN WEBAPP CLIENT ERROR "
                    f"role={str(payload.get('role') or '')[:20]} "
                    f"where={str(payload.get('where') or '')[:80]} "
                    f"message={str(payload.get('message') or '')[:500]}",
                    flush=True,
                )
                self._send(200, _json_bytes({"ok": True}))
                return

            uid = _validate_init_data(payload.get("initData", ""))
            if path in {"/api/dashboard", "/api/teacher/action"}:
                if not uid:
                    uid = _validate_launch_token(payload.get("launch", ""))
                if not uid:
                    print(f"PREPODMIN WebApp auth failed path={path}", flush=True)
                    self._send(401, _json_bytes({"ok": False, "error": "unauthorized"}))
                    return

            if path == "/api/teacher/action":
                data = _teacher_action(uid, payload)
                status = 200 if data.get("ok") else 400
                self._send(status, _json_bytes(data))
                return

            if path == "/api/dashboard":
                view_name = str(payload.get("view") or "home")
                print(f"PREPODMIN WebApp request path=teacher view={view_name} uid={uid}", flush=True)
                data = _view(uid, view_name)
                if not data:
                    self._send(403, _json_bytes({"ok": False, "error": "not_available"}))
                    return
                self._send(200, _json_bytes({"view": view_name, "data": data}))
                return

            if not uid:
                uid = student_webapp.validate_launch_token(payload.get("launch", ""))
            if not uid:
                print(f"PREPODMIN WebApp auth failed path={path}", flush=True)
                self._send(401, _json_bytes({"ok": False, "error": "unauthorized"}))
                return

            if path == "/api/student":
                view_name = str(payload.get("view") or "home")
                print(f"PREPODMIN WebApp request path=student view={view_name} uid={uid} link={payload.get('link_id')}", flush=True)
                data = student_webapp.view(
                    uid,
                    view_name,
                    payload.get("link_id"),
                )
            else:
                data = student_webapp.action(uid, payload)
            if not data:
                self._send(403, _json_bytes({"ok": False, "error": "not_available"}))
                return
            self._send(200, _json_bytes(data))
        except Exception as exc:
            print(
                f"PREPODMIN WebApp api error path={path}: {type(exc).__name__}: {exc}\n"
                + traceback.format_exc(),
                flush=True,
            )
            self._send(400, _json_bytes({"ok": False, "error": "bad_request"}))

    def log_message(self, fmt, *args):
        return


def start_web_server():
    ThreadingHTTPServer(("0.0.0.0", base.PORT), WebAppHandler).serve_forever()


def install_server():
    base.start_health_server = start_web_server
    print(
        f"PREPODMIN WebApp server ready: url={WEBAPP_URL or 'missing-public-url'}",
        flush=True,
    )


def _main_keyboard_with_webapp():
    current = getattr(base, "MAIN_KB", None)
    rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []
    rows = [
        row for row in rows
        if not any(getattr(button, "text", button) == "💗 Главная ПРЕПОДМИН" for button in row)
    ]
    rows.insert(0, [KeyboardButton("💗 Главная ПРЕПОДМИН")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def _launch_markup(uid):
    token = _launch_token(uid)
    sep = "&" if "?" in WEBAPP_URL else "?"
    url = f"{WEBAPP_URL}{sep}launch={token}&v={WEBAPP_BUILD}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💗 Открыть главную",
            web_app=WebAppInfo(url=url),
        )
    ]])


async def open_webapp(update, context):
    if not base.teacher(update.effective_user.id):
        return
    if not WEBAPP_URL:
        await update.message.reply_text("Главная сейчас недоступна. Попробуй чуть позже.")
        return
    await update.message.reply_text(
        "💗 <b>ПРЕПОДМИН</b>\n\nОткрывай красивую главную — здесь будут реальные занятия, ДЗ, оплаты, задачи и зона внимания.",
        parse_mode="HTML",
        reply_markup=_launch_markup(update.effective_user.id),
    )


async def webapp_action(update, context):
    if not update.message or not update.message.web_app_data:
        return
    if not base.teacher(update.effective_user.id):
        return
    try:
        payload = json.loads(update.message.web_app_data.data or "{}")
        action = str(payload.get("action") or "")
    except Exception:
        action = ""

    mapping = {
        "students": groups.people_menu,
        "schedule": schedule.schedule_menu,
        "homework": learning.homework_menu,
        "attendance": learning.attendance_menu,
        "payments": payments.payments_menu,
        "slots": slots.slots_menu,
        "tasks": tasks.tasks_menu,
        "reports": reports.reports_menu,
    }
    if action == "attention":
        text, _rows = reports.attention_text(update.effective_user.id)
        await update.message.reply_text(text[:3900], reply_markup=base.MAIN_KB)
        return

    handler = mapping.get(action)
    if not handler:
        await update.message.reply_text(
            "Не поняла действие. Открой «💗 Главная ПРЕПОДМИН» ещё раз.",
            reply_markup=base.MAIN_KB,
        )
        return
    try:
        await handler(update, context)
    except ApplicationHandlerStop:
        return


async def _push_keyboard_migration(context):
    migration_key = "webapp-auth-launch-v2"
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_webapp_migrations (
                teacher_telegram_user_id INTEGER NOT NULL,
                migration_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(teacher_telegram_user_id,migration_key)
            )
            """
        )
        teachers = conn.execute(
            """
            SELECT telegram_user_id
            FROM teachers
            WHERE onboarding_completed_at IS NOT NULL
            ORDER BY telegram_user_id
            """
        ).fetchall()
        sent_rows = {
            int(r[0]) for r in conn.execute(
                "SELECT teacher_telegram_user_id FROM teacher_webapp_migrations WHERE migration_key=?",
                (migration_key,),
            ).fetchall()
        }

    sent = failed = skipped = 0
    for row in teachers:
        uid = int(row["telegram_user_id"])
        if uid in sent_rows:
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "💗 Главная ПРЕПОДМИН обновлена.\n"
                    "Теперь открывай её через кнопку «💗 Главная ПРЕПОДМИН» снизу."
                ),
                reply_markup=base.MAIN_KB,
            )
            with base.db() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO teacher_webapp_migrations(
                        teacher_telegram_user_id,migration_key,sent_at
                    ) VALUES(?,?,?)
                    """,
                    (uid, migration_key, datetime.utcnow().isoformat()),
                )
                conn.commit()
            sent += 1
        except Exception as exc:
            failed += 1
            print(
                f"PREPODMIN WebApp keyboard migration failed uid={uid} error={type(exc).__name__}",
                flush=True,
            )
    print(
        f"PREPODMIN WebApp keyboard migration: sent={sent} skipped={skipped} failed={failed}",
        flush=True,
    )


def _production_self_check():
    teacher_views = ("home", "students", "schedule", "homework", "payments", "attention", "tasks", "attendance", "reports", "slots")
    student_views = ("home", "homework", "schedule", "profile", "attendance", "payment")
    ok = failed = 0
    with base.db() as conn:
        teacher_rows = conn.execute(
            "SELECT telegram_user_id FROM teachers WHERE onboarding_completed_at IS NOT NULL"
        ).fetchall()
        student_rows = conn.execute(
            """
            SELECT DISTINCT telegram_user_id
            FROM student_reminder_people
            WHERE active=1 AND telegram_user_id IS NOT NULL
            """
        ).fetchall()

    for row in teacher_rows:
        uid = int(row["telegram_user_id"])
        for name in teacher_views:
            try:
                data = _view(uid, name)
                if data is None:
                    raise RuntimeError("view returned None")
                ok += 1
            except Exception as exc:
                failed += 1
                print(
                    f"PREPODMIN WEBAPP SELFTEST FAIL role=teacher uid={uid} view={name} "
                    f"error={type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                    flush=True,
                )

    for row in student_rows:
        uid = int(row["telegram_user_id"])
        for name in student_views:
            try:
                data = student_webapp.view(uid, name)
                if data is None:
                    raise RuntimeError("view returned None")
                ok += 1
            except Exception as exc:
                failed += 1
                print(
                    f"PREPODMIN WEBAPP SELFTEST FAIL role=student uid={uid} view={name} "
                    f"error={type(exc).__name__}: {exc}\n{traceback.format_exc()}",
                    flush=True,
                )
    print(f"PREPODMIN WEBAPP SELFTEST done ok={ok} failed={failed}", flush=True)


def install(app):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    base.MAIN_KB = _main_keyboard_with_webapp()
    _production_self_check()
    app.add_handler(
        MessageHandler(filters.Regex(r"^💗 Главная ПРЕПОДМИН$"), open_webapp),
        group=-41,
    )
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_action),
        group=-40,
    )
    if app.job_queue is not None:
        app.job_queue.run_once(
            _push_keyboard_migration,
            when=3,
            name="prepodmin_webapp_keyboard_migration_v2",
        )
    print(
        "PREPODMIN WebApp home installed: authenticated launcher + real dashboard + Telegram quick actions",
        flush=True,
    )
