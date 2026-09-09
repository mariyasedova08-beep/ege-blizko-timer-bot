from datetime import datetime, timedelta
import random
import re
import secrets
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import run_bot_live6

live6 = run_bot_live6
live5 = live6.live5
live4 = live6.live4
live3 = live6.live3
live2 = live6.live2
run_bot = live6.run_bot
bot = live6.bot


# Банк собран по карточке «Тривиальные названия веществ» ЕГЭ БЛИЗКО.
TRIVIAL_BANK = (
    {"id": "cryolite", "formula": "Na₃[AlF₆]", "names": ("криолит",)},
    {"id": "silica", "formula": "SiO₂", "names": ("кварц", "кремнезём")},
    {"id": "pyrite", "formula": "FeS₂", "names": ("пирит", "серный колчедан")},
    {"id": "calcium_carbide", "formula": "CaC₂", "names": ("карбид кальция",)},
    {"id": "aluminium_carbide", "formula": "Al₄C₃", "names": ("карбид алюминия",)},
    {"id": "carbon_dioxide", "formula": "CO₂", "names": ("углекислый газ",)},
    {"id": "hydrogen_peroxide", "formula": "H₂O₂", "names": ("перекись водорода",)},
    {"id": "copper_sulfate_penta", "formula": "CuSO₄·5H₂O", "names": ("медный купорос",)},
    {"id": "calcium_carbonate", "formula": "CaCO₃", "names": ("мел", "мрамор", "известняк")},
    {"id": "sulfur_dioxide", "formula": "SO₂", "names": ("сернистый газ",)},
    {"id": "sulfur_trioxide", "formula": "SO₃", "names": ("серный ангидрид",)},
    {"id": "carbon_monoxide", "formula": "CO", "names": ("угарный газ",)},
    {"id": "magnetite_scale", "formula": "Fe₃O₄", "names": ("железная окалина",)},
    {"id": "ammonia_water", "formula": "NH₃ (водный раствор)", "names": ("нашатырный спирт",)},
    {"id": "silicon_carbide", "formula": "SiC", "names": ("карборунд",)},
    {"id": "phosphine", "formula": "PH₃", "names": ("фосфин",)},
    {"id": "silane", "formula": "SiH₄", "names": ("силан",)},
    {"id": "ammonia", "formula": "NH₃", "names": ("аммиак",)},
    {"id": "baking_soda", "formula": "NaHCO₃", "names": ("пищевая сода", "питьевая сода", "пищевая (питьевая) сода")},
    {"id": "nitrous_oxide", "formula": "N₂O", "names": ("веселящий газ",)},
    {"id": "nitrogen_dioxide", "formula": "NO₂", "names": ("бурый газ",)},
    {"id": "ozone", "formula": "O₃", "names": ("озон",)},
    {"id": "dry_ice", "formula": "CO₂ (твёрдый)", "names": ("сухой лёд",)},
    {"id": "potassium_hydroxide", "formula": "KOH", "names": ("едкое кали",)},
    {"id": "sodium_hydroxide", "formula": "NaOH", "names": ("едкий натр",)},
    {"id": "methane", "formula": "CH₄", "names": ("метан",)},
    {"id": "potassium_nitrate", "formula": "KNO₃", "names": ("калиевая селитра",)},
    {"id": "sodium_nitrate", "formula": "NaNO₃", "names": ("натриевая селитра",)},
    {"id": "potassium_chlorate", "formula": "KClO₃", "names": ("бертолетова соль",)},
    {"id": "malachite", "formula": "(CuOH)₂CO₃", "names": ("малахит",)},
    {"id": "calcium_hydroxide", "formula": "Ca(OH)₂", "names": ("известковая вода", "гашеная известь")},
    {"id": "calcium_oxide", "formula": "CaO", "names": ("негашеная известь",)},
    {"id": "potash", "formula": "K₂CO₃", "names": ("поташ",)},
    {"id": "gypsum", "formula": "CaSO₄·2H₂O", "names": ("гипс",)},
    {"id": "corundum", "formula": "Al₂O₃", "names": ("корунд",)},
    {"id": "ammonium_nitrate", "formula": "NH₄NO₃", "names": ("аммиачная селитра",)},
    {"id": "ammonium_chloride", "formula": "NH₄Cl", "names": ("нашатырь",)},
)
TRIVIAL_BY_ID = {item["id"]: item for item in TRIVIAL_BANK}

