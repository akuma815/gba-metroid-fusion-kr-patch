from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import additional_text as at
from rombuild import load_source


class AdditionalTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = load_source()
        cls.cfg = at.load_format()
        cls.catalog = json.loads(at.CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_roundtrip(self):
        result = at.verify_catalog(self.catalog, self.rom, self.cfg)
        self.assertEqual(result["entries"], 651)
        self.assertEqual(result["pointer_bytes"], 2604)
        self.assertEqual(result["meta_bytes"], 84)

    def test_translation_binding(self):
        translation = json.loads(at.TRANSLATION_PATH.read_text(encoding="utf-8"))
        result = at.verify_translation(self.catalog, translation)
        self.assertEqual(result["entries"], 93)

    def test_changed_token_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["populations"][0]["languages"][0]["entries"][0]["source_tokens"] += "{br}"
        with self.assertRaises(at.AdditionalTextError):
            at.verify_catalog(changed, self.rom, self.cfg)

    def test_changed_meta_pointer_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        raw = bytearray.fromhex(changed["populations"][0]["meta_table_raw_hex"])
        raw[0] ^= 4
        changed["populations"][0]["meta_table_raw_hex"] = raw.hex().upper()
        with self.assertRaises(at.AdditionalTextError):
            at.verify_catalog(changed, self.rom, self.cfg)

    def test_changed_pointer_is_rejected(self):
        changed = copy.deepcopy(self.catalog)
        changed["populations"][0]["languages"][0]["entries"][0]["pointer_raw_hex"] = "00000000"
        with self.assertRaises(at.AdditionalTextError):
            at.verify_catalog(changed, self.rom, self.cfg)


if __name__ == "__main__":
    unittest.main()
