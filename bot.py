import json
import os
import sqlite3
import threading
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from phrases import DAILY_PHRASES

# Дата ЕГЭ по химии
EXAM_DATE = date(2027, 6, 1)

# 264 уникальные фразы идут с 10.09.2026 по 31.05.2027 включительно
PHRASE_START_DATE = date(2026, 9, 10)

# Часовой пояс
TIMEZONE = ZoneInfo("Europe/Moscow")

# Временное локальное хранилище событий CoreApp.
# Для первого этапа интеграции этого достаточно; позже перенесём в постоянную БД.
COREAPP_DB_PATH = os.getenv("COREAPP_DB_PATH", "/tmp/coreapp_webhooks.db")


def today_moscow():
    return datetime.now(TIMEZONE).date()


def days_left():
    return (EXAM_DATE - today_moscow()).days


def get_daily_phrase(for_date=None):
    current_date = for_date or today_moscow()
    index = (current_date - PHRASE_START_DATE).days

    if 0 <= index < len(DAILY_PHRASES):
        return DAILY_PHRASES[index]

    return "Каждый день — ещё один маленький шаг к сотке."


def get_countdown_text():
    days = days_left()

    if days > 1:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            "До ЕГЭ по химии осталось\n"
            f"<b>{days} дней</b> 💗\n\n"
            f"{get_daily_phrase()}"
        )

    if days == 1:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            "До ЕГЭ по химии остался\n"
            "<b>1 день</b> 💗\n\n"
            f"{get_daily_phrase()}"
        )

    if days == 0:
        return (
            "🧪 <b>ЕГЭ близко</b>\n\n"
            "<b>ЕГЭ ПО ХИМИИ — СЕГОДНЯ!</b> 💗\n\n"
            "Вы уже сделали огромную работу. "
            "Теперь спокойно показываем всё, что умеем."
        )

    return (
        "🧪 <b>ЕГЭ близко</b>\n\n"
        "ЕГЭ по химии уже позади 💗"
    )


def get_homework_reminder_text():
    return (
        "📝 <b>Время домашки</b> 💗\n\n"
        "Не откладываем на потом — проверьте, что сегодняшняя домашняя работа сделана и отправлена в CoreApp.\n\n"
        "Спокойно, системно и по чуть-чуть каждый день — так и приходят к сильному результату 🧪"
    )


def get_target_thread_id():
    thread_id = os.getenv("MESSAGE_THREAD_ID")
    return int(thread_id) if thread_id else None


def init_coreapp_db():
    with sqlite3.connect(COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS homework_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                user_id TEXT,
                user_email TEXT,
                user_name TEXT,
                course_id TEXT,
                lesson_id TEXT,
                lesson_name TEXT,
                correct_count TEXT,
                total_count TEXT,
                raw_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_coreapp_submission(payload):
    with sqlite3.connect(COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO homework_submissions (
                received_at,
                user_id,
                user_email,
                user_name,
                course_id,
                lesson_id,
                lesson_name,
                correct_count,
                total_count,
                raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(TIMEZONE).isoformat(),
                str(payload.get("user_id", "")),
                str(payload.get("user_email", "")),
                str(payload.get("user_name", "")),
                str(payload.get("course_id", "")),
                str(payload.get("lesson_id", "")),
                str(payload.get("lesson_name", "")),
                str(payload.get("correct_count", "")),
                str(payload.get("total_count", "")),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        conn.commit()


def get_recent_coreapp_submissions(limit=5):
    with sqlite3.connect(COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT received_at, user_name, user_email, lesson_name
            FROM homework_submissions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows


class CoreAppWebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print("CoreApp HTTP:", format % args)

    def _send_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {"ok": True, "service": "ege-blizko-timer-bot"})
            return

        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path != "/coreapp/homework-submitted":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return

        expected_secret = os.getenv("COREAPP_WEBHOOK_SECRET", "")
        supplied_secret = parse_qs(parsed.query).get("secret", [""])[0]

        if not expected_secret or supplied_secret != expected_secret:
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body or "{}")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return

        try:
            save_coreapp_submission(payload)
        except Exception as exc:
            print("CoreApp save error:", repr(exc))
            self._send_json(500, {"ok": False, "error": "storage_error"})
            return

        print(
            "CoreApp homework submitted:",
            payload.get("user_name"),
            payload.get("user_email"),
            payload.get("lesson_name"),
        )
        self._send_json(200, {"ok": True})


def start_http_server():
    init_coreapp_db()
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), CoreAppWebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"HTTP-сервер CoreApp запущен на порту {port}")
    return server


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я таймер курса «ЕГЭ близко» 🧪\n\n"
        "Мои команды:\n"
        "/ege — сколько дней до ЕГЭ\n"
        "/weeks — сколько недель до ЕГЭ\n"
        "/chatid — показать ID этого чата\n"
        "/threadid — показать ID текущей темы\n"
        "/corestatus — проверить события CoreApp\n"
        "/test — отправить тестовый отсчёт в группу курса"
    )


