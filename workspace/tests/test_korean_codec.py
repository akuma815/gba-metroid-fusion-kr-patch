from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import korean_codec as codec
from rombuild import load_source


class KoreanCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code_map = codec.load_json(codec.CODE_MAP_PATH)
        cls.profile = codec.load_json(codec.FONT_PROFILE_PATH)
        cls.mapping = codec.character_map(cls.code_map)
        cls.report = codec.build_report(load_source(), cls.code_map, cls.profile)

    def test_full_corpus_encodes_without_missing_literals(self):
        encoding = self.report["encoding"]
        self.assertEqual(encoding["entry_count"], 349)
        self.assertEqual(encoding["serialized_bytes"], 45328)
        self.assertTrue(encoding["all_terminated_ff00"])
        self.assertEqual(encoding["unmapped_literals"], 0)
        self.assertEqual(encoding["curly_quote_alias_occurrences"], 8)

    def test_curly_quotes_alias_without_editing_text(self):
        self.assertEqual(self.mapping["‘"], 0x0047)
        self.assertEqual(self.mapping["’"], 0x0047)
        self.assertEqual(codec.encode_korean("‘X’{end}", self.mapping), [0x0047, 0x0098, 0x0047, 0xFF00])

    def test_unmapped_and_unterminated_text_fail(self):
        with self.assertRaises(codec.KoreanCodecError):
            codec.encode_korean("한글★{end}", self.mapping)
        with self.assertRaises(codec.KoreanCodecError):
            codec.encode_korean("한글", self.mapping)

    def test_unused_sequence_alias_is_not_silently_accepted(self):
        self.assertNotIn("”", self.mapping)
        with self.assertRaises(codec.KoreanCodecError):
            codec.encode_korean("”{end}", self.mapping)

    def test_bitmap_payload_is_complete_and_nonoverlapping(self):
        payload = self.report["font_payload"]
        self.assertEqual(payload["mapped_glyphs"], 546)
        self.assertEqual(payload["tile_writes"], 2184)
        self.assertEqual(payload["changed_tiles"], 2181)
        self.assertEqual(payload["byte_identical_tiles"], 3)
        offsets = [int(item["offset"], 0) for item in payload["writes"]]
        self.assertEqual(len(offsets), len(set(offsets)))


if __name__ == "__main__":
    unittest.main()
