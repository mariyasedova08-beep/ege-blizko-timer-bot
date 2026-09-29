"""Seed the ordered PREPADMIN roadmap into EGE BLIZKO -> Tasks -> Work."""

import sqlite3
from datetime import datetime

import run_bot_live90 as live90

bot = live90.bot
live79 = live90.live79

NO_DATE = "9999-12-31"
REMINDER_TIME = "10:00"

TASKS = (
    ("prepodmin-roadmap-01", "01. ПРЕПАДМИН — проверить финальную навигацию и привести все экраны к единому интерфейсу"),
    ("prepodmin-roadmap-02", "02. ПРЕПАДМИН — полностью протестировать сценарий преподавателя от группы до отчёта"),
    ("prepodmin-roadmap-03", "03. ПРЕПАДМИН — довести быстрый онбординг преподавателя до 10–15 минут"),
    ("prepodmin-roadmap-04", "04. ПРЕПАДМИН — доделать оплаты и абонементы с автоматическим уменьшением занятий"),
    ("prepodmin-roadmap-05", "05. ПРЕПАДМИН — доделать кабинет ученика и понятную отправку доступа ребёнку"),
    ("prepodmin-roadmap-06", "06. ПРЕПАДМИН — проверить материалы: отправка → получение → открыто"),
    ("prepodmin-roadmap-07", "07. ПРЕПАДМИН — довести переносы и отмены занятий до короткого рабочего сценария"),
    ("prepodmin-roadmap-08", "08. ПРЕПАДМИН — доделать напоминания и сообщения ученикам и группам"),
    ("prepodmin-roadmap-09", "09. ПРЕПАДМИН — собрать главный экран: занятия, задачи, долги, зона внимания, быстрые действия"),
    ("prepodmin-roadmap-10", "10. ПРЕПАДМИН — проверить надёжность: рестарты, Railway, health, логи и ошибки Telegram"),
    ("prepodmin-roadmap-11", "11. ПРЕПАДМИН — провести пилот на 3–5 преподавателях"),
    ("prepodmin-roadmap-12", "12. ПРЕПАДМИН — собрать аналитику пилота, исправить затыки и подготовить запуск"),
)


def seed():
    live79.live35.ensure_admin_tasks_table()
    live79.ensure_task_sections()
    now = datetime.now(bot.TIMEZONE).isoformat()
    created = 0
    reused = 0

    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        # Active Work tasks with no date are shown newest first.
        # Insert in reverse so task 01 gets the highest id and appears first.
        for task_key, task_text in reversed(TASKS):
            row = conn.execute(
                "SELECT id FROM admin_tasks WHERE task_key=? LIMIT 1",
                (task_key,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE admin_tasks
                    SET task_text=?, start_date=?, reminder_time=?, task_kind='task'
                    WHERE id=?
                    """,
                    (task_text, NO_DATE, REMINDER_TIME, int(row[0])),
                )
                reused += 1
                continue

            cur = conn.execute(
                """
                INSERT INTO admin_tasks
                    (task_key, task_text, start_date, reminder_time, created_at, task_kind)
                VALUES (?, ?, ?, ?, ?, 'task')
                """,
                (task_key, task_text, NO_DATE, REMINDER_TIME, now),
            )
            if cur.rowcount:
                created += 1

        conn.commit()

    print(
        f"PREPADMIN roadmap tasks ready in EGE BLIZKO Work: "
        f"created={created} reused={reused} total={len(TASKS)}",
        flush=True,
    )
