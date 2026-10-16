from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import korean_codec as kc
import text_centering as centering
from rombuild import load_source


class TextCenteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = load_source()
        cls.mapping = kc.character_map(kc.load_json(kc.CODE_MAP_PATH))

    def test_replaces_only_the_first_line_start_control(self):
        source = "{ctrl:8001}가나{ctrl:8030}다라{end}"
        updated, changes = centering.center_text(source, self.rom, self.mapping)
        self.assertRegex(updated, r"^\{ctrl:80[0-9A-F]{2}\}가나")
        self.assertIn("가나{ctrl:8030}다라{end}", updated)
        self.assertEqual(updated.count("{ctrl:8030}"), 1)
        self.assertEqual(len(changes), 1)

    def test_inserts_a_missing_control_only_at_line_start(self):
        source = "{ctrl:8001}가나{br}다라{glyph:030A}{end}"
        updated, changes = centering.center_text(source, self.rom, self.mapping)
        second = updated.split("{br}")[1]
        self.assertRegex(second, r"^\{ctrl:80[0-9A-F]{2}\}다라")
        self.assertEqual(len(changes), 2)

    def test_four_hangul_cells_center_to_8054(self):
        updated, _ = centering.center_text("{ctrl:8000}가나다라{end}", self.rom, self.mapping)
        self.assertEqual(updated, "{ctrl:8054}가나다라{end}")

    def test_non_target_rows_are_untouched(self):
        rows = [{"entry_id": "navigation/ja/000", "한국어_번역": "{ctrl:8000}가{end}"}]
        self.assertEqual(centering.apply_rows(rows, self.rom, self.mapping), [])
        self.assertEqual(rows[0]["한국어_번역"], "{ctrl:8000}가{end}")


if __name__ == "__main__":
    unittest.main()
