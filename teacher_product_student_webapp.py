"""Student PREPODMIN WebApp: read-only cabinet + safe student actions."""
import hashlib
import hmac
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_student_reminders as student_reminders
import teacher_product_learning as learning
import teacher_product_cancellations as cancellations

PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
STUDENT_WEBAPP_URL = os.getenv(
    "TEACHER_PRODUCT_STUDENT_WEBAPP_URL",
    f"https://{PUBLIC_DOMAIN}/student" if PUBLIC_DOMAIN else "",
).strip()
HTML_PATH = Path(__file__).with_name("teacher_product_student_webapp.html")
STUDENT_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("💗 Мой кабинет")]],
    resize_keyboard=True,
    is_persistent=True,
)
STUDENT_WEBAPP_BUILD = "20260919-2"
_INSTALLED = False


def launch_token(uid, ttl=24 * 60 * 60):
    expires = int(time.time()) + int(ttl)
    payload = f"{int(uid)}.{expires}"
    sig = hmac.new(
        base.BOT_TOKEN.encode("utf-8"),
        ("prepodmin-student:" + payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{sig}"


def validate_launch_token(token):
    try:
        uid_text, exp_text, sig = str(token or "").split(".", 2)
        uid, expires = int(uid_text), int(exp_text)
        if expires < int(time.time()):
            return None
        payload = f"{uid}.{expires}"
        expected = hmac.new(
            base.BOT_TOKEN.encode("utf-8"),
            ("prepodmin-student:" + payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return uid if hmac.compare_digest(expected, sig) else None
    except Exception:
        return None


def _links(telegram_uid):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT p.*,t.name AS teacher_name,t.subject AS teacher_subject,
                   g.name AS group_name
            FROM student_reminder_people p
            JOIN teachers t ON t.telegram_user_id=p.teacher_id
            LEFT JOIN teacher_groups g ON g.id=p.group_id
            WHERE p.telegram_user_id=? AND p.active=1
            ORDER BY p.id
            """,
            (int(telegram_uid),),
        ).fetchall()


def _link(telegram_uid, link_id=None):
    rows = _links(telegram_uid)
    if not rows:
        return None
    if link_id is not None:
        for row in rows:
            if int(row["id"]) == int(link_id):
                return row
    return rows[0]


def _matches_event(link, event):
    if link["kind"] == "individual":
        return event["kind"] == "individual" and int(event["person_id"]) == int(link["student_id"])
    return event["kind"] == "group" and int(event["person_id"]) == int(link["group_id"])


def _event_start(uid, event):
    return datetime.combine(
        event["actual_date"],
        datetime.strptime(event["actual_time"], "%H:%M").time(),
        tzinfo=schedule.tz(uid),
    )


def _reply(link, event):
    starts_at = _event_start(int(link["teacher_id"]), event).isoformat()
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT response
            FROM student_lesson_replies
            WHERE person_id=? AND lesson_kind=? AND slot_id=?
              AND occurrence_key=? AND starts_at=?
            """,
            (
                int(link["id"]),
                event["kind"],
                int(event["slot_id"]),
                event["occurrence_key"],
                starts_at,
            ),
        ).fetchone()
    return row["response"] if row else None


def _upcoming(link, days=14):
    uid = int(link["teacher_id"])
    rows = cancellations._upcoming_occurrences(uid, days=days)
    out = []
    for event in rows:
        if not _matches_event(link, event):
            continue
        start = _event_start(uid, event)
        out.append({
            "kind": event["kind"],
            "slot_id": int(event["slot_id"]),
            "occurrence_key": event["occurrence_key"],
            "date_iso": event["actual_date"].isoformat(),
            "date": event["actual_date"].strftime("%d.%m"),
            "time": event["actual_time"],
            "label": event["name"],
            "moved": bool(event["moved"]),
            "reply": _reply(link, event),
            "starts_at": start.isoformat(),
        })
    out.sort(key=lambda x: x["starts_at"])
    return out


def _subject(link):
    if link["kind"] == "individual":
        return "individual", int(link["student_id"])
    return "group_member", int(link["id"])


def _homework(link):
    subject_kind, subject_id = _subject(link)
    today = datetime.now(schedule.tz(int(link["teacher_id"]))).date()
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT h.id,h.homework_text,h.due_date,h.target_kind,h.target_id,
                   hs.status,hs.subject_kind,hs.subject_id
            FROM teacher_homework h
            JOIN teacher_homework_status hs ON hs.assignment_id=h.id
            WHERE h.teacher_telegram_user_id=?
              AND h.active=1
              AND hs.subject_kind=?
              AND hs.subject_id=?
            ORDER BY CASE WHEN hs.status='pending' THEN 0 ELSE 1 END,
                     h.due_date,h.id
            LIMIT 60
            """,
            (int(link["teacher_id"]), subject_kind, subject_id),
        ).fetchall()
    items = []
    for r in rows:
        if r["target_kind"] == "group":
            target = link["group_name"] or "Группа"
        else:
            target = link["name"]
        items.append({
            "assignment_id": int(r["id"]),
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "text": r["homework_text"],
            "due": date.fromisoformat(r["due_date"]).strftime("%d.%m"),
            "due_iso": r["due_date"],
            "target": target,
            "status": r["status"],
            "overdue": r["status"] != "done" and r["due_date"] < today.isoformat(),
        })
    return items


def _attendance(link):
    subject_kind, subject_id = _subject(link)
    today = datetime.now(schedule.tz(int(link["teacher_id"]))).date()
    start = today - timedelta(days=29)
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT status,COUNT(*) AS c
            FROM teacher_attendance
            WHERE teacher_telegram_user_id=?
              AND subject_kind=? AND subject_id=?
              AND lesson_date>=? AND lesson_date<=?
            GROUP BY status
            """,
            (
                int(link["teacher_id"]),
                subject_kind,
                subject_id,
                start.isoformat(),
                today.isoformat(),
            ),
        ).fetchall()
    counts = {"present": 0, "absent": 0}
    for r in rows:
        if r["status"] in counts:
            counts[r["status"]] = int(r["c"] or 0)
    total = counts["present"] + counts["absent"]
    return {
        "present": counts["present"],
        "absent": counts["absent"],
        "percent": None if not total else round(100 * counts["present"] / total),
    }


def _payment(link):
    if link["kind"] != "individual" or not link["student_id"]:
        return {
            "short": "—",
            "hint": "по группе",
            "full": "Оплата для участника группы сейчас ведётся преподавателем отдельно.",
        }
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT payment_type,amount_rub,next_due_date,active,
                   lessons_total,lessons_remaining
            FROM student_payment_plans
            WHERE teacher_telegram_user_id=? AND student_id=?
            """,
            (int(link["teacher_id"]), int(link["student_id"])),
        ).fetchone()
    if not row or not int(row["active"] or 0):
        return {"short": "не настроена", "hint": "", "full": "Активная оплата пока не настроена."}
    amount = int(row["amount_rub"] or 0)
    amount_text = f"{amount:,}".replace(",", " ") + " ₽"
    if row["payment_type"] == "package":
        left = int(row["lessons_remaining"] or 0)
        total = int(row["lessons_total"] or 0)
        return {
            "short": f"{left}/{total}",
            "hint": "занятий осталось",
            "full": f"Абонемент: {amount_text}. Осталось {left} из {total} занятий.",
        }
    due = row["next_due_date"]
    if not due:
        return {"short": amount_text, "hint": "", "full": f"Сумма: {amount_text}."}
    due_date = date.fromisoformat(due)
    today = datetime.now(schedule.tz(int(link["teacher_id"]))).date()
    if due_date < today:
        short, hint = "просрочено", due_date.strftime("%d.%m")
    elif due_date == today:
        short, hint = "сегодня", amount_text
    else:
        short, hint = "до " + due_date.strftime("%d.%m"), amount_text
    return {
        "short": short,
        "hint": hint,
        "full": f"{amount_text}. Следующая дата оплаты: {due_date.strftime('%d.%m.%Y')}.",
    }


def _changes(link):
    uid = int(link["teacher_id"])
    today = datetime.now(schedule.tz(uid)).date()
    result = []
    for e in _upcoming(link, days=30):
        if e["moved"]:
            result.append({
                "title": "↪️ Занятие перенесено",
                "text": f"{e['date']} в {e['time']} · {e['label']}",
                "sort": e["date_iso"] + "T" + e["time"],
            })

    with base.db() as conn:
        if link["kind"] == "individual":
            slots = conn.execute(
                """
                SELECT id FROM schedule_slots
                WHERE teacher_telegram_user_id=? AND student_id=? AND active=1
                """,
                (uid, int(link["student_id"])),
            ).fetchall()
            kind = "individual"
        else:
            slots = conn.execute(
                """
                SELECT id FROM group_schedule_slots
                WHERE teacher_telegram_user_id=? AND group_id=? AND active=1
                """,
                (uid, int(link["group_id"])),
            ).fetchall()
            kind = "group"
        slot_ids = [int(r["id"]) for r in slots]
        if slot_ids:
            marks = ",".join("?" for _ in slot_ids)
            rows = conn.execute(
                f"""
                SELECT actual_date,actual_time
                FROM teacher_lesson_cancellations
                WHERE teacher_telegram_user_id=? AND lesson_kind=?
                  AND schedule_slot_id IN ({marks})
                  AND actual_date>=? AND actual_date<=?
                ORDER BY actual_date,actual_time
                """,
                (uid, kind, *slot_ids, (today - timedelta(days=7)).isoformat(), (today + timedelta(days=30)).isoformat()),
            ).fetchall()
            for r in rows:
                result.append({
                    "title": "❌ Занятие отменено",
                    "text": f"{date.fromisoformat(r['actual_date']).strftime('%d.%m')} в {r['actual_time']}",
                    "sort": r["actual_date"] + "T" + r["actual_time"],
                })
    result.sort(key=lambda x: x["sort"], reverse=True)
    for x in result:
        x.pop("sort", None)
    return result[:12]


def _base_payload(link):
    teacher_name = link["teacher_name"] or "Преподаватель"
    subject = link["teacher_subject"] or ""
    scope = (
        f"Группа · {link['group_name']}"
        if link["kind"] == "group"
        else "Индивидуальные занятия"
    )
    return {
        "link_id": int(link["id"]),
        "student": {"name": link["name"]},
        "teacher": {"name": teacher_name, "subject": subject},
        "profile": {
            "name": link["name"],
            "scope": scope,
            "teacher": teacher_name,
            "subject": subject,
        },
    }


def view(telegram_uid, view_name="home", link_id=None):
    link = _link(telegram_uid, link_id)
    if not link:
        return None
    base_payload = _base_payload(link)
    homework = _homework(link)
    upcoming = _upcoming(link, 14)
    attendance = _attendance(link)
    payment = _payment(link)

    if view_name == "home":
        pending = [x for x in homework if x["status"] != "done"]
        data = {
            **base_payload,
            "next_lesson": upcoming[0] if upcoming else None,
            "homework": pending,
            "attendance": attendance,
            "payment": payment,
            "changes": _changes(link),
            "counts": {
                "homework": len(pending),
                "homework_overdue": sum(1 for x in pending if x["overdue"]),
                "upcoming": len(upcoming),
            },
        }
    elif view_name == "homework":
        data = {**base_payload, "items": homework}
    elif view_name == "schedule":
        by_day = {}
        for e in upcoming:
            by_day.setdefault(e["date_iso"], []).append(e)
        days = []
        start = datetime.now(schedule.tz(int(link["teacher_id"]))).date()
        for i in range(14):
            d = start + timedelta(days=i)
            days.append({
                "date_iso": d.isoformat(),
                "label": ("Сегодня · " if i == 0 else "") + d.strftime("%d.%m"),
                "events": by_day.get(d.isoformat(), []),
            })
        data = {**base_payload, "days": days}
    elif view_name == "profile":
        data = {**base_payload, "payment": payment}
    elif view_name == "attendance":
        data = {**base_payload, **attendance}
    elif view_name == "payment":
        data = {**base_payload, **payment}
    else:
        return None
    return {"link_id": int(link["id"]), "view": view_name, "data": data}


def _notify_teacher(teacher_id, text):
    if not base.BOT_TOKEN:
        return
    try:
        body = urlencode({"chat_id": int(teacher_id), "text": text}).encode("utf-8")
        req = Request(
            f"https://api.telegram.org/bot{base.BOT_TOKEN}/sendMessage",
            data=body,
            method="POST",
        )
        with urlopen(req, timeout=5) as response:
            response.read(1)
    except Exception as exc:
        print(
            f"PREPODMIN student webapp teacher notification failed: {type(exc).__name__}",
            flush=True,
        )


def action(telegram_uid, payload):
    link = _link(telegram_uid, payload.get("link_id"))
    if not link:
        return None

    action_name = str(payload.get("action") or "")
    if action_name == "homework_done":
        try:
            aid = int(payload["assignment_id"])
            subject_kind = str(payload["subject_kind"])
            subject_id = int(payload["subject_id"])
        except Exception:
            return {"ok": False, "error": "bad_request"}
        expected_kind, expected_id = _subject(link)
        if subject_kind != expected_kind or subject_id != expected_id:
            return {"ok": False, "error": "forbidden"}
        a = learning._assignment(aid)
        if not a or not int(a["active"]):
            return {"ok": False, "error": "closed"}
        learning._sync_statuses(a)
        now = datetime.utcnow().isoformat()
        with base.db() as conn:
            cur = conn.execute(
                """
                UPDATE teacher_homework_status
                SET status='done',done_at=?,updated_at=?
                WHERE assignment_id=? AND subject_kind=? AND subject_id=?
                """,
                (now, now, aid, subject_kind, subject_id),
            )
            conn.commit()
        return {"ok": bool(cur.rowcount), "action": "homework_done"}

    if action_name == "lesson_reply":
        try:
            response = str(payload["response"])
            kind = str(payload["kind"])
            slot_id = int(payload["slot_id"])
            occurrence_key = str(payload["occurrence_key"])
        except Exception:
            return {"ok": False, "error": "bad_request"}
        if response not in {"yes", "no"} or kind not in {"individual", "group"}:
            return {"ok": False, "error": "bad_request"}
        event = cancellations._event_from_occurrence(
            int(link["teacher_id"]), kind, slot_id, occurrence_key
        )
        if (
            not event
            or not _matches_event(link, event)
            or cancellations.is_cancelled(
                int(link["teacher_id"]), kind, slot_id, occurrence_key
            )
        ):
            return {"ok": False, "error": "unavailable"}
        start = _event_start(int(link["teacher_id"]), event)
        if start <= datetime.now(schedule.tz(int(link["teacher_id"]))):
            return {"ok": False, "error": "past"}

        with base.db() as conn:
            previous = conn.execute(
                """
                SELECT response FROM student_lesson_replies
                WHERE person_id=? AND lesson_kind=? AND slot_id=?
                  AND occurrence_key=? AND starts_at=?
                """,
                (
                    int(link["id"]), kind, slot_id, occurrence_key,
                    start.isoformat(),
                ),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO student_lesson_replies(
                    person_id,lesson_kind,slot_id,occurrence_key,
                    starts_at,response,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(person_id,lesson_kind,slot_id,occurrence_key,starts_at)
                DO UPDATE SET response=excluded.response,updated_at=excluded.updated_at
                """,
                (
                    int(link["id"]), kind, slot_id, occurrence_key,
                    start.isoformat(), response, datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        if not previous or previous["response"] != response:
            label = "будет" if response == "yes" else "не сможет быть"
            _notify_teacher(
                int(link["teacher_id"]),
                f"📩 {link['name']} {label} на занятии {start.strftime('%d.%m в %H:%M')}.",
            )
        return {"ok": True, "action": "lesson_reply", "response": response}

    return {"ok": False, "error": "unknown_action"}


def _launch_markup(uid):
    token = launch_token(uid)
    sep = "&" if "?" in STUDENT_WEBAPP_URL else "?"
    url = f"{STUDENT_WEBAPP_URL}{sep}launch={token}&v={STUDENT_WEBAPP_BUILD}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "💗 Открыть мой кабинет",
            web_app=WebAppInfo(url=url),
        )
    ]])