STUDENT_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🧪 Тривиальные названия"],
        ["❌ Мои ошибки", "📊 Моя статистика"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def ensure_trivial_tables():
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trivial_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                telegram_username TEXT,
                telegram_name TEXT,
                mode TEXT NOT NULL,
                total INTEGER NOT NULL,
                correct INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trivial_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                correct INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trivial_errors (
                telegram_user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                error_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (telegram_user_id, item_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trivial_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                friday_time TEXT NOT NULL DEFAULT '16:00',
                last_friday_sent TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO trivial_settings (id, friday_time, updated_at) VALUES (1, '16:00', ?)",
            (now,),
        )
        conn.commit()


def normalize_answer(text):
    value = str(text or "").lower().strip().replace("ё", "е")
    value = re.sub(r"[.,;:!?()\[\]{}\-—–]+", " ", value)
    return " ".join(value.split())


def accepted_names(item):
    return {normalize_answer(name) for name in item["names"]}


def unresolved_error_ids(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT item_id, error_count - correct_count AS debt
            FROM trivial_errors
            WHERE telegram_user_id = ? AND error_count > correct_count
            ORDER BY debt DESC, updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [item_id for item_id, _ in rows if item_id in TRIVIAL_BY_ID]


def create_session(user, mode, questions):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO trivial_sessions (
                telegram_user_id, telegram_username, telegram_name,
                mode, total, correct, started_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (user.id, user.username or "", user.full_name or "", mode, len(questions), now),
        )
        conn.commit()
        return cursor.lastrowid


def record_attempt(user_id, item_id, direction, is_correct):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO trivial_attempts (telegram_user_id, item_id, direction, correct, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, item_id, direction, 1 if is_correct else 0, now),
        )
        conn.execute(
            """
            INSERT INTO trivial_errors (
                telegram_user_id, item_id, error_count, correct_count, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id, item_id) DO UPDATE SET
                error_count = error_count + excluded.error_count,
                correct_count = correct_count + excluded.correct_count,
                updated_at = excluded.updated_at
            """,
            (user_id, item_id, 0 if is_correct else 1, 1 if is_correct else 0, now),
        )
        conn.commit()


def finish_session(session_id, correct_count):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "UPDATE trivial_sessions SET correct = ?, finished_at = ? WHERE id = ?",
            (correct_count, now, session_id),
        )
        conn.commit()


def make_questions(mode, user_id):
    if mode == "mistakes":
        error_ids = unresolved_error_ids(user_id)
        if not error_ids:
            return []
        source = [TRIVIAL_BY_ID[item_id] for item_id in error_ids]
        questions = []
        while len(questions) < 10:
            item = random.choice(source)
            questions.append({"item_id": item["id"], "direction": random.choice(("formula_name", "name_formula"))})
        return questions

    items = random.sample(list(TRIVIAL_BANK), k=min(10, len(TRIVIAL_BANK)))
    questions = []
    for item in items:
        if mode == "formula_name":
            direction = "formula_name"
        elif mode == "name_formula":
            direction = "name_formula"
        elif mode == "manual":
            direction = "manual"
        else:
            direction = random.choice(("formula_name", "name_formula"))
        questions.append({"item_id": item["id"], "direction": direction})
    return questions


def mode_title(mode):
    return {
        "formula_name": "Формула → название",
        "name_formula": "Название → формула",
        "mixed": "Смешанный режим",
        "manual": "Ввод ответа вручную",
        "mistakes": "Мои ошибки",
    }.get(mode, "Тривиальные названия")


def start_session_context(context, user, mode):
    questions = make_questions(mode, user.id)
    if not questions:
        return False
    session_id = create_session(user, mode, questions)
    context.user_data["trivial_session"] = {
        "token": secrets.token_hex(2),
        "session_id": session_id,
        "mode": mode,
        "questions": questions,
        "index": 0,
        "correct": 0,
        "wrong": [],
        "current_choices": None,
        "correct_choice": None,
        "awaiting_manual": False,
    }
    return True


def question_prompt(question):
    item = TRIVIAL_BY_ID[question["item_id"]]
    direction = question["direction"]
    if direction in ("formula_name", "manual"):
        return f"Как называется вещество?\n\n🧪 {item['formula']}"
    shown_name = random.choice(item["names"])
    return f"Какая формула соответствует названию?\n\n🧪 {shown_name}"


def choice_values(question):
    item = TRIVIAL_BY_ID[question["item_id"]]
    direction = question["direction"]
    if direction == "formula_name":
        correct = random.choice(item["names"])
        pool = []
        for other in TRIVIAL_BANK:
            if other["id"] != item["id"]:
                pool.append(random.choice(other["names"]))
    else:
        correct = item["formula"]
        pool = [other["formula"] for other in TRIVIAL_BANK if other["id"] != item["id"]]
    pool = list(dict.fromkeys(pool))
    distractors = random.sample(pool, k=3)
    choices = distractors + [correct]
    random.shuffle(choices)
    return choices, choices.index(correct)


async def show_trivial_menu(update, context, edit=False):
    user = update.effective_user
    error_count = len(unresolved_error_ids(user.id)) if user else 0
    extra = f"\n\n❌ Сейчас для повторения: {error_count}" if error_count else "\n\nНачни с 10 вопросов — это займёт примерно 3–5 минут 💗"
    text = "🧪 Тривиальные названия веществ\n\nВыбери режим:" + extra
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Формула → название", callback_data="triv:start:formula_name")],
        [InlineKeyboardButton("Название → формула", callback_data="triv:start:name_formula")],
        [InlineKeyboardButton("🎲 Смешанный", callback_data="triv:start:mixed")],
        [InlineKeyboardButton("⌨️ Ввод вручную", callback_data="triv:start:manual")],
        [InlineKeyboardButton("❌ Мои ошибки", callback_data="triv:start:mistakes")],
        [InlineKeyboardButton("📊 Статистика", callback_data="triv:stats"), InlineKeyboardButton("🏆 Рейтинг", callback_data="triv:top")],
    ])
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def send_current_question(update, context, edit=False):
    session = context.user_data.get("trivial_session")
    if not session:
        await show_trivial_menu(update, context, edit=edit)
        return

    if session["index"] >= len(session["questions"]):
        await finish_trivial_session(update, context, edit=edit)
        return

    question = session["questions"][session["index"]]
    number = session["index"] + 1
    total = len(session["questions"])
    prompt = f"{mode_title(session['mode'])}\n\nВопрос {number}/{total}\n\n{question_prompt(question)}"

    if question["direction"] == "manual":
        session["awaiting_manual"] = True
        context.user_data["trivial_session"] = session
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(prompt + "\n\nНапиши ответ сообщением 👇")
        else:
            await update.effective_message.reply_text(prompt + "\n\nНапиши ответ сообщением 👇")
        return

    choices, correct_choice = choice_values(question)
    session["current_choices"] = choices
    session["correct_choice"] = correct_choice
    session["awaiting_manual"] = False
    context.user_data["trivial_session"] = session
    rows = [[InlineKeyboardButton(value, callback_data=f"triv:a:{session['token']}:{i}")] for i, value in enumerate(choices)]
    rows.append([InlineKeyboardButton("← В меню", callback_data="triv:menu")])
    keyboard = InlineKeyboardMarkup(rows)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(prompt, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(prompt, reply_markup=keyboard)


async def finish_trivial_session(update, context, edit=False):
    session = context.user_data.get("trivial_session")
    if not session:
        return
    total = len(session["questions"])
    correct = session["correct"]
    finish_session(session["session_id"], correct)
    percent = round(correct * 100 / total) if total else 0
    wrong_ids = list(dict.fromkeys(session["wrong"]))
    lines = [
        "💗 Готово!",
        "",
        f"Результат: {correct}/{total} — {percent}%",
    ]
    if not wrong_ids:
        lines.extend(["", "🔥 10/10! Тривиальные названия сегодня побеждены."])
    else:
        lines.extend(["", "Повтори:"])
        for item_id in wrong_ids[:6]:
            item = TRIVIAL_BY_ID[item_id]
            lines.append(f"• {item['formula']} — {', '.join(item['names'])}")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Повторить ошибки", callback_data="triv:start:mistakes")],
        [InlineKeyboardButton("🎲 Ещё 10 вопросов", callback_data="triv:start:mixed")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="triv:stats")],
    ])
    context.user_data.pop("trivial_session", None)
    text = "\n".join(lines)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


