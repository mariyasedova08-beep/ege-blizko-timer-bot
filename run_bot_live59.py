import json
import os
import sqlite3
import hmac
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import run_bot_live58

live58 = run_bot_live58
live56 = live58.live56
live55 = live58.live55
live54 = live55.live54
live52 = live55.live52
live51 = live55.live51
live50 = live55.live50
live49 = live55.live49
live48 = live55.live48
live46 = live55.live46
live44 = live55.live44
live43 = live55.live43
live41 = live55.live41
live39 = live55.live39
live37 = live55.live37
live35 = live55.live35
live34 = live55.live34
live31 = live55.live31
live24 = live55.live24
live17 = live55.live17
bot = live55.bot

WEBHOOK_PATHS = {
    "/coreapp/homework-submitted",
    "/coreapp/lesson-completed",
    "/coreapp/lesson-complete",
    "/coreapp/lesson-finished",
    "/coreapp/student-joined",
    "/coreapp/student-removed",
}

FIELD_ALIASES = {
    "user_id": ("user_id", "userId", "student_id", "studentId"),
    "user_email": ("user_email", "userEmail", "email"),
    "user_name": ("user_name", "userName", "name", "student_name", "studentName"),
    "course_id": ("course_id", "courseId"),
    "lesson_id": ("lesson_id", "lessonId"),
    "lesson_name": ("lesson_name", "lessonName"),
    "correct_count": ("correct_count", "correctCount"),
    "total_count": ("total_count", "totalCount"),
}


