"""PREPODMIN Mini App group lesson management.

Uses existing group_schedule_slots/moves and teacher_lesson_cancellations.
Authorized teacher uid is supplied by the verified teacher WebApp endpoint.
Mutations have idempotency keys; student notifications run once in PTB JobQueue.
"""
import re
import sqlite3
from datetime import date, datetime, timedelta

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_schedule as schedule
import teacher_product_cancellations as cancellations


def ensure_tables():
    groups.ensure_tables()
    cancellations.ensure_tables()
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_webapp_lesson_actions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                request_key TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('add','move','cancel')),
                slot_id INTEGER NOT NULL,
                original_date TEXT,
                old_date TEXT,
                old_time TEXT,
                new_date TEXT,
                new_time TEXT,
                group_name TEXT NOT NULL,
                moved_before INTEGER NOT NULL DEFAULT 0,
                notification_choice TEXT NOT NULL DEFAULT 'legacy',
                state TEXT NOT NULL DEFAULT 'pending'
                  CHECK(state IN ('pending','sending','done','failed','none')),
                sent_count INTEGER,
                failed_count INTEGER,
                linked_count INTEGER,
                created_at TEXT NOT NULL,
                finished_at TEXT,
                UNIQUE(teacher_telegram_user_id,request_key)
            );
            CREATE INDEX IF NOT EXISTS idx_teacher_webapp_lesson_action_queue
            ON teacher_webapp_lesson_actions(state,id);
            CREATE TABLE IF NOT EXISTS teacher_webapp_lesson_topics(
                teacher_telegram_user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                occurrence_key TEXT NOT NULL,
                topic TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key)
            );
            """
        )
        # Safe additive migration for every existing installation: historic jobs
        # retain legacy global-message behavior, new jobs persist a per-action choice.
        columns = {c[1] for c in conn.execute(
            "PRAGMA table_info(teacher_webapp_lesson_actions)"
        ).fetchall()}
        if "notification_choice" not in columns:
            conn.execute(
                "ALTER TABLE teacher_webapp_lesson_actions ADD COLUMN "
                "notification_choice TEXT NOT NULL DEFAULT 'legacy'"
            )
        conn.commit()


def upcoming(uid, gid, days=45):
    """Future occurrences with stable original dates and individual topics."""
    if not groups.get_group(uid, gid):
        return []
    ensure_tables()  # additive; old plans/attendance/moves stay untouched
    events = [{
        "slot_id": int(e["slot_id"]),
        "occurrence_key": e["occurrence_key"],
        "date": e["actual_date"].isoformat(),
        "time": e["actual_time"],
        "date_label": e["actual_date"].strftime("%d.%m"),
        "moved": bool(e["moved"]),
    } for e in cancellations._upcoming_occurrences(uid, kind="group", days=days)
        if int(e["person_id"]) == int(gid)][:25]
    with base.db() as conn:
        saved = conn.execute(
            "SELECT schedule_slot_id,occurrence_key,topic "
            "FROM teacher_webapp_lesson_topics "
            "WHERE teacher_telegram_user_id=? AND group_id=?",
            (int(uid), int(gid)),
        ).fetchall()
    topics = {(int(r["schedule_slot_id"]), r["occurrence_key"]): r["topic"] for r in saved}
    for event in events:
        event["topic"] = topics.get((event["slot_id"], event["occurrence_key"]), "")
    return events


def save_topic(uid, payload):
    """Set/clear one lesson's theme; no notification or payment side effects."""
    try:
        gid = int(payload.get("group_id"))
        slot_id = int(payload.get("slot_id"))
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "error": "invalid_occurrence"}
    if (isinstance(payload.get("group_id"), bool)
            or isinstance(payload.get("slot_id"), bool)
            or gid <= 0 or slot_id <= 0):
        return {"ok": False, "error": "invalid_occurrence"}
    if not base.teacher(uid) or not groups.get_group(uid, gid):
        return {"ok": False, "error": "group_not_found"}
    occurrence_key = str(payload.get("occurrence_key") or "")
    try:
        original = date.fromisoformat(occurrence_key)
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid_occurrence"}
    if original.isoformat() != occurrence_key:
        return {"ok": False, "error": "invalid_occurrence"}
    slot = groups.group_slot(uid, slot_id)
    if not slot or int(slot["group_id"]) != gid:
        return {"ok": False, "error": "slot_not_found"}
    if original.weekday() != int(slot["weekday"]):
        return {"ok": False, "error": "invalid_occurrence"}
    raw_topic = payload.get("topic")
    if not isinstance(raw_topic, str):
        return {"ok": False, "error": "invalid_topic"}
    topic = " ".join(raw_topic.split())
    if len(topic) > 160:
        return {"ok": False, "error": "invalid_topic"}
    # Only lessons currently visible to this teacher can be edited.
    if not any(e["slot_id"] == slot_id and e["occurrence_key"] == occurrence_key
               for e in upcoming(uid, gid)):
        return {"ok": False, "error": "lesson_not_available"}
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        if topic:
            conn.execute(
                "INSERT INTO teacher_webapp_lesson_topics "
                "(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key,"
                "topic,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key) "
                "DO UPDATE SET topic=excluded.topic,updated_at=excluded.updated_at",
                (int(uid),gid,slot_id,occurrence_key,topic,now,now),
            )
        else:
            conn.execute(
                "DELETE FROM teacher_webapp_lesson_topics "
                "WHERE teacher_telegram_user_id=? AND group_id=? "
                "AND schedule_slot_id=? AND occurrence_key=?",
                (int(uid),gid,slot_id,occurrence_key),
            )
        conn.commit()
    return {"ok": True, "group_id": gid, "slot_id": slot_id, "topic": topic}


