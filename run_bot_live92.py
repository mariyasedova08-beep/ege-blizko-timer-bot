"""Expose the existing student cabinet together with the trainer menu.

The student-cabinet implementation already lives in run_bot_live49. Later
parent/payment patches replaced its start and text routers, so linked students
were sent straight to the trainer-only screen. This final compatibility layer
restores the student cabinet for linked accounts while leaving parent, tutor,
survey, payment, and trainer routes in the fallback chain.
"""

from telegram import ReplyKeyboardMarkup

import run_bot_live49 as student_cabinet
import run_bot_live90 as live90


bot = student_cabinet.bot
live7 = live90.live7
live23 = live90.live23
STUDENT_CABINET_BUTTON = "👤 Мой кабинет"


_previous_start_router = live7.start_router


async def start_router_with_student_cabinet(update, context):
    if update.effective_chat.type == "private":
        args = [str(value or "").strip().lower() for value in (context.args or [])]
        if not args or args[0] in {"cabinet", "my", "lk"}:
            student = student_cabinet._student_by_telegram(update.effective_user.id)
            if student:
                await student_cabinet.show_student_cabinet(update, context, student=student)
                return
    return await _previous_start_router(update, context)


live7.start_router = start_router_with_student_cabinet


_previous_text_router = live7.student_text_router


async def text_router_with_student_cabinet(update, context):
    if (
        update.effective_chat.type == "private"
        and update.message
        and update.message.text
        and update.message.text.strip() == STUDENT_CABINET_BUTTON
    ):
        student = student_cabinet._student_by_telegram(update.effective_user.id)
        if student:
            await student_cabinet.show_student_cabinet(update, context, student=student)
            return
    return await _previous_text_router(update, context)


live7.student_text_router = text_router_with_student_cabinet


_previous_trivial_callback = live7.trivial_callback


async def trivial_callback_with_student_cabinet(update, context):
    query = update.callback_query
    if query and str(query.data or "").startswith("triv:studentcab:"):
        await student_cabinet.student_cabinet_callback(update, context)
        return
    return await _previous_trivial_callback(update, context)


live7.trivial_callback = trivial_callback_with_student_cabinet


_previous_cabinet_command = live23.cabinet_command


async def cabinet_command_with_student_cabinet(update, context):
    if not bot.user_is_admin(update):
        student = student_cabinet._student_by_telegram(update.effective_user.id)
        if student:
            await student_cabinet.show_student_cabinet(update, context, student=student)
            return
    return await _previous_cabinet_command(update, context)


live23.cabinet_command = cabinet_command_with_student_cabinet


# Keep every trainer/payment row that later patches added, but put the cabinet
# first and remove only obsolete parent-cabinet labels from student keyboards.
current = getattr(live7, "STUDENT_KEYBOARD", None)
rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []
rows = [
    row
    for row in rows
    if STUDENT_CABINET_BUTTON not in row
    and "👨‍👩‍👧 Личный кабинет" not in row
]
live7.STUDENT_KEYBOARD = ReplyKeyboardMarkup(
    [[STUDENT_CABINET_BUTTON]] + rows,
    resize_keyboard=True,
    is_persistent=True,
)


def verify_student_cabinet_wiring():
    if live7.start_router is not start_router_with_student_cabinet:
        raise RuntimeError("Student cabinet start route is not active")
    if live7.student_text_router is not text_router_with_student_cabinet:
        raise RuntimeError("Student cabinet text route is not active")
    if live7.trivial_callback is not trivial_callback_with_student_cabinet:
        raise RuntimeError("Student cabinet callback route is not active")
    keyboard_rows = getattr(live7.STUDENT_KEYBOARD, "keyboard", ())
    if not keyboard_rows or keyboard_rows[0] != [STUDENT_CABINET_BUTTON]:
        raise RuntimeError("Student cabinet button is missing from keyboard")
    print("LIVE92: student cabinet and trainer menu connected", flush=True)


verify_student_cabinet_wiring()
