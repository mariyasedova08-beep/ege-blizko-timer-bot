"""Grade 11 payment schedules and admin previews. No student message delivery."""
import html
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


CADENCE_LABELS = {
    "monthly": "Ежемесячно",
    "quarterly": "Раз в три месяца",
    "prepaid": "Курс оплачен полностью",
    "review": "Нужно уточнить график",
}
NOTICE_DAYS_BEFORE_MONTH_END = 3
PAYMENT_GRACE_DAYS = 7
_payments = None
_bot = None
_cabinet = None


def cents(value):
    amount = Decimal(str(value or 0))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Некорректная сумма оплаты")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def money(value_cents):
    amount = Decimal(value_cents) / 100
    return f"{amount:,.0f}".replace(",", " ") + " ₽" if value_cents % 100 == 0 else f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " ₽"


def period_dates(period):
    year, month = map(int, period.split("-"))
    previous_month_end = date(year, month, 1) - timedelta(days=1)
    return (
        previous_month_end - timedelta(days=NOTICE_DAYS_BEFORE_MONTH_END),
        previous_month_end + timedelta(days=PAYMENT_GRACE_DAYS),
    )


def infer_initial_cadence(student, periods, as_of):
    keys = [period for period, _label in periods]
    rate = cents(student["monthly_amount"])
    coverage = {p: cents(v) for p, v in student["coverage"].items() if p in keys and cents(v) > 0}
    if not rate or any(value != rate for value in coverage.values()):
        return "review"
    if set(coverage) == set(keys):
        return "prepaid"
    # The owner defined these patterns for the initial September snapshot.
    # Later accumulated monthly payments must never be inferred as quarterly.
    if as_of.strftime("%Y-%m") != keys[0]:
        return "review"
    if set(coverage) == {keys[0]}:
        return "monthly"
    if set(coverage) == set(keys[:3]):
        return "quarterly"
    return "review"


