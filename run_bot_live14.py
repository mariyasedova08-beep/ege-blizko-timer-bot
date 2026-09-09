import json
import sqlite3

import run_bot_live13

live13 = run_bot_live13
live10 = live13.live10
bot = live10.bot


def _score_text(value):
    if value is None:
        return "—"
    value = float(value)
    return str(int(value)) if value.is_integer() else str(round(value, 1)).replace(".", ",")


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def probnik_stats_text(event_name=None):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        if event_name:
            row = conn.execute(
                """
                SELECT event_name, event_date
                FROM probnik_results
                WHERE lower(event_name) = lower(?)
                ORDER BY synced_at DESC LIMIT 1
                """,
                (event_name,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT event_name, event_date
                FROM probnik_results
                ORDER BY substr(event_date, 7, 4) DESC,
                         substr(event_date, 4, 2) DESC,
                         substr(event_date, 1, 2) DESC
                LIMIT 1
                """
            ).fetchone()

        if not row:
            return "📝 Результатов пробников пока нет. Сначала синхронизируй Google-таблицу."

        name, date_text = row
        results = conn.execute(
            """
            SELECT student_name, primary_score, secondary_score, tasks_json
            FROM probnik_results
            WHERE event_name = ? AND event_date = ?
            ORDER BY CASE WHEN secondary_score IS NULL THEN 1 ELSE 0 END,
                     secondary_score DESC, student_name
            """,
            (name, date_text),
        ).fetchall()

    # Правило курса: если вторичный балл не заполнен, ученик пробник не писал.
    written = [r for r in results if r[2] is not None]
    not_written = [r for r in results if r[2] is None]
    scores = [float(r[2]) for r in written]
    avg = round(sum(scores) / len(scores), 1) if scores else None

    lines = [
        f"📝 {name}",
        f"📅 {date_text}",
        "",
        f"Написали: {len(written)}",
    ]

    if not_written:
        lines.append(f"Не писали: {len(not_written)}")

    if avg is not None:
        lines.append(f"Средний вторичный балл: {_score_text(avg)}")
    else:
        lines.append("Средний вторичный балл: —")

    if written:
        best = max(written, key=lambda r: r[2])
        lines.append(f"Лучший результат: {best[0]} — {_score_text(best[2])}")

    # Проблемные задания считаем только среди тех, кто реально писал пробник.
    task_stats = {str(i): {"answered": 0, "zero": 0} for i in range(1, 35)}
    for _, _, _, tasks_json in written:
        try:
            tasks = json.loads(tasks_json or "{}")
        except Exception:
            tasks = {}
        for task, raw_value in tasks.items():
            if task not in task_stats:
                continue
            score = _num(raw_value)
            if score is None:
                continue
            task_stats[task]["answered"] += 1
            if score == 0:
                task_stats[task]["zero"] += 1

    weak = []
    for task, stat in task_stats.items():
        if stat["answered"] == 0 or stat["zero"] == 0:
            continue
        zero_pct = round(stat["zero"] * 100 / stat["answered"])
        weak.append((zero_pct, stat["zero"], int(task), stat["answered"]))

    weak.sort(key=lambda item: (-item[0], -item[1], item[2]))

    if weak:
        lines.extend(["", "🧪 Самые проблемные задания:"])
        for zero_pct, zero_count, task, answered in weak[:5]:
            lines.append(
                f"• №{task} — {zero_pct}% получили 0 баллов ({zero_count} из {answered})"
            )

    return "\n".join(lines)


live10.probnik_stats_text = probnik_stats_text


if __name__ == "__main__":
    live10.main()
