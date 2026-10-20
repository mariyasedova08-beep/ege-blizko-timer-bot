"""Read live PREPODMIN group records for a coherent Telegram Mini App workspace.

No table copies or migrations. Authorized teacher ID comes from validated WebApp
initData / launch token in teacher_product_webapp, never from client-supplied data.
"""
from datetime import datetime, timedelta

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_learning as learning
import teacher_product_schedule as schedule
import teacher_product_today as today


def _payments():
    # Lazy import avoids circular dependency: group_payments patches webapp.
    import teacher_product_group_payments as payments
    return payments


def _owned(uid, gid):
    teacher = base.teacher(int(uid))
    if not teacher or not teacher["onboarding_completed_at"]:
        return None
    return groups.get_group(int(uid), int(gid))


def _sessions(uid, gid, now, offset_start, offset_end):
    sessions = []
    for offset in range(offset_start, offset_end):
        day = now + timedelta(days=offset)
        for item in today._group_today(uid, day):
            if int(item["group_id"]) == int(gid):
                sessions.append({
                    "slot_id": int(item["slot_id"]),
                    "date": day.isoformat(),
                    "date_label": day.strftime("%d.%m"),
                    "time": item["time"],
                    "moved": bool(item.get("moved")),
                })
    return sorted(sessions, key=lambda x: (x["date"], x["time"]))


def _homework(uid, gid):
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT h.id,h.homework_text,h.due_date,
                   SUM(CASE WHEN hs.status='done' THEN 1 ELSE 0 END) AS done,
                   COUNT(hs.subject_id) AS total
            FROM teacher_homework h
            LEFT JOIN teacher_homework_status hs
              ON hs.assignment_id=h.id AND hs.subject_kind='group_member'
            WHERE h.teacher_telegram_user_id=? AND h.target_kind='group'
              AND h.target_id=? AND h.active=1
            GROUP BY h.id,h.homework_text,h.due_date
            ORDER BY h.due_date DESC,h.id DESC LIMIT 20
            """,
            (int(uid), int(gid)),
        ).fetchall()
    return [{
        "id": int(r["id"]),
        "text": r["homework_text"],
        "due": r["due_date"],
        "done": int(r["done"] or 0),
        "total": int(r["total"] or 0),
    } for r in rows]


def _payment(uid, pid):
    pay = _payments()
    plan = pay._plan(uid, pid)
    label, level = pay._status(uid, plan)
    return {
        "label": label, "level": level,
        "amount": int(plan["amount_rub"] or 0) if plan and int(plan["active"] or 0) else None,
        "type": (
            "course" if int(plan["course_paid"] or 0) else plan["payment_type"]
        ) if plan and int(plan["active"] or 0) else None,
        "remaining": (
            int(plan["lessons_remaining"] or 0)
            if plan and plan["payment_type"] == "package" and int(plan["active"] or 0)
            else None
        ),
    }


def _member_homework(uid, gid, pid):
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT h.homework_text,h.due_date,hs.status
            FROM teacher_homework_status hs
            JOIN teacher_homework h ON h.id=hs.assignment_id
            WHERE h.teacher_telegram_user_id=? AND h.target_kind='group'
              AND h.target_id=? AND h.active=1
              AND hs.subject_kind='group_member' AND hs.subject_id=?
            ORDER BY h.due_date DESC,h.id DESC LIMIT 15
            """,
            (int(uid), int(gid), int(pid)),
        ).fetchall()
    return [{
        "text": r["homework_text"], "due": r["due_date"], "status": r["status"],
    } for r in rows]


def group_view(uid, gid):
    group = _owned(uid, gid)
    if not group:
        return None
    members = learning._members(uid, gid)
    now = datetime.now(schedule.tz(uid)).date()
    recent = _sessions(uid, gid, now, -13, 1)
    upcoming = _sessions(uid, gid, now, 0, 14)[:8]
    # Attendance only on the most recent actual occurrence, including today.
    last_session = recent[-1] if recent else None
    student_rows = []
    for m in members:
        pid = int(m["id"])
        attendance = (
            learning._attendance_status(
                uid, "group", last_session["slot_id"],
                datetime.fromisoformat(last_session["date"]).date(),
                "group_member", pid,
            )
            if last_session else None
        )
        student_rows.append({
            "id": pid,
            "name": m["name"],
            "connected": bool(m["telegram_user_id"]),
            "payment": _payment(uid, pid),
            "attendance": attendance,
        })
    homework = _homework(uid, gid)
    return {
        "title": group["name"],
        "group_id": int(gid),
        "members": student_rows,
        "member_count": len(student_rows),
        "connected_count": sum(int(m["connected"]) for m in student_rows),
        "payment_issues": sum(int(m["payment"]["level"] == "bad") for m in student_rows),
        "slots": [
            {"weekday": int(r["weekday"]), "time": r["time_text"]}
            for r in groups.group_slots(uid) if int(r["group_id"]) == int(gid)
        ],
        "upcoming": upcoming,
        "attendance_session": last_session,
        "homework": homework,
    }


