"""One-time read-only anonymous report for the teacher research survey."""
import json
import os
import sqlite3

DB = os.getenv("COREAPP_DB_PATH", "/data/coreapp.db")

LABELS = {
    "work_format": {
        "individual": "Индивидуально",
        "groups": "В группах",
        "institution": "В школе или учебном центре",
        "mixed": "Индивидуально и в группах",
    },
    "student_count": {
        "1_10": "1–10",
        "11_30": "11–30",
        "31_60": "31–60",
        "61_plus": "Больше 60",
    },
    "main_system": {
        "spreadsheets": "Google Таблицы или Excel",
        "notebook": "Блокнот или заметки",
        "crm": "CRM или сервис преподавателя",
        "many_places": "В нескольких разных местах",
    },
    "admin_time": {
        "under_1": "Меньше часа",
        "1_3": "1–3 часа",
        "3_5": "3–5 часов",
        "over_5": "Больше 5 часов",
    },
    "priority_function": {
        "payments": "Оплаты и долги",
        "schedule": "Расписание и переносы",
        "homework": "Домашние задания",
        "attendance": "Посещаемость",
        "reminders": "Напоминания ученикам",
        "reports": "Отчёты и результаты",
    },
    "reminder_mode": {
        "approval": "Сначала показать мне черновик",
        "automatic": "Автоматически по моим правилам",
        "manual": "Только после моего нажатия",
        "none": "Мне не нужны рассылки",
    },
    "monthly_price": {
        "free": "Только бесплатно",
        "up_to_500": "До 500 ₽",
        "500_1000": "500–1 000 ₽",
        "1000_2000": "1 000–2 000 ₽",
        "over_2000": "Больше 2 000 ₽",
    },
    "pilot": {
        "yes": "Да, хочу участвовать",
        "maybe": "Возможно, расскажите подробнее",
        "no": "Нет",
    },
}
ORDER = [
    "work_format", "student_count", "main_system", "admin_time",
    "priority_function", "reminder_mode", "monthly_price", "pilot",
]


def decode_codes(question_key, stored):
    if not stored:
        return []
    try:
        val = json.loads(stored)
    except Exception:
        val = stored
    codes = val if isinstance(val, list) else [val]
    result = []
    for code in codes:
        if not isinstance(code, str):
            continue
        items = ["individual", "groups"] if question_key == "work_format" and code == "mixed" else [code]
        for item in items:
            if item not in result:
                result.append(item)
    return result


def safe_text(value):
    return " ".join(str(value or "").split())[:500]

try:
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        started = conn.execute("SELECT COUNT(*) FROM teacher_survey_sessions").fetchone()[0]
        completed = conn.execute("SELECT COUNT(*) FROM teacher_survey_sessions WHERE completed_at IS NOT NULL").fetchone()[0]
        incomplete = started - completed
        print(f"TSR SUMMARY started={started} completed={completed} incomplete={incomplete} completion_rate={(completed*100/started if started else 0):.1f}", flush=True)

        progress = conn.execute(
            "SELECT current_question, COUNT(*) c FROM teacher_survey_sessions WHERE completed_at IS NULL GROUP BY current_question ORDER BY c DESC"
        ).fetchall()
        for row in progress:
            print(f"TSR INCOMPLETE current_question={row['current_question'] or 'none'} count={row['c']}", flush=True)

        completed_ids = [r[0] for r in conn.execute("SELECT telegram_user_id FROM teacher_survey_sessions WHERE completed_at IS NOT NULL").fetchall()]
        if completed_ids:
            placeholders = ",".join("?" for _ in completed_ids)
            rows = conn.execute(
                f"SELECT question_key, answer_code, answer_text FROM teacher_survey_answers WHERE telegram_user_id IN ({placeholders}) ORDER BY question_key, id",
                completed_ids,
            ).fetchall()
        else:
            rows = []

        by_key = {}
        for row in rows:
            by_key.setdefault(row["question_key"], []).append(row)

        for key in ORDER:
            counts = {code: 0 for code in LABELS[key] if not (key == "work_format" and code == "mixed")}
            respondent_count = 0
            for row in by_key.get(key, []):
                codes = decode_codes(key, row["answer_code"])
                if codes:
                    respondent_count += 1
                for code in codes:
                    counts[code] = counts.get(code, 0) + 1
            print(f"TSR QUESTION key={key} respondents={respondent_count}", flush=True)
            for code, count in sorted(counts.items(), key=lambda x: (-x[1], LABELS[key].get(x[0], x[0]))):
                pct = count * 100 / respondent_count if respondent_count else 0
                print(f"TSR OPTION key={key} code={code} label={LABELS[key].get(code, code)} count={count} pct={pct:.1f}", flush=True)

        for key in ("subject", "biggest_routine"):
            texts = [safe_text(row["answer_text"]) for row in by_key.get(key, []) if safe_text(row["answer_text"])]
            print(f"TSR TEXTS key={key} count={len(texts)}", flush=True)
            for i, text in enumerate(texts, 1):
                print(f"TSR TEXT key={key} n={i} value={text}", flush=True)
except Exception as exc:
    print(f"TSR ERROR {type(exc).__name__}: {exc}", flush=True)
