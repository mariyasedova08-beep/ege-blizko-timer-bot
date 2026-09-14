import os
import sqlite3
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.getenv("TEACHER_PRODUCT_BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "8080"))
DB_PATH = os.getenv("TEACHER_PRODUCT_DB_PATH", "/data/teacher_product.sqlite3")

NAME, SUBJECT, FORMAT, COUNT = range(4)
ADD_STUDENT_NAME, ADD_STUDENT_CONTACT = range(10, 12)

MAIN_KB = ReplyKeyboardMarkup(
    [["👥 Ученики", "📅 Расписание"], ["🔔 Напоминания", "💳 Оплаты"], ["⚙️ Настройки"]],
    resize_keyboard=True,
)


def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teachers (
                telegram_user_id INTEGER PRIMARY KEY,
                name TEXT,
                subject TEXT,
                work_format TEXT,
                student_count TEXT,
                timezone TEXT DEFAULT 'Europe/Moscow',
                onboarding_completed_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                contact TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (teacher_telegram_user_id) REFERENCES teachers(telegram_user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_students_teacher
            ON students(teacher_telegram_user_id, active, name);
            """
        )
        conn.commit()


def teacher(uid):
    with db() as conn:
        return conn.execute("SELECT * FROM teachers WHERE telegram_user_id=?", (int(uid),)).fetchone()


def upsert_teacher(uid, **fields):
    row = teacher(uid)
    now = datetime.utcnow().isoformat()
    if not row:
        with db() as conn:
            conn.execute(
                "INSERT INTO teachers (telegram_user_id, created_at) VALUES (?, ?)",
                (int(uid), now),
            )
            conn.commit()
    if fields:
        allowed = {"name", "subject", "work_format", "student_count", "timezone", "onboarding_completed_at"}
        clean = {k: v for k, v in fields.items() if k in allowed}
        if clean:
            sql = ", ".join(f"{k}=?" for k in clean)
            with db() as conn:
                conn.execute(
                    f"UPDATE teachers SET {sql} WHERE telegram_user_id=?",
                    tuple(clean.values()) + (int(uid),),
                )
                conn.commit()


def list_students(uid):
    with db() as conn:
        return conn.execute(
            "SELECT id, name, contact FROM students WHERE teacher_telegram_user_id=? AND active=1 ORDER BY lower(name)",
            (int(uid),),
        ).fetchall()


def add_student(uid, name, contact=""):
    with db() as conn:
        conn.execute(
            "INSERT INTO students (teacher_telegram_user_id, name, contact, created_at) VALUES (?, ?, ?, ?)",
            (int(uid), name.strip(), contact.strip(), datetime.utcnow().isoformat()),
        )
        conn.commit()


def remove_student(uid, student_id):
    with db() as conn:
        conn.execute(
            "UPDATE students SET active=0 WHERE id=? AND teacher_telegram_user_id=?",
            (int(student_id), int(uid)),
        )
        conn.commit()


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b'{"ok":true,"service":"teacher-product-mvp"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        return


def start_health_server():
    HTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    row = teacher(uid)
    if row and row["onboarding_completed_at"]:
        await update.message.reply_text(
            f"С возвращением, {row['name'] or 'коллега'} 💗\n\nЭто твой личный администратор преподавателя.",
            reply_markup=MAIN_KB,
        )
        return ConversationHandler.END

    upsert_teacher(uid)
    await update.message.reply_text(
        "Привет! Я помогу собрать учеников, расписание, переносы, напоминания и оплаты в одном месте.\n\n"
        "Начнём с короткой настройки. Как тебя зовут?"
    )
    return NAME


async def onboarding_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    upsert_teacher(update.effective_user.id, name=name)
    await update.message.reply_text("Какой предмет ты преподаёшь?")
    return SUBJECT


async def onboarding_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upsert_teacher(update.effective_user.id, subject=update.message.text.strip())
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Индивидуально", callback_data="fmt:individual")],
        [InlineKeyboardButton("В группах", callback_data="fmt:groups")],
        [InlineKeyboardButton("И так, и так", callback_data="fmt:mixed")],
    ])
    await update.message.reply_text("Как ты работаешь сейчас?", reply_markup=kb)
    return FORMAT


async def onboarding_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    value = q.data.split(":", 1)[1]
    labels = {"individual": "Индивидуально", "groups": "В группах", "mixed": "Индивидуально и в группах"}
    upsert_teacher(q.from_user.id, work_format=value)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("1–10", callback_data="cnt:1_10"), InlineKeyboardButton("11–30", callback_data="cnt:11_30")],
        [InlineKeyboardButton("31–60", callback_data="cnt:31_60"), InlineKeyboardButton("60+", callback_data="cnt:60_plus")],
    ])
    await q.edit_message_text(f"Формат: {labels[value]}\n\nСколько у тебя учеников?", reply_markup=kb)
    return COUNT


async def onboarding_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    value = q.data.split(":", 1)[1]
    upsert_teacher(q.from_user.id, student_count=value, onboarding_completed_at=datetime.utcnow().isoformat())
    row = teacher(q.from_user.id)
    await q.edit_message_text(
        "Готово 💗\n\n"
        f"{row['name']}, твой кабинет создан. Первый шаг — добавь реальных учеников, с которыми работаешь."
    )
    await context.bot.send_message(
        chat_id=q.from_user.id,
        text="Открывай «👥 Ученики» — дальше всё будет строиться вокруг них.",
        reply_markup=MAIN_KB,
    )
    return ConversationHandler.END


async def students_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    rows = list_students(uid)
    if rows:
        names = "\n".join(f"• {r['name']}" for r in rows[:20])
        text = f"👥 Ученики: {len(rows)}\n\n{names}"
        if len(rows) > 20:
            text += f"\n…ещё {len(rows)-20}"
    else:
        text = "👥 Пока учеников нет. Добавь первого — это займёт меньше минуты."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ученика", callback_data="student:add")],
        [InlineKeyboardButton("🗑 Удалить / архив", callback_data="student:remove")],
    ])
    await update.message.reply_text(text, reply_markup=kb)


async def add_student_begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Как зовут ученика?")
    return ADD_STUDENT_NAME


async def add_student_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_student_name"] = update.message.text.strip()
    await update.message.reply_text(
        "Добавь контакт ученика: Telegram @username, телефон или email.\n\n"
        "Если пока не хочешь — отправь «-»."
    )
    return ADD_STUDENT_CONTACT


async def add_student_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.text.strip()
    if contact == "-":
        contact = ""
    name = context.user_data.pop("new_student_name", "Ученик")
    add_student(update.effective_user.id, name, contact)
    count = len(list_students(update.effective_user.id))
    await update.message.reply_text(
        f"✅ {name} добавлен(а).\n\nСейчас в кабинете учеников: {count}.",
        reply_markup=MAIN_KB,
    )
    return ConversationHandler.END


async def remove_student_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = list_students(q.from_user.id)
    if not rows:
        await q.edit_message_text("Удалять пока некого 🙂")
        return
    buttons = [[InlineKeyboardButton(f"🗑 {r['name']}", callback_data=f"student:rm:{r['id']}")] for r in rows[:30]]
    await q.edit_message_text("Кого убрать в архив?", reply_markup=InlineKeyboardMarkup(buttons))


async def remove_student_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sid = int(q.data.rsplit(":", 1)[1])
    remove_student(q.from_user.id, sid)
    await q.edit_message_text("✅ Ученик перенесён в архив.")


async def stub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    labels = {
        "📅 Расписание": "📅 Расписание и переносы — следующий модуль MVP. Собираем его первым после учеников.",
        "🔔 Напоминания": "🔔 Автоматические напоминания будут привязаны к расписанию и переносам.",
        "💳 Оплаты": "💳 Учёт оплат войдёт в MVP после расписания.",
        "⚙️ Настройки": "⚙️ Настройки кабинета скоро появятся здесь.",
    }
    await update.message.reply_text(labels.get(update.message.text, "Раздел в разработке."), reply_markup=MAIN_KB)


def build_app():
    app = Application.builder().token(BOT_TOKEN).build()
    onboarding = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_name)],
            SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_subject)],
            FORMAT: [CallbackQueryHandler(onboarding_format, pattern=r"^fmt:")],
            COUNT: [CallbackQueryHandler(onboarding_count, pattern=r"^cnt:")],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    adding = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_student_begin, pattern=r"^student:add$")],
        states={
            ADD_STUDENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_student_name)],
            ADD_STUDENT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_student_contact)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )
    app.add_handler(onboarding)
    app.add_handler(adding)
    app.add_handler(MessageHandler(filters.Regex(r"^👥 Ученики$"), students_menu))
    app.add_handler(CallbackQueryHandler(remove_student_picker, pattern=r"^student:remove$"))
    app.add_handler(CallbackQueryHandler(remove_student_apply, pattern=r"^student:rm:\d+$"))
    app.add_handler(MessageHandler(filters.Regex(r"^(📅 Расписание|🔔 Напоминания|💳 Оплаты|⚙️ Настройки)$"), stub))
    return app


def main():
    ensure_tables()
    threading.Thread(target=start_health_server, daemon=True).start()
    print("Teacher Product MVP ready: onboarding + students", flush=True)
    if not BOT_TOKEN:
        print("TEACHER_PRODUCT_BOT_TOKEN is missing; health server stays available", flush=True)
        threading.Event().wait()
        return
    build_app().run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
