"""October 2026 exception and one-off course reminder. No external secrets."""
from __future__ import annotations

import html
import re
import sqlite3
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from contextlib import contextmanager

TZ = ZoneInfo('Europe/Moscow')
MONTH = '2026-10'
COURSE = '6a8c4641d6c9f299cf1387a6'
NOTICE_AT = datetime(2026, 10, 27, 19, tzinfo=TZ)
NOTICE_END = datetime(2026, 10, 28, tzinfo=TZ)
CUTOFF = datetime(2026, 11, 5, tzinfo=TZ)  # exclusive: all of November 4
CLOSE_AT = datetime(2026, 11, 5, 9, tzinfo=TZ)  # retain existing close hour
START = datetime(2026, 10, 1, tzinfo=TZ)
NOTICE_KEY = 'october-2026-rules-20261027'
_INSTALLED = False

MESSAGE = '''Ребята, итоги октября подведём 5 ноября 💗 В этот же день объявим «Ученика месяца», «Прорыв месяца» и проведём розыгрыш скидки.

📝 Пробник пишем 31 октября. Он войдёт в октябрьские итоги — перенос нужен, чтобы я успела проверить ваши работы и учесть результаты.

⏳ Закрыть октябрьские долги можно до 4 ноября включительно, 23:59 по Москве.

🎁 Условия участия в розыгрыше скидки 5% на ноябрь:
• помесячная оплата обучения;
• все октябрьские ДЗ закрыты;
• итоговые ДЗ выполнены минимум на 80%;
• по каждому назначенному тренажёру завершено минимум 3 тренировки;
• результаты октябрьских пробников — от 61 балла.

Учитываются только назначенные мной тренажёры. Проходить весь каталог не нужно 💗 Победителя розыгрыша выберем случайным образом среди выполнивших все условия.

🏆 «Ученик месяца» — по совокупности результатов: своевременность ДЗ, назначенные тренировки, участие и личный прогресс в пробниках, отсутствие долгов. Поздняя сдача закрывает долг, но не превращает работу в сданную вовремя.

🚀 «Прорыв месяца» — за рост относительно собственных прошлых результатов и заметные изменения в работе.

💳 Оплата ноября — до 7 ноября включительно. Розыгрыш пройдёт раньше, чтобы победитель мог учесть скидку при оплате.

Проверьте свой прогресс в личном кабинете бота. Если выполненная работа или тренировка не отобразилась — напишите мне до подведения итогов 🐶'''

SCHEMA = '''
CREATE TABLE IF NOT EXISTS october_2026_deliveries (
 campaign TEXT NOT NULL, kind TEXT NOT NULL, recipient_id INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','sent','failed','uncertain','cancelled')),
 message_id INTEGER, updated_at TEXT NOT NULL,
 PRIMARY KEY(campaign,kind,recipient_id)
);
CREATE TABLE IF NOT EXISTS october_2026_config (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
);
'''


def now():
    return datetime.now(TZ)


def scheduled_close_key(at):
    at = at.astimezone(TZ)
    if CLOSE_AT <= at and at.year == 2026 and at.month == 11:
        return MONTH
    if at.day != 1 or at.time() < time(9):
        return None
    previous = (at.date().replace(day=1).toordinal() - 1)
    key = date.fromordinal(previous).strftime('%Y-%m')
    return None if key == MONTH else key


def blocked(key, at=None):
    return key == MONTH and (at or now()) < CLOSE_AT


