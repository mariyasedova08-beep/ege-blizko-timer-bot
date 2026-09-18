"""One-time completion of the three PREPODMIN MVP planning tasks requested on 2026-09-18."""
from datetime import datetime

import teacher_product_mvp as base
import teacher_product_tasks as tasks

TARGET_PHRASES = (
    "Расписание и переносы",
    "состав MVP универсального бота",
    "режимы сообщений ученикам",
)


def run():
    tasks.ensure_tables()
    now = datetime.utcnow().isoformat()
    completed = 0
    matched = []
    with base.db() as conn:
        for phrase in TARGET_PHRASES:
            rows = conn.execute(
                """
                SELECT id,teacher_telegram_user_id,title,due_date,due_time,source_text
                FROM teacher_tasks
                WHERE completed=0
                  AND (
                        lower(title) LIKE lower(?)
                     OR lower(coalesce(source_text,'')) LIKE lower(?)
                  )
                """,
                (f"%{phrase}%", f"%{phrase}%"),
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
