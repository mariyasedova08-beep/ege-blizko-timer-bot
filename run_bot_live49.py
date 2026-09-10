import sqlite3
from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

import run_bot_live48

live48 = run_bot_live48
live47 = live48.live47
live46 = live48.live46
live45 = live48.live45
live44 = live48.live44
live43 = live48.live43
live41 = live48.live41
live39 = live48.live39
live37 = live48.live37
live35 = live48.live35
live34 = live48.live34
live31 = live48.live31
live24 = live48.live24
live17 = live48.live17
live7 = live48.live7
live23 = live48.live23
live15 = live48.live15
bot = live48.bot
run_bot = live48.run_bot

COURSE_NAME = "Годовой курс подготовки к ЕГЭ по Химии"


def _student_by_telegram(telegram_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                   user_name, user_email, coreapp_user_id, telegram_user_id
            FROM students
            WHERE active = 1 AND telegram_user_id = ?
            LIMIT 1
            """,
            (int(telegram_id),),
        ).fetchone()


def _student_by_id(student_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                   user_name, user_email, coreapp_user_id, telegram_user_id
            FROM students
            WHERE active = 1 AND id = ?
            LIMIT 1
            """,
            (int(student_id),),
        ).fetchone()


def _parent_student_ids(telegram_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return [
            int(r[0])
            for r in conn.execute(
                """
                SELECT student_id
                FROM parent_links
                WHERE telegram_user_id = ? AND active = 1
                ORDER BY id
                """,
                (int(telegram_id),),
            ).fetchall()
        ]


def _first_name(student):
    shown = str(student[1] or "").strip() if student else ""
    return shown.split()[0] if shown else ""


def _student5(student):
    return (student[0], student[1], student[4], student[3], student[5])


def _monthly_metrics(student, now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        names = live15._probnik_names_for_month(conn, now.year, now.month)
        return live15._student_month_metrics(conn, _student5(student), now.year, now.month, names)


def _latest_probnik(student):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT student_name, event_name, event_date, secondary_score, tasks_json
            FROM probnik_results
            WHERE secondary_score IS NOT NULL
            ORDER BY substr(event_date, 7, 4) DESC,
                     substr(event_date, 4, 2) DESC,
                     substr(event_date, 1, 2) DESC,
                     id DESC
            """
        ).fetchall()
    for row in rows:
        if live43._match_student(row[0], [student]):
            return row
    return None


def _contact_button():
    admin_id = bot.get_admin_id()
    if not admin_id:
        return None
    return InlineKeyboardButton(
        "✉️ Написать Марии Александровне",
        url=f"tg://user?id={int(admin_id)}",
    )


def _student_home_markup():
    rows = [
        [
            InlineKeyboardButton("📊 Неделя", callback_data="triv:studentcab:week"),
            InlineKeyboardButton("📅 Месяц", callback_data="triv:studentcab:month"),
        ],
        [
            InlineKeyboardButton("🏠 ДЗ", callback_data="triv:studentcab:homework"),
            InlineKeyboardButton("🎓 Посещение", callback_data="triv:studentcab:attendance"),
        ],
        [
            InlineKeyboardButton("📝 Пробники", callback_data="triv:studentcab:probnik"),
            InlineKeyboardButton("🧪 Тренажёры", callback_data="triv:studentcab:trainers"),
        ],
        [InlineKeyboardButton("🧠 Слабые места", callback_data="triv:studentcab:weak")],
    ]
    contact = _contact_button()
    if contact:
        rows.append([contact])
    return InlineKeyboardMarkup(rows)


def _back_markup():
    rows = [[InlineKeyboardButton("← В мой кабинет", callback_data="triv:studentcab:home")]]
    contact = _contact_button()
    if contact:
        rows.append([contact])
    return InlineKeyboardMarkup(rows)


def _student_home_text(student):
    now = datetime.now(bot.TIMEZONE)
    first = _first_name(student)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        att_present, att_total = live41._weekly_attendance(conn, int(student[0]), now)
        hw_done, hw_total = live41._weekly_homework(conn, student, now)
        sessions, questions, correct = live41._weekly_trainer_stats(conn, int(student[5]), now)
    latest = _latest_probnik(student)
    probnik = "пока нет результата"
    if latest:
        score = latest[3]
        try:
            score = int(float(score)) if float(score).is_integer() else round(float(score), 1)
        except Exception:
            pass
        probnik = f"{latest[1]} — {score} баллов"
    accuracy = round(correct * 100 / questions) if questions else None
    trainer = f"{sessions} трен. · {accuracy}%" if questions else "0 тренировок"
    att = f"{att_present}/{att_total}" if att_total else "—"
    hw = f"{hw_done}/{hw_total}" if hw_total else "—"
    greeting = f"Привет, {first}! 💗" if first else "Привет! 💗"
    return "\n".join([
        greeting,
        "",
        "👤 Твой личный кабинет",
        f"🎓 {COURSE_NAME}",
        "",
        "📍 Сейчас:",
        f"🎓 Посещение за неделю: {att}",
        f"🏠 ДЗ за неделю: {hw}",
        f"🧪 Тренажёры за неделю: {trainer}",
        f"📝 Последний пробник: {probnik}",
        "",
        "Выбирай раздел ниже 👇",
    ])


def _attendance_text(student):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT s.lesson_number, s.lesson_date, ar.status
            FROM attendance_records ar
            JOIN attendance_sessions s ON s.lesson_number = ar.lesson_number
            WHERE ar.student_id = ? AND s.finalized = 1
            ORDER BY s.lesson_date DESC
            LIMIT 8
            """,
            (int(student[0]),),
        ).fetchall()
    lines = ["🎓 Посещаемость", ""]
    if not rows:
        return "\n".join(lines + ["Пока нет сохранённых отметок посещаемости."])
    present = sum(1 for _, _, status in rows if status == "present")
    lines.append(f"Последние {len(rows)} уроков: {present}/{len(rows)} посещено")
    lines.append("")
    for lesson, lesson_date, status in rows:
        icon = "✅" if status == "present" else "❌"
        try:
            shown_date = datetime.strptime(lesson_date, "%Y-%m-%d").strftime("%d.%m")
        except Exception:
            shown_date = str(lesson_date)
        lines.append(f"{icon} Урок №{lesson} · {shown_date}")
    return "\n".join(lines)


def _homework_text(student):
    today = datetime.now(bot.TIMEZONE).date()
    dates = run_bot.COURSE_LESSON_DATES
    expected = [i + 1 for i in range(len(dates) - 1) if dates[i + 1] <= today]
    expected = expected[-6:]
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        submissions = conn.execute(
            """
            SELECT user_id, lower(user_email), lesson_id, lesson_name
            FROM homework_submissions
            WHERE (coalesce(user_id, '') != '' AND user_id = ?)
               OR (coalesce(user_email, '') != '' AND lower(user_email) = lower(?))
            """,
            (str(student[4] or ""), str(student[3] or "")),
        ).fetchall()
    lines = ["🏠 Домашние работы", ""]
    if not expected:
        return "\n".join(lines + ["Пока нет ДЗ, срок которых уже наступил."])
    done_count = 0
    statuses = []
    for lesson_number in expected:
        previous_date = dates[lesson_number - 1]
        target_number = lesson_number + 1
        matched = any(
            live31._submission_explicitly_matches(
                lesson_id, lesson_name, target_number, lesson_number, previous_date
            )
            for _uid, _mail, lesson_id, lesson_name in submissions
        )
        if matched:
            done_count += 1
        statuses.append((lesson_number, matched))
    lines.append(f"Последние обязательные работы: {done_count}/{len(statuses)} закрыто")
    lines.append("")
    for lesson_number, matched in statuses:
        lines.append(f"{'✅' if matched else '⏳'} ДЗ после урока №{lesson_number}")
    return "\n".join(lines)


def _probnik_text(student):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT student_name, event_name, event_date, secondary_score, tasks_json
            FROM probnik_results
            WHERE secondary_score IS NOT NULL
            ORDER BY substr(event_date, 7, 4) DESC,
                     substr(event_date, 4, 2) DESC,
                     substr(event_date, 1, 2) DESC,
                     id DESC
            """
        ).fetchall()
    matched = [row for row in rows if live43._match_student(row[0], [student])][:5]
    lines = ["📝 Пробники", ""]
    if not matched:
        return "\n".join(lines + ["Пока нет синхронизированных результатов."])
    for _name, event_name, event_date, score, _tasks in matched:
        try:
            score = int(float(score)) if float(score).is_integer() else round(float(score), 1)
        except Exception:
            pass
        lines.append(f"• {event_name} · {event_date} — {score} баллов")
    return "\n".join(lines)


def _trainer_stats_text(student):
    uid = int(student[5])
    now = datetime.now(bot.TIMEZONE)
    prefix = f"{now.year:04d}-{now.month:02d}%"
    tables = [
        ("🧫 Тривиальные названия", "trivial_sessions"),
        ("🧪 Кислоты и остатки", "acid_sessions"),
        ("⚙️ Металлы", "metals_sessions"),
    ]
    lines = ["🧪 Тренажёры — этот месяц", ""]
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for title, table in tables:
            sessions, total, correct = conn.execute(
                f"""
                SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
                FROM {table}
                WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at LIKE ?
                """,
                (uid, prefix),
            ).fetchone()
            sessions, total, correct = int(sessions or 0), int(total or 0), int(correct or 0)
            pct = round(correct * 100 / total) if total else 0
            lines.append(f"{title}: {sessions} трен. · {pct}%")
    return "\n".join(lines)


def _weak_text(student):
    uid = int(student[5])
    trivial_errors = len(live7.unresolved_error_ids(uid))
    acid_errors = len(live17._unresolved_errors(uid))
    metals_errors = len(live48._unresolved_error_ids(uid))
    latest = _latest_probnik(student)
    lines = ["🧠 Слабые места", ""]
    if latest:
        weak = live43._zero_tasks(latest[4])
        if weak:
            lines.append("📝 Последний пробник: " + ", ".join(f"№{n}" for n in weak[:10]))
        else:
            lines.append("📝 В последнем пробнике нет заданий с 0 баллов.")
    else:
        lines.append("📝 По пробникам пока недостаточно данных.")
    lines.extend([
        "",
        "❌ Ошибки для повторения в тренажёрах:",
        f"• Тривиальные названия: {trivial_errors}",
        f"• Кислоты и остатки: {acid_errors}",
        f"• Металлы: {metals_errors}",
    ])
    return "\n".join(lines)


async def _trainer_markup(context, back_callback="triv:studentcab:home"):
    me = await context.bot.get_me()
    rows = []
    if me.username:
        for title, start_param in live41._active_trainers():
            rows.append([InlineKeyboardButton(title, url=f"https://t.me/{me.username}?start={start_param}")])
    rows.append([InlineKeyboardButton("← В мой кабинет", callback_data=back_callback)])
    contact = _contact_button()
    if contact:
        rows.append([contact])
    return InlineKeyboardMarkup(rows)


async def show_student_cabinet(update, context, student=None, edit=False):
    student = student or _student_by_telegram(update.effective_user.id)
    if not student:
        await update.effective_message.reply_text(
            "👤 Личный кабинет откроется после привязки Telegram к записи ученика.\n\n"
            "Используй /link и привяжи e-mail из CoreApp 💗"
        )
        return
    text = _student_home_text(student)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=_student_home_markup())
    else:
        await update.effective_message.reply_text(text, reply_markup=_student_home_markup())


def _parent_home_markup(student_id):
    sid = int(student_id)
    rows = [
        [
            InlineKeyboardButton("📅 Месяц", callback_data=f"triv:studentcab:p:{sid}:month"),
            InlineKeyboardButton("🎓 Посещение", callback_data=f"triv:studentcab:p:{sid}:attendance"),
        ],
        [
            InlineKeyboardButton("🏠 ДЗ", callback_data=f"triv:studentcab:p:{sid}:homework"),
            InlineKeyboardButton("📝 Пробники", callback_data=f"triv:studentcab:p:{sid}:probnik"),
        ],
    ]
    contact = _contact_button()
    if contact:
        rows.append([contact])
    return InlineKeyboardMarkup(rows)


def _parent_home_text(student):
    now = datetime.now(bot.TIMEZONE)
    metrics = _monthly_metrics(student, now)
    lines = [
        "Здравствуйте!",
        "",
        "👨‍👩‍👧 Личный кабинет родителя",
        f"🎓 {COURSE_NAME}",
        f"👩‍🎓 Ученик: {student[1]}",
        "",
        f"📅 {live15.MONTH_NAMES[now.month]} {now.year}",
    ]
    lines.extend(live15._metrics_lines(metrics))
    return "\n".join(lines)


async def show_parent_cabinet(update, context, student_id=None, edit=False):
    parent_id = int(update.effective_user.id)
    allowed = _parent_student_ids(parent_id)
    if not allowed:
        return False
    if student_id is None:
        if len(allowed) > 1:
            rows = []
            for sid in allowed:
                student = _student_by_id(sid)
                if student:
                    rows.append([InlineKeyboardButton(student[1], callback_data=f"triv:studentcab:p:{sid}:home")])
            markup = InlineKeyboardMarkup(rows) if rows else None
            if edit and update.callback_query:
                await update.callback_query.edit_message_text("Здравствуйте!\n\nВыберите ученика:", reply_markup=markup)
            else:
                await update.effective_message.reply_text("Здравствуйте!\n\nВыберите ученика:", reply_markup=markup)
            return True
        student_id = allowed[0]
    if int(student_id) not in allowed:
        return True
    student = _student_by_id(student_id)
    if not student:
        return True
    text = _parent_home_text(student)
    markup = _parent_home_markup(student_id)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)
    return True


async def student_cabinet_callback(update, context):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = str(query.data or "")

    if data.startswith("triv:studentcab:p:"):
        parts = data.split(":")
        if len(parts) != 5:
            return
        try:
            sid = int(parts[3])
        except Exception:
            return
        action = parts[4]
        if sid not in _parent_student_ids(update.effective_user.id):
            await query.edit_message_text("Доступ к данным этого ученика не найден.")
            return
        student = _student_by_id(sid)
        if not student:
            return
        contact_rows = [[InlineKeyboardButton("← В кабинет", callback_data=f"triv:studentcab:p:{sid}:home")]]
        contact = _contact_button()
        if contact:
            contact_rows.append([contact])
        parent_back = InlineKeyboardMarkup(contact_rows)
        if action == "home":
            await show_parent_cabinet(update, context, sid, edit=True)
        elif action == "month":
            await query.edit_message_text(_parent_home_text(student), reply_markup=_parent_home_markup(sid))
        elif action == "attendance":
            await query.edit_message_text("Здравствуйте!\n\n" + _attendance_text(student), reply_markup=parent_back)
        elif action == "homework":
            await query.edit_message_text("Здравствуйте!\n\n" + _homework_text(student), reply_markup=parent_back)
        elif action == "probnik":
            await query.edit_message_text("Здравствуйте!\n\n" + _probnik_text(student), reply_markup=parent_back)
        return

    student = _student_by_telegram(update.effective_user.id)
    if not student:
        await query.edit_message_text("Сначала нужно привязать Telegram к ученику через /link.")
        return

    action = data.rsplit(":", 1)[-1]
    now = datetime.now(bot.TIMEZONE)
    if action == "home":
        await show_student_cabinet(update, context, student, edit=True)
    elif action == "week":
        await query.edit_message_text(live41.weekly_report_text(student, now), reply_markup=_back_markup())
    elif action == "month":
        metrics = _monthly_metrics(student, now)
        text = "\n".join([
            f"📅 Твои итоги месяца: {live15.MONTH_NAMES[now.month]} {now.year}",
            "",
            *live15._metrics_lines(metrics),
        ])
        await query.edit_message_text(text, reply_markup=_back_markup())
    elif action == "attendance":
        await query.edit_message_text(_attendance_text(student), reply_markup=_back_markup())
    elif action == "homework":
        await query.edit_message_text(_homework_text(student), reply_markup=_back_markup())
    elif action == "probnik":
        await query.edit_message_text(_probnik_text(student), reply_markup=_back_markup())
    elif action == "trainers":
        await query.edit_message_text(_trainer_stats_text(student), reply_markup=await _trainer_markup(context))
    elif action == "weak":
        await query.edit_message_text(_weak_text(student), reply_markup=_back_markup())


_previous_trivial_callback = live7.trivial_callback


async def combined_trivial_callback_with_student_cabinet(update, context):
    if update.callback_query and str(update.callback_query.data or "").startswith("triv:studentcab:"):
        await student_cabinet_callback(update, context)
        return
    await _previous_trivial_callback(update, context)


live7.trivial_callback = combined_trivial_callback_with_student_cabinet


_previous_start_router = live7.start_router


async def combined_start_router_with_student_cabinet(update, context):
    if update.effective_chat.type == "private" and context.args and context.args[0].lower() in {"cabinet", "my", "lk"}:
        student = _student_by_telegram(update.effective_user.id)
        if student:
            await show_student_cabinet(update, context, student=student)
            return
        if await show_parent_cabinet(update, context):
            return
    await _previous_start_router(update, context)


live7.start_router = combined_start_router_with_student_cabinet


_previous_text_router = live7.student_text_router


async def combined_text_router_with_student_cabinet(update, context):
    if update.effective_chat.type == "private" and update.message and update.message.text == "👤 Мой кабинет":
        student = _student_by_telegram(update.effective_user.id)
        if student:
            await show_student_cabinet(update, context, student=student)
            return
        if await show_parent_cabinet(update, context):
            return
        await update.message.reply_text("Сначала привяжи Telegram к своей записи через /link 💗")
        return
    await _previous_text_router(update, context)


live7.student_text_router = combined_text_router_with_student_cabinet

# Добавляем личный кабинет в постоянную клавиатуру ученика.
live7.STUDENT_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["👤 Мой кабинет"],
        ["🧪 Тривиальные названия"],
        ["❌ Мои ошибки", "📊 Моя статистика"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


_previous_cabinet_command = live23.cabinet_command


async def combined_cabinet_command(update, context):
    if bot.user_is_admin(update):
        await _previous_cabinet_command(update, context)
        return
    student = _student_by_telegram(update.effective_user.id)
    if student:
        await show_student_cabinet(update, context, student=student)
        return
    if await show_parent_cabinet(update, context):
        return
    await update.message.reply_text("Сначала привяжи Telegram к записи ученика через /link 💗")


live23.cabinet_command = combined_cabinet_command


_previous_test = bot.test


async def test_with_student_cabinet_preview(update, context):
    is_preview = bool(context.args) and context.args[0].lower() in {"studentcabinet", "cabinet", "lk", "лк"}
    if not is_preview:
        await _previous_test(update, context)
        return
    if update.effective_chat.type != "private" or not bot.user_is_admin(update):
        return
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                   user_name, user_email, coreapp_user_id, telegram_user_id
            FROM students
            WHERE active = 1 AND telegram_user_id IS NOT NULL
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
    if not row:
        await update.message.reply_text("🧪 ТЕСТ: пока нет привязанного ученика для предпросмотра.")
        return
    await update.message.reply_text(
        "🧪 ТЕСТ ЛИЧНОГО КАБИНЕТА — это видишь только ты. Ученику ничего не отправлено.\n\n"
        + _student_home_text(row),
        reply_markup=_student_home_markup(),
    )


bot.test = test_with_student_cabinet_preview


if __name__ == "__main__":
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
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live24.main()
