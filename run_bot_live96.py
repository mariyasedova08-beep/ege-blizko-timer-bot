"""Redact HTTP query strings before they reach Railway runtime logs."""

import run_bot_live90 as live90


bot = live90.bot


def _redact_query(value):
    text = str(value)
    if "?" not in text:
        return value
    before, after = text.split("?", 1)
    space_index = after.find(" ")
    suffix = after[space_index:] if space_index >= 0 else ""
    return before + "?[REDACTED]" + suffix


def redacted_log_message(self, format, *args):
    safe_args = tuple(_redact_query(value) for value in args)
    print("CoreApp HTTP:", format % safe_args, flush=True)


bot.CoreAppWebhookHandler.log_message = redacted_log_message


def verify_http_log_redaction():
    sample = _redact_query("POST /coreapp/event?secret=private HTTP/1.1")
    if "private" in sample or "?[REDACTED]" not in sample:
        raise RuntimeError("HTTP query redaction self-check failed")
    if bot.CoreAppWebhookHandler.log_message is not redacted_log_message:
        raise RuntimeError("HTTP query redaction is not active")
    print("LIVE96: HTTP query redaction ready", flush=True)


verify_http_log_redaction()
