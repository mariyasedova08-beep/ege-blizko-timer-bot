"""Dynamic public trainer hub for subscribers of the EGE BLIZKO Telegram channel.

The public menu is driven by weekly_trainer_catalog, so a newly registered trainer
appears automatically without editing this module. Maria can show/hide trainers
for channel subscribers from the existing admin trainer menu.
"""

import json
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90

bot = live90.bot
live79 = live90.live79
live7 = live79.live7
live23 = live79.live23
live41 = live79.live41

CHANNEL_USERNAME = "@egeblizko_chem"
CHANNEL_URL = "https://t.me/egeblizko_chem"
PUBLIC_START_ARGS = {"trainers", "trainer", "тренажеры", "тренажёры"}

# Existing trainers use these session tables. Future trainers are auto-detected
# as <code>_sessions when they follow the same naming convention.
SPECIAL_STATS_TABLES = {
    "trivial": "trivial_sessions",
    "acid": "acid_sessions",
    "metals": "metals_sessions",
    "nonmetals": "nonmetals_sessions",
    "oxides": "oxides_sessions",
    "oxideprops": "oxide_properties_sessions",
}

_INSTALLED = False
_previous_start_router = None
_previous_trivial_callback = None
_previous_cabinet_callback = None


def ensure_tables():
    live41.ensure_weekly_report_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channel_trainer_users (
                telegram_user_id INTEGER PRIMARY KEY,
                audience TEXT NOT NULL CHECK(audience IN ('channel','student')),
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                entry_count INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS channel_trainer_opens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                trainer_key TEXT NOT NULL,
                opened_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS channel_trainer_catalog_settings (
                code TEXT PRIMARY KEY,
                public_active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_channel_trainer_opens_user
            ON channel_trainer_opens(telegram_user_id, opened_at);

            CREATE INDEX IF NOT EXISTS idx_channel_trainer_opens_key
            ON channel_trainer_opens(trainer_key, opened_at);
            """
        )
        conn.commit()


def _table_exists(conn, name):
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (str(name),),
        ).fetchone()
    )


def _catalog_rows(include_hidden=False):
    """Return registered trainers; public visibility defaults to ON."""
    ensure_tables()
    where = "WHERE c.active=1"
    if not include_hidden:
        where += " AND coalesce(s.public_active,1)=1"
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            f"""
            SELECT
                c.code,
                c.title,
                c.start_param,
                c.sort_order,
                coalesce(s.public_active,1) AS public_active
            FROM weekly_trainer_catalog c
            LEFT JOIN channel_trainer_catalog_settings s ON s.code=c.code
            {where}
            ORDER BY c.sort_order,c.title
            """
        ).fetchall()


def _catalog_item(arg):
    value = str(arg or "").strip().lower()
    if not value:
        return None
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT
                c.code,
                c.title,
                c.start_param,
                c.sort_order,
                coalesce(s.public_active,1) AS public_active
            FROM weekly_trainer_catalog c
            LEFT JOIN channel_trainer_catalog_settings s ON s.code=c.code
            WHERE c.active=1
              AND (lower(c.start_param)=? OR lower(c.code)=?)
            LIMIT 1
            """,
            (value, value),
        ).fetchone()


def _set_public_active(code, active):
    ensure_tables()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO channel_trainer_catalog_settings(code,public_active,updated_at)
            VALUES(?,?,?)
            ON CONFLICT(code) DO UPDATE SET
                public_active=excluded.public_active,
                updated_at=excluded.updated_at
            """,
            (str(code), 1 if active else 0, now),
        )
        conn.commit()


def _is_course_student(user_id):
    uid = int(user_id)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        if _table_exists(conn, "students"):
            cols = {row[1] for row in conn.execute("PRAGMA table_info(students)").fetchall()}
            if "telegram_user_id" in cols:
                active_clause = " AND active=1" if "active" in cols else ""
                row = conn.execute(
                    f"SELECT 1 FROM students WHERE telegram_user_id=?{active_clause} LIMIT 1",
                    (uid,),
                ).fetchone()
                if row:
                    return True

        if _table_exists(conn, "individual_students"):
            cols = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(individual_students)"
                ).fetchall()
            }
            if "telegram_user_id" in cols:
                active_clause = " AND active=1" if "active" in cols else ""
                row = conn.execute(
                    f"""
                    SELECT 1 FROM individual_students
                    WHERE telegram_user_id=?{active_clause}
                    LIMIT 1
                    """,
                    (uid,),
                ).fetchone()
                if row:
                    return True
    return False


def _record_entry(user_id):
    ensure_tables()
    uid = int(user_id)
    audience = "student" if _is_course_student(uid) else "channel"
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO channel_trainer_users(
                telegram_user_id,audience,first_seen_at,last_seen_at,entry_count
            ) VALUES(?,?,?,?,1)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                audience=excluded.audience,
                last_seen_at=excluded.last_seen_at,
                entry_count=channel_trainer_users.entry_count+1
            """,
            (uid, audience, now, now),
        )
        conn.commit()
    return audience


