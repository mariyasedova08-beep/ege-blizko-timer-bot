"""Private admin-only WebApp for EGE BLIZKO."""

import hashlib
import html as html_lib
import hmac
import json
import os
import re
import sqlite3
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

import run_bot_live90 as live90
import run_bot_live10 as live10
import admin_quick_tasks
import lesson_recordings

bot = live90.bot
live79 = live90.live79
live23 = live79.live23
live7 = live79.live7
live34 = live79.live34
live56 = live79.live56
live85 = live90.live85

PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
WEBAPP_URL = os.getenv(
    "EGE_ADMIN_WEBAPP_URL",
    f"https://{PUBLIC_DOMAIN}/admin-app" if PUBLIC_DOMAIN else "",
).strip()
WEBAPP_BUILD = "20260919-4"
HTML_PATH = Path(__file__).with_name("ege_admin_webapp.html")
_INSTALLED = False

_previous_get = None
_previous_post = None
_previous_markup = None
_previous_callback = None
_previous_text_router = None
_previous_start_router = None


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _admin_id():
    return bot.get_admin_id()


def _launch_token(ttl=24 * 60 * 60):
    uid = _admin_id()
    if not uid:
        return ""
    expires = int(time.time()) + int(ttl)
    payload = f"{uid}.{expires}"
    secret = os.getenv("BOT_TOKEN", "")
    signature = hmac.new(
        secret.encode("utf-8"),
        ("ege-admin-webapp:" + payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def _validate_launch_token(token):
    try:
        uid_text, exp_text, signature = str(token or "").split(".", 2)
        uid = int(uid_text)
        expires = int(exp_text)
        admin_id = _admin_id()
        if not admin_id or uid != admin_id or expires < int(time.time()):
            return None
        payload = f"{uid}.{expires}"
        secret = os.getenv("BOT_TOKEN", "")
        expected = hmac.new(
            secret.encode("utf-8"),
            ("ege-admin-webapp:" + payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return uid if hmac.compare_digest(expected, signature) else None
    except Exception:
        return None


def _events(day):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT event_type,lesson_number,event_time,topic
            FROM course_schedule
            WHERE active=1 AND event_date=?
            ORDER BY event_time
            """,
            (day.isoformat(),),
        ).fetchall()
    result = []
    for event_type, lesson_number, event_time, topic in rows:
        result.append(
            {
                "type": event_type or "event",
                "lesson_number": int(lesson_number) if lesson_number is not None else None,
                "time": str(event_time or ""),
                "topic": str(topic or ""),
            }
        )
    return result


def _task_rows(limit=100):
    live79.live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT id,task_text,start_date,reminder_time,task_kind
            FROM admin_tasks
            WHERE completed_at IS NULL
            ORDER BY
                CASE WHEN start_date=? THEN 0 ELSE 1 END,
                start_date,reminder_time,id DESC
            LIMIT ?
            """,
            (admin_quick_tasks.NO_DATE, int(limit)),
        ).fetchall()
    return rows


def _tasks_payload(limit=100):
    now = datetime.now(bot.TIMEZONE).date()
    items = []
    for task_id, text, start_date, reminder_time, kind in _task_rows(limit):
        no_date = str(start_date) == admin_quick_tasks.NO_DATE
        items.append(
            {
                "id": int(task_id),
                "text": str(text or "Задача"),
                "date": "" if no_date else str(start_date or ""),
                "time": "" if no_date else str(reminder_time or ""),
                "kind": str(kind or "task"),
                "overdue": bool(not no_date and str(start_date or "") < now.isoformat()),
                "no_date": no_date,
            }
        )
    return items


def _student_rows():
    live34.ensure_attention_tables()
    rows = live34._student_rows()
    result = []
    for row in rows:
        result.append(
            {
                "id": int(row[0]),
                "name": live34._shown_name(row),
                "email": str(row[3] or ""),
                "linked": row[5] is not None,
            }
        )
    return result


def _attention_rows():
    live34.ensure_attention_tables()
    now = datetime.now(bot.TIMEZONE)
    result = []
    for row in live34._student_rows():
        metrics = live34.attention_metrics(row, now)
        if not metrics:
            continue
        result.append(
            {
                "id": int(row[0]),
                "name": live34._shown_name(row),
                "reasons": [str(metric["label"]) for metric in metrics],
                "linked": row[5] is not None,
            }
        )
    return result


def _payments_payload():
    live85.ensure_payment_tables()
    students = live85._payment_rows()
    current = live85._current_course_period()
    completed = set(live85._completed_course_periods())
    items = []
    debt_count = 0
    due_now = 0
    for student in students:
        coverage = student["coverage"]
        missing_past = [period for period in completed if period not in coverage]
        current_paid = bool(current and current in coverage)
        if missing_past:
            debt_count += 1
        if current and not current_paid:
            due_now += 1
        paid_through = live85._paid_through(student)
        items.append(
            {
                "id": int(student["id"]),
                "name": str(student["name"] or ""),
                "monthly_amount": float(student["monthly_amount"] or 0),
                "current_paid": current_paid if current else None,
                "missing_past": len(missing_past),
                "paid_through": paid_through[1] if paid_through else "",
            }
        )
    return {
        "period": current or "",
        "students": items,
        "due_now": due_now,
        "debt_count": debt_count,
    }


def _probnik_date_key(value):
    text = str(value or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            pass
    return datetime.min


def _num(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except Exception:
        return None


def _task_scores(tasks_json):
    try:
        data = json.loads(tasks_json or "{}")
    except Exception:
        data = {}
    result = {}
    for key, value in data.items():
        score = _num(value)
        if score is not None:
            result[str(key)] = score
    return result


def _probnik_payload():
    """Beautiful per-student probnik statistics using the canonical matching logic."""
    live10.ensure_probnik_tables()
    students = live34._student_rows()

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        raw_rows = conn.execute(
            """
            SELECT id,student_name,event_name,event_date,
                   primary_score,secondary_score,tasks_json
            FROM probnik_results
            WHERE secondary_score IS NOT NULL OR primary_score IS NOT NULL
            ORDER BY id
            """
        ).fetchall()

    by_student = {int(row[0]): [] for row in students}
    unmatched = 0
    for result_id, result_name, event_name, event_date, primary, secondary, tasks_json in raw_rows:
        matched = live56.unique_probnik_student_match(result_name, students)
        if not matched:
            unmatched += 1
            continue
        sid = int(matched[0])
        by_student.setdefault(sid, []).append(
            {
                "id": int(result_id),
                "result_name": str(result_name or ""),
                "event_name": str(event_name or "Пробник"),
                "event_date": str(event_date or ""),
                "primary": _num(primary),
                "secondary": _num(secondary),
                "tasks": _task_scores(tasks_json),
            }
        )

    cards = []
    all_secondary = []
    latest_event_candidates = []

    for student in students:
        sid = int(student[0])
        results = by_student.get(sid, [])
        results.sort(key=lambda x: (_probnik_date_key(x["event_date"]), x["id"]))

        secondary = [x["secondary"] for x in results if x["secondary"] is not None]
        display_scores = [
            x["secondary"] if x["secondary"] is not None else x["primary"]
            for x in results
            if x["secondary"] is not None or x["primary"] is not None
        ]
        all_secondary.extend(secondary)

        latest = results[-1] if results else None
        if latest:
            latest_event_candidates.append(latest)

        zero_counts = {}
        for result in results:
            for task, score in result["tasks"].items():
                try:
                    task_no = int(task)
                except Exception:
                    continue
                if 1 <= task_no <= 34 and score == 0:
                    zero_counts[task_no] = zero_counts.get(task_no, 0) + 1
        weak = sorted(zero_counts.items(), key=lambda item: (-item[1], item[0]))[:5]

        delta = None
        if len(secondary) >= 2:
            delta = round(secondary[-1] - secondary[0], 1)

        average = round(sum(secondary) / len(secondary), 1) if secondary else None
        latest_score = None
        latest_score_kind = ""
        if latest:
            if latest["secondary"] is not None:
                latest_score = latest["secondary"]
                latest_score_kind = "вторичный"
            elif latest["primary"] is not None:
                latest_score = latest["primary"]
                latest_score_kind = "первичный"

        history = []
        for result in reversed(results[-6:]):
            score = result["secondary"] if result["secondary"] is not None else result["primary"]
            history.append(
                {
                    "event": result["event_name"],
                    "date": result["event_date"],
                    "score": score,
                    "score_kind": "secondary" if result["secondary"] is not None else "primary",
                }
            )

        cards.append(
            {
                "student_id": sid,
                "name": live34._shown_name(student),
                "results_count": len(results),
                "latest_score": latest_score,
                "latest_score_kind": latest_score_kind,
                "latest_event": latest["event_name"] if latest else "",
                "latest_date": latest["event_date"] if latest else "",
                "average": average,
                "delta": delta,
                "weak_tasks": [
                    {"task": task, "misses": misses}
                    for task, misses in weak
                ],
                "history": history,
            }
        )

    cards.sort(
        key=lambda x: (
            x["results_count"] == 0,
            -(x["latest_score"] if x["latest_score"] is not None else -1),
            x["name"].casefold(),
        )
    )

    # Latest probnik summary across all matched students.
    latest_key = None
    latest_name = ""
    latest_date = ""
    if latest_event_candidates:
        latest = max(
            latest_event_candidates,
            key=lambda x: (_probnik_date_key(x["event_date"]), x["id"]),
        )
        latest_name = latest["event_name"]
        latest_date = latest["event_date"]
        latest_key = (latest_name, latest_date)

    latest_scores = []
    latest_task_stats = {}
    if latest_key:
        for results in by_student.values():
            for result in results:
                if (result["event_name"], result["event_date"]) != latest_key:
                    continue
                if result["secondary"] is not None:
                    latest_scores.append(result["secondary"])
                for task, score in result["tasks"].items():
                    try:
                        task_no = int(task)
                    except Exception:
                        continue
                    if not (1 <= task_no <= 34):
                        continue
                    entry = latest_task_stats.setdefault(task_no, {"zeros": 0, "answered": 0})
                    entry["answered"] += 1
                    if score == 0:
                        entry["zeros"] += 1

    weak_group = []
    for task, info in latest_task_stats.items():
        if not info["answered"]:
            continue
        pct = round(100 * info["zeros"] / info["answered"])
        weak_group.append(
            {
                "task": task,
                "zeros": info["zeros"],
                "answered": info["answered"],
                "pct": pct,
            }
        )
    weak_group.sort(key=lambda x: (-x["pct"], -x["zeros"], x["task"]))

    return {
        "latest": {
            "name": latest_name,
            "date": latest_date,
            "written": len(latest_scores),
            "average": round(sum(latest_scores) / len(latest_scores), 1) if latest_scores else None,
            "best": max(latest_scores) if latest_scores else None,
        },
        "overall": {
            "students_with_results": sum(1 for card in cards if card["results_count"]),
            "students_total": len(cards),
            "results_total": sum(card["results_count"] for card in cards),
            "average_all": round(sum(all_secondary) / len(all_secondary), 1) if all_secondary else None,
            "unmatched_results": unmatched,
        },
        "weak_group": weak_group[:5],
        "students": cards,
    }


_CORE_COURSE_CACHE = {"fetched_at": 0.0, "items": []}


def _core_course_ids():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return [
            str(row[0] or "").strip()
            for row in conn.execute(
                """
                SELECT DISTINCT course_id
                FROM students
                WHERE active=1 AND coalesce(course_id,'')!=''
                """
            ).fetchall()
            if str(row[0] or "").strip()
        ]


def _final_homework_catalog(force=False):
    now = time.time()
    if (
        not force
        and _CORE_COURSE_CACHE["items"]
        and now - float(_CORE_COURSE_CACHE["fetched_at"] or 0) < 600
    ):
        return list(_CORE_COURSE_CACHE["items"])

    items = []
    seen = set()
    for course_id in _core_course_ids():
        try:
            req = Request(
                f"https://coreapp.ai/app/player/course/{course_id}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urlopen(req, timeout=12) as resp:
                body = resp.read(1000000).decode("utf-8", errors="ignore")
        except Exception as exc:
            print(
                f"EGE final homework catalog fetch failed course={course_id}: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            continue

        # CORE renders published course lessons in anchor blocks. We keep only
        # explicit final-homework / examination lessons, so ordinary homework
        # never leaks into this statistic.
        lower_body = body.casefold().replace("ё", "е")
        needle = "итоговая домашняя работа"
        for title_match in re.finditer(re.escape(needle), lower_body):
            pos = title_match.start()

            # The lesson link is immediately before the visible title in CORE's
            # rendered course HTML. Take the closest lesson id, not a module id.
            before = body[max(0, pos - 2500):pos]
            lesson_ids = re.findall(
                r'(?:/|%2F)lesson(?:/|%2F)([0-9a-fA-F]{12,})',
                before,
                flags=re.I,
            )
            if not lesson_ids:
                # Fallback: CORE sometimes emits escaped JSON-style URLs.
                lesson_ids = re.findall(
                    r'lesson[\\/"%2F:]+([0-9a-fA-F]{12,})',
                    before,
                    flags=re.I,
                )
            if not lesson_ids:
                continue
            lesson_id = lesson_ids[-1]

            neighborhood = body[max(0, pos - 800):min(len(body), pos + 1800)]
            title_candidates = re.findall(
                r'>([^<>]*ИТОГОВАЯ\s+ДОМАШНЯЯ\s+РАБОТА[^<>]*)<',
                neighborhood,
                flags=re.I,
            )
            title = (
                html_lib.unescape(title_candidates[0]).strip()
                if title_candidates
                else "Итоговая домашняя работа"
            )
            title = re.sub(r"\s+", " ", title).strip()

            key = (course_id, lesson_id)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "course_id": course_id,
                    "lesson_id": lesson_id,
                    "title": title,
                }
            )

    _CORE_COURSE_CACHE["fetched_at"] = now
    _CORE_COURSE_CACHE["items"] = list(items)
    return items


def _final_homework_payload():
    catalog = _final_homework_catalog()
    students = live34._student_rows()

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        submissions = conn.execute(
            """
            SELECT user_id,lower(user_email),lesson_id,lesson_name,
                   correct_count,total_count,received_at
            FROM homework_submissions
            """
        ).fetchall()

    student_by_id = {int(row[0]): row for row in students}
    identity_by_student = {
        int(row[0]): (
            str(row[4] or "").strip(),
            str(row[3] or "").strip().casefold(),
        )
        for row in students
    }

    works = []
    student_done = {int(row[0]): set() for row in students}

    for item in catalog:
        lesson_id = str(item["lesson_id"])
        title_norm = re.sub(r"\s+", " ", str(item["title"]).casefold().replace("ё", "е")).strip()
        relevant = []
        for row in submissions:
            uid, email, sub_lesson_id, sub_name, correct, total, received_at = row
            sub_id = str(sub_lesson_id or "").strip()
            sub_norm = re.sub(
                r"\s+", " ", str(sub_name or "").casefold().replace("ё", "е")
            ).strip()
            if sub_id == lesson_id or (
                title_norm
                and sub_norm
                and (sub_norm == title_norm or title_norm in sub_norm or sub_norm in title_norm)
            ):
                relevant.append(row)

        done_student_ids = set()
        scores = []
        latest_at = ""
        for uid, email, _sub_lesson_id, _sub_name, correct, total, received_at in relevant:
            uid = str(uid or "").strip()
            email_norm = str(email or "").strip().casefold()
            for sid, (core_id, student_email) in identity_by_student.items():
                if (core_id and uid and core_id == uid) or (
                    student_email and email_norm and student_email == email_norm
                ):
                    done_student_ids.add(sid)
                    student_done[sid].add(lesson_id)
                    break
            try:
                correct_n = float(str(correct).replace(",", "."))
                total_n = float(str(total).replace(",", "."))
                if total_n > 0:
                    scores.append(round(correct_n * 100 / total_n, 1))
            except Exception:
                pass
            if received_at and str(received_at) > latest_at:
                latest_at = str(received_at)

        missing_ids = [
            int(row[0]) for row in students if int(row[0]) not in done_student_ids
        ]
        works.append(
            {
                **item,
                "done": len(done_student_ids),
                "missing": len(missing_ids),
                "total": len(students),
                "started": bool(relevant),
                "average_accuracy": (
                    round(sum(scores) / len(scores), 1) if scores else None
                ),
                "missing_names": [
                    live34._shown_name(student_by_id[sid]) for sid in missing_ids
                ],
                "latest_submission_at": latest_at,
            }
        )

    per_student = []
    total_works = len(catalog)
    for student in students:
        sid = int(student[0])
        done_count = len(student_done.get(sid, set()))
        per_student.append(
            {
                "student_id": sid,
                "name": live34._shown_name(student),
                "done": done_count,
                "total": total_works,
                "missing": max(0, total_works - done_count),
                "percent": round(100 * done_count / total_works) if total_works else 0,
                "items": [
                    {
                        "lesson_id": item["lesson_id"],
                        "title": item["title"],
                        "done": item["lesson_id"] in student_done.get(sid, set()),
                    }
                    for item in catalog
                ],
            }
        )
    per_student.sort(key=lambda x: (x["percent"], x["name"].casefold()))

    started = [w for w in works if w["started"]]
    return {
        "catalog_count": len(catalog),
        "students_total": len(students),
        "started_count": len(started),
        "completed_submissions": sum(w["done"] for w in works),
        "works": works,
        "students": per_student,
    }


def _recordings_payload():
    lesson_recordings.ensure_tables()
    rows = lesson_recordings._saved_rows()
    return [
        {
            "lesson_number": int(number),
            "url": str(url or ""),
            "updated_at": str(updated_at or ""),
        }
        for number, url, updated_at in rows[:40]
    ]


def _home():
    today = datetime.now(bot.TIMEZONE).date()
    tomorrow = today + timedelta(days=1)
    students = _student_rows()
    attention = _attention_rows()
    tasks = _tasks_payload(60)
    payments = _payments_payload()
    recordings = _recordings_payload()
    probniki = _probnik_payload()
    final_hw = _final_homework_payload()

    lesson_number = bot.get_course_lesson_number(today)
    percent = round(100 * lesson_number / bot.TOTAL_LESSONS) if bot.TOTAL_LESSONS else 0
    return {
        "date": today.strftime("%d.%m.%Y"),
        "weekday": ("Пн","Вт","Ср","Чт","Пт","Сб","Вс")[today.weekday()],
        "course": {
            "days_left": bot.days_left(),
            "lesson_number": lesson_number,
            "total_lessons": bot.TOTAL_LESSONS,
            "percent": percent,
        },
        "counts": {
            "today": len(_events(today)),
            "tasks": len(tasks),
            "attention": len(attention),
            "students": len(students),
            "linked": sum(1 for s in students if s["linked"]),
            "payments_due": payments["due_now"],
            "recordings": len(recordings),
            "probniki_students": probniki["overall"]["students_with_results"],
            "probniki_results": probniki["overall"]["results_total"],
            "final_homework": final_hw["catalog_count"],
            "final_homework_started": final_hw["started_count"],
        },
        "today_events": _events(today),
        "tomorrow_events": _events(tomorrow),
        "tasks": tasks[:6],
        "attention": attention[:4],
        "probniki": {
            "latest": probniki["latest"],
            "overall": probniki["overall"],
            "weak_group": probniki["weak_group"],
        },
        "final_homework": {
            "catalog_count": final_hw["catalog_count"],
            "started_count": final_hw["started_count"],
            "completed_submissions": final_hw["completed_submissions"],
            "students_total": final_hw["students_total"],
            "works": final_hw["works"][:3],
        },
    }


def _day_view(offset):
    day = datetime.now(bot.TIMEZONE).date() + timedelta(days=int(offset))
    tasks = []
    for item in _tasks_payload(100):
        if item["no_date"]:
            if offset == 0:
                tasks.append(item)
            continue
        if item["date"] <= day.isoformat():
            tasks.append(item)
    return {
        "date": day.strftime("%d.%m.%Y"),
        "weekday": ("Пн","Вт","Ср","Чт","Пт","Сб","Вс")[day.weekday()],
        "events": _events(day),
        "tasks": tasks[:40],
    }


def _view(name):
    if name == "home":
        return _home()
    if name == "today":
        return _day_view(0)
    if name == "tomorrow":
        return _day_view(1)
    if name == "tasks":
        return {"items": _tasks_payload(120)}
    if name == "students":
        rows = _student_rows()
        return {
            "items": rows,
            "total": len(rows),
            "linked": sum(1 for x in rows if x["linked"]),
        }
    if name == "attention":
        return {"items": _attention_rows()}
    if name == "payments":
        return _payments_payload()
    if name == "recordings":
        return {"items": _recordings_payload()}
    if name == "probniki":
        return _probnik_payload()
    if name == "final_homework":
        return _final_homework_payload()
    return None


def _action(payload):
    action_name = str(payload.get("action") or "")
    if action_name != "task_done":
        return {"ok": False, "error": "unknown_action"}
    try:
        task_id = int(payload.get("task_id"))
    except Exception:
        return {"ok": False, "error": "bad_task_id"}

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT task_text,completed_at FROM admin_tasks WHERE id=? LIMIT 1",
            (task_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        if row[1]:
            return {"ok": True, "already_done": True, "task_id": task_id}
        conn.execute(
            """
            UPDATE admin_tasks
            SET completed_at=?
            WHERE id=? AND completed_at IS NULL
            """,
            (datetime.now(bot.TIMEZONE).isoformat(), task_id),
        )
        conn.commit()
    print(f"EGE admin WebApp task completed task_id={task_id}", flush=True)
    return {"ok": True, "task_id": task_id, "title": str(row[0] or "")}


def _http_get(self):
    parsed = urlparse(self.path)
    if parsed.path == "/admin-app":
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
            print(f"EGE admin WebApp html error: {type(exc).__name__}: {exc}", flush=True)
            self._send_json(500, {"ok": False, "error": "webapp_unavailable"})
        return
    return _previous_get(self)


def _http_post(self):
    parsed = urlparse(self.path)
    if parsed.path not in {"/admin-app/api", "/admin-app/action", "/admin-app/client-error"}:
        return _previous_post(self)

    try:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 30000:
            raise ValueError("bad length")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))

        if parsed.path == "/admin-app/client-error":
            print(
                "EGE ADMIN WEBAPP CLIENT ERROR "
                f"where={str(payload.get('where') or '')[:100]} "
                f"message={str(payload.get('message') or '')[:500]}",
                flush=True,
            )
            self._send_json(200, {"ok": True})
            return

        uid = _validate_launch_token(payload.get("launch"))
        if not uid or uid != _admin_id():
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        if parsed.path == "/admin-app/action":
            data = _action(payload)
            self._send_json(200 if data.get("ok") else 400, data)
            return

        view_name = str(payload.get("view") or "home")
        data = _view(view_name)
        if data is None:
            self._send_json(404, {"ok": False, "error": "view_not_found"})
            return
        print(f"EGE admin WebApp request view={view_name}", flush=True)
        self._send_json(200, {"ok": True, "view": view_name, "data": data})
    except Exception as exc:
        print(
            f"EGE admin WebApp api error: {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            flush=True,
        )
        self._send_json(400, {"ok": False, "error": "bad_request"})


def _launcher_markup():
    token = _launch_token()
    sep = "&" if "?" in WEBAPP_URL else "?"
    url = f"{WEBAPP_URL}{sep}launch={token}&v={WEBAPP_BUILD}"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("💗 Открыть ЕГЭ БЛИЗКО", url=url)]]
    )


def _admin_keyboard():
    current = getattr(live23, "ADMIN_KEYBOARD", None)
    rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []
    rows = [
        [button for button in row if getattr(button, "text", button) != "💗 ЕГЭ БЛИЗКО"]
        for row in rows
    ]
    rows = [row for row in rows if row]
    rows.insert(0, [KeyboardButton("💗 ЕГЭ БЛИЗКО")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


async def _open_app_message(message):
    await message.reply_text(
        "💗 <b>ЕГЭ БЛИЗКО</b>\n\n"
        "Твоя красивая админская главная: расписание, задачи, ученики, "
        "зона внимания, оплаты и записи уроков — в одном месте.",
        parse_mode="HTML",
        reply_markup=_launcher_markup(),
    )


async def _text_router(update, context):
    if (
        update.effective_chat
        and update.effective_chat.type == "private"
        and bot.user_is_admin(update)
        and update.message
        and update.message.text == "💗 ЕГЭ БЛИЗКО"
    ):
        await _open_app_message(update.message)
        return
    return await _previous_text_router(update, context)


async def _start_router(update, context):
    if (
        update.effective_chat
        and update.effective_chat.type == "private"
        and bot.user_is_admin(update)
        and not context.args
    ):
        await update.message.reply_text(
            "Привет, Маша 💗",
            reply_markup=live23.ADMIN_KEYBOARD,
        )
        await _open_app_message(update.message)
        return
    return await _previous_start_router(update, context)


def _cabinet_markup():
    base = _previous_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "web_app", None)
        for row in rows
        for button in row
    ):
        rows.insert(
            0,
            [InlineKeyboardButton(
                "💗 Открыть красивую главную",
                url=f"{WEBAPP_URL}?launch={_launch_token()}&v={WEBAPP_BUILD}"
            )],
        )
    return InlineKeyboardMarkup(rows)


async def _cabinet_callback(update, context):
    return await _previous_callback(update, context)


_admin_launch_push_done = False


async def _push_admin_launch_once(context):
    global _admin_launch_push_done
    if _admin_launch_push_done:
        return
    _admin_launch_push_done = True
    admin_id = _admin_id()
    if not admin_id:
        return
    try:
        await context.bot.send_message(
            chat_id=int(admin_id),
            text=(
                "💗 <b>ЕГЭ БЛИЗКО — новая ссылка</b>\n\n"
                "На телефоне открывай приложение этой кнопкой. "
                "Она использует обычную защищённую ссылку и не зависит от Telegram WebApp-кнопки."
            ),
            parse_mode="HTML",
            reply_markup=_launcher_markup(),
        )
        print("EGE admin WebApp mobile launcher pushed=1", flush=True)
    except Exception as exc:
        print(
            f"EGE admin WebApp mobile launcher push failed: {type(exc).__name__}: {exc}",
            flush=True,
        )


def install():
    global _INSTALLED
    global _previous_get, _previous_post
    global _previous_markup, _previous_callback
    global _previous_text_router, _previous_start_router

    if _INSTALLED:
        return
    _INSTALLED = True

    _previous_get = bot.CoreAppWebhookHandler.do_GET
    _previous_post = bot.CoreAppWebhookHandler.do_POST
    bot.CoreAppWebhookHandler.do_GET = _http_get
    bot.CoreAppWebhookHandler.do_POST = _http_post

    _previous_markup = live23.cabinet_markup
    _previous_callback = live23.cabinet_callback
    live23.cabinet_markup = _cabinet_markup
    live23.cabinet_callback = _cabinet_callback

    live23.ADMIN_KEYBOARD = _admin_keyboard()

    _previous_text_router = live7.student_text_router
    _previous_start_router = live7.start_router
    live7.student_text_router = _text_router
    live7.start_router = _start_router

    try:
        final_check = _final_homework_payload()
        print(
            "EGE final homework check: "
            f"catalog={final_check['catalog_count']} "
            f"started={final_check['started_count']} "
            f"students={final_check['students_total']} "
            f"submissions={final_check['completed_submissions']}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"EGE final homework check failed: {type(exc).__name__}: {exc}",
            flush=True,
        )

    try:
        check = _probnik_payload()
        print(
            "EGE admin WebApp probnik check: "
            f"students={check['overall']['students_total']} "
            f"with_results={check['overall']['students_with_results']} "
            f"results={check['overall']['results_total']} "
            f"unmatched={check['overall']['unmatched_results']}",
            flush=True,
        )

    except Exception as exc:
        print(
            f"EGE admin WebApp probnik check failed: {type(exc).__name__}: {exc}\n"
            + traceback.format_exc(),
            flush=True,
        )

    # Reuse the existing repeating scheduler chain to send Maria one fresh
    # mobile-safe launcher after deployment.
    original_tick = live7.friday_trivial_tick

    async def tick_with_admin_webapp_push(context):
        await _push_admin_launch_once(context)
        return await original_tick(context)

    live7.friday_trivial_tick = tick_with_admin_webapp_push

    print(
        f"EGE admin WebApp ready: admin-only url={WEBAPP_URL or 'missing'} launcher=url-button",
        flush=True,
    )
