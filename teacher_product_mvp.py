import os
import secrets
import sqlite3
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
import teacher_product_subjects as subject_catalog

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
BOT_USERNAME = os.getenv("TEACHER_PRODUCT_BOT_USERNAME", "prepodmin_bot").strip().lstrip("@") or "prepodmin_bot"
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
                subject_id TEXT,
                theme_id TEXT NOT NULL DEFAULT 'pink-pulse',
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
        # Additive migration: never drop or reset existing teacher/student records.
        columns = {r[1] for r in conn.execute("PRAGMA table_info(teachers)")}
        if "subject_id" not in columns:
            conn.execute("ALTER TABLE teachers ADD COLUMN subject_id TEXT")
        if "theme_id" not in columns:
            conn.execute("ALTER TABLE teachers ADD COLUMN theme_id TEXT NOT NULL DEFAULT 'pink-pulse'")
        # Preserve every legacy free-text subject, including multi-subject labels.
        # Only fill a catalog ID when the existing value is an unambiguous alias.
        for row in conn.execute(
            "SELECT telegram_user_id, subject FROM teachers "
            "WHERE subject_id IS NULL AND subject IS NOT NULL"
        ).fetchall():
            item = subject_catalog.subject_by_text(row["subject"])
            if item:
                conn.execute(
                    "UPDATE teachers SET subject_id=? WHERE telegram_user_id=?",
                    (item["id"], row["telegram_user_id"]),
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
        allowed = {"name", "subject", "subject_id", "theme_id", "work_format", "student_count", "timezone", "onboarding_completed_at"}
        clean = {k: v for k, v in fields.items() if k in allowed}
        if "subject" in clean and "subject_id" not in clean:
            # Old code may still update the text field; never keep a stale icon ID.
            item = subject_catalog.subject_by_text(clean["subject"])
            clean["subject_id"] = item["id"] if item else None
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
        cursor = conn.execute(
            "INSERT INTO students (teacher_telegram_user_id, name, contact, created_at) VALUES (?, ?, ?, ?)",
            (int(uid), name.strip(), contact.strip(), datetime.utcnow().isoformat()),
        )
        student_id = int(cursor.lastrowid)
        conn.commit()
    return student_id


def normalize_telegram_username(value):
    raw = str(value or "").strip()
    if raw == "-":
        return ""
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
            break
    raw = raw.split("?", 1)[0].strip().strip("/").lstrip("@")
    if not raw:
        return ""
    if not all(ch.isalnum() or ch == "_" for ch in raw):
        return None
    return "@" + raw


def ensure_student_invite(uid, student_id, name):
    """Create or restore the personal Telegram invite for one individual student."""
    with db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_reminder_people'"
        ).fetchone()
        if not exists:
            return None
        row = conn.execute(
            """SELECT * FROM student_reminder_people
               WHERE teacher_id=? AND kind='individual' AND student_id=? LIMIT 1""",
            (int(uid), int(student_id)),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE student_reminder_people SET active=1,name=? WHERE id=?",
                (name.strip(), int(row["id"])),
            )
        else:
            conn.execute(
                """INSERT INTO student_reminder_people
                   (teacher_id,kind,student_id,name,invite_token,created_at)
                   VALUES(?,'individual',?,?,?,?)""",
                (
                    int(uid),
                    int(student_id),
                    name.strip(),
                    secrets.token_urlsafe(24),
                    datetime.utcnow().isoformat(),
                ),
            )
        conn.commit()
        return conn.execute(
            """SELECT * FROM student_reminder_people
               WHERE teacher_id=? AND kind='individual' AND student_id=? LIMIT 1""",
            (int(uid), int(student_id)),
        ).fetchone()


def student_invite_url(row):
    return f"https://t.me/{BOT_USERNAME}?start=join_{row['invite_token']}"


def student_invite_text(row):
    return (
        f"{row['name']}, присоединяйся к ПРЕПАДМИН, чтобы получать напоминания "
        "об уроках и пользоваться личным кабинетом. Открой ссылку и нажми «Запустить»."
    )


def student_share_url(row):
    return "https://t.me/share/url?" + urlencode({
        "url": student_invite_url(row),
        "text": student_invite_text(row),
    })


def student_direct_url(row, contact):
    username = str(contact or "").strip().lstrip("@")
    if not username:
        return student_share_url(row)
    return f"https://t.me/{username}?" + urlencode({
        "text": f"{student_invite_text(row)}\n\n{student_invite_url(row)}",
    })


def student_invite_markup(row, contact=""):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"📨 Отправить {row['name']}",
            url=student_direct_url(row, contact),
        )
    ]])


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


