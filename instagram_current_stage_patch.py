"""Current-stage Instagram positioning patch.

Maria is returning after a two-year pause. On 2026-09-13 we only package the
profile; active content starts the next day. Trainers and the teacher bot are
shown as part of her developing teaching system, not sold as standalone offers.
"""
import instagram_return_system as ig

# Day 1 is packaging only: no feed/stories publication is required today.
ig.FIRST_14[1] = (
    "Подготовка профиля",
    "Сегодня ничего не публикуй. Обнови шапку профиля так, чтобы за 10 секунд было понятно: Мария Седова — преподаватель химии, готовит к ЕГЭ и ОГЭ на годовых курсах и создаёт собственную систему подготовки, тренажёры и банк заданий.",
    "На этом этапе не продаём тренажёры и бот как отдельный продукт. Они звучат как часть твоей методики и разработки. Активный возврат в контент начинается завтра.",
)

# Keep the first two weeks non-commercial while the audience is being reactivated.
ig.FIRST_14[10] = (
    "Разморозка",
    "Покажи один из тренажёров ЕГЭ БЛИЗКО как часть своей системы подготовки: зачем он нужен ученикам и какую проблему решает. Без отдельной продажи тренажёра.",
    "Сейчас наша задача — показать глубину системы и твою работу, а не делать оффер на ещё не упакованный отдельный продукт.",
)

# Until a standalone trainer/bot offer is ready, Friday content should lead to
# trust/Telegram rather than promise a product that is not packaged yet.
ig.WEEKDAY_TASKS[4] = (
    "Reel → мягкий следующий шаг",
    "Сними Reel с понятной пользой и одним следующим шагом: подписаться, перейти в Telegram, сохранить материал или узнать о курсах. Тренажёры и бот показывай как часть системы, без отдельной продажи.",
)

print("Instagram current-stage positioning ready: profile first, no standalone trainer/bot offer", flush=True)
