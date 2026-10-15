"""PREPODMIN-only approved subject and theme catalog.

Assets are in the isolated PREPODMIN deployment allowlist. Never read
teacher-provided SVG or arbitrary theme paths.
"""
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent / "deployment" / "prepodmin" / "design"
_CATALOG = json.loads((_ROOT / "catalog.json").read_text(encoding="utf-8"))
_ICONS = json.loads((_ROOT / "icons.json").read_text(encoding="utf-8"))

SUBJECTS = tuple(_CATALOG["subjects"])
THEMES = tuple(_CATALOG["themes"])
DEFAULT_THEME_ID = _CATALOG["defaultThemeId"]
_BY_ID = {item["id"]: item for item in SUBJECTS}
_THEMES_BY_ID = {item["id"]: item for item in THEMES}
_ALIASES = {}
for _item in SUBJECTS:
    for _alias in (_item["name"], _item["shortName"], *_item["legacyAliases"]):
        _ALIASES[" ".join(_alias.strip().casefold().split())] = _item["id"]

if len(SUBJECTS) != 15 or len(_BY_ID) != 15 or len(_ICONS) != 15:
    raise ValueError("The approved subject catalog must contain exactly 15 unique SVG icons")
if len(THEMES) != 14 or len(_THEMES_BY_ID) != 14 or DEFAULT_THEME_ID not in _THEMES_BY_ID:
    raise ValueError("The approved theme catalog must contain exactly 14 unique themes")
if set(_ICONS) != set(_BY_ID):
    raise ValueError("Subject icons and catalog IDs must match")


def subject_by_id(value):
    return _BY_ID.get(str(value or ""))


def subject_by_text(value):
    key = " ".join(str(value or "").strip().casefold().split())
    return subject_by_id(_ALIASES.get(key))


def subject_id_for_profile(row):
    """Resolve legacy text without rewriting it; never invent a subject ID."""
    if not row:
        return None
    stored_id = row["subject_id"] if "subject_id" in row.keys() else None
    item = subject_by_id(stored_id)
    if item:
        return item["id"]
    item = subject_by_text(row["subject"])
    return item["id"] if item else None


def theme_by_id(value):
    return _THEMES_BY_ID.get(str(value or ""))


def public_subjects():
    """Trusted SVG strings, never derived from a teacher's free-form input."""
    return [
        {"id": s["id"], "name": s["name"], "shortName": s["shortName"],
         "examLevels": s["examLevels"], "icon_svg": _ICONS[s["id"]]}
        for s in SUBJECTS
    ]


def public_themes():
    return list(THEMES)
