"""Direct Google Sheets -> EGE BLIZKO payment sync.

This endpoint mirrors the existing probnik sync flow but reuses the payment
parser/storage model, so Maria no longer needs to export and upload XLSX files.
"""

import json
import os
from urllib.parse import parse_qs, urlparse

import payment_name_aliases  # noqa: F401 - installs stable payment name aliases
import payment_schedule
import run_bot_live85 as payments


bot = payments.bot
SYNC_PATH = "/sheets/payment-sync"
ALLOWED_PERIODS = {period for period, _label in payments.PAYMENT_PERIODS}

_previous_do_post = bot.CoreAppWebhookHandler.do_POST


def _amount(value):
    return payments._amount(value)


def _students_from_payload(payload):
    sheet_name = str(payload.get("sheet_name") or "").strip()
    if sheet_name.casefold() != payments.PAYMENT_SHEET_NAME.casefold():
        raise ValueError("wrong_sheet")

    raw_students = payload.get("students")
    if not isinstance(raw_students, list):
        raise ValueError("students_missing")

    students = []
    seen_keys = set()

    for raw in raw_students:
        if not isinstance(raw, dict):
            continue
        name = payments._clean_name(raw.get("display_name") or raw.get("name"))
        if not name:
            continue

        source_key = payments._name_key(name)
        if not source_key:
            continue
        if source_key in seen_keys:
            raise ValueError("duplicate_student")
        seen_keys.add(source_key)

        raw_coverage = raw.get("coverage") or {}
        coverage = {}
        if isinstance(raw_coverage, dict):
            for period, value in raw_coverage.items():
                period = str(period or "").strip()
                if period not in ALLOWED_PERIODS:
                    continue
                amount = _amount(value)
                if amount is not None:
                    coverage[period] = amount

        # Preserve the same semantics as XLSX import: only students with at least
        # one payment mark participate in the snapshot.
        if not coverage:
            continue

        monthly_amount = _amount(raw.get("monthly_amount"))
        if monthly_amount is None:
            monthly_amount = coverage.get(payments.PAYMENT_PERIODS[0][0])
        if monthly_amount is None:
            monthly_amount = next(iter(coverage.values()))

        students.append(
            {
                "source_key": source_key,
                "display_name": name,
                "monthly_amount": monthly_amount,
                "coverage": coverage,
            }
        )

    if not students:
        raise ValueError("no_payments")

    return students


def _payment_sheets_do_post(self):
    parsed = urlparse(self.path)
    if parsed.path != SYNC_PATH:
        return _previous_do_post(self)

    expected_secret = os.getenv("SHEETS_SYNC_SECRET", "")
    supplied_secret = parse_qs(parsed.query).get("secret", [""])[0]
    if not expected_secret or supplied_secret != expected_secret:
        self._send_json(401, {"ok": False, "error": "unauthorized"})
        return

    try:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_body or "{}")
    except Exception:
        self._send_json(400, {"ok": False, "error": "invalid_json"})
        return

    try:
        students = _students_from_payload(payload)
        source_title = str(payload.get("spreadsheet_title") or "Google Sheets")
        source_name = f"Google Sheets: {source_title} / {payments.PAYMENT_SHEET_NAME}"
        student_count, coverage_count = payments.save_payment_snapshot(
            students, source_name
        )
        payment_schedule.ensure_payment_plans()
    except ValueError as exc:
        self._send_json(
            400,
            {"ok": False, "error": str(exc) or "invalid_payload"},
        )
        return
    except Exception as exc:
        print(
            "Google Sheets payment sync error:",
            type(exc).__name__,
            flush=True,
        )
        self._send_json(500, {"ok": False, "error": "storage_error"})
        return

    current_period = payments._current_course_period()
    current_paid = 0
    if current_period:
        current_paid = sum(
            1
            for student in students
            if current_period in student.get("coverage", {})
        )

    print(
        "Google Sheets payment sync:",
        student_count,
        "students,",
        coverage_count,
        "coverage marks",
        flush=True,
    )
    self._send_json(
        200,
        {
            "ok": True,
            "students": student_count,
            "coverage_count": coverage_count,
            "current_period": current_period,
            "current_paid": current_paid,
        },
    )


bot.CoreAppWebhookHandler.do_POST = _payment_sheets_do_post


def verify_installation():
    if bot.CoreAppWebhookHandler.do_POST is not _payment_sheets_do_post:
        raise RuntimeError("Payment Sheets sync HTTP wrapper is not active")
    print(
        f"Payment Google Sheets sync ready: POST {SYNC_PATH}",
        flush=True,
    )


verify_installation()