def _clock(value):
    raw = str(value or "")
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", raw):
        return None
    return raw


def _key(payload):
    key = str(payload.get("request_key") or "")
    return key if re.fullmatch(r"[A-Za-z0-9_-]{12,80}", key) else None


def save(uid, payload):
    """Create recurring slot / move one occurrence / cancel one occurrence."""
    kind = str(payload.get("lesson_action") or "")
    if kind not in ("add", "move", "cancel"):
        return {"ok": False, "error": "invalid_lesson_action"}
    try:
        gid = int(payload.get("group_id"))
    except (ValueError, TypeError, OverflowError):
        return {"ok": False, "error": "invalid_group_id"}
    group = groups.get_group(uid, gid) if base.teacher(uid) else None
    if not group:
        return {"ok": False, "error": "group_not_found"}
    request_key = _key(payload)
    if not request_key:
        return {"ok": False, "error": "invalid_request_key"}
    # Existing callers without this field keep their historic global setting.
    # The Mini App always sends one explicit choice for moves/cancellations.
    choice = str(payload.get("notification_choice") or "legacy")
    if kind != "add" and choice not in ("send", "draft", "off", "legacy"):
        return {"ok": False, "error": "invalid_notification_choice"}
    now = datetime.now(schedule.tz(uid))
    today = now.date()
    weekday = None
    occurrence = slot_id = old_date = old_time = new_date = new_time = None
    moved_before = False
    if kind == "add":
        try:
            weekday = int(payload.get("weekday"))
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "error": "invalid_weekday"}
        if isinstance(payload.get("weekday"), bool) or not 0 <= weekday <= 6:
            return {"ok": False, "error": "invalid_weekday"}
        new_time = _clock(payload.get("time"))
        if not new_time:
            return {"ok": False, "error": "invalid_time"}
    else:
        try:
            slot_id = int(payload.get("slot_id"))
            occurrence = date.fromisoformat(str(payload.get("occurrence_key")))
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "error": "invalid_occurrence"}
        slot = groups.group_slot(uid, slot_id)
        if not slot or int(slot["group_id"]) != gid:
            return {"ok": False, "error": "slot_not_found"}
        if occurrence.weekday() != int(slot["weekday"]):
            return {"ok": False, "error": "invalid_occurrence"}
        if occurrence < today - timedelta(days=90) or occurrence > today + timedelta(days=180):
            return {"ok": False, "error": "invalid_occurrence"}
        if kind == "move":
            try:
                new_date = date.fromisoformat(str(payload.get("new_date")))
            except (TypeError, ValueError):
                return {"ok": False, "error": "invalid_new_date"}
            new_time = _clock(payload.get("new_time"))
            if not new_time:
                return {"ok": False, "error": "invalid_time"}
            if not today <= new_date <= today + timedelta(days=180):
                return {"ok": False, "error": "invalid_new_date"}
            moved_dt = datetime.combine(new_date, datetime.strptime(new_time, "%H:%M").time(), tzinfo=schedule.tz(uid))
            if moved_dt <= now:
                return {"ok": False, "error": "lesson_in_past"}

    ensure_tables()
    with base.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute(
            "SELECT id,kind,slot_id,group_id,original_date,new_date,new_time,state,notification_choice FROM teacher_webapp_lesson_actions "
            "WHERE teacher_telegram_user_id=? AND request_key=?",
            (int(uid), request_key),
        ).fetchone()
        if previous:
            if (previous["kind"] != kind or int(previous["group_id"]) != gid
                    or (kind != "add" and previous["notification_choice"] != choice)):
                return {"ok":False,"error":"request_key_conflict"}
            if kind == "add":
                original_slot = conn.execute(
                    "SELECT weekday,time_text FROM group_schedule_slots "
                    "WHERE id=? AND teacher_telegram_user_id=?",
                    (int(previous["slot_id"]),int(uid)),
                ).fetchone()
                if (not original_slot or int(original_slot["weekday"]) != weekday
                        or original_slot["time_text"] != new_time):
                    return {"ok":False,"error":"request_key_conflict"}
            elif (int(previous["slot_id"]) != slot_id
                    or previous["original_date"] != occurrence.isoformat()
                    or kind == "move" and (
                        previous["new_date"] != new_date.isoformat()
                        or previous["new_time"] != new_time
                    )):
                return {"ok":False,"error":"request_key_conflict"}
            return {"ok":True,"duplicate":True,"action_id":int(previous["id"]),"state":previous["state"]}

        if kind == "add":
            current=conn.execute(
                "SELECT 1 FROM group_schedule_slots WHERE teacher_telegram_user_id=? "
                "AND group_id=? AND active=1 AND weekday=? AND time_text=? LIMIT 1",
                (int(uid),gid,weekday,new_time),
            ).fetchone()
            if current:
                return {"ok":False,"error":"slot_already_exists"}
            cur=conn.execute(
                "INSERT INTO group_schedule_slots(teacher_telegram_user_id,group_id,weekday,time_text,created_at) "
                "VALUES(?,?,?,?,?)",
                (int(uid),gid,weekday,new_time,datetime.utcnow().isoformat()),
            )
            slot_id=int(cur.lastrowid)
        else:
            current=conn.execute(
                "SELECT gs.weekday,gs.time_text FROM group_schedule_slots gs "
                "JOIN teacher_groups g ON g.id=gs.group_id "
                "WHERE gs.teacher_telegram_user_id=? AND gs.id=? AND gs.group_id=? AND gs.active=1 AND g.active=1",
                (int(uid),slot_id,gid),
            ).fetchone()
            if not current:
                return {"ok":False,"error":"slot_not_found"}
            moved=conn.execute(
                "SELECT new_date,new_time FROM group_schedule_moves "
                "WHERE teacher_telegram_user_id=? AND schedule_slot_id=? AND original_date=? "
                "ORDER BY id DESC LIMIT 1",
                (int(uid),slot_id,occurrence.isoformat()),
            ).fetchone()
            old_date = moved["new_date"] if moved else occurrence.isoformat()
            old_time = moved["new_time"] if moved else current["time_text"]
            moved_before=bool(moved)
            already_cancelled=conn.execute(
                "SELECT 1 FROM teacher_lesson_cancellations WHERE teacher_telegram_user_id=? "
                "AND lesson_kind='group' AND schedule_slot_id=? AND occurrence_key=?",
                (int(uid),slot_id,occurrence.isoformat()),
            ).fetchone()
            if already_cancelled:
                return {"ok":False,"error":"lesson_cancelled"}
            before=datetime.combine(date.fromisoformat(old_date),
                datetime.strptime(old_time,"%H:%M").time(), tzinfo=schedule.tz(uid))
            if before <= now:
                return {"ok":False,"error":"lesson_in_past"}
            if (str(payload.get("expected_date") or "") != old_date
                    or str(payload.get("expected_time") or "") != old_time):
                return {"ok":False,"error":"lesson_changed_refresh"}
            attendance=conn.execute(
                "SELECT 1 FROM teacher_attendance WHERE teacher_telegram_user_id=? AND "
                "lesson_kind='group' AND schedule_slot_id=? AND lesson_date IN (?,?) LIMIT 1",
                (int(uid),slot_id,occurrence.isoformat(),old_date),
            ).fetchone()
            if attendance:
                return {"ok":False,"error":"attendance_already_recorded"}
            if kind == "move":
                if old_date == new_date.isoformat() and old_time == new_time:
                    return {"ok":False,"error":"lesson_unchanged"}
                conn.execute(
                    "DELETE FROM group_schedule_moves WHERE teacher_telegram_user_id=? AND "
                    "schedule_slot_id=? AND original_date=?",
                    (int(uid),slot_id,occurrence.isoformat()),
                )
                conn.execute(
                    "INSERT INTO group_schedule_moves(teacher_telegram_user_id,schedule_slot_id,"
                    "original_date,new_date,new_time,created_at) VALUES(?,?,?,?,?,?)",
                    (int(uid),slot_id,occurrence.isoformat(),new_date.isoformat(),new_time,datetime.utcnow().isoformat()),
                )
            else:
                conn.execute(
                    "INSERT INTO teacher_lesson_cancellations("
                    "teacher_telegram_user_id,lesson_kind,schedule_slot_id,occurrence_key,"
                    "actual_date,actual_time,cancelled_at) VALUES(?,'group',?,?,?,?,?)",
                    (int(uid),slot_id,occurrence.isoformat(),old_date,old_time,now.isoformat()),
                )

        created = datetime.utcnow().isoformat()
        cur=conn.execute(
            "INSERT INTO teacher_webapp_lesson_actions("
            "teacher_telegram_user_id,group_id,request_key,kind,slot_id,original_date,old_date,"
            "old_time,new_date,new_time,group_name,moved_before,notification_choice,state,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(uid),gid,request_key,kind,int(slot_id),
             occurrence.isoformat() if occurrence else None,old_date,old_time,
             new_date.isoformat() if new_date else None,new_time,group["name"],
             int(moved_before),choice if kind!="add" else "legacy",
             "none" if kind=="add" or choice=="off" else "pending",created),
        )
        action_id=int(cur.lastrowid)
        conn.commit()
    return {
        "ok":True,"duplicate":False,"action_id":action_id,
        "state":"none" if kind=="add" or choice=="off" else "pending",
        "notification_choice":choice if kind!="add" else None,
    }


