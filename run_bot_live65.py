import html
import re
import sqlite3
from datetime import datetime

import run_bot_live64

live64 = run_bot_live64
live63 = live64.live63
live61 = live64.live61
live60 = live64.live60
live59 = live64.live59
live56 = live64.live56
live55 = live64.live55
live54 = live64.live54
live52 = live64.live52
live51 = live64.live51
live50 = live64.live50
live49 = live64.live49
live48 = live64.live48
live46 = live64.live46
live44 = live64.live44
live43 = live64.live43
live41 = live64.live41
live39 = live64.live39
live37 = live64.live37
live35 = live64.live35
live34 = live64.live34
live31 = live64.live31
live24 = live64.live24
live17 = live64.live17
bot = live64.bot
live23 = live64.live23
live7 = live64.live7

NEW_STUDENT_STATE_KEY = "admin_new_student_registration"
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _new_student_cancel_markup():
    return live7.InlineKeyboardMarkup([
        [live7.InlineKeyboardButton("✖️ Отмена", callback_data="cab:newstudent:cancel")]
    ])


def _new_student_invite_markup(username):
    rows = []
    if username:
        rows.append([
            live7.InlineKeyboardButton(
                "👤 Подключить личный кабинет",
                url=f"https://t.me/{username}?start=link",
            )
        ])
    rows.append([live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return live7.InlineKeyboardMarkup(rows)


def _save_new_student(name, email):
    email = bot.normalize_email(email)
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, telegram_user_id FROM students WHERE lower(user_email) = lower(?) LIMIT 1",
            (email,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE students
                SET user_name = ?,
                    active = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (name, now, int(row[0])),
            )
            student_id = int(row[0])
            already_linked = row[1] is not None
            created = False
        else:
            cur = conn.execute(
                """
                INSERT INTO students
                    (coreapp_user_id, user_email, user_name, course_id, active,
                     telegram_user_id, telegram_username, updated_at)
                VALUES ('', ?, ?, '', 1, NULL, NULL, ?)
                """,
                (email, name, now),
            )
            student_id = int(cur.lastrowid)
            already_linked = False
            created = True
        conn.commit()
    return student_id, created, already_linked


def _active_student_count():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM students WHERE active = 1").fetchone()[0] or 0)


_previous_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_new_student():
    base = _previous_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    if not any(
        getattr(button, "callback_data", None) == "cab:newstudent"
        for row in rows for button in row
    ):
        insert_at = max(0, len(rows) - 1)
        rows.insert(insert_at, [
            live7.InlineKeyboardButton("➕ Новый ученик", callback_data="cab:newstudent")
        ])
    return live7.InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_new_student

_previous_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_new_student(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = str(query.data or "")

    if data == "cab:newstudent":
        await query.answer()
        context.user_data[NEW_STUDENT_STATE_KEY] = {"stage": "name"}
        await query.message.reply_text(
            "➕ <b>Регистрация нового ученика</b>\n\n"
            "Шаг 1 из 2. Напиши <b>имя и фамилию ребёнка</b> одним сообщением.\n\n"
            "Например: <code>Анна Иванова</code>",
            parse_mode="HTML",
            reply_markup=_new_student_cancel_markup(),
        )
        return

    if data == "cab:newstudent:cancel":
        context.user_data.pop(NEW_STUDENT_STATE_KEY, None)
        await query.answer("Регистрация отменена")
        await query.edit_message_text("✖️ Регистрация нового ученика отменена.")
        return

    await _previous_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_new_student

_previous_text_router = live7.student_text_router


async def student_text_router_with_new_student(update, context):
    if (
        update.effective_chat.type == "private"
        and bot.user_is_admin(update)
        and update.message
        and update.message.text
        and context.user_data.get(NEW_STUDENT_STATE_KEY)
    ):
        state = context.user_data.get(NEW_STUDENT_STATE_KEY) or {}
        text = str(update.message.text or "").strip()
        stage = state.get("stage")

        if stage == "name":
            if len(text) < 2:
                await update.message.reply_text("Имя слишком короткое. Напиши имя и фамилию ребёнка ещё раз.")
                return
            state["name"] = text
            state["stage"] = "email"
            context.user_data[NEW_STUDENT_STATE_KEY] = state
            await update.message.reply_text(
                "Шаг 2 из 2. Теперь отправь <b>e-mail ребёнка из CoreApp</b>.\n\n"
                "По этому адресу ребёнок потом привяжет Telegram и получит личный кабинет.",
                parse_mode="HTML",
                reply_markup=_new_student_cancel_markup(),
            )
            return

        if stage == "email":
            email = bot.normalize_email(text)
            if not _EMAIL_RE.match(email):
                await update.message.reply_text(
                    "Похоже, это не e-mail. Отправь адрес в формате <code>name@example.com</code>.",
                    parse_mode="HTML",
                    reply_markup=_new_student_cancel_markup(),
                )
                return

            name = str(state.get("name") or "Ученик").strip()
            student_id, created, already_linked = _save_new_student(name, email)
            context.user_data.pop(NEW_STUDENT_STATE_KEY, None)

            me = await context.bot.get_me()
            action = "добавлен в базу" if created else "обновлён в базе"
            link_status = (
                "Telegram у этого ученика уже привязан ✅"
                if already_linked
                else "Теперь перешли ребёнку сообщение ниже, чтобы он подключил Telegram."
            )
            await update.message.reply_text(
                "✅ <b>Ученик зарегистрирован</b>\n\n"
                f"👤 {html.escape(name)}\n"
                f"📧 {html.escape(email)}\n\n"
                f"Запись {action}. Активных учеников сейчас: <b>{_active_student_count()}</b>.\n"
                f"{link_status}",
                parse_mode="HTML",
            )

            if not already_linked:
                await update.message.reply_text(
                    "📩 <b>Сообщение для ребёнка — можно переслать целиком:</b>\n\n"
                    "Привет! 💗 Подключи свой личный кабинет «ЕГЭ БЛИЗКО».\n"
                    "Нажми кнопку ниже, запусти бота и отправь e-mail, который используешь в CoreApp.\n"
                    "После привязки появится кнопка «👤 Мой кабинет».",
                    parse_mode="HTML",
                    reply_markup=_new_student_invite_markup(getattr(me, "username", None)),
                )
            else:
                await update.message.reply_text(
                    "Ученик уже может пользоваться личным кабинетом.",
                    reply_markup=live7.InlineKeyboardMarkup([
                        [live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")]
                    ]),
                )
            print(f"Admin registered student record id={student_id}; created={created}; linked={already_linked}", flush=True)
            return

    await _previous_text_router(update, context)


live7.student_text_router = student_text_router_with_new_student


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
    live56.log_probnik_cabinet_audit()
    print("New student registration button ready", flush=True)
    print("Actionable admin task list ready", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print("Safe /test oxides route ready", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)
    live24.main()
