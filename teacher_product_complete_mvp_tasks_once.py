"""One-time completion of the three PREPODMIN MVP planning tasks requested on 2026-09-18."""
from datetime import datetime

import teacher_product_mvp as base
import teacher_product_tasks as tasks

TARGETS = (
    (
        "Спроектировать модуль «Расписание и переносы» как ядро продукта:",
        "2026-09-16",
    ),
    (
        "Утвердить состав MVP универсального бота:",
        "2026-09-17",
    ),
    (
        "Спроектировать режимы сообщений ученикам:",
        "2026-09-18",
    ),
)


def run():
    tasks.ensure_tables()
    now = datetime.utcnow().isoformat()
    completed = 0
    matched = []
    with base.db() as conn:
        for title_prefix, due_date in TARGETS:
            rows = conn.execute(
                """
                SELECT id,teacher_telegram_user_id,title,due_date,due_time
                FROM teacher_tasks
                WHERE completed=0
                  AND title LIKE ?
                  AND due_date=?
                """,
                (title_prefix + "%", due_date),
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