async def open_student_webapp(update, context):
    uid = int(update.effective_user.id)
    print(
        f"PREPODMIN student cabinet tap received teacher={bool(base.teacher(uid))}",
        flush=True,
    )
    if base.teacher(uid):
        await update.message.reply_text(
            "💗 Это кнопка ученического кабинета.\n\n"
            "Твой преподавательский кабинет открывается через «💗 Главная ПРЕПОДМИН».",
            reply_markup=base.MAIN_KB,
        )
        raise ApplicationHandlerStop

    link = _link(uid)
    if not link:
        await update.message.reply_text(
            "Твой Telegram пока не привязан к ученику. Попроси преподавателя прислать ссылку подключения.",
            reply_markup=STUDENT_KB,
        )
        raise ApplicationHandlerStop

    await update.message.reply_text(
        "💗 <b>Мой кабинет</b>\n\n"
        "Здесь твоё расписание, ДЗ, посещаемость, оплата и изменения занятий.",
        parse_mode="HTML",
        reply_markup=_launch_markup(uid),
    )
    print("PREPODMIN student cabinet launcher sent=1", flush=True)
    raise ApplicationHandlerStop


async def student_cabinet_button_router(update, context):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip().replace("\ufe0f", "")
    if text not in {"💗 Мой кабинет", "Мой кабинет"}:
        return
    await open_student_webapp(update, context)


