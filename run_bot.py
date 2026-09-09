from datetime import date, timedelta

import bot

# Расписание курса: понедельник, среда, воскресенье.
# Единственное исключение: урок 08.11.2026 переносится на субботу 07.11.2026.
bot.LESSON_WEEKDAYS = {0, 2, 6}
SPECIAL_LESSON_DATES = {date(2026, 11, 7)}
SKIPPED_LESSON_DATES = {date(2026, 11, 8)}


def get_course_lesson_number(for_date=None):
    current_date = for_date or bot.today_moscow()
    if current_date < bot.COURSE_START_DATE:
        return 0

    count = 0
    cursor = bot.COURSE_START_DATE
    while cursor <= current_date and count < bot.TOTAL_LESSONS:
        is_regular_lesson = (
            cursor.weekday() in bot.LESSON_WEEKDAYS
            and cursor not in SKIPPED_LESSON_DATES
        )
        if is_regular_lesson or cursor in SPECIAL_LESSON_DATES:
            count += 1
        cursor += timedelta(days=1)

    return min(count, bot.TOTAL_LESSONS)


def get_course_progress_text(for_date=None):
    current_date = for_date or bot.today_moscow()
    lesson_number = get_course_lesson_number(current_date)
    progress = lesson_number / bot.TOTAL_LESSONS if bot.TOTAL_LESSONS else 0
    percent = progress * 100

    if lesson_number == 0:
        filled = 0
    elif lesson_number >= bot.TOTAL_LESSONS:
        filled = bot.PROGRESS_SEGMENTS
    else:
        filled = max(1, round(progress * bot.PROGRESS_SEGMENTS))

    empty = bot.PROGRESS_SEGMENTS - filled
    bar = "🩷" * filled + "🤍" * empty
    percent_text = f"{percent:.1f}".replace(".", ",")

    is_regular_today = (
        current_date.weekday() in bot.LESSON_WEEKDAYS
        and current_date not in SKIPPED_LESSON_DATES
    )
    today_is_lesson = (
        current_date >= bot.COURSE_START_DATE
        and (is_regular_today or current_date in SPECIAL_LESSON_DATES)
        and lesson_number <= bot.TOTAL_LESSONS
    )

    lines = [
        "💗 <b>Прогресс курса</b>",
        bar,
        f"<b>{lesson_number} / {bot.TOTAL_LESSONS} уроков</b> · {percent_text}%",
    ]

    if today_is_lesson and 0 < lesson_number <= bot.TOTAL_LESSONS:
        lines.append(f"Сегодня — урок №{lesson_number} 🧪")

    return "\n".join(lines)


bot.get_course_lesson_number = get_course_lesson_number
bot.get_course_progress_text = get_course_progress_text


if __name__ == "__main__":
    bot.main()
