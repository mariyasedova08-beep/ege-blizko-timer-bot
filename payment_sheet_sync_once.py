"""One-time sync of the current Google Sheet payment snapshot.

This module is imported explicitly for one production migration and then removed
from the Railway start command. It preserves existing payment_student ids by
using the alias-normalized source keys from payment_name_aliases.
"""
import sqlite3

import payment_name_aliases  # noqa: F401 - patches run_bot_live85._name_key
import run_bot_live85 as payments
import payment_schedule

bot = payments.bot
MIGRATION_KEY = "google_sheet_2026_09_12_alias_v1"

SNAPSHOT = [
    ("Шейхрамова Милана", 13200, {"2026-09": 13200}),
    ("Приголовкина Серафима", 12000, {"2026-09": 12000, "2026-10": 12000, "2026-11": 12000}),
    ("Елизавета Овсянникова", 12540, {"2026-09": 12540}),
    ("Аня Панкова", 13200, {"2026-09": 13200}),
    ("Смольянинов Степан", 12000, {"2026-09": 12000, "2026-10": 12000, "2026-11": 12000}),
    ("Гапонова Анастасия", 13200, {"2026-09": 13200}),
    ("Первышина Ева", 13200, {"2026-09": 13200}),
    ("Яков", 13200, {"2026-09": 13200}),
    ("Никифорова Алиса", 12000, {
        "2026-09": 12000, "2026-10": 12000, "2026-11": 12000,
        "2026-12": 12000, "2027-01": 12000, "2027-02": 12000,
        "2027-03": 12000, "2027-04": 12000, "2027-05": 12000,
    }),
    ("Силинг Иосиф", 13200, {"2026-09": 13200}),
    ("Трубецкая Василисса", 13200, {"2026-09": 13200}),
    ("Месхи Мариам", 13200, {"2026-09": 13200}),
    ("Иноземцева Злата", 13200, {"2026-09": 13200}),
]


def _students():
    result = []
    for name, monthly_amount, coverage in SNAPSHOT:
        result.append({
            "source_key": payments._name_key(name),
            "display_name": name,
            "monthly_amount": monthly_amount,
            "coverage": dict(coverage),
        })
    return result


def _ensure_migration_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payment_data_migrations (
            migration_key TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)


def apply_once():
    payments.ensure_payment_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        _ensure_migration_table(conn)
        already = conn.execute(
            "SELECT 1 FROM payment_data_migrations WHERE migration_key = ?",
            (MIGRATION_KEY,),
        ).fetchone()
    if already:
        print("PAYMENT_SYNC_ONCE already_applied", flush=True)
        return

    count, coverage_count = payments.save_payment_snapshot(_students(), "Google Sheets: Доход / 11 КЛАСС")
    payment_schedule.install(payments, bot, None)
    payment_schedule.ensure_payment_plans()

    now = payments.datetime.now(bot.TIMEZONE).isoformat()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        _ensure_migration_table(conn)
        conn.execute(
            "INSERT OR IGNORE INTO payment_data_migrations (migration_key, applied_at) VALUES (?, ?)",
            (MIGRATION_KEY, now),
        )
        conn.commit()
    print(f"PAYMENT_SYNC_ONCE applied students={count} coverage={coverage_count}", flush=True)


def audit():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute("""
            SELECT ps.id, ps.source_key, ps.display_name, ps.active,
                   pp.cadence, pp.monthly_amount_cents,
                   COUNT(pc.id) AS coverage_count
            FROM payment_students ps
            LEFT JOIN payment_plans pp ON pp.payment_student_id = ps.id
            LEFT JOIN payment_coverage pc ON pc.payment_student_id = ps.id
            WHERE ps.source_sheet = ?
            GROUP BY ps.id, ps.source_key, ps.display_name, ps.active,
                     pp.cadence, pp.monthly_amount_cents
            ORDER BY ps.active DESC, lower(ps.display_name)
        """, (payments.PAYMENT_SHEET_NAME,)).fetchall()
    active = [row for row in rows if int(row[3] or 0) == 1]
    inactive = [row for row in rows if int(row[3] or 0) == 0]
    print(f"PAYMENT_AUDIT active={len(active)} inactive_legacy={len(inactive)}", flush=True)
    for sid, key, name, _active, cadence, rate, coverage_count in active:
        print(
            f"PAYMENT_STUDENT id={sid} key={key} name={name} cadence={cadence} "
            f"rate_cents={rate} coverage={coverage_count}",
            flush=True,
        )


apply_once()
audit()
