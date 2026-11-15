import unittest
from prepare_december_theme import decorate


class ReviewCopyTests(unittest.TestCase):
    def test_original_working_markup_is_retained(self):
        source = '<html><head><title>Тест</title></head><body><canvas id="ink"></canvas><button onclick="work()">Работа</button></body></html>'
        for surface in ('student', 'teacher', 'lab'):
            result = decorate(source, surface)
            self.assertIn('<canvas id="ink"></canvas><button onclick="work()">Работа</button>', result)
            self.assertIn('data-enabled="false"', result)
            self.assertIn('data-surface="' + surface + '"', result)

    def test_release_date_uses_moscow_midnight(self):
        result = decorate('<html><head></head><body></body></html>', 'student', True)
        self.assertIn('2026-11-30T21:00:00Z', result)
        self.assertIn('data-enabled="true"', result)

    def test_repeated_injection_is_refused(self):
        result = decorate('<html><head></head><body></body></html>', 'teacher')
        with self.assertRaises(ValueError):
            decorate(result, 'teacher')

    def test_partial_document_is_refused(self):
        with self.assertRaises(ValueError):
            decorate('<section id="lesson"></section>', 'lab')

    def test_wrong_surface_is_refused(self):
        with self.assertRaises(ValueError):
            decorate('<html><head></head><body></body></html>', 'prepodmin')
