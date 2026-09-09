import sqlite3
from datetime import datetime

import run_bot_live8

live8 = run_bot_live8
live7 = live8.live7
bot = live7.bot

_original_trivial_stats_command = live7.trivial_stats_command


def teacher_trivial_stats_text():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        summary = conn.execute(
            """
            SELECT COUNT(DISTINCT telegram_user_id), COUNT(*),
                   COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0)
            FROM trivial_sessions
            WHERE finished_at IS NOT NULL
            """
        ).fetchone()

        students = conn.execute(
            """
            SELECT telegram_user_id,
                   MAX(COALESCE(telegram_name, '')),
                   MAX(COALESCE(telegram_username, '')),
                   COUNT(*), COALESCE(SUM(total), 0), COALESCE(SUM(correct), 0),
                   MAX(finished_at)
            FROM trivial_sessions
            WHERE finished_at IS NOT NULL
            GROUP BY telegram_user_id
            ORDER BY MAX(finished_at) DESC
            """
        ).fetchall()

        confusing = conn.execute(
            """
            SELECT item_id, COUNT(*) AS mistakes
            FROM trivial_attempts
            WHERE correct = 0
            GROUP BY item_id
            ORDER BY mistakes DESC, item_id
            LIMIT 7
            """
        ).fetchall()

    users, sessions, total, correct = summary
    percent = round(correct * 100 / total) if total else 0

    lines = [
        "📊 Статистика тренажёра — преподавателю",
        "",
        f"Учеников проходили: {users}",
        f"Завершено тренировок: {sessions}",
        f"Ответов: {correct}/{total}",
        f"Средняя точность: {percent}%",
    ]

    if students:
        lines.extend(["", "👩‍🎓 По ученикам:"])
        for user_id, name, username, count, student_total, student_correct, last_at in students:
            label = name.strip() or (f"@{username}" if username else "Ученик")
            student_percent = round(student_correct * 100 / student_total) if student_total else 0
            unresolved = len(live7.unresolved_error_ids(user_id))
            try:
                last_text = datetime.fromisoformat(last_at).astimezone(bot.TIMEZONE).strftime("%d.%m %H:%M")
            except Exception:
                last_text = "—"
            lines.append(
                f"• {label}: {count} трен., {student_percent}% ({student_correct}/{student_total}), "
                f"ошибок к повторению {unresolved}, последний раз {last_text}"
            )
    else:
        lines.extend(["", "Пока никто не завершил тренировку."])

    if confusing:
        lines.extend(["", "🧪 Чаще всего ошибаются:"])
        for item_id, mistakes in confusing:
            item = live7.TRIVIAL_BY_ID.get(item_id)
            if item:
                lines.append(f"• {item['formula']} — {', '.join(item['names'])}: {mistakes}")

    return "\n".join(lines)


async def teacher_aware_trivial_stats(update, context):
    if update.effective_chat.type != "private":
        return
    if bot.user_is_admin(update):
        text = teacher_trivial_stats_text()
        # Telegram limit is 4096 chars; split conservatively if the class grows.
        while text:
            if len(text) <= 3800:
                await update.message.reply_text(text)
                break
            split_at = text.rfind("\n", 0, 3800)
            if split_at < 1:
                split_at = 3800
            await update.message.reply_text(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return
    await _original_trivial_stats_command(update, context)


live7.trivial_stats_command = teacher_aware_trivial_stats


if __name__ == "__main__":
    live7.main()
