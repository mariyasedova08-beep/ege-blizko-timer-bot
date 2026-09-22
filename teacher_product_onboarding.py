"""Guided 10–15 minute setup for PREPODMIN teachers.

The wizard deliberately reuses the production forms for groups, students,
schedule and payments.  It only provides a progress screen and clear routing,
so there is one source of truth for every entity.
"""
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, ContextTypes, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_groups as groups
import teacher_product_schedule as schedule
import teacher_product_payments as payments


SETUP_LABEL = "🚀 Быстрая настройка"
_PATCHED = False
_ORIGINAL_ONBOARDING_COUNT = base.onboarding_count


def ensure_tables():
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_quick_setup (
                teacher_telegram_user_id INTEGER PRIMARY KEY,
                finished_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _table_exists(conn, name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def _count(conn, sql, params):
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] if row else 0)
    except Exception:
        return 0


def setup_status(uid):
    """Return progress derived from real product data, never from button clicks."""
    uid = int(uid)
    teacher = base.teacher(uid)
    with base.db() as conn:
        student_count = _count(
            conn,
            "SELECT COUNT(*) FROM students WHERE teacher_telegram_user_id=? AND active=1",
            (uid,),
        )
        group_count = _count(
            conn,
            "SELECT COUNT(*) FROM teacher_groups WHERE teacher_telegram_user_id=? AND active=1",
            (uid,),
        ) if _table_exists(conn, "teacher_groups") else 0
        member_count = _count(
            conn,
            "SELECT COUNT(*) FROM student_reminder_people WHERE teacher_id=? AND kind='group' AND active=1",
            (uid,),
        ) if _table_exists(conn, "student_reminder_people") else 0
        individual_slots = _count(
            conn,
            "SELECT COUNT(*) FROM schedule_slots WHERE teacher_telegram_user_id=? AND active=1",
            (uid,),
        ) if _table_exists(conn, "schedule_slots") else 0
        group_slots = _count(
            conn,
            "SELECT COUNT(*) FROM group_schedule_slots WHERE teacher_telegram_user_id=? AND active=1",
            (uid,),
        ) if _table_exists(conn, "group_schedule_slots") else 0
        payment_count = _count(
            conn,
            "SELECT COUNT(*) FROM student_payment_plans WHERE teacher_telegram_user_id=? AND active=1",
            (uid,),
        ) if _table_exists(conn, "student_payment_plans") else 0

    work_format = str(teacher["work_format"] or "mixed") if teacher else "mixed"
    profile_done = bool(teacher and teacher["onboarding_completed_at"])
    if work_format == "groups":
        people_done = group_count > 0 and member_count > 0
    elif work_format == "individual":
        people_done = student_count > 0
    else:
        people_done = student_count > 0 or (group_count > 0 and member_count > 0)
    schedule_done = individual_slots + group_slots > 0

    return {
        "profile": profile_done,
        "people": people_done,
        "schedule": schedule_done,
        "payments": payment_count > 0,
        "student_count": student_count,
        "group_count": group_count,
        "member_count": member_count,
        "work_format": work_format,
    }


def _main_keyboard():
    # Other PREPODMIN modules extend the keyboard while the app is assembled.
    # Preserve every existing button and only prepend the setup entry.
    existing = []
    for row in getattr(base.MAIN_KB, "keyboard", ()):
        labels = [button.text for button in row]
        if SETUP_LABEL not in labels:
            existing.append(labels)
    return ReplyKeyboardMarkup([[SETUP_LABEL], *existing], resize_keyboard=True)


def _mark(done):
    return "✅" if done else "○"


def _progress_text(uid):
    s = setup_status(uid)
    completed = sum(bool(s[key]) for key in ("profile", "people", "schedule", "payments"))
    return (
        "🚀 Быстрая настройка ПРЕП | АДМИН\n\n"
        f"Готово: {completed}/4 шагов\n\n"
        f"{_mark(s['profile'])} 1. Профиль преподавателя\n"
        f"{_mark(s['people'])} 2. Группы и ученики\n"
        f"{_mark(s['schedule'])} 3. Регулярное расписание\n"
        f"{_mark(s['payments'])} 4. Оплаты\n\n"
        "Нажми на следующий незавершённый шаг. После каждого шага возвращайся "
        "сюда — прогресс обновится автоматически. Обычно вся настройка занимает 10–15 минут."
    )


def _progress_markup(uid):
    s = setup_status(uid)
    buttons = []
    if not s["people"]:
        if s["work_format"] != "individual":
            buttons.append([InlineKeyboardButton("➕ Создать группу", callback_data="group:add")])
        if s["group_count"]:
            buttons.append([InlineKeyboardButton("👥 Добавить учеников в группу", callback_data="setup:group_people")])
        if s["work_format"] != "groups":
            buttons.append([InlineKeyboardButton("➕ Добавить индивидуального ученика", callback_data="student:add")])
    if not s["schedule"]:
        buttons.append([InlineKeyboardButton("📅 Добавить расписание", callback_data="setup:schedule")])
    if not s["payments"]:
        payment_callback = "pay:setup" if s["student_count"] else "setup:payment_help"
        buttons.append([InlineKeyboardButton("💳 Настроить оплату", callback_data=payment_callback)])
    buttons.append([InlineKeyboardButton("🔄 Обновить прогресс", callback_data="setup:home")])
    if s["people"] and s["schedule"]:
        buttons.append([InlineKeyboardButton("✅ Завершить настройку", callback_data="setup:finish")])
    return InlineKeyboardMarkup(buttons)


