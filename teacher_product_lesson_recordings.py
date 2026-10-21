"""Private PREPODMIN group lesson recordings: HTTPS links and teacher-only MP4.

This module never sends recordings to Telegram or the student cabinet. Video
bytes live beside the PREPODMIN database, outside the Git checkout. Server
operators must back up both SQLite and video directory separately.
"""
import hashlib
import hmac
import os
import re
import secrets
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_schedule as schedule
import teacher_product_cancellations as cancellations

MAX_MP4_BYTES = 200 * 1024 * 1024
_TICKET_LIFETIME = 60 * 60  # 1 hour, renewable from an authenticated cabinet
_FILE_RE = re.compile(r"[a-f0-9]{32}\.mp4\Z")
_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)\Z")


def ensure_tables():
    with base.db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS teacher_webapp_lesson_recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                schedule_slot_id INTEGER NOT NULL,
                occurrence_key TEXT NOT NULL,
                external_url TEXT NOT NULL DEFAULT '',
                file_name TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
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


def _root():
    raw = os.getenv("TEACHER_PRODUCT_RECORDINGS_DIR", "").strip()
    path = Path(raw) if raw else Path(base.DB_PATH).absolute().parent / "lesson_recordings"
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("Recording directory must be an absolute non-symlink path")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("Invalid recording directory")
    os.chmod(path, 0o700)
    return path


def _file_path(name):
    if not _FILE_RE.fullmatch(name or ""):
        raise ValueError("invalid_recording_file")
    return _root() / name


def _row(uid, gid, slot_id, key):
    ensure_tables()
    with base.db() as conn:
        return conn.execute(
            "SELECT * FROM teacher_webapp_lesson_recordings WHERE "
            "teacher_telegram_user_id=? AND group_id=? AND schedule_slot_id=? "
            "AND occurrence_key=?",
            (int(uid), gid, slot_id, key),
        ).fetchone()


def decorate(uid, gid, events):
    ensure_tables()
    with base.db() as conn:
        rows = conn.execute(
            "SELECT schedule_slot_id,occurrence_key,external_url,file_name,file_size "
            "FROM teacher_webapp_lesson_recordings WHERE teacher_telegram_user_id=? AND group_id=?",
            (int(uid),int(gid)),
        ).fetchall()
    attachments = {
        (int(row["schedule_slot_id"]),row["occurrence_key"]): {
            "url":row["external_url"],"has_file":bool(row["file_name"]),
            "file_size":int(row["file_size"] or 0),
        } for row in rows
    }
    for event in events:
        event["recording"] = attachments.get(
            (event["slot_id"],event["occurrence_key"]),
            {"url":"","has_file":False,"file_size":0},
        )
    return events


def set_link(uid, payload):
    ident, error = _identify(uid, payload)
    if error:
        return {"ok":False,"error":error}
    url = payload.get("url")
    if not isinstance(url,str) or len(url.strip()) > 2048:
        return {"ok":False,"error":"invalid_recording_url"}
    url = url.strip()
    if url:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or not parsed.netloc or parsed.username
                or parsed.password or any(c.isspace() for c in url)):
            return {"ok":False,"error":"invalid_recording_url"}
    gid,slot_id,key = ident
    ensure_tables()
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            "INSERT INTO teacher_webapp_lesson_recordings "
            "(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key,"
            "external_url,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key) "
            "DO UPDATE SET external_url=excluded.external_url,updated_at=excluded.updated_at",
            (int(uid),gid,slot_id,key,url,now,now),
        )
        conn.commit()
    return {"ok":True,"url":url}


def upload(uid, payload, stream, length, content_type):
    """Stream raw authenticated MP4 bytes, never buffering an entire file."""
    ident, error = _identify(uid,payload)
    if error:
        return {"ok":False,"error":error}
    if type(length) is not int or not (12 <= length <= MAX_MP4_BYTES):
        return {"ok":False,"error":"invalid_recording_size"}
    if content_type.split(";",1)[0].strip().lower() not in ("video/mp4","application/octet-stream"):
        return {"ok":False,"error":"invalid_recording_type"}
    folder = _root()
    if shutil.disk_usage(folder).free < length + 64 * 1024 * 1024:
        return {"ok":False,"error":"recording_disk_full"}
    gid,slot_id,key=ident
    name=secrets.token_hex(16)+".mp4"
    destination=_file_path(name)
    temp=folder/(name+".part")
    old_name=""
    try:
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as output:
            remaining=length
            first=True
            while remaining:
                chunk=stream.read(min(256*1024,remaining))
                if not chunk:
                    raise ValueError("recording_incomplete")
                if first:
                    if len(chunk)<12 or chunk[4:8]!=b"ftyp":
                        raise ValueError("invalid_mp4_header")
                    first=False
                output.write(chunk)
                remaining-=len(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp,destination)
        ensure_tables()
        now=datetime.utcnow().isoformat()
        with base.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old=conn.execute(
                "SELECT file_name FROM teacher_webapp_lesson_recordings WHERE "
                "teacher_telegram_user_id=? AND group_id=? AND schedule_slot_id=? AND occurrence_key=?",
                (int(uid),gid,slot_id,key),
            ).fetchone()
            old_name=old["file_name"] if old else ""
            conn.execute(
                "INSERT INTO teacher_webapp_lesson_recordings "
                "(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key,"
                "file_name,file_size,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(teacher_telegram_user_id,group_id,schedule_slot_id,occurrence_key) "
                "DO UPDATE SET file_name=excluded.file_name,file_size=excluded.file_size,"
                "updated_at=excluded.updated_at",
                (int(uid),gid,slot_id,key,name,length,now,now),
            )
            conn.commit()
        if old_name and old_name!=name:
            try:
                _file_path(old_name).unlink(missing_ok=True)
            except OSError:
                pass  # never roll back an already-saved replacement
        return {"ok":True,"has_file":True,"file_size":length}
    except (OSError,ValueError):
        destination.unlink(missing_ok=True)
        return {"ok":False,"error":"invalid_mp4_or_storage"}
    finally:
        temp.unlink(missing_ok=True)


