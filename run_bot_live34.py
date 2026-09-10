import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta

import run_bot_live33

live33 = run_bot_live33
live32 = live33.live32
live31 = live33.live31
live30 = live31.live30
live28 = live30.live28
live25 = live30.live25
live24 = live30.live24
live23 = live24.live23
live17 = live23.live17
live7 = live30.live7
live3 = live30.live3
run_bot = live30.run_bot
bot = live33.bot

# Зона внимания: мягкие пороги, чтобы не тревожить из-за одного случайного сбоя.
ATTENDANCE_LOOKBACK = 4
ATTENDANCE_ABSENCE_THRESHOLD = 2
HOMEWORK_LOOKBACK = 3
HOMEWORK_MISSING_THRESHOLD = 2
PROBNIK_SCORE_THRESHOLD = 60
TRAINER_LOOKBACK_DAYS = 7
TRAINER_MIN_SESSIONS = 2

CHILD_ALERT_WEEKDAY = 6  # воскресенье
CHILD_ALERT_AFTER = "20:30"
PARENT_RECHECK_DAYS = 3
PARENT_INVITE_HOURS = 168


def ensure_attention_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attention_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                child_telegram_user_id INTEGER NOT NULL,
                snapshot_json TEXT NOT NULL,
                sent_to_child_at TEXT NOT NULL,
                parent_check_at TEXT NOT NULL,
                parent_notified_at TEXT,
                resolved_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parent_invites (
                code TEXT PRIMARY KEY,
                student_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parent_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                telegram_username TEXT,
                telegram_name TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                linked_at TEXT NOT NULL,
                UNIQUE(student_id, telegram_user_id)
            )
            """
        )
        conn.commit()


def _shown_name(row):
    return (row[1] or row[2] or row[3] or "Ученик").strip()


def _norm_name(value):
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text)
    return " ".join(text.split())


def _student_rows():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        return conn.execute(
            """
            SELECT id,
                   coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, 'Ученик'),
                   user_name,
                   user_email,
                   coreapp_user_id,
                   telegram_user_id
            FROM students
            WHERE active = 1
            ORDER BY lower(coalesce(nullif(display_name, ''), nullif(user_name, ''), user_email, ''))
            """
        ).fetchall()


def _attendance_metric(conn, student_id):
    rows = conn.execute(
        """
        SELECT ar.status
        FROM attendance_records ar
        JOIN attendance_sessions s ON s.lesson_number = ar.lesson_number
        WHERE ar.student_id = ? AND s.finalized = 1
        ORDER BY s.lesson_date DESC
        LIMIT ?
        """,
        (student_id, ATTENDANCE_LOOKBACK),
    ).fetchall()
    if len(rows) < 3:
        return None
    absences = sum(1 for (status,) in rows if status == "absent")
    if absences < ATTENDANCE_ABSENCE_THRESHOLD:
        return None
    return {
        "key": "attendance",
        "value": absences,
        "label": f"посещаемость: {absences} пропуска из {len(rows)} последних уроков",
    }


def _overdue_homework_lesson_numbers(today):
    dates = run_bot.COURSE_LESSON_DATES
    overdue = []
    # ДЗ после урока N считаем просроченным только когда уже наступил урок N+1.
    for i in range(len(dates) - 1):
        if dates[i + 1] <= today:
            overdue.append(i + 1)  # номер урока начинается с 1
    return overdue[-HOMEWORK_LOOKBACK:]


def _homework_metric(conn, student_row, today):
    student_id, _display, _user_name, email, coreapp_user_id, _telegram_id = student_row
    expected = _overdue_homework_lesson_numbers(today)
    if len(expected) < 2:
        return None

    submissions = conn.execute(
        """
        SELECT user_id, lower(user_email), lesson_id, lesson_name
        FROM homework_submissions
        WHERE (coalesce(user_id, '') != '' AND user_id = ?)
           OR (coalesce(user_email, '') != '' AND lower(user_email) = lower(?))
        """,
        (str(coreapp_user_id or ""), str(email or "")),
    ).fetchall()

    done = set()
    dates = run_bot.COURSE_LESSON_DATES
    for lesson_number in expected:
        previous_date = dates[lesson_number - 1]
        target_number = lesson_number + 1
        for _uid, _mail, lesson_id, lesson_name in submissions:
            if live31._submission_explicitly_matches(
                lesson_id,
                lesson_name,
                target_number,
                lesson_number,
                previous_date,
            ):
                done.add(lesson_number)
                break

    missing = len(expected) - len(done)
    if missing < HOMEWORK_MISSING_THRESHOLD:
        return None
    return {
        "key": "homework",
        "value": missing,
        "label": f"ДЗ: не закрыто {missing} из {len(expected)} последних обязательных работ",
    }


def _probnik_metric(conn, student_row):
    name = _shown_name(student_row)
    candidates = {
        _norm_name(name),
        _norm_name(student_row[2]),
        _norm_name(student_row[3]),
    }
    candidates.discard("")
    rows = conn.execute(
        """
        SELECT student_name, secondary_score, event_date
        FROM probnik_results
        WHERE secondary_score IS NOT NULL
        ORDER BY substr(event_date, 7, 4) DESC,
                 substr(event_date, 4, 2) DESC,
                 substr(event_date, 1, 2) DESC,
                 id DESC
        """
    ).fetchall()
    matched = None
    for result_name, score, event_date in rows:
        rn = _norm_name(result_name)
        if rn in candidates or any(c and (c in rn or rn in c) for c in candidates):
            matched = (float(score), event_date)
            break
    if not matched:
        return None
    score, event_date = matched
    if score >= PROBNIK_SCORE_THRESHOLD:
        return None
    return {
        "key": "probnik",
        "value": score,
        "label": f"пробник: {score:g} баллов (ниже {PROBNIK_SCORE_THRESHOLD})",
        "event_date": event_date,
    }


def _trainer_metric(conn, student_row, now):
    telegram_id = student_row[5]
    if telegram_id is None:
        return None
    if (now.date() - run_bot.COURSE_START_DATE).days < TRAINER_LOOKBACK_DAYS:
        return None
    since = (now - timedelta(days=TRAINER_LOOKBACK_DAYS)).isoformat()
    trivial = conn.execute(
        """
        SELECT COUNT(*) FROM trivial_sessions
        WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at >= ?
        """,
        (int(telegram_id), since),
    ).fetchone()[0]
    acid = conn.execute(
        """
        SELECT COUNT(*) FROM acid_sessions
        WHERE telegram_user_id = ? AND finished_at IS NOT NULL AND finished_at >= ?
        """,
        (int(telegram_id), since),
    ).fetchone()[0]
    sessions = int(trivial or 0) + int(acid or 0)
    if sessions >= TRAINER_MIN_SESSIONS:
        return None
    return {
        "key": "trainer",
        "value": sessions,
        "label": f"тренажёры: {sessions} за последние {TRAINER_LOOKBACK_DAYS} дней",
    }


def attention_metrics(student_row, now=None):
    now = now or datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        metrics = [
            _attendance_metric(conn, int(student_row[0])),
            _homework_metric(conn, student_row, now.date()),
            _probnik_metric(conn, student_row),
            _trainer_metric(conn, student_row, now),
        ]
    return [m for m in metrics if m]


def attention_snapshot(student_row, now=None):
    metrics = attention_metrics(student_row, now)
    return {m["key"]: m for m in metrics}


def _parents_for_student(conn, student_id):
    return conn.execute(
        """
        SELECT telegram_user_id, telegram_name
        FROM parent_links
        WHERE student_id = ? AND active = 1
        ORDER BY id
        """,
        (int(student_id),),
    ).fetchall()


def _latest_child_alert(conn, student_id):
    return conn.execute(
        """
        SELECT sent_to_child_at
        FROM attention_alerts
        WHERE student_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (int(student_id),),
    ).fetchone()