async def show_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = int(update.effective_user.id)
    text = _progress_text(uid)
    markup = _progress_markup(uid)
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        await q.edit_message_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)
    raise ApplicationHandlerStop


async def choose_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    s = setup_status(q.from_user.id)
    buttons = []
    if s["student_count"]:
        buttons.append([InlineKeyboardButton("👤 Индивидуальное занятие", callback_data="schedule:individual")])
    if s["group_count"]:
        buttons.append([InlineKeyboardButton("👥 Занятие группы", callback_data="groups:schedule")])
    if not buttons:
        buttons.append([InlineKeyboardButton("➕ Сначала добавить ученика", callback_data="student:add")])
        buttons.append([InlineKeyboardButton("➕ Сначала создать группу", callback_data="group:add")])
    buttons.append([InlineKeyboardButton("⬅️ К настройке", callback_data="setup:home")])
    await q.edit_message_text(
        "📅 Расписание\n\nВыбери, какое регулярное занятие добавить.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    raise ApplicationHandlerStop


async def choose_group_people(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = groups.groups(q.from_user.id)
    buttons = [
        [InlineKeyboardButton(f"👥 {row['name']}", callback_data=f"gmem:members:{row['id']}")]
        for row in rows[:40]
    ]
    buttons.append([InlineKeyboardButton("⬅️ К настройке", callback_data="setup:home")])
    await q.edit_message_text(
        "В какую группу добавить учеников?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    raise ApplicationHandlerStop


async def payment_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "💳 Оплаты\n\n"
        "Сначала добавь индивидуального ученика — после этого можно указать сумму, "
        "тип и ближайшую дату оплаты. Групповые оплаты пока не входят в быстрый запуск.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить ученика", callback_data="student:add")],
            [InlineKeyboardButton("⬅️ К настройке", callback_data="setup:home")],
        ]),
    )
    raise ApplicationHandlerStop


async def finish_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    ensure_tables()
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            INSERT INTO teacher_quick_setup(teacher_telegram_user_id,finished_at,updated_at)
            VALUES(?,?,?)
            ON CONFLICT(teacher_telegram_user_id) DO UPDATE SET
                finished_at=excluded.finished_at, updated_at=excluded.updated_at
            """,
            (uid, now, now),
        )
        conn.commit()
    await q.edit_message_text(
        "✅ Основная настройка готова!\n\n"
        "Теперь ПРЕП | АДМИН уже может показывать занятия, учеников и ближайшие дела. "
        "Оплаты и остальные разделы можно дополнять постепенно."
    )
    await context.bot.send_message(
        chat_id=uid,
        text="Открывай нужный раздел с клавиатуры ниже 💗",
        reply_markup=base.MAIN_KB,
    )
    raise ApplicationHandlerStop


async def onboarding_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish the short profile, then immediately open the guided product setup."""
    q = update.callback_query
    await q.answer()
    value = q.data.split(":", 1)[1]
    base.upsert_teacher(
        q.from_user.id,
        student_count=value,
        onboarding_completed_at=datetime.utcnow().isoformat(),
    )
    row = base.teacher(q.from_user.id)
    await q.edit_message_text(
        f"Готово, {row['name']} 💗\n\nПрофиль создан. Теперь за несколько шагов настроим рабочий кабинет."
    )
    await context.bot.send_message(
        chat_id=q.from_user.id,
        text=_progress_text(q.from_user.id),
        reply_markup=_progress_markup(q.from_user.id),
    )
    return -1


def patch():
    """Patch callbacks before the application handler tree is built."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True
    base.onboarding_count = onboarding_count


def install(app):
    ensure_tables()
    base.MAIN_KB = _main_keyboard()
    app.add_handler(MessageHandler(filters.Regex(r"^🚀 Быстрая настройка$"), show_setup), group=-30)
    app.add_handler(CallbackQueryHandler(show_setup, pattern=r"^setup:home$"), group=-30)
    app.add_handler(CallbackQueryHandler(choose_schedule, pattern=r"^setup:schedule$"), group=-30)
    app.add_handler(CallbackQueryHandler(choose_group_people, pattern=r"^setup:group_people$"), group=-30)
    app.add_handler(CallbackQueryHandler(payment_help, pattern=r"^setup:payment_help$"), group=-30)
    app.add_handler(CallbackQueryHandler(finish_setup, pattern=r"^setup:finish$"), group=-30)
