"""Opt-in result messages to parents linked to the matched student.

No import-time database access. Activation requires an explicit UTC cutoff;
old student notices are not replayed automatically.
"""
import math
import os
import sqlite3
from datetime import datetime, timezone

FLAG = 'PROBNIK_PARENT_NOTIFY_ENABLED'
SINCE = 'PROBNIK_PARENT_NOTIFY_SINCE'
_running = False


def cutoff():
    if os.getenv(FLAG, '').strip() != '1' or os.getenv('PROBNIK_RESULT_NOTIFY_ENABLED', '').strip() != '1':
        return None
    try:
        value = datetime.fromisoformat(os.environ[SINCE])
        if value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc).isoformat()
    except (KeyError, ValueError):
        return None


def ensure_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS probnik_parent_notice_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_fingerprint TEXT NOT NULL,
        student_id INTEGER NOT NULL,
        parent_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        sent_at TEXT, reason TEXT,
        UNIQUE(source_fingerprint, student_id, parent_id))''')


def parent_ids(conn, student_id):
    columns = {r[1] for r in conn.execute('PRAGMA table_info(parent_links)')}
    field = ('parent_telegram_user_id' if 'parent_telegram_user_id' in columns
             else 'telegram_user_id' if 'telegram_user_id' in columns else None)
    if field is None or not {'student_id', 'active'} <= columns:
        return []
    # The column name is chosen exclusively from the two literal names above.
    rows = conn.execute(f'SELECT DISTINCT {field} FROM parent_links WHERE student_id=? AND active=1', (student_id,))
    result = []
    for row in rows:
        try:
            uid = int(row[0])
            if uid > 0:
                result.append(uid)
        except (TypeError, ValueError):
            continue
    return result


def score_text(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return str(int(number)) if number.is_integer() else str(round(number, 2)).replace('.', ',')


def message(name, event, day, primary, secondary):
    p, s = score_text(primary), score_text(secondary)
    if p is None and s is None:
        return None
    lines = ['ЕГЭ БЛИЗКО', '', 'Опубликован результат пробного экзамена.',
             f'Ученик: {name}', f'{event} · {day}', '']
    if s is not None:
        lines.append(f'Вторичный балл: {s}')
    if p is not None:
        lines.append(f'Первичный балл: {p}')
    lines += ['', 'Подробности доступны в родительском кабинете → «Пробники».']
    return '\n'.join(lines)


async def dispatch_pending(context):
    global _running
    since = cutoff()
    if since is None or _running:
        return
    _running = True
    try:
        await _dispatch(context, since)
    finally:
        _running = False


async def _dispatch(context, since):
    import run_bot_live56 as live56
    db = live56.bot.COREAPP_DB_PATH
    students = live56._all_active_students()
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'probnik_result_notice_queue', 'probnik_results', 'parent_links'} <= tables:
            return
        ensure_tables(conn)
        sources = conn.execute('''SELECT fingerprint,student_name FROM probnik_result_notice_queue
            WHERE created_at>=? AND status IN ('pending','sent','blocked')''', (since,)).fetchall()
        for fingerprint, name in sources:
            student = live56.unique_probnik_student_match(name, students)
            if student is None:
                continue
            for parent in parent_ids(conn, int(student[0])):
                conn.execute('''INSERT OR IGNORE INTO probnik_parent_notice_queue
                    (source_fingerprint,student_id,parent_id) VALUES (?,?,?)''',
                    (fingerprint, int(student[0]), parent))
        pending = conn.execute('''SELECT q.id,q.student_id,q.parent_id,n.student_name,n.event_name,n.event_date
            FROM probnik_parent_notice_queue q JOIN probnik_result_notice_queue n
            ON n.fingerprint=q.source_fingerprint
            WHERE q.status='pending' AND n.created_at>=?
              AND n.status IN ('pending','sent','blocked') ORDER BY q.id LIMIT 30''', (since,)).fetchall()

    for notice_id, sid, parent, name, event, day in pending:
        # Recheck identities and the current parent link just before sending.
        student = live56.unique_probnik_student_match(name, live56._all_active_students())
        with sqlite3.connect(db) as conn:
            linked = parent in parent_ids(conn, sid)
            row = conn.execute('''SELECT primary_score,secondary_score FROM probnik_results
                WHERE student_name=? AND event_name=? AND event_date=?''', (name, event, day)).fetchone()
        text = message(name, event, day, *row) if row else None
        if student is None or int(student[0]) != sid or not linked or text is None:
            status, reason = 'cancelled', 'identity_link_or_result_unavailable'
        else:
            # Honor a switched-off flag before every outgoing message.
            if cutoff() is None:
                return
            try:
                await context.bot.send_message(chat_id=parent, text=text, parse_mode=None)
            except Exception as exc:
                print('Probnik parent notice failed:', type(exc).__name__, flush=True)
                continue
            status, reason = 'sent', None
        with sqlite3.connect(db) as conn:
            conn.execute('''UPDATE probnik_parent_notice_queue SET status=?,reason=?,sent_at=?
                WHERE id=? AND status='pending' ''',
                (status, reason, datetime.now(timezone.utc).isoformat() if status == 'sent' else None, notice_id))
