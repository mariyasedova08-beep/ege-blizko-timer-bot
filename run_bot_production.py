"""Production entrypoint for EGE БЛИЗКО.

Keeps the existing production runtime patches while disabling the retired
teacher-survey feature before the rest of the application wrappers are installed.
"""
from datetime import datetime, time

import payment_name_aliases  # noqa: F401
import payment_delivery_hook  # noqa: F401
import payment_student_ui  # noqa: F401
import parent_cabinet  # noqa: F401
import parent_schema_compat  # noqa: F401
import parent_self_link_guard  # noqa: F401
import parent_admin_ui  # noqa: F401
import parent_test_ui  # noqa: F401
import parent_invite_campaign  # noqa: F401
import parent_forward_to_student  # noqa: F401
import parent_home_button  # noqa: F401

import run_bot_live90 as live90


def disable_teacher_survey():
    """Remove the retired teacher survey from all live production entry points."""
    # run_bot_live90 installs the survey wrappers at import time. Restore the
    # original handlers before later production modules wrap these routers.
    live90.live23.cabinet_markup = live90._previous_cabinet_markup
    live90.live23.cabinet_callback = live90._previous_cabinet_callback
    live90.live7.start_router = live90._previous_start_router
    live90.live7.student_text_router = live90._previous_text_router



