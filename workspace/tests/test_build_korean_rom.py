from __future__ import annotations

import sys
import struct
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import build_korean_rom as build
from font_codec import decode_tile
from rombuild import ROM_SIZE


class KoreanRomBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder, cls.report = build.build()

    def test_build_stays_8mib_and_uses_only_reclaimed_text_space(self):
        self.assertEqual(len(self.builder.buf), ROM_SIZE)
        allocation = self.report["allocation"]
        self.assertEqual(allocation["available_bytes"], 109288)
        self.assertEqual(allocation["used_bytes"], 43146)
        self.assertEqual(
            allocation["remaining_bytes"],
            allocation["available_bytes"]
            - allocation["used_bytes"]
            - allocation["pause_ui_graphics_bytes"]
            - allocation["title_graphics_bytes"],
        )
        self.assertGreater(allocation["remaining_bytes"], 0)
        suffix = allocation["file_select_suffix_layout"]
        self.assertEqual(suffix["entry_count"], 14)
        self.assertEqual(suffix["physical_bytes"], 266)

    def test_file_select_suffix_aliases_share_one_physical_block(self):
        allocations = build.allocate_strings(
            build.tc.build_rows(),
            build.kc.character_map(build.kc.load_json(build.kc.CODE_MAP_PATH)),
            build.reclaim_ranges(
                build.tc.load_json(build.tc.SOURCE_FILES["navigation"]),
                build.tc.load_json(build.tc.SOURCE_FILES["additional"]),
                build.tc.load_json(build.tc.SOURCE_FILES["file_select"]),
            ),
        )[0]
        parent = allocations["file_select/ja/011"]
        previous = parent["offset"]
        for index in range(12, 25):
            item = allocations[f"file_select/ja/{index:03d}"]
            self.assertEqual(item["alias_parent_entry_id"], "file_select/ja/011")
            self.assertGreater(item["offset"], previous)
            self.assertEqual(item["write_raw"], b"")
            self.assertTrue(item["raw"].endswith(b"\x00\xFF"))
            previous = item["offset"]

    def test_choice_controls_keep_yes_and_no_after_position_controls(self):
        for entry_id in ("message/ja/043", "message/ja/044"):
            self.assertIn("{ctrl:8340}예 ", build.RUNTIME_LAYOUT_OVERRIDES[entry_id])
            self.assertIn("{ctrl:83A0}아니요", build.RUNTIME_LAYOUT_OVERRIDES[entry_id])

    def test_runtime_strings_use_centered_line_start_controls(self):
        allocations = build.allocate_strings(
            build.tc.build_rows(),
            build.kc.character_map(build.kc.load_json(build.kc.CODE_MAP_PATH)),
            build.reclaim_ranges(
                build.tc.load_json(build.tc.SOURCE_FILES["navigation"]),
                build.tc.load_json(build.tc.SOURCE_FILES["additional"]),
                build.tc.load_json(build.tc.SOURCE_FILES["file_select"]),
            ),
        )[0]
        location_units = tuple(
            int.from_bytes(allocations["location/ja/000"]["raw"][i:i + 2], "little")
            for i in range(0, len(allocations["location/ja/000"]["raw"]), 2)
        )
        self.assertEqual(location_units[0], 0x8057)
        message_units = tuple(
            int.from_bytes(allocations["message/ja/007"]["raw"][i:i + 2], "little")
            for i in range(0, len(allocations["message/ja/007"]["raw"]), 2)
        )
        line_break = message_units.index(0xFE00)
        self.assertEqual(message_units[line_break + 1], 0x8000)
        choice_units = tuple(
            int.from_bytes(allocations["message/ja/043"]["raw"][i:i + 2], "little")
            for i in range(0, len(allocations["message/ja/043"]["raw"]), 2)
        )
        self.assertEqual(choice_units[0], 0x804D)
        self.assertIn(0x8340, choice_units)
        self.assertIn(0x83A0, choice_units)
        message_045 = tuple(
            int.from_bytes(allocations["message/ja/045"]["raw"][i:i + 2], "little")
            for i in range(0, len(allocations["message/ja/045"]["raw"]), 2)
        )
        message_046 = tuple(
            int.from_bytes(allocations["message/ja/046"]["raw"][i:i + 2], "little")
            for i in range(0, len(allocations["message/ja/046"]["raw"]), 2)
        )
        self.assertEqual(message_045[0], 0x8026)
        self.assertEqual(message_045[message_045.index(0xFE00) + 1], 0x801F)
        self.assertEqual(message_046[0], 0x8029)
        self.assertEqual(message_046[message_046.index(0xFE00) + 1], 0x803D)

    def test_japanese_only_first_run_rows_do_not_append_korean_to_source_glyphs(self):
        for index in range(25, 29):
            text = build.RUNTIME_LAYOUT_OVERRIDES[f"file_select/ja/{index:03d}"]
            self.assertNotRegex(text, r"\{glyph:[0-9A-F]{4}\}")
            self.assertTrue(text.endswith("{end}"))

    def test_difficulty_options_are_on_separate_lines(self):
        self.assertEqual(
            build.RUNTIME_LAYOUT_OVERRIDES["file_select/ja/026"],
            "게임 레벨{br}EASY{br}NORMAL{end}",
        )
        self.assertEqual(
            build.RUNTIME_LAYOUT_OVERRIDES["file_select/ja/027"],
            "게임 레벨{br}EASY{br}NORMAL{br}HARD{end}",
        )

    def test_complete_pointer_and_font_population(self):
        writes = self.report["writes"]
        self.assertEqual(writes["text_strings"], 349)
        self.assertEqual(writes["pointer_fields"], 696)
        self.assertEqual(writes["font_tiles"], 2184)
        self.assertEqual(writes["width_table_entries"], 88)
        self.assertEqual(self.report["verification"]["japanese_mode_shared_targets"], 347)

    def test_file_select_save_summary_uses_korean_obj_graphics(self):
        assets = {
            item["asset_id"]: item
            for item in self.report["writes"]["pause_ui_graphics_assets"]
        }
        labels = assets["file_select_obj_tileset_ko"]["labels"]
        self.assertEqual(
            [(item["source"], item["ko"]) for item in labels],
            [
                ("メインデッキ", "메인 덱"),
                ("SECTOR", "섹터"),
                ("EASY / やさしい", "쉬움"),
                ("NORMAL / ふつう", "보통"),
                ("HARD / むずかしい", "어려움"),
            ],
        )

    def test_ui_vram_streams_do_not_use_distance_one_matches(self):
        for asset in self.report["writes"]["pause_ui_graphics_assets"]:
            start = int(asset["target_offset"], 0)
            stream = self.builder.buf[start:]
            self.assertEqual(stream[0], 0x10)
            output_size = int.from_bytes(stream[1:4], "little")
            source = 4
            produced = 0
            while produced < output_size:
                flags = stream[source]
                source += 1
                for bit in range(7, -1, -1):
                    if produced >= output_size:
                        break
                    if flags & (1 << bit):
                        first, second = stream[source], stream[source + 1]
                        source += 2
                        length = (first >> 4) + 3
                        distance = ((first & 0x0F) << 8 | second) + 1
                        self.assertGreaterEqual(distance, 2, asset["asset_id"])
                        produced += length
                    else:
                        source += 1
                        produced += 1

    def test_target_sprite_erases_both_rows_but_preserves_chrome(self):
        assets = {
            item["asset_id"]: item
            for item in build.uig.build_decoded_assets(self.builder.source)
        }
        modified = assets["pause_map_chrome_tileset_ko"]["decoded"]
        source, _ = build.uig.decompress_gba_lz77(self.builder.source[0x571DF8:])
        for top_ids, bottom_ids, old_ink in (
            (range(727, 731), range(759, 763), 7),
            (range(731, 735), range(763, 767), 2),
        ):
            top_tiles = [
                decode_tile(modified[tile_id * 32:(tile_id + 1) * 32])
                for tile_id in top_ids
            ]
            for y in range(8):
                row = sum((tile[y] for tile in top_tiles), [])
                for x in tuple(range(8)) + tuple(range(24, 32)):
                    self.assertNotEqual(row[x], old_ink)
            for tile_id in tuple(top_ids) + tuple(bottom_ids):
                before = decode_tile(source[tile_id * 32:(tile_id + 1) * 32])
                after = decode_tile(modified[tile_id * 32:(tile_id + 1) * 32])
                for y in range(8):
                    for x in range(8):
                        if before[y][x] in (8, 14):
                            self.assertEqual(after[y][x], before[y][x])

    def test_open_security_label_is_replaced_with_centered_korean(self):
        assets = {
            item["asset_id"]: item
            for item in build.uig.build_decoded_assets(self.builder.source)
        }
        modified = assets["pause_map_chrome_tileset_ko"]["decoded"]
        tiles = [
            decode_tile(modified[tile_id * 32:(tile_id + 1) * 32])
            for tile_id in (492, 493)
        ]
        canvas = [sum((tile[y] for tile in tiles), []) for y in range(8)]
        self.assertTrue(all(pixel in (0, 1, 13, 14) for row in canvas for pixel in row))
        self.assertTrue(any(pixel == 1 for row in canvas for pixel in row))
        self.assertTrue(any(pixel == 13 for row in canvas for pixel in row))
        self.assertGreater(sum(pixel == 14 for row in canvas for pixel in row), 10)

    def test_sleep_and_status_labels_clear_source_and_center_in_cells(self):
        assets = {
            item["asset_id"]: item
            for item in build.uig.build_decoded_assets(self.builder.source)
        }
        modified = assets["pause_map_chrome_tileset_ko"]["decoded"]
        source, _ = build.uig.decompress_gba_lz77(self.builder.source[0x571DF8:])
        for tile_ids, clear_rect, glyph_x in (
            (range(891, 896), (9, 1, 36, 7), 14),
            (range(923, 928), (4, 1, 31, 7), 9),
        ):
            before_tiles = [
                decode_tile(source[tile_id * 32:(tile_id + 1) * 32])
                for tile_id in tile_ids
            ]
            after_tiles = [
                decode_tile(modified[tile_id * 32:(tile_id + 1) * 32])
                for tile_id in tile_ids
            ]
            left, top, right, bottom = clear_rect
            for y in range(8):
                for x in range(40):
                    tile = x // 8
                    px = x % 8
                    protected = not (left <= x < right and top <= y < bottom)
                    glyph_cell = glyph_x <= x < glyph_x + 16 and 1 <= y < 8
                    if protected and not glyph_cell:
                        self.assertEqual(after_tiles[tile][y][px], before_tiles[tile][y][px])
            self.assertTrue(any(
                after_tiles[x // 8][y][x % 8] == 2
                for y in range(1, 8)
                for x in range(glyph_x, glyph_x + 16)
            ))
        self.assertEqual(
            modified[927 * 32:928 * 32],
            source[927 * 32:928 * 32],
        )

    def test_status_item_korean_uses_dedicated_tiles_and_only_status_map_cells(self):
        assets = {
            item["asset_id"]: item
            for item in build.uig.build_decoded_assets(self.builder.source)
        }
        status = assets["pause_status_tileset_ko"]
        source_tiles, _ = build.uig.decompress_gba_lz77(self.builder.source[0x56C930:])
        modified_tiles = status["decoded"]
        for tile_id in range(1024):
            before = source_tiles[tile_id * 32:(tile_id + 1) * 32]
            if before != bytes(32):
                self.assertEqual(modified_tiles[tile_id * 32:(tile_id + 1) * 32], before)

        expected_labels = {
            "CHARGE", "WIDE", "PLASMA", "WAVE", "ICE_BEAM",
            "SUPER", "ICE_MISSILE", "DIFFUSION", "POWER",
            "VARIA", "GRAVITY", "MORPH BALL", "HI-JUMP",
            "SPEED BOOSTER", "SPACE JUMP", "SCREW ATTACK",
        }
        translated_labels = {item["source"] for item in status["labels"]}
        self.assertTrue(expected_labels.issubset(translated_labels))
        self.assertTrue({
            "ENERGY", "MISSILE_COUNTER", "P.BOMB_COUNTER", "BEAM", "SUIT",
            "MISSILE_CATEGORY", "BOMB_CATEGORY", "MISC_CATEGORY",
        }.isdisjoint(translated_labels))

        source_map, _ = build.uig.decompress_gba_lz77(self.builder.source[0x576FB0:])
        modified_map = assets["pause_tilemap_05"]["decoded"]
        before_entries = struct.unpack("<1024H", source_map)
        after_entries = struct.unpack("<1024H", modified_map)
        changed = {index for index, pair in enumerate(zip(before_entries, after_entries)) if pair[0] != pair[1]}
        allowed = set()
        for label in status["labels"]:
            if "pause_tilemap_05" not in label.get("maps", ()) or label.get("in_place"):
                continue
            for x, y in label["positions"]:
                allowed.update(y * 32 + x + index for index in range(len(label["tiles"])))
        self.assertTrue(changed)
        self.assertTrue(changed.issubset(allowed))

        # SPEED BOOSTER's final R shares a tile with the panel's right border.
        # Only color 8 (the Latin glyph) may be cleared from that final tile;
        # every chrome pixel must survive unchanged.
        speed_entry = after_entries[28 * 32 + 28]
        speed_tile = build.uig.decode_tile(
            modified_tiles[(speed_entry & 0x3FF) * 32:((speed_entry & 0x3FF) + 1) * 32]
        )
        source_speed_tile = build.uig.decode_tile(source_tiles[250 * 32:251 * 32])
        for y in range(8):
            for x in range(8):
                expected = 13 if source_speed_tile[y][x] == 8 else source_speed_tile[y][x]
                self.assertEqual(speed_tile[y][x], expected)

    def test_static_verification_passes_without_undeclared_diffs(self):
        self.builder.verify()
        self.assertEqual(self.report["status"], "static_build_pass_runtime_qa_pending")
        self.assertEqual(self.report["output"]["rom_size"], ROM_SIZE)
        self.assertEqual(len(self.report["output"]["rom_sha256"]), 64)

    def test_korean_title_reference_is_rebuilt_as_two_bg_assets(self):
        title = self.report["writes"]["title_graphics"]
        expected = (build.tsg.APPROVED_REFERENCE_SHA256 if build.tsg.APPROVED_REFERENCE.is_file()
                    else build.tsg.REFERENCE_SHA256)
        self.assertEqual(title["reference_sha256"], expected)
        self.assertLessEqual(title["unique_tiles"], 896)
        self.assertGreater(title["opaque_pixels"], 10000)
        self.assertEqual(
            [item["asset_id"] for item in title["assets"]],
            ["title_logo_graphics_ko", "title_logo_tilemap_ko"],
        )
        self.assertEqual(self.report["verification"]["title_graphics_assets"], 2)

    def test_title_build_does_not_modify_shared_file_select_palette(self):
        start = build.tsg.LOGO_PALETTE_OFFSET
        end = start + build.tsg.LOGO_PALETTE_BYTES
        self.assertEqual(self.builder.buf[start:end], self.builder.source[start:end])
        self.assertEqual(
            self.report["writes"]["title_graphics"]["palette_policy"],
            "preserve original shared title and file-select palette byte-for-byte",
        )

    def test_original_root_korean_rom_is_not_the_output(self):
        self.assertNotEqual(
            build.OUTPUT_ROM.resolve(),
            (PROJECT / "Metroid Fusion (Korean).gba").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
