from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups


def _day_keyboard(selected, prefix):
    selected = set(int(x) for x in selected)
    labels = schedule.DAY_NAMES
    rows = [
        [
            InlineKeyboardButton(("✅ " if i in selected else "") + labels[i], callback_data=f"{prefix}:day:{i}")
            for i in (0, 1, 2)
        ],
        [
            InlineKeyboardButton(("✅ " if i in selected else "") + labels[i], callback_data=f"{prefix}:day:{i}")
            for i in (3, 4, 5)
        ],
        [InlineKeyboardButton(("✅ " if 6 in selected else "") + labels[6], callback_data=f"{prefix}:day:6")],
        [InlineKeyboardButton("Готово — перейти ко времени", callback_data=f"{prefix}:day:done")],
    ]
    return InlineKeyboardMarkup(rows)


def _selected_text(days):
    return ", ".join(schedule.DAY_NAMES[int(d)] for d in sorted(days))


# ---------- Individual schedule: choose several weekdays, then a time for each ----------

async def individual_pick_student(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sid = int(q.data.rsplit(":", 1)[1])
    student = schedule.get_student(q.from_user.id, sid)
    if not student:
        await q.edit_message_text("Не нашла ученика. Открой «👥 Ученики и группы» и попробуй снова.")
        return ConversationHandler.END
    context.user_data["lesson_sid"] = sid
    context.user_data["lesson_name"] = student["name"]
    context.user_data["lesson_days"] = []
    context.user_data.pop("lesson_times", None)
    context.user_data.pop("lesson_time_index", None)
    await q.edit_message_text(
        f"Ученик: {student['name']}\n\nВыбери все дни, когда проходят регулярные занятия. Можно выбрать несколько дней.",
        reply_markup=_day_keyboard([], "lesson"),
    )
    return schedule.ADD_LESSON_DAY


async def individual_pick_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    value = q.data.rsplit(":", 1)[1]
    selected = set(context.user_data.get("lesson_days", []))

    if value != "done":
        day = int(value)
        if day in selected:
            selected.remove(day)
        else:
            selected.add(day)
        context.user_data["lesson_days"] = sorted(selected)
        name = context.user_data.get("lesson_name", "Ученик")
        suffix = f"\n\nВыбрано: {_selected_text(selected)}" if selected else "\n\nПока ничего не выбрано."
        await q.edit_message_text(
            f"Ученик: {name}\n\nВыбери все дни, когда проходят регулярные занятия. Можно выбрать несколько дней.{suffix}",
            reply_markup=_day_keyboard(selected, "lesson"),
        )
        return schedule.ADD_LESSON_DAY

    if not selected:
        await q.answer("Выбери хотя бы один день", show_alert=True)
        return schedule.ADD_LESSON_DAY

    days = sorted(selected)
    context.user_data["lesson_days"] = days
    context.user_data["lesson_times"] = {}
    context.user_data["lesson_time_index"] = 0
    first = days[0]
    await q.edit_message_text(
        f"Выбрано: {_selected_text(days)}\n\n{schedule.DAY_NAMES_FULL[first]} — во сколько занятие?\nНапример: 18:30"
    )
    return schedule.ADD_LESSON_TIME


async def individual_pick_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = schedule.parse_time(update.message.text)
    if not time_text:
        await update.message.reply_text("Не поняла время. Напиши, например: 18:30")
        return schedule.ADD_LESSON_TIME

    days = context.user_data.get("lesson_days", [])
    idx = int(context.user_data.get("lesson_time_index", 0))
    if not days or idx >= len(days):
        await update.message.reply_text("Настройка сбилась. Открой расписание и попробуй снова.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END

    times = context.user_data.setdefault("lesson_times", {})
    day = int(days[idx])
    times[str(day)] = time_text
    idx += 1
    context.user_data["lesson_time_index"] = idx

    if idx < len(days):
        next_day = int(days[idx])
        await update.message.reply_text(
            f"✅ {schedule.DAY_NAMES_FULL[day]} — {time_text}\n\n{schedule.DAY_NAMES_FULL[next_day]} — во сколько занятие?"
        )
        return schedule.ADD_LESSON_TIME

    sid = context.user_data.get("lesson_sid")
    name = context.user_data.get("lesson_name", "Ученик")
    if sid is None:
        await update.message.reply_text("Настройка сбилась. Открой расписание и попробуй снова.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END

    for weekday in days:
        schedule.add_slot(update.effective_user.id, sid, int(weekday), times[str(int(weekday))])

    lines = [f"• {schedule.DAY_NAMES_FULL[int(d)]} — {times[str(int(d))]}" for d in days]
    for key in ("lesson_sid", "lesson_name", "lesson_days", "lesson_times", "lesson_time_index"):
        context.user_data.pop(key, None)
    await update.message.reply_text(
        f"✅ Расписание для {name} сохранено:\n" + "\n".join(lines),
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


# ---------- Group schedule: same multi-day flow ----------

async def group_pick_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = int(q.data.rsplit(":", 1)[1])
    row = groups.get_group(q.from_user.id, gid)
    if not row:
        await q.edit_message_text("Группа не найдена.")
        return ConversationHandler.END
    context.user_data["gs_gid"] = gid
    context.user_data["gs_name"] = row["name"]
    context.user_data["gs_days"] = []
    context.user_data.pop("gs_times", None)
    context.user_data.pop("gs_time_index", None)
    await q.edit_message_text(
        f"Группа: {row['name']}\n\nВыбери все дни, когда проходят регулярные занятия. Можно выбрать несколько дней.",
        reply_markup=_day_keyboard([], "gs"),
    )
    return groups.ADD_GROUP_SLOT_DAY


async def group_pick_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    value = q.data.rsplit(":", 1)[1]
    selected = set(context.user_data.get("gs_days", []))

    if value != "done":
        day = int(value)
        if day in selected:
            selected.remove(day)
        else:
            selected.add(day)
        context.user_data["gs_days"] = sorted(selected)
        name = context.user_data.get("gs_name", "Группа")
        suffix = f"\n\nВыбрано: {_selected_text(selected)}" if selected else "\n\nПока ничего не выбрано."
        await q.edit_message_text(
            f"Группа: {name}\n\nВыбери все дни, когда проходят регулярные занятия. Можно выбрать несколько дней.{suffix}",
            reply_markup=_day_keyboard(selected, "gs"),
        )
        return groups.ADD_GROUP_SLOT_DAY

    if not selected:
        await q.answer("Выбери хотя бы один день", show_alert=True)
        return groups.ADD_GROUP_SLOT_DAY

    days = sorted(selected)
    context.user_data["gs_days"] = days
    context.user_data["gs_times"] = {}
    context.user_data["gs_time_index"] = 0
    first = days[0]
    await q.edit_message_text(
        f"Выбрано: {_selected_text(days)}\n\n{schedule.DAY_NAMES_FULL[first]} — во сколько занятие?\nНапример: 18:30"
    )
    return groups.ADD_GROUP_SLOT_TIME


async def group_pick_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = schedule.parse_time(update.message.text)
    if not time_text:
        await update.message.reply_text("Не поняла время. Напиши, например: 18:30")
        return groups.ADD_GROUP_SLOT_TIME

    days = context.user_data.get("gs_days", [])
    idx = int(context.user_data.get("gs_time_index", 0))
    if not days or idx >= len(days):
        await update.message.reply_text("Настройка сбилась. Открой расписание и попробуй снова.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END

    times = context.user_data.setdefault("gs_times", {})
    day = int(days[idx])
    times[str(day)] = time_text
    idx += 1
    context.user_data["gs_time_index"] = idx

    if idx < len(days):
        next_day = int(days[idx])
        await update.message.reply_text(
            f"✅ {schedule.DAY_NAMES_FULL[day]} — {time_text}\n\n{schedule.DAY_NAMES_FULL[next_day]} — во сколько занятие?"
        )
        return groups.ADD_GROUP_SLOT_TIME

    gid = context.user_data.get("gs_gid")
    name = context.user_data.get("gs_name", "Группа")
    if gid is None:
        await update.message.reply_text("Настройка сбилась. Открой расписание и попробуй снова.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END

    for weekday in days:
        groups.add_group_slot(update.effective_user.id, gid, int(weekday), times[str(int(weekday))])

    lines = [f"• {schedule.DAY_NAMES_FULL[int(d)]} — {times[str(int(d))]}" for d in days]
    for key in ("gs_gid", "gs_name", "gs_days", "gs_times", "gs_time_index"):
        context.user_data.pop(key, None)
    await update.message.reply_text(
        f"✅ Расписание группы «{name}» сохранено:\n" + "\n".join(lines),
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


def patched_schedule_build_app():
    schedule.ensure_tables()
    base.stub = schedule.enhanced_stub
    app = base.build_app()
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(schedule.add_begin, pattern=r"^schedule:add$")],
        states={
            schedule.ADD_LESSON_STUDENT: [CallbackQueryHandler(individual_pick_student, pattern=r"^lesson:student:\d+$")],
            schedule.ADD_LESSON_DAY: [CallbackQueryHandler(individual_pick_days, pattern=r"^lesson:day:(?:[0-6]|done)$")],
            schedule.ADD_LESSON_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, individual_pick_time)],
        },
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(schedule.transfer_picker, pattern=r"^schedule:transfer$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(schedule.move_begin, pattern=r"^schedule:move:\d+$")],
        states={
            schedule.MOVE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule.move_date)],
            schedule.MOVE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule.move_time)],
        },
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(schedule.remove_picker, pattern=r"^schedule:remove$"))
    app.add_handler(CallbackQueryHandler(schedule.remove_apply, pattern=r"^schedule:rm:\d+$"))
    return app


