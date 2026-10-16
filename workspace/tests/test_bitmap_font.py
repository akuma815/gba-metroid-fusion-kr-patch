from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import hangul_glyph as glyph
from font_codec import encode_fullwidth


class BitmapFontTests(unittest.TestCase):
    FONT = "Galmuri11-Condensed_9x12.png"

    def test_source_identity_and_layout(self):
        path = glyph.FONT_DIR / self.FONT
        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            "07A9617723AA4EDBFB18442DB86419C3F2B48E4F7C6E2E33229305ADCA582AA1",
        )
        image = glyph._load_bitmap_sheet(self.FONT)
        self.assertEqual(image.size, (576, 2100))
        # 64*175=11200칸 중 가~힣 11172칸 뒤의 28칸은 완전 투명해야 한다.
        self.assertIsNone(image.crop((36 * 9, 174 * 12, 576, 2100)).getbbox())

    def test_full_hangul_inventory_has_no_empty_glyph(self):
        for codepoint in range(glyph.HANGUL_FIRST, glyph.HANGUL_LAST + 1):
            rows = glyph.sheet_bitmap(chr(codepoint), self.FONT)
            self.assertEqual((len(rows[0]), len(rows)), (9, 12))
            self.assertTrue(any(value for row in rows for value in row))

    def test_poc_glyphs_fit_game_cell_and_encode(self):
        for ch in "한글표시검토":
            rows = glyph.outline(
                glyph.render_sheet_bitmap(ch, self.FONT, at=(1, 1)), body=2, edge=3
            )
            x0, x1, y0, y1 = glyph.extent(rows)
            self.assertLessEqual(x1 - x0 + 1, 12)
            self.assertLessEqual(y1 - y0 + 1, 16)
            encoded = encode_fullwidth(rows)
            self.assertEqual(set(encoded), {"left_top", "right_top", "left_bottom", "right_bottom"})
            self.assertTrue(all(len(tile) == 32 for tile in encoded.values()))

    def test_non_precomposed_character_is_rejected(self):
        with self.assertRaises(ValueError):
            glyph.sheet_bitmap("A", self.FONT)


if __name__ == "__main__":
    unittest.main()
