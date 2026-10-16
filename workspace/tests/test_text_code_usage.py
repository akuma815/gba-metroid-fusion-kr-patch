from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import additional_text as at
import file_select_text as fst
import navigation_text as nt
import text_code_usage as usage
from rombuild import load_source


class TextCodeUsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = load_source()
        cls.nav = json.loads(nt.CATALOG_PATH.read_text(encoding="utf-8"))
        cls.additional = json.loads(at.CATALOG_PATH.read_text(encoding="utf-8"))
        cls.file_select = json.loads(fst.CATALOG_PATH.read_text(encoding="utf-8"))
        cls.inventory = usage.build_inventory(cls.rom, cls.nav, cls.additional, cls.file_select)

    def test_population_and_candidates(self):
        self.assertEqual(self.inventory["scope"]["entry_count"], 2411)
        self.assertEqual(self.inventory["scope"]["text_bytes"], 559158)
        scenarios = {item["scenario_id"]: item for item in self.inventory["allocation_scenarios"]}
        self.assertEqual(scenarios["replace_ja_preserve_hiragana_and_western"]["candidate_count"], 581)
        self.assertEqual(scenarios["replace_both_japanese_modes_preserve_western"]["candidate_count"], 724)

    def test_extended_japanese_glyphs_are_counted(self):
        japanese = next(item for item in self.inventory["languages"] if item["language_id"] == "ja")
        self.assertEqual(japanese["unique_glyph_codes"], 865)
        self.assertEqual(japanese["glyph_max"], "0x15DA")

    def test_physical_tile_footprint(self):
        self.assertEqual(usage.physical_tiles(0x800, 12), {0x800, 0x801, 0x820, 0x821})
        self.assertEqual(usage.physical_tiles(0x800, 8), {0x800, 0x820})


if __name__ == "__main__":
    unittest.main()
