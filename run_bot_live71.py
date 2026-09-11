import html
import secrets
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import run_bot_live70
from molar_mass import MolarMassError, format_result

live70 = run_bot_live70
live69 = live70.live69
live68 = live70.live68
live67 = live70.live67
live66 = live70.live66
live65 = live70.live65
live64 = live70.live64
live63 = live70.live63
live61 = live70.live61
live60 = live70.live60
live59 = live70.live59
live56 = live70.live56
live55 = live70.live55
live54 = live70.live54
live52 = live70.live52
live51 = live70.live51
live50 = live70.live50
live49 = live70.live49
live48 = live70.live48
live46 = live70.live46
live44 = live70.live44
live43 = live70.live43
live41 = live70.live41
live39 = live70.live39
live37 = live70.live37
live35 = live70.live35
live34 = live70.live34
live31 = live70.live31
live24 = live70.live24
live17 = live70.live17
live28 = live70.live28
bot = live70.bot
run_bot = live70.run_bot
live23 = live64.live23
live7 = live64.live7

MOLAR_STATE_KEY = "staff_molar_mass_waiting_formula"
TUTOR_BUTTON = "⚗️ Молярная масса"
TUTOR_KEYBOARD = ReplyKeyboardMarkup([[TUTOR_BUTTON]], resize_keyboard=True)


def ensure_molar_access_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS molar_staff (
                role TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                telegram_username TEXT,
                telegram_name TEXT,
                linked_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS molar_staff_invites (
                code TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                used_at TEXT
            )
            """
        )
        conn.commit()


def _tutor_row():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT telegram_user_id, telegram_username, telegram_name, linked_at
            FROM molar_staff
            WHERE role = 'tutor'
            LIMIT 1
            """
        ).fetchone()


def _is_tutor(user_id):
    if not user_id:
        return False
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM molar_staff WHERE role = 'tutor' AND telegram_user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone())


def _create_tutor_invite():
    code = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:18]
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        # Одновременно держим только одну активную ссылку для тьютора.
        conn.execute("DELETE FROM molar_staff_invites WHERE role = 'tutor' AND used_at IS NULL")
        conn.execute(
            "INSERT INTO molar_staff_invites (code, role, created_at) VALUES (?, 'tutor', ?)",
            (code, now),
        )
        conn.commit()
    return code


def _link_tutor(code, user):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT code FROM molar_staff_invites
            WHERE code = ? AND role = 'tutor' AND used_at IS NULL
            LIMIT 1
            """,
            (str(code or "").strip(),),
        ).fetchone()
        if not row:
            return False

        conn.execute(
            """
            INSERT INTO molar_staff
                (role, telegram_user_id, telegram_username, telegram_name, linked_at)
            VALUES ('tutor', ?, ?, ?, ?)
            ON CONFLICT(role) DO UPDATE SET
                telegram_user_id = excluded.telegram_user_id,
                telegram_username = excluded.telegram_username,
                telegram_name = excluded.telegram_name,
                linked_at = excluded.linked_at
            """,
            (int(user.id), user.username or "", user.full_name or "", now),
        )
        conn.execute(
            "UPDATE molar_staff_invites SET used_at = ? WHERE code = ?",
            (now, str(code or "").strip()),
        )
        conn.commit()
    return True


def _staff_allowed(update):
    if not update.effective_user:
        return False
    return bot.user_is_admin(update) or _is_tutor(update.effective_user.id)


def _molar_screen_text():
    tutor = _tutor_row()
    if tutor:
        tutor_name = str(tutor[2] or tutor[1] or "Тьютор").strip()
        tutor_status = f"✅ Тьютор подключён: {html.escape(tutor_name)}"
    else:
        tutor_status = "🔗 Тьютор пока не подключён"
    return (
        "⚗️ <b>Калькулятор молярной массы</b>\n\n"
        "Считает по школьным атомным массам из загруженной таблицы.\n"
        "Поддерживает индексы, скобки и кристаллизационную воду.\n\n"
        "Примеры: <code>H2SO4</code>, <code>Ca(OH)2</code>, "
        "<code>Al2(SO4)3</code>, <code>CuSO4·5H2O</code>.\n\n"
        f"{tutor_status}"
    )


def _molar_screen_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚗️ Ввести формулу", callback_data="cab:molar:enter")],
        [InlineKeyboardButton("🔗 Ссылка для тьютора", callback_data="cab:molar:tutorlink")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def _molar_result_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚗️ Посчитать ещё", callback_data="cab:molar:enter")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def _formula_prompt():
    return (
        "⚗️ Отправь формулу вещества одним сообщением.\n\n"
        "Например: H2SO4, Ca(OH)2 или Al2(SO4)3.\n"
        "Можно использовать обычные цифры или нижние индексы: H₂SO₄."
    )


def complete_molar_mass_task():
    # Задача «Подключить таблицу с молярными массами к боту» выполнена этой версией.
    try:
        task_key = live50.MOLAR_MASS_TASK_KEY
    except Exception:
        return
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            UPDATE admin_tasks
            SET completed_at = COALESCE(completed_at, ?)
            WHERE task_key = ?
            """,
            (datetime.now(bot.TIMEZONE).isoformat(), task_key),
        )
        conn.commit()


