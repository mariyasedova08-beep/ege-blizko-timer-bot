import secrets
import sqlite3

import run_bot_live11

live11 = run_bot_live11
live10 = live11.live10
bot = live10.bot

_original_sheetsstatus = live10.sheetsstatus_command


def rotate_sheets_secret():
    live11.ensure_sheets_sync_settings()
    value = secrets.token_urlsafe(24)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("UPDATE sheets_sync_settings SET secret = ? WHERE id = 1", (value,))
        conn.commit()
    return value


async def sheetsstatus_with_rotate(update, context):
    if not (update.effective_chat.type == "private" and bot.user_is_admin(update)):
        return
    if context.args and context.args[0].lower() == "rotate":
        value = rotate_sheets_secret()
        await update.message.reply_text(
            "🔐 Новый код для синхронизации Google Sheets:\n\n"
            + value
            + "\n\nСтарый код больше не работает. Скопируй новый в Apps Script и никому его не пересылай."
        )
        return
    await _original_sheetsstatus(update, context)


live10.sheetsstatus_command = sheetsstatus_with_rotate


if __name__ == "__main__":
    live11.ensure_sheets_sync_settings()
    live10.main()
