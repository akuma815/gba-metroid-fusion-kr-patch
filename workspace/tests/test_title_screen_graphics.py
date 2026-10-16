from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import title_screen_graphics as title
from rombuild import load_source


class TitleScreenGraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = load_source()
        cls.plan = title.build_plan(cls.rom, [(0x700000, 0x780000)], [])

    def test_reference_identity_and_native_dimensions(self):
        reference = title.APPROVED_REFERENCE if title.APPROVED_REFERENCE.is_file() else title.REFERENCE
        digest = title.APPROVED_REFERENCE_SHA256 if title.APPROVED_REFERENCE.is_file() else title.REFERENCE_SHA256
        self.assertEqual(title.sha256(reference.read_bytes()), digest)
        self.assertEqual(self.plan["preview"]["reference"].size, (240, 160))

    def test_title_layer_fits_original_bg1_contract(self):
        assets = {item["asset_id"]: item for item in self.plan["assets"]}
        self.assertEqual(len(assets["title_logo_graphics_ko"]["decoded"]), 0x8000)
        self.assertEqual(len(assets["title_logo_tilemap_ko"]["decoded"]), 0x800)
        self.assertEqual(len(self.plan["palette"]), 0x100)
        self.assertLessEqual(self.plan["unique_tiles"], 896)

    def test_shared_file_select_palette_is_preserved_byte_for_byte(self):
        source = self.rom[
            title.LOGO_PALETTE_OFFSET:
            title.LOGO_PALETTE_OFFSET + title.LOGO_PALETTE_BYTES
        ]
        self.assertEqual(self.plan["palette"], source)
        self.assertEqual(title.sha256(source), title.LOGO_PALETTE_SHA256)

    def test_compressed_assets_self_roundtrip(self):
        for asset in self.plan["assets"]:
            restored, consumed = title.decompress_gba_lz77(asset["compressed"])
            self.assertEqual(restored, asset["decoded"])
            self.assertLessEqual(consumed, len(asset["compressed"]))


if __name__ == "__main__":
    unittest.main()
