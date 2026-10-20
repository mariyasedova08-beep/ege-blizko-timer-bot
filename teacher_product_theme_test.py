"""Theme settings tests: isolated PREPODMIN data, no network or deployment."""
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

import teacher_product_mvp as base
import teacher_product_subjects as catalog
import teacher_product_webapp as webapp


class ThemeCatalogTest(unittest.TestCase):
    def test_approved_palettes_are_complete(self):
        self.assertEqual(len(catalog.THEMES), 14)
        self.assertEqual(len({t["id"] for t in catalog.THEMES}), 14)
        self.assertEqual(catalog.DEFAULT_THEME_ID, "pink-pulse")
        self.assertEqual(catalog.theme_by_id("pink-pulse")["colors"]["accent"], "#F00087")
        self.assertEqual(catalog.theme_by_id("rose-ash")["name"], "Пепел розы")
        self.assertTrue(catalog.theme_by_id("night")["isDark"])
        self.assertFalse(catalog.theme_by_id("mint")["isDark"])
        required = {"background", "soft", "accent", "button", "text",
                    "surface", "muted", "border", "onButton"}
        for theme in catalog.THEMES:
            self.assertEqual(set(theme["colors"]), required)
            for color in theme["colors"].values():
                self.assertRegex(color, r"^#[0-9A-Fa-f]{6}$")

    def test_auto_expand_desktop_only_where_telegram_supports_it(self):
        """Exercise the launch helper in Node without a real bot or browser."""
        import subprocess

        html = Path(webapp.HTML_PATH).read_text(encoding="utf-8")
        start = html.index("function initializePrepadminViewport(app){")
        end = html.index("var tg=", start)
        helper = html[start:end]
        script = helper + """
const assert = require('node:assert/strict');
function simulate(platform, modern, fullscreen, requestWorks=true) {
  const calls=[];
  const app={
    platform: platform,
    isFullscreen: fullscreen,
    ready(){calls.push('ready')},
    expand(){calls.push('expand')},
    isVersionAtLeast(v){assert.equal(v,'8.0');return modern},
    requestFullscreen(){calls.push('fullscreen');if(!requestWorks)throw Error('unsupported')}
  };
  initializePrepadminViewport(app);
  return calls;
}
assert.deepEqual(simulate('tdesktop',true,false), ['ready','expand','fullscreen']);
assert.deepEqual(simulate('macos',true,false), ['ready','expand','fullscreen']);
assert.deepEqual(simulate('android',true,false), ['ready','expand']);
assert.deepEqual(simulate('ios',true,false), ['ready','expand']);
assert.deepEqual(simulate('tdesktop',false,false), ['ready','expand']);
assert.deepEqual(simulate('tdesktop',true,true), ['ready','expand']);
assert.deepEqual(simulate('tdesktop',true,false,false), ['ready','expand','fullscreen']);
initializePrepadminViewport(null);
console.log('PREPODMIN_DESKTOP_VIEWPORT_OK');
"""
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PREPODMIN_DESKTOP_VIEWPORT_OK", result.stdout)

    def test_html_has_theme_ui_and_live_palette_tokens(self):
        html = Path(webapp.HTML_PATH).read_text(encoding="utf-8")
        for token in ("function renderSettings(", "function applyTheme(",
                      "function saveTheme(", "function cancelTheme(",
                      "aria-pressed", "data-theme", "--on-button",
                      "--bottom", "data-theme-dark",
                      "Темы кабинета", "action:'theme_update'"):
            self.assertIn(token, html)


    def test_prepodmin_light_typography_and_independent_branding(self):
        teacher = Path(webapp.HTML_PATH).read_text(encoding="utf-8")
        self.assertNotIn("<span>как в ЕГЭ БЛИЗКО</span>", teacher)
        # A calm five-tab navigation replaces the former giant home tile catalog.
        self.assertIn('id="nav-more"', teacher)
        self.assertIn("function renderMore()", teacher)
        self.assertNotIn("<strong>Все разделы</strong></div>", teacher)
        for token in (
            ".brand-wordmark{font-size:23px;font-weight:720",
            "h1{font-size:clamp(27px,5vw,32px);font-weight:670",
            ".section-title strong{font-size:17px;font-weight:640",
            ".subject-tile span{font-size:12px;font-weight:530",
            ".theme-name{font-size:13px;font-weight:590",
        ):
            self.assertIn(token, teacher)
        # All user themes still use live CSS palette variables.
        self.assertIn("function applyTheme(", teacher)
        self.assertIn("var(--soft)", teacher)
        self.assertIn("var(--hot)", teacher)


    def test_elegant_cabinet_matches_ege_blizko_font_and_outline_icons(self):
        teacher = Path(webapp.HTML_PATH).read_text(encoding="utf-8")
        student = Path("ege_student_webapp.html").read_text(encoding="utf-8")
        font = 'Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif'
        self.assertIn(font, teacher)
        self.assertIn(font, student)
        for fragment in (
            "brand-wordmark", "top-kicker", "function uiIcon(name)",
            "function hydrateNavIcons()", 'data-ui-icon="home"',
            "more-link-icon", "uiIcon(icon)", "var(--soft)",
            "var(--paper)", "var(--hot)", "var(--muted)",
        ):
            self.assertIn(fragment, teacher)
        self.assertNotIn("card('📚'", teacher)
        self.assertNotIn("card('🚨'", teacher)


class ThemeSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base.DB_PATH = os.path.join(self.tmp.name, "theme.sqlite3")
        base.ensure_tables()
        base.upsert_teacher(700, name="Мария", subject="Химия",
                            subject_id="chemistry", work_format="groups",
                            onboarding_completed_at="2026-10-10")
        base.upsert_teacher(701, name="Елена", subject="Биология",
                            subject_id="biology", work_format="individual",
                            theme_id="rose-ash", onboarding_completed_at="2026-10-10")
        with base.db() as conn:
            conn.execute(
                "INSERT INTO students(teacher_telegram_user_id,name,contact,created_at) "
                "VALUES(?,?,?,?)",
                (700, "Ученик", "@test", "2026-10-01"),
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_theme_selection_persists_for_all_fourteen(self):
        self.assertEqual(webapp._theme_state(700)["id"], "pink-pulse")
        self.assertEqual(webapp._view(700, "settings")["theme_id"], "pink-pulse")
        self.assertEqual(len(webapp._view(700, "settings")["themes"]), 14)
        for theme in catalog.THEMES:
            response = webapp._teacher_action(700, {
                "action": "theme_update", "theme_id": theme["id"],
            })
            self.assertTrue(response["ok"])
            self.assertEqual(response["theme_id"], theme["id"])
            self.assertEqual(response["theme"]["colors"], theme["colors"])
            self.assertEqual(webapp._theme_state(700)["id"], theme["id"])
            self.assertEqual(webapp._view(700, "settings")["theme_id"], theme["id"])

    def test_other_teacher_and_records_remain_untouched(self):
        response = webapp._teacher_action(700, {
            "action": "theme_update", "theme_id": "night",
            "teacher_id": 701,  # Must never change another teacher.
        })
        self.assertTrue(response["ok"])
        self.assertEqual(base.teacher(700)["theme_id"], "night")
        self.assertEqual(base.teacher(700)["name"], "Мария")
        self.assertEqual(base.teacher(700)["subject"], "Химия")
        self.assertEqual(base.teacher(700)["subject_id"], "chemistry")
        self.assertEqual(base.teacher(700)["work_format"], "groups")
        self.assertEqual(base.teacher(700)["onboarding_completed_at"], "2026-10-10")
        self.assertEqual(base.teacher(701)["theme_id"], "rose-ash")
        self.assertEqual(base.teacher(701)["subject"], "Биология")
        with base.db() as conn:
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM students WHERE teacher_telegram_user_id=700"
            ).fetchone()[0], 1)

    def test_rejects_invalid_theme_without_changes(self):
        for value in ("", "unknown", "../../etc/passwd", "pink-pulse;DROP TABLE teachers", None):
            result = webapp._teacher_action(700, {
                "action": "theme_update", "theme_id": value,
            })
            self.assertEqual(result["error"], "invalid_theme_id")
            self.assertEqual(base.teacher(700)["theme_id"], "pink-pulse")
        self.assertEqual(webapp._teacher_action(999, {
            "action": "theme_update", "theme_id": "night",
        })["error"], "profile_not_found")

    def test_unknown_saved_theme_falls_back_without_overwriting(self):
        base.upsert_teacher(700, theme_id="legacy-unknown")
        self.assertEqual(webapp._theme_state(700)["id"], "pink-pulse")
        self.assertEqual(webapp._view(700, "settings")["theme_id"], "pink-pulse")
        self.assertEqual(base.teacher(700)["theme_id"], "legacy-unknown")


if __name__ == "__main__":
    unittest.main()
