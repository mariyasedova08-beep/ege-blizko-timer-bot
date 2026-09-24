"""Small production-volume persistence probe for the PREPADMIN pilot.

Stores only a technical boot counter in the existing SQLite database. No teacher,
student, message, payment, or other product data is read or changed.
"""
from datetime import datetime

import teacher_product_mvp as base


def check():
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pilot_runtime_persistence_probe (
                id INTEGER PRIMARY KEY CHECK(id=1),
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                boot_count INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        row = conn.execute(
            "SELECT boot_count FROM pilot_runtime_persistence_probe WHERE id=1"
        ).fetchone()
        if row is None:
            count = 1
            conn.execute(
                """
                INSERT INTO pilot_runtime_persistence_probe(
                    id,first_seen_at,last_seen_at,boot_count
                ) VALUES(1,?,?,1)
                """,
                (now, now),
            )
        else:
            count = int(row["boot_count"] or 0) + 1
            conn.execute(
                """
                UPDATE pilot_runtime_persistence_probe
                SET last_seen_at=?,boot_count=?
                WHERE id=1
                """,
                (now, count),
            )
        conn.commit()
    if count >= 2:
        print(
            f"PREPADMIN persistence probe ok: /data database survived restart; boot_count={count}",
            flush=True,
        )
    else:
        print(
            "PREPADMIN persistence probe initialized; one more restart will confirm /data persistence",
            flush=True,
        )
    return count
