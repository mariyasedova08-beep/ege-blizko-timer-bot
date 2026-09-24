"""Isolated PREPADMIN pilot smoke test.

Exercises the core data path on a temporary SQLite database so production data is
never mutated: teacher isolation, students, groups, schedules, group members,
homework, attendance, tasks, payments, and file-backed persistence.
"""
import os
import tempfile
from datetime import date, datetime

import teacher_product_mvp as base
import teacher_product_schedule as schedule
import teacher_product_groups as groups
import teacher_product_student_reminders as student_reminders
import teacher_product_learning as learning
import teacher_product_tasks as tasks
import teacher_product_payments as payments
import teacher_product_group_payments as group_payments
import teacher_product_onboarding as onboarding


def _group_id(uid, name):
    with base.db() as conn:
        row = conn.execute(
            "SELECT id FROM teacher_groups WHERE teacher_telegram_user_id=? AND name=?",
            (int(uid), name),
        ).fetchone()
    return int(row[0]) if row else None


def run():
    original_path = base.DB_PATH
    fd, path = tempfile.mkstemp(prefix="prepadmin-pilot-", suffix=".sqlite3")
    os.close(fd)
    try:
        base.DB_PATH = path
        base.ensure_tables()
        schedule.ensure_tables()
        groups.ensure_tables()
        student_reminders.ensure_tables()
        learning.ensure_tables()
        tasks.ensure_tables()
        payments.ensure_tables()
        group_payments.ensure_tables()
        onboarding.ensure_tables()

        now = datetime.utcnow().isoformat()
        teacher_a, teacher_b = 910001, 910002
        base.upsert_teacher(
            teacher_a,
            name="Пилот А",
            subject="Химия",
            work_format="groups",
            timezone="Europe/Moscow",
            onboarding_completed_at=now,
        )
        base.upsert_teacher(
            teacher_b,
            name="Пилот Б",
            subject="Математика",
            work_format="individual",
            timezone="Europe/Moscow",
            onboarding_completed_at=now,
        )

        student_a = base.add_student(teacher_a, "Аня", "@anya")
        student_b = base.add_student(teacher_b, "Борис", "@boris")
        if schedule.get_student(teacher_b, student_a) is not None:
            raise RuntimeError("student tenant isolation failed")
        if schedule.get_student(teacher_a, student_b) is not None:
            raise RuntimeError("student reverse tenant isolation failed")

        groups.add_group(teacher_a, "ЕГЭ химия")
        groups.add_group(teacher_b, "Алгебра")
        group_a = _group_id(teacher_a, "ЕГЭ химия")
        group_b = _group_id(teacher_b, "Алгебра")
        if not group_a or not group_b:
            raise RuntimeError("group creation failed")
        if groups.get_group(teacher_b, group_a) is not None:
            raise RuntimeError("group tenant isolation failed")

        member_a = student_reminders.add_member(teacher_a, group_a, "Злата")
        member_b = student_reminders.add_member(teacher_b, group_b, "Миша")
        if not member_a or not member_b:
            raise RuntimeError("group member creation failed")

        schedule.add_slot(teacher_a, student_a, 0, "18:00")
        groups.add_group_slot(teacher_a, group_a, 2, "19:00")
        if len(schedule.slots(teacher_a)) != 1 or len(groups.group_slots(teacher_a)) != 1:
            raise RuntimeError("schedule creation failed")
        if schedule.slots(teacher_b):
            raise RuntimeError("schedule leaked across teachers")

        with base.db() as conn:
            cur = conn.execute(
                """
                INSERT INTO teacher_homework(
                    teacher_telegram_user_id,target_kind,target_id,
                    homework_text,due_date,active,created_at
                ) VALUES(?,'group',?,?,?,1,?)
                """,
                (teacher_a, group_a, "Решить №1–10", date.today().isoformat(), now),
            )
            homework_id = int(cur.lastrowid)
            conn.commit()
        assignment = learning._assignment(homework_id, teacher_a)
        learning._sync_statuses(assignment)
        with base.db() as conn:
            hw_rows = conn.execute(
                "SELECT subject_kind,subject_id,status FROM teacher_homework_status WHERE assignment_id=?",
                (homework_id,),
            ).fetchall()
        if len(hw_rows) != 1 or hw_rows[0]["subject_kind"] != "group_member":
            raise RuntimeError("group homework recipient sync failed")
        if int(hw_rows[0]["subject_id"]) != int(member_a["id"]):
            raise RuntimeError("group homework linked to wrong member")

        learning._set_attendance(
            teacher_a, "group", int(groups.group_slots(teacher_a)[0]["id"]),
            date.today(), "group_member", int(member_a["id"]), "present",
        )
        with base.db() as conn:
            attendance_count = conn.execute(
                "SELECT COUNT(*) FROM teacher_attendance WHERE teacher_telegram_user_id=?",
                (teacher_a,),
            ).fetchone()[0]
        if int(attendance_count) != 1:
            raise RuntimeError("attendance write failed")

        payments._save_plan(
            teacher_a, student_a, "monthly", 15000, date(2026, 9, 28)
        )
        with base.db() as conn:
            monthly = conn.execute(
                """
                SELECT payment_type,amount_rub,next_due_date
                FROM student_payment_plans
                WHERE teacher_telegram_user_id=? AND student_id=?
                """,
                (teacher_a, student_a),
            ).fetchone()
        if (
            not monthly
            or monthly["payment_type"] != "monthly"
            or int(monthly["amount_rub"]) != 15000
            or monthly["next_due_date"] != "2026-09-28"
        ):
            raise RuntimeError("individual monthly payment plan failed")

        parsed = tasks.parse_tasks(teacher_a, "Подготовить конспект завтра в 12:00")
        if not parsed:
            raise RuntimeError("task parser returned no task")
        task_ids = tasks.save_tasks(teacher_a, parsed, "text", "pilot-selftest")
        if len(task_ids) != 1:
            raise RuntimeError("task save failed")

        group_payments._save_group_plan(
            teacher_a,
            {
                "pid": int(member_a["id"]),
                "gid": group_a,
                "type": "package",
                "amount": 12000,
                "name": "Злата",
            },
            lessons=4,
        )
        setup_state = onboarding.setup_status(teacher_a)
        if not setup_state["payments"]:
            raise RuntimeError("group-only onboarding payment progress failed")

        group_payments._reconcile_package_charge(
            teacher_a,
            "group_member",
            int(member_a["id"]),
            int(groups.group_slots(teacher_a)[0]["id"]),
            date.today(),
            "present",
        )
        with base.db() as conn:
            left = conn.execute(
                """
                SELECT lessons_remaining FROM group_member_payment_plans
                WHERE teacher_telegram_user_id=? AND person_id=?
                """,
                (teacher_a, int(member_a["id"])),
            ).fetchone()[0]
        if int(left) != 3:
            raise RuntimeError(f"group package accounting failed: {left}")

        # File-backed restart check: every connection above is closed here. Opening
        # a fresh connection to the same SQLite file must see the committed state.
        with base.db() as reopened:
            persisted = reopened.execute(
                "SELECT COUNT(*) FROM teacher_groups WHERE teacher_telegram_user_id=?",
                (teacher_a,),
            ).fetchone()[0]
            persisted_payment = reopened.execute(
                """
                SELECT lessons_remaining FROM group_member_payment_plans
                WHERE teacher_telegram_user_id=? AND person_id=?
                """,
                (teacher_a, int(member_a["id"])),
            ).fetchone()[0]
        if int(persisted) != 1 or int(persisted_payment) != 3:
            raise RuntimeError("file-backed restart persistence failed")

        with base.db() as conn:
            leaked = conn.execute(
                """
                SELECT COUNT(*)
                FROM group_member_payment_plans
                WHERE teacher_telegram_user_id=? AND person_id=?
                """,
                (teacher_b, int(member_a["id"])),
            ).fetchone()[0]
        if int(leaked) != 0:
            raise RuntimeError("payment tenant isolation failed")

        print(
            "PREPADMIN PILOT SELFTEST ok: isolation + students + groups + schedule + "
            "homework + attendance + tasks + payments + persistence",
            flush=True,
        )
    finally:
        base.DB_PATH = original_path
        try:
            os.remove(path)
        except OSError:
            pass