def student_stats_text(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM trivial_sessions
            WHERE telegram_user_id = ? AND finished_at IS NOT NULL
            """,
            (user_id,),
        ).fetchone()
        dates = [r[0] for r in conn.execute(
            """
            SELECT DISTINCT substr(finished_at, 1, 10)
            FROM trivial_sessions
            WHERE telegram_user_id = ? AND finished_at IS NOT NULL
            ORDER BY 1 DESC
            """,
            (user_id,),
        ).fetchall()]
    sessions, total, correct = row
    percent = round(correct * 100 / total) if total else 0
    errors = len(unresolved_error_ids(user_id))

    streak = 0
    if dates:
        parsed = [datetime.strptime(value, "%Y-%m-%d").date() for value in dates]
        cursor = parsed[0]
        streak = 1
        for value in parsed[1:]:
            if cursor - value == timedelta(days=1):
                streak += 1
                cursor = value
            else:
                break

    return (
        "📊 Моя статистика\n\n"
        f"Пройдено тренировок: {sessions}\n"
        f"Ответов: {correct}/{total}\n"
        f"Точность: {percent}%\n"
        f"❌ Осталось ошибок для повторения: {errors}\n"
        f"🔥 Серия дней: {streak}"
    )


def top_text():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT telegram_name, telegram_username,
                   SUM(total) AS total_q, SUM(correct) AS correct_q
            FROM trivial_sessions
            WHERE finished_at IS NOT NULL
            GROUP BY telegram_user_id, telegram_name, telegram_username
            HAVING SUM(total) >= 10
            ORDER BY (1.0 * SUM(correct) / SUM(total)) DESC, SUM(total) DESC
            LIMIT 10
            """
        ).fetchall()
    if not rows:
        return "🏆 Рейтинг пока пуст. Стань первым 💗"
    lines = ["🏆 Топ по тривиальным названиям", ""]
    medals = ["🥇", "🥈", "🥉"]
    for index, (name, username, total, correct) in enumerate(rows, start=1):
        label = name or (f"@{username}" if username else "Ученик")
        percent = round(correct * 100 / total) if total else 0
        prefix = medals[index - 1] if index <= 3 else f"{index}."
        lines.append(f"{prefix} {label} — {percent}% ({correct}/{total})")
    return "\n".join(lines)


