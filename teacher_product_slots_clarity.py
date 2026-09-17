"""Clear day view for PREPODMIN availability slots.

Keeps the existing slot settings/blocks, but renders three separate concepts:
actual lessons, transfer history for the selected day, and truly free windows.
"""
from datetime import date

import teacher_product_mvp as base
import teacher_product_slots as slots


_original_day_text = None
_installed = False


def _minutes(value):
    return slots._minutes(value)


def _clock(total):
    return slots._clock(total)


def _icon(kind):
    return "👤" if kind == "individual" else "👥"


def _move_rows(uid, day):
    """Return all individual/group moves touching this date, with original time/name."""
    target = day.isoformat()
    result = []
    with base.db() as conn:
        individual = conn.execute(
            """
            SELECT sm.schedule_slot_id, sm.original_date, sm.new_date, sm.new_time,
                   ss.time_text AS original_time, s.name AS name
            FROM schedule_moves sm
            JOIN schedule_slots ss ON ss.id=sm.schedule_slot_id
            JOIN students s ON s.id=ss.student_id
            WHERE sm.teacher_telegram_user_id=?
              AND (sm.original_date=? OR sm.new_date=?)
            ORDER BY sm.original_date, ss.time_text, lower(s.name)
            """,
            (int(uid), target, target),
        ).fetchall()
        for row in individual:
            result.append({
                "kind": "individual",
                "name": row["name"],
                "original_date": row["original_date"],
                "original_time": row["original_time"],
                "new_date": row["new_date"],
                "new_time": row["new_time"],
            })

        group = conn.execute(
            """
            SELECT gm.schedule_slot_id, gm.original_date, gm.new_date, gm.new_time,
                   gs.time_text AS original_time, g.name AS name
            FROM group_schedule_moves gm
            JOIN group_schedule_slots gs ON gs.id=gm.schedule_slot_id
            JOIN teacher_groups g ON g.id=gs.group_id
            WHERE gm.teacher_telegram_user_id=?
              AND (gm.original_date=? OR gm.new_date=?)
            ORDER BY gm.original_date, gs.time_text, lower(g.name)
            """,
            (int(uid), target, target),
        ).fetchall()
        for row in group:
            result.append({
                "kind": "group",
                "name": row["name"],
                "original_date": row["original_date"],
                "original_time": row["original_time"],
                "new_date": row["new_date"],
                "new_time": row["new_time"],
            })
    result.sort(key=lambda r: (r["original_date"], r["original_time"], r["kind"], r["name"].lower()))
    return result


def _format_move(row, selected_day):
    old_date = date.fromisoformat(row["original_date"])
    new_date = date.fromisoformat(row["new_date"])
    old_t = row["original_time"]
    new_t = row["new_time"]
    if old_date == new_date:
        route = f"{old_t} → {new_t}"
    else:
        route = f"{old_date.strftime('%d.%m')} {old_t} → {new_date.strftime('%d.%m')} {new_t}"
    return f"• {_icon(row['kind'])} {row['name']}: {route}"


def _merge_intervals(intervals):
    clean = sorted((int(s), int(e)) for s, e in intervals if e > s)
    merged = []
    for start, end in clean:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(s, e) for s, e in merged]


def _free_windows(start, end, occupied):
    clipped = []
    for s, e in occupied:
        s = max(start, s)
        e = min(end, e)
        if e > s:
            clipped.append((s, e))
    merged = _merge_intervals(clipped)
    free = []
    cursor = start
    for s, e in merged:
        if s > cursor:
            free.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < end:
        free.append((cursor, end))
    return free


def _free_label(start, end, duration):
    minutes = end - start
    full = minutes // duration
    rest = minutes % duration
    if full <= 0:
        return f"• {_clock(start)}–{_clock(end)} — {minutes} мин (короче обычного слота)"
    detail = f"{full} " + ("слот" if full == 1 else "слота" if full in {2, 3, 4} else "слотов")
    detail += f" по {duration} мин"
    if rest:
        detail += f" + {rest} мин"
    return f"• {_clock(start)}–{_clock(end)} — {detail}"


