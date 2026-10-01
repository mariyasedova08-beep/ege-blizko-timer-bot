"""Monthly identified student feedback surveys: 01.10.2026–01.05.2027."""
from datetime import date, datetime, time
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

import run_bot_live90 as live90
import student_october_survey as legacy

bot = live90.bot
live23 = live90.live23
QUESTIONS = legacy.QUESTIONS
QUESTION_BY_KEY = legacy.QUESTION_BY_KEY
SEND_TIME = time(17, 0)
SEND_TIME_TEXT = "17:00"
DATES = (
    date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1),
    date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1), date(2027, 5, 1),
)
DAY_BY_TOKEN = {d.strftime("%Y%m"): d for d in DATES}
TOKEN_BY_DAY = {d: d.strftime("%Y%m") for d in DATES}


def key_for(day):
    return f"student_feedback_{day:%Y_%m_%d}"


def _now():
    return datetime.now(bot.TIMEZONE)


def ensure_tables():
    legacy.ensure_tables()


def _session(key, uid):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM student_survey_sessions WHERE survey_key=? AND telegram_user_id=?",
            (key, int(uid)),
        ).fetchone()


def _ensure_session(key, uid, fallback):
    row = _session(key, uid)
    if row:
        return row
    student = legacy._student_row(uid)
    name = (student["student_name"] if student else None) or fallback or "Ученик"
    now = _now().isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO student_survey_sessions "
            "(survey_key,telegram_user_id,student_name,current_index,started_at,updated_at,completed_at) "
            "VALUES (?,?,?,0,?,?,NULL)",
            (key, int(uid), name, now, now),
        )
        conn.commit()
    return _session(key, uid)


def _latest_open(uid):
    keys = tuple(key_for(d) for d in DATES)
    marks = ",".join("?" for _ in keys)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            f"SELECT * FROM student_survey_sessions WHERE telegram_user_id=? "
            f"AND completed_at IS NULL AND survey_key IN ({marks}) ORDER BY started_at DESC LIMIT 1",
            (int(uid), *keys),
        ).fetchone()


def _save(key, uid, question, code=None, text=None):
    session = _session(key, uid)
    if not session or session["completed_at"]:
        return None
    idx = int(session["current_index"])
    if idx >= len(QUESTIONS) or QUESTIONS[idx]["key"] != question["key"]:
        return None
    now = _now().isoformat()
    nxt = idx + 1
    done = now if nxt >= len(QUESTIONS) else None
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            "INSERT INTO student_survey_answers "
            "(survey_key,telegram_user_id,question_key,answer_code,answer_text,answered_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(survey_key,telegram_user_id,question_key) DO UPDATE SET "
            "answer_code=excluded.answer_code,answer_text=excluded.answer_text,answered_at=excluded.answered_at",
            (key, int(uid), question["key"], code, text, now),
        )
        conn.execute(
            "UPDATE student_survey_sessions SET current_index=?,updated_at=?,completed_at=? "
            "WHERE survey_key=? AND telegram_user_id=?",
            (nxt, now, done, key, int(uid)),
        )
        conn.commit()
    return nxt, bool(done)


def _q_markup(question, token):
    if question["type"] != "choice":
        return None
    buttons = [InlineKeyboardButton(label, callback_data=f"msv:a:{token}:{question['key']}:{code}") for code, label in question["options"]]
    if len(buttons) == 5 and all(code.isdigit() for code, _ in question["options"]):
        return InlineKeyboardMarkup([buttons])
    return InlineKeyboardMarkup([[b] for b in buttons])


async def _show_question(target, key, token, uid, edit=False):
    session = _session(key, uid)
    if not session:
        return
    idx = int(session["current_index"])
    if session["completed_at"] or idx >= len(QUESTIONS):
        text = "Спасибо 💗 Я всё сохранила. Твои ответы помогут сделать занятия удобнее и полезнее."
        if edit:
            await target.edit_message_text(text)
        else:
            await target.reply_text(text)
        return
    q = QUESTIONS[idx]
    if edit:
        await target.edit_message_text(q["text"], reply_markup=_q_markup(q, token))
    else:
        await target.reply_text(q["text"], reply_markup=_q_markup(q, token))


