"""Add privacy-safe source diagnostics for recurring Telegram network errors."""

import run_bot_live90 as live90


live70 = live90.live79.live70
_previous_error_handler = live70._error_handler


def _error_source(update, context):
    if getattr(context, "job", None) is not None:
        return "scheduled_job"
    if update is None:
        return "background_or_polling"
    if getattr(update, "callback_query", None) is not None:
        return "callback_query"
    if getattr(update, "message", None) is not None:
        return "message_update"
    return "other_update"


async def error_handler_with_source(update, context):
    error = getattr(context, "error", None)
    if type(error).__name__ == "NetworkError":
        print(
            f"BOT NETWORK ERROR SOURCE: {_error_source(update, context)}",
            flush=True,
        )
    return await _previous_error_handler(update, context)


live70._error_handler = error_handler_with_source


def verify_network_error_diagnostics():
    if live70._error_handler is not error_handler_with_source:
        raise RuntimeError("Network error source diagnostics are not active")
    print("LIVE95: network error source diagnostics ready", flush=True)


verify_network_error_diagnostics()
