"""90-day Instagram return system for Maria's admin cabinet.

The goal is gradual exposure after a two-year pause: rebuild consistency first,
then authority, reach and conversion. No automatic posting and no unsolicited
Instagram reminders are sent; the system lives inside the admin cabinet.
"""
import html
import sqlite3
from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90

live79 = live90.live79
live23 = live79.live23
live7 = live79.live7
bot = live90.bot

START_DATE = date(2026, 9, 13)
TOTAL_DAYS = 90
_INSTALLED = False

FIRST_14 = {
    1: ("Разморозка", "Обнови шапку профиля: убери «строго», сделай понятный оффер и добавь путь в Telegram/к тренажёрам.", "Сегодня ничего не продаём. Цель — чтобы новый человек за 10 секунд понял: кто ты, кому помогаешь и куда нажать дальше."),
    2: ("Разморозка", "Выложи 3–5 Stories: «Я возвращаю эту страницу после двух лет тишины» + что изменилось в твоей работе + вопрос аудитории.", "Не нужно оправдываться за паузу. Это не отчёт о пропаже, а новая точка старта."),
    3: ("Разморозка", "Сделай пост/карусель-знакомство: кто ты сейчас, 10 лет в химии, как устроено ЕГЭ БЛИЗКО и во что ты веришь как преподаватель.", "Закрепи этот пост. Он будет работать вместо необходимости заново представляться каждому новому человеку."),
    4: ("Разморозка", "Первый короткий Reel: 15–30 секунд, одна мысль. Тема: «Почему я почти не задаю просто учить — мы играем в долгую».", "Один дубль, минимум монтажа. Не проверяй просмотры первый час и не удаляй публикацию 24 часа."),
    5: ("Разморозка", "Stories без экспертного давления: покажи кусочек рабочего дня/прогулки и задай один простой вопрос про подготовку к ЕГЭ.", "Люди возвращаются не только к знаниям, но и к человеку. Тебе не нужно всё время преподавать в кадре."),
    6: ("Разморозка", "Опубликуй полезную карусель/шпаргалку по химии с очень конкретной пользой и призывом сохранить.", "Главная метрика такого поста — сохранения, а не лайки."),
    7: ("Разморозка", "Ничего нового не снимай. Посмотри первую неделю: что было легче всего опубликовать, что сохранили/ответили, что вызвало тревогу.", "Первая неделя — не экзамен на охваты. Мы собираем данные о формате и о твоей реакции."),
    8: ("Разморозка", "Reel: одна типичная ошибка ученика в химии → почему она возникает → как исправить.", "Говори как на уроке одному ученику, а не как будто выступаешь перед тысячами людей."),
    9: ("Разморозка", "Покажи доказательство: отзыв, динамику ученика, фрагмент результата или процесс подготовки — без длинной продажи.", "Нам нужно постепенно вернуть странице социальное доказательство."),
    10: ("Разморозка", "Покажи один из тренажёров ЕГЭ БЛИЗКО и предложи попробовать 10 вопросов бесплатно.", "Это первая мягкая воронка: контент → Telegram/бот → полезный опыт → доверие."),
    11: ("Разморозка", "Voice-over Reel на фоне прогулки/природы: одна твоя мысль о подготовке, дисциплине или памяти.", "Тебе не обязательно каждый раз быть говорящей головой. Используем твой естественный визуал."),
    12: ("Разморозка", "Пост: «Как проходят мои занятия сейчас» — живые уроки, система, ДЗ, тренажёры, контроль результата.", "Не перечисляй функции. Покажи, зачем каждая часть нужна ученику."),
    13: ("Разморозка", "Stories/короткое видео из-за кулис: как ты создаёшь бот, банк заданий или новый тренажёр.", "Это одновременно демонстрация масштаба работы и мостик к будущему продукту для преподавателей."),
    14: ("Разморозка", "Итоги двух недель: выбери 3 формата, которые реально можешь поддерживать, и откажись от лишнего.", "Наша система должна быть выдерживаемой месяцами, а не красивой только на бумаге."),
}