def remove_file(uid,payload):
    ident,error=_identify(uid,payload)
    if error:
        return {"ok":False,"error":error}
    gid,slot_id,key=ident
    ensure_tables()
    with base.db() as conn:
        row=conn.execute(
            "SELECT file_name FROM teacher_webapp_lesson_recordings "
            "WHERE teacher_telegram_user_id=? AND group_id=? AND schedule_slot_id=? AND occurrence_key=?",
            (int(uid),gid,slot_id,key),
        ).fetchone()
        name=row["file_name"] if row else ""
        conn.execute(
            "UPDATE teacher_webapp_lesson_recordings SET file_name='',file_size=0,"
            "updated_at=? WHERE teacher_telegram_user_id=? AND group_id=? "
            "AND schedule_slot_id=? AND occurrence_key=?",
            (datetime.utcnow().isoformat(),int(uid),gid,slot_id,key),
        )
        conn.commit()
    if name:
        try:
            _file_path(name).unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok":True}


def _secret():
    value=os.getenv("TEACHER_PRODUCT_RECORDING_SIGNING_KEY","").strip() or base.BOT_TOKEN
    if not value or len(value)<16:
        raise RuntimeError("No secure PREPODMIN recording signing key")
    return value.encode("utf-8")


def ticket(uid,payload):
    ident,error=_identify(uid,payload)
    if error:
        return {"ok":False,"error":error}
    row=_row(uid,*ident)
    if not row or not row["file_name"]:
        return {"ok":False,"error":"recording_not_found"}
    expires=int(time.time())+_TICKET_LIFETIME
    content=f"{int(uid)}.{int(row['id'])}.{expires}"
    signature=hmac.new(_secret(),content.encode(),hashlib.sha256).hexdigest()
    return {"ok":True,"url":f"/api/teacher/recording/file/{int(row['id'])}?token={content}.{signature}"}


def serve(handler,recording_id,token):
    """Return 404 for all unauthorized requests, support HTML5 video byte ranges."""
    try:
        parts=token.split(".")
        if len(parts)!=4:
            raise ValueError()
        uid,embedded_id,expires=map(int,parts[:3])
        if embedded_id!=int(recording_id) or expires<int(time.time()) or expires>int(time.time())+_TICKET_LIFETIME:
            raise ValueError()
        message=".".join(parts[:3])
        expected=hmac.new(_secret(),message.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,parts[3]):
            raise ValueError()
        ensure_tables()
        with base.db() as conn:
            row=conn.execute(
                "SELECT * FROM teacher_webapp_lesson_recordings "
                "WHERE id=? AND teacher_telegram_user_id=?",(embedded_id,uid),
            ).fetchone()
        if not row or not row["file_name"] or not groups.get_group(uid,int(row["group_id"])):
            raise ValueError()
        path=_file_path(row["file_name"])
        if path.is_symlink() or not path.is_file():
            raise ValueError()
        total=path.stat().st_size
        if total<12:
            raise ValueError()
    except (ValueError,RuntimeError,TypeError,OSError):
        handler._send(404,b"Recording unavailable","text/plain; charset=utf-8")
        return
    first,last=0,total-1
    range_header=handler.headers.get("Range","")
    if range_header:
        match=_RANGE_RE.fullmatch(range_header.strip())
        if not match:
            handler._send(416,b"Invalid range","text/plain; charset=utf-8")
            return
        first=int(match.group(1))
        last=int(match.group(2)) if match.group(2) else total-1
        if first>=total or last<first or last>=total:
            handler._send(416,b"Invalid range","text/plain; charset=utf-8")
            return
    amount=last-first+1
    handler.send_response(206 if range_header else 200)
    handler.send_header("Content-Type","video/mp4")
    handler.send_header("Content-Length",str(amount))
    handler.send_header("Accept-Ranges","bytes")
    if range_header:
        handler.send_header("Content-Range",f"bytes {first}-{last}/{total}")
    handler.send_header("Content-Disposition",'inline; filename="lesson-recording.mp4"')
    handler.send_header("Cache-Control","private, no-store")
    handler.send_header("Referrer-Policy","no-referrer")
    handler.send_header("X-Content-Type-Options","nosniff")
    handler.end_headers()
    try:
        with path.open("rb") as stream:
            stream.seek(first)
            remaining=amount
            while remaining:
                block=stream.read(min(256*1024,remaining))
                if not block:
                    break
                handler.wfile.write(block)
                remaining-=len(block)
    except (BrokenPipeError,ConnectionResetError):
        pass  # browser stopped playback
