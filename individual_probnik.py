"""Individual probnik results kept outside group students and parent identities."""
import math
import os
import re
import sqlite3
from datetime import datetime, timezone

FLAG = 'INDIVIDUAL_PROBNIK_ENABLED'
BUTTON = '📝 Пробники'
_live = None
_running = False


def enabled():
    return os.getenv(FLAG, '').strip() == '1'


def norm(value):
    return ' '.join(re.sub(r'[^a-zа-я0-9]+', ' ', str(value or '').lower().replace('ё', 'е')).split())


def number(value):
    if value is None or value == '':
        return None
    try:
        result = float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        raise ValueError('invalid_individual_score')
    if not math.isfinite(result) or result < 0:
        raise ValueError('invalid_individual_score')
    return result


def ensure_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS individual_probnik_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT, individual_id INTEGER NOT NULL,
        event_name TEXT NOT NULL, event_date TEXT NOT NULL,
        primary_score REAL, secondary_score REAL, tasks_json TEXT NOT NULL,
        synced_at TEXT NOT NULL, UNIQUE(individual_id,event_name,event_date))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS individual_probnik_notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, individual_id INTEGER NOT NULL,
        event_name TEXT NOT NULL, event_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', reason TEXT, sent_at TEXT,
        UNIQUE(individual_id,event_name,event_date))''')


def ordinary_rows(conn):
    return conn.execute('''SELECT id,
        coalesce(nullif(display_name,''),nullif(user_name,''),user_email,'Ученик'),
        user_name,user_email,coreapp_user_id,telegram_user_id
        FROM students WHERE active=1''').fetchall()


def split_payload(payload, individuals, regular, match_regular):
    group_sheets, prepared = [], []
    names = {}
    for sid, name, telegram_id, *_rest in individuals:
        names.setdefault(norm(name), []).append((sid, name, telegram_id))
    for sheet in payload.get('sheets') or []:
        name = str(sheet.get('student_name') or sheet.get('sheet_name') or '').strip()
        matches = names.get(norm(name), [])
        if not matches:
            possible = [(int(r[0]),r[1],r[1],'','',r[2]) for r in individuals]
            if any(match_regular(name,[row]) is not None for row in possible):
                raise ValueError('individual_sheet_requires_exact_name')
            group_sheets.append(sheet)
            continue
        # Never interpret the same source name as both an individual and a group pupil.
        if len(matches) != 1 or any(match_regular(name,[row]) is not None for row in regular):
            raise ValueError('ambiguous_individual_name')
        sid, _name, telegram = matches[0]
        if telegram is not None and any(row[5] is not None and int(row[5]) == int(telegram) for row in regular):
            raise ValueError('individual_telegram_also_in_group')
        for result in sheet.get('results') or []:
            if str(result.get('publication_status') or '').strip().lower() != 'опубликовано':
                continue
            event = str(result.get('event_name') or '').strip()
            day = str(result.get('event_date') or '').strip()
            if not event or not day:
                continue
            parsed = datetime.strptime(day, '%d.%m.%Y')
            day = parsed.strftime('%d.%m.%Y')
            primary, secondary = number(result.get('primary_score')), number(result.get('secondary_score'))
            tasks = result.get('tasks') or {}
            if not isinstance(tasks, dict):
                raise ValueError('invalid_individual_tasks')
            if primary is None and secondary is None and not any(v not in (None, '') for v in tasks.values()):
                continue
            prepared.append((int(sid),event,day,primary,secondary,tasks))
    return {**payload, 'sheets':group_sheets}, prepared


def save_individual_results(conn, rows):
    import json
    ensure_tables(conn)
    for sid,event,day,primary,secondary,tasks in rows:
        conn.execute('''INSERT INTO individual_probnik_results
            (individual_id,event_name,event_date,primary_score,secondary_score,tasks_json,synced_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(individual_id,event_name,event_date) DO UPDATE SET
            primary_score=excluded.primary_score,secondary_score=excluded.secondary_score,
            tasks_json=excluded.tasks_json,synced_at=excluded.synced_at''',
            (sid,event,day,primary,secondary,json.dumps(tasks,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
        if primary is not None or secondary is not None:
            conn.execute('''INSERT OR IGNORE INTO individual_probnik_notices
                (individual_id,event_name,event_date) VALUES(?,?,?)''',(sid,event,day))
    return len(rows),len({r[0] for r in rows})


def fmt(value):
    return str(int(value)) if float(value).is_integer() else str(round(float(value),2)).replace('.',',')


def results_text(conn, sid):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'individual_probnik_results' not in tables:
        return '📝 Пробники\n\nОпубликованных результатов пока нет.'
    rows = conn.execute('''SELECT event_name,event_date,primary_score,secondary_score
        FROM individual_probnik_results WHERE individual_id=?
          AND (primary_score IS NOT NULL OR secondary_score IS NOT NULL)
        ORDER BY substr(event_date,7,4) DESC,substr(event_date,4,2) DESC,
                 substr(event_date,1,2) DESC,id DESC LIMIT 10''',(sid,)).fetchall()
    lines = ['📝 Пробники','']
    for event,day,primary,secondary in rows:
        lines.append(f'{event} · {day}')
        if secondary is not None: lines.append(f'Вторичный балл: {fmt(secondary)}')
        if primary is not None: lines.append(f'Первичный балл: {fmt(primary)}')
        lines.append('')
    if not rows:lines.append('Опубликованных результатов пока нет.')
    return '\n'.join(lines).strip()


async def dispatch_pending(context):
    global _running
    if not enabled() or _running or _live is None:
        return
    _running=True
    try:
        with sqlite3.connect(_live.bot.COREAPP_DB_PATH) as conn:
            ensure_tables(conn)
            pending = conn.execute('''SELECT id,individual_id,event_name,event_date
                FROM individual_probnik_notices WHERE status='pending' ORDER BY id LIMIT 30''').fetchall()
        for nid,sid,event,day in pending:
            if not enabled():return
            with sqlite3.connect(_live.bot.COREAPP_DB_PATH) as conn:
                person = conn.execute('''SELECT display_name,telegram_user_id FROM individual_students
                    WHERE id=? AND active=1''',(sid,)).fetchone()
                score = conn.execute('''SELECT primary_score,secondary_score FROM individual_probnik_results
                    WHERE individual_id=? AND event_name=? AND event_date=?''',(sid,event,day)).fetchone()
                collision = (person and person[1] is not None and conn.execute(
                    'SELECT 1 FROM students WHERE telegram_user_id=? AND active=1',(person[1],)).fetchone())
            if person is None or collision or score is None or all(x is None for x in score):
                with sqlite3.connect(_live.bot.COREAPP_DB_PATH) as conn:
                    conn.execute("UPDATE individual_probnik_notices SET status='blocked',reason='identity_or_result_unavailable' WHERE id=?",(nid,))
                continue
            # Keep pending until the individual links her Telegram account.
            if person[1] is None:continue
            text = f'ЕГЭ БЛИЗКО\n\nОпубликован результат: {event} · {day}\n'
            if score[1] is not None:text+=f'\nВторичный балл: {fmt(score[1])}'
            if score[0] is not None:text+=f'\nПервичный балл: {fmt(score[0])}'
            text+='\n\nПосмотреть результаты: кнопка «📝 Пробники» в боте.'
            try:
                await context.bot.send_message(chat_id=int(person[1]),text=text,parse_mode=None)
            except Exception as exc:
                print('Individual probnik notice failed:',type(exc).__name__,flush=True)
                continue
            with sqlite3.connect(_live.bot.COREAPP_DB_PATH) as conn:
                conn.execute("UPDATE individual_probnik_notices SET status='sent',sent_at=? WHERE id=? AND status='pending'",(datetime.now(timezone.utc).isoformat(),nid))
    finally:
        _running=False


def install(live):
    """Called from live67 after its existing routers are installed; opt-in only."""
    global _live
    if not enabled() or getattr(live,'_individual_probnik_installed',False):return
    from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
    _live=live
    live._individual_probnik_installed=True
    live.INDIVIDUAL_KEYBOARD=ReplyKeyboardMarkup([['🧪 Тренажёры'],[BUTTON]],resize_keyboard=True)
    sync_owner=live.live24.live10
    previous_sync=sync_owner.save_probnik_sync
    def sync(payload):
        with sqlite3.connect(live.bot.COREAPP_DB_PATH) as conn:
            individuals=conn.execute('SELECT id,display_name,telegram_user_id FROM individual_students WHERE active=1').fetchall()
            regular=ordinary_rows(conn)
        groups,prepared=split_payload(payload,individuals,regular,live.live56.unique_probnik_student_match)
        # Validate all individual rows before delegating any group writes.
        rows,students=previous_sync(groups)
        if prepared:
            with sqlite3.connect(live.bot.COREAPP_DB_PATH) as conn:
                added,individuals_count=save_individual_results(conn,prepared)
                conn.execute('UPDATE probnik_sync_status SET last_rows=?,last_students=? WHERE id=1',(rows+added,students+individuals_count))
            return rows+added,students+individuals_count
        return rows,students
    sync_owner.save_probnik_sync=sync
    previous_start=live.live7.start_router
    previous_text=live.live7.student_text_router
    async def home(message,context,row):
        await message.reply_text('ЕГЭ БЛИЗКО\n\nДоступны тренажёры и результаты пробников.',reply_markup=live.INDIVIDUAL_KEYBOARD)
    async def start(update,context):
        if update.effective_chat.type=='private' and not context.args:
            row=live._individual_by_telegram(update.effective_user.id)
            if row:return await home(update.effective_message,context,row)
        return await previous_start(update,context)
    async def text(update,context):
        if update.effective_chat.type=='private' and update.effective_message and update.effective_message.text==BUTTON:
            row=live._individual_by_telegram(update.effective_user.id)
            if row:
                with sqlite3.connect(live.bot.COREAPP_DB_PATH) as conn:response=results_text(conn,int(row[0]))
                return await update.effective_message.reply_text(response,reply_markup=live.INDIVIDUAL_KEYBOARD,parse_mode=None)
        return await previous_text(update,context)
    live.live7.start_router=start
    live.live7.student_text_router=text
    def admin_text():
        rows=live._individual_rows()
        return f'👤 Индивидуальные ученики\n\nВсего: {len(rows)}\n\nДоступны тренажёры и пробники. Вкладку таблицы называйте точно как ученика в этом списке.'
    live._individuals_text=admin_text
    previous_callback=live.live23.cabinet_callback
    async def callback(update,context):
        q=update.callback_query
        if q and live.live23._admin_private(update):
            parts=str(q.data or '').split(':')
            if len(parts)==4 and parts[:3]==['cab','individual','probnik'] and parts[3].isdigit():
                row=live._individual_by_id(int(parts[3]))
                if row:
                    with sqlite3.connect(live.bot.COREAPP_DB_PATH) as conn:response=results_text(conn,int(row[0]))
                    await q.answer()
                    return await q.message.reply_text(response,parse_mode=None)
            if len(parts)==3 and parts[:2]==['cab','individual'] and parts[2].isdigit():
                row=live._individual_by_id(int(parts[2]))
                if row:
                    await q.answer()
                    buttons=[[InlineKeyboardButton(BUTTON,callback_data=f'cab:individual:probnik:{row[0]}')],
                             [InlineKeyboardButton('🔗 Ссылка подключения',callback_data=f'cab:individual:link:{row[0]}')],
                             [InlineKeyboardButton('← К списку',callback_data='cab:individuals')]]
                    if row[2] is not None:buttons.insert(1,[InlineKeyboardButton('🧪 Отправить тренажёры',callback_data=f'cab:individual:send:{row[0]}')])
                    return await q.edit_message_text(f'👤 {row[1]}\n\nТренажёры и пробники подключены.',reply_markup=InlineKeyboardMarkup(buttons))
        return await previous_callback(update,context)
    live.live23.cabinet_callback=callback
