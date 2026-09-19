"""Pink-beige Telegram WebApp home screen for PREPODMIN."""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl

from telegram import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
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

PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
WEBAPP_URL = os.getenv(
    "TEACHER_PRODUCT_WEBAPP_URL",
    f"https://{PUBLIC_DOMAIN}/webapp" if PUBLIC_DOMAIN else "",
).strip()
MAX_AUTH_AGE = 24 * 60 * 60
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
            }))
            return
        if path in {"/", "/webapp"}:
            try:
                self._send(200, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            except Exception as exc:
                print(f"PREPODMIN WebApp html error: {type(exc).__name__}: {exc}", flush=True)
                self._send(500, b"WebApp unavailable", "text/plain; charset=utf-8")
            return
        self._send(404, _json_bytes({"ok": False, "error": "not_found"}))

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/dashboard":
            self._send(404, _json_bytes({"ok": False, "error": "not_found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 20000:
                raise ValueError("bad length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            uid = _validate_init_data(payload.get("initData", ""))
            if not uid:
                self._send(401, _json_bytes({"ok": False, "error": "unauthorized"}))
                return
            data = _dashboard(uid)
            if not data:
                self._send(403, _json_bytes({"ok": False, "error": "not_onboarded"}))
                return
            self._send(200, _json_bytes(data))
        except Exception as exc:
            print(f"PREPODMIN WebApp api error: {type(exc).__name__}: {exc}", flush=True)
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
    if WEBAPP_URL:
        rows.insert(0, [
            KeyboardButton(
                "💗 Главная ПРЕПОДМИН",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        ])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


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


def install(app):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    base.MAIN_KB = _main_keyboard_with_webapp()
    app.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_action),
        group=-40,
    )
    print(
        "PREPODMIN WebApp home installed: real dashboard + Telegram quick actions",
        flush=True,
    )