def ensure_coreapp_webhook_audit_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coreapp_webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                http_status INTEGER NOT NULL,
                content_type TEXT,
                has_user_id INTEGER NOT NULL DEFAULT 0,
                has_user_email INTEGER NOT NULL DEFAULT 0,
                has_lesson_id INTEGER NOT NULL DEFAULT 0,
                has_lesson_name INTEGER NOT NULL DEFAULT 0,
                saved INTEGER NOT NULL DEFAULT 0,
                duplicate INTEGER NOT NULL DEFAULT 0,
                error_code TEXT
            )
            """
        )
        conn.commit()


def _scalar(value):
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value).strip()
    return ""


def _candidate_dicts(payload):
    if not isinstance(payload, dict):
        return []
    result = [payload]
    for key in ("data", "payload", "event", "body"):
        value = payload.get(key)
        if isinstance(value, dict):
            result.append(value)
    return result


def normalize_coreapp_payload(payload, query_values=None):
    candidates = _candidate_dicts(payload)
    query_values = query_values or {}
    normalized = {}

    for canonical, aliases in FIELD_ALIASES.items():
        found = ""
        for source in candidates:
            for alias in aliases:
                if alias in source:
                    found = _scalar(source.get(alias))
                    if found:
                        break
            if found:
                break
        if not found:
            for alias in aliases:
                values = query_values.get(alias)
                if values:
                    found = _scalar(values[0])
                    if found:
                        break
        normalized[canonical] = found

    for source in candidates:
        student = source.get("student") or source.get("user")
        if isinstance(student, dict):
            normalized["user_id"] = normalized["user_id"] or _scalar(student.get("id") or student.get("user_id"))
            normalized["user_email"] = normalized["user_email"] or _scalar(student.get("email") or student.get("user_email"))
            normalized["user_name"] = normalized["user_name"] or _scalar(student.get("name") or student.get("user_name"))
        lesson = source.get("lesson")
        if isinstance(lesson, dict):
            normalized["lesson_id"] = normalized["lesson_id"] or _scalar(lesson.get("id") or lesson.get("lesson_id"))
            normalized["lesson_name"] = normalized["lesson_name"] or _scalar(lesson.get("name") or lesson.get("title") or lesson.get("lesson_name"))

    normalized["user_email"] = bot.normalize_email(normalized.get("user_email"))
    return normalized


def _existing_submission(conn, payload):
    user_id = str(payload.get("user_id") or "").strip()
    email = bot.normalize_email(payload.get("user_email"))
    lesson_id = str(payload.get("lesson_id") or "").strip()
    lesson_name = str(payload.get("lesson_name") or "").strip()

    identity_sql = []
    identity_args = []
    if user_id:
        identity_sql.append("user_id = ?")
        identity_args.append(user_id)
    if email:
        identity_sql.append("lower(user_email) = lower(?)")
        identity_args.append(email)
    if not identity_sql:
        return None

    lesson_sql = []
    lesson_args = []
    if lesson_id:
        lesson_sql.append("lesson_id = ?")
        lesson_args.append(lesson_id)
    if lesson_name:
        lesson_sql.append("lesson_name = ?")
        lesson_args.append(lesson_name)
    if not lesson_sql:
        return None

    sql = (
        "SELECT id FROM homework_submissions WHERE ("
        + " OR ".join(identity_sql)
        + ") AND ("
        + " OR ".join(lesson_sql)
        + ") ORDER BY id DESC LIMIT 1"
    )
    return conn.execute(sql, tuple(identity_args + lesson_args)).fetchone()


def save_live_coreapp_completion(payload):
    user_id = str(payload.get("user_id") or "").strip()
    email = bot.normalize_email(payload.get("user_email"))
    lesson_id = str(payload.get("lesson_id") or "").strip()
    lesson_name = str(payload.get("lesson_name") or "").strip()
    if not (user_id or email):
        raise ValueError("missing_student_identity")
    if not (lesson_id or lesson_name):
        raise ValueError("missing_lesson_identity")

    payload = dict(payload)
    payload["source"] = "coreapp_webhook_live"
    bot.upsert_student(payload, active=1)
    now = datetime.now(bot.TIMEZONE).isoformat()

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        existing = _existing_submission(conn, payload)
        if existing:
            conn.execute(
                """
                UPDATE homework_submissions
                SET received_at = ?,
                    user_id = CASE WHEN ? != '' THEN ? ELSE user_id END,
                    user_email = CASE WHEN ? != '' THEN ? ELSE user_email END,
                    user_name = CASE WHEN ? != '' THEN ? ELSE user_name END,
                    course_id = CASE WHEN ? != '' THEN ? ELSE course_id END,
                    lesson_id = CASE WHEN ? != '' THEN ? ELSE lesson_id END,
                    lesson_name = CASE WHEN ? != '' THEN ? ELSE lesson_name END,
                    correct_count = CASE WHEN ? != '' THEN ? ELSE correct_count END,
                    total_count = CASE WHEN ? != '' THEN ? ELSE total_count END,
                    raw_json = ?
                WHERE id = ?
                """,
                (
                    now,
                    user_id, user_id,
                    email, email,
                    str(payload.get("user_name") or ""), str(payload.get("user_name") or ""),
                    str(payload.get("course_id") or ""), str(payload.get("course_id") or ""),
                    lesson_id, lesson_id,
                    lesson_name, lesson_name,
                    str(payload.get("correct_count") or ""), str(payload.get("correct_count") or ""),
                    str(payload.get("total_count") or ""), str(payload.get("total_count") or ""),
                    json.dumps(payload, ensure_ascii=False),
                    int(existing[0]),
                ),
            )
            conn.commit()
            return False, True

        conn.execute(
            """
            INSERT INTO homework_submissions (
                received_at, user_id, user_email, user_name, course_id,
                lesson_id, lesson_name, correct_count, total_count, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                user_id,
                email,
                str(payload.get("user_name") or ""),
                str(payload.get("course_id") or ""),
                lesson_id,
                lesson_name,
                str(payload.get("correct_count") or ""),
                str(payload.get("total_count") or ""),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        conn.commit()
    return True, False


def _record_webhook_event(path, method, status, content_type, payload=None, saved=False, duplicate=False, error_code=None):
    payload = payload or {}
    try:
        ensure_coreapp_webhook_audit_table()
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO coreapp_webhook_events (
                    received_at, path, method, http_status, content_type,
                    has_user_id, has_user_email, has_lesson_id, has_lesson_name,
                    saved, duplicate, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(bot.TIMEZONE).isoformat(),
                    path,
                    method,
                    int(status),
                    str(content_type or "")[:120],
                    1 if payload.get("user_id") else 0,
                    1 if payload.get("user_email") else 0,
                    1 if payload.get("lesson_id") else 0,
                    1 if payload.get("lesson_name") else 0,
                    1 if saved else 0,
                    1 if duplicate else 0,
                    str(error_code or "")[:120],
                ),
            )
            conn.commit()
    except Exception as exc:
        print("CoreApp audit write error:", type(exc).__name__)


