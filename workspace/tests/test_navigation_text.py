from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import navigation_text as nt
from rombuild import load_source


class NavigationTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = load_source()
        cls.cfg = nt.load_format()
        cls.catalog = json.loads(nt.CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_roundtrip(self):
        result = nt.verify_catalog(self.catalog, self.rom, self.cfg)
        self.assertEqual(result["entries"], 1575)
        self.assertEqual(result["pointer_bytes"], 6300)
        self.assertEqual(result["text_bytes"], 410468)

    def test_translation_binding(self):
        translation = json.loads(nt.TRANSLATION_PATH.read_text(encoding="utf-8"))
        result = nt.verify_translation(self.catalog, translation)
        self.assertEqual(result["entries"], 225)

    def test_changed_token_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["languages"][0]["entries"][0]["source_tokens"] += "{br}"
        with self.assertRaises(nt.NavigationTextError):
            nt.verify_catalog(changed, self.rom, self.cfg)

    def test_changed_pointer_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["languages"][0]["entries"][0]["pointer_raw_hex"] = "00000000"
        with self.assertRaises(nt.NavigationTextError):
            nt.verify_catalog(changed, self.rom, self.cfg)

    def test_unmapped_literal_is_rejected(self):
        with self.assertRaises(nt.NavigationTextError):
            nt.encode_tokens("한")

    def test_extended_glyph_roundtrip(self):
        self.assertEqual(nt.decode_units([0x15D6]), "{glyph:15D6}")
        self.assertEqual(nt.encode_tokens("{glyph:15D6}"), [0x15D6])


if __name__ == "__main__":
    unittest.main()