def _collision_lines(event_intervals):
    collisions = []
    seen = set()
    for i, (s1, e1, a) in enumerate(event_intervals):
        for s2, e2, b in event_intervals[i + 1:]:
            if not slots._overlap(s1, e1, s2, e2):
                continue
            overlap_start = max(s1, s2)
            overlap_end = min(e1, e2)
            key = (overlap_start, overlap_end, a["kind"], a["name"], b["kind"], b["name"])
            if key in seen:
                continue
            seen.add(key)
            collisions.append(
                f"⚠️ {_clock(overlap_start)}–{_clock(overlap_end)}: "
                f"{_icon(a['kind'])} {a['name']} + {_icon(b['kind'])} {b['name']}"
            )
    return collisions


def clear_day_text(uid, day):
    window = slots._window(uid, day)
    duration = slots._settings(uid)
    events = slots._events(uid, day)
    blocks = slots._blocks(uid, day)
    moves = _move_rows(uid, day)

    lines = [
        f"🗓 {slots.DAY_NAMES_FULL[day.weekday()].capitalize()}, {day.strftime('%d.%m.%Y')}",
        f"Обычная длительность занятия: {duration} мин",
        "",
    ]

    event_intervals = []
    for event in events:
        try:
            start_at = _minutes(event["time"])
        except Exception:
            continue
        event_intervals.append((start_at, start_at + duration, event))

    lines.append("📚 ЗАНЯТИЯ")
    if event_intervals:
        for start_at, end_at, event in event_intervals:
            moved = " ↪️" if event.get("moved") else ""
            lines.append(
                f"🔴 {_clock(start_at)}–{_clock(end_at)}  {_icon(event['kind'])} {event['name']}{moved}"
            )
    else:
        lines.append("Занятий нет.")

    collision_lines = _collision_lines(event_intervals)
    if collision_lines:
        lines.append("")
        lines.append("⚠️ НАКЛАДКИ В РАСПИСАНИИ")
        lines.extend(collision_lines)

    if moves:
        lines.append("")
        lines.append("🔁 ПЕРЕНОСЫ")
        for row in moves:
            lines.append(_format_move(row, day))

    if blocks:
        lines.append("")
        lines.append("🔒 ЗАКРЫТО ВРУЧНУЮ")
        for block in blocks:
            label = str(block["label"] or "личное")
            marker = "🟡" if ("брон" in label.lower() or "удерж" in label.lower()) else "🔒"
            lines.append(f"{marker} {block['start_time']}–{block['end_time']} • {label}")

    lines.append("")
    lines.append("🟢 СВОБОДНО")
    if not window or not int(window["active"] or 0):
        lines.append("По рабочему шаблону это выходной.")
    else:
        start = _minutes(window["start_time"])
        end = _minutes(window["end_time"])
        if end <= start:
            lines.append("⚠️ Рабочее окно настроено некорректно.")
        else:
            occupied = [(s, e) for s, e, _event in event_intervals]
            for block in blocks:
                try:
                    occupied.append((_minutes(block["start_time"]), _minutes(block["end_time"])))
                except Exception:
                    pass
            free = _free_windows(start, end, occupied)
            usable = [(s, e) for s, e in free if e - s >= duration]
            short = [(s, e) for s, e in free if 0 < e - s < duration]
            lines.append(f"Рабочее окно: {window['start_time']}–{window['end_time']}")
            if usable:
                for s, e in usable:
                    lines.append(_free_label(s, e, duration))
            else:
                lines.append("Свободных окон на полное занятие нет.")
            if short:
                short_text = ", ".join(f"{_clock(s)}–{_clock(e)}" for s, e in short)
                lines.append(f"Короткие промежутки: {short_text}")

            outside = [(s, e, ev) for s, e, ev in event_intervals if s < start or e > end]
            if outside:
                lines.append("")
                lines.append("⚠️ ВНЕ РАБОЧЕГО ОКНА")
                for s, e, event in outside:
                    lines.append(f"• {_clock(s)}–{_clock(e)} {_icon(event['kind'])} {event['name']}")

    if moves:
        lines.append("")
        lines.append("↪️ = занятие перенесено; точный маршрут переноса указан выше.")
    return "\n".join(lines)


def install():
    global _original_day_text, _installed
    if _installed:
        return
    _original_day_text = slots._day_text
    slots._day_text = clear_day_text
    _installed = True
    print("PREPODMIN slots clarity ready: actual schedule + transfer routes + free windows + collision warnings", flush=True)