def _subject_keyboard():
    """Telegram's buttons are text; the matching SVG tiles appear in the WebApp."""
    symbols = {
        "russian": "📖", "mathematics": "📈", "physics": "⚛️",
        "chemistry": "🧪", "biology": "🧬", "geography": "🌍",
        "social-studies": "👥", "history": "🏛", "literature": "📚",
        "informatics": "💻", "english": "🇬🇧", "german": "🇩🇪",
        "french": "🇫🇷", "spanish": "🇪🇸", "chinese": "🇨🇳",
    }
    buttons = [
        InlineKeyboardButton(
            f"{symbols.get(item['id'], '📘')} {item['shortName']}",
            callback_data=f"tsub:{item['id']}",
        )
        for item in subject_catalog.SUBJECTS
    ]
    return InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def _format_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Индивидуально", callback_data="fmt:individual")],
        [InlineKeyboardButton("В группах", callback_data="fmt:groups")],
        [InlineKeyboardButton("И так, и так", callback_data="fmt:mixed")],
    ])


def _profile_values(row):
    """Only a teacher-entered valid name and subject count as a complete profile."""
    if row is None:
        return None, None
    return normalize_teacher_name(row["name"]), normalize_teacher_subject(row["subject"])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    row = teacher(uid)
    name, subject = _profile_values(row)
    if row and row["onboarding_completed_at"] and name and subject:
        await update.message.reply_text(
            f"С возвращением, {name} 💗\n\n"
            f"Предмет: {subject}. Это твой личный администратор преподавателя.",
            reply_markup=MAIN_KB,
        )
        return ConversationHandler.END

    upsert_teacher(uid)
    if row and row["onboarding_completed_at"] and name and not subject:
        await update.message.reply_text(
            f"{name}, давай дополним профиль 💗\n\n"
            "Выбери предмет из списка ниже:", reply_markup=_subject_keyboard()
        )
        return SUBJECT
    if row and row["onboarding_completed_at"] and not name:
        await update.message.reply_text(
            "Чтобы в кабинете отображалось твоё имя, напиши, как к тебе обращаться: "
            "например, «Маша» или «Мария Александровна».\n\n"
            "Имя ты указываешь самостоятельно — из Telegram его не берём."
        )
        return NAME

    await update.message.reply_text(
        "Привет! Я ПРЕПАДМИН 💗\n\n"
        "Твой личный администратор преподавателя в Telegram.\n\n"
        "Я помогу держать в порядке учеников и группы, расписание и переносы, "
        "домашние задания, оплаты и напоминания — чтобы тебе не приходилось "
        "держать всё в голове и переписках.\n\n"
        "Ты преподаёшь — ПРЕПАДМИН администрирует.\n\n"
        "Шаг 1 из 2: Как тебя зовут?\n"
        "Напиши имя, которое будет видно в твоём кабинете "
        "(например, «Маша» или «Мария Александровна»)."
    )
    return NAME


# Navigation labels must never become a teacher's name or subject.
# Teachers choose their own profile values; never infer a name from a button.
_PROFILE_NAVIGATION = frozenset({
    "мой кабинет", "кабинет", "препадмин", "преподмин", "преп | админ",
    "ученики", "ученики и группы", "задачи", "расписание",
    "домашние задания", "оплаты", "напоминания", "отчёты",
    "настройки", "быстрая задача", "быстрая настройка", "материалы",
    "разработчикам", "открыть препадмин", "мой профиль",
})


def normalize_teacher_name(value):
    """Return a teacher-entered human name, or None for menu buttons/invalid input."""
    name = " ".join(str(value or "").strip().split())
    if not 2 <= len(name) <= 80:
        return None
    if name.casefold() in _PROFILE_NAVIGATION or name.startswith("/"):
        return None
    if not any(c.isalpha() for c in name):
        return None
    if not all(c.isalpha() or c in " -'’." for c in name):
        return None
    return name


def normalize_teacher_subject(value):
    subject = " ".join(str(value or "").strip().split())
    if not 2 <= len(subject) <= 100 or subject.casefold() in _PROFILE_NAVIGATION:
        return None
    if subject.startswith("/") or not any(c.isalpha() for c in subject):
        return None
    # Exclude menu emoji/buttons; allow everyday subject labels (e.g. 'Химия, биология').
    if not all(c.isalpha() or c.isdigit() or c in " -'’.,/+()" for c in subject):
        return None
    return subject


