"""Public trainer hub for subscribers of the EGE BLIZKO Telegram channel.

The channel is only an entry point. Exercises stay inside the existing student bot.
Paid-course cabinets and homework are not exposed here.
"""

import json
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import run_bot_live90 as live90
import nonmetals_trainer
import oxide_properties_trainer

bot = live90.bot
live79 = live90.live79
live7 = live79.live7
live17 = live79.live17
live23 = live79.live23
live48 = live79.live48
live60 = live79.live60

CHANNEL_USERNAME = "@egeblizko_chem"
CHANNEL_URL = "https://t.me/egeblizko_chem"
PUBLIC_START_ARGS = {"trainers", "trainer", "тренажеры", "тренажёры"}

TRAINERS = {
    "trivial": ("🧫 Тривиальные названия", "trivial_sessions"),
    "acid": ("🧪 Кислоты и остатки", "acid_sessions"),
    "metals": ("⚙️ Металлы", "metals_sessions"),
    "nonmetals": ("⚛️ Неметаллы", "nonmetals_sessions"),
    "oxides": ("🧪 Оксиды", "oxides_sessions"),
    "oxideprops": ("🧬 Свойства оксидов", "oxide_properties_sessions"),
}

_INSTALLED = False
_previous_start_router = None
_previous_trivial_callback = None
_previous_cabinet_callback = None


def ensure_tables():
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


def _is_course_student(user_id):
    uid = int(user_id)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        if _table_exists(conn, "students"):
            cols = {row[1] for row in conn.execute("PRAGMA table_info(students)").fetchall()}
            if "telegram_user_id" in cols:
                row = conn.execute(
                    "SELECT 1 FROM students WHERE telegram_user_id=? AND coalesce(active,1)=1 LIMIT 1",
                    (uid,),
                ).fetchone()
                if row:
                    return True
        if _table_exists(conn, "individual_students"):
            cols = {row[1] for row in conn.execute("PRAGMA table_info(individual_students)").fetchall()}
            if "telegram_user_id" in cols:
                row = conn.execute(
                    "SELECT 1 FROM individual_students WHERE telegram_user_id=? AND coalesce(active,1)=1 LIMIT 1",
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
            f"Channel trainer membership check failed: {type(exc).__name__}: {exc}",
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


def _hub_markup():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚙️ Металлы", callback_data="triv:channel:open:metals"),
                InlineKeyboardButton("⚛️ Неметаллы", callback_data="triv:channel:open:nonmetals"),
            ],
            [
                InlineKeyboardButton("🧪 Оксиды", callback_data="triv:channel:open:oxides"),
                InlineKeyboardButton("🧬 Свойства оксидов", callback_data="triv:channel:open:oxideprops"),
            ],
            [
                InlineKeyboardButton("🧪 Кислоты", callback_data="triv:channel:open:acid"),
                InlineKeyboardButton("🧫 Тривиальные", callback_data="triv:channel:open:trivial"),
            ],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="triv:channel:stats")],
            [InlineKeyboardButton("💗 Канал ЕГЭ БЛИЗКО", url=CHANNEL_URL)],
        ]
    )


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
    text = (
        "🧪 <b>Тренажёры ЕГЭ БЛИЗКО</b>\n\n"
        "Выбирай тему и тренируйся столько, сколько нужно.\n"
        "Ошибки и личная статистика сохраняются 💗"
    )
    if audience == "channel":
        text += "\n\nТы вошёл как подписчик канала."
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=_hub_markup()
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode="HTML", reply_markup=_hub_markup()
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


async def _open_trainer(update, context, trainer_key):
    if trainer_key not in TRAINERS:
        return
    if not await _require_subscription(update, context, edit=True):
        return

    _record_open(update.effective_user.id, trainer_key)
    if trainer_key == "trivial":
        await live7.show_trivial_menu(update, context, edit=True)
    elif trainer_key == "acid":
        await live17.show_acid_menu(update, context, edit=True)
    elif trainer_key == "metals":
        await live48.show_metals_menu(update, context, edit=True)
    elif trainer_key == "nonmetals":
        await nonmetals_trainer.show_nonmetals_menu(update, context, edit=True)
    elif trainer_key == "oxides":
        await live60.show_oxides_menu(update, context, edit=True)
    elif trainer_key == "oxideprops":
        await oxide_properties_trainer.show_menu(update, context, edit=True)


def _user_stats_text(user_id):
    uid = int(user_id)
    lines = ["📊 <b>Моя статистика</b>", ""]
    total_sessions = total_questions = total_correct = 0

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for key, (label, table) in TRAINERS.items():
            if not _table_exists(conn, table):
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
            lines.append(f"{label}: {sessions} трен. · {pct}%")

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
        for key, (label, table) in TRAINERS.items():
            if not _table_exists(conn, table):
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
            sessions, q, correct = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
            total_sessions += sessions
            total_q += q
            total_correct += correct
            pct = round(correct * 100 / q) if q else 0
            lines.append(f"{label}: {sessions} трен. · {pct}%")

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
            [InlineKeyboardButton("← В кабинет", callback_data="cab:back")],
        ]
    )


async def start_router(update, context):
    if (
        update.effective_chat
        and update.effective_chat.type == "private"
        and context.args
        and context.args[0].lower() in PUBLIC_START_ARGS
    ):
        if await _require_subscription(update, context, edit=False):
            await _show_hub(update, context, edit=False)
        return
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

    if data.startswith("triv:channel:open:"):
        await query.answer()
        trainer_key = data.rsplit(":", 1)[-1]
        await _open_trainer(update, context, trainer_key)
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
        if membership.get("ok"):
            status = membership["result"].get("status")
            print(
                f"Channel trainers ready: channel={CHANNEL_USERNAME} "
                f"bot=@{username} status={status} public_start=trainers",
                flush=True,
            )
        else:
            print(
                f"Channel trainers selfcheck failed for {CHANNEL_USERNAME}",
                flush=True,
            )
    except Exception as exc:
        # Do not include exception text here: urllib errors may echo the request URL,
        # which contains the Telegram bot token.
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
