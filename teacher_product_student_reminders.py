"""Opt-in student lesson reminders and per-occurrence attendance replies."""

import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
                          ConversationHandler, MessageHandler, filters)

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_student_messaging as messaging

ADD_MEMBER = 130
OFFSETS = (1440, 60)


def ensure_tables():
    with base.db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS student_reminder_settings (
                teacher_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS student_reminder_people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('individual','group')),
                student_id INTEGER,
                group_id INTEGER,
                name TEXT NOT NULL,
                invite_token TEXT NOT NULL UNIQUE,
                telegram_user_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS student_reminder_individual
                ON student_reminder_people(teacher_id, student_id) WHERE kind='individual';
            CREATE INDEX IF NOT EXISTS student_reminder_group
                ON student_reminder_people(teacher_id, group_id, active);
            CREATE TABLE IF NOT EXISTS student_lesson_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                lesson_kind TEXT NOT NULL,
                slot_id INTEGER NOT NULL,
                occurrence_key TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                offset_minutes INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                UNIQUE(person_id, lesson_kind, slot_id, occurrence_key, starts_at, offset_minutes)
            );
            CREATE TABLE IF NOT EXISTS student_lesson_replies (
                person_id INTEGER NOT NULL,
                lesson_kind TEXT NOT NULL,
                slot_id INTEGER NOT NULL,
                occurrence_key TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                response TEXT NOT NULL CHECK(response IN ('yes','no')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY(person_id, lesson_kind, slot_id, occurrence_key, starts_at)
            );
        """)


def enabled(uid):
    with base.db() as conn:
        row = conn.execute("SELECT enabled FROM student_reminder_settings WHERE teacher_id=?", (int(uid),)).fetchone()
    return bool(row and row["enabled"])


def toggle(uid):
    with base.db() as conn:
        conn.execute("INSERT OR IGNORE INTO student_reminder_settings(teacher_id) VALUES(?)", (int(uid),))
        conn.execute("UPDATE student_reminder_settings SET enabled=1-enabled WHERE teacher_id=?", (int(uid),))
    return enabled(uid)


def _individual(uid, sid):
    student = schedule.get_student(uid, sid)
    if not student:
        return None
    with base.db() as conn:
        conn.execute("""INSERT OR IGNORE INTO student_reminder_people
            (teacher_id,kind,student_id,name,invite_token,created_at)
            VALUES(?,'individual',?,?,?,?)""",
            (int(uid), int(sid), student["name"], secrets.token_urlsafe(24), datetime.utcnow().isoformat()))
        conn.execute("""UPDATE student_reminder_people SET active=1,name=?
            WHERE teacher_id=? AND kind='individual' AND student_id=?""",
            (student["name"], int(uid), int(sid)))
        return conn.execute("""SELECT * FROM student_reminder_people
            WHERE teacher_id=? AND kind='individual' AND student_id=?""", (int(uid), int(sid))).fetchone()


def _members(uid, gid):
    with base.db() as conn:
        return conn.execute("""SELECT * FROM student_reminder_people
            WHERE teacher_id=? AND kind='group' AND group_id=? AND active=1 ORDER BY lower(name)""",
            (int(uid), int(gid))).fetchall()


def add_member(uid, gid, name):
    if not groups.get_group(uid, gid) or not name.strip():
        return None
    with base.db() as conn:
        cursor = conn.execute("""INSERT INTO student_reminder_people
            (teacher_id,kind,group_id,name,invite_token,created_at)
            VALUES(?,'group',?,?,?,?)""",
            (int(uid), int(gid), name.strip(), secrets.token_urlsafe(24), datetime.utcnow().isoformat()))
        return conn.execute("SELECT * FROM student_reminder_people WHERE id=?", (cursor.lastrowid,)).fetchone()


def _invite(row):
    return "https://t.me/prepodmin_bot?start=join_" + row["invite_token"]


def _share_url(row):
    return "https://t.me/share/url?" + urlencode({
        "url": _invite(row),
        "text": f"{row['name']}, присоединяйся к ПРЕПОДМИН, чтобы получать напоминания об уроках и подтверждать участие. Открой ссылку и нажми «Запустить».",
    })


def _invitation_buttons(row, back_label, back_callback):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Отправить ученику", url=_share_url(row))],
        [InlineKeyboardButton(back_label, callback_data=back_callback)],
    ])


async def menu(update, context):
    q = update.callback_query
    await q.answer()
    if not base.teacher(q.from_user.id):
        raise ApplicationHandlerStop
    kb = [[InlineKeyboardButton("👤 Индивидуальные", callback_data="srem:individual")],
          [InlineKeyboardButton("👥 Группы", callback_data="srem:groups")],
          [InlineKeyboardButton("📋 Ближайшие ответы", callback_data="srem:replies")],
          [InlineKeyboardButton("↩️ К напоминаниям", callback_data="srem:back")]]
    await q.edit_message_text("Привяжи учеников к Telegram по личным ссылкам. Здесь же видны ответы на ближайшие уроки.",
                              reply_markup=InlineKeyboardMarkup(kb))
    raise ApplicationHandlerStop


async def setting(update, context):
    from teacher_product_reminders import reminder_keyboard, reminder_text
    q = update.callback_query
    await q.answer()
    if not base.teacher(q.from_user.id):
        raise ApplicationHandlerStop
    if q.data == "srem:toggle":
        toggle(q.from_user.id)
    await q.edit_message_text(reminder_text(q.from_user.id), reply_markup=reminder_keyboard(q.from_user.id))
    raise ApplicationHandlerStop


async def picker(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    kind = q.data.split(":")[1]
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    if kind == "individual":
        rows = base.list_students(uid)
        kb = [[InlineKeyboardButton(r["name"], callback_data=f"srem:ind:{r['id']}")] for r in rows[:60]]
    else:
        rows = groups.groups(uid)
        kb = [[InlineKeyboardButton(r["name"], callback_data=f"srem:group:{r['id']}")] for r in rows[:60]]
    kb.append([InlineKeyboardButton("↩️ Назад", callback_data="srem:people")])
    await q.edit_message_text("Выбери ученика:" if kind == "individual" else "Выбери группу:",
                              reply_markup=InlineKeyboardMarkup(kb))
    raise ApplicationHandlerStop


async def person(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    sid = int(q.data.rsplit(":", 1)[1])
    row = _individual(uid, sid) if base.teacher(uid) else None
    if not row:
        await q.edit_message_text("Ученик не найден.")
    else:
        state = "привязан" if row["telegram_user_id"] else "пока не привязан"
        await q.edit_message_text(f"{row['name']} — {state}.\n\nЛичная ссылка для ученика:\n{_invite(row)}\n\n"
                                  "Нажми «Отправить ученику», выбери его чат и отправь приглашение. "
                                  "После перехода по ссылке ученику нужно нажать «Запустить».",
                                  reply_markup=_invitation_buttons(row, "↩️ Назад", "srem:individual"))
    raise ApplicationHandlerStop


async def group(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    gid = int(q.data.rsplit(":", 1)[1])
    g = groups.get_group(uid, gid) if base.teacher(uid) else None
    if not g:
        await q.edit_message_text("Группа не найдена.")
        raise ApplicationHandlerStop
    rows = _members(uid, gid)
    lines = [f"👥 {g['name']}", ""]
    lines += [f"• {r['name']} — {'привязан' if r['telegram_user_id'] else 'ожидает привязки'}"
              for r in rows] or ["Участников пока нет."]
    kb = [[InlineKeyboardButton("➕ Добавить участника", callback_data=f"srem:add:{gid}")]]
    kb += [[InlineKeyboardButton(f"🔗 {r['name']}", callback_data=f"srem:member:{r['id']}"),
            InlineKeyboardButton("🗑", callback_data=f"srem:remove:{r['id']}")] for r in rows[:40]]
    kb.append([InlineKeyboardButton("↩️ К группам", callback_data="srem:groups")])
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
    raise ApplicationHandlerStop


async def member(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pid = int(q.data.rsplit(":", 1)[1])
    with base.db() as conn:
        row = conn.execute("SELECT * FROM student_reminder_people WHERE id=? AND teacher_id=? AND kind='group' AND active=1",
                           (pid, uid)).fetchone()
    if not row or not groups.get_group(uid, row["group_id"]):
        await q.edit_message_text("Участник не найден.")
    else:
        await q.edit_message_text(f"{row['name']}\n\nЛичная ссылка:\n{_invite(row)}\n\n"
                                  "Нажми «Отправить ученику», выбери его чат и отправь приглашение. "
                                  "После перехода по ссылке ученику нужно нажать «Запустить».",
                                  reply_markup=_invitation_buttons(row, "↩️ К группе", f"srem:group:{row['group_id']}"))
    raise ApplicationHandlerStop


async def remove(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    pid = int(q.data.rsplit(":", 1)[1])
    with base.db() as conn:
        row = conn.execute("SELECT group_id FROM student_reminder_people WHERE id=? AND teacher_id=? AND kind='group' AND active=1",
                           (pid, uid)).fetchone()
        if row and groups.get_group(uid, row["group_id"]):
            conn.execute("UPDATE student_reminder_people SET active=0 WHERE id=?", (pid,))
    await q.edit_message_text("Участник убран. Напоминания ему больше не придут.")
    raise ApplicationHandlerStop


async def add_begin(update, context):
    q = update.callback_query
    await q.answer()
    gid = int(q.data.rsplit(":", 1)[1])
    if not base.teacher(q.from_user.id) or not groups.get_group(q.from_user.id, gid):
        await q.edit_message_text("Группа не найдена.")
        return ConversationHandler.END
    context.user_data["srem_group"] = gid
    await q.edit_message_text("Напиши имя ученика этой группы. Для каждого будет своя ссылка на бота.")
    return ADD_MEMBER


async def add_name(update, context):
    gid = context.user_data.pop("srem_group", None)
    name = update.message.text.strip()
    if not gid or not name or len(name) > 100 or name.startswith("/"):
        await update.message.reply_text("Не удалось добавить ученика. Открой группу и попробуй снова.")
        return ConversationHandler.END
    row = add_member(update.effective_user.id, gid, name)
    if row:
        await update.message.reply_text(
            f"✅ {name} добавлен(а). Нажми «Отправить ученику», выбери его чат и отправь приглашение.\n\n"
            f"Личная ссылка: {_invite(row)}",
            reply_markup=_invitation_buttons(row, "↩️ К группе", f"srem:group:{gid}"),
        )
    else:
        await update.message.reply_text("Группа не найдена.")
    return ConversationHandler.END


async def join(update, context):
    # Run before the teacher onboarding handler; never silently turn a pupil into a teacher.
    if not context.args or not context.args[0].startswith("join_"):
        with base.db() as conn:
            linked = conn.execute("""SELECT name FROM student_reminder_people
                WHERE telegram_user_id=? AND active=1 LIMIT 1""", (update.effective_user.id,)).fetchone()
        if linked and not base.teacher(update.effective_user.id):
            await update.message.reply_text("Ты привязан(а) к ПРЕПОДМИН. Здесь будут приходить напоминания об уроках и кнопки подтверждения.")
            raise ApplicationHandlerStop
        return
    token = context.args[0][5:]
    uid = update.effective_user.id
    with base.db() as conn:
        row = conn.execute("SELECT * FROM student_reminder_people WHERE invite_token=? AND active=1", (token,)).fetchone()
        if row and row["kind"] == "individual" and not schedule.get_student(row["teacher_id"], row["student_id"]):
            row = None
        if row and row["kind"] == "group" and not groups.get_group(row["teacher_id"], row["group_id"]):
            row = None
        if row and row["telegram_user_id"] not in (None, uid):
            row = None
        if row and conn.execute("""SELECT 1 FROM student_reminder_people
            WHERE teacher_id=? AND telegram_user_id=? AND active=1 AND id<>?""",
            (row["teacher_id"], uid, row["id"])).fetchone():
            row = None
        if row:
            conn.execute("UPDATE student_reminder_people SET telegram_user_id=? WHERE id=?", (uid, row["id"]))
    await update.message.reply_text(
        f"✅ Ты привязан(а) как {row['name']}. Когда преподаватель включит напоминания, здесь можно будет подтвердить участие в уроке."
        if row else "Ссылка недействительна или уже привязана к другому аккаунту. Попроси преподавателя проверить её.")
    raise ApplicationHandlerStop


def recipients(uid, event):
    with base.db() as conn:
        if event["kind"] == "individual":
            return conn.execute("""SELECT p.* FROM student_reminder_people p
                JOIN students s ON s.id=p.student_id AND s.active=1
                WHERE p.teacher_id=? AND p.kind='individual' AND p.student_id=?
                  AND p.active=1 AND p.telegram_user_id IS NOT NULL""",
                (uid, event["person_id"])).fetchall()
        return conn.execute("""SELECT p.* FROM student_reminder_people p
            JOIN teacher_groups g ON g.id=p.group_id AND g.active=1
            WHERE p.teacher_id=? AND p.kind='group' AND p.group_id=?
              AND p.active=1 AND p.telegram_user_id IS NOT NULL""",
            (uid, event["person_id"])).fetchall()


def reply_for(person_id, event):
    with base.db() as conn:
        row = conn.execute("""SELECT response FROM student_lesson_replies
            WHERE person_id=? AND lesson_kind=? AND slot_id=? AND occurrence_key=? AND starts_at=?""",
            (person_id, event["kind"], event["slot_id"], event["occurrence_key"], event["event_dt"].isoformat())).fetchone()
    return row["response"] if row else None


async def deliver(context, uid, event, now):
    if messaging.get_mode(uid) == "off":
        return
    starts_at = event["event_dt"].isoformat()
    for offset in OFFSETS:
        elapsed = (now - (event["event_dt"] - timedelta(minutes=offset))).total_seconds()
        if not 0 <= elapsed < 150:
            continue
        for person in recipients(uid, event):
            if reply_for(person["id"], event):
                continue
            with base.db() as conn:
                existing = conn.execute("""SELECT 1 FROM student_lesson_messages
                    WHERE person_id=? AND lesson_kind=? AND slot_id=? AND occurrence_key=?
                      AND starts_at=? AND offset_minutes=?""",
                    (person["id"], event["kind"], event["slot_id"], event["occurrence_key"], starts_at, offset)).fetchone()
            if existing:
                continue
            dt = event["event_dt"]
            text = (f"🔔 {person['name']}, занятие {dt.strftime('%d.%m в %H:%M')}"
                    + (f" · группа {event['name']}" if event["kind"] == "group" else "")
                    + ("\n↪️ Время занятия изменено." if event["moved"] else "")
                    + "\n\nБудешь на уроке?")
            # Reserve a stable callback ID; release it if Telegram rejects delivery.
            with base.db() as conn:
                cur = conn.execute("""INSERT OR IGNORE INTO student_lesson_messages
                    (person_id,lesson_kind,slot_id,occurrence_key,starts_at,offset_minutes,sent_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (person["id"], event["kind"], event["slot_id"], event["occurrence_key"], starts_at,
                     offset, datetime.utcnow().isoformat()))
                message_id = cur.lastrowid if cur.rowcount else None
            if not message_id:
                continue
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Буду", callback_data=f"srem:reply:{message_id}:yes"),
                InlineKeyboardButton("❌ Не смогу", callback_data=f"srem:reply:{message_id}:no")
            ]])
            result = await messaging.dispatch(
                context,
                uid,
                int(person["telegram_user_id"]),
                text,
                recipient_name=person["name"],
                category="lesson_reminder",
                source_key=(
                    f"lesson:reminder:{person['id']}:{event['kind']}:"
                    f"{event['slot_id']}:{event['occurrence_key']}:"
                    f"{starts_at}:{offset}"
                ),
                reply_markup=markup,
                expires_at=event["event_dt"],
            )
            if result == "failed":
                with base.db() as conn:
                    conn.execute("DELETE FROM student_lesson_messages WHERE id=?", (message_id,))
                    conn.commit()
            print(
                f"Student lesson reminder routed person={person['id']} status={result}",
                flush=True,
            )