async def student_callback(update, context):
    query = update.callback_query
    if not query or not query.data.startswith("msv:"):
        return
    await query.answer()
    parts = query.data.split(":")
    uid = int(update.effective_user.id)
    if len(parts) == 3 and parts[1] == "start":
        token = parts[2]
        day = DAY_BY_TOKEN.get(token)
        if not day:
            await query.edit_message_text("Этот опрос уже недоступен.")
            raise ApplicationHandlerStop
        key = key_for(day)
        _ensure_session(key, uid, update.effective_user.full_name or "Ученик")
        await _show_question(query, key, token, uid, edit=True)
        raise ApplicationHandlerStop
    if len(parts) == 5 and parts[1] == "a":
        _, _, token, qkey, code = parts
        day = DAY_BY_TOKEN.get(token)
        q = QUESTION_BY_KEY.get(qkey)
        if not day or not q:
            raise ApplicationHandlerStop
        key = key_for(day)
        session = _session(key, uid)
        if not session or session["completed_at"]:
            await query.edit_message_text("Этот опрос уже завершён 💗")
            raise ApplicationHandlerStop
        idx = int(session["current_index"])
        if idx >= len(QUESTIONS) or QUESTIONS[idx]["key"] != qkey:
            await _show_question(query, key, token, uid, edit=True)
            raise ApplicationHandlerStop
        if code not in {x for x, _ in q.get("options", ())}:
            raise ApplicationHandlerStop
        saved = _save(key, uid, q, code=code)
        if saved and saved[1]:
            await query.edit_message_text("Спасибо 💗 Я всё сохранила. Твои ответы помогут сделать занятия удобнее и полезнее.")
        elif saved:
            await _show_question(query, key, token, uid, edit=True)
        raise ApplicationHandlerStop
    raise ApplicationHandlerStop


async def student_text(update, context):
    if not update.message or not update.message.text or update.effective_chat.type != "private":
        return
    uid = int(update.effective_user.id)
    session = _latest_open(uid)
    if not session:
        return
    key = session["survey_key"]
    day = next((d for d in DATES if key_for(d) == key), None)
    if not day:
        return
    idx = int(session["current_index"])
    if idx >= len(QUESTIONS):
        return
    q = QUESTIONS[idx]
    if q["type"] != "text":
        await update.message.reply_text("Здесь нужно выбрать вариант кнопкой под вопросом 💗")
        raise ApplicationHandlerStop
    answer = " ".join(update.message.text.split()).strip()
    if not answer:
        await update.message.reply_text("Напиши хотя бы пару слов 💗")
        raise ApplicationHandlerStop
    saved = _save(key, uid, q, text=answer[:1500])
    if saved and saved[1]:
        await update.message.reply_text("Спасибо 💗 Я всё сохранила. Твои ответы помогут сделать занятия удобнее и полезнее.")
    elif saved:
        await _show_question(update.message, key, TOKEN_BY_DAY[day], uid)
    raise ApplicationHandlerStop


def _intro(day):
    return (
        "Привет 💗 Хочу коротко спросить, как тебе сейчас учится.\n\n"
        "Всего 6 вопросов — примерно на 2 минуты. Здесь нет правильных ответов: "
        "мне важно понять, что уже хорошо, а что можно сделать удобнее.\n\n"
        "Ответы увижу я, Маша, и буду использовать их только для улучшения занятий."
    )


async def delivery_tick(context):
    now = _now()
    day = now.date()
    if day not in TOKEN_BY_DAY or now.time().replace(tzinfo=None) < SEND_TIME:
        return
    key = key_for(day)
    token = TOKEN_BY_DAY[day]
    sent, failed = [], []
    for uid, name in legacy._recipients():
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            old = conn.execute(
                "SELECT status FROM student_survey_deliveries WHERE survey_key=? AND telegram_user_id=?",
                (key, int(uid)),
            ).fetchone()
        if old and old[0] == "sent":
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=_intro(day),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Пройти опрос", callback_data=f"msv:start:{token}")]]),
            )
            status, error = "sent", None
            sent.append(name)
        except Exception as exc:
            status, error = "failed", repr(exc)[:500]
            failed.append(name)
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO student_survey_deliveries "
                "(survey_key,telegram_user_id,student_name,status,sent_at,error) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(survey_key,telegram_user_id) DO UPDATE SET student_name=excluded.student_name,"
                "status=excluded.status,sent_at=excluded.sent_at,error=excluded.error",
                (key, int(uid), name, status, _now().isoformat(), error),
            )
            conn.commit()
    if sent or failed:
        admin_id = bot.get_admin_id()
        if admin_id:
            lines = [f"📊 Опрос учеников • {day:%d.%m.%Y}"]
            if sent:
                lines.append(f"✅ Доставлено: {len(sent)}")
            if failed:
                lines.append(f"⚠️ Не доставлено: {len(failed)} — " + ", ".join(failed))
            try:
                await context.bot.send_message(chat_id=int(admin_id), text="\n".join(lines))
            except Exception:
                pass


