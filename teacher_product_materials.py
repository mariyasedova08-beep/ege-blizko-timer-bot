"""Teacher -> student materials for PREPADMIN.

Teachers can save named materials (type + title + URL) for an individual student.
The material is kept in the student's cabinet and can also be delivered through
the existing student-message gateway. Opening is tracked from Telegram or WebApp.
"""
from datetime import datetime
from urllib.parse import urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import teacher_product_mvp as base
import teacher_product_student_messaging as messaging


MAT_TYPE, MAT_TITLE, MAT_URL = range(920, 923)

TYPE_LABELS = {
    "video": ("🎥", "Видео"),
    "notes": ("📄", "Конспект"),
    "trainer": ("🧪", "Тренажёр"),
    "article": ("🔗", "Статья / ссылка"),
    "other": ("📚", "Другое"),
}

_INSTALLED = False


def ensure_tables():
    with base.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teacher_student_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_telegram_user_id INTEGER NOT NULL,
                target_kind TEXT NOT NULL DEFAULT 'individual'
                    CHECK(target_kind IN ('individual','group_member')),
                target_id INTEGER NOT NULL,
                material_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                delivery_status TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                opened_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_student_materials_target
            ON teacher_student_materials(
                teacher_telegram_user_id,target_kind,target_id,active,created_at
            );
            """
        )
        conn.commit()


def _valid_url(value):
    try:
        parsed = urlparse(str(value or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def _student(uid, student_id):
    with base.db() as conn:
        return conn.execute(
            """
            SELECT s.id,s.name,s.contact,
                   p.telegram_user_id,p.id AS person_id
            FROM students s
            LEFT JOIN student_reminder_people p
              ON p.teacher_id=s.teacher_telegram_user_id
             AND p.kind='individual'
             AND p.student_id=s.id
             AND p.active=1
            WHERE s.id=? AND s.teacher_telegram_user_id=? AND s.active=1
            LIMIT 1
            """,
            (int(student_id), int(uid)),
        ).fetchone()


def _materials(uid, target_kind, target_id, limit=50):
    ensure_tables()
    with base.db() as conn:
        return conn.execute(
            """
            SELECT *
            FROM teacher_student_materials
            WHERE teacher_telegram_user_id=?
              AND target_kind=? AND target_id=? AND active=1
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(uid), str(target_kind), int(target_id), int(limit)),
        ).fetchall()


def _material(material_id):
    ensure_tables()
    with base.db() as conn:
        return conn.execute(
            "SELECT * FROM teacher_student_materials WHERE id=? AND active=1",
            (int(material_id),),
        ).fetchone()


def _status(row):
    if row["opened_at"]:
        try:
            when = datetime.fromisoformat(row["opened_at"]).strftime("%d.%m %H:%M")
        except Exception:
            when = "открыто"
        return f"👀 открыто {when}"

    status = str(row["delivery_status"] or "")
    if status == "sent":
        return "📨 отправлено"
    if status == "draft":
        return "📝 ждёт подтверждения"
    if status == "manual":
        return "✋ в непосланных"
    if status == "failed":
        return "⚠️ не доставлено"
    if status == "off":
        return "🔕 уведомление выключено"
    if status == "saved":
        return "💾 сохранено"
    return "💾 сохранено"


def _label(material_type):
    icon, label = TYPE_LABELS.get(str(material_type), ("📚", "Материал"))
    return icon, label


def _student_picker_markup(uid):
    rows = base.list_students(uid)
    buttons = [
        [InlineKeyboardButton(r["name"], callback_data=f"mat:student:{int(r['id'])}")]
        for r in rows[:60]
    ]
    return InlineKeyboardMarkup(buttons) if buttons else None


async def materials_home(update, context):
    uid = int(update.effective_user.id)
    if not base.teacher(uid):
        raise ApplicationHandlerStop

    rows = base.list_students(uid)
    if not rows:
        await update.message.reply_text(
            "📚 Материалы\n\nСначала добавь ученика в разделе «👥 Ученики».",
            reply_markup=base.MAIN_KB,
        )
        raise ApplicationHandlerStop

    await update.message.reply_text(
        "📚 Материалы ученику\n\nВыбери ученика:",
        reply_markup=_student_picker_markup(uid),
    )
    raise ApplicationHandlerStop


