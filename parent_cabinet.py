import secrets, sqlite3
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler
import run_bot_live85 as payments
import run_bot_live15 as live15
import payment_student_ui, payment_schedule

bot = payments.bot
live7 = payments.live79.live7

STATUS="🚦 Как идут дела"; PROGRESS="📊 Успеваемость"; PROBNIK="📝 Пробники"
HOMEWORK="🏠 Домашние работы"; ATTENDANCE="🎓 Посещаемость"; PAYMENT="💳 Оплата"
CONTACT="💬 Мария Александровна"; CHILD="👨‍👩‍👧 Выбрать ребёнка"


def ensure_tables():
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS parent_invites(
            token TEXT PRIMARY KEY, student_id INTEGER NOT NULL, created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL, used_at TEXT, used_by INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS parent_links(
            parent_telegram_user_id INTEGER NOT NULL, student_id INTEGER NOT NULL,
            parent_username TEXT, parent_name TEXT, active INTEGER NOT NULL DEFAULT 1,
            linked_at TEXT NOT NULL, PRIMARY KEY(parent_telegram_user_id, student_id))""")
        c.commit()


def now(): return datetime.now(bot.TIMEZONE)


def student_by_id(sid):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c:
        return c.execute("""SELECT id, coalesce(nullif(display_name,''),nullif(user_name,''),user_email,'Ученик'),
            coreapp_user_id,user_email,telegram_user_id FROM students WHERE id=? AND active=1""",(int(sid),)).fetchone()


def link_ids(uid):
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c:
        return [int(r[0]) for r in c.execute("SELECT student_id FROM parent_links WHERE parent_telegram_user_id=? AND active=1 ORDER BY linked_at",(int(uid),)).fetchall()]


def is_parent(uid): return bool(link_ids(uid))


def payment_row(student):
    return payment_student_ui._row_for_telegram_user(student[4]) if student and student[4] is not None else None


def student_name(student):
    row=payment_row(student)
    return row["name"] if row else student[1]


def selected_student(context, uid):
    ids=link_ids(uid)
    if not ids: return None
    sid=context.user_data.get("parent_student_id")
    if sid in ids:
        s=student_by_id(sid)
        if s: return s
    s=student_by_id(ids[0])
    if s: context.user_data["parent_student_id"]=s[0]
    return s


def keyboard(uid):
    rows=[[STATUS],[PROGRESS,PROBNIK],[HOMEWORK,ATTENDANCE],[PAYMENT],[CONTACT]]
    if len(link_ids(uid))>1: rows.append([CHILD])
    return ReplyKeyboardMarkup(rows,resize_keyboard=True,is_persistent=True)


def resolve_student(q):
    q=str(q or "").strip()
    if not q: return None
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c: students=live15._active_students(c)
    qkey=payments._name_key(q); qn=live15._norm_name(q); exact=[]; partial=[]
    for s in students:
        names=[s[1]]; pr=payment_row(s)
        if pr: names.append(pr["name"])
        if any(payments._name_key(n)==qkey for n in names if n): exact.append(s); continue
        if qn and any(qn in live15._norm_name(n) or live15._norm_name(n) in qn for n in names if n): partial.append(s)
    return exact[0] if len(exact)==1 else partial[0] if len(partial)==1 else None


def metrics(student):
    d=now()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c:
        names=live15._probnik_names_for_month(c,d.year,d.month)
        return live15._student_month_metrics(c,student,d.year,d.month,names)


def pct(v): return "—" if v is None else f"{round(float(v))}%"
def attendance_pct(m): return None if not m["attendance_total"] else m["attendance_present"]*100/m["attendance_total"]
def trainer_pct(m): return None if not m["trainer_total"] else m["trainer_correct"]*100/m["trainer_total"]


def status(m):
    warnings=[]
    ap=attendance_pct(m)
    if m["attendance_total"]>=2 and ap<90: warnings.append((2 if ap<75 else 1,f"посещаемость {round(ap)}%"))
    hp=m["homework_accuracy"]
    if m["homework_count"] and hp is not None and hp<75: warnings.append((2 if hp<60 else 1,f"точность ДЗ {round(hp)}%"))
    pa=m["probnik_avg"]
    if m["probnik_count"] and pa is not None and pa<70: warnings.append((2 if pa<60 else 1,f"средний результат пробников {round(pa)}"))
    evidence=m["attendance_total"]+m["homework_count"]+m["probnik_count"]+m["trainer_sessions"]
    if not evidence: return "⚪","Пока мало данных",[]
    if any(x[0]==2 for x in warnings): return "🔴","Нужно внимание",[x[1] for x in warnings]
    if warnings: return "🟡","Есть на что обратить внимание",[x[1] for x in warnings]
    return "🟢","Всё идёт стабильно",[]


def status_text(s):
    m=metrics(s); icon,title,w=status(m); d=now(); ap=attendance_pct(m); tp=trainer_pct(m)
    lines=[f"{icon} {title}","",f"Ребёнок: {student_name(s)}",f"Период: {live15.MONTH_NAMES[d.month]} {d.year}",""]
    lines.append(f"📝 Пробники: {m['probnik_count']} · средний {live15._fmt(m['probnik_avg'])} · лучший {live15._fmt(m['probnik_best'])}" if m["probnik_count"] else "📝 Пробники: в этом месяце пока нет результатов")
    lines.append(f"🏠 ДЗ: сдано {m['homework_count']}"+(f" · точность {pct(m['homework_accuracy'])}" if m["homework_accuracy"] is not None else ""))
    lines.append("🎓 Посещаемость: занятия ещё не отмечены" if ap is None else f"🎓 Посещаемость: {m['attendance_present']}/{m['attendance_total']} · {pct(ap)}")
    lines.append("🧪 Тренажёры: пока без тренировок в этом месяце" if not m["trainer_sessions"] else f"🧪 Тренажёры: {m['trainer_sessions']} · точность {pct(tp)}")
    if w:
        lines += ["","На что стоит обратить внимание:"]+[f"• {x}" for x in w]+["","Мария Александровна видит эту динамику и учитывает её в работе."]
    elif icon=="🟢": lines += ["","По текущим данным дополнительное вмешательство родителя не требуется."]
    return "\n".join(lines)


def progress_text(s):
    m=metrics(s); d=now(); ap=attendance_pct(m); tp=trainer_pct(m)
    prob="—" if not m["probnik_count"] else f"средний {live15._fmt(m['probnik_avg'])}, лучший {live15._fmt(m['probnik_best'])}"
    return "\n".join([f"📊 Успеваемость — {student_name(s)}",f"{live15.MONTH_NAMES[d.month]} {d.year}","",f"📝 Пробники: {prob}",
        f"🏠 ДЗ: {m['homework_count']} сдач"+(f" · точность {pct(m['homework_accuracy'])}" if m["homework_accuracy"] is not None else ""),
        "🎓 Посещаемость: "+("ещё не отмечена" if ap is None else f"{m['attendance_present']}/{m['attendance_total']} · {pct(ap)}"),
        "🧪 Тренажёры: "+("0 тренировок" if not m["trainer_sessions"] else f"{m['trainer_sessions']} · точность {pct(tp)}")])


def probnik_text(s):
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c:
        names=[r[0] for r in c.execute("SELECT DISTINCT student_name FROM probnik_results").fetchall()]
        name=live15._best_probnik_name(s[1],names)
        if not name and payment_row(s): name=live15._best_probnik_name(payment_row(s)["name"],names)
        rows=c.execute("""SELECT event_date,event_name,secondary_score FROM probnik_results
            WHERE student_name=? AND secondary_score IS NOT NULL
            ORDER BY substr(event_date,7,4) DESC, substr(event_date,4,2) DESC, substr(event_date,1,2) DESC LIMIT 5""",(name,)).fetchall() if name else []
    out=[f"📝 Пробники — {student_name(s)}",""]
    if not rows: return "\n".join(out+["Результатов пробников пока нет."])
    out += [f"• {dt} · {ev or 'Пробник'}: {live15._fmt(sc)}" for dt,ev,sc in rows]
    if len(rows)>=2:
        delta=float(rows[0][2])-float(rows[1][2]); out += ["",f"Динамика к предыдущему пробнику: {'+' if delta>0 else ''}{live15._fmt(delta)}"]
    return "\n".join(out)


def homework_text(s):
    m=metrics(s); d=now()
    return "\n".join([f"🏠 Домашние работы — {student_name(s)}",f"{live15.MONTH_NAMES[d.month]} {d.year}","",f"Сдано работ: {m['homework_count']}",
        f"Средняя точность: {pct(m['homework_accuracy'])}" if m["homework_accuracy"] is not None else "Точность: пока недостаточно данных", "", "Здесь учитываются фактически отправленные домашние работы."])


def attendance_text(s):
    m=metrics(s); d=now(); ap=attendance_pct(m)
    base=[f"🎓 Посещаемость — {student_name(s)}",f"{live15.MONTH_NAMES[d.month]} {d.year}",""]
    return "\n".join(base+(["Занятия в этом месяце ещё не отмечены."] if ap is None else [f"Посещено: {m['attendance_present']} из {m['attendance_total']}",f"Посещаемость: {pct(ap)}"]))


def payment_text(s):
    r=payment_row(s)
    if not r: return "💳 Оплата\n\nПлатёжные данные пока не подключены. По вопросу оплаты напишите Марии Александровне."
    lines=["💳 Оплата курса","",f"Ученик: {r['name']}",f"График: {payment_schedule.CADENCE_LABELS[r['cadence']]}",f"✅ Оплачено: {payment_student_ui._paid_period_label(r)}"]
    item=r.get("next_invoice")
    if r["cadence"]=="prepaid" or not item:
        return "\n".join(lines+(["","График оплаты сейчас уточняется. Напишите Марии Александровне."] if r["cadence"]=="review" else ["","🏁 Курс оплачен полностью.","Дополнительные платежи не требуются."]))
    lines += ["",f"Следующая оплата: {item['label']}",f"Сумма: {payment_schedule.money(item['remaining_cents'])}",f"Оплатить до: {item['due_date']:%d.%m.%Y} включительно."]
    if item["status"]=="overdue": lines.append("🔴 Срок оплаты уже прошёл.")
    return "\n".join(lines+["","После оплаты, пожалуйста, пришлите Марии Александровне расчётный чек, чтобы она отметила платёж."])


async def home(update,context):
    uid=update.effective_user.id; s=selected_student(context,uid)
    if not s: return await update.effective_message.reply_text("Родительский кабинет пока не привязан. Попросите у Марии Александровны персональную ссылку.")
    await update.effective_message.reply_text(f"👨‍👩‍👧 Кабинет родителя\n\nРебёнок: {student_name(s)}\n\nЗдесь можно посмотреть текущую динамику, пробники, домашние работы, посещаемость и оплату.",reply_markup=keyboard(uid))


async def contact(update,context,uid):
    s=selected_student(context,uid); aid=bot.get_admin_id(); markup=None
    if aid: markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Написать Марии Александровне",url=f"tg://user?id={int(aid)}")]])
    await update.effective_message.reply_text(f"💬 Связаться с Марией Александровной\n\nЕсли нужен личный комментарий по {student_name(s) if s else 'ребёнку'}, вопрос по обучению или оплате, можно написать Марии Александровне напрямую.",reply_markup=markup or keyboard(uid))


async def choose_child(update,context):
    rows=[]
    for sid in link_ids(update.effective_user.id):
        s=student_by_id(sid)
        if s: rows.append([InlineKeyboardButton(student_name(s),callback_data=f"pcab:child:{sid}")])
    if rows: await update.effective_message.reply_text("Выберите ребёнка:",reply_markup=InlineKeyboardMarkup(rows))


def consume(token,user):
    ensure_tables(); d=now()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c:
        row=c.execute("SELECT student_id,expires_at,used_at,used_by FROM parent_invites WHERE token=?",(token,)).fetchone()
        if not row: return None,"Ссылка недействительна. Попросите у Марии Александровны новую персональную ссылку."
        sid,exp,used,used_by=row
        try: expires=datetime.fromisoformat(exp)
        except ValueError: return None,"Ссылка недействительна."
        if d>expires: return None,"Срок действия ссылки истёк. Попросите у Марии Александровны новую ссылку."
        if used and used_by is not None and int(used_by)!=int(user.id): return None,"Эта ссылка уже была использована. Попросите у Марии Александровны новую ссылку."
        s=student_by_id(sid)
        if not s: return None,"Ученик сейчас недоступен. Напишите Марии Александровне."
        c.execute("""INSERT INTO parent_links(parent_telegram_user_id,student_id,parent_username,parent_name,active,linked_at)
            VALUES(?,?,?,?,1,?) ON CONFLICT(parent_telegram_user_id,student_id) DO UPDATE SET parent_username=excluded.parent_username,parent_name=excluded.parent_name,active=1""",
            (int(user.id),int(sid),user.username or "",user.full_name or "",d.isoformat()))
        c.execute("UPDATE parent_invites SET used_at=COALESCE(used_at,?),used_by=COALESCE(used_by,?) WHERE token=?",(d.isoformat(),int(user.id),token)); c.commit()
    return s,None


_original_start=live7.start_router; _original_text=live7.student_text_router

async def start_router(update,context):
    if update.effective_chat.type=="private":
        arg=context.args[0] if context.args else ""
        if arg.startswith("parent_"):
            s,err=consume(arg[7:],update.effective_user)
            if err: return await update.message.reply_text(err)
            context.user_data["parent_student_id"]=s[0]
            await update.message.reply_text(f"✅ Родительский кабинет подключён.\n\nРебёнок: {student_name(s)}",reply_markup=keyboard(update.effective_user.id))
            return await update.message.reply_text(status_text(s))
        if is_parent(update.effective_user.id): return await home(update,context)
    return await _original_start(update,context)

async def text_router(update,context):
    if not update.message or not update.message.text or update.effective_chat.type!="private" or not is_parent(update.effective_user.id):
        return await _original_text(update,context)
    uid=update.effective_user.id; s=selected_student(context,uid); t=update.message.text.strip()
    if not s: return await update.message.reply_text("Кабинет не привязан к ученику. Напишите Марии Александровне.")
    if t==STATUS: msg=status_text(s)
    elif t==PROGRESS: msg=progress_text(s)
    elif t==PROBNIK: msg=probnik_text(s)
    elif t==HOMEWORK: msg=homework_text(s)
    elif t==ATTENDANCE: msg=attendance_text(s)
    elif t==PAYMENT: msg=payment_text(s)
    elif t==CONTACT: return await contact(update,context,uid)
    elif t==CHILD: return await choose_child(update,context)
    else: msg="Используйте кнопки родительского кабинета ниже 👇"
    await update.message.reply_text(msg,reply_markup=keyboard(uid))

live7.start_router=start_router; live7.student_text_router=text_router


async def parent_command(update,context):
    if update.effective_chat.type!="private": return
    return await home(update,context) if is_parent(update.effective_user.id) else await update.message.reply_text("Родительский кабинет подключается по персональной ссылке от Марии Александровны.")

async def invite_command(update,context):
    if update.effective_chat.type!="private" or not bot.user_is_admin(update): return
    q=" ".join(context.args).strip()
    if not q: return await update.message.reply_text("Например: /parentinvite Аня Панкова")
    s=resolve_student(q)
    if not s: return await update.message.reply_text("Не удалось однозначно найти ученика. Укажите имя точнее.")
    token=secrets.token_hex(12); d=now(); exp=d+timedelta(days=30)
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c:
        c.execute("INSERT INTO parent_invites(token,student_id,created_at,expires_at) VALUES(?,?,?,?)",(token,s[0],d.isoformat(),exp.isoformat())); c.commit()
    me=await context.bot.get_me(); link=f"https://t.me/{me.username}?start=parent_{token}"
    await update.message.reply_text(f"👨‍👩‍👧 Персональная ссылка для родителя\n\nРебёнок: {student_name(s)}\nСсылка одноразовая и действует 30 дней.\n\n{link}\n\nОтправьте её родителю. После перехода кабинет привяжется только к этому ребёнку.")

async def status_command(update,context):
    if update.effective_chat.type!="private" or not bot.user_is_admin(update): return
    ensure_tables()
    with sqlite3.connect(bot.COREAPP_DB_PATH) as c:
        rows=c.execute("SELECT parent_name,parent_username,student_id FROM parent_links WHERE active=1 ORDER BY linked_at").fetchall()
        pending=c.execute("SELECT COUNT(*) FROM parent_invites WHERE used_at IS NULL AND expires_at>=?",(now().isoformat(),)).fetchone()[0]
    lines=[f"👨‍👩‍👧 Родительские кабинеты: {len(rows)}",f"Неиспользованных ссылок: {pending}"]
    for pn,pu,sid in rows:
        s=student_by_id(sid)
        if s: lines.append(f"• {student_name(s)} — {pn or 'Родитель'}"+(f" (@{pu})" if pu else ""))
    await update.message.reply_text("\n".join(lines))

async def callback(update,context):
    q=update.callback_query; uid=update.effective_user.id
    try: sid=int(q.data.rsplit(":",1)[1])
    except Exception: return
    if sid not in link_ids(uid): return await q.answer("Этот кабинет вам не доступен",show_alert=True)
    s=student_by_id(sid)
    if not s: return await q.answer("Ученик недоступен",show_alert=True)
    context.user_data["parent_student_id"]=sid; await q.answer("Ребёнок выбран"); await q.edit_message_text(f"✅ Выбран ребёнок: {student_name(s)}")
    await q.message.reply_text("Родительский кабинет обновлён 👇",reply_markup=keyboard(uid))


_original_build=ApplicationBuilder.build

def build(self):
    app=_original_build(self)
    app.add_handler(CommandHandler("parent",parent_command)); app.add_handler(CommandHandler("parentinvite",invite_command)); app.add_handler(CommandHandler("parentstatus",status_command)); app.add_handler(CallbackQueryHandler(callback,pattern=r"^pcab:"))
    return app

ensure_tables(); ApplicationBuilder.build=build
print("Parent cabinet MVP ready",flush=True)
