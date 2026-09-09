import run_bot


async def send_probnik_bundle(context, probnik_date, weekday_kind):
    chat_id = run_bot.bot.os.getenv("CHAT_ID")
    if not chat_id:
        return False, "CHAT_ID пока не настроен."

    number = run_bot.probnik_number(probnik_date)
    target_chat_id = int(chat_id)
    thread_id = run_bot.bot.get_target_thread_id()

    if weekday_kind == "thursday":
        card_file_id = run_bot.get_asset("probnik_card")
        blank_file_id = run_bot.get_asset("probnik_blank")

        if not card_file_id:
            return False, "Сначала нужно сохранить карточку пробника командой /setprobnikcard."
        if not blank_file_id:
            return False, "Сначала нужно сохранить бланк командой /setprobnikblank."

        await context.bot.send_photo(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            photo=card_file_id,
        )
        await context.bot.send_message(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            text=run_bot.thursday_text(number),
            parse_mode="HTML",
        )
        await context.bot.send_document(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            document=blank_file_id,
            caption="Бланк ответов для пробника 💗",
        )
    else:
        await context.bot.send_message(
            chat_id=target_chat_id,
            message_thread_id=thread_id,
            text=run_bot.friday_text(number),
            parse_mode="HTML",
        )

    return True, None


run_bot.send_probnik_bundle = send_probnik_bundle


if __name__ == "__main__":
    run_bot.main()