def _alert_is_recent(last_row, now):
    if not last_row or not last_row[0]:
        return False
    try:
        previous = datetime.fromisoformat(last_row[0])
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=bot.TIMEZONE)
        return now - previous < timedelta(days=7)
    except Exception:
        return False


def _child_alert_text(name, metrics):
    lines = [
        f"🚨 {name}, ты попал(а) в мою зону внимания 💗",
        "",
        "Сейчас есть несколько вещей, которые нужно подтянуть:",
    ]
    lines.extend(f"• {m['label']}" for m in metrics)
    lines.extend([
        "",
        "В ближайшие 3 дня постарайся исправить каждый отмеченный пункт, который можешь изменить сейчас.",
        "Я проверю динамику через 3 дня. Если хотя бы один показатель не улучшится, бот сообщит родителю.",
        "",
        "Если есть причина или нужна помощь — напиши Марии Александровне 💗",
    ])
    return "\n".join(lines)


def _metric_not_improved(old_metric, new_snapshot):
    key = old_metric.get("key")
    if key not in new_snapshot:
        return False
    new_metric = new_snapshot[key]
    old_value = old_metric.get("value")
    new_value = new_metric.get("value")
    try:
        if key in {"attendance", "homework"}:
            return float(new_value) >= float(old_value)
        if key == "probnik":
            return float(new_value) <= float(old_value)
        if key == "trainer":
            return float(new_value) <= float(old_value)
    except Exception:
        return True
    return True


