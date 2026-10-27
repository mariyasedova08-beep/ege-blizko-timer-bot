import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('november_patch',ROOT/'deploy/november_theme_patch.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


class ThemePatchTests(unittest.TestCase):
    def html(self):
        return ('<!doctype html><html lang="ru"><head><style>body{color:black}</style></head>'
                '<body><main id="app"></main><script>const paymentDeadline="7 ноября";'
                'const examDate="31 октября";fetch("/admin-app/api");</script></body></html>').encode()

    def test_original_logic_and_markup_preserved_for_both_roles(self):
        original = self.html()
        original_scripts = re.findall(rb'<script[^>]*>(.*?)</script>',original,re.S)
        for role in ('teacher','student'):
            result = p.transform(original,role)
            self.assertEqual(re.findall(rb'<script[^>]*>(.*?)</script>',result,re.S)[:-1],original_scripts)
            styles = p.START+'\n<style id="ege-november-theme">\n'+(ROOT/'ege_november_theme.css').read_text()+'\n</style>\n'
            scripts = p.SCRIPT+'\n<script id="ege-november-decor" data-cabinet-role="'+role+'">\n'+(ROOT/'ege_november_theme.js').read_text()+'\n</script>\n'
            self.assertEqual(result.replace(styles.encode(),b'').replace(scripts.encode(),b''),original)

    def test_repeat_is_exactly_idempotent(self):
        for role in ('teacher','student'):
            result = p.transform(self.html(),role)
            self.assertEqual(p.transform(result,role),result)
            self.assertEqual(result.count(p.START.encode()),1)
            self.assertEqual(result.count(p.SCRIPT.encode()),1)

    def test_changed_or_partial_theme_is_not_overwritten(self):
        changed = p.transform(self.html(),'teacher').replace(b'--ink:#242025',b'--ink:#000000')
        with self.assertRaisesRegex(ValueError,'EXISTING_THEME_DIFFERS'):
            p.transform(changed,'teacher')
        with self.assertRaisesRegex(ValueError,'EXISTING_THEME_DIFFERS'):
            p.transform(self.html().replace(b'</head>',p.START.encode()+b'</head>'),'teacher')

    def test_unknown_role_and_structure_stop(self):
        with self.assertRaisesRegex(ValueError,'INVALID_ROLE'): p.transform(self.html(),'parent')
        with self.assertRaisesRegex(ValueError,'UNKNOWN_HTML'): p.transform(b'<html></html>','student')


if __name__=='__main__': unittest.main()