def patched_groups_build_app():
    groups.ensure_tables()
    base.MAIN_KB = ReplyKeyboardMarkup(
        [["👥 Ученики и группы", "📅 Расписание"], ["🔔 Напоминания", "💳 Оплаты"], ["⚙️ Настройки"]],
        resize_keyboard=True,
    )
    schedule.schedule_menu = groups.schedule_selector
    app = schedule.build_app()

    app.add_handler(MessageHandler(filters.Regex(r"^👥 Ученики и группы$"), groups.people_menu))
    app.add_handler(CallbackQueryHandler(groups.individual_menu, pattern=r"^people:individual$"))
    app.add_handler(CallbackQueryHandler(groups.groups_menu, pattern=r"^people:groups$"))
    app.add_handler(CallbackQueryHandler(groups.people_back, pattern=r"^people:back$"))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(groups.add_group_begin, pattern=r"^group:add$")],
        states={groups.ADD_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, groups.add_group_name)]},
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(groups.remove_group_picker, pattern=r"^group:remove$"))
    app.add_handler(CallbackQueryHandler(groups.remove_group_apply, pattern=r"^group:rm:\d+$"))

    app.add_handler(CallbackQueryHandler(groups.individual_schedule_callback, pattern=r"^schedule:individual$"))
    app.add_handler(CallbackQueryHandler(groups.group_schedule_menu, pattern=r"^groups:schedule$"))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(groups.group_slot_add_begin, pattern=r"^gs:add$")],
        states={
            groups.ADD_GROUP_SLOT_GROUP: [CallbackQueryHandler(group_pick_group, pattern=r"^gs:group:\d+$")],
            groups.ADD_GROUP_SLOT_DAY: [CallbackQueryHandler(group_pick_days, pattern=r"^gs:day:(?:[0-6]|done)$")],
            groups.ADD_GROUP_SLOT_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, group_pick_time)],
        },
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(groups.group_transfer_picker, pattern=r"^gs:transfer$"))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(groups.group_move_begin, pattern=r"^gs:move:\d+$")],
        states={
            groups.MOVE_GROUP_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, groups.group_move_date)],
            groups.MOVE_GROUP_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, groups.group_move_time)],
        },
        fallbacks=[], per_message=False,
    ))
    app.add_handler(CallbackQueryHandler(groups.group_remove_picker, pattern=r"^gs:remove$"))
    app.add_handler(CallbackQueryHandler(groups.group_remove_apply, pattern=r"^gs:rm:\d+$"))
    return app


def apply():
    schedule.build_app = patched_schedule_build_app
    groups.build_app = patched_groups_build_app