def _parent_alert_text(student_name, unchanged_metrics):
    lines = [
        "👨‍👩‍👧 <b>Уведомление по курсу «ЕГЭ БЛИЗКО»</b>",
        "",
        f"Три дня назад {student_name} получил(а) личное напоминание по учебной работе.",
        "К сожалению, часть показателей пока не улучшилась:",
    ]
    lines.extend(f"• {m['label']}" for m in unchanged_metrics)
    lines.extend([
        "",
        "Пожалуйста, обратите на это внимание. Это не итоговая оценка, а сигнал о текущей динамике на курсе.",
    ])
    return "\n".join(lines)


async def send_weekly_child_alerts(context, now):
    if now.weekday() != CHILD_ALERT_WEEKDAY or now.strftime("%H:%M") < CHILD_ALERT_AFTER:
        return

    for student_row in _student_rows():
        student_id = int(student_row[0])
        telegram_id = student_row[5]
        if telegram_id is None:
            continue
        metrics = attention_metrics(student_row, now)
        if not metrics:
            continue

        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            if _alert_is_recent(_latest_child_alert(conn, student_id), now):
                continue

        name = _shown_name(student_row)
        try:
            await context.bot.send_message(
                chat_id=int(telegram_id),
                text=_child_alert_text(name, metrics),
            )
        except Exception as exc:
            print(f"Could not send attention alert to student {telegram_id}: {exc}")
            continue

        check_at = now + timedelta(days=PARENT_RECHECK_DAYS)
        snapshot = {m["key"]: m for m in metrics}
        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO attention_alerts
                    (student_id, child_telegram_user_id, snapshot_json,
                     sent_to_child_at, parent_check_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    student_id,
                    int(telegram_id),
                    json.dumps(snapshot, ensure_ascii=False),
                    now.isoformat(),
                    check_at.isoformat(),
                ),
            )
            conn.commit()


async def recheck_and_notify_parents(context, now):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        alerts = conn.execute(
            """
            SELECT id, student_id, snapshot_json
            FROM attention_alerts
            WHERE parent_notified_at IS NULL
              AND resolved_at IS NULL
              AND parent_check_at <= ?
            ORDER BY id
            """,
            (now.isoformat(),),
        ).fetchall()

    students = {int(row[0]): row for row in _student_rows()}
    for alert_id, student_id, snapshot_json in alerts:
        student_row = students.get(int(student_id))
        if not student_row:
            continue
        try:
            old_snapshot = json.loads(snapshot_json or "{}")
        except Exception:
            old_snapshot = {}
        new_snapshot = attention_snapshot(student_row, now)
        unchanged = []
        for key, old_metric in old_snapshot.items():
            if _metric_not_improved(old_metric, new_snapshot):
                unchanged.append(new_snapshot.get(key, old_metric))

        if not unchanged:
            with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                conn.execute(
                    "UPDATE attention_alerts SET resolved_at = ? WHERE id = ?",
                    (now.isoformat(), int(alert_id)),
                )
                conn.commit()
            continue

        with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
            parents = _parents_for_student(conn, int(student_id))
        if not parents:
            # Не помечаем как отправленное: после подключения родителя проверка сработает снова.
            continue

        text = _parent_alert_text(_shown_name(student_row), unchanged)
        sent_any = False
        for parent_id, _parent_name in parents:
            try:
                await context.bot.send_message(chat_id=int(parent_id), text=text, parse_mode="HTML")
                sent_any = True
            except Exception as exc:
                print(f"Could not send parent attention alert to {parent_id}: {exc}")
        if sent_any:
            with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
                conn.execute(
                    "UPDATE attention_alerts SET parent_notified_at = ? WHERE id = ?",
                    (now.isoformat(), int(alert_id)),
                )
                conn.commit()


