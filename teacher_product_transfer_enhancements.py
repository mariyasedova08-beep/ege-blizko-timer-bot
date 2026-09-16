"""Friendlier lesson transfers plus immediate Telegram notifications for linked pupils."""

from datetime import date, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, ConversationHandler

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_student_reminders as student_reminders

_PATCHED = False


def _fmt_date(value):
    return date.fromisoformat(value).strftime("%d.%m")


def _same_date_markup(kind, slot_id, original):
    prefix = "ind" if kind == "individual" else "group"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"🕒 Только время — оставить {_fmt_date(original)}",
            callback_data=f"xfer:{prefix}:same:{int(slot_id)}",
        )
    ]])


def _delivery_summary(kind, sent, failed, total):
    if total == 0:
        return (
            "📨 Уведомление не отправлено: Telegram ученика ещё не привязан."
            if kind == "individual"
            else "📨 Уведомления не отправлены: в группе пока нет привязанных Telegram."
        )
    if failed == 0:
        return "📨 Ученик уведомлён." if kind == "individual" else f"📨 Уведомления отправлены: {sent}."
    return f"⚠️ Уведомления: отправлено {sent}, не доставлено {failed}."


async def _notify_transfer(context, uid, kind, slot_id, original, old_time, new_date, new_time):
    if kind == "individual":
        row = schedule.slot(uid, slot_id)
        if not row:
            return 0, 0, 0
        event = {"kind": "individual", "person_id": int(row["student_id"])}
        group_name = None
    else:
        row = groups.group_slot(uid, slot_id)
        if not row:
            return 0, 0, 0
        event = {"kind": "group", "person_id": int(row["group_id"])}
        group_name = row["group_name"]

    people = student_reminders.recipients(uid, event)
    sent = 0
    failed = 0
    for person in people:
        lines = [
            f"↪️ {person['name']}, занятие перенесено.",
            "",
            f"Было: {_fmt_date(original)} в {old_time}",
            f"Стало: {_fmt_date(new_date)} в {new_time}",
        ]
        if group_name:
            lines.insert(2, f"Группа: {group_name}")
        try:
            await context.bot.send_message(person["telegram_user_id"], "\n".join(lines))
            sent += 1
            print(f"Transfer notification sent person={person['id']}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"Transfer notification failed person={person['id']}: {type(exc).__name__}", flush=True)
    return sent, failed, len(people)


async def individual_move_begin(update, context):
    q = update.callback_query
    await q.answer()
    s = schedule.slot(q.from_user.id, int(q.data.rsplit(":", 1)[1]))
    if not s:
        await q.edit_message_text("Занятие не найдено. Открой расписание заново.")
        return ConversationHandler.END
    original = schedule.next_date(q.from_user.id, s)
    context.user_data.update(
        move_slot=int(s["id"]),
        move_original=original.isoformat(),
        move_name=s["student_name"],
        move_old_time=s["time_text"],
    )
    await q.edit_message_text(
        f"Переносим: {s['student_name']} — {original.strftime('%d.%m')} в {s['time_text']}.\n\n"
        "Можно изменить дату и время или только время.\n\n"
        "Новая дата — напиши, например: 18.09\n"
        "Только время — нажми кнопку ниже или сразу напиши новое время, например: 19:00",
        reply_markup=_same_date_markup("individual", s["id"], original.isoformat()),
    )
    return schedule.MOVE_DATE


async def individual_same_date(update, context):
    q = update.callback_query
    await q.answer()
    slot_id = int(q.data.rsplit(":", 1)[1])
    original = context.user_data.get("move_original")
    if context.user_data.get("move_slot") != slot_id or not original:
        await q.answer("Открой перенос занятия заново", show_alert=True)
        raise ApplicationHandlerStop
    context.user_data["move_new_date"] = original
    context.user_data["move_same_date_pending"] = True
    await q.edit_message_text(f"Дата остаётся {_fmt_date(original)}.\n\nНапиши новое время, например: 19:00")
    raise ApplicationHandlerStop


async def individual_move_date(update, context):
    if context.user_data.pop("move_same_date_pending", False):
        return await individual_move_time(update, context)

    raw = update.message.text
    direct_time = schedule.parse_time(raw)
    if direct_time:
        original = context.user_data.get("move_original")
        if not original:
            await update.message.reply_text("Перенос сбился. Попробуй ещё раз через «📅 Расписание».", reply_markup=base.MAIN_KB)
            return ConversationHandler.END
        context.user_data["move_new_date"] = original
        return await individual_move_time(update, context)

    today = datetime.now(schedule.tz(update.effective_user.id)).date()
    d = schedule.parse_date(raw, today)
    if not d or d < today:
        await update.message.reply_text(
            "Не поняла дату. Напиши, например: 18.09.\n"
            "Если меняется только время — напиши сразу новое время, например: 19:00"
        )
        return schedule.MOVE_DATE
    context.user_data["move_new_date"] = d.isoformat()
    await update.message.reply_text("Во сколько будет занятие в эту дату? Например: 19:00")
    return schedule.MOVE_TIME


async def individual_move_time(update, context):
    t = schedule.parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Не поняла время. Напиши, например: 19:00")
        return schedule.MOVE_TIME

    slot_id = context.user_data.pop("move_slot", None)
    original = context.user_data.pop("move_original", None)
    new_date = context.user_data.pop("move_new_date", None)
    name = context.user_data.pop("move_name", "Ученик")
    old_time = context.user_data.pop("move_old_time", "")
    context.user_data.pop("move_same_date_pending", None)
    if not slot_id or not original or not new_date:
        await update.message.reply_text("Перенос сбился. Попробуй ещё раз через «📅 Расписание».", reply_markup=base.MAIN_KB)
        return ConversationHandler.END
    if original == new_date and old_time == t:
        await update.message.reply_text("ℹ️ Дата и время не изменились.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END

    schedule.save_move(update.effective_user.id, slot_id, original, new_date, t)
    sent, failed, total = await _notify_transfer(
        context, update.effective_user.id, "individual", slot_id, original, old_time, new_date, t
    )
    await update.message.reply_text(
        f"✅ Перенос сохранён.\n{name}: {_fmt_date(original)} {old_time} → {_fmt_date(new_date)} {t}.\n\n"
        f"{_delivery_summary('individual', sent, failed, total)}",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


async def group_move_begin(update, context):
    q = update.callback_query
    await q.answer()
    s = groups.group_slot(q.from_user.id, int(q.data.rsplit(":", 1)[1]))
    if not s:
        await q.edit_message_text("Занятие не найдено.")
        return ConversationHandler.END
    original = groups.next_group_date(q.from_user.id, s)
    context.user_data.update(
        gm_slot=int(s["id"]),
        gm_original=original.isoformat(),
        gm_name=s["group_name"],
        gm_old_time=s["time_text"],
    )
    await q.edit_message_text(
        f"Переносим: {s['group_name']} — {original.strftime('%d.%m')} в {s['time_text']}.\n\n"
        "Можно изменить дату и время или только время.\n\n"
        "Новая дата — напиши, например: 18.09\n"
        "Только время — нажми кнопку ниже или сразу напиши новое время, например: 19:00",
        reply_markup=_same_date_markup("group", s["id"], original.isoformat()),
    )
    return groups.MOVE_GROUP_DATE


async def group_same_date(update, context):
    q = update.callback_query
    await q.answer()
    slot_id = int(q.data.rsplit(":", 1)[1])
    original = context.user_data.get("gm_original")
    if context.user_data.get("gm_slot") != slot_id or not original:
        await q.answer("Открой перенос занятия заново", show_alert=True)
        raise ApplicationHandlerStop
    context.user_data["gm_new_date"] = original
    context.user_data["gm_same_date_pending"] = True
    await q.edit_message_text(f"Дата остаётся {_fmt_date(original)}.\n\nНапиши новое время, например: 19:00")
    raise ApplicationHandlerStop


async def group_move_date(update, context):
    if context.user_data.pop("gm_same_date_pending", False):
        return await group_move_time(update, context)

    raw = update.message.text
    direct_time = schedule.parse_time(raw)
    if direct_time:
        original = context.user_data.get("gm_original")
        if not original:
            await update.message.reply_text("Перенос сбился. Попробуй ещё раз через расписание.", reply_markup=base.MAIN_KB)
            return ConversationHandler.END
        context.user_data["gm_new_date"] = original
        return await group_move_time(update, context)

    today = datetime.now(schedule.tz(update.effective_user.id)).date()
    d = schedule.parse_date(raw, today)
    if not d or d < today:
        await update.message.reply_text(
            "Не поняла дату. Напиши, например: 18.09.\n"
            "Если меняется только время — напиши сразу новое время, например: 19:00"
        )
        return groups.MOVE_GROUP_DATE
    context.user_data["gm_new_date"] = d.isoformat()
    await update.message.reply_text("Во сколько будет занятие в эту дату? Например: 19:00")
    return groups.MOVE_GROUP_TIME


async def group_move_time(update, context):
    t = schedule.parse_time(update.message.text)
    if not t:
        await update.message.reply_text("Не поняла время. Напиши, например: 19:00")
        return groups.MOVE_GROUP_TIME

    slot_id = context.user_data.pop("gm_slot", None)
    original = context.user_data.pop("gm_original", None)
    new_date = context.user_data.pop("gm_new_date", None)
    name = context.user_data.pop("gm_name", "Группа")
    old_time = context.user_data.pop("gm_old_time", "")
    context.user_data.pop("gm_same_date_pending", None)
    if not slot_id or not original or not new_date:
        await update.message.reply_text("Перенос сбился. Попробуй ещё раз через расписание.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END
    if original == new_date and old_time == t:
        await update.message.reply_text("ℹ️ Дата и время не изменились.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END

    groups.save_group_move(update.effective_user.id, slot_id, original, new_date, t)
    sent, failed, total = await _notify_transfer(
        context, update.effective_user.id, "group", slot_id, original, old_time, new_date, t
    )
    await update.message.reply_text(
        f"✅ Перенос группы сохранён.\n{name}: {_fmt_date(original)} {old_time} → {_fmt_date(new_date)} {t}.\n\n"
        f"{_delivery_summary('group', sent, failed, total)}",
        reply_markup=base.MAIN_KB,
    )
    return ConversationHandler.END


def patch():
    global _PATCHED
    if _PATCHED:
        return
    schedule.move_begin = individual_move_begin
    schedule.move_date = individual_move_date
    schedule.move_time = individual_move_time
    groups.group_move_begin = group_move_begin
    groups.group_move_date = group_move_date
    groups.group_move_time = group_move_time
    _PATCHED = True


def install(app):
    app.add_handler(CallbackQueryHandler(individual_same_date, pattern=r"^xfer:ind:same:\d+$"), group=-13)
    app.add_handler(CallbackQueryHandler(group_same_date, pattern=r"^xfer:group:same:\d+$"), group=-13)
    print("Transfer notifications and time-only moves ready", flush=True)
