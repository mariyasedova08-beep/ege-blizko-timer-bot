"""Selective trainer notifications for confirmed OGE (grade 9) pupils.

Separate manually approved audience: never infer grade 9 from the existing
CoreApp students table, which also contains older students.
Installed after the final EGE BLIZKO runtime wrappers.
"""
import html
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, time

from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup

import run_bot_live90 as live90

bot = live90.bot
live23 = live90.live23
live7 = live90.live7
_previous_cabinet_markup = None
_previous_cabinet_callback = None
_previous_start_router = None
_previous_tick = None
_installed = False


def _db():
    return sqlite3.connect(bot.COREAPP_DB_PATH, timeout=20)


def ensure_tables():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS oge9_trainer_invite (
                id INTEGER PRIMARY KEY CHECK(id=1),
                code TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS oge9_trainer_members (
                telegram_user_id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                added_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS oge9_trainer_requests (
                telegram_user_id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                requested_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS oge9_trainer_campaigns (
                trainer_code TEXT PRIMARY KEY,
                mode TEXT NOT NULL CHECK(mode IN ('once','daily')),
                start_on TEXT NOT NULL,
                end_on TEXT NOT NULL,
                send_hour INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS oge9_trainer_deliveries (
                trainer_code TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                day_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(trainer_code,telegram_user_id,day_key)
            );
        """)


def _members():
    with _db() as conn:
        return conn.execute(
            "SELECT telegram_user_id, display_name FROM oge9_trainer_members ORDER BY lower(display_name)"
        ).fetchall()


def _trainers():
    with _db() as conn:
        try:
            return conn.execute(
                "SELECT code,title,start_param FROM weekly_trainer_catalog "
                "WHERE active=1 ORDER BY sort_order,title"
            ).fetchall()
        except sqlite3.OperationalError:
            return []


def _trainer(code):
    return next((r for r in _trainers() if r[0] == code), None)


def _invite_code():
    with _db() as conn:
        row = conn.execute("SELECT code FROM oge9_trainer_invite WHERE id=1").fetchone()
        if row:
            return row[0]
        code = secrets.token_urlsafe(12).replace("-", "").replace("_", "")
        conn.execute("INSERT INTO oge9_trainer_invite(id,code) VALUES(1,?)", (code,))
        return code


def _keyboard(rows):
    return Markup(rows)


def _back(where="home"):
    return [Button("← Назад", callback_data="cab:o9:" + where)]


async def _edit(q, text, buttons):
    await q.edit_message_text(text, reply_markup=_keyboard(buttons))


async def _home(q):
    members = len(_members())
    with _db() as conn:
        pending = conn.execute("SELECT COUNT(*) FROM oge9_trainer_requests").fetchone()[0]
        campaigns = conn.execute(
            "SELECT COUNT(*) FROM oge9_trainer_campaigns WHERE enabled=1"
        ).fetchone()[0]
    await _edit(q,
        "🧪 Напоминания ОГЭ · 9 класс\n\n"
        f"Подтверждённых учеников: {members}\n"
        f"Заявок на подключение: {pending}\n"
        f"Активных назначений: {campaigns}\n\n"
        "Сообщения получат только подтверждённые девятиклассники. "
        "Ученикам других классов ничего не отправляется.",
        [
            [Button("👥 Получатели 9 класса", callback_data="cab:o9:roster:0")],
            [Button("🔗 Ссылка для подключения", callback_data="cab:o9:link")],
            [Button(f"✅ Подтвердить заявки ({pending})", callback_data="cab:o9:requests")],
            [Button("🧪 Выбрать тренажёр", callback_data="cab:o9:trainers")],
            [Button("📆 Активные назначения", callback_data="cab:o9:campaigns")],
            _back("cabinet"),
        ])


async def _roster(q, page=0):
    page = max(0, int(page))
    with _db() as conn:
        try:
            candidates = conn.execute(
                "SELECT id,coalesce(nullif(user_name,''),nullif(user_email,''),'Ученик'), "
                "telegram_user_id FROM students "
                "WHERE active=1 AND telegram_user_id IS NOT NULL "
                "ORDER BY lower(user_name),id"
            ).fetchall()
        except sqlite3.OperationalError:
            candidates = []
    selected = {int(row[0]) for row in _members()}
    per_page = 10
    page = min(page, max(0, (len(candidates)-1)//per_page))
    rows = []
    for student_id, name, telegram_id in candidates[page*per_page:(page+1)*per_page]:
        uid = int(telegram_id)
        label = ("✅ " if uid in selected else "▫️ ") + str(name)[:29]
        rows.append([Button(label, callback_data=f"cab:o9:toggle:{uid}:{page}")])
    navigation = []
    if page > 0:
        navigation.append(Button("←", callback_data=f"cab:o9:roster:{page-1}"))
    if (page+1)*per_page < len(candidates):
        navigation.append(Button("→", callback_data=f"cab:o9:roster:{page+1}"))
    if navigation:
        rows.append(navigation)
    rows.extend([
        [Button("🔗 Подключить новых учеников", callback_data="cab:o9:link")],
        _back(),
    ])
    await _edit(q,
        "👥 Получатели 9 класса\n\n"
        "Выбери ТОЛЬКО тех, кто действительно учится в 9 классе. "
        "Список ниже содержит всех ранее подключённых к ЕГЭ БЛИЗКО детей, "
        "включая другие классы.\n\n"
        f"Подтверждено: {len(selected)}. Нажми на имя, чтобы включить или исключить.\n"
        + ("Нет подключённых учеников. Используй ссылку ниже." if not candidates else ""),
        rows)


async def _join_link(q, context):
    code = _invite_code()
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start=oge9_{code}"
    await _edit(q,
        "🔗 Ссылка для подключения 9 класса\n\n"
        + link + "\n\n"
        "Отправь её только своим девятиклассникам. Когда ученик нажмёт "
        "«Запустить», заявка появится в админке. Каждую заявку нужно "
        "подтвердить вручную, прежде чем пойдут уведомления.",
        [_back()])


async def _requests(q):
    with _db() as conn:
        rows = conn.execute(
            "SELECT telegram_user_id,display_name FROM oge9_trainer_requests "
            "ORDER BY requested_at LIMIT 20"
        ).fetchall()
    buttons = []
    for uid, name in rows:
        buttons.append([
            Button("✅ " + str(name)[:19], callback_data=f"cab:o9:approve:{uid}"),
            Button("✕", callback_data=f"cab:o9:reject:{uid}"),
        ])
    buttons.append(_back())
    await _edit(q, "Заявки на подключение 9 класса\n\n"
        + ("Подтверди только своих учеников." if rows else "Пока новых заявок нет."),
        buttons)


async def _trainer_menu(q):
    rows = _trainers()
    buttons = [
        [Button(str(title)[:45], callback_data="cab:o9:trainer:" + str(code))]
        for code, title, _ in rows
        if re.fullmatch(r"[a-z0-9_]{1,25}", str(code))
    ]
    buttons.append(_back())
    await _edit(q, "🧪 Выбери нужный тренажёр для 9 класса.\n\n"
        "По умолчанию не назначен ни один. Рассылка НЕ начинается "
        "до твоего отдельного выбора и подтверждения.",
        buttons)


async def _trainer_actions(q, code):
    trainer = _trainer(code)
    if not trainer:
        await _trainer_menu(q)
        return
    await _edit(q,
        "🧪 " + str(trainer[1]) + "\n\n"
        f"Получатели: {len(_members())} подтверждённых учеников ОГЭ.\n\n"
        "Выбери, как напомнить:",
        [
            [Button("📨 Отправить сейчас", callback_data=f"cab:o9:do:{code}:now")],
            [Button("🕔 Однократно в ближайшие 17:00", callback_data=f"cab:o9:do:{code}:once")],
            [Button("📆 Ежедневно 7 дней · 17:00", callback_data=f"cab:o9:do:{code}:daily17")],
            [Button("📆 Ежедневно 7 дней · 19:00", callback_data=f"cab:o9:do:{code}:daily19")],
            [Button("⛔ Отключить напоминания", callback_data=f"cab:o9:do:{code}:stop")],
            _back("trainers"),
        ])


async def _send_for_trainer(context, trainer, now):
    code, title, start_param = trainer
    me = await context.bot.get_me()
    url = f"https://t.me/{me.username}?start={start_param}"
    key = now.date().isoformat()
    sent = failed = skipped = 0
    for uid, name in _members():
        with _db() as conn:
            already = conn.execute(
                "SELECT 1 FROM oge9_trainer_deliveries "
                "WHERE trainer_code=? AND telegram_user_id=? AND day_key=?",
                (code,uid,key)
            ).fetchone()
        if already:
            skipped += 1
            continue
        try:
            first_name = str(name).strip().split()[0]
            await context.bot.send_message(
                chat_id=int(uid),
                text=(f"Привет, {first_name}! 💗\n\n"
                    f"🧪 Тренажёр на сегодня: {title}\n"
                    "Пройди именно этот тренажёр, чтобы закрепить тему. "
                    "Мы играем в долгую! 💗"),
                reply_markup=_keyboard([[Button("🧪 Открыть тренажёр", url=url)]]),
            )
            with _db() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO oge9_trainer_deliveries "
                    "(trainer_code,telegram_user_id,day_key,sent_at) VALUES(?,?,?,?)",
                    (code,uid,key,now.isoformat())
                )
            sent += 1
        except Exception as exc:
            failed += 1
            print(f"OGE9 trainer delivery failed uid={uid}: {type(exc).__name__}", flush=True)
    return sent, failed, skipped


async def _configure(q, context, code, action):
    trainer = _trainer(code)
    if not trainer:
        await _trainer_menu(q)
        return
    if action != "stop" and not _members():
        await _edit(q,
            "Сначала добавь и подтверди получателей 9 класса. "
            "Рассылку без списка не запускаю.",
            [[Button("👥 Получатели",callback_data="cab:o9:roster:0")],_back("trainers")])
        return
    now = datetime.now(bot.TIMEZONE)
    if action == "now":
        sent, failed, skipped = await _send_for_trainer(context,trainer,now)
        msg = f"Отправлено: {sent}. Не доставлено: {failed}. Уже отправлено сегодня: {skipped}."
    elif action == "stop":
        with _db() as conn:
            conn.execute(
                "UPDATE oge9_trainer_campaigns SET enabled=0 WHERE trainer_code=?", (code,)
            )
        msg = "Повторные напоминания по этому тренажёру выключены."
    elif action in ("once","daily17","daily19"):
        hour = 19 if action == "daily19" else 17
        first = now.date() if now.time() < time(hour,0) else now.date()+timedelta(days=1)
        mode = "once" if action == "once" else "daily"
        last = first if mode == "once" else first+timedelta(days=6)
        with _db() as conn:
            conn.execute(
                "INSERT INTO oge9_trainer_campaigns(trainer_code,mode,start_on,end_on,send_hour,enabled) "
                "VALUES(?,?,?,?,?,1) ON CONFLICT(trainer_code) DO UPDATE SET "
                "mode=excluded.mode,start_on=excluded.start_on,end_on=excluded.end_on,"
                "send_hour=excluded.send_hour,enabled=1",
                (code,mode,first.isoformat(),last.isoformat(),hour)
            )
        msg = f"Назначено: {trainer[1]} · {first:%d.%m}–{last:%d.%m} в {hour}:00 (Москва)."
    else:
        await _trainer_actions(q,code)
        return
    await _edit(q, msg, [
        [Button("🧪 Другой тренажёр", callback_data="cab:o9:trainers")],
        _back(),
    ])


async def _campaigns(q):
    with _db() as conn:
        rows = conn.execute(
            "SELECT trainer_code,mode,start_on,end_on,send_hour FROM oge9_trainer_campaigns "
            "WHERE enabled=1 ORDER BY start_on,send_hour"
        ).fetchall()
    lines = ["📆 Активные напоминания ОГЭ", ""]
    buttons = []
    for code, mode, start, end, hour in rows:
        trainer = _trainer(code)
        lines.append(f"• {trainer[1] if trainer else code}: {start} — {end}, {hour}:00")
        buttons.append([Button("⚙️ " + str(trainer[1] if trainer else code)[:32],
                                callback_data=f"cab:o9:trainer:{code}")])
    if not rows:
        lines.append("Пока ничего не назначено.")
    buttons.append(_back())
    await _edit(q,"\n".join(lines),buttons)


async def _on_callback(update,context):
    q = update.callback_query
    if not q or not live23._admin_private(update):
        return await _previous_cabinet_callback(update,context)
    data = str(q.data or "")
    if not data.startswith("cab:o9:"):
        return await _previous_cabinet_callback(update,context)
    await q.answer()
    args = data.split(":")[2:]
    action = args[0] if args else "home"
    if action == "home":
        await _home(q)
    elif action == "cabinet":
        await q.edit_message_text(live23.cabinet_text(),
                                  reply_markup=live23.cabinet_markup())
    elif action == "roster":
        await _roster(q,int(args[1]) if len(args)>1 else 0)
    elif action == "toggle" and len(args)>2:
        uid,page = int(args[1]),int(args[2])
        with _db() as conn:
            existing = conn.execute(
                "SELECT 1 FROM oge9_trainer_members WHERE telegram_user_id=?", (uid,)
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM oge9_trainer_members WHERE telegram_user_id=?", (uid,))
            else:
                # Only allow identities actually linked in the CoreApp student table.
                row = conn.execute(
                    "SELECT coalesce(nullif(user_name,''),nullif(user_email,''),'Ученик') "
                    "FROM students WHERE telegram_user_id=? AND active=1 LIMIT 1", (uid,)
                ).fetchone()
                if row:
                    conn.execute("INSERT INTO oge9_trainer_members VALUES(?,?,?)",
                                 (uid,row[0],datetime.now(bot.TIMEZONE).isoformat()))
        await _roster(q,page)
    elif action == "link":
        await _join_link(q,context)
    elif action == "requests":
        await _requests(q)
    elif action in ("approve","reject") and len(args)>1:
        uid=int(args[1])
        with _db() as conn:
            row=conn.execute(
                "SELECT display_name FROM oge9_trainer_requests WHERE telegram_user_id=?",(uid,)
            ).fetchone()
            if row and action=="approve":
                conn.execute(
                    "INSERT INTO oge9_trainer_members VALUES(?,?,?) "
                    "ON CONFLICT(telegram_user_id) DO UPDATE SET "
                    "display_name=excluded.display_name,added_at=excluded.added_at",
                    (uid,row[0],datetime.now(bot.TIMEZONE).isoformat()))
            conn.execute("DELETE FROM oge9_trainer_requests WHERE telegram_user_id=?",(uid,))
        await _requests(q)
    elif action == "trainers":
        await _trainer_menu(q)
    elif action == "trainer" and len(args)>1:
        await _trainer_actions(q,args[1])
    elif action == "do" and len(args)>2:
        await _configure(q,context,args[1],args[2])
    elif action == "campaigns":
        await _campaigns(q)


async def _on_start(update,context):
    if update.effective_chat.type=="private":
        arg=context.args[0] if getattr(context,"args",None) else ""
        if arg.startswith("oge9_") and arg[5:]==_invite_code():
            user=update.effective_user
            name=(user.full_name or user.first_name or str(user.id)).strip()
            with _db() as conn:
                already=conn.execute(
                    "SELECT 1 FROM oge9_trainer_members WHERE telegram_user_id=?",
                    (int(user.id),)
                ).fetchone()
                if not already:
                    conn.execute(
                        "INSERT INTO oge9_trainer_requests VALUES(?,?,?) "
                        "ON CONFLICT(telegram_user_id) DO UPDATE SET "
                        "display_name=excluded.display_name,requested_at=excluded.requested_at",
                        (int(user.id),name,datetime.now(bot.TIMEZONE).isoformat())
                    )
            await update.message.reply_text(
                "💗 " + ("Ты уже подключён(а) к напоминаниям ОГЭ." if already else
                "Заявка на напоминания ОГЭ отправлена преподавателю. Ожидай подтверждения.")
            )
            return
    return await _previous_start_router(update,context)


async def _daily_tick(context):
    try:
        await _previous_tick(context)
    finally:
        now=datetime.now(bot.TIMEZONE)
        if not (now.minute<10 and now.hour in (17,19)):
            return
        day=now.date().isoformat()
        with _db() as conn:
            campaigns=conn.execute(
                "SELECT trainer_code FROM oge9_trainer_campaigns WHERE enabled=1 "
                "AND start_on<=? AND end_on>=? AND send_hour=?",
                (day,day,now.hour)
            ).fetchall()
            conn.execute(
                "UPDATE oge9_trainer_campaigns SET enabled=0 "
                "WHERE enabled=1 AND end_on<?",(day,)
            )
        for (code,) in campaigns:
            trainer=_trainer(code)
            if trainer:
                await _send_for_trainer(context,trainer,now)


def _cabinet_markup():
    old=_previous_cabinet_markup()
    return _keyboard([
        *old.inline_keyboard,
        [Button("📬 Напоминания ОГЭ · 9 класс",callback_data="cab:o9:home")],
    ])


def install():
    global _installed,_previous_cabinet_markup,_previous_cabinet_callback
    global _previous_start_router,_previous_tick
    if _installed:
        return
    ensure_tables()
    _previous_cabinet_markup=live23.cabinet_markup
    _previous_cabinet_callback=live23.cabinet_callback
    _previous_start_router=live7.start_router
    _previous_tick=live7.friday_trivial_tick
    live23.cabinet_markup=_cabinet_markup
    live23.cabinet_callback=_on_callback
    live7.start_router=_on_start
    live7.friday_trivial_tick=_daily_tick
    _installed=True
    print("OGE9 selective trainer reminders installed; sends only to approved roster",flush=True)