async def student_materials(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    student_id = int(q.data.rsplit(":", 1)[1])
    student = _student(uid, student_id)
    if not student:
        await q.edit_message_text("Ученик не найден.")
        raise ApplicationHandlerStop

    rows = _materials(uid, "individual", student_id, limit=20)
    lines = [f"📚 Материалы · {student['name']}"]
    if rows:
        lines.append("")
        for row in rows[:12]:
            icon, type_label = _label(row["material_type"])
            lines.append(
                f"{icon} {type_label}: {row['title']}\n"
                f"   {_status(row)}"
            )
    else:
        lines += ["", "Материалов пока нет."]

    kb = [
        [InlineKeyboardButton("➕ Добавить материал", callback_data=f"mat:add:{student_id}")],
    ]
    if rows:
        kb.append([
            InlineKeyboardButton("🗑 Удалить материал", callback_data=f"mat:remove:{student_id}")
        ])
    kb.append([InlineKeyboardButton("← К ученикам", callback_data="mat:students")])

    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(kb),
        disable_web_page_preview=True,
    )
    raise ApplicationHandlerStop


async def students_callback(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    rows = base.list_students(uid)
    if not rows:
        await q.edit_message_text("Ученики пока не добавлены.")
        raise ApplicationHandlerStop
    await q.edit_message_text(
        "📚 Материалы ученику\n\nВыбери ученика:",
        reply_markup=_student_picker_markup(uid),
    )
    raise ApplicationHandlerStop


async def add_begin(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    student_id = int(q.data.rsplit(":", 1)[1])
    student = _student(uid, student_id)
    if not student:
        await q.edit_message_text("Ученик не найден.")
        return ConversationHandler.END

    context.user_data["material_draft"] = {
        "student_id": student_id,
        "student_name": student["name"],
    }
    await q.edit_message_text(
        f"➕ Материал для {student['name']}\n\n"
        "Сначала укажи, <b>что это за материал</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 Видео", callback_data="mat:type:video")],
            [InlineKeyboardButton("📄 Конспект", callback_data="mat:type:notes")],
            [InlineKeyboardButton("🧪 Тренажёр", callback_data="mat:type:trainer")],
            [InlineKeyboardButton("🔗 Статья / ссылка", callback_data="mat:type:article")],
            [InlineKeyboardButton("📚 Другое", callback_data="mat:type:other")],
            [InlineKeyboardButton("Отмена", callback_data=f"mat:student:{student_id}")],
        ]),
    )
    return MAT_TYPE


async def add_type(update, context):
    q = update.callback_query
    await q.answer()
    draft = context.user_data.get("material_draft")
    if not draft:
        return ConversationHandler.END

    material_type = q.data.rsplit(":", 1)[1]
    if material_type not in TYPE_LABELS:
        return MAT_TYPE
    draft["material_type"] = material_type
    icon, type_label = _label(material_type)

    await q.edit_message_text(
        f"{icon} Тип: <b>{type_label}</b>\n\n"
        "Теперь напиши <b>название материала</b> — чтобы было понятно, что внутри.\n\n"
        "Например:\n"
        "«Металлы — химические свойства»\n"
        "«Разбор задания №34»\n"
        "«Алканы — получение и свойства»",
        parse_mode="HTML",
    )
    return MAT_TITLE


async def add_title(update, context):
    draft = context.user_data.get("material_draft")
    if not draft:
        return ConversationHandler.END
    title = str(update.message.text or "").strip()
    if len(title) < 2:
        await update.message.reply_text("Название слишком короткое. Напиши, что это за материал.")
        return MAT_TITLE
    if len(title) > 180:
        await update.message.reply_text("Сделай название короче — до 180 символов.")
        return MAT_TITLE

    draft["title"] = title
    await update.message.reply_text(
        "Теперь пришли ссылку на материал.\n"
        "Подойдут YouTube, VK Видео, Rutube, Core или обычная https-ссылка."
    )
    return MAT_URL