async def trivial_command(update, context):
    if update.effective_chat.type != "private":
        me = await context.bot.get_me()
        await update.message.reply_text(
            "Тренажёр открывается в личном чате с ботом 💗",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🧪 Открыть тренажёр", url=f"https://t.me/{me.username}?start=trivial")]]),
        )
        return
    await show_trivial_menu(update, context)


async def trivial_stats_command(update, context):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(student_stats_text(update.effective_user.id))


async def trivial_top_command(update, context):
    if update.effective_chat.type != "private":
        return
    await update.message.reply_text(top_text())


async def trivial_callback(update, context):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data

    if data == "triv:menu":
        context.user_data.pop("trivial_session", None)
        await show_trivial_menu(update, context, edit=True)
        return
    if data == "triv:stats":
        await query.edit_message_text(
            student_stats_text(update.effective_user.id),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← В меню", callback_data="triv:menu")]]),
        )
        return
    if data == "triv:top":
        await query.edit_message_text(
            top_text(),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← В меню", callback_data="triv:menu")]]),
        )
        return
    if data.startswith("triv:start:"):
        mode = data.split(":", 2)[2]
        if mode not in {"formula_name", "name_formula", "mixed", "manual", "mistakes"}:
            return
        if not start_session_context(context, update.effective_user, mode):
            await query.edit_message_text(
                "❌ Ошибок для повторения пока нет. Отличная работа 💗",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎲 Смешанный режим", callback_data="triv:start:mixed"), InlineKeyboardButton("← В меню", callback_data="triv:menu")]]),
            )
            return
        await send_current_question(update, context, edit=True)
        return
    if data.startswith("triv:a:"):
        parts = data.split(":")
        if len(parts) != 4:
            return
        _, _, token, choice_text = parts
        session = context.user_data.get("trivial_session")
        if not session or session.get("token") != token:
            await query.edit_message_text("Эта тренировка уже закончилась. Открой новую: /trivial")
            return
        try:
            choice_index = int(choice_text)
        except ValueError:
            return
        choices = session.get("current_choices") or []
        correct_choice = session.get("correct_choice")
        if choice_index < 0 or choice_index >= len(choices) or correct_choice is None:
            return
        question = session["questions"][session["index"]]
        item = TRIVIAL_BY_ID[question["item_id"]]
        is_correct = choice_index == correct_choice
        record_attempt(update.effective_user.id, item["id"], question["direction"], is_correct)
        if is_correct:
            session["correct"] += 1
            result = "✅ Верно!"
        else:
            session["wrong"].append(item["id"])
            if question["direction"] == "formula_name":
                answer = ", ".join(item["names"])
            else:
                answer = item["formula"]
            result = f"❌ Не совсем.\n\nПравильный ответ: {answer}"
        session["index"] += 1
        context.user_data["trivial_session"] = session
        await query.edit_message_text(
            result,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Дальше ➡️", callback_data=f"triv:next:{session['token']}")]]),
        )
        return
    if data.startswith("triv:next:"):
        token = data.split(":", 2)[2]
        session = context.user_data.get("trivial_session")
        if not session or session.get("token") != token:
            await show_trivial_menu(update, context, edit=True)
            return
        await send_current_question(update, context, edit=True)