async def onboarding_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = normalize_teacher_name(update.message.text)
    if name is None:
        await update.message.reply_text(
            "Введи, пожалуйста, своё имя текстом (например, «Маша» "
            "или «Мария Александровна»). Кнопки меню не подходят."
        )
        return NAME
    uid = update.effective_user.id
    upsert_teacher(uid, name=name)
    row = teacher(uid)
    _saved_name, existing_subject = _profile_values(row)
    if row["onboarding_completed_at"] and existing_subject:
        await update.message.reply_text(
            f"Готово, {name} 💗\nПредмет: {existing_subject}. "
            "Имя в кабинете обновлено, ученики и расписание сохранены.",
            reply_markup=MAIN_KB,
        )
        return ConversationHandler.END
    await update.message.reply_text(
        f"Отлично, {name}! 💗\n\nШаг 2 из 2: Какой предмет ты преподаёшь? "
        "Выбери предмет из списка ниже:", reply_markup=_subject_keyboard()
    )
    return SUBJECT


async def onboarding_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = normalize_teacher_subject(update.message.text)
    if subject is None:
        await update.message.reply_text(
            "Выбери предмет из списка ниже. Можно также написать его название текстом.",
            reply_markup=_subject_keyboard(),
        )
        return SUBJECT
    item = subject_catalog.subject_by_text(subject)
    if item is None:
        await update.message.reply_text("Выбери предмет из каталога:", reply_markup=_subject_keyboard())
        return SUBJECT
    subject = item["name"]
    uid = update.effective_user.id
    upsert_teacher(uid, subject=subject, subject_id=item["id"])
    row = teacher(uid)
    saved_name, _saved_subject = _profile_values(row)
    if row["onboarding_completed_at"] and saved_name:
        await update.message.reply_text(
            f"Готово, {saved_name} 💗\nПредмет: {subject}. "
            "Профиль обновлён, остальные данные кабинета сохранены.",
            reply_markup=MAIN_KB,
        )
        return ConversationHandler.END
    await update.message.reply_text("Как ты работаешь сейчас?", reply_markup=_format_keyboard())
    return FORMAT


async def onboarding_subject_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    item = subject_catalog.subject_by_id(q.data.removeprefix("tsub:"))
    if item is None:
        await q.answer("Выбери предмет из списка.", show_alert=True)
        return SUBJECT
    await q.answer()
    uid = q.from_user.id
    upsert_teacher(uid, subject=item["name"], subject_id=item["id"])
    row = teacher(uid)
    name, _subject = _profile_values(row)
    if row["onboarding_completed_at"] and name:
        await q.edit_message_text(
            f"Готово, {name} 💗\nПредмет: {item['name']}. "
            "Профиль обновлён, ученики и расписание сохранены."
        )
        return ConversationHandler.END
    await q.edit_message_text(
        f"Предмет: {item['name']} 💗\n\nКак ты работаешь сейчас?",
        reply_markup=_format_keyboard(),
    )
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
    row = teacher(q.from_user.id)
    name, subject = _profile_values(row)
    if not name or not subject:
        await q.edit_message_text(
            "Чтобы завершить регистрацию, сначала укажи своё имя и предмет. "
            "Напиши /start — вернёмся к анкете. Ничего не удалено."
        )
        return ConversationHandler.END
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
        "Напиши Telegram ученика: @username.\n\n"
        "Например: @alina_chem\n"
        "Если Telegram пока нет — отправь «-». Приглашение можно будет отправить позже."
    )
    return ADD_STUDENT_CONTACT


async def add_student_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = normalize_telegram_username(update.message.text)
    if contact is None:
        await update.message.reply_text(
            "Не похоже на Telegram @username. Напиши, например, @alina_chem "
            "или отправь «-», если Telegram пока нет."
        )
        return ADD_STUDENT_CONTACT

    name = context.user_data.pop("new_student_name", "Ученик")
    student_id = add_student(update.effective_user.id, name, contact)
    invite = ensure_student_invite(update.effective_user.id, student_id, name)
    count = len(list_students(update.effective_user.id))

    if invite:
        await update.message.reply_text(
            f"✅ {name} добавлен(а).\n"
            f"Telegram: {contact or 'пока не указан'}\n\n"
            "📨 Теперь сразу отправь персональное приглашение. "
            "Ученик откроет его, нажмёт «Запустить» — и Telegram привяжется к карточке автоматически.",
            reply_markup=student_invite_markup(invite, contact),
        )
        await update.message.reply_text(
            f"Сейчас в кабинете учеников: {count}. "
            "После подключения я сообщу тебе об этом здесь.",
            reply_markup=MAIN_KB,
        )
    else:
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
            SUBJECT: [
                CallbackQueryHandler(onboarding_subject_choice, pattern=r"^tsub:[a-z-]+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding_subject),
            ],
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
