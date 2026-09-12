"""Temporary read-only smoke test for parent admin screens after schema migration."""
import parent_admin_ui
import parent_invite_campaign

checks = [
    ("parents_text", lambda: parent_admin_ui.parents_text()),
    ("parents_markup", lambda: parent_admin_ui.parents_markup()),
    ("student_picker_markup", lambda: parent_admin_ui.student_picker_markup()),
    ("linked_text", lambda: parent_admin_ui.linked_text()),
    ("campaign_text", lambda: parent_invite_campaign.campaign_text()),
]

failed = []
for name, fn in checks:
    try:
        value = fn()
        size = len(str(value))
        print(f"PARENT_SMOKE {name}=ok size={size}", flush=True)
    except Exception as exc:
        failed.append(name)
        print(f"PARENT_SMOKE {name}=FAIL {type(exc).__name__}: {exc}", flush=True)

if failed:
    raise RuntimeError("Parent smoke checks failed: " + ", ".join(failed))
print("PARENT_SMOKE all_ok", flush=True)
