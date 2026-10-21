"""Private PREPODMIN group lesson recording links.

Only HTTPS URLs are stored; no videos are uploaded or hosted. Each link is
attached to a single stable lesson occurrence. Nothing is sent to students.
"""
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_schedule as schedule
import teacher_product_cancellations as cancellations


def ensure_tables():
    with base.db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS teacher_webapp_lesson_recording_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                occurrence_key TEXT NOT NULL,
                recording_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key)
            )"""
        )
        conn.commit()


def past_lessons(uid, gid, days=31, limit=12):
    """Past actual sessions with their stable original dates, including moves."""
    if not groups.get_group(uid, gid):
        return []
    now = datetime.now(schedule.tz(uid))
    start = now.date() - timedelta(days=days)
    possible = set()
    slots = [row for row in groups.group_slots(uid) if int(row["group_id"]) == int(gid)]
    for slot in slots:
        slot_id = int(slot["id"])
        for offset in range(days + 1):
            original = start + timedelta(days=offset)
            if original.weekday() == int(slot["weekday"]):
                possible.add((slot_id, original.isoformat()))
    for moved in cancellations._move_rows(uid, "group", start, now.date()):
        possible.add((int(moved["schedule_slot_id"]), str(moved["original_date"])))
    valid_slots = {int(row["id"]) for row in slots}
    result = []
    for slot_id, original in possible:
        if slot_id not in valid_slots:
            continue
        event = cancellations._event_from_occurrence(uid, "group", slot_id, original)
        if not event or int(event["person_id"]) != int(gid):
            continue
        if cancellations.is_cancelled(uid, "group", slot_id, original):
            continue
        actual = datetime.combine(
            event["actual_date"], datetime.strptime(event["actual_time"], "%H:%M").time(),
            tzinfo=schedule.tz(uid),
        )
        if not (start <= event["actual_date"] <= now.date() and actual < now):
            continue
        result.append({
            "slot_id": slot_id, "occurrence_key": original,
            "date": event["actual_date"].isoformat(),
            "date_label": event["actual_date"].strftime("%d.%m"),
            "time": event["actual_time"], "moved": bool(event["moved"]),
        })
    result.sort(key=lambda r: (r["date"], r["time"], r["slot_id"]), reverse=True)
    return result[:limit]


def _owned_occurrence(uid, gid, slot_id, key):
    if not base.teacher(uid) or not groups.get_group(uid, gid):
        return "group_not_found"
    slot = groups.group_slot(uid, slot_id)
    if not slot or int(slot["group_id"]) != gid:
        return "slot_not_found"
    try:
        original = date.fromisoformat(key)
    except (ValueError, TypeError):
        return "invalid_occurrence"
    if original.isoformat() != key or original.weekday() != int(slot["weekday"]):
        return "invalid_occurrence"
    import teacher_product_webapp_lessons as lessons
    visible = lessons.upcoming(uid, gid) + past_lessons(uid, gid)
    if not any(v["slot_id"] == slot_id and v["occurrence_key"] == key for v in visible):
        return "lesson_not_available"
    return None


def _identify(uid, payload):
    try:
        gid, slot_id = int(payload.get("group_id")), int(payload.get("slot_id"))
    except (ValueError, TypeError, OverflowError, AttributeError):
        return None, "invalid_occurrence"
    key = str(payload.get("occurrence_key") or "")
    if isinstance(payload.get("group_id"), bool) or isinstance(payload.get("slot_id"), bool):
        return None, "invalid_occurrence"
    if gid <= 0 or slot_id <= 0:
        return None, "invalid_occurrence"
    error = _owned_occurrence(uid, gid, slot_id, key)
    return ((gid, slot_id, key), None) if error is None else (None, error)

def decorate(uid, gid, events):
    """Attach teacher-only metadata for links without touching the schedule."""
    ensure_tables()
    with base.db() as conn:
        rows = conn.execute(
            "SELECT schedule_slot_id,occurrence_key,recording_url "
            "FROM teacher_webapp_lesson_recording_links "
            "WHERE teacher_telegram_user_id=? AND group_id=?",
            (int(uid), int(gid)),
        ).fetchall()
    urls = {(int(row["schedule_slot_id"]),row["occurrence_key"]):row["recording_url"]
            for row in rows}
    for event in events:
        event["recording_url"] = urls.get(
            (event["slot_id"],event["occurrence_key"]), "")
    return events


def set_link(uid, payload):
    """Create/change/remove one HTTPS link; no upload and no Telegram send."""
    identity, error = _identify(uid, payload)
    if error:
        return {"ok":False,"error":error}
    raw_url = payload.get("url")
    if not isinstance(raw_url,str) or len(raw_url.strip()) > 2048:
        return {"ok":False,"error":"invalid_recording_url"}
    url = raw_url.strip()
    if url:
        try:
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or not parsed.netloc or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or any(ord(c)<33 or ord(c)==127 for c in url)):
                return {"ok":False,"error":"invalid_recording_url"}
            _ = parsed.port  # invalid ports must be rejected
        except ValueError:
            return {"ok":False,"error":"invalid_recording_url"}
    gid,slot_id,key = identity
    ensure_tables()
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        if not url:
            conn.execute(
                "DELETE FROM teacher_webapp_lesson_recording_links WHERE "
                "teacher_telegram_user_id=? AND group_id=? AND schedule_slot_id=? "
                "AND occurrence_key=?",
                (int(uid), gid, slot_id, key),
            )
        else:
            conn.execute(
                "INSERT INTO teacher_webapp_lesson_recording_links "
                "(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key,"
                "recording_url,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key) "
                "DO UPDATE SET recording_url=excluded.recording_url,updated_at=excluded.updated_at",
                (int(uid), gid, slot_id, key, url, now, now),
            )
        conn.commit()
    return {"ok":True,"url":url}
