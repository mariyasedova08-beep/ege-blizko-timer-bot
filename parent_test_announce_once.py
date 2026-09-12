"""Send Maria one one-time message opening the safe parent-cabinet test."""
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder

import parent_cabinet

bot = parent_cabinet.bot
KEY = "parent_cabinet_test_message_2026_09_12_v1"
_original_build = ApplicationBuilder.build


def ensure_table():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS one_time_admin_messages (
                message_key TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def already_sent():
    ensure_table()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            "SELECT 1 FROM one_time_admin_messages WHERE message_key = ?",
            (KEY,),
        ).fetchone() is not None


def mark_sent():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO one_time_admin_messages(message_key, sent_at) VALUES(?, ?)",
            (KEY, parent_cabinet.now().isoformat()),
        )
        conn.commit()


async def send_once(context):
    if already_sent():
        print("PARENT_TEST_MESSAGE skipped=already_sent", flush=True)
        return
    admin_id = bot.get_admin_id()
    if not admin_id:
        print("PARENT_TEST_MESSAGE failed=no_admin_id", flush=True)
        return
    try:
        await context.bot.send_message(
            chat_id=int(admin_id),
            text=(
                "🧪 <b>Тест родительского кабинета готов</b>\n\n"
                "Нажми кнопку ниже, выбери ученика и посмотри кабинет ровно так, как его будет видеть родитель. "
                "Тест не создаёт настоящую родительскую привязку."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧪 Открыть тест кабинета родителя", callback_data="cab:parents:test")]
            ]),
        )
        mark_sent()
        print("PARENT_TEST_MESSAGE sent=1 failed=0", flush=True)
    except Exception as exc:
        print(f"PARENT_TEST_MESSAGE sent=0 failed=1 error={type(exc).__name__}", flush=True)


def build_with_message(self):
    app = _original_build(self)
    app.job_queue.run_once(send_once, when=3, name="parent_test_message_once")
    return app


ensure_table()
ApplicationBuilder.build = build_with_message
print("Parent test one-time message registered", flush=True)