def _stats(day):
    key = key_for(day)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        delivered = conn.execute("SELECT count(*) c FROM student_survey_deliveries WHERE survey_key=? AND status='sent'", (key,)).fetchone()["c"]
        failed = conn.execute("SELECT count(*) c FROM student_survey_deliveries WHERE survey_key=? AND status='failed'", (key,)).fetchone()["c"]
        started = conn.execute("SELECT count(*) c FROM student_survey_sessions WHERE survey_key=?", (key,)).fetchone()["c"]
        completed = conn.execute("SELECT count(*) c FROM student_survey_sessions WHERE survey_key=? AND completed_at IS NOT NULL", (key,)).fetchone()["c"]
        answers = conn.execute("SELECT question_key,answer_code FROM student_survey_answers WHERE survey_key=? AND answer_code IS NOT NULL", (key,)).fetchall()
    numeric = {"lesson_clarity": [], "question_comfort": [], "progress_feeling": []}
    hw = {"low": 0, "ok": 0, "high": 0}
    for row in answers:
        qkey, code = row["question_key"], row["answer_code"]
        if qkey in numeric and str(code).isdigit():
            numeric[qkey].append(int(code))
        if qkey == "homework_amount" and code in hw:
            hw[code] += 1
    def avg(q):
        return "—" if not numeric[q] else f"{sum(numeric[q]) / len(numeric[q]):.1f}/5"
    return delivered, failed, started, completed, avg, hw


def _summary(day):
    delivered, failed, started, completed, avg, hw = _stats(day)
    return (
        f"📊 Опрос учеников • {day:%d.%m.%Y}\n\nДоставлено: {delivered}\nНе доставлено: {failed}\n"
        f"Начали: {started}\nЗавершили: {completed}\n\nПонятность уроков: {avg('lesson_clarity')}\n"
        f"Комфорт задавать вопросы: {avg('question_comfort')}\nОщущение прогресса: {avg('progress_feeling')}\n\n"
        f"Домашняя работа:\n• хочется больше — {hw['low']}\n• в самый раз — {hw['ok']}\n• слишком много — {hw['high']}"
    )


def _sessions(day):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT telegram_user_id,student_name,current_index,completed_at FROM student_survey_sessions "
            "WHERE survey_key=? ORDER BY completed_at IS NULL,lower(student_name)",
            (key_for(day),),
        ).fetchall()


def _months_text():
    lines = ["📊 Опросы учеников", "", "Одинаковые 6 вопросов — каждое 1 число месяца в 17:00 по Москве.", ""]
    for day in DATES:
        delivered, _f, started, completed, _a, _h = _stats(day)
        mark = "✅" if completed else ("⏳" if started else ("📨" if delivered else "▫️"))
        lines.append(f"{mark} {day:%d.%m.%Y} — завершили {completed}/{delivered}")
    return "\n".join(lines)


def _months_markup():
    buttons = [InlineKeyboardButton(d.strftime("%d.%m.%Y"), callback_data=f"cab:msvmonth:{TOKEN_BY_DAY[d]}") for d in DATES]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return InlineKeyboardMarkup(rows)