def install_ege11_chat_trainer_focus():
    """Grade-11-only rotating trainer prompts, managed from teacher cabinet.

    Keeps the existing EGE Telegram group / topic, delivery hours and other
    recurring jobs. Old *automatic* trivia/acid/oxide-classification posts stop.
    """
    import html
    import os
    import sqlite3
    from contextlib import closing
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    import run_bot_live7 as live7
    import run_bot_live18 as live18
    import run_bot_live23 as live23
    import run_bot_live60 as live60

    bot = live90.bot
    CODE_ORDER = ("oxideprops", "hydroxides", "middlesalts", "specialsalts")
    DEFAULT_ACTIVE = {"oxideprops", "hydroxides"}
    GROUP_SLOTS = {0: ("mon", "11:00"), 4: ("fri", "16:00"), 5: ("sat", "14:00")}

    def db():
        return sqlite3.connect(bot.COREAPP_DB_PATH, timeout=20)

    def init():
        with closing(db()) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS ege11_trainer_focus (
                    code TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS ege11_trainer_settings (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    paused INTEGER NOT NULL DEFAULT 0 CHECK(paused IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS ege11_trainer_deliveries (
                    slot_key TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    trainer_code TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY(slot_key,chat_id)
                );
            """)
            conn.execute("INSERT OR IGNORE INTO ege11_trainer_settings(id,paused) VALUES(1,0)")
            for code in CODE_ORDER:
                conn.execute(
                    "INSERT OR IGNORE INTO ege11_trainer_focus(code,enabled) VALUES(?,?)",
                    (code, 1 if code in DEFAULT_ACTIVE else 0),
                )
            conn.commit()

    def focus_state():
        with closing(db()) as conn:
            return {
                row[0]: bool(row[1])
                for row in conn.execute("SELECT code,enabled FROM ege11_trainer_focus")
            }

    def is_paused():
        with closing(db()) as conn:
            value = conn.execute(
                "SELECT paused FROM ege11_trainer_settings WHERE id=1"
            ).fetchone()
        return bool(value[0]) if value else True

    def catalog():
        with closing(db()) as conn:
            rows = conn.execute(
                "SELECT code,title,start_param FROM weekly_trainer_catalog "
                "WHERE active=1 AND code IN (?,?,?,?)",
                CODE_ORDER,
            ).fetchall()
        return {row[0]: (row[1], row[2]) for row in rows}

    def target_chat():
        value = os.getenv("CHAT_ID", "").strip()
        if not value:
            return None
        try:
            chat_id = int(value)
        except ValueError:
            return None
        # The separate OGE group must never receive grade-11 reminders.
        return chat_id if chat_id != -1004449482685 else None

    async def post_to_11(context, slot_key, code):
        chat_id = target_chat()
        entry = catalog().get(code)
        if chat_id is None or not entry:
            return False
        with closing(db()) as conn:
            exists = conn.execute(
                "SELECT 1 FROM ege11_trainer_deliveries "
                "WHERE slot_key=? AND chat_id=?",
                (slot_key, chat_id),
            ).fetchone()
        if exists:
            return False
        me = await context.bot.get_me()
        if not me.username:
            return False
        title, start_param = entry
        link = "https://t.me/" + me.username + "?start=" + start_param
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🧪 Открыть тренажёр", url=link)
        ]])
        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=bot.get_target_thread_id(),
            text=(
                "💗 <b>ЕГЭ БЛИЗКО — актуальная практика</b>\n\n"
                "Сегодня закрепляем: <b>" + html.escape(title) + "</b>.\n\n"
                "Выберите 10–20 вопросов, а после загляните в «Мои ошибки».\n"
                "Мы играем в долгую — немного практики регулярно 💗"
            ),
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        with closing(db()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO ege11_trainer_deliveries"
                "(slot_key,chat_id,trainer_code,sent_at) VALUES(?,?,?,?)",
                (slot_key, chat_id, code, datetime.now(bot.TIMEZONE).isoformat()),
            )
            conn.commit()
        print("EGE11 trainer group notification delivered: code=" + code, flush=True)
        return True

    def next_code(chat_id):
        focus = focus_state()
        available = catalog()
        codes = [code for code in CODE_ORDER if focus.get(code) and code in available]
        if not codes:
            return None
        with closing(db()) as conn:
            last = conn.execute(
                "SELECT trainer_code FROM ege11_trainer_deliveries "
                "WHERE chat_id=? ORDER BY sent_at DESC LIMIT 1",
                (chat_id,),
            ).fetchone()
        previous = last[0] if last else None
        return codes[(codes.index(previous) + 1) % len(codes)] if previous in codes else codes[0]

    def make_markup():
        source = old_markup()
        return InlineKeyboardMarkup([
            *source.inline_keyboard,
            [InlineKeyboardButton(
                "📣 Тренажёры ЕГЭ · 11 класс", callback_data="cab:e11:home"
            )],
        ])

    def settings_markup():
        focus = focus_state()
        titles = catalog()
        rows = []
        for code in CODE_ORDER:
            title = titles.get(code, (code, ""))[0]
            status = "✅" if focus.get(code) else "▫️"
            rows.append([InlineKeyboardButton(
                status + " " + title,
                callback_data="cab:e11:toggle:" + code,
            )])
        rows.extend([
            [InlineKeyboardButton(
                "▶️ Возобновить" if is_paused() else "⏸ Приостановить",
                callback_data="cab:e11:pause",
            )],
            [InlineKeyboardButton("← Кабинет Маши", callback_data="cab:e11:back")],
        ])
        return InlineKeyboardMarkup(rows)

    async def show_settings(query):
        focus = focus_state()
        names = catalog()
        selected = [names[c][0] for c in CODE_ORDER if focus.get(c) and c in names]
        chat = target_chat()
        if is_paused():
            status = "⏸ Публикации приостановлены"
        elif chat is None:
            status = "⚠️ Для ЕГЭ 11 не настроен CHAT_ID"
        elif not selected:
            status = "⏸ Нет выбранных тренажёров"
        else:
            status = "✅ Напоминания включены"
        await query.edit_message_text(
            "📣 <b>ЕГЭ · 11 класс — тренажёры в чат</b>\n\n"
            + status
            + "\n\n<b>Актуальны сейчас:</b>\n"
            + ("\n".join("• " + html.escape(t) for t in selected) if selected else "Темы не выбраны")
            + "\n\nПонедельник 11:00 · пятница 16:00 · суббота 14:00 (МСК).\n"
            + "Одно напоминание за раз, темы чередуются.\n\n"
            + "Нажми на тему, чтобы включить или отключить её. "
            + "Тренажёры остаются доступными детям.\n"
            + "Старые автоматические напоминания о кислотах, классификации "
            + "оксидов и тривиальных названиях отключены.",
            parse_mode="HTML",
            reply_markup=settings_markup(),
        )

    async def cabinet_callback(update, context):
        query = update.callback_query
        if (not query or not live23._admin_private(update) or
                not str(query.data or "").startswith("cab:e11:")):
            return await old_callback(update, context)
        command = str(query.data).split(":")
        await query.answer()
        if command[2] == "back":
            await query.edit_message_text(
                live23.cabinet_text(), parse_mode="HTML",
                reply_markup=live23.cabinet_markup(),
            )
            return
        if command[2] == "pause":
            with closing(db()) as conn:
                conn.execute(
                    "UPDATE ege11_trainer_settings SET paused=1-paused WHERE id=1"
                )
                conn.commit()
        elif command[2] == "toggle" and len(command) == 4:
            code = command[3]
            if code in CODE_ORDER:
                with closing(db()) as conn:
                    conn.execute(
                        "UPDATE ege11_trainer_focus SET enabled=1-enabled WHERE code=?",
                        (code,),
                    )
                    conn.commit()
        await show_settings(query)

    async def disabled_old_group_post(context):
        return False

    # Keep these trainers available, suppress only their obsolete group posts.
    live7.send_trivial_announcement = disabled_old_group_post
    live18.send_acid_saturday_reminder = disabled_old_group_post
    live60.send_oxides_announcement = disabled_old_group_post

    old_markup = live23.cabinet_markup
    old_callback = live23.cabinet_callback
    old_tick = live7.friday_trivial_tick

    async def tick(context):
        await old_tick(context)
        try:
            now = datetime.now(bot.TIMEZONE)
            config = GROUP_SLOTS.get(now.weekday())
            if config is None or now.strftime("%H:%M") != config[1]:
                return
            if is_paused():
                return
            chat_id = target_chat()
            if chat_id is None:
                return
            code = next_code(chat_id)
            if code:
                await post_to_11(context, now.date().isoformat() + ":" + config[0], code)
        except Exception as exc:
            print("EGE11 trainer group tick failed: " + type(exc).__name__, flush=True)

    init()
    live23.cabinet_markup = make_markup
    live23.cabinet_callback = cabinet_callback
    live7.friday_trivial_tick = tick
    print("EGE11 current-topic chat reminders ready; legacy trainer posts disabled", flush=True)


def main():
    disable_teacher_survey()

    # Student feedback campaign is separate from the retired teacher survey.
    # Same six identified questions are sent on the first of each month Oct-May.
    import student_monthly_survey
    student_monthly_survey.install()

    # Retired anonymous survey: keep Maria's archive/results only.
    import student_anonymous_why_admin_only
    student_anonymous_why_admin_only.install()

    # Compatibility alias: live60 already exposes the live15 module used by the
    # existing metals/oxides metrics, while live79 does not export it directly.
    live90.live79.live15 = live90.live79.live60.live15

    import nonmetals_trainer
    nonmetals_trainer.install()

    import oxide_properties_trainer
    oxide_properties_trainer.install()

    import hydroxides_trainer
    hydroxides_trainer.install()

    import middle_salts_trainer
    middle_salts_trainer.install()

    # Additional 50-question salt chemistry trainer; preserves all existing handlers.
    import special_salts_trainer
    special_salts_trainer.install()

    # Personal launch campaigns at 16:00 Moscow.
    import oxide_properties_campaign  # noqa: F401
    import hydroxides_campaign  # noqa: F401

    import individual_trainer_daily
    import instagram_return_system
    import instagram_current_stage_patch  # noqa: F401
    import instagram_daily_reminder
    import student_keyboard_cleanup
    import homework_deadline_logic

    live90.live79.live71.ensure_molar_access_tables()
    live90.live79.live70.ensure_health_tables()
    live90.live79.live59.ensure_coreapp_webhook_audit_table()
    live90.live79.live31.live25.ensure_lesson_day_before_table()
    live90.live79.live31.live24.ensure_probnik_poll_tables()
    live90.live79.live28.ensure_unanswered_reminder_tables()
    live90.live79.live31.live30.live3.ensure_attendance_tables()
    live90.live79.live31.live30.ensure_auto_attendance_table()

    import attendance_correction_20260930
    attendance_correction_20260930.seed()
    live90.live79.live31.ensure_personal_homework_reminder_table()
    live90.live79.live17.ensure_acid_tables()
    live90.live79.live24.live18.ensure_acid_reminder_table()
    live90.live79.live34.ensure_attention_tables()
    live90.live79.live35.ensure_admin_tasks_table()
    live90.live79.ensure_task_sections()
    live90.live79.live73.ensure_admin_task_view_state()
    live90.live79.live35.seed_monday_task()
    import polina_salary_tasks
    polina_salary_tasks.seed()

    import timeweb_migration_task  # noqa: F401

    import prepodmin_roadmap_tasks
    prepodmin_roadmap_tasks.seed()

    import attendance_fix_20260930
    attendance_fix_20260930.seed()
    live90.live79.live37.update_monday_task_text()
    live90.live79.live39.seed_probnik_return_task()
    live90.live79.live41.ensure_weekly_report_tables()
    live90.live79.live41.seed_current_trainers()
    live90.live79.live48.ensure_metals_tables()
    live90.live79.live48.register_metals_trainer()
    live90.live79.live60.ensure_oxides_tables()
    live90.live79.live60.register_oxides_trainer()
    nonmetals_trainer.ensure_nonmetals_tables()
    nonmetals_trainer.register_nonmetals_trainer()
    live90.live79.live43.ensure_probnik_analysis_tables()
    live90.live79.live44.enable_probnik_analysis_now()
    live90.live79.live46.ensure_monthly_auto_report_table()
    live90.live79.live50.seed_molar_mass_task()
    live90.live79.live51.ensure_course_schedule_table()
    live90.live79.live66.seed_zlata_accounting_task()
    live90.live79.live67.ensure_individual_students_table()
    individual_trainer_daily.install()

    # Do not catch up a missed daily reminder late in the evening after a restart.
    # The existing scheduler runs repeatedly, so a short window is enough to make
    # delivery restart-safe while preserving the requested 16:00 timing.
    original_individual_tick = individual_trainer_daily.individual_daily_trainer_tick

    async def individual_tick_1600_window(context):
        now = datetime.now(live90.bot.TIMEZONE)
        if not (time(16, 0) <= now.time() < time(16, 10)):
            return
        await original_individual_tick(context)

    individual_trainer_daily.individual_daily_trainer_tick = individual_tick_1600_window

    instagram_return_system.install()
    instagram_daily_reminder.install()
    student_keyboard_cleanup.install()
    # Install last: it must wrap the final periodic tick and replace the legacy
    # generic homework job before live24.main registers scheduled jobs.
    homework_deadline_logic.install()

    import metals_olya_campaign  # noqa: F401

    live90.live79.live71.complete_molar_mass_task()
    live90.live79.live74.ensure_notification_catchup_tables()
    live90.live79.live77.ensure_lesson_feedback_tables()
    live90.live79.live78.seed_priority_tasks()
    live90.live84.seed_teacher_product_tasks()
    live90.live85.ensure_payment_tables()
    live90.payment_schedule.ensure_payment_plans()
    live90.live79.live56.log_probnik_cabinet_audit()

    print("Teacher survey removed from production UI and routes", flush=True)
    print("Student feedback surveys scheduled monthly: 2026-10-01 through 2027-05-01 at 17:00", flush=True)
    print("Anonymous why-Masha survey: admin archive only; student input disabled", flush=True)
    print("Payment tracking ready: grade 11 Excel import, admin preview only", flush=True)
    print("Teacher product first five tasks seeded", flush=True)
    print("Admin tasks separated: active / completed / content / technical", flush=True)
    print("Admin current-task table shows first seven tasks", flush=True)
    print("Completed admin tasks stay completed after restart", flush=True)
    print("Lesson feedback ready: Mon/Wed 20:30, Sun 13:00; summary +1.5h", flush=True)
    print("Group traffic light ready", flush=True)
    print("Restart-safe notification catch-up enabled", flush=True)
    print("Admin task views auto-refresh after completion", flush=True)
    print("Today dashboard ready", flush=True)
    print("Molar mass calculator ready for admin and tutor", flush=True)
    print("Health monitoring and Telegram admin error alerts enabled", flush=True)
    print("Probnik group reminders enabled: Thu/Fri + Friday poll + Sat morning", flush=True)
    print("Probnik personal no-response DMs enabled: 1.5h before probnik", flush=True)
    print("Probnik attention/parent escalation remains paused", flush=True)
    print("Individual students trainer-only mode ready", flush=True)
    print("Individual students daily trainer reminder: every day 16:00", flush=True)
    print("Individual students trainer stats available in admin cabinet", flush=True)
    print("Instagram 90-day return system available in admin cabinet", flush=True)
    print("Instagram current-stage positioning: profile first, content from next day", flush=True)
    print("Instagram daily plan reminder: every day 11:00", flush=True)
    print("Student stale parent keyboard cleanup enabled", flush=True)
    print("Homework deadlines: Sun->Sun, Mon->Wed, Wed->Mon", flush=True)
    print("Schedule-based homework cabinet ready", flush=True)
    print(f"Oxides trainer ready: questions={len(live90.live79.live60.OXIDES_BANK)} monday_reminder=11:00", flush=True)
    print(f"Nonmetals trainer ready: questions={len(nonmetals_trainer.NONMETALS_BANK)}", flush=True)
    print(
        f"Oxide properties trainer ready: questions={len(oxide_properties_trainer.OXIDE_PROPERTIES_BANK)}; "
        "dm=2026-10-01..07 16:00 Moscow",
        flush=True,
    )
    print(
        f"Hydroxides trainer ready: questions={len(hydroxides_trainer.HYDROXIDES_BANK)}",
        flush=True,
    )
    print(
        f"Middle salts trainer ready: questions={len(middle_salts_trainer.MIDDLE_SALTS_BANK)}",
        flush=True,
    )
    print(f"Special salts trainer ready: questions={len(special_salts_trainer.SPECIAL_SALTS_BANK)}", flush=True)
    print("CoreApp live sync receiver v2 ready", flush=True)

    import run_bot_live91  # noqa: F401
    import run_bot_live94  # noqa: F401
    import run_bot_live95  # noqa: F401
    import run_bot_live96  # noqa: F401
    import run_bot_live97  # noqa: F401
    import tutor_dashboard  # noqa: F401
    import tutor_seed_20260914  # noqa: F401
    import admin_quick_tasks

    # Install last so the quick-task button wraps the final cabinet/text routers.
    admin_quick_tasks.install()

    import individual_exam_countdown
    individual_exam_countdown.install()

    # Install after the final admin wrappers: Tomorrow should wrap the current
    # cabinet and task handlers rather than replacing any of them.
    import admin_tomorrow
    admin_tomorrow.install()

    # Install last: preserve all final cabinet/task wrappers and add
    # teacher-only editing + student read-only lesson recordings.
    import lesson_recordings
    lesson_recordings.install()

    # Student homework cabinet: show every evidenced unfinished CoreApp assignment.
    import student_homework_all_debts
    student_homework_all_debts.install()

    # Final student UX layer: one persistent button, all navigation inside cabinet.
    import student_keyboard_compact
    student_keyboard_compact.install()

    # Private beautiful admin WebApp: Maria only. Do not expose to students/tutor/parents.
    import ege_admin_webapp
    ege_admin_webapp.install()

    # Monthly Kulyochki: automatic rewards, practical-lesson awards,
    # student cabinet, discount draw and breakthrough-of-the-month flow.
    import kulek_rewards
    kulek_rewards.install()

    # Student beautiful WebApp: personal read-only cabinet for each linked child.
    # Install after Kulechki so its launcher wraps the final student cabinet UI.
    import ege_student_webapp
    ege_student_webapp.install()

    # Public trainer hub for subscribers of the Telegram channel.
    # Install last so the channel gate wraps the final start/trainer/admin routes
    # without exposing paid-course cabinets or homework.
    import public_channel_trainers
    public_channel_trainers.SPECIAL_STATS_TABLES["specialsalts"] = "specialsalts_sessions"
    public_channel_trainers.install()

    # Interactive chemistry laboratory inside EGE BLIZKO trainers.
    import ege_lab_webapp
    ege_lab_webapp.install()

    # Direct Google Sheets payment sync. Install after all runtime wrappers so
    # /sheets/payment-sync remains the outermost HTTP route.
    import payment_google_sheets_sync  # noqa: F401

    import oge9_trainer_notifications
    oge9_trainer_notifications.install()

    # Grade-11 chat topics rotate independently of OGE9 and personal campaigns.
    install_ege11_chat_trainer_focus()

    live90.live79.live24.main()


if __name__ == "__main__":
    main()