class FlexibleCoreAppWebhookHandler(bot.CoreAppWebhookHandler):
    def _authorized(self, parsed):
        expected = os.getenv("COREAPP_WEBHOOK_SECRET", "")
        supplied = parse_qs(parsed.query).get("secret", [""])[0]
        return bool(expected and hmac.compare_digest(str(supplied), str(expected)))

    def _read_payload(self, parsed):
        query_values = parse_qs(parsed.query, keep_blank_values=True)
        content_type = str(self.headers.get("Content-Type", "") or "")
        length_text = str(self.headers.get("Content-Length", "0") or "0")
        try:
            length = max(0, min(int(length_text), 1_000_000))
        except Exception:
            length = 0
        raw = self.rfile.read(length) if length else b""
        body = {}
        if raw:
            text = raw.decode("utf-8", errors="strict")
            if "application/x-www-form-urlencoded" in content_type:
                form = parse_qs(text, keep_blank_values=True)
                body = {k: (v[0] if v else "") for k, v in form.items()}
            else:
                try:
                    body = json.loads(text)
                except json.JSONDecodeError:
                    form = parse_qs(text, keep_blank_values=True)
                    if form:
                        body = {k: (v[0] if v else "") for k, v in form.items()}
                    else:
                        raise
        return normalize_coreapp_payload(body, query_values), content_type

    def _process(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        if path not in WEBHOOK_PATHS:
            return self._send_json(404, {"ok": False, "error": "not_found"})
        if not self._authorized(parsed):
            _record_webhook_event(path, method, 401, self.headers.get("Content-Type"), error_code="unauthorized")
            return self._send_json(401, {"ok": False, "error": "unauthorized"})

        try:
            payload, content_type = self._read_payload(parsed)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            _record_webhook_event(path, method, 400, self.headers.get("Content-Type"), error_code="invalid_body")
            return self._send_json(400, {"ok": False, "error": "invalid_body"})

        try:
            saved = False
            duplicate = False
            if path in {"/coreapp/homework-submitted", "/coreapp/lesson-completed", "/coreapp/lesson-complete", "/coreapp/lesson-finished"}:
                saved, duplicate = save_live_coreapp_completion(payload)
            elif path == "/coreapp/student-joined":
                if not (payload.get("user_id") or payload.get("user_email")):
                    raise ValueError("missing_student_identity")
                bot.upsert_student(payload, active=1)
                saved = True
            else:
                if not (payload.get("user_id") or payload.get("user_email")):
                    raise ValueError("missing_student_identity")
                bot.upsert_student(payload, active=0)
                saved = True
        except ValueError as exc:
            code = str(exc)
            _record_webhook_event(path, method, 422, content_type, payload, error_code=code)
            print(f"CoreApp webhook rejected: path={path} reason={code}")
            return self._send_json(422, {"ok": False, "error": code})
        except Exception as exc:
            _record_webhook_event(path, method, 500, content_type, payload, error_code=type(exc).__name__)
            print(f"CoreApp webhook storage error: path={path} type={type(exc).__name__}")
            return self._send_json(500, {"ok": False, "error": "storage_error"})

        _record_webhook_event(path, method, 200, content_type, payload, saved=saved, duplicate=duplicate)
        print(
            "CoreApp webhook accepted: "
            f"path={path} method={method} saved={1 if saved else 0} duplicate={1 if duplicate else 0} "
            f"has_user={1 if (payload.get('user_id') or payload.get('user_email')) else 0} "
            f"has_lesson={1 if (payload.get('lesson_id') or payload.get('lesson_name')) else 0}"
        )
        return self._send_json(200, {"ok": True, "saved": bool(saved), "duplicate": bool(duplicate)})

    def do_POST(self):
        self._process("POST")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._send_json(200, {"ok": True, "service": "ege-blizko-timer-bot"})
        if parsed.path in WEBHOOK_PATHS:
            return self._process("GET")
        return self._send_json(404, {"ok": False, "error": "not_found"})


bot.CoreAppWebhookHandler = FlexibleCoreAppWebhookHandler


if __name__ == "__main__":
    ensure_coreapp_webhook_audit_table()
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
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live56.log_probnik_cabinet_audit()
    print("CoreApp live sync receiver v2 ready")
    live24.main()