def zone_attention_text():
    now = datetime.now(bot.TIMEZONE)
    rows = _student_rows()
    blocks = []
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        for student_row in rows:
            metrics = attention_metrics(student_row, now)
            if not metrics:
                continue
            student_id = int(student_row[0])
            parents = _parents_for_student(conn, student_id)
            last = conn.execute(
                """
                SELECT sent_to_child_at, parent_notified_at
                FROM attention_alerts
                WHERE student_id = ? ORDER BY id DESC LIMIT 1
                """,
                (student_id,),
            ).fetchone()
            lines = [f"👩‍🎓 {_shown_name(student_row)}"]
            lines.extend(f"• {m['label']}" for m in metrics)
            lines.append("👨‍👩‍👧 Родитель: " + ("подключён" if parents else "не подключён"))
            if student_row[5] is None:
                lines.append("🔗 Telegram ученика не привязан")
            if last and last[0]:
                try:
                    d = datetime.fromisoformat(last[0]).astimezone(bot.TIMEZONE).strftime("%d.%m")
                    lines.append(f"📩 Последнее сообщение ученику: {d}")
                except Exception:
                    pass
            if last and last[1]:
                try:
                    d = datetime.fromisoformat(last[1]).astimezone(bot.TIMEZONE).strftime("%d.%m")
                    lines.append(f"📨 Родителю отправлено: {d}")
                except Exception:
                    pass
            blocks.append("\n".join(lines))

    if not blocks:
        return "🚨 Зона внимания\n\n✅ Сейчас учеников, требующих внимания по заданным критериям, нет."
    return (
        "🚨 Зона внимания\n\n"
        f"Сейчас требуют внимания: {len(blocks)}\n\n"
        + "\n\n".join(blocks)
    )


def parent_status_text():
    rows = _student_rows()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        linked = []
        missing = []
        for row in rows:
            parents = _parents_for_student(conn, int(row[0]))
            if parents:
                linked.append(f"✅ {_shown_name(row)} — {len(parents)}")
            else:
                missing.append(f"• {_shown_name(row)}")
    lines = [f"👨‍👩‍👧 Родители подключены: {len(linked)} из {len(rows)} учеников"]
    if linked:
        lines.extend(["", *linked])
    if missing:
        lines.extend(["", "Не подключены:", *missing])
    return "\n".join(lines)


def parent_menu_markup():
    rows = []
    for student in _student_rows():
        label = _shown_name(student)
        if len(label) > 34:
            label = label[:31] + "…"
        rows.append([
            live7.InlineKeyboardButton(
                f"🔗 {label}",
                callback_data=f"cab:parentinvite:{int(student[0])}",
            )
        ])
    rows.append([live7.InlineKeyboardButton("📋 Статус родителей", callback_data="cab:parentstatus")])
    rows.append([live7.InlineKeyboardButton("← В кабинет", callback_data="cab:back")])
    return live7.InlineKeyboardMarkup(rows)


def _make_parent_invite(student_id):
    code = secrets.token_hex(4)
    now = datetime.now(bot.TIMEZONE)
    expires = now + timedelta(hours=PARENT_INVITE_HOURS)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO parent_invites (code, student_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (code, int(student_id), now.isoformat(), expires.isoformat()),
        )
        conn.commit()
    return code, expires