async def delivery_tick(context):
    """Deliver a recorded lesson change only once, respecting messaging mode."""
    import teacher_product_transfer_enhancements as transfers
    ensure_tables()
    claimed=[]
    with base.db() as conn:
        rows=conn.execute(
            "SELECT * FROM teacher_webapp_lesson_actions WHERE state='pending' "
            "AND kind IN ('move','cancel') ORDER BY id LIMIT 10"
        ).fetchall()
        for row in rows:
            change=conn.execute(
                "UPDATE teacher_webapp_lesson_actions SET state='sending' "
                "WHERE id=? AND state='pending'",(int(row["id"]),),
            )
            if change.rowcount==1:
                claimed.append(dict(row))
        conn.commit()
    for row in claimed:
        state="done"
        sent=failed=linked=0
        try:
            # Only the explicit choice on THIS lesson is overridden; neither
            # the teacher's saved messaging preference nor other jobs change.
            choice = row["notification_choice"]
            override = {"send":"auto","draft":"draft"}.get(choice)
            notification_kwargs = ({"mode_override":override}
                                   if override else {})
            if row["kind"]=="move":
                sent,failed,linked=await transfers._notify_transfer(
                    context,int(row["teacher_telegram_user_id"]),"group",
                    int(row["slot_id"]),row["old_date"],row["old_time"],
                    row["new_date"],row["new_time"],**notification_kwargs
                )
            elif row["kind"]=="cancel":
                event={
                    "kind":"group","slot_id":int(row["slot_id"]),
                    "person_id":int(row["group_id"]),"name":row["group_name"],
                    "occurrence_key":row["original_date"],
                    "actual_date":date.fromisoformat(row["old_date"]),
                    "actual_time":row["old_time"],"moved":bool(row["moved_before"]),
                }
                sent,failed,linked=await cancellations._notify_students(
                    context,int(row["teacher_telegram_user_id"]),event,
                    **notification_kwargs
                )
            if failed:
                state="failed"
        except Exception as exc:
            print("PREPODMIN WebApp lesson notice exception: "+type(exc).__name__,flush=True)
            state="failed"
        with base.db() as conn:
            conn.execute(
                "UPDATE teacher_webapp_lesson_actions SET state=?,sent_count=?,failed_count=?,"
                "linked_count=?,finished_at=? WHERE id=? AND state='sending'",
                (state,int(sent),int(failed),int(linked),datetime.utcnow().isoformat(),int(row["id"])),
            )
            conn.commit()
