import json
import sqlite3

import run_bot_live12

live12 = run_bot_live12
live10 = live12.live10
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

    total_students = len(results)
    scored = [r for r in results if r[2] is not None]
    scores = [r[2] for r in scored]
    avg = round(sum(scores) / len(scores), 1) if scores else None

    lines = [
        f"📝 {name}",
        f"📅 {date_text}",
        "",
        f"Написали: {total_students}",
    ]

    if len(scored) != total_students:
        lines.append(f"С заполненным вторичным баллом: {len(scored)} из {total_students}")

    if avg is not None:
        lines.append(f"Средний вторичный балл: {_score_text(avg)}")
    else:
        lines.append("Средний вторичный балл: —")

    if scored:
        best = max(scored, key=lambda r: r[2])
        lines.append(f"Лучший результат: {best[0]} — {_score_text(best[2])}")

    task_stats = {str(i): {"answered": 0, "zero": 0} for i in range(1, 35)}
    for _, _, _, tasks_json in results:
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
        if stat["answered"] == 0:
            continue
        zero_pct = round(stat["zero"] * 100 / stat["answered"])
        weak.append((zero_pct, stat["zero"], int(task), stat["answered"]))

    weak.sort(key=lambda item: (-item[0], -item[1], item[2]))
    weak = [item for item in weak if item[1] > 0]

    if weak:
        lines.extend(["", "🧪 Самые проблемные задания:"])
        for zero_pct, zero_count, task, answered in weak[:5]:
            lines.append(
                f"• №{task} — {zero_pct}% получили 0 баллов ({zero_count} из {answered})"
            )

    return "\n".join(lines)


def student_card_text(query_name):
    query_name = query_name.strip()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT student_name FROM probnik_results ORDER BY student_name"
            ).fetchall()
        ]
        exact = next((n for n in names if n.lower() == query_name.lower()), None)
        if exact is None:
            matches = [n for n in names if query_name.lower() in n.lower()]
            if len(matches) == 1:
                exact = matches[0]
        if exact is None:
            return "Не нашла ученика. Напиши имя как на вкладке Google-таблицы."

        rows = conn.execute(
            """
            SELECT event_name, event_date, primary_score, secondary_score, tasks_json
            FROM probnik_results
            WHERE student_name = ?
            ORDER BY substr(event_date, 7, 4), substr(event_date, 4, 2), substr(event_date, 1, 2)
            """,
            (exact,),
        ).fetchall()

    lines = [f"👩‍🎓 {exact}", ""]
    secondary_scores = []
    task_misses = {str(i): 0 for i in range(1, 35)}

    for event_name, date_text, primary, secondary, tasks_json in rows:
        score_part = f"{_score_text(secondary)} баллов" if secondary is not None else "вторичный балл не заполнен"
        primary_part = f"перв. {_score_text(primary)}" if primary is not None else "перв. —"
        lines.append(f"• {event_name} ({date_text}) — {score_part} [{primary_part}]")

        if secondary is not None:
            secondary_scores.append(float(secondary))

        try:
            tasks = json.loads(tasks_json or "{}")
        except Exception:
            tasks = {}
        for task, raw_value in tasks.items():
            score = _num(raw_value)
            if task in task_misses and score == 0:
                task_misses[task] += 1

    if secondary_scores:
        best = max(secondary_scores)
        avg = sum(secondary_scores) / len(secondary_scores)
        lines.extend([
            "",
            f"🏆 Лучший результат: {_score_text(best)}",
            f"📊 Средний результат: {_score_text(avg)}",
        ])

        if len(secondary_scores) >= 2:
            delta = secondary_scores[-1] - secondary_scores[0]
            if delta > 0:
                arrow = "📈"
                delta_text = f"+{_score_text(delta)}"
            elif delta < 0:
                arrow = "📉"
                delta_text = _score_text(delta)
            else:
                arrow = "➡️"
                delta_text = "0"
            lines.append(f"{arrow} Динамика от первого к последнему: {delta_text}")

    common_misses = [(count, int(task)) for task, count in task_misses.items() if count > 0]
    common_misses.sort(key=lambda item: (-item[0], item[1]))
    if common_misses:
        lines.extend(["", "❌ Чаще всего получает 0 баллов:"])
        for count, task in common_misses[:5]:
            lines.append(f"• №{task} — {count} раз(а)")

    return "\n".join(lines)


def weak_group_text():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute("SELECT tasks_json FROM probnik_results").fetchall()

    if not rows:
        return "🧪 Пока нет данных для анализа слабых заданий."

    stats = {str(i): {"answered": 0, "zero": 0} for i in range(1, 35)}
    for (tasks_json,) in rows:
        try:
            tasks = json.loads(tasks_json or "{}")
        except Exception:
            continue
        for task, raw_value in tasks.items():
            if task not in stats:
                continue
            score = _num(raw_value)
            if score is None:
                continue
            stats[task]["answered"] += 1
            if score == 0:
                stats[task]["zero"] += 1

    ranked = []
    for task, stat in stats.items():
        if not stat["answered"] or not stat["zero"]:
            continue
        pct = round(stat["zero"] * 100 / stat["answered"])
        ranked.append((pct, stat["zero"], int(task), stat["answered"]))

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    lines = ["🧪 Что повторить группе", ""]
    for pct, zero_count, task, answered in ranked[:8]:
        lines.append(f"• №{task} — {pct}% получили 0 баллов ({zero_count} из {answered})")

    if len(lines) == 2:
        lines.append("Нет заданий с нулевыми результатами 💗")

    return "\n".join(lines)


live10.probnik_stats_text = probnik_stats_text
live10.student_card_text = student_card_text
live10.weak_group_text = weak_group_text


if __name__ == "__main__":
    live10.main()
