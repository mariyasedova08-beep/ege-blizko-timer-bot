# EGE BLIZKO — выборочные тренажёры в общий чат 9 класса

**Scope:** existing production Telegram bot EGE BLIZKO only, not PREPODMIN and not future educational SaaS.

## Feature
- Admin-only menu: `Кабинет Маши → 📣 Тренажёры ОГЭ → в чат`.
- One explicitly linked Telegram group, optional forum topic, not a list of individual recipients.
- Teacher selects trainer only from active `weekly_trainer_catalog`.
- Actions: confirm sending right now; schedule once at 17:00 Moscow; every day for 7 days at 17:00 or 19:00; stop the selected trainer's schedule.
- One message per trainer per chat per day (durable SQLite idempotency). Existing jobs and 11th-grade messages are unchanged.
- Uses native private admin entry to save the destination; requires bot membership in the group. Admin sends `/chatid` inside the group. For a forum topic, also send `/threadid` inside the topic. These commands already exist in the running bot.
- Messages contain the chosen trainer's deep link and a button.
- The code does **not** infer grade level from CoreApp accounts and does **not** automatically remind every trainer.

## Setup after Timeweb deployment
1. Ensure the bot is in the OGE ninth-grade chat and has permission to post.
2. In the OGE group send `/chatid`; if using a topic, `/threadid` there.
3. Open private admin chat, `Кабинет Маши → 📣 Тренажёры ОГЭ → в чат → 🔗 Привязать чат ОГЭ`, paste the group ID (and optional topic ID separated by a space).
4. Open `🧪 Выбрать тренажёр`, choose exactly the intended trainer. Confirm immediate sending or pick a schedule. Nothing sends until those actions.
5. Verify a single message arrives in the right group; inspect the deep link. Test scheduling and restart idempotency.

## Safety and release
- The implementation is currently **branch-only**, not deployed.
- Verify Python syntax, handlers, DB creation, Telegram rights, and rehearsal on a staging DB before deploying.
- The separate Timeweb production service and `/health` should be monitored during the deploy; always back up its DB first.
- Never repoint the existing `CHAT_ID` for older class notifications; this feature uses its own table `oge9_chat_settings`.
- No changes to medical bot or PREPODMIN.
