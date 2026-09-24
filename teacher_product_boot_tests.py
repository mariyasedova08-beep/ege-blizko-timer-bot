"""Run the PREPADMIN regression suite in an isolated subprocess at boot.

The subprocess boundary prevents test DB-path mutations from leaking into the live
process. A regression failure stops the deployment before Telegram polling starts.
"""
import subprocess
import sys


TEST_MODULES = (
    "teacher_product_onboarding_test",
    "teacher_product_reset_test",
    "teacher_product_student_reminders_test",
    "teacher_product_transfer_button_test",
    "teacher_product_webapp_test",
)


def run():
    cmd = [sys.executable, "-m", "unittest", *TEST_MODULES]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=90,
        check=False,
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        print("PREPADMIN REGRESSION TESTS failed", flush=True)
        if output:
            print(output[-8000:], flush=True)
        raise RuntimeError("PREPADMIN regression suite failed")
    summary = output.splitlines()[-1] if output else "OK"
    print(f"PREPADMIN REGRESSION TESTS ok: {summary}", flush=True)
    return True
