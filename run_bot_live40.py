import run_bot_live39

live39 = run_bot_live39
live38 = live39.live38
live37 = live39.live37
live35 = live39.live35
live34 = live39.live34
live31 = live39.live31
live24 = live39.live24
live17 = live39.live17
bot = live39.bot


def _child_alert_text_with_greeting(name, metrics):
    lines = [
        f"Привет, {name}! 💗",
        "",
        "🚨 Ты попал(а) в мою зону внимания.",
        "",
        "Сейчас есть несколько вещей, которые нужно подтянуть:",
    ]
    lines.extend(f"• {m['label']}" for m in metrics if m.get("key") != "probnik")
    lines.extend([
        "",
        "В ближайшие 3 дня постарайся исправить ситуацию. Если есть несданное ДЗ — обязательно закрой его.",
        "Тренажёры полезны, но их прохождение само по себе не считается исправлением ситуации.",
        "Через 3 дня я проверю динамику. Если ситуация не исправится, бот сообщит родителю.",
        "",
        "Если есть причина или нужна помощь — напиши Марии Александровне 💗",
    ])
    return "\n".join(lines)


def _parent_alert_text_with_greeting(student_name, unchanged_metrics):
    metrics = [m for m in unchanged_metrics if m.get("key") != "probnik"]
    lines = [
        "Здравствуйте!",
        "",
        f"👨‍👩‍👧 <b>{live39.COURSE_NAME}</b>",
        "",
        "<b>Уведомление по учебной работе</b>",
        "",
        f"Три дня назад {student_name} получил(а) личное напоминание по учебной работе.",
        "Сейчас по-прежнему есть основания обратить внимание на ситуацию:",
    ]
    lines.extend(f"• {m['label']}" for m in metrics)
    lines.extend([
        "",
        "Пожалуйста, обратите на это внимание. Это не итоговая оценка, а сигнал о текущей работе на курсе.",
        "",
        "Если есть причина или нужна помощь — напишите Марии Александровне 💗",
    ])
    return "\n".join(lines)


live34._child_alert_text = _child_alert_text_with_greeting
live34._parent_alert_text = _parent_alert_text_with_greeting


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    live34.ensure_attention_tables()
    live35.ensure_admin_tasks_table()
    live35.seed_monday_task()
    live37.update_monday_task_text()
    live39.seed_probnik_return_task()
    live24.main()