def _record_open(user_id, trainer_key):
    ensure_tables()
    now = datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO channel_trainer_opens(telegram_user_id,trainer_key,opened_at)
            VALUES(?,?,?)
            """,
            (int(user_id), str(trainer_key), now),
        )
        conn.commit()


async def _subscription_state(context, user_id):
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, int(user_id))
    except Exception as exc:
        print(
            f"Channel trainer membership check failed: {type(exc).__name__}",
            flush=True,
        )
        return None

    status = str(getattr(member, "status", "") or "").lower()
    if status in {"creator", "administrator", "member"}:
        return True
    if status == "restricted" and bool(getattr(member, "is_member", False)):
        return True
    return False


def _subscribe_markup():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💗 Подписаться на ЕГЭ БЛИЗКО", url=CHANNEL_URL)],
            [InlineKeyboardButton("✅ Я подписался", callback_data="triv:channel:check")],
        ]
    )


async def _hub_markup(context):
    me = await context.bot.get_me()
    username = str(me.username or "").strip()
    rows = []
    current = []

    for code, title, start_param, _sort_order, _public_active in _catalog_rows():
        button = InlineKeyboardButton(
            str(title),
            url=f"https://t.me/{username}?start={start_param}",
        )
        current.append(button)
        if len(current) == 2:
            rows.append(current)
            current = []

    if current:
        rows.append(current)

    rows.extend(
        [
            [InlineKeyboardButton("📊 Моя статистика", callback_data="triv:channel:stats")],
            [InlineKeyboardButton("💗 Канал ЕГЭ БЛИЗКО", url=CHANNEL_URL)],
        ]
    )
    return InlineKeyboardMarkup(rows)


async def _show_gate(update, edit=False):
    text = (
        "🧪 <b>Тренажёры ЕГЭ БЛИЗКО</b>\n\n"
        "Бесплатные тренажёры доступны подписчикам канала 💗\n\n"
        "Подпишись на канал и нажми «✅ Я подписался»."
    )
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=_subscribe_markup()
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=_subscribe_markup()
        )


async def _show_hub(update, context, edit=False):
    user = update.effective_user
    if not user:
        return

    audience = _record_entry(user.id)
    visible_count = len(_catalog_rows())
    text = (
        "🧪 <b>Тренажёры ЕГЭ БЛИЗКО</b>\n\n"
        f"Сейчас доступно: <b>{visible_count}</b>.\n"
        "Выбирай тему и тренируйся столько, сколько нужно.\n"
        "Ошибки и личная статистика сохраняются 💗"
    )
    if audience == "channel":
        text += "\n\nТы вошёл как подписчик канала."

    markup = await _hub_markup(context)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=markup
        )


async def _require_subscription(update, context, edit=False):
    state = await _subscription_state(context, update.effective_user.id)
    if state is True:
        return True
    if state is False:
        await _show_gate(update, edit=edit)
        return False

    text = (
        "Не получилось проверить подписку прямо сейчас. "
        "Нажми «Проверить ещё раз» через несколько секунд."
    )
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Проверить ещё раз", callback_data="triv:channel:check")]]
    )
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)
    return False


def _stats_table_for(conn, code):
    special = SPECIAL_STATS_TABLES.get(str(code))
    if special and _table_exists(conn, special):
        return special
    candidate = f"{code}_sessions"
    if _table_exists(conn, candidate):
        return candidate
    return None


def _user_stats_text(user_id):
    uid = int(user_id)
    lines = ["📊 <b>Моя статистика</b>", ""]
    total_sessions = total_questions = total_correct = 0

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for code, title, _start_param, _sort_order, _public_active in _catalog_rows():
            table = _stats_table_for(conn, code)
            if not table:
                continue
            row = conn.execute(
                f"""
                SELECT COUNT(*),COALESCE(SUM(total),0),COALESCE(SUM(correct),0)
                FROM {table}
                WHERE telegram_user_id=? AND finished_at IS NOT NULL
                """,
                (uid,),
            ).fetchone()
            sessions, questions, correct = (
                int(row[0] or 0),
                int(row[1] or 0),
                int(row[2] or 0),
            )
            total_sessions += sessions
            total_questions += questions
            total_correct += correct
            pct = round(correct * 100 / questions) if questions else 0
            lines.append(f"{title}: {sessions} трен. · {pct}%")

    total_pct = round(total_correct * 100 / total_questions) if total_questions else 0
    lines.extend(
        [
            "",
            f"Всего тренировок: <b>{total_sessions}</b>",
            f"Ответов: <b>{total_correct}/{total_questions}</b>",
            f"Общая точность: <b>{total_pct}%</b>",
        ]
    )
    return "\n".join(lines)


def _admin_channel_stats_text():
    ensure_tables()
    now = datetime.now(bot.TIMEZONE)
    prefix = f"{now.year:04d}-{now.month:02d}%"
    lines = [
        "📣 <b>Тренажёры из канала</b>",
        f"{now.strftime('%m.%Y')}",
        "",
    ]

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        channel_users = int(
            conn.execute(
                "SELECT COUNT(*) FROM channel_trainer_users WHERE audience='channel'"
            ).fetchone()[0]
            or 0
        )
        month_users = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM channel_trainer_users
                WHERE audience='channel' AND last_seen_at LIKE ?
                """,
                (prefix,),
            ).fetchone()[0]
            or 0
        )
        opens = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM channel_trainer_opens o
                JOIN channel_trainer_users u ON u.telegram_user_id=o.telegram_user_id
                WHERE u.audience='channel' AND o.opened_at LIKE ?
                """,
                (prefix,),
            ).fetchone()[0]
            or 0
        )

        lines.extend(
            [
                f"Подписчиков, вошедших в тренажёры: <b>{channel_users}</b>",
                f"Активных в этом месяце: <b>{month_users}</b>",
                f"Открытий тренажёров за месяц: <b>{opens}</b>",
                "",
                "<b>По темам:</b>",
            ]
        )

        total_sessions = total_q = total_correct = 0
        for code, title, _start_param, _sort_order, _public_active in _catalog_rows(
            include_hidden=True
        ):
            table = _stats_table_for(conn, code)
            if not table:
                continue
            row = conn.execute(
                f"""
                SELECT COUNT(*),COALESCE(SUM(s.total),0),COALESCE(SUM(s.correct),0)
                FROM {table} s
                JOIN channel_trainer_users u
                  ON u.telegram_user_id=s.telegram_user_id
                 AND u.audience='channel'
                WHERE s.finished_at IS NOT NULL AND s.finished_at LIKE ?
                """,
                (prefix,),
            ).fetchone()
            sessions, q, correct = (
                int(row[0] or 0),
                int(row[1] or 0),
                int(row[2] or 0),
            )
            total_sessions += sessions
            total_q += q
            total_correct += correct
            pct = round(correct * 100 / q) if q else 0
            lines.append(f"{title}: {sessions} трен. · {pct}%")

        pct = round(total_correct * 100 / total_q) if total_q else 0
        lines.extend(
            [
                "",
                f"Завершено тренировок за месяц: <b>{total_sessions}</b>",
                f"Решено вопросов: <b>{total_q}</b>",
                f"Средняя точность: <b>{pct}%</b>",
            ]
        )

    return "\n".join(lines)


def _admin_train_menu_markup():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🧪 Кислоты", callback_data="cab:acid"),
                InlineKeyboardButton("🧫 Тривиальные", callback_data="cab:trivial"),
            ],
            [
                InlineKeyboardButton("⚙️ Металлы", callback_data="cab:metals"),
                InlineKeyboardButton("🧪 Оксиды", callback_data="cab:oxides"),
            ],
            [InlineKeyboardButton("⚛️ Неметаллы", callback_data="cab:nonmetals")],
            [InlineKeyboardButton("📣 Подписчики канала", callback_data="cab:channeltrainers")],
            [InlineKeyboardButton("⚙️ Каталог для канала", callback_data="cab:channelcatalog")],
            [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
        ]
    )


def _admin_catalog_markup():
    rows = []
    for code, title, _start_param, _sort_order, public_active in _catalog_rows(
        include_hidden=True
    ):
        icon = "✅" if int(public_active or 0) else "⛔"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} {title}",
                    callback_data=f"cab:channeltoggle:{code}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("← К тренажёрам", callback_data="cab:trainmenu")])
    return InlineKeyboardMarkup(rows)


def _admin_catalog_text():
    visible = sum(
        1
        for _code, _title, _start, _sort, active in _catalog_rows(
            include_hidden=True
        )
        if int(active or 0)
    )
    total = len(_catalog_rows(include_hidden=True))
    return (
        "⚙️ <b>Каталог тренажёров для канала</b>\n\n"
        f"В канале показывается: <b>{visible}/{total}</b>.\n\n"
        "Нажми на тренажёр, чтобы скрыть или вернуть его.\n"
        "Новые тренажёры, зарегистрированные в ЕГЭ БЛИЗКО, "
        "появляются здесь автоматически."
    )


async def start_router(update, context):
    if not update.effective_chat or update.effective_chat.type != "private":
        await _previous_start_router(update, context)
        return

    arg = context.args[0].lower() if context.args else ""
    if arg in PUBLIC_START_ARGS:
        if await _require_subscription(update, context, edit=False):
            await _show_hub(update, context, edit=False)
        return

    trainer = _catalog_item(arg)
    if trainer and not _is_course_student(update.effective_user.id):
        code, title, _start_param, _sort_order, public_active = trainer
        if not int(public_active or 0):
            await update.effective_message.reply_text(
                f"{title} сейчас временно скрыт из бесплатного каталога.",
                reply_markup=InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton(
                            "🧪 Открыть каталог",
                            callback_data="triv:channel:menu",
                        )
                    ]]
                ),
            )
            return
        if not await _require_subscription(update, context, edit=False):
            return
        _record_entry(update.effective_user.id)
        _record_open(update.effective_user.id, code)

    await _previous_start_router(update, context)


async def trivial_callback(update, context):
    query = update.callback_query
    data = str(query.data or "") if query else ""

    if data == "triv:channel:check":
        await query.answer()
        if await _require_subscription(update, context, edit=True):
            await _show_hub(update, context, edit=True)
        return

    if data == "triv:channel:menu":
        await query.answer()
        if await _require_subscription(update, context, edit=True):
            await _show_hub(update, context, edit=True)
        return

    if data == "triv:channel:stats":
        await query.answer()
        if not await _require_subscription(update, context, edit=True):
            return
        await query.edit_message_text(
            _user_stats_text(update.effective_user.id),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("← К тренажёрам", callback_data="triv:channel:menu")]]
            ),
        )
        return

    await _previous_trivial_callback(update, context)


async def cabinet_callback(update, context):
    query = update.callback_query
    if query and update.effective_chat.type == "private" and bot.user_is_admin(update):
        data = str(query.data or "")

        if data == "cab:trainmenu":
            await query.answer()
            await query.edit_message_text(
                "🧪 <b>Тренажёры</b>\n\nВыбирай статистику:",
                parse_mode="HTML",
                reply_markup=_admin_train_menu_markup(),
            )
            return

        if data == "cab:channeltrainers":
            await query.answer()
            await query.edit_message_text(
                _admin_channel_stats_text(),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("← К тренажёрам", callback_data="cab:trainmenu")]]
                ),
            )
            return

        if data == "cab:channelcatalog":
            await query.answer()
            await query.edit_message_text(
                _admin_catalog_text(),
                parse_mode="HTML",
                reply_markup=_admin_catalog_markup(),
            )
            return

        if data.startswith("cab:channeltoggle:"):
            code = data.rsplit(":", 1)[-1]
            item = next(
                (
                    row
                    for row in _catalog_rows(include_hidden=True)
                    if str(row[0]) == code
                ),
                None,
            )
            if not item:
                await query.answer("Тренажёр уже не найден.", show_alert=True)
                return
            new_active = not bool(int(item[4] or 0))
            _set_public_active(code, new_active)
            await query.answer("Включён" if new_active else "Скрыт")
            await query.edit_message_text(
                _admin_catalog_text(),
                parse_mode="HTML",
                reply_markup=_admin_catalog_markup(),
            )
            return

    await _previous_cabinet_callback(update, context)


def _startup_selfcheck():
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("Channel trainers selfcheck: BOT_TOKEN missing", flush=True)
        return

    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=15
        ) as response:
            me = json.load(response)
        if not me.get("ok"):
            print("Channel trainers selfcheck: getMe failed", flush=True)
            return

        bot_id = int(me["result"]["id"])
        username = str(me["result"].get("username") or "")
        query = urllib.parse.urlencode(
            {"chat_id": CHANNEL_USERNAME, "user_id": bot_id}
        )
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getChatMember?{query}", timeout=15
        ) as response:
            membership = json.load(response)

        catalog = _catalog_rows(include_hidden=True)
        if membership.get("ok"):
            status = membership["result"].get("status")
            print(
                f"Channel trainers ready: channel={CHANNEL_USERNAME} "
                f"bot=@{username} status={status} catalog={len(catalog)} "
                f"public_start=trainers",
                flush=True,
            )
        else:
            print(
                f"Channel trainers selfcheck failed for {CHANNEL_USERNAME}",
                flush=True,
            )
    except Exception as exc:
        # Never print exception text: urllib errors may echo a URL containing
        # the bot token.
        print(
            f"Channel trainers selfcheck error: {type(exc).__name__}",
            flush=True,
        )


def install():
    global _INSTALLED
    global _previous_start_router, _previous_trivial_callback, _previous_cabinet_callback

    if _INSTALLED:
        return

    ensure_tables()

    _previous_start_router = live7.start_router
    _previous_trivial_callback = live7.trivial_callback
    _previous_cabinet_callback = live23.cabinet_callback

    live7.start_router = start_router
    live7.trivial_callback = trivial_callback
    live23.cabinet_callback = cabinet_callback

    _startup_selfcheck()
    _INSTALLED = True
