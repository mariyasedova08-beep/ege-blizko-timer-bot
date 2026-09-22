"""Compact in-bot guide for PREPODMIN teachers."""
from datetime import datetime

from telegram import KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CommandHandler, MessageHandler, filters

import teacher_product_mvp as base


BUTTON = "❓ Инструкция"
_INSTALLED = False


HELP_TEXT = (
    "❓ <b>Краткая инструкция ПРЕПОДМИН</b>\n\n"
    "💗 <b>Главная ПРЕПОДМИН</b> — общий экран: ближайшие занятия, задачи, долги по ДЗ и оплате, зона внимания.\n\n"
    "🚀 <b>Быстрая настройка</b> — первый запуск: добавь учеников/группы, расписание и оплаты.\n\n"
    "👥 <b>Ученики и группы</b> — добавление, архив и состав групп. Для ученика укажи @username → нажми «Отправить приглашение» → ученик нажимает «Запустить». Статус покажет, подключён ли Telegram.\n\n"
    "📅 <b>Расписание</b> — регулярные занятия индивидуально и в группах. Здесь же можно переносить и отменять отдельные занятия.\n\n"
    "📍 <b>Сегодня</b> / 🌅 <b>Завтра</b> — быстрый план занятий и дел на нужный день.\n\n"
    "📚 <b>Домашнее</b> — задай ДЗ ученику или группе, поставь дедлайн и следи за выполнением и просрочками.\n\n"
    "✅ <b>Посещаемость</b> — отмечай, кто был на занятии. Для абонемента проведённый урок уменьшает остаток занятий. Перенос или отмена занятие не списывают.\n\n"
    "💳 <b>Оплаты</b> — сумма, тип оплаты, дата следующей оплаты или абонемент по количеству занятий. Можно видеть долги и остаток уроков.\n\n"
    "🔔 <b>Напоминания</b> — сообщения ученикам о занятиях. Ученик может ответить «Буду» или «Не смогу». Отправка работает только для подключённых Telegram.\n\n"
    "🗓 <b>Мои слоты</b> — настрой рабочие часы; ПРЕПОДМИН покажет занятые и свободные окна и учтёт переносы.\n\n"
    "✅ <b>Задачи</b> / ➕ <b>Быстрая задача</b> — личные рабочие дела с датой и временем; выполненные можно закрывать.\n\n"
    "📊 <b>Отчёты и зона внимания</b> — статистика по ученикам, группам и курсам: посещаемость, ДЗ, оплаты и то, что требует внимания. Удобнее всего смотреть на Главной.\n\n"
    "⚙️ <b>Настройки</b> — выбери режим сообщений ученикам: автоматически, черновик с подтверждением, вручную или полностью выключить.\n\n"
    "💬 <b>Разработчикам</b> — отправь проблему или идею прямо из бота.\n\n"
    "💡 <b>Если не знаешь, с чего начать:</b> открой «🚀 Быстрая настройка» и пройди шаги сверху вниз."
)


def _with_help_button():
    current = getattr(base, "MAIN_KB", None)
    rows = [list(row) for row in getattr(current, "keyboard", ())] if current else []
    cleaned = []
    for row in rows:
        new_row = [
            button for button in row
            if getattr(button, "text", button) != BUTTON
        ]
        if new_row:
            cleaned.append(new_row)
    cleaned.append([KeyboardButton(BUTTON)])
    return ReplyKeyboardMarkup(
        cleaned,
        resize_keyboard=True,
        is_persistent=True,
    )


async def show_help(update, context):
    uid = int(update.effective_user.id)
    teacher = base.teacher(uid)
    if not teacher or not teacher["onboarding_completed_at"]:
        await update.message.reply_text(
            "Сначала пройди короткую настройку через /start — после этого инструкция будет доступна в меню."
        )
        raise ApplicationHandlerStop

    await update.message.reply_text(
        HELP_TEXT,
        parse_mode="HTML",
        reply_markup=base.MAIN_KB,
        disable_web_page_preview=True,
    )
    raise ApplicationHandlerStop


async def _push_help_button(context):
    migration_key = "teacher-help-v1"
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teacher_help_migrations(
                teacher_telegram_user_id INTEGER NOT NULL,
                migration_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                PRIMARY KEY(teacher_telegram_user_id,migration_key)
            )
            """
        )
        teachers = conn.execute(
            """
            SELECT telegram_user_id
            FROM teachers
            WHERE onboarding_completed_at IS NOT NULL
            ORDER BY telegram_user_id
            """
        ).fetchall()
        sent_ids = {
            int(row[0]) for row in conn.execute(
                """
                SELECT teacher_telegram_user_id
                FROM teacher_help_migrations
                WHERE migration_key=?
                """,
                (migration_key,),
            ).fetchall()
        }

    sent = skipped = failed = 0
    for row in teachers:
        uid = int(row["telegram_user_id"])
        if uid in sent_ids:
            skipped += 1
            continue
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    "❓ В ПРЕПОДМИН появилась краткая инструкция по всем основным функциям.\n\n"
                    "Она всегда доступна по кнопке «❓ Инструкция» в меню."
                ),
                reply_markup=base.MAIN_KB,
            )
            with base.db() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO teacher_help_migrations(
                        teacher_telegram_user_id,migration_key,sent_at
                    ) VALUES(?,?,?)
                    """,
                    (uid, migration_key, datetime.utcnow().isoformat()),
                )
                conn.commit()
            sent += 1
        except Exception as exc:
            failed += 1
            print(
                f"PREPODMIN help keyboard push failed uid={uid} error={type(exc).__name__}: {exc}",
                flush=True,
            )

    print(
        f"PREPODMIN help keyboard push: sent={sent} skipped={skipped} failed={failed}",
        flush=True,
    )


def install(app):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    base.MAIN_KB = _with_help_button()
    app.add_handler(CommandHandler("help", show_help), group=-95)
    app.add_handler(
        MessageHandler(filters.Regex(r"^❓ Инструкция$"), show_help),
        group=-95,
    )

    if app.job_queue is not None:
        app.job_queue.run_once(
            _push_help_button,
            when=5,
            name="prepodmin_help_keyboard_push_v1",
        )

    print("PREPODMIN teacher help ready: menu button + /help", flush=True)