async def handle_manual_answer(update, context):
    session = context.user_data.get("trivial_session")
    if not session or not session.get("awaiting_manual"):
        return False
    if session["index"] >= len(session["questions"]):
        return False
    question = session["questions"][session["index"]]
    if question["direction"] != "manual":
        return False
    item = TRIVIAL_BY_ID[question["item_id"]]
    answer = normalize_answer(update.message.text)
    is_correct = answer in accepted_names(item)
    record_attempt(update.effective_user.id, item["id"], "manual", is_correct)
    if is_correct:
        session["correct"] += 1
        await update.message.reply_text("✅ Верно!")
    else:
        session["wrong"].append(item["id"])
        await update.message.reply_text(f"❌ Правильный ответ: {', '.join(item['names'])}")
    session["index"] += 1
    session["awaiting_manual"] = False
    context.user_data["trivial_session"] = session
    await send_current_question(update, context)
    return True


async def student_text_router(update, context):
    if not update.message or not update.message.text:
        return
    if update.effective_chat.type == "private" and await handle_manual_answer(update, context):
        return
    text = update.message.text.strip()
    if update.effective_chat.type == "private" and text == "🧪 Тривиальные названия":
        await show_trivial_menu(update, context)
        return
    if update.effective_chat.type == "private" and text == "❌ Мои ошибки":
        if start_session_context(context, update.effective_user, "mistakes"):
            await send_current_question(update, context)
        else:
            await update.message.reply_text("❌ Ошибок для повторения пока нет. Отличная работа 💗")
        return
    if update.effective_chat.type == "private" and text == "📊 Моя статистика":
        await update.message.reply_text(student_stats_text(update.effective_user.id))
        return
    await live6.combined_private_text_handler(update, context)


async def start_router(update, context):
    if update.effective_chat.type == "private" and context.args and context.args[0].lower() == "trivial":
        await update.message.reply_text("🧪 Тренажёр ЕГЭ БЛИЗКО открыт 💗", reply_markup=STUDENT_KEYBOARD)
        await show_trivial_menu(update, context)
        return
    tutor_id = live6.get_tutor_id()
    if update.effective_chat.type == "private" and not bot.user_is_admin(update) and update.effective_user.id != tutor_id:
        await update.message.reply_text(
            "Привет 💗 Здесь можно тренировать тривиальные названия веществ.",
            reply_markup=STUDENT_KEYBOARD,
        )
        await show_trivial_menu(update, context)
        return
    await bot.start(update, context)


