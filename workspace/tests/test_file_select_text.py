from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import file_select_text as fst
from rombuild import load_source


class FileSelectTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = load_source()
        cls.cfg = fst.load_format()
        cls.catalog = json.loads(fst.CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_roundtrip(self):
        result = fst.verify_catalog(self.catalog, self.rom, self.cfg)
        self.assertEqual(result["entries"], 185)
        self.assertEqual(result["pointer_bytes"], 740)
        self.assertEqual(result["meta_bytes"], 56)

    def test_translation_binding(self):
        translation = json.loads(fst.TRANSLATION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(fst.verify_translation(self.catalog, translation)["entries"], 31)

    def test_suffix_alias_is_preserved(self):
        japanese = self.catalog["languages"][0]
        self.assertIn("internal_suffix_alias", japanese["entries"][12]["flags"])
        changed = copy.deepcopy(self.catalog)
        changed["languages"][0]["entries"][12]["alias"]["delta_bytes"] += 2
        with self.assertRaises(fst.FileSelectTextError):
            fst.verify_catalog(changed, self.rom, self.cfg)

    def test_changed_pointer_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["languages"][0]["entries"][0]["pointer_raw_hex"] = "00000000"
        with self.assertRaises(fst.FileSelectTextError):
            fst.verify_catalog(changed, self.rom, self.cfg)


if __name__ == "__main__":
    unittest.main()
