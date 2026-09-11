import secrets
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import run_bot_live66

live66 = run_bot_live66
live65 = live66.live65
live64 = live66.live64
live63 = live66.live63
live61 = live66.live61
live60 = live66.live60
live59 = live66.live59
live56 = live66.live56
live55 = live66.live55
live54 = live66.live54
live52 = live66.live52
live51 = live66.live51
live50 = live66.live50
live49 = live66.live49
live48 = live66.live48
live46 = live66.live46
live44 = live66.live44
live43 = live66.live43
live41 = live66.live41
live39 = live66.live39
live37 = live66.live37
live35 = live66.live35
live34 = live66.live34
live31 = live66.live31
live24 = live66.live24
live17 = live66.live17
bot = live66.bot
live23 = live64.live23
live7 = live64.live7

INDIVIDUAL_ADD_STATE = "admin_individual_add"
INDIVIDUAL_KEYBOARD = ReplyKeyboardMarkup([["🧪 Тренажёры"]], resize_keyboard=True)


def ensure_individual_students_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS individual_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                display_name TEXT NOT NULL,
                telegram_user_id INTEGER UNIQUE,
                telegram_username TEXT,
                invite_code TEXT UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                linked_at TEXT
            )
            """
        )
        conn.commit()


def _individual_rows():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, display_name, telegram_user_id, telegram_username
            FROM individual_students
            WHERE active = 1
            ORDER BY lower(display_name), id
            """
        ).fetchall()


def _individual_by_id(student_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, display_name, telegram_user_id, telegram_username, invite_code
            FROM individual_students
            WHERE id = ? AND active = 1
            LIMIT 1
            """,
            (int(student_id),),
        ).fetchone()


def _individual_by_telegram(telegram_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id, display_name, telegram_user_id, telegram_username, invite_code
            FROM individual_students
            WHERE telegram_user_id = ? AND active = 1
            LIMIT 1
            """,
            (int(telegram_id),),
        ).fetchone()


def _new_invite_code():
    return secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]


