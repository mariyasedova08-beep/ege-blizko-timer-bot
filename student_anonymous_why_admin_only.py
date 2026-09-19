"""Admin-only compatibility layer for the retired anonymous student survey.

Keeps Maria's cabinet summary/responses, disables all student participation and
scheduled recovery/delivery. Old invitation buttons receive a closed notice.
"""
from telegram.ext import ApplicationBuilder, CallbackQueryHandler

import student_anonymous_why_survey as survey

_original_build = None
_installed = False


async def closed_callback(update, context):
    query = update.callback_query
    if not query or query.data != "anonwhy:start":
        return
    await query.answer("Опрос завершён", show_alert=True)


def _build_admin_only(self):
    application = _original_build(self)
    application.add_handler(
        CallbackQueryHandler(closed_callback, pattern=r"^anonwhy:start$"),
        group=-10000,
    )
    return application


def install():
    global _original_build, _installed
    if _installed:
        return

    survey.ensure_tables()
    survey._patch_admin_cabinet()

    _original_build = ApplicationBuilder.build
    ApplicationBuilder.build = _build_admin_only

    _installed = True
    print(
        "Anonymous why-Masha survey admin-only: student input disabled; admin archive retained",
        flush=True,
    )