def member_view(uid, pid):
    pay = _payments()
    member = pay._member(uid, pid)
    if not member or not _owned(uid, member["group_id"]):
        return None
    gid = int(member["group_id"])
    return {
        "title": member["name"],
        "id": int(pid),
        "group_id": gid,
        "group_name": member["group_name"],
        "connected": bool(member["telegram_user_id"]),
        "payment": _payment(uid, pid),
        "homework": _member_homework(uid, gid, pid),
    }



def send_group_action(uid, payload):
    """Send an authorized inline control to the teacher's own Telegram chat.

    Inline-button Mini Apps do not support Telegram.WebApp.sendData().
    This server action uses validated WebApp auth and never accepts chat_id
    or bot token from a client.
    """
    import json
    from urllib.request import Request, urlopen

    try:
        gid = int(payload.get("group_id"))
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "error": "invalid_group_id"}
    group = _owned(uid, gid)
    if not group:
        return {"ok": False, "error": "group_not_found"}
    section = str(payload.get("section") or "")
    options = {
        "members": ("Добавить ученика", f"gmem:add:{gid}"),
        "schedule": ("Настроить расписание", f"gs:add:{gid}"),
        "payments": ("Оплаты группы", f"gpay:group:{gid}"),
        "homework": ("Выдать ДЗ группе", f"edu:hwquick:group:{gid}"),
    }
    choice = options.get(section)
    if not choice:
        return {"ok": False, "error": "invalid_group_action"}
    token = base.BOT_TOKEN
    if not token:
        return {"ok": False, "error": "bot_unavailable"}
    request_body = json.dumps({
        "chat_id": int(uid),
        "text": f"ПРЕПАДМИН · {group['name']}\\nНажми кнопку, чтобы продолжить работу:",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": choice[0], "callback_data": choice[1]}],
                [{"text": "Карточка группы", "callback_data": f"gmem:group:{gid}"}],
            ],
        },
    }, ensure_ascii=False).encode("utf-8")
    request = Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            body = json.load(response)
        if not body.get("ok"):
            return {"ok": False, "error": "message_not_delivered"}
    except Exception as exc:
        # Never expose Telegram token or request URL via logs and API errors.
        print(f"PREPODMIN group action delivery failed: {type(exc).__name__}", flush=True)
        return {"ok": False, "error": "message_not_delivered"}
    return {"ok": True, "section": section, "group_id": gid}



def mark_attendance(uid, payload):
    try:
        gid = int(payload.get("group_id"))
        pid = int(payload.get("member_id"))
        slot_id = int(payload.get("slot_id"))
        day = datetime.strptime(str(payload.get("date")), "%Y-%m-%d").date()
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "error": "invalid_attendance_data"}
    status = str(payload.get("status") or "")
    if status not in ("present", "absent"):
        return {"ok": False, "error": "invalid_attendance_status"}
    group = _owned(uid, gid)
    if not group:
        return {"ok": False, "error": "group_not_found"}
    now = datetime.now(schedule.tz(uid)).date()
    if day > now or day < now - timedelta(days=13):
        return {"ok": False, "error": "attendance_date_out_of_range"}
    if not any(int(m["id"]) == pid for m in learning._members(uid, gid)):
        return {"ok": False, "error": "member_not_found"}
    event = learning._event_from_key(uid, "group", slot_id, day)
    if not event or int(event["group_id"]) != gid:
        return {"ok": False, "error": "session_not_found"}
    current = learning._attendance_status(uid, "group", slot_id, day, "group_member", pid)
    if current == status:
        return {"ok": True, "unchanged": True, "status": status}
    # Reuse patched setter; this also reconciles package charges on corrections.
    learning._set_attendance(uid, "group", slot_id, day, "group_member", pid, status)
    return {"ok": True, "status": status}