async def send_trivial_announcement(context):
    chat_id = bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False
    me = await context.bot.get_me()
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🧪 Начать тренажёр", url=f"https://t.me/{me.username}?start=trivial")]])
    await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=bot.get_target_thread_id(),
        text=(
            "🧪 <b>Мини-челлендж: тривиальные названия</b>\n\n"
            "10 вопросов займут примерно 3–5 минут.\n"
            "Попробуйте сегодня набрать <b>10/10</b> 💗\n\n"
            "Кто уже проходил — обязательно загляните в режим «Мои ошибки»."
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    return True


async def trivial_announce_command(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    ok = await send_trivial_announcement(context)
    await update.message.reply_text("✅ Анонс отправлен в группу." if ok else "CHAT_ID не настроен.")


def get_friday_settings():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute("SELECT friday_time, last_friday_sent FROM trivial_settings WHERE id = 1").fetchone()
    return row or ("16:00", None)


async def set_trivial_time(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    if not context.args or not re.fullmatch(r"\d{1,2}:\d{2}", context.args[0]):
        await update.message.reply_text("Например: /trivialtime 16:00")
        return
    try:
        parsed = datetime.strptime(context.args[0], "%H:%M")
    except ValueError:
        await update.message.reply_text("Не получилось прочитать время. Например: /trivialtime 16:00")
        return
    time_text = parsed.strftime("%H:%M")
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("UPDATE trivial_settings SET friday_time = ?, updated_at = ? WHERE id = 1", (time_text, now))
        conn.commit()
    await update.message.reply_text(f"✅ Пятничное напоминание будет приходить в {time_text} по Москве.")


async def friday_trivial_tick(context):
    now = datetime.now(bot.TIMEZONE)
    if now.weekday() != 4:  # пятница по datetime
        return
    friday_time, last_sent = get_friday_settings()
    if now.strftime("%H:%M") != friday_time:
        return
    key = now.date().isoformat()
    if last_sent == key:
        return
    if await send_trivial_announcement(context):
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                "UPDATE trivial_settings SET last_friday_sent = ?, updated_at = ? WHERE id = 1",
                (key, datetime.now(bot.TIMEZONE).isoformat()),
            )
            conn.commit()


async def trivial_friday_status(update, context):
    if not bot.user_is_admin(update) or update.effective_chat.type != "private":
        return
    friday_time, _ = get_friday_settings()
    await update.message.reply_text(f"🧪 Тривиальные названия: напоминание каждую пятницу в {friday_time} по Москве.")


def main():
    token = bot.os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная BOT_TOKEN не установлена")

    bot.start_http_server()
    run_bot.ensure_probnik_assets_table()
    live3.ensure_attendance_tables()
    live4.ensure_display_name_column()
    live6.ensure_tutor_tables()
    ensure_trivial_tables()
    application = bot.Application.builder().token(token).build()

    application.add_handler(bot.CommandHandler("start", start_router))
    application.add_handler(bot.CommandHandler("ege", bot.ege))
    application.add_handler(bot.CommandHandler("weeks", bot.weeks))
    application.add_handler(bot.CommandHandler("progress", bot.progress))
    application.add_handler(bot.CommandHandler("chatid", bot.chatid))
    application.add_handler(bot.CommandHandler("threadid", bot.threadid))
    application.add_handler(bot.CommandHandler("myid", bot.myid))
    application.add_handler(bot.CommandHandler("link", bot.link))
    application.add_handler(bot.CommandHandler("corestatus", bot.corestatus))
    application.add_handler(bot.CommandHandler("homeworkstatus", bot.homeworkstatus))
    application.add_handler(bot.CommandHandler("attendance", live3.show_attendance))
    application.add_handler(bot.CommandHandler("attendancestats", live4.attendance_stats))
    application.add_handler(bot.CommandHandler("rename", live6.rename_command_wrapper))

    application.add_handler(bot.CommandHandler("tutorinvite", live6.tutor_invite))
    application.add_handler(bot.CommandHandler("tutorlink", live6.tutor_link))
    application.add_handler(bot.CommandHandler("tutorstatus", live6.tutor_status))
    application.add_handler(bot.CommandHandler("tutorreminder", live6.tutor_reminder_command))
    application.add_handler(bot.CommandHandler("tutorreminders", live6.tutor_reminders_list))
    application.add_handler(bot.CommandHandler("tutordel", live6.tutor_delete))
    application.add_handler(bot.CommandHandler("tutortest", live6.tutor_test))
    application.add_handler(bot.CommandHandler("tutorcancel", live6.tutor_cancel))

    application.add_handler(bot.CommandHandler("trivial", trivial_command))
    application.add_handler(bot.CommandHandler("trivial10", trivial_command))
    application.add_handler(bot.CommandHandler("trivialmistakes", trivial_command))
    application.add_handler(bot.CommandHandler("trivialstats", trivial_stats_command))
    application.add_handler(bot.CommandHandler("trivialtop", trivial_top_command))
    application.add_handler(bot.CommandHandler("trivialannounce", trivial_announce_command))
    application.add_handler(bot.CommandHandler("trivialtime", set_trivial_time))
    application.add_handler(bot.CommandHandler("trivialfriday", trivial_friday_status))

    application.add_handler(bot.CommandHandler("test", bot.test))
    application.add_handler(bot.CommandHandler("testlesson", run_bot.test_lesson_reminder))
    application.add_handler(bot.CommandHandler("setprobnikcard", run_bot.set_probnik_card))
    application.add_handler(bot.CommandHandler("setprobnikblank", run_bot.set_probnik_blank))
    application.add_handler(bot.CommandHandler("setprobnikzoom", live2.set_probnik_zoom))
    application.add_handler(bot.CommandHandler("testprobnikthu", run_bot.test_probnik_thursday))
    application.add_handler(bot.CommandHandler("testprobnikfri", run_bot.test_probnik_friday))
    application.add_handler(bot.CommandHandler("testprobniksat", live2.test_probnik_saturday))

    application.add_handler(CallbackQueryHandler(trivial_callback, pattern=r"^triv:"))
    application.add_handler(CallbackQueryHandler(live3.attendance_callback, pattern=r"^att:"))
    application.add_handler(CallbackQueryHandler(live4.rename_callback, pattern=r"^ren:"))

    application.add_handler(
        bot.MessageHandler(
            bot.filters.PHOTO | bot.filters.Document.IMAGE | bot.filters.Document.PDF,
            run_bot.save_probnik_asset_from_message,
        )
    )
    application.add_handler(bot.MessageHandler(bot.filters.Document.ALL, bot.import_students_document))
    application.add_handler(bot.MessageHandler(bot.filters.TEXT & ~bot.filters.COMMAND, student_text_router))

    application.job_queue.run_daily(
        bot.daily_countdown,
        time=datetime.strptime("09:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )
    application.job_queue.run_daily(
        bot.daily_homework_reminder,
        time=datetime.strptime("19:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 2, 6),
    )
    application.job_queue.run_daily(
        run_bot.send_lesson_reminder,
        time=datetime.strptime("18:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(1, 3),
    )
    application.job_queue.run_daily(
        run_bot.send_lesson_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(0, 6),
    )
    application.job_queue.run_daily(
        run_bot.probnik_daily_reminder,
        time=datetime.strptime("10:00", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
    )
    application.job_queue.run_daily(
        live2.probnik_saturday_reminder,
        time=datetime.strptime("09:30", "%H:%M").time().replace(tzinfo=bot.TIMEZONE),
        days=(6,),
    )
    application.job_queue.run_repeating(live6.tutor_reminder_tick, interval=30, first=10)
    application.job_queue.run_repeating(friday_trivial_tick, interval=30, first=15)

    print("Бот запущен")
    application.run_polling()


if __name__ == "__main__":
    main()
