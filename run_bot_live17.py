import random
import re
import secrets
import sqlite3
from datetime import datetime

import run_bot_live16

live16 = run_bot_live16
live15 = live16.live15
live7 = live16.live7
bot = live16.bot

# Таблица пользователя «КИСЛОТЫ И КИСЛОТНЫЕ ОСТАТКИ».
# Заряды кислотных остатков намеренно не используются в этом тренажёре.
ACID_BANK = (
    {"id": "hf", "acid_names": ("плавиковая", "фтороводородная"), "acid_formula": "HF", "residue_names": ("фторид",), "residue_formula": "F"},
    {"id": "hcl", "acid_names": ("соляная", "хлороводородная"), "acid_formula": "HCl", "residue_names": ("хлорид",), "residue_formula": "Cl", "focus": True},
    {"id": "hbr", "acid_names": ("бромоводородная",), "acid_formula": "HBr", "residue_names": ("бромид",), "residue_formula": "Br"},
    {"id": "hi", "acid_names": ("йодоводородная",), "acid_formula": "HI", "residue_names": ("йодид",), "residue_formula": "I"},
    {"id": "h2s", "acid_names": ("сероводородная",), "acid_formula": "H₂S", "residue_names": ("сульфид",), "residue_formula": "S"},
    {"id": "h2so3", "acid_names": ("сернистая",), "acid_formula": "H₂SO₃", "residue_names": ("сульфит",), "residue_formula": "SO₃"},
    {"id": "h2so4", "acid_names": ("серная",), "acid_formula": "H₂SO₄", "residue_names": ("сульфат",), "residue_formula": "SO₄"},
    {"id": "hno3", "acid_names": ("азотная",), "acid_formula": "HNO₃", "residue_names": ("нитрат",), "residue_formula": "NO₃"},
    {"id": "hno2", "acid_names": ("азотистая",), "acid_formula": "HNO₂", "residue_names": ("нитрит",), "residue_formula": "NO₂"},
    {"id": "h3po4", "acid_names": ("фосфорная",), "acid_formula": "H₃PO₄", "residue_names": ("фосфат",), "residue_formula": "PO₄", "focus": True},
    {"id": "h2co3", "acid_names": ("угольная",), "acid_formula": "H₂CO₃", "residue_names": ("карбонат",), "residue_formula": "CO₃"},
    {"id": "ch3cooh", "acid_names": ("уксусная",), "acid_formula": "CH₃COOH", "residue_names": ("ацетат",), "residue_formula": "CH₃COO"},
    {"id": "h2sio3", "acid_names": ("кремниевая",), "acid_formula": "H₂SiO₃", "residue_names": ("силикат",), "residue_formula": "SiO₃"},
    {"id": "hclo4", "acid_names": ("хлорная",), "acid_formula": "HClO₄", "residue_names": ("перхлорат",), "residue_formula": "ClO₄", "focus": True},
    {"id": "hclo3", "acid_names": ("хлорноватая",), "acid_formula": "HClO₃", "residue_names": ("хлорат",), "residue_formula": "ClO₃", "focus": True},
    {"id": "hclo2", "acid_names": ("хлористая",), "acid_formula": "HClO₂", "residue_names": ("хлорит",), "residue_formula": "ClO₂", "focus": True},
    {"id": "hclo", "acid_names": ("хлорноватистая",), "acid_formula": "HClO", "residue_names": ("гипохлорит",), "residue_formula": "ClO", "focus": True},
    {"id": "hmno4", "acid_names": ("марганцовая",), "acid_formula": "HMnO₄", "residue_names": ("перманганат",), "residue_formula": "MnO₄"},
    {"id": "h2mno4", "acid_names": ("марганцовистая",), "acid_formula": "H₂MnO₄", "residue_names": ("манганат",), "residue_formula": "MnO₄"},
    {"id": "h2cro4", "acid_names": ("хромовая",), "acid_formula": "H₂CrO₄", "residue_names": ("хромат",), "residue_formula": "CrO₄"},
    {"id": "h2cr2o7", "acid_names": ("дихромовая",), "acid_formula": "H₂Cr₂O₇", "residue_names": ("дихромат",), "residue_formula": "Cr₂O₇"},
    {"id": "hcooh", "acid_names": ("муравьиная",), "acid_formula": "HCOOH", "residue_names": ("формиат",), "residue_formula": "HCOO"},
    {"id": "h3po3", "acid_names": ("фосфористая",), "acid_formula": "H₃PO₃", "residue_names": ("фосфит",), "residue_formula": "HPO₃", "focus": True},
    {"id": "h3po2", "acid_names": ("фосфорноватистая",), "acid_formula": "H₃PO₂", "residue_names": ("гипофосфит",), "residue_formula": "H₂PO₂", "focus": True},
)
ACID_BY_ID = {item["id"]: item for item in ACID_BANK}
FOCUS_IDS = {item["id"] for item in ACID_BANK if item.get("focus")}

