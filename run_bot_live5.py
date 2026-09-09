import run_bot_live4

live4 = run_bot_live4
bot = live4.bot

_original_chatid = bot.chatid
_original_threadid = bot.threadid
_original_myid = bot.myid


async def safe_chatid(update, context):
    # Техническая команда: в детском чате отвечает только преподавателю.
    if update.effective_chat.type != "private" and not bot.user_is_admin(update):
        return
    await _original_chatid(update, context)


async def safe_threadid(update, context):
    # Техническая команда: в детском чате отвечает только преподавателю.
    if update.effective_chat.type != "private" and not bot.user_is_admin(update):
        return
    await _original_threadid(update, context)


async def safe_myid(update, context):
    # Не засоряем общий чат ответами с техническими ID.
    if update.effective_chat.type != "private" and not bot.user_is_admin(update):
        return
    await _original_myid(update, context)


bot.chatid = safe_chatid
bot.threadid = safe_threadid
bot.myid = safe_myid


if __name__ == "__main__":
    live4.main()
