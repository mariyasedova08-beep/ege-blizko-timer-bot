"""Persistent progress and resumable sessions for EGE task 6."""

import json
import random
import re
import sqlite3
from datetime import datetime

from ege_task6_bank import TASK6_BANK

TASK_BY_ID = {str(item["id"]): item for item in TASK6_BANK}


def ensure_tables(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ege_task6_attempts(
                uid INTEGER NOT NULL,
                task_id TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                correct_checks INTEGER NOT NULL DEFAULT 0,
                wrong_checks INTEGER NOT NULL DEFAULT 0,
                first_try_correct INTEGER,
                last_correct INTEGER NOT NULL DEFAULT 0,
                last_answer_x TEXT NOT NULL DEFAULT '',
                last_answer_y TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL,
                PRIMARY KEY(uid,task_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ege_task6_sessions(
                uid INTEGER PRIMARY KEY,
                mode TEXT NOT NULL,
                order_json TEXT NOT NULL,
                current_index INTEGER NOT NULL DEFAULT 0,
                selected_x TEXT NOT NULL DEFAULT '',
                selected_y TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL
            )"""
        )
        conn.commit()


def _now(tz):
    return datetime.now(tz).isoformat()


def _tags(task):
    text = str(task.get("text") or "").casefold().replace("ё", "е")
    tags = []
    if "осад" in text:
        tags.append("осадки")
    if "газ" in text or "выделен" in text:
        tags.append("газы")
    if "нагрев" in text:
        tags.append("нагревание")
    if "избыт" in text:
        tags.append("избыток реагента")
    if "сильн" in text or "слаб" in text or "электролит" in text:
        tags.append("электролиты")
    if "ионн" in text or "h⁺" in text or "oh⁻" in text or "fe²⁺" in text or "f⁻" in text:
        tags.append("ионные уравнения")
    if (
        ("гидроксид алюмини" in text or "гидроксид цинк" in text)
        and ("раствор" in text or "осад" in text)
    ):
        tags.append("амфотерность")
    if not tags:
        tags.append("распознавание реакций")
    return list(dict.fromkeys(tags))


def progress(db_path, uid):
    ensure_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """SELECT task_id,attempts,correct_checks,wrong_checks,
                      first_try_correct,last_correct
               FROM ege_task6_attempts
               WHERE uid=?""",
            (int(uid),),
        ).fetchall()

    answered = len(rows)
    checks = sum(int(r[1] or 0) for r in rows)
    correct_checks = sum(int(r[2] or 0) for r in rows)
    correct_last = sum(1 for r in rows if int(r[5] or 0))
    first_try_correct = sum(1 for r in rows if int(r[4] or 0) == 1)
    error_ids = [str(r[0]) for r in rows if int(r[3] or 0) > 0]

    weak_counts = {}
    for task_id, attempts, correct, wrong, first_try, last_correct in rows:
        wrong = int(wrong or 0)
        if not wrong:
            continue
        task = TASK_BY_ID.get(str(task_id))
        if not task:
            continue
        for tag in _tags(task):
            weak_counts[tag] = weak_counts.get(tag, 0) + wrong

    weak_types = [
        {"type": name, "errors": count}
        for name, count in sorted(
            weak_counts.items(), key=lambda item: (-item[1], item[0])
        )[:4]
    ]

    return {
        "total": len(TASK6_BANK),
        "answered": answered,
        "correct_tasks": correct_last,
        "checks": checks,
        "correct_checks": correct_checks,
        "accuracy": round(100 * correct_checks / checks) if checks else 0,
        "first_try_correct": first_try_correct,
        "first_try_accuracy": round(100 * first_try_correct / answered) if answered else 0,
        "error_task_ids": error_ids,
        "error_count": len(error_ids),
        "weak_types": weak_types,
    }


def build_order(mode, error_ids=None):
    mode = str(mode or "10")
    all_ids = [str(item["id"]) for item in TASK6_BANK]
    clean_ids = [
        str(item["id"]) for item in TASK6_BANK if not bool(item.get("needs_review"))
    ]
    rng = random.SystemRandom()

    if mode == "errors":
        allowed = set(all_ids)
        items = [str(x) for x in (error_ids or []) if str(x) in allowed]
        rng.shuffle(items)
        return items
    if mode == "all":
        items = list(all_ids)
        rng.shuffle(items)
        return items

    count = 20 if mode == "20" else 10
    items = list(clean_ids)
    rng.shuffle(items)
    return items[:count]


def load_session(db_path, uid):
    ensure_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """SELECT mode,order_json,current_index,selected_x,selected_y,updated
               FROM ege_task6_sessions WHERE uid=?""",
            (int(uid),),
        ).fetchone()
    if not row:
        return None
    try:
        order = [str(x) for x in json.loads(row[1] or "[]")]
    except Exception:
        order = []
    order = [task_id for task_id in order if task_id in TASK_BY_ID]
    return {
        "mode": str(row[0] or "10"),
        "order": order,
        "current_index": max(0, min(int(row[2] or 0), len(order))),
        "selected_x": str(row[3] or ""),
        "selected_y": str(row[4] or ""),
        "updated": str(row[5] or ""),
    }


def start_session(db_path, uid, mode, tz):
    ensure_tables(db_path)
    p = progress(db_path, uid)
    order = build_order(mode, p["error_task_ids"])
    now = _now(tz)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO ege_task6_sessions(
                   uid,mode,order_json,current_index,selected_x,selected_y,updated
               ) VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(uid) DO UPDATE SET
                   mode=excluded.mode,
                   order_json=excluded.order_json,
                   current_index=0,
                   selected_x='',
                   selected_y='',
                   updated=excluded.updated""",
            (int(uid), str(mode or "10"), json.dumps(order), 0, "", "", now),
        )
        conn.commit()
    return load_session(db_path, uid)


def save_selection(db_path, uid, selected_x, selected_y, tz):
    ensure_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """UPDATE ege_task6_sessions
               SET selected_x=?,selected_y=?,updated=?
               WHERE uid=?""",
            (str(selected_x or ""), str(selected_y or ""), _now(tz), int(uid)),
        )
        conn.commit()
    return load_session(db_path, uid)


def answer_key(task_id, answer_x, answer_y):
    task = TASK_BY_ID.get(str(task_id))
    if not task:
        return None
    correct = (
        str(answer_x or "") == str(task.get("answer_x") or "")
        and str(answer_y or "") == str(task.get("answer_y") or "")
    )
    return {
        "correct": bool(correct),
        "answer_x": str(task.get("answer_x") or ""),
        "answer_y": str(task.get("answer_y") or ""),
        "scored": not bool(task.get("needs_review")),
    }


def record_answer(db_path, uid, task_id, answer_x, answer_y, tz):
    result = answer_key(task_id, answer_x, answer_y)
    if not result:
        raise ValueError("unknown task")

    ensure_tables(db_path)
    if result["scored"]:
        now = _now(tz)
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """SELECT attempts,first_try_correct
                   FROM ege_task6_attempts
                   WHERE uid=? AND task_id=?""",
                (int(uid), str(task_id)),
            ).fetchone()
            previous_attempts = int(row[0] or 0) if row else 0
            first_try = (
                int(row[1]) if row and row[1] is not None
                else (1 if result["correct"] else 0)
            )
            conn.execute(
                """INSERT INTO ege_task6_attempts(
                       uid,task_id,attempts,correct_checks,wrong_checks,
                       first_try_correct,last_correct,last_answer_x,last_answer_y,updated
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(uid,task_id) DO UPDATE SET
                       attempts=ege_task6_attempts.attempts+1,
                       correct_checks=ege_task6_attempts.correct_checks+excluded.correct_checks,
                       wrong_checks=ege_task6_attempts.wrong_checks+excluded.wrong_checks,
                       first_try_correct=COALESCE(ege_task6_attempts.first_try_correct,excluded.first_try_correct),
                       last_correct=excluded.last_correct,
                       last_answer_x=excluded.last_answer_x,
                       last_answer_y=excluded.last_answer_y,
                       updated=excluded.updated""",
                (
                    int(uid), str(task_id), 1,
                    1 if result["correct"] else 0,
                    0 if result["correct"] else 1,
                    first_try,
                    1 if result["correct"] else 0,
                    str(answer_x or ""), str(answer_y or ""), now,
                ),
            )
            # Advance the resumable session after a checked answer.
            conn.execute(
                """UPDATE ege_task6_sessions
                   SET current_index=MIN(current_index+1,
                       COALESCE(json_array_length(order_json),current_index+1)),
                       selected_x='',selected_y='',updated=?
                   WHERE uid=?""",
                (now, int(uid)),
            )
            conn.commit()
    else:
        # Ambiguous source item: do not count it, but still advance the session.
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """UPDATE ege_task6_sessions
                   SET current_index=current_index+1,
                       selected_x='',selected_y='',updated=?
                   WHERE uid=?""",
                (_now(tz), int(uid)),
            )
            conn.commit()

    result["progress"] = progress(db_path, uid)
    result["session"] = load_session(db_path, uid)
    return result