async def add_url(update, context):
    uid = int(update.effective_user.id)
    draft = context.user_data.get("material_draft")
    if not draft:
        return ConversationHandler.END

    url = str(update.message.text or "").strip()
    if not _valid_url(url):
        await update.message.reply_text(
            "Не вижу корректную ссылку. Пришли ссылку, начинающуюся с https://"
        )
        return MAT_URL

    student = _student(uid, draft["student_id"])
    if not student:
        context.user_data.pop("material_draft", None)
        await update.message.reply_text("Ученик больше не найден.", reply_markup=base.MAIN_KB)
        return ConversationHandler.END

    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        cur = conn.execute(
            """
            INSERT INTO teacher_student_materials(
                teacher_telegram_user_id,target_kind,target_id,
                material_type,title,url,active,delivery_status,created_at
            ) VALUES(?,'individual',?,?,?,?,1,'saved',?)
            """,
            (
                uid,
                int(draft["student_id"]),
                draft["material_type"],
                draft["title"],
                url,
                now,
            ),
        )
        material_id = int(cur.lastrowid)
        conn.commit()

    icon, type_label = _label(draft["material_type"])
    result = "saved"

    if student["telegram_user_id"] is not None:
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Открыть материал", callback_data=f"mat:open:{material_id}")
        ]])
        result = await messaging.dispatch(
            context,
            uid,
            int(student["telegram_user_id"]),
            (
                f"{icon} Новый материал от преподавателя\n\n"
                f"{type_label}: {draft['title']}\n\n"
                "Нажми кнопку ниже — материал также сохранён в твоём кабинете."
            ),
            recipient_name=student["name"],
            category="material",
            source_key=f"material:{material_id}",
            reply_markup=markup,
        )

    with base.db() as conn:
        conn.execute(
            """
            UPDATE teacher_student_materials
            SET delivery_status=?,sent_at=CASE WHEN ?='sent' THEN ? ELSE sent_at END
            WHERE id=?
            """,
            (result, result, now, material_id),
        )
        conn.commit()

    delivery = messaging.delivery_summary(
        uid,
        1 if student["telegram_user_id"] is not None else 0,
        sent=1 if result == "sent" else 0,
        failed=1 if result == "failed" else 0,
        singular=True,
    )
    context.user_data.pop("material_draft", None)

    await update.message.reply_text(
        f"✅ Материал сохранён у {student['name']}.\n\n"
        f"{icon} {type_label}: {draft['title']}\n"
        f"{delivery}\n\n"
        "Он останется в разделе «Материалы» личного кабинета ученика.",
        reply_markup=base.MAIN_KB,
        disable_web_page_preview=True,
    )
    return ConversationHandler.END


async def open_material(update, context):
    q = update.callback_query
    material_id = int(q.data.rsplit(":", 1)[1])
    row = _material(material_id)
    if not row:
        await q.answer("Материал уже недоступен.", show_alert=True)
        raise ApplicationHandlerStop

    uid = int(q.from_user.id)
    with base.db() as conn:
        linked = conn.execute(
            """
            SELECT 1
            FROM student_reminder_people p
            WHERE p.teacher_id=?
              AND p.kind='individual'
              AND p.student_id=?
              AND p.telegram_user_id=?
              AND p.active=1
            LIMIT 1
            """,
            (
                int(row["teacher_telegram_user_id"]),
                int(row["target_id"]),
                uid,
            ),
        ).fetchone()

    if not linked:
        await q.answer("Этот материал привязан к другому ученику.", show_alert=True)
        raise ApplicationHandlerStop

    mark_opened(material_id)
    await q.answer("Отмечено как открыто 💗")
    await q.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🌐 Перейти к материалу", url=row["url"])
        ]])
    )
    raise ApplicationHandlerStop