async def _link_parent_from_start(update, context, code):
    if update.effective_chat.type != "private":
        return
    now = datetime.now(bot.TIMEZONE)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT i.student_id, i.expires_at, i.used_at,
                   coalesce(nullif(s.display_name, ''), nullif(s.user_name, ''), s.user_email, 'ученика')
            FROM parent_invites i
            JOIN students s ON s.id = i.student_id
            WHERE i.code = ? AND s.active = 1
            LIMIT 1
            """,
            (code,),
        ).fetchone()
        if not row:
            await update.message.reply_text("Ссылка для родителя не найдена. Попросите преподавателя создать новую.")
            return
        student_id, expires_text, used_at, student_name = row
        try:
            expires = datetime.fromisoformat(expires_text)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=bot.TIMEZONE)
        except Exception:
            expires = now - timedelta(seconds=1)
        if now > expires:
            await update.message.reply_text("Срок действия ссылки закончился. Попросите преподавателя создать новую.")
            return
        user = update.effective_user
        conn.execute(
            """
            INSERT INTO parent_links
                (student_id, telegram_user_id, telegram_username, telegram_name, active, linked_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(student_id, telegram_user_id) DO UPDATE SET
                telegram_username = excluded.telegram_username,
                telegram_name = excluded.telegram_name,
                active = 1,
                linked_at = excluded.linked_at
            """,
            (int(student_id), int(user.id), user.username or "", user.full_name or "", now.isoformat()),
        )
        conn.execute("UPDATE parent_invites SET used_at = ? WHERE code = ?", (now.isoformat(), code))
        conn.commit()
    await update.message.reply_text(
        f"✅ Готово! Вы подключены как родитель ученика {student_name}.\n\n"
        "Если учебная ситуация потребует внимания и не улучшится после личного напоминания ученику, бот пришлёт вам уведомление."
    )


_original_start_router = live7.start_router


async def start_router_with_parent_link(update, context):
    if context.args:
        arg = context.args[0].strip()
        if arg.startswith("parent_"):
            await _link_parent_from_start(update, context, arg[len("parent_"):])
            return
    await _original_start_router(update, context)


live7.start_router = start_router_with_parent_link


_original_cabinet_markup = live23.cabinet_markup


def cabinet_markup_with_attention():
    base = _original_cabinet_markup()
    rows = [list(row) for row in base.inline_keyboard]
    # Перед последними служебными кнопками добавляем два новых раздела.
    rows.insert(-1, [
        live7.InlineKeyboardButton("🚨 Зона внимания", callback_data="cab:zone"),
        live7.InlineKeyboardButton("👨‍👩‍👧 Родители", callback_data="cab:parents"),
    ])
    return live7.InlineKeyboardMarkup(rows)


live23.cabinet_markup = cabinet_markup_with_attention


_original_cabinet_callback = live23.cabinet_callback


async def cabinet_callback_with_attention(update, context):
    query = update.callback_query
    if not query or not live23._admin_private(update):
        return
    data = query.data or ""

    if data == "cab:zone":
        await query.answer()
        await live23._send_chunks(query.message, zone_attention_text())
        return

    if data == "cab:parents":
        await query.answer()
        await query.edit_message_text(
            "👨‍👩‍👧 <b>Родители</b>\n\n"
            "Нажми на ученика — я создам персональную ссылку. Её нужно переслать родителю, чтобы он один раз открыл бота и нажал Start.",
            parse_mode="HTML",
            reply_markup=parent_menu_markup(),
        )
        return

    if data == "cab:parentstatus":
        await query.answer()
        await live23._send_chunks(query.message, parent_status_text())
        return

    if data.startswith("cab:parentinvite:"):
        await query.answer()
        try:
            student_id = int(data.rsplit(":", 1)[1])
        except Exception:
            return
        student = next((r for r in _student_rows() if int(r[0]) == student_id), None)
        if not student:
            await query.message.reply_text("Ученика не нашла.")
            return
        code, expires = _make_parent_invite(student_id)
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start=parent_{code}"
        await query.message.reply_text(
            f"👨‍👩‍👧 Ссылка для родителя ученика {_shown_name(student)}\n\n"
            f"{link}\n\n"
            f"Действует до {expires.strftime('%d.%m.%Y %H:%M')}. Перешли это сообщение родителю."
        )
        return

    await _original_cabinet_callback(update, context)


live23.cabinet_callback = cabinet_callback_with_attention


_previous_tick = live7.friday_trivial_tick


async def combined_tick_with_attention(context):
    try:
        await _previous_tick(context)
    finally:
        now = datetime.now(bot.TIMEZONE)
        await send_weekly_child_alerts(context, now)
        await recheck_and_notify_parents(context, now)


live7.friday_trivial_tick = combined_tick_with_attention


if __name__ == "__main__":
    live31.live25.ensure_lesson_day_before_table()
    live31.live24.ensure_probnik_poll_tables()
    live31.live28.ensure_unanswered_reminder_tables()
    live31.live30.live3.ensure_attendance_tables()
    live31.live30.ensure_auto_attendance_table()
    live31.ensure_personal_homework_reminder_table()
    live17.ensure_acid_tables()
    ensure_attention_tables()
    live24.main()