@contextmanager
def _connect(kr):
    conn = sqlite3.connect(kr.bot.COREAPP_DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _dt(kr, value):
    parsed = kr._parse_dt(value)
    return parsed.astimezone(TZ) if parsed else None


def _condition(code, label, items):
    return {'code': code, 'label': label, 'earned': sum(bool(x['done']) for x in items),
            'total': len(items), 'done': all(x['done'] for x in items),
            'missing': [x['label'] for x in items if not x['done']]}


def conditions(kr, student, card):
    """Grace applies to draw eligibility only, never rewrites on-time awards."""
    sid, uid = int(student[0]), student[5]
    with _connect(kr) as conn:
        submissions = conn.execute('''SELECT received_at,user_id,lower(user_email),
            lesson_id,lesson_name,correct_count,total_count FROM homework_submissions
            WHERE julianday(received_at)>=julianday(?) AND julianday(received_at)<julianday(?)
            ORDER BY received_at''', (datetime(2026,9,1,tzinfo=TZ).isoformat(), CUTOFF.isoformat())).fetchall()
        own = [r for r in submissions if kr._student_matches_submission(student, r[1], r[2])]
        hw = []
        for source_no, source_date in enumerate(tuple(kr.deadlines._course_dates()), 1):
            due = kr.deadlines.due_lesson_for_source(source_date)
            if not due:
                continue
            due_date, due_no = due
            in_month = START.date() <= due_date <= date(2026, 10, 31)
            crossing = (START.date() <= source_date <= date(2026, 10, 31)
                        and date(2026, 11, 1) <= due_date < CUTOFF.date())
            if not (in_month or crossing):
                continue
            done = any(kr.deadlines._explicit_match(r[3], r[4], due_no, source_no, source_date)
                       for r in own)
            hw.append({'done': done, 'label': f'ДЗ после урока №{source_no}'})
        finals = []
        for item in kr._final_catalog():
            lid = str(item['lesson_id'])
            title = re.sub(r'\s+', ' ', str(item['title']).casefold().replace('ё', 'е')).strip()
            def matches(row):
                name = re.sub(r'\s+', ' ', str(row[4] or '').casefold().replace('ё', 'е')).strip()
                return str(row[3] or '').strip() == lid or bool(title and name and
                    (name == title or title in name or name in title))
            relevant = [r for r in submissions if matches(r)]
            # Freeze October's evidenced task set; November-only work is not added.
            if not any(START <= (_dt(kr, r[0]) or CUTOFF) < datetime(2026,11,1,tzinfo=TZ) for r in relevant):
                continue
            best = 0
            for row in own:
                if matches(row):
                    try:
                        correct, total = float(str(row[5]).replace(',', '.')), float(str(row[6]).replace(',', '.'))
                        if total > 0:
                            best = max(best, 100 * correct / total)
                    except (ValueError, TypeError):
                        pass
            finals.append({'done': best >= 80, 'label': item['title'] + ': нужно 80%+'})
        trainers = []
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for item in card['categories']['trainers']['items']:
            if item.get('excluded_from_requirement'):
                continue
            code = str(item['code'])
            if code in getattr(kr, 'MONTHLY_EXCLUDED_TRAINERS', {'decomposition'}):
                continue
            table = kr.TRAINER_TABLES.get(code, f'{code}_sessions')
            count = int(item.get('sessions') or 0)
            if uid is not None and table in tables and re.fullmatch(r'[A-Za-z0-9_]+', table):
                # Carry only an existing October topic into the grace interval.
                # Historical monthly counts retain their assignment policy.
                extra = conn.execute(f'''SELECT count(*) FROM {table} s
                    WHERE s.telegram_user_id=? AND s.finished_at IS NOT NULL
                    AND julianday(s.finished_at)>=julianday(?) AND julianday(s.finished_at)<julianday(?)
                    AND EXISTS (SELECT 1 FROM ege11_trainer_assignment_periods p
                        WHERE p.code=? AND julianday(s.finished_at)>=julianday(p.starts_at)
                        AND (p.ends_at IS NULL OR julianday(s.finished_at)<julianday(p.ends_at)))''',
                    (int(uid), datetime(2026,11,1,tzinfo=TZ).isoformat(), CUTOFF.isoformat(), code)).fetchone()[0]
                count += int(extra)
            trainers.append({'done': count >= 3, 'label': f"{item['title']}: ещё {max(0,3-count)} тренировок"})
    exams = [{'done': bool(x.get('score') is not None and float(x['score']) >= 61),
              'label': f"{x['event']} ({x['date']}): нужно 61+"}
             for x in card['categories']['probnik']['items']]
    has_31 = any(str(x.get('date')) in ('31.10.2026', '2026-10-31')
                 for x in card['categories']['probnik']['items'])
    if not has_31:
        exams.append({'done': False, 'label': 'Пробник 31 октября: результат ещё не внесён'})
    return [_condition('homework','Октябрьские ДЗ закрыты до 4 ноября',hw),
            _condition('final','Итоговые ДЗ 80%+',finals),
            _condition('trainers','Назначенные тренажёры: 3+ завершённых тренировки',trainers),
            _condition('probnik','Октябрьские пробники 61+',exams)]


def status_from_card(kr, student, card):
    items = conditions(kr, student, card)
    monthly = bool(card.get('monthly_payment'))
    # Existing draw rows are not modified by this exception.
    return {'month': MONTH, 'label': 'Октябрь 2026', 'monthly_payment': monthly,
            'eligible': monthly and all(x['done'] for x in items),
            'remaining_count': sum(not x['done'] for x in items), 'conditions': items,
            'cutoff': CUTOFF.isoformat(), 'cutoff_label': '4 ноября · 23:59 МСК',
            'draw_done': False, 'winner': False, 'discount_percent': 5,
            'payment_due_label': '7 ноября', 'window_open': now() < CUTOFF}


def _queue(kr, campaign, kind, recipient):
    with _connect(kr) as conn:
        conn.execute('''INSERT OR IGNORE INTO october_2026_deliveries
            (campaign,kind,recipient_id,status,updated_at) VALUES(?,?,?,'pending',?)''',
            (campaign,kind,int(recipient),now().isoformat()))


async def _send_once(kr, context, campaign, kind, recipient, text, thread=None):
    with _connect(kr) as conn:
        conn.execute('BEGIN IMMEDIATE')
        claimed = conn.execute('''UPDATE october_2026_deliveries SET status='sending',updated_at=?
            WHERE campaign=? AND kind=? AND recipient_id=? AND status='pending' ''',
            (now().isoformat(),campaign,kind,int(recipient))).rowcount
    if not claimed:
        return False
    kwargs = {'chat_id':int(recipient),'text':text}
    if thread:
        kwargs['message_thread_id'] = int(thread)
    try:
        message = await context.bot.send_message(**kwargs)
    except Exception as error:
        # Ambiguous network failures must never be retried automatically.
        state = 'failed' if type(error).__name__ in ('Forbidden','BadRequest') else 'uncertain'
        with _connect(kr) as conn:
            conn.execute('''UPDATE october_2026_deliveries SET status=?,updated_at=?
                WHERE campaign=? AND kind=? AND recipient_id=?''',
                (state,now().isoformat(),campaign,kind,int(recipient)))
        print('October campaign delivery: '+state+' '+type(error).__name__,flush=True)
        return False
    with _connect(kr) as conn:
        conn.execute('''UPDATE october_2026_deliveries SET status='sent',message_id=?,updated_at=?
            WHERE campaign=? AND kind=? AND recipient_id=?''',
            (message.message_id,now().isoformat(),campaign,kind,int(recipient)))
    return True


async def campaign_tick(kr, context):
    at = now()
    if not NOTICE_AT <= at < NOTICE_END:
        return
    with _connect(kr) as conn:
        settings = dict(conn.execute('SELECT key,value FROM october_2026_config'))
        if settings.get('enabled') != '1':
            return
        rows = conn.execute('''SELECT DISTINCT q.recipient_id,q.kind FROM october_2026_deliveries q
            WHERE q.campaign=? AND q.status='pending' ORDER BY q.kind,q.recipient_id''',
            (NOTICE_KEY,)).fetchall()
        active = {int(r[0]) for r in conn.execute('''SELECT DISTINCT telegram_user_id FROM students
            WHERE active=1 AND course_id=? AND telegram_user_id IS NOT NULL''',(COURSE,))}
    chat = int(settings['chat_id'])
    if chat >= 0 or chat == -1004449482685:
        raise ValueError('OCTOBER_WRONG_COURSE_CHAT')
    if not rows:
        return
    info = await context.bot.get_chat(chat)
    if info.type not in ('group','supergroup'):
        raise ValueError('OCTOBER_WRONG_CHAT_TYPE')
    for row in rows:
        uid, kind = int(row[0]), row[1]
        if kind not in ('course','student'):
            raise ValueError('OCTOBER_UNEXPECTED_RECIPIENT_KIND')
        if kind == 'student' and uid not in active:
            with _connect(kr) as conn:
                conn.execute("UPDATE october_2026_deliveries SET status='cancelled' WHERE campaign=? AND kind=? AND recipient_id=? AND status='pending'",(NOTICE_KEY,kind,uid))
            continue
        if kind == 'course' and uid != chat:
            raise ValueError('OCTOBER_UNEXPECTED_CHAT')
        if kind == 'student':
            member = await context.bot.get_chat_member(chat,uid)
            if member.status in ('left','kicked'):
                print('October campaign: former chat member skipped',flush=True)
                continue
        await _send_once(kr,context,NOTICE_KEY,kind,uid,MESSAGE,
                         settings.get('thread_id') if kind == 'course' else None)


def probnik_ready(kr):
    with _connect(kr) as conn:
        return bool(conn.execute("SELECT 1 FROM probnik_results WHERE event_date IN ('31.10.2026','2026-10-31') AND secondary_score IS NOT NULL LIMIT 1").fetchone())


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    import kulek_rewards as kr
    kr._october_close_key = scheduled_close_key
    kr._october_probnik_ready = lambda: probnik_ready(kr)
    old_payload = kr.month_payload
    def payload(month_key=None, force=False, with_breakthrough=True):
        key = kr._month_key(month_key)
        result = old_payload(month_key, force=force, with_breakthrough=with_breakthrough)
        if key != MONTH:
            return result
        students = {int(x[0]):x for x in kr._student_rows()}
        for card in result['students']:
            card['draw_eligible'] = status_from_card(kr,students[int(card['id'])],card)['eligible']
        result['eligible_draw_count'] = sum(bool(c['draw_eligible']) for c in result['students'])
        return result
    kr.month_payload = payload
    old_status = kr.discount_status
    def discount_status(sid, month_key=kr.SEPTEMBER_DISCOUNT_KEY):
        key = kr._month_key(month_key)
        if key != MONTH:
            return old_status(sid,month_key)
        student = next((x for x in kr._student_rows() if int(x[0]) == int(sid)),None)
        data = kr.month_payload(key,with_breakthrough=False)
        card = next((x for x in data['students'] if int(x['id']) == int(sid)),None)
        if not student or not card:
            return None
        status = status_from_card(kr,student,card)
        draw = data.get('draw')
        status['draw_done'] = bool(draw)
        status['winner'] = bool(draw and int(draw['student_id']) == int(sid))
        return status
    kr.discount_status = discount_status
    old_active_status = kr.active_discount_status
    kr.active_discount_status = lambda sid: (discount_status(sid,MONTH)
        if START <= now() < datetime(2026,11,8,tzinfo=TZ) else old_active_status(sid))
    old_cutoff = kr._discount_cutoff
    kr._discount_cutoff = lambda key: CLOSE_AT if kr._month_key(key) == MONTH else old_cutoff(key)
    for name in ('choose_student_of_month','choose_breakthrough','draw_discount','freeze_discount_pool'):
        original = getattr(kr,name)
        def guarded(*args,_original=original,**kwargs):
            key = kr._month_key(args[0] if args else kwargs.get('month_key'))
            if blocked(key) or (key == MONTH and not probnik_ready(kr)):
                return {'ok':False,'error':'month_not_closed','cutoff':CLOSE_AT.isoformat()}
            return _original(*args,**kwargs)
        setattr(kr,name,guarded)
    old_callback = kr.live79.live23.cabinet_callback
    async def cabinet_callback(update,context):
        query = update.callback_query
        data = str(query.data or '') if query else ''
        parts = data.split(':')
        if (len(parts)>=4 and parts[:2]==['cab','kulek'] and parts[3]==MONTH
                and parts[2] in ('studentmonthpick','breakthroughpick','draw')
                and kr.live79.live23._admin_private(update)):
            if blocked(MONTH) or not probnik_ready(kr):
                await query.answer('Итоги октября — 5 ноября, после внесения результатов пробника 31 октября.',show_alert=True)
                return
        return await old_callback(update,context)
    kr.live79.live23.cabinet_callback = cabinet_callback
    old_announce = kr.announce_breakthrough_course
    async def announce(context,key):
        if blocked(kr._month_key(key)):
            return False
        return await old_announce(context,key)
    kr.announce_breakthrough_course = announce
    old_notice = kr.discount_notice_text
    def notice(sid,key=kr.SEPTEMBER_DISCOUNT_KEY):
        if kr._month_key(key) != MONTH:
            return old_notice(sid,key)
        status = discount_status(sid,MONTH)
        if not status or not status['monthly_payment']:
            return ''
        lines = ['🎁 <b>Розыгрыш скидки 5% — 5 ноября</b>',
                 'Октябрьские долги — до 4 ноября включительно. Оплата ноября — до 7 ноября.', '']
        for item in status['conditions']:
            lines.append(('✅ ' if item['done'] else '🟡 ') + html.escape(item['label'])
                         + ': ' + str(item['earned']) + '/' + str(item['total']))
            lines.extend('• '+html.escape(x) for x in item['missing'])
        return '\n'.join(lines)
    kr.discount_notice_text = notice
    old_pool_text = kr.discount_pool_text
    def pool_text(key=kr.SEPTEMBER_DISCOUNT_KEY):
        if kr._month_key(key) == MONTH and blocked(MONTH):
            return '🎁 Итоги октября и розыгрыш — 5 ноября. Долги закрываем до 4 ноября включительно.'
        return old_pool_text(key)
    kr.discount_pool_text = pool_text
    old_tick = kr.discount_draw_tick
    async def tick(context):
        await old_tick(context)
        await campaign_tick(kr,context)
        if now() >= CLOSE_AT and now().strftime('%Y-%m') == '2026-11':
            admin = kr.bot.get_admin_id()
            if admin:
                _queue(kr,'october-2026-draw-ready','admin',int(admin))
                await _send_once(kr,context,'october-2026-draw-ready','admin',int(admin),
                    'Итоги октября назначены на 5 ноября. Проверь внесение результатов пробника 31 октября. '
                    'Розыгрыш скидки 5% на ноябрь запускается вручную в Кулёчки → Октябрь → Рандомайзер. '
                    'Оплата ноября — до 7 ноября включительно.')
    kr.discount_draw_tick = tick
    kr._CACHE.clear()
    _INSTALLED = True
    print('October 2026 close ready: notice=2026-10-27T19:00+03:00; cutoff=2026-11-05T00:00+03:00; results=2026-11-05T09:00+03:00',flush=True)