DIRECTIONS = (
    "acid_name_formula",
    "acid_formula_name",
    "residue_name_formula",
    "residue_formula_name",
)

# Без зарядов MnO4 соответствует и перманганату, и манганату.
# Поэтому вопрос «MnO4 → название» не задаём: без заряда он неоднозначен.
_residue_formula_counts = {}
for _item in ACID_BANK:
    _residue_formula_counts[_item["residue_formula"]] = _residue_formula_counts.get(_item["residue_formula"], 0) + 1
AMBIGUOUS_RESIDUE_FORMULAS = {formula for formula, count in _residue_formula_counts.items() if count > 1}


def ensure_acid_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS acid_sessions (
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
            CREATE TABLE IF NOT EXISTS acid_attempts (
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
            CREATE TABLE IF NOT EXISTS acid_errors (
                telegram_user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                error_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (telegram_user_id, item_id, direction)
            )
            """
        )
        conn.commit()


def _norm_text(value):
    value = str(value or "").lower().strip().replace("ё", "е")
    value = re.sub(r"[.,;:!?()\[\]{}\-—–]+", " ", value)
    return " ".join(value.split())


def _norm_formula(value):
    value = str(value or "").strip()
    trans = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
    value = value.translate(trans)
    value = re.sub(r"[\s\^+−–—-]", "", value)
    return value.lower()


def _answer_text(item, direction):
    if direction == "acid_name_formula":
        return item["acid_formula"]
    if direction == "acid_formula_name":
        return " / ".join(item["acid_names"])
    if direction == "residue_name_formula":
        return item["residue_formula"]
    return " / ".join(item["residue_names"])


def _question_text(item, direction):
    if direction == "acid_name_formula":
        return f"Какая формула у кислоты?\n\n🧪 {' / '.join(item['acid_names'])}"
    if direction == "acid_formula_name":
        return f"Как называется кислота?\n\n🧪 {item['acid_formula']}"
    if direction == "residue_name_formula":
        return f"Какая формула кислотного остатка?\n\n🧪 {' / '.join(item['residue_names'])}"
    return f"Как называется кислотный остаток?\n\n🧪 {item['residue_formula']}"


def _manual_is_correct(text, item, direction):
    if direction == "acid_name_formula":
        return _norm_formula(text) == _norm_formula(item["acid_formula"])
    if direction == "acid_formula_name":
        return _norm_text(text) in {_norm_text(x) for x in item["acid_names"]}
    if direction == "residue_name_formula":
        return _norm_formula(text) == _norm_formula(item["residue_formula"])
    return _norm_text(text) in {_norm_text(x) for x in item["residue_names"]}


def _valid_pair(item, direction):
    if direction == "residue_formula_name" and item["residue_formula"] in AMBIGUOUS_RESIDUE_FORMULAS:
        return False
    return True


def _question_pool(direction=None, focus_only=False):
    pairs = []
    for item in ACID_BANK:
        if focus_only and item["id"] not in FOCUS_IDS:
            continue
        dirs = (direction,) if direction else DIRECTIONS
        for d in dirs:
            if _valid_pair(item, d):
                pairs.append({"item_id": item["id"], "direction": d})
    return pairs


def _sample_balanced(direction=None, focus_only=False, total=10):
    if focus_only:
        pool = _question_pool(direction=direction, focus_only=True)
        return random.sample(pool, k=min(total, len(pool)))

    focus = _question_pool(direction=direction, focus_only=True)
    other = [q for q in _question_pool(direction=direction) if q["item_id"] not in FOCUS_IDS]
    # Особый акцент: минимум 6 из 10 вопросов — хлор и фосфор.
    focus_n = min(6, total, len(focus))
    other_n = min(total - focus_n, len(other))
    chosen = random.sample(focus, k=focus_n) + random.sample(other, k=other_n)
    remaining = total - len(chosen)
    if remaining:
        used = {(q["item_id"], q["direction"]) for q in chosen}
        rest = [q for q in _question_pool(direction=direction) if (q["item_id"], q["direction"]) not in used]
        chosen.extend(random.sample(rest, k=min(remaining, len(rest))))
    random.shuffle(chosen)
    return chosen


def _unresolved_errors(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT item_id, direction, error_count - correct_count AS debt
            FROM acid_errors
            WHERE telegram_user_id = ? AND error_count > correct_count
            ORDER BY debt DESC, updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [(item_id, direction) for item_id, direction, _ in rows if item_id in ACID_BY_ID]


def _make_questions(mode, user_id):
    mode_direction = {
        "acid_nf": "acid_name_formula",
        "acid_fn": "acid_formula_name",
        "residue_nf": "residue_name_formula",
        "residue_fn": "residue_formula_name",
    }
    if mode == "errors":
        errors = _unresolved_errors(user_id)
        if not errors:
            return []
        questions = []
        while len(questions) < 10:
            item_id, direction = random.choice(errors)
            if _valid_pair(ACID_BY_ID[item_id], direction):
                questions.append({"item_id": item_id, "direction": direction})
        return questions
    if mode == "focus":
        return _sample_balanced(focus_only=True, total=10)
    if mode == "manual":
        return _sample_balanced(total=10)
    return _sample_balanced(direction=mode_direction.get(mode), total=10)


def _create_session(user, mode, questions):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO acid_sessions (
                telegram_user_id, telegram_username, telegram_name,
                mode, total, correct, started_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (user.id, user.username or "", user.full_name or "", mode, len(questions), now),
        )
        conn.commit()
        return cur.lastrowid


def _record_attempt(user_id, item_id, direction, is_correct):
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT INTO acid_attempts (telegram_user_id, item_id, direction, correct, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, item_id, direction, 1 if is_correct else 0, now),
        )
        conn.execute(
            """
            INSERT INTO acid_errors (
                telegram_user_id, item_id, direction, error_count, correct_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id, item_id, direction) DO UPDATE SET
                error_count = error_count + excluded.error_count,
                correct_count = correct_count + excluded.correct_count,
                updated_at = excluded.updated_at
            """,
            (user_id, item_id, direction, 0 if is_correct else 1, 1 if is_correct else 0, now),
        )
        conn.commit()


def _finish_session(session_id, correct_count):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "UPDATE acid_sessions SET correct = ?, finished_at = ? WHERE id = ?",
            (correct_count, datetime.now(bot.TIMEZONE).isoformat(), session_id),
        )
        conn.commit()


def _start_acid_session(context, user, mode):
    questions = _make_questions(mode, user.id)
    if not questions:
        return False
    context.user_data.pop("trivial_session", None)
    context.user_data["acid_session"] = {
        "token": secrets.token_hex(2),
        "session_id": _create_session(user, mode, questions),
        "mode": mode,
        "questions": questions,
        "index": 0,
        "correct": 0,
        "wrong": [],
        "choices": None,
        "correct_choice": None,
        "awaiting_manual": False,
    }
    return True


def _choice_values(question):
    item = ACID_BY_ID[question["item_id"]]
    direction = question["direction"]
    correct = _answer_text(item, direction)
    pool = []
    for other in ACID_BANK:
        if other["id"] == item["id"]:
            continue
        if direction == "acid_name_formula":
            candidate = other["acid_formula"]
        elif direction == "acid_formula_name":
            candidate = " / ".join(other["acid_names"])
        elif direction == "residue_name_formula":
            candidate = other["residue_formula"]
        else:
            if other["residue_formula"] in AMBIGUOUS_RESIDUE_FORMULAS:
                continue
            candidate = " / ".join(other["residue_names"])
        if candidate != correct and candidate not in pool:
            pool.append(candidate)
    distractors = random.sample(pool, k=min(3, len(pool)))
    choices = distractors + [correct]
    random.shuffle(choices)
    return choices, choices.index(correct)


def _acid_menu_markup():
    B = live7.InlineKeyboardButton
    return live7.InlineKeyboardMarkup([
        [B("Кислота: название → формула", callback_data="triv:acid:start:acid_nf")],
        [B("Кислота: формула → название", callback_data="triv:acid:start:acid_fn")],
        [B("Остаток: название → формула", callback_data="triv:acid:start:residue_nf")],
        [B("Остаток: формула → название", callback_data="triv:acid:start:residue_fn")],
        [B("🎲 Смешанная тренировка", callback_data="triv:acid:start:mixed")],
        [B("🔥 Хлор + фосфор", callback_data="triv:acid:start:focus")],
        [B("⌨️ Без вариантов", callback_data="triv:acid:start:manual")],
        [B("❌ Мои ошибки", callback_data="triv:acid:start:errors"), B("📊 Статистика", callback_data="triv:acid:stats")],
    ])


async def show_acid_menu(update, context, edit=False):
    errors = len(_unresolved_errors(update.effective_user.id)) if update.effective_user else 0
    text = (
        "🧪 Кислоты и кислотные остатки\n\n"
        "Тренируем только названия и формулы — без зарядов.\n"
        "🔥 В смешанных режимах усиленный акцент на хлор и фосфор."
    )
    if errors:
        text += f"\n\n❌ Для повторения: {errors}"
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=_acid_menu_markup())
    else:
        await update.effective_message.reply_text(text, reply_markup=_acid_menu_markup())


def acid_stats_text(user_id):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(total),0), COALESCE(SUM(correct),0)
            FROM acid_sessions
            WHERE telegram_user_id = ? AND finished_at IS NOT NULL
            """,
            (user_id,),
        ).fetchone()
    sessions, total, correct = row
    pct = round(correct * 100 / total) if total else 0
    errors = len(_unresolved_errors(user_id))
    return (
        "📊 Кислоты и остатки\n\n"
        f"Тренировок: {sessions}\n"
        f"Ответов: {correct}/{total}\n"
        f"Точность: {pct}%\n"
        f"❌ Осталось на повторение: {errors}"
    )


async def _finish_or_show_question(update, context, edit=False):
    session = context.user_data.get("acid_session")
    if not session:
        await show_acid_menu(update, context, edit=edit)
        return
    if session["index"] >= len(session["questions"]):
        _finish_session(session["session_id"], session["correct"])
        total = len(session["questions"])
        correct = session["correct"]
        context.user_data.pop("acid_session", None)
        text = f"🎉 Готово!\n\nРезультат: {correct}/{total}"
        markup = live7.InlineKeyboardMarkup([
            [live7.InlineKeyboardButton("Ещё 10 вопросов", callback_data="triv:acid:start:mixed")],
            [live7.InlineKeyboardButton("← В меню", callback_data="triv:acid:menu")],
        ])
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        else:
            await update.effective_message.reply_text(text, reply_markup=markup)
        return

    q = session["questions"][session["index"]]
    item = ACID_BY_ID[q["item_id"]]
    number = session["index"] + 1
    prompt = f"{number}/{len(session['questions'])}\n\n{_question_text(item, q['direction'])}"

    if session["mode"] == "manual":
        session["awaiting_manual"] = True
        context.user_data["acid_session"] = session
        prompt += "\n\n⌨️ Напиши ответ сообщением."
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(prompt)
        else:
            await update.effective_message.reply_text(prompt)
        return

    choices, correct_choice = _choice_values(q)
    session["choices"] = choices
    session["correct_choice"] = correct_choice
    context.user_data["acid_session"] = session
    rows = []
    for idx, choice in enumerate(choices):
        rows.append([live7.InlineKeyboardButton(choice, callback_data=f"triv:acid:a:{session['token']}:{idx}")])
    markup = live7.InlineKeyboardMarkup(rows)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(prompt, reply_markup=markup)
    else:
        await update.effective_message.reply_text(prompt, reply_markup=markup)


async def acid_callback(update, context):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data

    if data == "triv:acid:menu":
        context.user_data.pop("acid_session", None)
        await show_acid_menu(update, context, edit=True)
        return
    if data == "triv:acid:stats":
        await query.edit_message_text(
            acid_stats_text(update.effective_user.id),
            reply_markup=live7.InlineKeyboardMarkup([[live7.InlineKeyboardButton("← В меню", callback_data="triv:acid:menu")]]),
        )
        return
    if data.startswith("triv:acid:start:"):
        mode = data.split(":", 3)[3]
        if mode not in {"acid_nf", "acid_fn", "residue_nf", "residue_fn", "mixed", "focus", "manual", "errors"}:
            return
        if not _start_acid_session(context, update.effective_user, mode):
            await query.edit_message_text(
                "❌ Ошибок для повторения пока нет 💗",
                reply_markup=live7.InlineKeyboardMarkup([[live7.InlineKeyboardButton("← В меню", callback_data="triv:acid:menu")]]),
            )
            return
        await _finish_or_show_question(update, context, edit=True)
        return
    if data.startswith("triv:acid:a:"):
        parts = data.split(":")
        if len(parts) != 5:
            return
        token = parts[3]
        try:
            choice_index = int(parts[4])
        except ValueError:
            return
        session = context.user_data.get("acid_session")
        if not session or session.get("token") != token:
            await query.edit_message_text("Эта тренировка уже закончилась. Открой новую через меню.")
            return
        choices = session.get("choices") or []
        correct_choice = session.get("correct_choice")
        if not (0 <= choice_index < len(choices)) or correct_choice is None:
            return
        q = session["questions"][session["index"]]
        item = ACID_BY_ID[q["item_id"]]
        is_correct = choice_index == correct_choice
        _record_attempt(update.effective_user.id, item["id"], q["direction"], is_correct)
        if is_correct:
            session["correct"] += 1
            result = "✅ Верно!"
        else:
            session["wrong"].append((item["id"], q["direction"]))
            result = f"❌ Не совсем.\n\nПравильный ответ: {_answer_text(item, q['direction'])}"
        session["index"] += 1
        context.user_data["acid_session"] = session
        await query.edit_message_text(
            result,
            reply_markup=live7.InlineKeyboardMarkup([[live7.InlineKeyboardButton("Дальше ➡️", callback_data=f"triv:acid:next:{session['token']}")]]),
        )
        return
    if data.startswith("triv:acid:next:"):
        token = data.split(":", 3)[3]
        session = context.user_data.get("acid_session")
        if not session or session.get("token") != token:
            await show_acid_menu(update, context, edit=True)
            return
        await _finish_or_show_question(update, context, edit=True)


async def handle_acid_manual_answer(update, context):
    session = context.user_data.get("acid_session")
    if not session or not session.get("awaiting_manual") or session.get("mode") != "manual":
        return False
    if session["index"] >= len(session["questions"]):
        return False
    q = session["questions"][session["index"]]
    item = ACID_BY_ID[q["item_id"]]
    is_correct = _manual_is_correct(update.message.text, item, q["direction"])
    _record_attempt(update.effective_user.id, item["id"], q["direction"], is_correct)
    if is_correct:
        session["correct"] += 1
        await update.message.reply_text("✅ Верно!")
    else:
        session["wrong"].append((item["id"], q["direction"]))
        await update.message.reply_text(f"❌ Правильный ответ: {_answer_text(item, q['direction'])}")
    session["index"] += 1
    session["awaiting_manual"] = False
    context.user_data["acid_session"] = session
    await _finish_or_show_question(update, context)
    return True


# Добавляем отдельную кнопку тренажёра в постоянное меню ученика.
live7.STUDENT_KEYBOARD = live7.ReplyKeyboardMarkup(
    [
        ["🧪 Тривиальные названия"],
        ["🧪 Кислоты и остатки"],
        ["❌ Мои ошибки", "📊 Моя статистика"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

_original_callback = live7.trivial_callback
_original_text_router = live7.student_text_router
_original_start_router = live7.start_router


async def combined_trivial_callback(update, context):
    if update.callback_query and str(update.callback_query.data or "").startswith("triv:acid:"):
        await acid_callback(update, context)
        return
    await _original_callback(update, context)


async def combined_student_text_router(update, context):
    if not update.message or not update.message.text:
        return await _original_text_router(update, context)
    if update.effective_chat.type == "private":
        if await handle_acid_manual_answer(update, context):
            return
        if update.message.text.strip() == "🧪 Кислоты и остатки":
            context.user_data.pop("trivial_session", None)
            await show_acid_menu(update, context)
            return
    await _original_text_router(update, context)


async def combined_start_router(update, context):
    if update.effective_chat.type == "private" and context.args and context.args[0].lower() in {"acid", "acids"}:
        await update.message.reply_text("🧪 Тренажёр «Кислоты и остатки» открыт 💗", reply_markup=live7.STUDENT_KEYBOARD)
        await show_acid_menu(update, context)
        return
    await _original_start_router(update, context)


live7.trivial_callback = combined_trivial_callback
live7.student_text_router = combined_student_text_router
live7.start_router = combined_start_router


if __name__ == "__main__":
    ensure_acid_tables()
    live15.main()