_previous_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_molar_mass():
    base = _previous_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:molar"
        for row in rows for button in row
    ):
        insert_at = max(0, len(rows) - 1)
        rows.insert(insert_at, [
            InlineKeyboardButton("⚗️ Молярная масса", callback_data="cab:molar")
        ])
    return InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_molar_mass

_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_molar_mass(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:molar":
        context.user_data.pop(MOLAR_STATE_KEY, None)
        await query.answer()
        await query.edit_message_text(
            _molar_screen_text(),
            parse_mode="HTML",
            reply_markup=_molar_screen_markup(),
        )
        return

    if data == "cab:molar:enter":
        context.user_data[MOLAR_STATE_KEY] = True
        await query.answer()
        await query.message.reply_text(_formula_prompt())
        return

    if data == "cab:molar:tutorlink":
        context.user_data.pop(MOLAR_STATE_KEY, None)
        code = _create_tutor_invite()
        me = await context.bot.get_me()
        if not getattr(me, "username", None):
            await query.answer("У бота нет username", show_alert=True)
            return
        await query.answer("Ссылка готова ✅")
        await query.message.reply_text(
            "🔗 <b>Ссылка для тьютора</b>\n\n"
            f"https://t.me/{me.username}?start=molar_tutor_{code}\n\n"
            "Перешли её тьютору. Ссылка одноразовая. После подключения у тьютора "
            "появится постоянная кнопка «⚗️ Молярная масса».",
            parse_mode="HTML",
        )
        return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_molar_mass

_previous_start_router = live7.start_router


async def start_router_with_molar_tutor(update, context):
    if update.effective_chat.type == "private" and context.args:
        arg = str(context.args[0] or "")
        if arg.startswith("molar_tutor_"):
            code = arg.split("molar_tutor_", 1)[1]
            if not _link_tutor(code, update.effective_user):
                await update.message.reply_text(
                    "Эта ссылка уже использована или устарела. Попроси Марию Александровну прислать новую."
                )
                return
            await update.message.reply_text(
                "✅ Доступ тьютора подключён.\n\n"
                "Теперь калькулятор молярной массы всегда доступен по кнопке ниже 👇",
                reply_markup=TUTOR_KEYBOARD,
            )
            return

    if (
        update.effective_chat.type == "private"
        and not context.args
        and update.effective_user
        and _is_tutor(update.effective_user.id)
    ):
        await update.message.reply_text(
            "Привет! ⚗️ Калькулятор молярной массы готов.",
            reply_markup=TUTOR_KEYBOARD,
        )
        return

    await _previous_start_router(update, context)


live7.start_router = start_router_with_molar_tutor

_previous_text_router = live7.student_text_router


async def text_router_with_molar_mass(update, context):
    if update.effective_chat.type == "private" and update.message and update.message.text:
        text = str(update.message.text or "").strip()
        user_id = update.effective_user.id if update.effective_user else None
        is_admin = bot.user_is_admin(update)
        is_tutor = _is_tutor(user_id)

        # Не перехватываем возврат Маши в её кабинет.
        if is_admin and text == "👩‍🏫 Кабинет Маши":
            context.user_data.pop(MOLAR_STATE_KEY, None)
            await _previous_text_router(update, context)
            return

        if is_tutor and text == TUTOR_BUTTON:
            context.user_data[MOLAR_STATE_KEY] = True
            await update.message.reply_text(_formula_prompt(), reply_markup=TUTOR_KEYBOARD)
            return

        if context.user_data.get(MOLAR_STATE_KEY) and (is_admin or is_tutor):
            try:
                result_text = format_result(text)
            except MolarMassError as exc:
                await update.message.reply_text(
                    f"Не получилось посчитать: {exc}\n\n"
                    "Попробуй ещё раз. Пример: Ca(OH)2",
                    reply_markup=TUTOR_KEYBOARD if is_tutor else None,
                )
                return
            except Exception:
                await update.message.reply_text(
                    "Не получилось разобрать формулу. Попробуй ещё раз, например: Al2(SO4)3.",
                    reply_markup=TUTOR_KEYBOARD if is_tutor else None,
                )
                return

            context.user_data.pop(MOLAR_STATE_KEY, None)
            await update.message.reply_text(
                result_text,
                reply_markup=TUTOR_KEYBOARD if is_tutor else _molar_result_markup(),
            )
            return

    await _previous_text_router(update, context)


live7.student_text_router = text_router_with_molar_mass


if __name__ == "__main__":
    ensure_molar_access_tables()
    live70.ensure_health_tables()
    live59.ensure_coreapp_webhook_audit_table()
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live28.ensure_unanswered_reminder_tables()
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
    live67.ensure_individual_students_table()
    complete_molar_mass_task()
    print("Molar mass calculator ready for admin and tutor", flush=True)
    print("Molar mass task marked completed", flush=True)
    print("Health monitoring and Telegram admin alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Actionable admin task list ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