async def remove_picker(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    student_id = int(q.data.rsplit(":", 1)[1])
    student = _student(uid, student_id)
    if not student:
        await q.edit_message_text("Ученик не найден.")
        raise ApplicationHandlerStop

    rows = _materials(uid, "individual", student_id, limit=30)
    if not rows:
        await q.edit_message_text(
            "Удалять пока нечего.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("← Назад", callback_data=f"mat:student:{student_id}")
            ]]),
        )
        raise ApplicationHandlerStop

    buttons = []
    for row in rows:
        icon, _label_text = _label(row["material_type"])
        buttons.append([
            InlineKeyboardButton(
                f"🗑 {icon} {row['title']}"[:62],
                callback_data=f"mat:delete:{int(row['id'])}",
            )
        ])
    buttons.append([
        InlineKeyboardButton("← Назад", callback_data=f"mat:student:{student_id}")
    ])
    await q.edit_message_text(
        f"🗑 Что удалить у {student['name']}?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    raise ApplicationHandlerStop


async def delete_material(update, context):
    q = update.callback_query
    await q.answer()
    uid = int(q.from_user.id)
    material_id = int(q.data.rsplit(":", 1)[1])

    with base.db() as conn:
        row = conn.execute(
            """
            SELECT target_id,title FROM teacher_student_materials
            WHERE id=? AND teacher_telegram_user_id=? AND active=1
            """,
            (material_id, uid),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE teacher_student_materials SET active=0 WHERE id=?",
                (material_id,),
            )
            conn.commit()

    if not row:
        await q.edit_message_text("Материал уже удалён.")
        raise ApplicationHandlerStop

    await q.edit_message_text(
        f"✅ Материал «{row['title']}» удалён из кабинета ученика.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "← К материалам",
                callback_data=f"mat:student:{int(row['target_id'])}",
            )
        ]]),
    )
    raise ApplicationHandlerStop


def list_for_subject(teacher_id, target_kind, target_id, limit=60):
    rows = _materials(teacher_id, target_kind, target_id, limit=limit)
    result = []
    for row in rows:
        icon, type_label = _label(row["material_type"])
        result.append({
            "id": int(row["id"]),
            "type": row["material_type"],
            "type_label": type_label,
            "icon": icon,
            "title": row["title"],
            "url": row["url"],
            "created_at": row["created_at"],
            "opened": bool(row["opened_at"]),
        })
    return result


def material_for_subject(material_id, teacher_id, target_kind, target_id):
    row = _material(material_id)
    if not row:
        return None
    if (
        int(row["teacher_telegram_user_id"]) != int(teacher_id)
        or str(row["target_kind"]) != str(target_kind)
        or int(row["target_id"]) != int(target_id)
    ):
        return None
    return row


def mark_opened(material_id):
    now = datetime.utcnow().isoformat()
    with base.db() as conn:
        conn.execute(
            """
            UPDATE teacher_student_materials
            SET opened_at=COALESCE(opened_at,?)
            WHERE id=? AND active=1
            """,
            (now, int(material_id)),
        )
        conn.commit()


def patch_main_keyboard():
    rows = []
    found = False
    for row in getattr(base.MAIN_KB, "keyboard", []) or []:
        labels = [getattr(button, "text", str(button)) for button in row]
        if "📚 Материалы" in labels:
            found = True
        rows.append(labels)
    if not found:
        rows.append(["📚 Материалы"])
    base.MAIN_KB = ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def install(app):
    global _INSTALLED
    if _INSTALLED:
        return

    ensure_tables()
    messaging.CATEGORY_LABELS["material"] = "материал"
    patch_main_keyboard()

    adding = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_begin, pattern=r"^mat:add:\d+$")],
        states={
            MAT_TYPE: [
                CallbackQueryHandler(
                    add_type,
                    pattern=r"^mat:type:(?:video|notes|trainer|article|other)$",
                )
            ],
            MAT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            MAT_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_url)],
        },
        fallbacks=[],
        per_message=False,
    )

    app.add_handler(adding, group=-40)
    app.add_handler(
        MessageHandler(filters.Regex(r"^📚 Материалы$"), materials_home),
        group=-40,
    )
    app.add_handler(
        CallbackQueryHandler(students_callback, pattern=r"^mat:students$"),
        group=-40,
    )
    app.add_handler(
        CallbackQueryHandler(student_materials, pattern=r"^mat:student:\d+$"),
        group=-40,
    )
    app.add_handler(
        CallbackQueryHandler(remove_picker, pattern=r"^mat:remove:\d+$"),
        group=-40,
    )
    app.add_handler(
        CallbackQueryHandler(delete_material, pattern=r"^mat:delete:\d+$"),
        group=-40,
    )
    app.add_handler(
        CallbackQueryHandler(open_material, pattern=r"^mat:open:\d+$"),
        group=-40,
    )

    _INSTALLED = True
    print(
        "PREPADMIN materials ready: type + title + URL + delivery + opened status",
        flush=True,
    )