def _month_markup(day):
    token = TOKEN_BY_DAY[day]
    rows = []
    for row in _sessions(day)[:35]:
        status = "✅" if row["completed_at"] else f"⏳ {row['current_index']}/6"
        rows.append([InlineKeyboardButton(f"{status} {row['student_name']}", callback_data=f"cab:msvdetail:{token}:{int(row['telegram_user_id'])}")])
    rows += [
        [InlineKeyboardButton("🔄 Обновить", callback_data=f"cab:msvmonth:{token}")],
        [InlineKeyboardButton("← К месяцам", callback_data="cab:studentsurvey")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ]
    return InlineKeyboardMarkup(rows)


def _detail(day, uid):
    key = key_for(day)
    session = _session(key, uid)
    if not session:
        return "Ответы ученика не найдены."
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT question_key,answer_code,answer_text FROM student_survey_answers WHERE survey_key=? AND telegram_user_id=?", (key, int(uid))).fetchall()
    by = {r["question_key"]: r for r in rows}
    labels = {
        "lesson_clarity":"Понятность уроков", "hardest_now":"Самое сложное сейчас", "homework_amount":"Объём ДЗ",
        "question_comfort":"Комфорт задавать вопросы", "progress_feeling":"Ощущение прогресса", "change_request":"Что изменить/добавить"
    }
    out = [f"📊 {session['student_name']} • {day:%d.%m.%Y}", ""]
    for i, q in enumerate(QUESTIONS, 1):
        row = by.get(q["key"])
        value = "—" if not row else legacy._answer_label(q["key"], row["answer_code"], row["answer_text"])
        out.append(f"{i}. {labels[q['key']]}: {value}")
    out += ["", "✅ Завершён" if session["completed_at"] else f"⏳ Пройдено {session['current_index']}/6"]
    return "\n".join(out)


_previous_markup = None
_previous_callback = None
_original_build = None
_installed = False


def _patch_cabinet():
    global _previous_markup, _previous_callback
    _previous_markup, _previous_callback = live23.cabinet_markup, live23.cabinet_callback

    def markup():
        rows = [list(r) for r in _previous_markup().inline_keyboard]
        rows = [[b for b in r if getattr(b, "callback_data", None) != "cab:studentsurvey"] for r in rows]
        rows = [r for r in rows if r]
        rows.insert(max(0, len(rows)-1), [InlineKeyboardButton("📊 Опросы учеников", callback_data="cab:studentsurvey")])
        return InlineKeyboardMarkup(rows)

    async def callback(update, context):
        q = update.callback_query
        data = q.data if q else ""
        if data == "cab:studentsurvey":
            await q.answer()
            await q.edit_message_text(_months_text(), reply_markup=_months_markup())
            return
        if data.startswith("cab:msvmonth:"):
            await q.answer()
            day = DAY_BY_TOKEN.get(data.rsplit(":",1)[1])
            if day:
                await q.edit_message_text(_summary(day), reply_markup=_month_markup(day))
            return
        if data.startswith("cab:msvdetail:"):
            await q.answer()
            parts = data.split(":")
            if len(parts) == 4:
                day = DAY_BY_TOKEN.get(parts[2])
                try:
                    uid = int(parts[3])
                except ValueError:
                    uid = None
                if day and uid is not None:
                    await q.edit_message_text(
                        _detail(day, uid),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("← К результатам месяца", callback_data=f"cab:msvmonth:{parts[2]}")],
                            [InlineKeyboardButton("← К месяцам", callback_data="cab:studentsurvey")],
                        ]),
                    )
            return
        if data.startswith("cab:studentsurveydetail:"):
            await q.answer()
            try:
                uid = int(data.rsplit(":",1)[1])
            except ValueError:
                return
            day = DATES[0]
            await q.edit_message_text(
                _detail(day, uid),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("← К результатам месяца", callback_data=f"cab:msvmonth:{TOKEN_BY_DAY[day]}")],
                    [InlineKeyboardButton("← К месяцам", callback_data="cab:studentsurvey")],
                ]),
            )
            return
        await _previous_callback(update, context)

    live23.cabinet_markup, live23.cabinet_callback = markup, callback


def _build(self):
    app = _original_build(self)
    app.add_handler(CallbackQueryHandler(student_callback, pattern=r"^msv:"), group=-31)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, student_text), group=-31)
    app.job_queue.run_repeating(delivery_tick, interval=60, first=20, name="student_feedback_monthly_delivery")
    return app


def install():
    global _original_build, _installed
    if _installed:
        return
    ensure_tables()
    _patch_cabinet()
    _original_build = ApplicationBuilder.build
    ApplicationBuilder.build = _build
    _installed = True
    print(
        "Student monthly surveys ready: dates=" + ",".join(d.isoformat() for d in DATES) + f" time={SEND_TIME_TEXT} questions={len(QUESTIONS)}",
        flush=True,
    )
