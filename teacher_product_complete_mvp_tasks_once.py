"""One-time completion of the three PREPODMIN MVP planning tasks requested on 2026-09-18."""
from datetime import datetime

import teacher_product_mvp as base
import teacher_product_tasks as tasks

TARGETS = (
    (
        "Спроектировать модуль «Расписание и переносы» как ядро продукта: создание занятий, перенос, отмена, свободные окна и уведомления ученикам",
        "2026-09-16",
        "10:00",
    ),
    (
        "Утвердить состав MVP универсального бота: курсы, группы, расписание, ученики, ДЗ, посещаемость, напоминания, отчёты и задачи",
        "2026-09-17",
        "10:00",
    ),
    (
        "Спроектировать режимы сообщений ученикам: автоматически по правилам / сначала черновик / только вручную / полностью выключено",
        "2026-09-18",
        "10:00",
    ),
)


def run():
    tasks.ensure_tables()
    now = datetime.utcnow().isoformat()
    completed = 0
    matched = []
    with base.db() as conn:
        for title, due_date, due_time in TARGETS:
            rows = conn.execute(
                """
                SELECT id,teacher_telegram_user_id,title,due_date,due_time
                FROM teacher_tasks
                WHERE completed=0
                  AND trim(title)=?
                  AND due_date=?
                  AND coalesce(due_time,'')=?
                """,
                (title, due_date, due_time),
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    UPDATE teacher_tasks
                    SET completed=1,completed_at=?
                    WHERE id=? AND teacher_telegram_user_id=? AND completed=0
                    """,
                    (now, int(row["id"]), int(row["teacher_telegram_user_id"])),
                )
                completed += 1
                matched.append(int(row["id"]))
        conn.commit()
    print(
        f"PREPODMIN one-time task completion: completed={completed} ids={matched}",
        flush=True,
    )
    return completed