async def ege(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        get_countdown_text(),
        parse_mode="HTML"
    )


async def weeks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = days_left()

    if days <= 0:
        await update.message.reply_text("ЕГЭ уже наступил 🧪")
        return

    weeks_count = days // 7
    remainder = days % 7

    await update.message.reply_text(
        "🧪 <b>ЕГЭ близко</b>\n\n"
        "До ЕГЭ осталось примерно\n"
        f"<b>{weeks_count} недель и {remainder} дней</b> 💗",
        parse_mode="HTML"
    )


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"ID этого чата:\n<code>{update.effective_chat.id}</code>",
        parse_mode="HTML"
    )


async def threadid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_thread_id = update.effective_message.message_thread_id

    if current_thread_id is None:
        await update.message.reply_text(
            "У этого сообщения нет ID темы. Отправьте /threadid внутри нужной темы форума."
        )
        return

    await update.message.reply_text(
        f"ID этой темы:\n<code>{current_thread_id}</code>",
        parse_mode="HTML"
    )


async def corestatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_recent_coreapp_submissions(5)

    if not rows:
        await update.message.reply_text(
            "CoreApp подключён, но событий о сданной домашней работе пока не получено."
        )
        return

    lines = ["✅ Последние события CoreApp:"]
    for received_at, user_name, user_email, lesson_name in rows:
        who = user_name or user_email or "ученик"
        lesson = lesson_name or "домашняя работа"
        lines.append(f"• {who} — {lesson}")

    await update.message.reply_text("\n".join(lines))


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("CHAT_ID")

    if not chat_id:
        await update.message.reply_text("CHAT_ID пока не настроен.")
        return

    target_chat_id = int(chat_id)
    target_thread_id = get_target_thread_id()

    await context.bot.send_message(
        chat_id=target_chat_id,
        message_thread_id=target_thread_id,
        text=(
            "🧪 <b>ТЕСТ ТАЙМЕРА</b>\n\n"
            + get_countdown_text()
        ),
        parse_mode="HTML"
    )

    if update.effective_chat.id != target_chat_id:
        await update.message.reply_text(
            "✅ Тестовое сообщение отправлено в группу курса."
        )


async def daily_countdown(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("CHAT_ID")

    if not chat_id:
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=get_target_thread_id(),
        text=get_countdown_text(),
        parse_mode="HTML"
    )


async def daily_homework_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("CHAT_ID")

    if not chat_id:
        return

    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=get_target_thread_id(),
        text=get_homework_reminder_text(),
        parse_mode="HTML"
    )


def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    start_http_server()

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ege", ege))
    application.add_handler(CommandHandler("weeks", weeks))
    application.add_handler(CommandHandler("chatid", chatid))
    application.add_handler(CommandHandler("threadid", threadid))
    application.add_handler(CommandHandler("corestatus", corestatus))
    application.add_handler(CommandHandler("test", test))

    # Ежедневное сообщение в 09:00 по Москве
    application.job_queue.run_daily(
        daily_countdown,
        time=datetime.strptime("09:00", "%H:%M").time().replace(
            tzinfo=TIMEZONE
        ),
    )

    # Напоминание о домашней работе: воскресенье, вторник и суббота в 19:00 по Москве
    # В python-telegram-bot: 0 = воскресенье, 2 = вторник, 6 = суббота
    application.job_queue.run_daily(
        daily_homework_reminder,
        time=datetime.strptime("19:00", "%H:%M").time().replace(
            tzinfo=TIMEZONE
        ),
        days=(0, 2, 6),
    )

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
