from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import ui_graphics_audit as audit
from rombuild import load_source


class UiGraphicsAuditTests(unittest.TestCase):
    def test_game_over_asset_boundary(self):
        report = audit.build_report(load_source())
        asset = report["assets"][0]
        self.assertEqual(asset["file_offset"], "0x73B6F0")
        self.assertEqual(asset["byte_length"], 1760)
        self.assertEqual(asset["format"], "GBA LZ77 type 0x10 -> 4bpp 8x8 tiles")
        self.assertEqual(asset["compressed_bytes_consumed"], 1759)
        self.assertEqual(asset["trailing_padding_bytes"], 1)
        self.assertEqual(asset["decoded_byte_length"], 6144)
        self.assertEqual(asset["tile_count"], 192)
        self.assertEqual(audit.GAME_OVER_TEXT_OFFSET + audit.GAME_OVER_TEXT_BYTES, audit.GAME_OVER_PALETTE_OFFSET)

    def test_lz77_decoder_rejects_non_stream(self):
        with self.assertRaises(ValueError):
            audit.decompress_gba_lz77(b"not lz77")

    def test_pause_runtime_stream_boundaries(self):
        report = audit.build_report(load_source())
        assets = {asset["asset_id"]: asset for asset in report["assets"]}
        first = assets["pause_preloaded_tileset_a"]
        second = assets["pause_preloaded_tileset_b"]
        self.assertEqual(first["file_offset"], "0x56C930")
        self.assertEqual(first["compressed_bytes_consumed"], 9746)
        self.assertEqual(first["decoded_byte_length"], 32768)
        self.assertEqual(first["status"], "confirmed_pause_status_tileset")
        self.assertEqual(first["background_palette_offset"], "0x567E84")
        self.assertEqual(second["file_offset"], "0x571DF8")
        self.assertEqual(second["compressed_bytes_consumed"], 13613)
        self.assertEqual(second["decoded_byte_length"], 32768)
        self.assertEqual(second["status"], "confirmed_pause_map_chrome_tileset")
        for asset_id, _ in audit.PAUSE_TILEMAP_STREAMS:
            self.assertEqual(assets[asset_id]["decoded_byte_length"], 2048)
            self.assertEqual(assets[asset_id]["entry_count"], 1024)
        self.assertEqual(
            assets["pause_tilemap_05"]["screen_mapping_status"],
            "confirmed_status_screen_composition_with_tileset_a",
        )


if __name__ == "__main__":
    unittest.main()
