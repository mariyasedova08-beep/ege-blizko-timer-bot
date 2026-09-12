"""Attach payment delivery jobs to the Telegram application without editing legacy main()."""
from telegram.ext import ApplicationBuilder

import payment_delivery
import payment_delivery_ui
import payment_schedule

_original_build = ApplicationBuilder.build
_installed = False


def _build_with_payment_delivery(self):
    application = _original_build(self)
    payment_delivery_ui.patch(payment_schedule)
    payment_delivery.register_jobs(application)
    return application


def install():
    global _installed
    if _installed:
        return
    ApplicationBuilder.build = _build_with_payment_delivery
    _installed = True
    print("Payment delivery application hook installed", flush=True)


install()
