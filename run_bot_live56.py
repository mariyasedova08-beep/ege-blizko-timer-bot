import sqlite3

import run_bot_live55

live55 = run_bot_live55
live54 = live55.live54
live52 = live55.live52
live51 = live55.live51
live50 = live55.live50
live49 = live55.live49
live48 = live55.live48
live46 = live55.live46
live44 = live55.live44
live43 = live55.live43
live41 = live55.live41
live39 = live55.live39
live37 = live55.live37
live35 = live55.live35
live34 = live55.live34
live31 = live55.live31
live24 = live55.live24
live17 = live55.live17
bot = live55.bot


def _student_name_candidates(student_row):
    values = [student_row[1], student_row[2]]
    result = []
    for value in values:
        norm = live34._norm_name(value)
        if norm and norm not in result:
            result.append(norm)
    return result


def _tokens(value):
    return tuple(x for x in live34._norm_name(value).split() if x)


def unique_probnik_student_match(result_name, student_rows):
    """Безопасно сопоставляет имя из таблицы пробников с учеником.

    Сначала полное совпадение. Затем допускаем сокращённое имя/полное имя,
    но только если среди всех учеников получается ровно один кандидат.
    Это чинит случаи вроде «Мариам» в кабинете и «Мариам Фамилия» в таблице,
    не привязывая результат наугад при двух одинаковых именах.
    """
    target = live34._norm_name(result_name)
    if not target:
        return None

    exact = [
        row for row in student_rows
        if target in _student_name_candidates(row)
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    partial = []
    for row in student_rows:
        for candidate in _student_name_candidates(row):
            if len(candidate) >= 3 and (candidate in target or target in candidate):
                partial.append(row)
                break
    # Убираем возможные повторы одной и той же записи.
    unique_partial = {int(row[0]): row for row in partial}
    if len(unique_partial) == 1:
        return next(iter(unique_partial.values()))
    if len(unique_partial) > 1:
        return None

    # Дополнительный безопасный случай: ФИО записано в другом порядке.
    target_tokens = set(_tokens(result_name))
    if len(target_tokens) >= 2:
        token_matches = []
        for row in student_rows:
            for value in (row[1], row[2]):
                candidate_tokens = set(_tokens(value))
                if len(candidate_tokens) >= 2 and candidate_tokens == target_tokens:
                    token_matches.append(row)
                    break
        unique_tokens = {int(row[0]): row for row in token_matches}
        if len(unique_tokens) == 1:
            return next(iter(unique_tokens.values()))
    return None


# Используем улучшенное сопоставление и для автоматического разбора пробников.
live43._match_student = unique_probnik_student_match


def _all_active_students():
    return live34._student_rows()


def latest_probnik_for_student(student):
    students = _all_active_students()
    student_id = int(student[0])
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT student_name, event_name, event_date,
                   primary_score, secondary_score, tasks_json
            FROM probnik_results
            WHERE secondary_score IS NOT NULL OR primary_score IS NOT NULL
            ORDER BY substr(event_date, 7, 4) DESC,
                     substr(event_date, 4, 2) DESC,
                     substr(event_date, 1, 2) DESC,
                     id DESC
            """
        ).fetchall()

    for result_name, event_name, event_date, primary, secondary, tasks_json in rows:
        matched = unique_probnik_student_match(result_name, students)
        if matched and int(matched[0]) == student_id:
            # Для кабинета приоритетно показываем вторичный балл ЕГЭ.
            # Если во входном пробнике он не заполнен, показываем первичный,
            # чтобы написанный пробник не выглядел как «результата нет».
            score = secondary if secondary is not None else primary
            return (result_name, event_name, event_date, score, tasks_json)
    return None


live49._latest_probnik = latest_probnik_for_student


def probnik_text_for_student(student):
    students = _all_active_students()
    student_id = int(student[0])
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT student_name, event_name, event_date,
                   primary_score, secondary_score, tasks_json
            FROM probnik_results
            WHERE secondary_score IS NOT NULL OR primary_score IS NOT NULL
            ORDER BY substr(event_date, 7, 4) DESC,
                     substr(event_date, 4, 2) DESC,
                     substr(event_date, 1, 2) DESC,
                     id DESC
            """
        ).fetchall()

    matched_rows = []
    for row in rows:
        result_name, event_name, event_date, primary, secondary, tasks_json = row
        matched = unique_probnik_student_match(result_name, students)
        if matched and int(matched[0]) == student_id:
            matched_rows.append(row)
            if len(matched_rows) >= 5:
                break

    lines = ["📝 Пробники", ""]
    if not matched_rows:
        return "\n".join(lines + ["Пока нет синхронизированных результатов."])

    for _name, event_name, event_date, primary, secondary, _tasks in matched_rows:
        value = secondary if secondary is not None else primary
        try:
            shown = int(float(value)) if float(value).is_integer() else round(float(value), 1)
        except Exception:
            shown = value
        suffix = "" if secondary is not None else " · первичный балл"
        lines.append(f"• {event_name} · {event_date} — {shown} баллов{suffix}")
    return "\n".join(lines)


live49._probnik_text = probnik_text_for_student


def log_probnik_cabinet_audit():
    """Только агрегаты в логах; без e-mail, Telegram ID и списка учеников."""
    try:
        students = _all_active_students()
        linked = [row for row in students if row[5] is not None]
        visible = sum(1 for row in linked if latest_probnik_for_student(row))
        mariam_rows = [
            row for row in linked
            if "мариам" in live34._norm_name(row[1]) or "мариам" in live34._norm_name(row[2])
        ]
        mariam_visible = any(latest_probnik_for_student(row) for row in mariam_rows)
        print(
            "Probnik cabinet audit: "
            f"linked={len(linked)}, visible={visible}, missing={len(linked) - visible}, "
            f"mariam_visible={'yes' if mariam_visible else 'no'}"
        )
    except Exception as exc:
        print("Probnik cabinet audit error:", repr(exc))


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
    live41.ensure_weekly_report_tables()
    live41.seed_current_trainers()
    live48.ensure_metals_tables()
    live48.register_metals_trainer()
    live43.ensure_probnik_analysis_tables()
    live44.enable_probnik_analysis_now()
    live46.ensure_monthly_auto_report_table()
    live50.seed_molar_mass_task()
    live51.ensure_course_schedule_table()
    log_probnik_cabinet_audit()
    live24.main()
