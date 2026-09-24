import os

from telegram import Update
from telegram.ext import ContextTypes

import teacher_product_tasks as tasks


def _voice_enabled():
    return os.getenv("PREPADMIN_VOICE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _allowed_ids():
    if not _voice_enabled():
        return set()
    raw = os.getenv("VOICE_BETA_USER_IDS", "").strip()
    result = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result


ORIGINAL_VOICE_TASK = tasks.voice_task


async def beta_voice_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    allowed = _allowed_ids()
    uid = int(update.effective_user.id)
    if uid not in allowed:
        await update.message.reply_text(
            "🎙 Голосовые задачи пока выключены на время пилота. "
            "Добавь задачу через «✅ Задачи» → «➕ Добавить текстом»."
        )
        return
    return await ORIGINAL_VOICE_TASK(update, context)


def build_app():
    tasks.voice_task = beta_voice_task
    return tasks.build_app()
