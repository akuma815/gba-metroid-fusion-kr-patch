from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import font_slot_audit as audit
from rombuild import load_source


class FontSlotAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = load_source()
        cls.inventory = audit.load_json(audit.CODE_USAGE_PATH)
        cls.corpus = audit.load_json(audit.CORPUS_PATH)
        cls.report = audit.build_audit(cls.rom, cls.inventory)

    def test_two_japanese_modes_scenario_and_width_boundary(self):
        self.assertEqual(self.report["scenario"]["candidate_count"], 724)
        self.assertEqual(self.report["scenario"]["physical_tile_count"], 2896)
        self.assertEqual(self.report["scenario"]["replaced_languages"], ["ja", "ja_hiragana"])
        self.assertEqual(self.report["width_policy"]["expected_instruction_hex"], "0A20")
        self.assertEqual(self.report["width_policy"]["patched_instruction_hex"], "0C20")

    def test_direct_pointer_shape_is_compressed_data_not_live_reference(self):
        pointers = self.report["candidate_physical_pointer_audit"]
        self.assertEqual(pointers["raw_aligned_address_occurrences"], 1)
        self.assertEqual(pointers["live_thumb_literal_references"], 0)
        self.assertEqual(pointers["unclassified_occurrences"], 0)
        self.assertEqual(pointers["compressed_false_positives"], 1)
        self.assertEqual(
            pointers["occurrences"][0]["classification"],
            "word_shaped_bytes_inside_confirmed_lz77_stream",
        )

    def test_known_font_base_consumers_are_accounted_for(self):
        model = self.report["font_consumer_model"]
        self.assertEqual(model["font_base_thumb_literal_count"], 5)
        self.assertEqual(
            sum(item["consumer"].startswith("numeric") for item in model["font_base_thumb_literals"]),
            1,
        )

    def test_code_map_is_complete_and_disjoint(self):
        code_map = audit.build_code_map(self.report, self.corpus)
        self.assertEqual(code_map["statistics"]["required_hangul"], 546)
        self.assertEqual(code_map["statistics"]["candidate_cells"], 724)
        self.assertEqual(code_map["statistics"]["unassigned_candidate_cells"], 178)
        codes = [int(item["code"], 0) for item in code_map["mappings"]]
        tiles = [audit.footprint(code) for code in codes]
        self.assertEqual(len(set(codes)), len(codes))
        self.assertEqual(len(set().union(*tiles)), len(codes) * 4)
        self.assertEqual(code_map["policy"]["curly_quote_aliases"]["U+2018"], "0x0047")
        self.assertEqual(code_map["policy"]["literal_sequence_aliases"], {})


if __name__ == "__main__":
    unittest.main()
