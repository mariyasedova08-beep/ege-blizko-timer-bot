"""Selective trainer reminders for one teacher-confirmed 9th grade GROUP CHAT.

Changes only EGE BLIZKO. Does not message individual pupils. The teacher uses
the existing /chatid and optional /threadid commands in the target Telegram
group, then binds that destination in the private admin panel.
"""
import html
import re
import sqlite3
from datetime import datetime, timedelta, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import run_bot_live90 as live90

bot = live90.bot
live23 = live90.live23
live7 = live90.live7
_OLD_MARKUP = None
_OLD_CALLBACK = None
_OLD_TEXT = None
_OLD_TICK = None
_INSTALLED = False
WAITING_CHAT_ID = set()


def db():
    return sqlite3.connect(bot.COREAPP_DB_PATH, timeout=20)


def ensure_tables():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS oge9_chat_settings (
                id INTEGER PRIMARY KEY CHECK(id=1),
                chat_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                thread_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS oge9_chat_campaigns (
                trainer_code TEXT PRIMARY KEY,
                mode TEXT NOT NULL CHECK(mode IN ('once','daily')),
                start_on TEXT NOT NULL,
                end_on TEXT NOT NULL,
                hour INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS oge9_chat_deliveries (
                trainer_code TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                day_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(trainer_code,chat_id,day_key)
            );
        """)


def destination():
    with db() as conn:
        return conn.execute("SELECT chat_id,title,thread_id FROM oge9_chat_settings WHERE id=1").fetchone()


def trainers():
    with db() as conn:
        try:
            return conn.execute(
                "SELECT code,title,start_param FROM weekly_trainer_catalog "
                "WHERE active=1 ORDER BY sort_order,title"
            ).fetchall()
        except sqlite3.OperationalError:
            return []


def trainer_by_code(code):
    return next((row for row in trainers() if row[0]==code),None)


def safe_code(code):
    return bool(re.fullmatch(r"[a-z0-9_]{1,25}",str(code)))


def buttons(*rows):
    return InlineKeyboardMarkup([[InlineKeyboardButton(text,callback_data=data) for text,data in row] for row in rows])


def back(target="home"):
    return [("← Назад","cab:o9:"+target)]


async def edit(q,text,keyboard):
    await q.edit_message_text(text,reply_markup=keyboard)


async def home(q):
    dest=destination()
    with db() as conn:
        rows=conn.execute(
            "SELECT COUNT(*) FROM oge9_chat_campaigns WHERE enabled=1"
        ).fetchone()
    target=(html.escape(dest[1])+" ("+str(dest[0])+")") if dest else "Пока не подключён"
    topic=(" · тема "+str(dest[2])) if dest and dest[2] else ""
    await edit(q,
        "🧪 <b>ОГЭ · тренажёры в чат</b>\n\n"
        "Куда отправляем: "+target+topic+"\n"
        "Активных расписаний: "+str(rows[0])+"\n\n"
        "Ты выбираешь тренажёры сама. Без выбора рассылок нет. "
        "Это одна публикация в чате, не личные сообщения детям.",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Привязать чат ОГЭ",callback_data="cab:o9:bind")],
            [InlineKeyboardButton("🧪 Выбрать тренажёр",callback_data="cab:o9:trainers")],
            [InlineKeyboardButton("📆 Мои напоминания",callback_data="cab:o9:campaigns")],
            [InlineKeyboardButton("← Кабинет Маши",callback_data="cab:o9:cabinet")],
        ]))


async def menu(q):
    dest=destination()
    if not dest:
        await edit(q,"Сначала подключи чат девятиклассников.",
            buttons([("🔗 Подключить чат","cab:o9:bind")],back()))
        return
    rows=[[
        InlineKeyboardButton(str(title)[:48],callback_data="cab:o9:trainer:"+str(code))
    ] for code,title,_ in trainers() if safe_code(code)]
    rows.append([InlineKeyboardButton("← Назад",callback_data="cab:o9:home")])
    await edit(q,"🧪 <b>Какой тренажёр отправляем в чат ОГЭ?</b>\n\n"
        "Выбирай только те, которые нужны твоему 9 классу.",InlineKeyboardMarkup(rows))


async def trainer_actions(q,code):
    entry=trainer_by_code(code)
    if not entry or not safe_code(code):
        await menu(q)
        return
    await edit(q,
        "🧪 "+html.escape(str(entry[1]))+"\n\n"
        "Выбери действие. Время — московское. "
        "Публикация идёт только в привязанный чат.",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("📨 Отправить сейчас",callback_data=f"cab:o9:confirm:{code}")],
            [InlineKeyboardButton("🕔 Один раз · 17:00",callback_data=f"cab:o9:do:{code}:once")],
            [InlineKeyboardButton("📅 7 дней · 17:00",callback_data=f"cab:o9:do:{code}:daily17")],
            [InlineKeyboardButton("📅 7 дней · 19:00",callback_data=f"cab:o9:do:{code}:daily19")],
            [InlineKeyboardButton("⛔ Остановить расписание",callback_data=f"cab:o9:do:{code}:stop")],
            [InlineKeyboardButton("← Тренажёры",callback_data="cab:o9:trainers")],
        ]))


async def confirm(q,code):
    entry=trainer_by_code(code)
    dest=destination()
    if not entry or not dest:
        await home(q)
        return
    await edit(q,
        "Подтверди публикацию:\n\n🧪 "+html.escape(str(entry[1]))
        +"\n📣 Чат: "+html.escape(dest[1])+"\n\nОтправить одно сообщение прямо сейчас?",
        buttons([("✅ Да, отправить",f"cab:o9:do:{code}:now")],
                [("← Отмена",f"cab:o9:trainer:{code}")]))


async def post(context,entry,now):
    dest=destination()
    if not dest:
        return "Чат ещё не привязан."
    chat_id,title,thread_id=dest
    code,title_trainer,start_param=entry
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",str(start_param)):
        return "Некорректная ссылка тренажёра. Сообщение не отправлено."
    day_key=now.date().isoformat()
    with db() as conn:
        exists=conn.execute(
            "SELECT 1 FROM oge9_chat_deliveries WHERE trainer_code=? AND chat_id=? AND day_key=?",
            (code,chat_id,day_key)
        ).fetchone()
    if exists:
        return "Этот тренажёр уже отправляли в выбранный чат сегодня."
    me=await context.bot.get_me()
    url=f"https://t.me/{me.username}?start={start_param}"
    message="Привет, девятиклассники! 💗\n\n🧪 Сегодня тренируем: "+str(title_trainer)+"\n\nПроходим именно этот тренажёр — мы играем в долгую! 💗"
    kwargs={"chat_id":int(chat_id),"text":message,
            "reply_markup":InlineKeyboardMarkup([
                [InlineKeyboardButton("🧪 Пройти тренажёр",url=url)]
            ])}
    if thread_id is not None:
        kwargs["message_thread_id"]=int(thread_id)
    try:
        await context.bot.send_message(**kwargs)
    except Exception as exc:
        print("OGE9 chat send failed:",type(exc).__name__,flush=True)
        return "Не удалось отправить сообщение. Проверь, что бот состоит в чате и может публиковать."
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO oge9_chat_deliveries(trainer_code,chat_id,day_key,sent_at) "
            "VALUES(?,?,?,?)",(code,chat_id,day_key,now.isoformat())
        )
    return "✅ Тренажёр опубликован в чате "+str(title)+". Другим группам ничего не отправляли."


async def configure(q,context,code,action):
    entry=trainer_by_code(code)
    if not entry or not safe_code(code):
        await menu(q)
        return
    if not destination():
        await home(q)
        return
    now=datetime.now(bot.TIMEZONE)
    if action=="now":
        text=await post(context,entry,now)
    elif action=="stop":
        with db() as conn:
            conn.execute("UPDATE oge9_chat_campaigns SET enabled=0 WHERE trainer_code=?",(code,))
        text="✅ Расписание остановлено. Ранее опубликованные сообщения остаются в чате."
    elif action in {"once","daily17","daily19"}:
        hour=19 if action=="daily19" else 17
        first=now.date() if now.time()<time(hour,0) else now.date()+timedelta(days=1)
        mode="once" if action=="once" else "daily"
        last=first if mode=="once" else first+timedelta(days=6)
        with db() as conn:
            conn.execute(
                "INSERT INTO oge9_chat_campaigns(trainer_code,mode,start_on,end_on,hour,enabled) "
                "VALUES(?,?,?,?,?,1) ON CONFLICT(trainer_code) DO UPDATE SET "
                "mode=excluded.mode,start_on=excluded.start_on,end_on=excluded.end_on,"
                "hour=excluded.hour,enabled=1",
                (code,mode,first.isoformat(),last.isoformat(),hour)
            )
        text=(f"✅ Назначено: {entry[1]}\n"
              f"С {first:%d.%m} по {last:%d.%m} в {hour}:00 (МСК).\n"
              "Только в чат ОГЭ.")
    else:
        await trainer_actions(q,code)
        return
    await edit(q,html.escape(text),
        buttons([("🧪 Ещё тренажёр","cab:o9:trainers")],back()))


async def campaigns(q):
    with db() as conn:
        rows=conn.execute(
            "SELECT trainer_code,mode,start_on,end_on,hour FROM oge9_chat_campaigns "
            "WHERE enabled=1 ORDER BY start_on,hour"
        ).fetchall()
    lines=["📆 <b>Активные напоминания ОГЭ</b>",""]
    keys=[]
    for code,mode,start,end,hour in rows:
        tr=trainer_by_code(code)
        lines.append("• "+html.escape(str(tr[1] if tr else code))+
                     f": {start} — {end}, {hour}:00")
        keys.append([InlineKeyboardButton("⚙️ "+str(tr[1] if tr else code)[:31],
            callback_data="cab:o9:trainer:"+code)])
    if not rows:
        lines.append("Пока нет назначенных напоминаний.")
    keys.append([InlineKeyboardButton("← Назад",callback_data="cab:o9:home")])
    await edit(q,"\n".join(lines),InlineKeyboardMarkup(keys))


async def callback(update,context):
    q=update.callback_query
    if not q or not live23._admin_private(update):
        return await _OLD_CALLBACK(update,context)
    data=str(q.data or "")
    if not data.startswith("cab:o9:"):
        return await _OLD_CALLBACK(update,context)
    await q.answer()
    args=data.split(":")[2:]
    action=args[0] if args else "home"
    if action=="home":
        await home(q)
    elif action=="cabinet":
        await q.edit_message_text(live23.cabinet_text(),
                                  parse_mode="HTML",reply_markup=live23.cabinet_markup())
    elif action=="bind":
        WAITING_CHAT_ID.add(int(update.effective_user.id))
        await edit(q,
            "🔗 <b>Привязать чат ОГЭ</b>\n\n"
            "1. Добавь бота ЕГЭ БЛИЗКО в чат 9 класса и разреши ему писать.\n"
            "2. В чате отправь <code>/chatid</code>.\n"
            "3. Скопируй ID и пришли мне <b>в личные сообщения</b> отдельным сообщением.\n"
            "Если используешь отдельную тему форума, отправь /threadid в этой теме "
            "и пришли оба числа в одном сообщении через пробел.",
            buttons(back()))
    elif action=="trainers":
        await menu(q)
    elif action=="trainer" and len(args)>1:
        await trainer_actions(q,args[1])
    elif action=="confirm" and len(args)>1:
        await confirm(q,args[1])
    elif action=="do" and len(args)>2:
        await configure(q,context,args[1],args[2])
    elif action=="campaigns":
        await campaigns(q)


async def on_text(update,context):
    user=update.effective_user
    if not user or not bot.user_is_admin(update) or update.effective_chat.type!="private":
        return await _OLD_TEXT(update,context)
    if int(user.id) not in WAITING_CHAT_ID:
        return await _OLD_TEXT(update,context)
    raw=(update.message.text or "").strip()
    match=re.fullmatch(r"(-\d{5,20})(?:\s+(\d{1,12}))?",raw)
    if not match:
        await update.message.reply_text(
            "Нужен ID чата из /chatid, например -1001234567890. "
            "Для темы: -1001234567890 12345."
        )
        return
    chat_id=int(match.group(1))
    thread_id=int(match.group(2)) if match.group(2) else None
    try:
        chat=await context.bot.get_chat(chat_id)
        if str(chat.type) not in ("group","supergroup"):
            await update.message.reply_text("Это не групповой чат. Пришли ID чата девятиклассников.")
            return
        me=await context.bot.get_me()
        member=await context.bot.get_chat_member(chat_id,me.id)
        if str(member.status) in ("left","kicked","banned"):
            await update.message.reply_text("Сначала добавь бота в этот чат.")
            return
    except Exception as exc:
        print("OGE9 chat bind validation failed:",type(exc).__name__,flush=True)
        await update.message.reply_text(
            "Не могу открыть этот чат. Проверь ID, добавь бота в группу "
            "и разреши ему отправлять сообщения."
        )
        return
    with db() as conn:
        conn.execute(
            "INSERT INTO oge9_chat_settings(id,chat_id,title,thread_id) VALUES(1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET chat_id=excluded.chat_id,"
            "title=excluded.title,thread_id=excluded.thread_id",
            (chat_id,str(chat.title or "Чат ОГЭ"),thread_id)
        )
    WAITING_CHAT_ID.discard(int(user.id))
    await update.message.reply_text(
        "✅ Чат ОГЭ подключён: "+str(chat.title or chat_id)
        +(f" · тема {thread_id}" if thread_id is not None else "")
        +"\n\nОткрой «Кабинет Маши» → «📣 Тренажёры ОГЭ в чат», "
        "выбери тренажёр и подтверди публикацию."
    )


async def tick(context):
    try:
        await _OLD_TICK(context)
    finally:
        now=datetime.now(bot.TIMEZONE)
        if now.minute>=10 or now.hour not in (17,19) or not destination():
            return
        today=now.date().isoformat()
        with db() as conn:
            rows=conn.execute(
                "SELECT trainer_code FROM oge9_chat_campaigns "
                "WHERE enabled=1 AND start_on<=? AND end_on>=? AND hour=?",
                (today,today,now.hour)
            ).fetchall()
            conn.execute(
                "UPDATE oge9_chat_campaigns SET enabled=0 WHERE enabled=1 AND end_on<?",
                (today,)
            )
        for (code,) in rows:
            entry=trainer_by_code(code)
            if entry:
                await post(context,entry,now)


def markup():
    old=_OLD_MARKUP()
    return InlineKeyboardMarkup(
        [*old.inline_keyboard, [
            InlineKeyboardButton("📣 Тренажёры ОГЭ → в чат",callback_data="cab:o9:home")
        ]]
    )


def install():
    global _INSTALLED,_OLD_MARKUP,_OLD_CALLBACK,_OLD_TEXT,_OLD_TICK
    if _INSTALLED:
        return
    ensure_tables()
    _OLD_MARKUP=live23.cabinet_markup
    _OLD_CALLBACK=live23.cabinet_callback
    _OLD_TEXT=live7.student_text_router
    _OLD_TICK=live7.friday_trivial_tick
    live23.cabinet_markup=markup
    live23.cabinet_callback=callback
    live7.student_text_router=on_text
    live7.friday_trivial_tick=tick
    _INSTALLED=True
    print("EGE BLIZKO OGE9 trainer chat scheduler installed; requires admin-bound group",flush=True)
