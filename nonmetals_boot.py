"""Compatibility bootstrap for the nonmetals trainer and its launch campaign."""
import run_bot_live85

live79 = run_bot_live85.live79
# run_bot_live79 does not re-export live15, while run_bot_live60 does.
# The trainer expects the alias for monthly student metrics.
if not hasattr(live79, "live15"):
    live79.live15 = live79.live60.live15

import nonmetals_campaign  # noqa: F401,E402

print("Nonmetals compatibility bootstrap ready", flush=True)