def current_start(person, message):
    uid = person["teacher_id"]
    kind = message["lesson_kind"]
    slot = schedule.slot(uid, message["slot_id"]) if kind == "individual" else groups.group_slot(uid, message["slot_id"])
    if not slot or (kind == "individual" and slot["student_id"] != person["student_id"]) or (
        kind == "group" and slot["group_id"] != person["group_id"]):
        return None
    original = message["occurrence_key"]
    if datetime.fromisoformat(original).weekday() != slot["weekday"]:
        return None
    table = "schedule_moves" if kind == "individual" else "group_schedule_moves"
    with base.db() as conn:
        move = conn.execute(f"""SELECT new_date,new_time FROM {table}
            WHERE teacher_telegram_user_id=? AND schedule_slot_id=? AND original_date=?
            ORDER BY id DESC LIMIT 1""", (uid, slot["id"], original)).fetchone()
    day = move["new_date"] if move else original
    time = move["new_time"] if move else slot["time_text"]
    return datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=schedule.tz(uid)).isoformat()


async def reply(update, context):
    q = update.callback_query
    uid = q.from_user.id
    parts = q.data.split(":")
    message_id, response = int(parts[2]), parts[3]
    with base.db() as conn:
        row = conn.execute("""SELECT m.*,p.name,p.telegram_user_id,p.teacher_id,p.kind,p.student_id,p.group_id,p.active
            FROM student_lesson_messages m JOIN student_reminder_people p ON p.id=m.person_id
            WHERE m.id=? AND p.telegram_user_id=? AND p.active=1""", (message_id, uid)).fetchone()
    if not row or response not in ("yes", "no") or not enabled(row["teacher_id"]):
        await q.answer("Подтверждение недоступно", show_alert=True)
        raise ApplicationHandlerStop
    now = datetime.now(schedule.tz(row["teacher_id"]))
    if (current_start(row, row) != row["starts_at"] or
        datetime.fromisoformat(row["starts_at"]) <= now):
        await q.answer("Время занятия изменилось или оно уже прошло. Жди нового напоминания.", show_alert=True)
        raise ApplicationHandlerStop
    with base.db() as conn:
        previous = conn.execute("""SELECT response FROM student_lesson_replies WHERE
            person_id=? AND lesson_kind=? AND slot_id=? AND occurrence_key=? AND starts_at=?""",
            (row["person_id"], row["lesson_kind"], row["slot_id"], row["occurrence_key"], row["starts_at"])).fetchone()
        conn.execute("""INSERT INTO student_lesson_replies
            (person_id,lesson_kind,slot_id,occurrence_key,starts_at,response,updated_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(person_id,lesson_kind,slot_id,occurrence_key,starts_at)
            DO UPDATE SET response=excluded.response,updated_at=excluded.updated_at""",
            (row["person_id"], row["lesson_kind"], row["slot_id"], row["occurrence_key"], row["starts_at"],
             response, datetime.utcnow().isoformat()))
    await q.answer("Ответ записан")
    await q.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Буду" if response == "yes" else "❌ Не смогу", callback_data="srem:ack")
    ]]))
    if not previous or previous["response"] != response:
        label = "будет" if response == "yes" else "не сможет быть"
        try:
            await context.bot.send_message(row["teacher_id"],
                f"📩 {row['name']} {label} на занятии {datetime.fromisoformat(row['starts_at']).strftime('%d.%m в %H:%M')}.")
        except Exception as exc:
            print(f"Student reply notification failed teacher={row['teacher_id']}: {type(exc).__name__}", flush=True)
    raise ApplicationHandlerStop


