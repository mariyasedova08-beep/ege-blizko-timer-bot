"""The pen experiment is present only in the inert sandbox bundle."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy'))
from build_lab_sandbox import build
from lab_isolated_data import load_candidate

class PenComparison(unittest.TestCase):
    def test_sandbox_contains_local_engine_and_comparison_but_source_app_does_not(self):
        bundle=json.loads(build());html=gzip.decompress(base64.b64decode(bundle['html_gzip_base64'])).decode()
        self.assertIn('id="penCompareOpen"',html);self.assertIn('id="penCompareCanvas"',html)
        self.assertNotIn('__PFH_VENDOR__',html);self.assertIn('window.LabPenFreehand=',html)
        self.assertNotIn('id="penCompare"',load_candidate()['HTML'])
        for name in ['preview/pen-comparison.html','vendor/perfect-freehand/index.cjs','vendor/perfect-freehand/LICENSE','deploy/build_lab_sandbox.py']:
            self.assertEqual(bundle['source_sha256'][name],hashlib.sha256((ROOT/name).read_bytes()).hexdigest())

    def test_vendored_engine_matches_provenance_and_includes_license(self):
        root=ROOT/'vendor/perfect-freehand';meta=json.loads((root/'PROVENANCE.json').read_text())
        self.assertEqual(meta['version'],'1.2.3');self.assertEqual(meta['license'],'MIT')
        self.assertEqual(meta['sha256'],hashlib.sha256((root/'index.cjs').read_bytes()).hexdigest())
        self.assertIn('Permission is hereby granted',(root/'LICENSE').read_text())
