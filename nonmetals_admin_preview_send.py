import asyncio
import os
import sqlite3
from datetime import datetime

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

MARKER = "nonmetals_admin_preview_2026_09_12"
DB_PATH = os.getenv("COREAPP_DB_PATH", "/data/coreapp.sqlite3")


def _already_sent():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS one_time_admin_messages (message_key TEXT PRIMARY KEY, sent_at TEXT NOT NULL)")
            return bool(conn.execute("SELECT 1 FROM one_time_admin_messages WHERE message_key=?", (MARKER,)).fetchone())
    except Exception:
        return False


def _mark_sent():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS one_time_admin_messages (message_key TEXT PRIMARY KEY, sent_at TEXT NOT NULL)")
        conn.execute("INSERT OR IGNORE INTO one_time_admin_messages(message_key, sent_at) VALUES (?, ?)", (MARKER, datetime.utcnow().isoformat()))
        conn.commit()


async def _send():
    if _already_sent():
        print("NONMETALS_ADMIN_PREVIEW skipped=already_sent", flush=True)
        return
    token = os.getenv("BOT_TOKEN")
    admin = os.getenv("ADMIN_TELEGRAM_ID")
    if not token or not admin:
        print("NONMETALS_ADMIN_PREVIEW failed=missing_env", flush=True)
        return
    bot = Bot(token=token)
    me = await bot.get_me()
    username = me.username
    if not username:
        print("NONMETALS_ADMIN_PREVIEW failed=no_username", flush=True)
        return
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⚛️ Открыть тренажёр", url=f"https://t.me/{username}?start=nonmetals")]])
    await bot.send_message(
        chat_id=int(admin),
        text=(
            "🧪 ТЕСТ — тренажёр «Неметаллы»\n\n"
            "Это видишь только ты. Ученикам и в общий чат ничего не отправлено.\n\n"
            "Нажми кнопку ниже и проверь настоящий тренажёр как ученик: 10 / 20 / все 50 вопросов, ошибки и статистику."
        ),
        reply_markup=markup,
    )
    _mark_sent()
    print("NONMETALS_ADMIN_PREVIEW sent=1", flush=True)


try:
    asyncio.run(_send())
except Exception as exc:
    print(f"NONMETALS_ADMIN_PREVIEW failed={type(exc).__name__}:{exc}", flush=True)