async def ack(update, context):
    await update.callback_query.answer("Ответ уже записан")
    raise ApplicationHandlerStop


async def replies(update, context):
    from teacher_product_reminders import _individual_events, _group_events
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if not base.teacher(uid):
        raise ApplicationHandlerStop
    now = datetime.now(schedule.tz(uid))
    events = sorted(_individual_events(uid, now, 168) + _group_events(uid, now, 168),
                    key=lambda e: e["event_dt"])[:25]
    lines = ["📋 Ответы на ближайшие занятия", ""]
    for event in events:
        people = recipients(uid, event)
        if not people:
            continue
        yes = [p["name"] for p in people if reply_for(p["id"], event) == "yes"]
        no = [p["name"] for p in people if reply_for(p["id"], event) == "no"]
        waiting = [p["name"] for p in people if reply_for(p["id"], event) is None]
        lines.append(f"{event['event_dt'].strftime('%d.%m %H:%M')} · {event['name']}")
        lines.append(f"✅ {', '.join(yes) or '—'} · ❌ {', '.join(no) or '—'} · ⏳ {', '.join(waiting) or '—'}")
    if len(lines) == 2:
        lines.append("Нет ближайших занятий с привязанными учениками.")
    await q.edit_message_text("\n".join(lines)[:3900], reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("↩️ Назад", callback_data="srem:people")]]))
    raise ApplicationHandlerStop


def install(app):
    app.add_handler(CommandHandler("start", join), group=-3)
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(add_begin, pattern=r"^srem:add:\d+$")],
        states={ADD_MEMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)]},
        fallbacks=[], per_message=False), group=-3)
    for pattern, handler in (
        (r"^srem:(toggle|back)$", setting), (r"^srem:people$", menu),
        (r"^srem:(individual|groups)$", picker), (r"^srem:ind:\d+$", person),
        (r"^srem:group:\d+$", group), (r"^srem:member:\d+$", member),
        (r"^srem:remove:\d+$", remove), (r"^srem:reply:\d+:(yes|no)$", reply),
        (r"^srem:replies$", replies), (r"^srem:ack$", ack),
    ):
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern), group=-3)
