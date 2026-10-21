"""Private, teacher-owned homework submissions for PREPODMIN.

Files never enter SQLite, Git, public web roots, Telegram, or EGE BLIZKO.
This module is inactive unless a separate protected server setting enables it.
"""
import hashlib
import hmac
import os
import re
import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import teacher_product_mvp as base
import teacher_product_learning as learning
import teacher_product_groups as groups
import teacher_product_webapp_homework as homework

MAX_BYTES = 8 * 1024 * 1024
MAX_FILES = 5
MAX_ATTEMPTS = 20
MAX_FILE_NAME = 120
TICKET_SECONDS = 15 * 60
_STORAGE_NAME = re.compile(r"[a-f0-9]{32}\.(?:pdf|png|jpg)\Z")
_RANGE = re.compile(r"bytes=(\d+)-(\d*)\Z")

def enabled():
    return os.getenv("TEACHER_PRODUCT_HOMEWORK_UPLOADS_ENABLED", "").strip() == "1"

def storage_root():
    location=os.getenv("TEACHER_PRODUCT_HOMEWORK_UPLOAD_DIR","").strip()
    if not location or not os.path.isabs(location):
        raise RuntimeError("PREPODMIN protected homework upload directory is not configured")
    folder=Path(location)
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise RuntimeError("Untrusted homework storage directory")
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if folder.is_symlink():
        raise RuntimeError("Symlinked homework directory")
    os.chmod(folder,0o700)
    return folder

def ensure_tables():
    homework.ensure_tables()
    with base.db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teacher_webapp_homework_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id INTEGER NOT NULL,
                teacher_telegram_user_id INTEGER NOT NULL,
                subject_kind TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('draft','submitted','revision','approved')),
                feedback TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                submitted_at TEXT,
                reviewed_at TEXT,
                UNIQUE(assignment_id,subject_kind,subject_id,attempt_number)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_teacher_webapp_hw_attempts_subject
            ON teacher_webapp_homework_attempts(assignment_id,subject_kind,subject_id,attempt_number)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teacher_webapp_homework_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER NOT NULL,
                stored_name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_teacher_webapp_hw_files_attempt ON teacher_webapp_homework_files(attempt_id,id)")
        conn.commit()

def _assignment_for_student(link,aid):
    uid=int(link["teacher_id"])
    a=learning._assignment(aid,uid)
    if not a or not int(a["active"]):
        return None
    if a["target_kind"]=="group":
        if link["kind"]!="group" or int(a["target_id"])!=int(link["group_id"]):
            return None
    else:
        if link["kind"]!="individual" or int(a["target_id"])!=int(link["student_id"]):
            return None
    if homework.mode_for_assignment(aid)!="attachment":
        return None
    kind=("individual" if link["kind"]=="individual" else "group_member")
    sid=int(link["student_id"] if kind=="individual" else link["id"])
    return a,kind,sid

def _latest(conn,aid,kind,sid):
    return conn.execute(
        "SELECT * FROM teacher_webapp_homework_attempts "
        "WHERE assignment_id=? AND subject_kind=? AND subject_id=? "
        "ORDER BY attempt_number DESC LIMIT 1",(aid,kind,sid)
    ).fetchone()

def _file_type(prefix):
    if prefix.startswith(b"%PDF-"):
        return "application/pdf","pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png","png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg","jpg"
    return None,None

def _files_for(conn,attempt_id):
    return [{
        "id":int(r["id"]),"name":r["display_name"],
        "media_type":r["media_type"],"size":int(r["size_bytes"]),
    } for r in conn.execute(
        "SELECT id,display_name,media_type,size_bytes FROM teacher_webapp_homework_files WHERE attempt_id=? ORDER BY id",
        (int(attempt_id),),
    ).fetchall()]

