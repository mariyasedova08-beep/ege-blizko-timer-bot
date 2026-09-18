"""One-time admin preview sender for the oxide properties trainer."""
import asyncio
import os

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

import bot
import oxide_properties_campaign as campaign


async def _send():
    admin_id = bot.get_admin_id()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not admin_id or not token:
        print("OXIDE_PROPERTIES_ADMIN_TEST startup skipped: missing admin/token", flush=True)
        return False
    if campaign._sent(campaign.ADMIN_TEST_KEY, int(admin_id)):
        print("OXIDE_PROPERTIES_ADMIN_TEST startup skipped: already sent", flush=True)
        return True

    tg = Bot(token=token)
    me = await tg.get_me()
    markup = None
    if me.username:
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🧪 Открыть «Свойства оксидов»",
                url=f"https://t.me/{me.username}?start=oxideproperties",
            )
        ]])
    await tg.send_message(
        chat_id=int(admin_id),
        text=(
            "🧪 <b>ТЕСТ — «Свойства оксидов»</b>\n\n"
            "Это тестовое сообщение видишь только ты.\n"
            "Нажми кнопку ниже — откроется настоящий тренажёр на 80 вопросов."
        ),
        parse_mode="HTML",
        reply_markup=markup,
    )
    campaign._mark_sent(campaign.ADMIN_TEST_KEY, int(admin_id))
    print(f"OXIDE_PROPERTIES_ADMIN_TEST startup sent=1 user={int(admin_id)}", flush=True)
    return True


def send_once():
    try:
        return asyncio.run(_send())
    except Exception as exc:
        print(
            f"OXIDE_PROPERTIES_ADMIN_TEST startup failed error={type(exc).__name__}",
            flush=True,
        )
        return False
