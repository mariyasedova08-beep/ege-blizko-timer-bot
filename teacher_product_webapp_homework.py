"""Durable, teacher-scoped homework issuing from PREPODMIN Mini App.

Creates assignments in the EXISTING teacher_homework tables. Queues a single
one-shot delivery job to the existing Telegram messaging gateway respecting
the teacher's auto/draft/manual/off preference. No auto-retry after a send
attempt: this avoids duplicate auto-mode Telegram sends on ambiguous failures.
"""
import re
from datetime import datetime, date, timedelta

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_learning as learning
import teacher_product_schedule as schedule


def ensure_tables():
    learning.ensure_tables()
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_webapp_homework_delivery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                request_key TEXT NOT NULL,
                assignment_id INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending'
                  CHECK(state IN ('pending','sending','done','failed')),
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                linked_count INTEGER,
                sent_count INTEGER,
                failed_count INTEGER,
                error_code TEXT,
                UNIQUE(teacher_telegram_user_id,request_key),
                UNIQUE(assignment_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_teacher_webapp_hw_delivery_pending "
            "ON teacher_webapp_homework_delivery(state,id)"
        )
        # Additive metadata only: legacy homework has no mode row and remains
        # 'self', with historical done marks of unknown provenance.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teacher_webapp_homework_modes (
                assignment_id INTEGER PRIMARY KEY,
                teacher_telegram_user_id INTEGER NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('self','attachment'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teacher_webapp_homework_status_origin (
                assignment_id INTEGER NOT NULL,
                subject_kind TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                completed_by TEXT NOT NULL CHECK(completed_by IN ('teacher','student')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY(assignment_id,subject_kind,subject_id)
            )
        """)
        conn.commit()


def mode_for_assignment(aid):
    ensure_tables()
    with base.db() as conn:
        row = conn.execute(
            "SELECT mode FROM teacher_webapp_homework_modes WHERE assignment_id=?",
            (int(aid),),
        ).fetchone()
    return row["mode"] if row else "self"


def mode_map(aids):
    ids = [int(aid) for aid in aids]
    if not ids:
        return {}
    ensure_tables()
    with base.db() as conn:
        marks = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT assignment_id,mode FROM teacher_webapp_homework_modes "
            f"WHERE assignment_id IN ({marks})",
            ids,
        ).fetchall()
    return {int(row["assignment_id"]):row["mode"] for row in rows}


def status_origins(aids):
    ids = [int(aid) for aid in aids]
    if not ids:
        return {}
    ensure_tables()
    with base.db() as conn:
        marks = ",".join("?" for _ in ids)
        rows = conn.execute(
            "SELECT assignment_id,subject_kind,subject_id,completed_by "
            "FROM teacher_webapp_homework_status_origin "
            f"WHERE assignment_id IN ({marks})", ids,
        ).fetchall()
    return {(int(r["assignment_id"]),r["subject_kind"],int(r["subject_id"])):r["completed_by"]
            for r in rows}


def create_group_assignment(uid, payload):
    """Idempotent action; student notifications are never sent from HTTP thread."""
    try:
        gid = int(payload.get("group_id"))
    except (ValueError, TypeError, OverflowError):
        return {"ok": False, "error": "invalid_group_id"}
    if not base.teacher(uid) or not groups.get_group(uid, gid):
        return {"ok": False, "error": "group_not_found"}

    text = str(payload.get("homework_text") or "").strip()
    if len(text) < 2 or len(text) > 3500:
        return {"ok": False, "error": "invalid_homework_text"}
    try:
        due = date.fromisoformat(str(payload.get("due_date") or ""))
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid_due_date"}
    today = datetime.now(schedule.tz(uid)).date()
    if due < today or due > today + timedelta(days=366):
        return {"ok": False, "error": "invalid_due_date"}

    mode = payload.get("submission_mode", "self")
    if mode not in ("self", "attachment"):
        return {"ok": False, "error": "invalid_submission_mode"}
    # A protected operator switch is required before file homework is issuable.
    # It must remain off until private storage, Nginx and backups are verified.
    if mode == "attachment":
        import teacher_product_homework_submissions as submissions
        if not submissions.enabled():
            return {"ok": False, "error": "attachment_submission_not_ready"}
        try:
            submissions.storage_root()
        except (RuntimeError, OSError):
            return {"ok": False, "error": "attachment_storage_unavailable"}

    request_key = str(payload.get("request_key") or "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{12,80}", request_key):
        return {"ok": False, "error": "invalid_request_key"}

    ensure_tables()
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        # Serialize check+insert across concurrent WebApp threads/processes.
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute(
            """
            SELECT h.id,h.target_id,h.homework_text,h.due_date,d.state,
                   COALESCE(m.mode,'self') AS submission_mode
            FROM teacher_webapp_homework_delivery d
            JOIN teacher_homework h ON h.id=d.assignment_id
            LEFT JOIN teacher_webapp_homework_modes m ON m.assignment_id=h.id
            WHERE d.teacher_telegram_user_id=? AND d.request_key=?
            """,
            (int(uid), request_key),
        ).fetchone()
        if previous:
            if (int(previous["target_id"]) != gid
                    or previous["homework_text"] != text
                    or previous["due_date"] != due.isoformat()
                    or previous["submission_mode"] != mode):
                return {"ok": False, "error": "request_key_conflict"}
            return {
                "ok": True, "duplicate": True, "assignment_id": int(previous["id"]),
                "delivery_state": previous["state"],
            }
        members = learning._members(uid, gid)
        if not members:
            return {"ok": False, "error": "empty_group"}
        cur = conn.execute(
            """
            INSERT INTO teacher_homework(
                teacher_telegram_user_id,target_kind,target_id,homework_text,
                due_date,active,created_at
            ) VALUES(?,'group',?,?,?,1,?)
            """,
            (int(uid), gid, text, due.isoformat(), now),
        )
        aid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO teacher_webapp_homework_modes "
            "(assignment_id,teacher_telegram_user_id,mode) VALUES(?,?,?)",
            (aid,int(uid),mode),
        )
        for member in members:
            conn.execute(
                """
                INSERT OR IGNORE INTO teacher_homework_status(
                    assignment_id,subject_kind,subject_id,status,updated_at
                ) VALUES(?,'group_member',?,'pending',?)
                """,
                (aid, int(member["id"]), now),
            )
        conn.execute(
            """
            INSERT INTO teacher_webapp_homework_delivery(
                teacher_telegram_user_id,group_id,request_key,assignment_id,
                state,created_at
            ) VALUES(?,?,?,?, 'pending',?)
            """,
            (int(uid), gid, request_key, aid, now),
        )
        conn.commit()
    return {
        "ok": True, "duplicate": False, "assignment_id": aid,
        "delivery_state": "pending", "submission_mode": mode,
    }


def mark_group_homework(uid, payload):
    """Teacher marks an existing group member's homework done/pending."""
    try:
        aid = int(payload.get("assignment_id"))
        pid = int(payload.get("member_id"))
    except (ValueError, TypeError, OverflowError):
        return {"ok": False, "error": "invalid_subject"}
    status = str(payload.get("status") or "")
    if status not in ("done", "pending"):
        return {"ok": False, "error": "invalid_homework_status"}
    assignment = learning._assignment(aid, uid)
    if not assignment or not assignment["active"] or assignment["target_kind"] != "group":
        return {"ok": False, "error": "assignment_not_found"}
    if mode_for_assignment(aid) != "self":
        return {"ok": False, "error": "manual_mark_not_allowed_for_attachment"}
    gid = int(assignment["target_id"])
    if not groups.get_group(uid, gid) or not any(
        int(member["id"]) == pid for member in learning._members(uid, gid)
    ):
        return {"ok": False, "error": "member_not_found"}

    learning._sync_statuses(assignment)
    with base.db() as conn:
        old = conn.execute(
            """
            SELECT status FROM teacher_homework_status
            WHERE assignment_id=? AND subject_kind='group_member' AND subject_id=?
            """,
            (aid, pid),
        ).fetchone()
        if not old:
            return {"ok": False, "error": "status_not_found"}
        if old["status"] == status:
            return {"ok": True, "unchanged": True, "status": status}
        now = datetime.utcnow().isoformat()
        conn.execute(
            """
            UPDATE teacher_homework_status
            SET status=?,done_at=?,updated_at=?
            WHERE assignment_id=? AND subject_kind='group_member' AND subject_id=?
            """,
            (status, now if status == "done" else None, now, aid, pid),
        )
        if status == "done":
            conn.execute(
                "INSERT INTO teacher_webapp_homework_status_origin "
                "(assignment_id,subject_kind,subject_id,completed_by,updated_at) "
                "VALUES(?,'group_member',?,'teacher',?) "
                "ON CONFLICT(assignment_id,subject_kind,subject_id) "
                "DO UPDATE SET completed_by='teacher',updated_at=excluded.updated_at",
                (aid,pid,now),
            )
        else:
            conn.execute(
                "DELETE FROM teacher_webapp_homework_status_origin "
                "WHERE assignment_id=? AND subject_kind='group_member' AND subject_id=?",
                (aid,pid),
            )
        conn.commit()
    return {"ok": True, "status": status}


def delivery_state(uid, aid):
    ensure_tables()
    with base.db() as conn:
        row = conn.execute(
            """
            SELECT state,linked_count,sent_count,failed_count,error_code
            FROM teacher_webapp_homework_delivery
            WHERE assignment_id=? AND teacher_telegram_user_id=?
            """,
            (int(aid), int(uid)),
        ).fetchone()
    if not row:
        return None
    return {
        "state": row["state"],
        "linked": row["linked_count"],
        "sent": row["sent_count"],
        "failed": row["failed_count"],
    }


async def delivery_tick(context):
    """Called from PREPODMIN's PTB JobQueue, never from WebApp's HTTP thread."""
    ensure_tables()
    pending = []
    with base.db() as conn:
        rows = conn.execute(
            """
            SELECT id,teacher_telegram_user_id,assignment_id
            FROM teacher_webapp_homework_delivery
            WHERE state='pending' ORDER BY id LIMIT 10
            """
        ).fetchall()
        for row in rows:
            now = datetime.utcnow().isoformat()
            updated = conn.execute(
                """
                UPDATE teacher_webapp_homework_delivery
                SET state='sending',started_at=? WHERE id=? AND state='pending'
                """,
                (now, int(row["id"])),
            )
            if updated.rowcount == 1:
                pending.append(dict(row))
        conn.commit()

    for job in pending:
        sent = failed = linked = 0
        state = "done"
        err = None
        try:
            assignment = learning._assignment(job["assignment_id"], job["teacher_telegram_user_id"])
            if not assignment or not assignment["active"]:
                state, err = "failed", "assignment_unavailable"
            else:
                sent, failed, linked = await learning._send_assignment(context, assignment)
                # A failed send is not automatically retried: Telegram may have
                # accepted it before a timeout. This prevents surprise duplicates.
                if failed:
                    state, err = "failed", "some_notifications_failed"
        except Exception as exc:
            state, err = "failed", "delivery_exception"
            print("PREPODMIN WebApp homework delivery exception: " + type(exc).__name__, flush=True)
        with base.db() as conn:
            conn.execute(
                """
                UPDATE teacher_webapp_homework_delivery
                SET state=?,finished_at=?,linked_count=?,sent_count=?,failed_count=?,
                    error_code=?
                WHERE id=? AND state='sending'
                """,
                (
                    state, datetime.utcnow().isoformat(),
                    int(linked), int(sent), int(failed), err, int(job["id"]),
                ),
            )
            conn.commit()