def upload(link,aid,stream,length,filename,claimed_type):
    """Stream a single authenticated student file without buffering its bytes."""
    if not enabled():
        return {"ok":False,"error":"uploads_disabled"}
    identity=_assignment_for_student(link,aid)
    if not identity:
        return {"ok":False,"error":"assignment_unavailable"}
    if type(length) is not int or not (12 <= length <= MAX_BYTES):
        return {"ok":False,"error":"file_size"}
    if len(filename)>MAX_FILE_NAME or not filename.strip():
        return {"ok":False,"error":"filename_invalid"}
    name=Path(filename).name.strip().replace("\r","").replace("\n","")
    if not name or len(name)>MAX_FILE_NAME or name in {".",".."}:
        return {"ok":False,"error":"filename_invalid"}
    if claimed_type.split(";",1)[0].lower().strip() not in (
        "application/pdf","image/png","image/jpeg","application/octet-stream"
    ):
        return {"ok":False,"error":"file_type"}
    folder=storage_root()
    if shutil.disk_usage(folder).free < length + 128 * 1024 * 1024:
        return {"ok":False,"error":"disk_full"}
    ensure_tables()
    a,kind,sid=identity
    token=secrets.token_hex(16)
    temp=folder/(token+".part")
    final=None
    try:
        fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,"wb") as target:
            prefix=stream.read(min(32,length))
            if not prefix or len(prefix)<12:
                raise ValueError("short_file")
            mime,ext=_file_type(prefix)
            if not mime:
                raise ValueError("bad_signature")
            final=folder/(token+"."+ext)
            target.write(prefix)
            left=length-len(prefix)
            while left>0:
                block=stream.read(min(256*1024,left))
                if not block:
                    raise ValueError("short_file")
                target.write(block)
                left-=len(block)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temp,final)
        now=datetime.utcnow().isoformat()
        with base.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prev=_latest(conn,int(a["id"]),kind,sid)
            if prev and prev["status"] in ("submitted","approved"):
                return {"ok":False,"error":"attempt_closed"}
            if prev and prev["status"]=="draft":
                attempt_id=int(prev["id"])
            else:
                number=int(prev["attempt_number"])+1 if prev else 1
                if number>MAX_ATTEMPTS:
                    return {"ok":False,"error":"too_many_attempts"}
                attempt_id=int(conn.execute(
                    "INSERT INTO teacher_webapp_homework_attempts "
                    "(assignment_id,teacher_telegram_user_id,subject_kind,subject_id,"
                    "attempt_number,status,created_at) VALUES(?,?,?,?,?,'draft',?)",
                    (int(a["id"]),int(link["teacher_id"]),kind,sid,number,now),
                ).lastrowid)
            num=conn.execute(
                "SELECT COUNT(*) FROM teacher_webapp_homework_files WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()[0]
            if num>=MAX_FILES:
                return {"ok":False,"error":"too_many_files"}
            conn.execute(
                "INSERT INTO teacher_webapp_homework_files "
                "(attempt_id,stored_name,display_name,media_type,size_bytes,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (attempt_id,final.name,name,mime,length,now),
            )
            conn.commit()
        return {"ok":True,"attempt_id":attempt_id,"name":name,"size":length}
    except (ValueError,OSError):
        return {"ok":False,"error":"upload_failed"}
    finally:
        temp.unlink(missing_ok=True)
        # Files not referenced by a committed row must never remain publicly accessible.
        if final and final.exists():
            with base.db() as conn:
                valid=conn.execute(
                    "SELECT 1 FROM teacher_webapp_homework_files WHERE stored_name=?",
                    (final.name,),
                ).fetchone()
            if not valid:
                final.unlink(missing_ok=True)

def submit(link,aid):
    if not enabled():
        return {"ok":False,"error":"uploads_disabled"}
    identity=_assignment_for_student(link,aid)
    if not identity:
        return {"ok":False,"error":"assignment_unavailable"}
    a,kind,sid=identity
    ensure_tables()
    with base.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        attempt=_latest(conn,int(a["id"]),kind,sid)
        if not attempt or attempt["status"]!="draft":
            return {"ok":False,"error":"no_draft"}
        files=conn.execute(
            "SELECT COUNT(*) FROM teacher_webapp_homework_files WHERE attempt_id=?",
            (int(attempt["id"]),),
        ).fetchone()[0]
        if files==0:
            return {"ok":False,"error":"no_files"}
        conn.execute(
            "UPDATE teacher_webapp_homework_attempts SET status='submitted',submitted_at=? "
            "WHERE id=? AND status='draft'",
            (datetime.utcnow().isoformat(),int(attempt["id"])),
        )
        conn.commit()
    return {"ok":True,"status":"submitted","attempt_id":int(attempt["id"])}

def review(uid,aid,mid,decision,feedback):
    if decision not in ("approved","revision"):
        return {"ok":False,"error":"invalid_review"}
    if not isinstance(feedback,str) or len(feedback.strip())>2000 or (decision=="revision" and not feedback.strip()):
        return {"ok":False,"error":"invalid_feedback"}
    a=learning._assignment(aid,uid)
    if (not a or not a["active"] or a["target_kind"]!="group"
            or not groups.get_group(uid,int(a["target_id"]))
            or homework.mode_for_assignment(aid)!="attachment"
            or not any(int(m["id"])==int(mid) for m in learning._members(uid,int(a["target_id"])))):
        return {"ok":False,"error":"assignment_unavailable"}
    ensure_tables()
    now=datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        attempt=_latest(conn,int(aid),"group_member",int(mid))
        if not attempt or attempt["status"]!="submitted":
            return {"ok":False,"error":"not_submitted"}
        conn.execute(
            "UPDATE teacher_webapp_homework_attempts "
            "SET status=?,feedback=?,reviewed_at=? WHERE id=? AND status='submitted'",
            (decision,feedback.strip(),now,int(attempt["id"])),
        )
        conn.execute(
            "UPDATE teacher_homework_status "
            "SET status=?,done_at=?,updated_at=? WHERE assignment_id=? "
            "AND subject_kind='group_member' AND subject_id=?",
            ("done" if decision=="approved" else "pending",now if decision=="approved" else None,now,int(aid),int(mid)),
        )
        if decision=="approved":
            conn.execute(
                "INSERT INTO teacher_webapp_homework_status_origin "
                "(assignment_id,subject_kind,subject_id,completed_by,updated_at) "
                "VALUES(?,'group_member',?,'teacher',?) "
                "ON CONFLICT(assignment_id,subject_kind,subject_id) "
                "DO UPDATE SET completed_by='teacher',updated_at=excluded.updated_at",
                (int(aid),int(mid),now),
            )
        conn.commit()
    return {"ok":True,"status":decision,"attempt_id":int(attempt["id"])}

def _descriptions_for_assignments(uid,ids,subject_kind=None,subject_id=None):
    ids=[int(x) for x in ids]
    if not ids:
        return {}
    ensure_tables()
    with base.db() as conn:
        marks=",".join("?" for _ in ids)
        cond="AND subject_kind=? AND subject_id=?" if subject_kind is not None else ""
        args=[int(uid),*ids]
        if subject_kind is not None: args.extend((subject_kind,int(subject_id)))
        rows=conn.execute(
            "SELECT * FROM teacher_webapp_homework_attempts "
            f"WHERE teacher_telegram_user_id=? AND assignment_id IN ({marks}) {cond} "
            "ORDER BY attempt_number DESC",args,
        ).fetchall()
        out={}
        for r in rows:
            key=(int(r["assignment_id"]),r["subject_kind"],int(r["subject_id"]))
            if key in out:
                continue
            out[key]={
                "attempt":int(r["attempt_number"]),
                "status":r["status"],"feedback":r["feedback"],
                "submitted_at":r["submitted_at"],
                "files":_files_for(conn,int(r["id"])),
            }
    return out

def for_teacher(uid,aids):
    return _descriptions_for_assignments(uid,aids)

def for_student(link,aids):
    kind="individual" if link["kind"]=="individual" else "group_member"
    sid=int(link["student_id"] if kind=="individual" else link["id"])
    return _descriptions_for_assignments(int(link["teacher_id"]),aids,kind,sid)

def _ticket_key():
    secret=os.getenv("TEACHER_PRODUCT_HOMEWORK_FILE_TICKET_KEY","").strip() or base.BOT_TOKEN
    if len(secret)<16:
        raise RuntimeError("Recording signing key is not configured")
    return secret.encode()

def file_ticket(uid,file_id):
    ensure_tables()
    with base.db() as conn:
        row=conn.execute(
            "SELECT a.teacher_telegram_user_id,h.active,h.target_id,f.id "
            "FROM teacher_webapp_homework_files f "
            "JOIN teacher_webapp_homework_attempts a ON a.id=f.attempt_id "
            "JOIN teacher_homework h ON h.id=a.assignment_id "
            "WHERE f.id=? AND a.teacher_telegram_user_id=?",
            (int(file_id),int(uid)),
        ).fetchone()
    if not row or not row["active"] or not groups.get_group(uid,int(row["target_id"])):
        return {"ok":False,"error":"file_unavailable"}
    exp=int(time.time())+TICKET_SECONDS
    message=f"{int(uid)}.{int(file_id)}.{exp}"
    sig=hmac.new(_ticket_key(),message.encode(),hashlib.sha256).hexdigest()
    return {"ok":True,"url":f"/api/teacher/homework/file/{int(file_id)}?ticket={message}.{sig}"}

def serve(handler,file_id,ticket):
    try:
        uid,id_text,expiry,sig=ticket.split(".",3)
        uid,fid,exp=int(uid),int(id_text),int(expiry)
        now=int(time.time())
        if fid!=int(file_id) or exp<now or exp>now+TICKET_SECONDS:
            raise ValueError()
        expected=hmac.new(_ticket_key(),f"{uid}.{fid}.{exp}".encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,expected):
            raise ValueError()
        ensure_tables()
        with base.db() as conn:
            row=conn.execute(
                "SELECT f.stored_name,f.media_type,h.active,h.target_id "
                "FROM teacher_webapp_homework_files f "
                "JOIN teacher_webapp_homework_attempts a ON a.id=f.attempt_id "
                "JOIN teacher_homework h ON h.id=a.assignment_id "
                "WHERE f.id=? AND a.teacher_telegram_user_id=?",
                (fid,uid),
            ).fetchone()
        if not row or not row["active"] or not groups.get_group(uid,int(row["target_id"])):
            raise ValueError()
        name=row["stored_name"]
        if not _STORAGE_NAME.fullmatch(name):
            raise ValueError()
        path=storage_root()/name
        if path.is_symlink() or not path.is_file():
            raise ValueError()
        total=path.stat().st_size
        if not total:
            raise ValueError()
    except (TypeError,ValueError,OSError,RuntimeError):
        handler._send(404,b"Not found","text/plain; charset=utf-8")
        return
    first,last=0,total-1
    range_header=handler.headers.get("Range","")
    if range_header:
        match=_RANGE.fullmatch(range_header)
        if not match:
            handler._send(416,b"Invalid range","text/plain; charset=utf-8")
            return
        first=int(match.group(1))
        last=int(match.group(2)) if match.group(2) else total-1
        if first>=total or last<first or last>=total:
            handler._send(416,b"Invalid range","text/plain; charset=utf-8")
            return
    handler.send_response(206 if range_header else 200)
    handler.send_header("Content-Type",row["media_type"])
    handler.send_header("Content-Length",str(last-first+1))
    handler.send_header("Cache-Control","private, no-store")
    handler.send_header("X-Content-Type-Options","nosniff")
    handler.send_header("Referrer-Policy","no-referrer")
    handler.send_header("Content-Security-Policy","sandbox")
    handler.send_header("Content-Disposition","inline; filename=homework-attachment")
    handler.send_header("Accept-Ranges","bytes")
    if range_header:handler.send_header("Content-Range",f"bytes {first}-{last}/{total}")
    handler.end_headers()
    try:
        with path.open("rb") as stream:
            stream.seek(first)
            count=last-first+1
            while count>0:
                part=stream.read(min(256*1024,count))
                if not part:break
                handler.wfile.write(part)
                count-=len(part)
    except (BrokenPipeError,ConnectionResetError):
        pass