def _create_individual(name):
    name = str(name or "").strip()
    code = _new_invite_code()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO individual_students
                (display_name, invite_code, active, created_at)
            VALUES (?, ?, 1, ?)
            """,
            (name, code, datetime.now(bot.TIMEZONE).isoformat()),
        )
        conn.commit()
        return int(cur.lastrowid), code


def _refresh_invite(student_id):
    code = _new_invite_code()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "UPDATE individual_students SET invite_code = ? WHERE id = ?",
            (code, int(student_id)),
        )
        conn.commit()
    return code


def _link_individual(code, user):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT id, display_name
            FROM individual_students
            WHERE invite_code = ? AND active = 1
            LIMIT 1
            """,
            (str(code or "").strip(),),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE individual_students
            SET telegram_user_id = NULL, telegram_username = NULL
            WHERE telegram_user_id = ? AND id != ?
            """,
            (int(user.id), int(row[0])),
        )
        conn.execute(
            """
            UPDATE individual_students
            SET telegram_user_id = ?, telegram_username = ?, linked_at = ?, invite_code = NULL
            WHERE id = ?
            """,
            (int(user.id), user.username or "", datetime.now(bot.TIMEZONE).isoformat(), int(row[0])),
        )
        conn.commit()
        return row


async def _trainer_markup(context):
    me = await context.bot.get_me()
    if not getattr(me, "username", None):
        return None
    rows = []
    for title, start_param in live41._active_trainers():
        rows.append([
            InlineKeyboardButton(title, url=f"https://t.me/{me.username}?start={start_param}")
        ])
    return InlineKeyboardMarkup(rows) if rows else None


async def _send_trainer_menu(message, context, name):
    first_name = str(name or "").strip().split()[0] if str(name or "").strip() else ""
    greeting = f"Привет, {first_name}! 💗" if first_name else "Привет! 💗"
    await message.reply_text(
        greeting + "\n\n🧪 <b>Тренажёры ЕГЭ БЛИЗКО</b>\n\nВыбирай нужный тренажёр 👇",
        parse_mode="HTML",
        reply_markup=await _trainer_markup(context),
    )


def _individuals_markup():
    rows = []
    for student_id, name, telegram_id, _username in _individual_rows():
        label = name if len(name) <= 28 else name[:25] + "…"
        icon = "✅" if telegram_id else "🔗"
        rows.append([
            InlineKeyboardButton(f"{icon} {label}", callback_data=f"cab:individual:{int(student_id)}")
        ])
    rows.append([InlineKeyboardButton("➕ Добавить ученика", callback_data="cab:individual:add")])
    rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return InlineKeyboardMarkup(rows)


def _individuals_text():
    rows = _individual_rows()
    linked = sum(1 for row in rows if row[2] is not None)
    return (
        "👤 <b>Индивидуальные ученики</b>\n\n"
        f"Всего: {len(rows)} · Telegram подключён: {linked}\n\n"
        "Для них сейчас подключаем только тренажёры. Личные кабинеты пока не создаём."
    )


_previous_cabinet_markup = live23.cabinet_markup


def cabinet_markup_individuals_only():
    base = _previous_cabinet_markup()
    rows = []
    for row in base.inline_keyboard:
        # Убираем прежнюю кнопку «Новый ученик», которая вела к созданию полного кабинета.
        filtered = [button for button in row if getattr(button, "callback_data", None) != "cab:newstudent"]
        if filtered:
            rows.append(filtered)
    if not any(
        getattr(button, "callback_data", None) == "cab:individuals"
        for row in rows for button in row
    ):
        insert_at = max(0, len(rows) - 1)
        rows.insert(insert_at, [
            InlineKeyboardButton("👤 Индивидуальные ученики", callback_data="cab:individuals")
        ])
    return InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_individuals_only

_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_individuals(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:individuals":
        await query.answer()
        await query.edit_message_text(
            _individuals_text(), parse_mode="HTML", reply_markup=_individuals_markup()
        )
        return

    if data == "cab:individual:add":
        await query.answer()
        context.user_data[INDIVIDUAL_ADD_STATE] = True
        await query.message.reply_text(
            "➕ <b>Добавить индивидуального ученика</b>\n\n"
            "Напиши следующим сообщением имя и фамилию.\n"
            "E-mail CoreApp сейчас не нужен — кабинеты пока не подключаем.",
            parse_mode="HTML",
        )
        return

    if data.startswith("cab:individual:link:"):
        try:
            student_id = int(data.rsplit(":", 1)[1])
        except Exception:
            return
        row = _individual_by_id(student_id)
        if not row:
            await query.answer("Ученик не найден")
            return
        code = _refresh_invite(student_id)
        me = await context.bot.get_me()
        await query.answer("Ссылка готова ✅")
        await query.message.reply_text(
            f"🔗 Ссылка для <b>{row[1]}</b>:\n\n"
            f"https://t.me/{me.username}?start=individual_{code}\n\n"
            "Перешли её ученику. После нажатия у него появится кнопка «🧪 Тренажёры».",
            parse_mode="HTML",
        )
        return

    if data.startswith("cab:individual:send:"):
        try:
            student_id = int(data.rsplit(":", 1)[1])
        except Exception:
            return
        row = _individual_by_id(student_id)
        if not row or row[2] is None:
            await query.answer("Telegram ещё не подключён", show_alert=True)
            return
        await query.answer("Отправляю ✅")
        try:
            await context.bot.send_message(
                chat_id=int(row[2]),
                text=f"Привет, {str(row[1]).split()[0]}! 💗\n\n🧪 Выбирай тренажёр для практики 👇",
                reply_markup=await _trainer_markup(context),
            )
        except Exception:
            await query.message.reply_text("Не получилось отправить меню тренажёров.")
        else:
            await query.message.reply_text(f"✅ Тренажёры отправлены: {row[1]}")
        return

    if data.startswith("cab:individual:"):
        try:
            student_id = int(data.rsplit(":", 1)[1])
        except Exception:
            return
        row = _individual_by_id(student_id)
        if not row:
            await query.answer("Ученик не найден")
            return
        await query.answer()
        _id, name, telegram_id, username, _code = row
        status = "✅ Telegram подключён" if telegram_id else "🔗 Telegram ещё не подключён"
        if username:
            status += f" · @{username}"
        buttons = []
        if telegram_id:
            buttons.append([InlineKeyboardButton("🧪 Отправить тренажёры", callback_data=f"cab:individual:send:{student_id}")])
        buttons.append([InlineKeyboardButton("🔗 Ссылка подключения", callback_data=f"cab:individual:link:{student_id}")])
        buttons.append([InlineKeyboardButton("← К списку", callback_data="cab:individuals")])
        await query.edit_message_text(
            f"👤 <b>{name}</b>\n\n{status}\n\nЛичный кабинет пока не подключаем — только тренажёры.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_individuals

_previous_start_router = live7.start_router


async def start_router_with_individuals(update, context):
    if update.effective_chat.type == "private" and context.args:
        arg = str(context.args[0] or "")
        if arg.startswith("individual_"):
            row = _link_individual(arg.split("individual_", 1)[1], update.effective_user)
            if not row:
                await update.message.reply_text(
                    "Эта ссылка уже использована или устарела. Попроси Марию Александровну прислать новую."
                )
                return
            await update.message.reply_text(
                "✅ Telegram подключён.\n\n"
                "Теперь тренажёры всегда доступны по кнопке ниже 👇",
                reply_markup=INDIVIDUAL_KEYBOARD,
            )
            await _send_trainer_menu(update.message, context, row[1])
            return
    await _previous_start_router(update, context)


live7.start_router = start_router_with_individuals

_previous_text_router = live7.student_text_router


async def text_router_with_individuals(update, context):
    if update.message and update.message.text:
        text = str(update.message.text).strip()

        if (
            update.effective_chat.type == "private"
            and bot.user_is_admin(update)
            and context.user_data.get(INDIVIDUAL_ADD_STATE)
        ):
            context.user_data.pop(INDIVIDUAL_ADD_STATE, None)
            if len(text) < 2:
                await update.message.reply_text("Имя слишком короткое. Нажми «Добавить ученика» и попробуй ещё раз.")
                return
            student_id, code = _create_individual(text)
            me = await context.bot.get_me()
            await update.message.reply_text(
                f"✅ <b>{text}</b> добавлен(а) в раздел «Индивидуальные ученики».\n\n"
                "Перешли ученику эту ссылку:\n"
                f"https://t.me/{me.username}?start=individual_{code}\n\n"
                "После подключения у него будет только кнопка «🧪 Тренажёры». Личный кабинет не создаётся.",
                parse_mode="HTML",
            )
            print(f"Individual student created id={student_id}", flush=True)
            return

        if update.effective_chat.type == "private" and text == "🧪 Тренажёры":
            row = _individual_by_telegram(update.effective_user.id)
            if row:
                await _send_trainer_menu(update.message, context, row[1])
                return

    await _previous_text_router(update, context)


live7.student_text_router = text_router_with_individuals


if __name__ == "__main__":
    live59.ensure_coreapp_webhook_audit_table()
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live60.ensure_oxides_tables()
    live60.register_oxides_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    live66.seed_zlata_accounting_task()
    live56.log_probnik_cabinet_audit()
    ensure_individual_students_table()
    print("Individual students trainer-only mode ready", flush=True)
    print("Zlata accounting task seeded for 12.09.2026 10:00", flush=True)
    print("Actionable admin task list ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