def ensure_payment_plans():
    _payments.ensure_payment_tables()
    students = _payments._payment_rows()
    now = datetime.now(_bot.TIMEZONE).isoformat()
    with sqlite3.connect(_bot.COREAPP_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payment_plans (
                payment_student_id INTEGER PRIMARY KEY,
                cadence TEXT NOT NULL CHECK(cadence IN ('monthly','quarterly','prepaid','review')),
                monthly_amount_cents INTEGER NOT NULL CHECK(monthly_amount_cents >= 0),
                created_at TEXT NOT NULL,
                FOREIGN KEY(payment_student_id) REFERENCES payment_students(id)
            )
        """)
        existing = {row[0] for row in conn.execute("SELECT payment_student_id FROM payment_plans")}
        for student in students:
            if student["id"] in existing:
                continue
            cadence = infer_initial_cadence(student, _payments.PAYMENT_PERIODS, _bot.today_moscow())
            conn.execute(
                "INSERT OR IGNORE INTO payment_plans (payment_student_id,cadence,monthly_amount_cents,created_at) VALUES (?,?,?,?)",
                (student["id"], cadence, cents(student["monthly_amount"]), now),
            )


def invoices_for(student, plan, periods, as_of):
    """Course-aligned invoices. The 7th is inclusive; debt starts on the 8th."""
    cadence, rate = plan
    if cadence not in ("monthly", "quarterly"):
        return []
    step = 1 if cadence == "monthly" else 3
    invoices = []
    for start in range(0, len(periods), step):
        block = periods[start:start + step]
        expected = rate * len(block)
        paid = sum(cents(student["coverage"].get(period, 0)) for period, _label in block)
        remaining = max(0, expected - paid)
        notice, due = period_dates(block[0][0])
        status = "paid" if remaining == 0 else "overdue" if as_of > due else "due" if as_of >= notice else "upcoming"
        label = block[0][1].lower() if len(block) == 1 else block[0][1].lower() + "–" + block[-1][1].lower()
        invoices.append({
            "period": block[0][0], "periods": [p for p, _label in block],
            "label": label, "expected_cents": expected, "paid_cents": paid,
            "remaining_cents": remaining, "notice_date": notice,
            "due_date": due, "status": status,
        })
    return invoices


def schedule_rows(as_of=None):
    ensure_payment_plans()
    as_of = as_of or _bot.today_moscow()
    with sqlite3.connect(_bot.COREAPP_DB_PATH) as conn:
        plans = {sid: (cadence, rate) for sid, cadence, rate in conn.execute(
            "SELECT payment_student_id,cadence,monthly_amount_cents FROM payment_plans"
        )}
    result = []
    for student in _payments._payment_rows():
        cadence, rate = plans[student["id"]]
        invoices = invoices_for(student, (cadence, rate), _payments.PAYMENT_PERIODS, as_of)
        next_invoice = next((item for item in invoices if item["remaining_cents"] > 0), None)
        result.append({**student, "cadence": cadence, "rate_cents": rate,
                       "invoices": invoices, "next_invoice": next_invoice,
                       "overdue_cents": sum(item["remaining_cents"] for item in invoices if item["status"] == "overdue")})
    return result


def summary_text():
    rows = schedule_rows()
    if not rows:
        return (
            "💳 <b>Оплаты 11 класса</b>\n\n"
            "Графики готовы к настройке. Пришли файл «Доход.xlsx» в личный чат этого бота.\n"
            "Будет прочитана только вкладка «11 КЛАСС».\n\n"
            "Первый файл закрепит индивидуальный график. Повторные загрузки обновят отметки оплаты."
        )
    counts = Counter(row["cadence"] for row in rows)
    imported = _payments._payment_status()[0]
    stamp = datetime.fromisoformat(imported).strftime("%d.%m.%Y %H:%M") if imported else "—"
    lines = ["💳 <b>Оплаты 11 класса</b>", "", f"Данные обновлены: {stamp}",
             f"Ученики: <b>{len(rows)}</b>",
             f"Ежемесячно: <b>{counts['monthly']}</b>",
             f"Раз в три месяца: <b>{counts['quarterly']}</b>",
             f"Курс оплачен полностью: <b>{counts['prepaid']}</b>"]
    if counts["review"]:
        lines.append(f"⚠️ Нужно уточнить график: <b>{counts['review']}</b>")
    overdue = [row for row in rows if row["overdue_cents"] > 0]
    lines.extend(["", f"Просрочено: <b>{len(overdue)}</b> учеников — <b>{money(sum(row['overdue_cents'] for row in overdue))}</b>"])
    upcoming = [row for row in rows if row["next_invoice"]]
    if upcoming:
        nearest = min(row["next_invoice"]["due_date"] for row in upcoming)
        group = [row for row in upcoming if row["next_invoice"]["due_date"] == nearest]
        total = sum(row["next_invoice"]["remaining_cents"] for row in group)
        lines.append(f"Ближайший срок: <b>{nearest:%d.%m.%Y}</b> — {len(group)} учеников, <b>{money(total)}</b>")
    lines.extend(["", "Оплата — до 7-го числа включительно. Просрочка — с 8-го.",
                  "Черновик напоминания — за 3 дня до конца предыдущего месяца.",
                  "🔒 Проверка: автоотправка ученикам не включена."])
    return "\n".join(lines)


def payments_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 По ученикам", callback_data="cab:payments:list")],
        [InlineKeyboardButton("📅 Ближайшие оплаты", callback_data="cab:payments:upcoming")],
        [InlineKeyboardButton("🔔 Проверить напоминания", callback_data="cab:payments:drafts")],
        [InlineKeyboardButton("📎 Правила и обновление", callback_data="cab:payments:help")],
        [InlineKeyboardButton("🔄 Обновить сводку", callback_data="cab:payments")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])


def student_list_markup(drafts=False):
    buttons = []
    for row in schedule_rows():
        item = row["next_invoice"]
        if drafts and not item:
            continue
        suffix = f"до {item['due_date']:%d.%m}" if item else CADENCE_LABELS[row["cadence"]]
        label = (row["name"] + " · " + suffix)[:60]
        action = "draft" if drafts else "student"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cab:payments:{action}:{row['id']}")])
    buttons.append([InlineKeyboardButton("← К сводке", callback_data="cab:payments")])
    return InlineKeyboardMarkup(buttons)


def student_text(student_id):
    row = next((item for item in schedule_rows() if item["id"] == int(student_id)), None)
    if not row:
        return "Ученик не найден. Обнови файл с оплатами."
    lines = [f"💳 <b>{html.escape(row['name'])}</b>", CADENCE_LABELS[row["cadence"]],
             f"Сумма за месяц: <b>{money(row['rate_cents'])}</b>", ""]
    for period, month in _payments.PAYMENT_PERIODS:
        paid = cents(row["coverage"].get(period, 0))
        lines.append(f"✅ {month}: {money(paid)}" if paid else f"▫️ {month}: нет отметки")
    item = row["next_invoice"]
    if item:
        lines.extend(["", f"Следующая оплата: <b>{html.escape(item['label'])}</b>",
                      f"Осталось внести: <b>{money(item['remaining_cents'])}</b>",
                      f"Напоминание: <b>{item['notice_date']:%d.%m.%Y}</b>",
                      f"Оплатить до: <b>{item['due_date']:%d.%m.%Y}</b> включительно."])
    elif row["cadence"] == "review":
        lines.extend(["", "График не определён: суммы и даты напоминаний требуют уточнения."])
    else:
        lines.extend(["", "🏁 Курс оплачен полностью. Напоминания не требуются."])
    if row["overdue_cents"]:
        lines.append(f"🔴 Просрочено: {money(row['overdue_cents'])}")
    lines.extend(["", "🔒 Сообщения ученику пока не отправляются."])
    return "\n".join(lines)


def upcoming_text():
    rows = [row for row in schedule_rows() if row["next_invoice"]]
    rows.sort(key=lambda row: row["next_invoice"]["due_date"])
    lines = ["📅 <b>Ближайшие оплаты</b>", ""]
    for row in rows:
        item = row["next_invoice"]
        lines.extend([f"<b>{html.escape(row['name'])}</b> — {money(item['remaining_cents'])}",
                      f"{html.escape(item['label'])}: до {item['due_date']:%d.%m.%Y}; напоминание {item['notice_date']:%d.%m.%Y}", ""])
    if not rows:
        lines.append("Нет рассчитанных предстоящих платежей. Проверь загрузку данных и графики.")
    return "\n".join(lines)


def reminder_draft(student_id):
    row = next((item for item in schedule_rows() if item["id"] == int(student_id)), None)
    if not row:
        return "Ученик не найден."
    item = row["next_invoice"]
    if not item:
        return "Напоминание не требуется: курс оплачен." if row["cadence"] != "review" else "Сначала нужно уточнить график оплаты."
    text = (
        f"🔔 <b>Черновик для проверки: {html.escape(row['name'])}</b>\n"
        f"Плановая дата: {item['notice_date']:%d.%m.%Y}\n\n"
        f"Привет! 💗 Напоминаю об оплате курса за {html.escape(item['label'])}.\n"
        f"Сумма: <b>{money(item['remaining_cents'])}</b>.\n"
        f"Пожалуйста, внеси оплату до <b>{item['due_date']:%d.%m.%Y}</b> включительно.\n"
        "После оплаты, пожалуйста, пришли Маше расчётный чек, чтобы она отметила платёж. 💗\n\n"
        "🔒 Это сообщение показано только тебе. Ученику ничего не отправлено."
    )
    return text


def help_text():
    return (
        "📎 <b>Правила оплаты 11 класса</b>\n\n"
        "Суммы в Excel — уже полученные оплаты, распределённые по месяцам. Цвета не учитываются.\n"
        "В первоначальном сентябрьском файле: один месяц — ежемесячно; сентябрь–ноябрь — раз в три месяца; сентябрь–май — курс оплачен полностью.\n"
        "График и индивидуальная месячная сумма закрепляются при первой загрузке и сохраняются при обновлениях.\n\n"
        "Срок — последний день предыдущего месяца плюс 7 дней, то есть до 7-го включительно. Просрочка начинается 8-го.\n"
        "Напоминание — за 3 дня до конца предыдущего месяца: например, 27 сентября или 28 октября.\n"
        "При оплате раз в три месяца следующий период — декабрь–февраль, затем март–май. Полностью оплатившим напоминания не нужны.\n\n"
        "После получения денег обнови Excel и пришли файл в личный чат бота. Будет прочитана только вкладка «11 КЛАСС».\n\n"
        "🔒 Сейчас доступны расчёт и черновики для Маши. Автоотправка ученикам не включена."
    )


def install(payments, bot, cabinet):
    global _payments, _bot, _cabinet
    _payments, _bot, _cabinet = payments, bot, cabinet
    previous_save = payments.save_payment_snapshot

    def save_snapshot(students, filename):
        result = previous_save(students, filename)
        ensure_payment_plans()
        return result

    previous_callback = cabinet.cabinet_callback

    async def callback(update, context):
        query = update.callback_query
        data = str(query.data or "") if query else ""
        if not data.startswith("cab:payments"):
            await previous_callback(update, context)
            return
        if not cabinet._admin_private(update):
            if query:
                await query.answer("Раздел доступен только преподавателю")
            return
        back = InlineKeyboardMarkup([[InlineKeyboardButton("← К оплатам", callback_data="cab:payments")]])
        markup = back
        if data == "cab:payments":
            text, markup = summary_text(), payments_markup()
        elif data == "cab:payments:list":
            text, markup = "👥 <b>Оплаты по ученикам</b>", student_list_markup()
        elif data == "cab:payments:upcoming":
            text = upcoming_text()
        elif data == "cab:payments:drafts":
            text, markup = "🔔 <b>Проверка напоминаний</b>\n\nВыбери ученика, чтобы увидеть черновик. Отправка ученикам выключена.", student_list_markup(drafts=True)
        elif data == "cab:payments:help":
            text = help_text()
        elif data.startswith(("cab:payments:student:", "cab:payments:draft:")):
            try:
                sid = int(data.rsplit(":", 1)[1])
            except ValueError:
                await query.answer("Не удалось определить ученика")
                return
            text = reminder_draft(sid) if ":draft:" in data else student_text(sid)
            if ":student:" in data:
                markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔔 Черновик напоминания", callback_data=f"cab:payments:draft:{sid}")],
                    [InlineKeyboardButton("← К ученикам", callback_data="cab:payments:list")],
                ])
        else:
            await previous_callback(update, context)
            return
        await query.answer()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    payments.save_payment_snapshot = save_snapshot
    payments.payments_summary_text = summary_text
    payments.payments_markup = payments_markup
    payments.payment_students_markup = student_list_markup
    payments.payment_student_text = student_text
    cabinet.cabinet_callback = callback
