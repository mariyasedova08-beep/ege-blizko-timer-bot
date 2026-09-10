from telegram.ext import ExtBot

import run_bot_live26

live26 = run_bot_live26
live25 = live26.live25
live24 = live26.live24
bot = live26.bot


# Явно включаем возможность менять голос во всех обычных опросах,
# которые отправляет этот бот (уроки и пробники).
_original_extbot_send_poll = ExtBot.send_poll


async def send_poll_with_revoting(self, *args, **kwargs):
    api_kwargs = dict(kwargs.pop("api_kwargs", None) or {})
    api_kwargs["allows_revoting"] = True
    kwargs["api_kwargs"] = api_kwargs
    return await _original_extbot_send_poll(self, *args, **kwargs)


ExtBot.send_poll = send_poll_with_revoting


if __name__ == "__main__":
    live25.ensure_lesson_day_before_table()
    live24.ensure_probnik_poll_tables()
    live24.main()