async def _push_student_cabinet(context):
    migration_key = "student-webapp-v1"
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_webapp_migrations(
                telegram_user_id INTEGER NOT NULL,
                migration_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(telegram_user_id,migration_key)
            )
            """
        )
        rows = conn.execute(
            """
            SELECT DISTINCT telegram_user_id
            FROM student_reminder_people
            WHERE active=1 AND telegram_user_id IS NOT NULL
            ORDER BY telegram_user_id
            """
        ).fetchall()
        sent = {
            int(r[0]) for r in conn.execute(
                "SELECT telegram_user_id FROM student_webapp_migrations WHERE migration_key=?",
                (migration_key,),
            ).fetchall()
        }
    ok = skipped = failed = 0
    for row in rows:
        uid = int(row["telegram_user_id"])
        if uid in sent or base.teacher(uid):
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "💗 В ПРЕПОДМИН появился личный кабинет ученика.\n\n"
                    "Теперь расписание, ДЗ, посещаемость и важные изменения можно смотреть в одном месте."
                ),
                reply_markup=STUDENT_KB,
            )
            with base.db() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO student_webapp_migrations(
                        telegram_user_id,migration_key,sent_at
                    ) VALUES(?,?,?)
                    """,
                    (uid, migration_key, datetime.utcnow().isoformat()),
                )
                conn.commit()
            ok += 1
        except Exception as exc:
            failed += 1
            print(
                f"PREPODMIN student WebApp migration failed uid={uid} error={type(exc).__name__}",
                flush=True,
            )
    print(
        f"PREPODMIN student WebApp migration: sent={ok} skipped={skipped} failed={failed}",
        flush=True,
    )


def install(app):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    # Earliest text route: the cabinet button must never be swallowed by
    # onboarding/conversation handlers on mobile Telegram.
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, student_cabinet_button_router),
        group=-100,
    )
    if app.job_queue is not None:
        app.job_queue.run_once(
            _push_student_cabinet,
            when=5,
            name="prepodmin_student_webapp_migration_v1",
        )
    print(
        "PREPODMIN student WebApp ready: home + homework + schedule + attendance + payment + replies",
        flush=True,
    )