WEEKDAY_TASKS = {
    0: ("Reel — экспертность", "Сними короткий Reel с одной сильной мыслью/ошибкой по химии. Структура: хук → объяснение → один вывод."),
    1: ("Stories — контакт", "Сделай 3–5 Stories: рабочий/личный контекст → вопрос или опрос → короткий ответ/мысль."),
    2: ("Карусель — сохраняемость", "Опубликуй карусель/шпаргалку, которую ученику захочется сохранить перед повторением."),
    3: ("Доказательство", "Покажи результат, отзыв, динамику, фрагмент урока, ДЗ или внутреннюю кухню ЕГЭ БЛИЗКО."),
    4: ("Reel → воронка", "Сними Reel, который естественно приводит к бесплатному тренажёру/Telegram: проблема → мини-решение → «попробуй 10 вопросов»."),
    5: ("Личный бренд", "Покажи тебя вне урока: прогулка, природа, жизнь, мысль недели. Свяжи с одной ценностью бренда, без обязательной продажи."),
    6: ("Аналитика", "Ничего не доказывай алгоритму. Запиши метрики недели, выбери лучший контент и одну гипотезу на следующую неделю."),
}

PHASES = (
    (1, 14, "🌱 Возвращение", "Вернуть привычку быть видимой и объяснить аудитории, кто ты сейчас."),
    (15, 42, "🧠 Экспертность", "Закрепить образ сильного, понятного и живого преподавателя химии."),
    (43, 70, "📣 Рост", "Расширять охват: сильнее хуки, повтор лучших тем, коллаборации и кросспостинг."),
    (71, 90, "💗 Конверсия", "Системно вести людей из контента в Telegram, тренажёры, курсы и пилот продукта для преподавателей."),
)


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS instagram_return_progress (
                day_number INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS instagram_return_metrics (
                snapshot_date TEXT PRIMARY KEY,
                followers INTEGER,
                views INTEGER,
                profile_visits INTEGER,
                link_clicks INTEGER,
                inquiries INTEGER,
                sales INTEGER,
                saved_at TEXT NOT NULL
            )
        """)
        # Baseline from Maria's Instagram screenshot on 12 Sep 2026.
        conn.execute("""
            INSERT OR IGNORE INTO instagram_return_metrics
                (snapshot_date, followers, views, profile_visits, link_clicks, inquiries, sales, saved_at)
            VALUES (?, ?, ?, NULL, NULL, NULL, NULL, ?)
        """, (date(2026, 9, 12).isoformat(), 627, 169, datetime.now(bot.TIMEZONE).isoformat()))
        conn.commit()


def _today_day(now=None):
    now = now or datetime.now(bot.TIMEZONE)
    day_num = (now.date() - START_DATE).days + 1
    return max(1, min(TOTAL_DAYS, day_num))


def _phase(day_num):
    for start, end, title, goal in PHASES:
        if start <= day_num <= end:
            return title, goal
    return PHASES[-1][2], PHASES[-1][3]


def _task(day_num):
    if day_num in FIRST_14:
        _phase_name, task, note = FIRST_14[day_num]
        return task, note
    target_date = START_DATE + timedelta(days=day_num - 1)
    label, task = WEEKDAY_TASKS[target_date.weekday()]
    phase_title, _goal = _phase(day_num)
    extra = ""
    if 43 <= day_num <= 70:
        if target_date.weekday() == 0:
            extra = " Возьми тему, которая уже сработала, и пересними её с новым хуком вместо постоянного изобретения нового."
        elif target_date.weekday() == 3:
            extra = " Раз в две недели добавляй совместный эфир/коллаборацию/взаимный контент с близким по аудитории экспертом."
        elif target_date.weekday() == 4:
            extra = " Лучший Reel недели продублируй в Shorts/другую короткую видео-площадку."
    if 71 <= day_num <= 90:
        if target_date.weekday() == 3:
            extra = " Чередуй доказательства для учеников и кейсы создания бота для преподавателей."
        elif target_date.weekday() == 4:
            extra = " CTA должен вести в один конкретный следующий шаг: тренажёр, Telegram, группа или пилот бота."
    note = f"Этап: {phase_title}. Не оценивай свою ценность по просмотрам одной публикации.{extra}"
    return f"{label}: {task}", note


def _is_done(day_num):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute("SELECT status FROM instagram_return_progress WHERE day_number = ?", (int(day_num),)).fetchone()
    return bool(row and row[0] == "done")


def _mark_done(day_num):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("""
            INSERT INTO instagram_return_progress (day_number, status, completed_at)
            VALUES (?, 'done', ?)
            ON CONFLICT(day_number) DO UPDATE SET status='done', completed_at=excluded.completed_at
        """, (int(day_num), datetime.now(bot.TIMEZONE).isoformat()))
        conn.commit()


def _completed_count():
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM instagram_return_progress WHERE status='done'").fetchone()[0] or 0)


def _latest_metrics(limit=2):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute("""
            SELECT snapshot_date, followers, views, profile_visits, link_clicks, inquiries, sales
            FROM instagram_return_metrics
            ORDER BY snapshot_date DESC
            LIMIT ?
        """, (int(limit),)).fetchall()


def _metric(value):
    return "—" if value is None else str(value)


def _main_text():
    day_num = _today_day()
    phase_title, phase_goal = _phase(day_num)
    task, note = _task(day_num)
    status = "✅ Сегодня выполнено" if _is_done(day_num) else "⏳ Сегодня ещё не отмечено"
    return (
        "📱 <b>Instagram — возвращение за 90 дней</b>\n\n"
        f"День <b>{day_num}/{TOTAL_DAYS}</b> · {phase_title}\n"
        f"{status}\n\n"
        f"<b>Цель этапа:</b> {html.escape(phase_goal)}\n\n"
        f"<b>Сегодня:</b> {html.escape(task)}\n\n"
        f"🧠 {html.escape(note)}\n\n"
        f"Пройдено дней: <b>{_completed_count()}</b>. Здесь считаем выходы, а не идеальность."
    )


def _main_markup():
    day_num = _today_day()
    rows = []
    if not _is_done(day_num):
        rows.append([InlineKeyboardButton("✅ Сделано сегодня", callback_data=f"cab:ig:done:{day_num}")])
    rows.extend([
        [InlineKeyboardButton("🪶 Мне страшно — упростить", callback_data=f"cab:ig:light:{day_num}")],
        [InlineKeyboardButton("🗺 План 90 дней", callback_data="cab:ig:roadmap"), InlineKeyboardButton("📊 Метрики", callback_data="cab:ig:metrics")],
        [InlineKeyboardButton("🧠 Правила головы", callback_data="cab:ig:mind")],
        [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
    ])
    return InlineKeyboardMarkup(rows)


def _roadmap_text():
    return (
        "🗺 <b>План возвращения</b>\n\n"
        "🌱 <b>Дни 1–14 — возвращение.</b> Не гонимся за ростом. Возвращаем Stories, лицо, голос, знакомство и первые Reels.\n\n"
        "🧠 <b>Дни 15–42 — экспертность.</b> 2 Reels + 1 карусель + доказательство + живые Stories в неделю. Формируем узнаваемую систему ЕГЭ БЛИЗКО.\n\n"
        "📣 <b>Дни 43–70 — рост.</b> Повторяем сильные темы, усиливаем хуки, делаем кросспостинг, тестируем коллаборации.\n\n"
        "💗 <b>Дни 71–90 — конверсия.</b> Регулярно ведём в Telegram/тренажёры/группы; продукт для преподавателей показываем отдельной рубрикой, а не смешиваем с каждым постом.\n\n"
        "Базовая пропорция контента сейчас: <b>75% ученики/химия · 25% бот/преподаватели</b>."
    )


def _mind_text():
    return (
        "🧠 <b>Правила, чтобы не бросить</b>\n\n"
        "1. До 30 публикаций нельзя делать вывод «это никому не нужно». Мы ещё собираем данные.\n"
        "2. Не удалять публикацию минимум 24 часа.\n"
        "3. Первый час после публикации не проверять просмотры.\n"
        "4. Оцениваем контент раз в неделю, не каждые 10 минут.\n"
        "5. Лайки — не главная метрика. Смотрим сохранения, переходы, Telegram, тренажёры, заявки и продажи.\n"
        "6. Страшно ≠ нельзя. Страшно означает: уменьшаем сложность формата, но сохраняем действие.\n"
        "7. Один хороший смысл превращаем в Reel + карусель + Stories + Telegram, а не придумываем четыре темы."
    )


def _light_text(day_num):
    task, _note = _task(day_num)
    target_date = START_DATE + timedelta(days=day_num - 1)
    if day_num <= 3:
        minimum = "Сделай только 3 Stories без идеального дизайна: одно живое фото/видео + одна мысль + один вопрос."
    elif target_date.weekday() in (0, 4) or day_num in (4, 8, 10, 11):
        minimum = "Сними Reel на 15 секунд одним дублем: 1 фраза-хук + 1 мысль + «сохрани/попробуй тренажёр». Без сложного монтажа."
    elif target_date.weekday() == 2 or day_num in (6, 12):
        minimum = "Сделай карусель из 3 слайдов: проблема → главное правило → мини-пример. Этого достаточно."
    else:
        minimum = "Сделай одну Stories с лицом/голосом и одной мыслью по теме. Не украшай и не переснимай больше двух раз."
    return (
        "🪶 <b>Минимальная версия</b>\n\n"
        f"Исходная задача: {html.escape(task)}\n\n"
        f"Сегодня достаточно вот этого:\n<b>{html.escape(minimum)}</b>\n\n"
        "Мы не отменяем выход — мы уменьшаем трение. После публикации закрывай Instagram минимум на час."
    )


def _metrics_text():
    rows = _latest_metrics(2)
    if not rows:
        return "📊 Метрик пока нет."
    current = rows[0]
    lines = ["📊 <b>Метрики — без самооценки</b>", ""]
    labels = ["Дата", "Подписчики", "Просмотры", "Визиты профиля", "Переходы по ссылке", "Заявки", "Продажи"]
    for label, value in zip(labels, current):
        lines.append(f"{label}: <b>{html.escape(_metric(value))}</b>")
    if len(rows) > 1:
        previous = rows[1]
        if current[1] is not None and previous[1] is not None:
            delta = current[1] - previous[1]
            lines.append(f"\nИзменение подписчиков: <b>{delta:+d}</b>")
    lines.extend([
        "",
        "Вносим цифры раз в неделю. Лайки специально не записываем — они слишком легко превращаются в оценку себя.",
    ])
    return "\n".join(lines)


def _metrics_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Внести метрики", callback_data="cab:ig:metrics:add")],
        [InlineKeyboardButton("← К Instagram", callback_data="cab:ig")],
    ])


def _parse_metric_token(token):
    token = str(token).strip()
    if token in {"-", "—", "нет", "?"}:
        return None
    value = int(token.replace(" ", ""))
    if value < 0:
        raise ValueError
    return value


def _save_metrics(values):
    followers, views, profile_visits, link_clicks, inquiries, sales = values
    now = datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute("""
            INSERT INTO instagram_return_metrics
                (snapshot_date, followers, views, profile_visits, link_clicks, inquiries, sales, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                followers=excluded.followers,
                views=excluded.views,
                profile_visits=excluded.profile_visits,
                link_clicks=excluded.link_clicks,
                inquiries=excluded.inquiries,
                sales=excluded.sales,
                saved_at=excluded.saved_at
        """, (now.date().isoformat(), followers, views, profile_visits, link_clicks, inquiries, sales, now.isoformat()))
        conn.commit()


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    ensure_tables()

    previous_markup = live23.cabinet_markup
    def cabinet_markup_with_instagram():
        base = previous_markup()
        rows = [list(row) for row in base.inline_keyboard]
        if not any(getattr(button, "callback_data", None) == "cab:ig" for row in rows for button in row):
            rows.append([InlineKeyboardButton("📱 Instagram — 90 дней", callback_data="cab:ig")])
        return InlineKeyboardMarkup(rows)
    live23.cabinet_markup = cabinet_markup_with_instagram

    previous_callback = live23.cabinet_callback
    async def cabinet_callback_with_instagram(update, context):
        query = update.callback_query
        if not query or not live23._admin_private(update):
            return await previous_callback(update, context)
        data = str(query.data or "")
        if data == "cab:ig":
            await query.answer()
            await query.edit_message_text(_main_text(), parse_mode="HTML", reply_markup=_main_markup())
            return
        if data.startswith("cab:ig:done:"):
            try:
                day_num = int(data.rsplit(":", 1)[1])
            except Exception:
                return
            _mark_done(day_num)
            await query.answer("Есть ✅")
            await query.edit_message_text(_main_text(), parse_mode="HTML", reply_markup=_main_markup())
            return
        if data.startswith("cab:ig:light:"):
            try:
                day_num = int(data.rsplit(":", 1)[1])
            except Exception:
                day_num = _today_day()
            await query.answer()
            await query.edit_message_text(
                _light_text(day_num), parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← К сегодняшней задаче", callback_data="cab:ig")]])
            )
            return
        if data == "cab:ig:roadmap":
            await query.answer()
            await query.edit_message_text(
                _roadmap_text(), parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← К Instagram", callback_data="cab:ig")]])
            )
            return
        if data == "cab:ig:mind":
            await query.answer()
            await query.edit_message_text(
                _mind_text(), parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← К Instagram", callback_data="cab:ig")]])
            )
            return
        if data == "cab:ig:metrics":
            await query.answer()
            await query.edit_message_text(_metrics_text(), parse_mode="HTML", reply_markup=_metrics_markup())
            return
        if data == "cab:ig:metrics:add":
            await query.answer()
            context.user_data["instagram_metrics_waiting"] = True
            await query.message.reply_text(
                "📊 Пришли <b>6 значений через пробел</b>:\n\n"
                "подписчики  просмотры  визиты_профиля  переходы_по_ссылке  заявки  продажи\n\n"
                "Если цифры нет — поставь <b>-</b>.\n"
                "Пример: <code>640 1200 85 17 3 1</code>",
                parse_mode="HTML",
            )
            return
        return await previous_callback(update, context)
    live23.cabinet_callback = cabinet_callback_with_instagram

    previous_text_router = live7.student_text_router
    async def text_router_with_instagram_metrics(update, context):
        if (
            update.message and update.message.text
            and update.effective_chat.type == "private"
            and bot.user_is_admin(update)
            and context.user_data.get("instagram_metrics_waiting")
        ):
            tokens = update.message.text.strip().split()
            if len(tokens) != 6:
                await update.message.reply_text("Нужно ровно 6 значений. Например: 640 1200 85 17 3 1. Если чего-то нет — поставь -")
                return
            try:
                values = [_parse_metric_token(token) for token in tokens]
            except Exception:
                await update.message.reply_text("Не смогла разобрать цифры. Используй целые числа или -")
                return
            context.user_data.pop("instagram_metrics_waiting", None)
            _save_metrics(values)
            await update.message.reply_text("✅ Метрики сохранены. Сравниваем раз в неделю, а не после каждого Reel.")
            return
        return await previous_text_router(update, context)
    live7.student_text_router = text_router_with_instagram_metrics

    _INSTALLED = True
    print("Instagram 90-day return system ready: starts 2026-09-13", flush=True)
