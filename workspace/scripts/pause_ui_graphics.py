"""Build Korean Pause-map and Status baked UI tile sets for Fusion JP."""
from __future__ import annotations

import hashlib
import struct
from collections import defaultdict
from pathlib import Path

from PIL import Image

from font_codec import decode_tile, encode_tile
from rombuild import PROJECT
from ui_graphics_audit import decompress_gba_lz77

GBA_ROM_BASE = 0x08000000
SMALL_FONT = PROJECT.parents[1] / "Font" / "Galmuri7_8x8.png"
SMALL_FONT_SHA256 = "A2BE473E22A62942164C95DB60F3F5AA88A99F76B525994D194E9F5F9DF387EA"

ASSETS = (
    {
        "asset_id": "pause_status_tileset_ko",
        "source_offset": 0x56C930,
        "pointer_offset": 0x0772EC,
        "expected_pointer": 0x0856C930,
        "labels": (
            # Counter labels keep their tilemap palette attributes so acquired
            # and disabled states continue to select the original color banks.
            {"source": "ENERGY", "ko": "에너지", "tiles": tuple(range(2, 9)), "erase": (8,), "erase_rows": (2, 7), "background": 10, "foreground": 8, "y": 1, "maps": ("pause_tilemap_05",), "positions": ((2, 2),), "hits": 1},
            {"source": "MISSILE_COUNTER", "ko": "미사일", "tiles": tuple(range(11, 19)), "erase": (8,), "erase_rows": (2, 7), "background": 10, "foreground": 8, "y": 1, "maps": ("pause_tilemap_05",), "positions": ((12, 2),), "hits": 1},
            {"source": "P.BOMB_COUNTER", "ko": "파워봄", "tiles": tuple(range(19, 27)), "erase": (8,), "erase_rows": (2, 7), "background": 10, "foreground": 8, "y": 1, "maps": ("pause_tilemap_05",), "positions": ((21, 2),), "hits": 1},
            # Category bars reserve rows 0, 1 and 7 for their chrome borders.
            {"source": "BEAM", "ko": "빔", "tiles": tuple(range(234, 238)), "erase": (8,), "erase_rows": (0, 7), "background": 14, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((2, 5), (2, 21)), "hits": 2},
            {"source": "SUIT", "ko": "슈트", "tiles": (331, 332, 333), "erase": (8,), "erase_rows": (0, 7), "background": 14, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((20, 8), (20, 21)), "hits": 2},
            # The ability-list panels occupy the lower part of the 32x32 map.
            # Item rows use the category heading as context, so the translated
            # graphic keeps the source's modifier-only wording.
            {"source": "MISSILE_CATEGORY", "ko": "미사일", "tiles": (266, 267, 268, 269, 270), "erase": (8,), "erase_rows": (0, 7), "background": 14, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((10, 21),), "hits": 1},
            {"source": "BOMB_CATEGORY", "ko": "봄", "tiles": (299, 300, 301, 302), "erase": (8,), "erase_rows": (0, 7), "background": 14, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((2, 28),), "hits": 1},
            {"source": "MISC_CATEGORY", "ko": "기타", "tiles": (363, 364, 365, 366), "erase": (8,), "erase_rows": (0, 7), "background": 14, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((20, 25),), "hits": 1},
            {"source": "CHARGE", "ko": "차지", "tiles": (426, 427, 428, 429, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((3, 22),), "hits": 1},
            {"source": "WIDE", "ko": "와이드", "tiles": (458, 459, 460, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((3, 23),), "hits": 1},
            {"source": "PLASMA", "ko": "플라스마", "tiles": (490, 491, 492, 493, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((3, 24),), "hits": 1},
            {"source": "WAVE", "ko": "웨이브", "tiles": (522, 523, 524, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((3, 25),), "hits": 1},
            {"source": "ICE_BEAM", "ko": "아이스", "tiles": (554, 555, 461, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((3, 26),), "hits": 1},
            {"source": "SUPER", "ko": "슈퍼", "tiles": (398, 399, 400, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((11, 22),), "hits": 1},
            {"source": "ICE_MISSILE", "ko": "아이스", "tiles": (430, 431, 461, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((11, 23),), "hits": 1},
            {"source": "DIFFUSION", "ko": "디퓨전", "tiles": (462, 463, 464, 465, 466), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((11, 24),), "hits": 1},
            {"source": "POWER", "ko": "파워", "tiles": (494, 495, 496, 497, 461, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((3, 29),), "hits": 1},
            {"source": "VARIA", "ko": "배리어", "tiles": (526, 527, 528, 529, 461, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((21, 22),), "hits": 1},
            {"source": "GRAVITY", "ko": "그래비티", "tiles": (558, 559, 560, 561, 461, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((21, 23),), "hits": 1},
            {"source": "MORPH BALL", "ko": "모프볼", "tiles": (586, 587, 588, 589, 590, 591, 592), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((21, 26),), "hits": 1},
            {"source": "HI-JUMP", "ko": "하이 점프", "tiles": (618, 619, 620, 621, 461, 461, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((21, 27),), "hits": 1},
            {"source": "SPEED BOOSTER", "ko": "스피드 부스터", "tiles": (243, 244, 245, 246, 247, 248, 249, 250), "erase": (8,), "fill_tile_indexes": tuple(range(7)), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((21, 28),), "hits": 1},
            {"source": "SPACE JUMP", "ko": "스페이스 점프", "tiles": (275, 276, 277, 278, 279, 280, 461), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((21, 29),), "hits": 1},
            {"source": "SCREW ATTACK", "ko": "스크루 어택", "tiles": (307, 308, 309, 310, 311, 312, 313), "erase": (8,), "background": 13, "foreground": 8, "y": 0, "maps": ("pause_tilemap_05",), "positions": ((21, 30),), "hits": 1},
        ),
    },
    {
        "asset_id": "pause_map_chrome_tileset_ko",
        "source_offset": 0x571DF8,
        "pointer_offset": 0x0772CC,
        "expected_pointer": 0x08571DF8,
        "labels": (
            {"source": "LOCK", "ko": "잠김", "tiles": (460, 461), "erase": (), "fill_rows": (1, 8), "background": 0, "foreground": 5, "y": 0, "obj_source_span": (460, 461), "obj_target_span": (460, 461), "obj_edit_tiles": (0, 1)},
            # An unlocked security level uses a distinct 16x8 OBJ. Preserve
            # its dark panel (index 14), white body (1), and shadow (13).
            {"source": "OPEN", "ko": "해제", "tiles": (492, 493), "erase": (), "fill_rows": (1, 8), "background": 14, "foreground": 1, "outline": 13, "y": 0, "obj_source_span": (492, 493), "obj_target_span": (492, 493), "obj_edit_tiles": (0, 1)},
            # TARGET is a 32x16 OBJ in 2D mapping mode. Its upper row starts at
            # 727/731 and lower row at +32. Earlier builds edited only the
            # lower row, leaving the top strokes of TARGET above 목표.
            {"source": "TARGET_BOX_DIM", "ko": "목표", "erase": (7,), "background": 6, "foreground": 7, "obj_width_tiles": 4, "obj_y": 6, "obj_source_span": tuple(range(727, 731)) + tuple(range(759, 763)), "obj_target_span": tuple(range(727, 731)) + tuple(range(759, 763))},
            {"source": "TARGET_BOX_ACTIVE", "ko": "목표", "erase": (2,), "background": 13, "foreground": 2, "obj_width_tiles": 4, "obj_y": 6, "obj_source_span": tuple(range(731, 735)) + tuple(range(763, 767)), "obj_target_span": tuple(range(731, 735)) + tuple(range(763, 767))},
            {"source": "SLEEP", "ko": "슬립", "background": 4, "foreground": 2, "obj_width_tiles": 5, "obj_height_tiles": 1, "clear_rect": (9, 1, 36, 7), "obj_x": 14, "obj_y": 1, "obj_source_span": tuple(range(891, 896)), "obj_target_span": tuple(range(891, 896))},
            {"source": "MAIN DECK", "ko": "메인 덱", "tiles": tuple(range(917, 923)), "erase": (8,), "erase_rows": (1, 6), "background": 10, "foreground": 8, "y": 0, "obj_source_span": tuple(range(917, 923)), "obj_target_span": tuple(range(917, 923)), "obj_edit_tiles": tuple(range(6))},
            # The fifth tile is the separate R prompt and must remain intact.
            {"source": "STATUS", "ko": "상태", "background": 4, "foreground": 2, "obj_width_tiles": 5, "obj_height_tiles": 1, "clear_rect": (4, 1, 31, 7), "obj_x": 9, "obj_y": 1, "obj_source_span": tuple(range(923, 928)), "obj_target_span": tuple(range(923, 928))},
            {"source": "OBJECTIVE", "ko": "목표", "tiles": tuple(range(976, 984)), "erase": (), "fill_rows": (1, 8), "background": 0, "foreground": 2, "y": 0, "obj_source_span": tuple(range(976, 984)), "obj_target_span": tuple(range(976, 984)), "obj_edit_tiles": tuple(range(8))},
        ),
    },
    {
        "asset_id": "file_select_obj_tileset_ko",
        "source_offset": 0x73D7E0,
        "pointer_offset": 0x09F90C,
        "expected_pointer": 0x0873D7E0,
        "labels": (
            # File-select save summaries are sprite graphics, not entries in
            # the ordinary file-select/location text pointer tables. The GBA
            # is in 2D OBJ mapping mode here, so the lower 8-pixel row begins
            # 32 tile indices after the upper row.
            {"source": "メインデッキ", "ko": "메인 덱", "sprite_base": 0x1D7},
            {"source": "SECTOR", "ko": "섹터", "sprite_base": 0x1D3},
            # Keep the original six descriptors (English and kana modes), but
            # redirect both sets to these three non-overlapping Korean tiles.
            {"source": "EASY / やさしい", "ko": "쉬움", "sprite_base": 0x284},
            {"source": "NORMAL / ふつう", "ko": "보통", "sprite_base": 0x288},
            {"source": "HARD / むずかしい", "ko": "어려움", "sprite_base": 0x28C},
        ),
    },
)

TILEMAPS = (
    {"asset_id": "pause_tilemap_02", "source_offset": 0x576800, "pointer_offset": 0x0774D8, "expected_pointer": 0x08576800},
    {"asset_id": "pause_tilemap_03", "source_offset": 0x5769EC, "pointer_offset": 0x077444, "expected_pointer": 0x085769EC},
    {"asset_id": "pause_tilemap_04", "source_offset": 0x576CAC, "pointer_offset": 0x0774EC, "expected_pointer": 0x08576CAC},
    {"asset_id": "pause_tilemap_05", "source_offset": 0x576FB0, "pointer_offset": 0x077470, "expected_pointer": 0x08576FB0},
)


class PauseUiError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _load_font() -> Image.Image:
    data = SMALL_FONT.read_bytes()
    if sha256(data) != SMALL_FONT_SHA256:
        raise PauseUiError("Galmuri7_8x8.png SHA-256 mismatch")
    image = Image.open(SMALL_FONT).convert("RGBA")
    if image.size != (512, 1400):
        raise PauseUiError(f"unexpected small font size {image.size}")
    return image


def _glyph_mask(font: Image.Image, character: str) -> list[list[bool]]:
    if not ("가" <= character <= "힣"):
        raise PauseUiError(f"unsupported small-font character {character!r}")
    index = ord(character) - 0xAC00
    x0 = index % 64 * 8
    y0 = index // 64 * 8
    return [
        [font.getpixel((x0 + x, y0 + y))[:3] == (99, 207, 99) for x in range(8)]
        for y in range(8)
    ]


def _edit_label(tiles: list[list[list[int]]], label: dict, font: Image.Image) -> None:
    tile_ids = label["tiles"]
    erase_tile_ids = label.get("erase_tiles", tile_ids)
    erase = set(label["erase"])
    background = label["background"]
    fill_rows = label.get("fill_rows")
    is_status_label = label.get("maps") == ("pause_tilemap_05",)
    if is_status_label:
        # Item rows are eight pixels tall. Headings use Galmuri7's seven
        # visible rows at y=1..7, keeping the top chrome line intact.
        fill_rows = (0, 8) if background == 13 else (1, 8)
    status_source_x = 0
    if is_status_label:
        source_pixels = [
            tile_index * 8 + x
            for tile_index, tile_id in enumerate(tile_ids)
            for y in range(fill_rows[0], fill_rows[1])
            for x in range(8)
            if tiles[tile_id][y][x] in erase
        ]
        if source_pixels:
            status_source_x = min(source_pixels)
    erase_rows = label.get("erase_rows", (0, 8))
    fill_tile_indexes = set(label.get("fill_tile_indexes", range(len(erase_tile_ids))))
    for erase_index, tile_id in enumerate(erase_tile_ids):
        tile = tiles[tile_id]
        for y in range(8):
            for x in range(8):
                if ((erase_rows[0] <= y < erase_rows[1] and tile[y][x] in erase)
                        or (fill_rows and erase_index in fill_tile_indexes
                            and fill_rows[0] <= y < fill_rows[1])):
                    tile[y][x] = background

    glyphs = [None if ch == " " else _glyph_mask(font, ch) for ch in label["ko"]]
    if len(glyphs) > len(tile_ids):
        raise PauseUiError(f"{label['source']} Korean label exceeds its tile span")
    # Status labels follow the source label's first tile.  Centering short
    # Korean strings made them drift away from the panel's bullet/left edge.
    start = 0 if is_status_label or label.get("align") == "left" else (len(tile_ids) - len(glyphs)) // 2
    y_offset = label.get("status_y", 1) if is_status_label else label.get("y", 0)
    if is_status_label and background != 13:
        row_pairs = tuple((row, row) for row in range(7))
    else:
        row_pairs = tuple((row, row) for row in range(7 if is_status_label else 8))
    for slot, mask in enumerate(glyphs):
        if mask is None:
            continue
        for output_y, sy in row_pairs:
            dy = output_y + y_offset
            if dy >= 8:
                continue
            for x in range(8):
                if mask[sy][x]:
                    if is_status_label:
                        px = status_source_x + slot * 8 + x
                        tile_index, tile_x = divmod(px, 8)
                        if tile_index >= len(tile_ids):
                            continue
                        tiles[tile_ids[tile_index]][dy][tile_x] = label["foreground"]
                        continue
                    tile = tiles[tile_ids[start + slot]]
                    if "outline" in label:
                        for ox, oy in ((1, 0), (0, 1)):
                            if x + ox < 8 and dy + oy < 8:
                                tile[dy + oy][x + ox] = label["outline"]
                    tile[dy][x] = label["foreground"]


def _edit_file_select_sprite_label(
    tiles: list[list[list[int]]], label: dict, font: Image.Image,
) -> None:
    """Render a centered Galmuri7 label into a 32x16 2D-mapped OBJ."""
    width, height = 32, 16
    placements = []
    cursor = 0
    for character in label["ko"]:
        if character == " ":
            cursor += 4
            continue
        placements.append((cursor, _glyph_mask(font, character)))
        cursor += 7
    content_width = 0 if not placements else placements[-1][0] + 8
    start_x = max(0, (width - content_width) // 2)
    start_y = 4
    foreground = set()
    for glyph_x, mask in placements:
        for y, row in enumerate(mask):
            for x, enabled in enumerate(row):
                px = start_x + glyph_x + x
                py = start_y + y
                if enabled and 0 <= px < width and 0 <= py < height:
                    foreground.add((px, py))

    canvas = [[0 for _ in range(width)] for _ in range(height)]
    for x, y in foreground:
        for oy in (-1, 0, 1):
            for ox in (-1, 0, 1):
                px, py = x + ox, y + oy
                if (0 <= px < width and 0 <= py < height
                        and (px, py) not in foreground):
                    canvas[py][px] = 3
    for x, y in foreground:
        canvas[y][x] = 2

    base = label["sprite_base"]
    target_ids = tuple(range(base, base + 4)) + tuple(range(base + 32, base + 36))
    if base >= 0x280:
        for tile_id in target_ids:
            if any(pixel for row in tiles[tile_id] for pixel in row):
                raise PauseUiError(f"file-select target tile 0x{tile_id:X} is not empty")
    for tile_id in target_ids:
        tiles[tile_id] = [[0 for _ in range(8)] for _ in range(8)]
    for y in range(height):
        for x in range(width):
            tile_id = base + (x // 8) + (32 if y >= 8 else 0)
            tiles[tile_id][y % 8][x % 8] = canvas[y][x]


def _edit_2d_obj_label(
    tiles: list[list[list[int]]], label: dict, font: Image.Image,
) -> None:
    """Replace text inside a two-row 2D-mapped OBJ while retaining chrome."""
    width_tiles = label["obj_width_tiles"]
    if len(tiles) != width_tiles * 2:
        raise PauseUiError(f"{label['source']} unexpected 2D OBJ tile span")
    erase = set(label["erase"])
    background = label["background"]
    for tile in tiles:
        for y in range(8):
            for x in range(8):
                if tile[y][x] in erase:
                    tile[y][x] = background

    glyphs = [None if ch == " " else _glyph_mask(font, ch) for ch in label["ko"]]
    if len(glyphs) > width_tiles:
        raise PauseUiError(f"{label['source']} Korean label exceeds its OBJ width")
    start_tile = (width_tiles - len(glyphs)) // 2
    start_y = label["obj_y"]
    for slot, mask in enumerate(glyphs):
        if mask is None:
            continue
        for sy, row in enumerate(mask):
            py = start_y + sy
            if not 0 <= py < 16:
                continue
            for x, enabled in enumerate(row):
                if enabled:
                    tile_index = (py // 8) * width_tiles + start_tile + slot
                    tiles[tile_index][py % 8][x] = label["foreground"]


def _edit_obj_canvas_label(
    tiles: list[list[list[int]]], label: dict, font: Image.Image,
) -> None:
    """Clear a protected OBJ text cell and place Hangul at exact pixel bounds."""
    width_tiles = label["obj_width_tiles"]
    height_tiles = label["obj_height_tiles"]
    if len(tiles) != width_tiles * height_tiles:
        raise PauseUiError(f"{label['source']} unexpected OBJ canvas span")
    left, top, right, bottom = label["clear_rect"]
    for py in range(top, bottom):
        for px in range(left, right):
            tile_index = (py // 8) * width_tiles + px // 8
            tiles[tile_index][py % 8][px % 8] = label["background"]

    start_x = label["obj_x"]
    start_y = label["obj_y"]
    for slot, character in enumerate(label["ko"]):
        if character == " ":
            continue
        mask = _glyph_mask(font, character)
        for sy, row in enumerate(mask):
            py = start_y + sy
            if not 0 <= py < height_tiles * 8:
                continue
            for x, enabled in enumerate(row):
                px = start_x + slot * 8 + x
                if enabled and 0 <= px < width_tiles * 8:
                    tile_index = (py // 8) * width_tiles + px // 8
                    tiles[tile_index][py % 8][px % 8] = label["foreground"]


def build_decoded_assets(rom: bytes) -> list[dict]:
    font = _load_font()
    tilemaps: dict[str, dict] = {}
    for spec in TILEMAPS:
        decoded, consumed = decompress_gba_lz77(rom[spec["source_offset"]:])
        if len(decoded) != 2048:
            raise PauseUiError(f"{spec['asset_id']} decoded size {len(decoded)} != 2048")
        tilemaps[spec["asset_id"]] = {
            **spec,
            "source_consumed": consumed,
            "source_decoded_sha256": sha256(decoded),
            "entries": list(struct.unpack("<1024H", decoded)),
            "source_decoded": decoded,
        }

    result = []
    for spec in ASSETS:
        decoded, consumed = decompress_gba_lz77(rom[spec["source_offset"]:])
        if len(decoded) != 32768:
            raise PauseUiError(f"{spec['asset_id']} decoded size {len(decoded)} != 32768")
        tiles = [decode_tile(decoded[i:i + 32]) for i in range(0, len(decoded), 32)]
        runtime_tiles = [[row[:] for row in tile] for tile in tiles]
        runtime_tilemap_patches = []
        used_ids = {
            entry & 0x3FF
            for tilemap in tilemaps.values()
            for entry in tilemap["entries"]
        }
        free_ids = [
            index for index in range(1024)
            if decoded[index * 32:(index + 1) * 32] == bytes(32) and index not in used_ids
        ]
        free_cursor = 0
        tile_lookup = {
            decoded[index * 32:(index + 1) * 32]: index
            for index in range(1024)
        }
        active_labels = spec["labels"]
        if spec["asset_id"] == "pause_status_tileset_ko":
            # The five category headings and three top counters are only five
            # pixels high in the source UI and cannot hold readable Galmuri7.
            # Keep those source graphics intact; translate item rows only.
            active_labels = tuple(label for label in active_labels if label["background"] == 13)
        for label in active_labels:
            if "sprite_base" in label:
                _edit_file_select_sprite_label(tiles, label, font)
                continue
            if label.get("runtime_only"):
                source_ids = label["tiles"]
                edited = [[row[:] for row in tiles[tile_id]] for tile_id in source_ids]
                local_label = {**label, "tiles": tuple(range(len(source_ids)))}
                _edit_label(edited, local_label, font)
                target_ids = label["target_tiles"]
                for tile_id, tile in zip(target_ids, edited):
                    runtime_tiles[tile_id] = tile
                for map_id in label["maps"]:
                    entries = tilemaps[map_id]["entries"]
                    for x, y in label["positions"]:
                        base = y * 32 + x
                        actual = tuple(entries[base + i] & 0x3FF for i in range(len(source_ids)))
                        if actual != source_ids:
                            raise PauseUiError(f"{label['source']} runtime tilemap source mismatch")
                        new_entries = tuple(
                            (entries[base + i] & ~0x3FF) | target_ids[i]
                            for i in range(len(source_ids))
                        )
                        runtime_tilemap_patches.append({
                            "map_id": map_id, "x": x, "y": y,
                            "entries": new_entries,
                        })
                continue
            if "obj_source_span" in label:
                source_span = label["obj_source_span"]
                target_span = label["obj_target_span"]
                if len(source_span) != len(target_span):
                    raise PauseUiError(f"{label['source']} OBJ source/target span mismatch")
                edited = [[row[:] for row in tiles[tile_id]] for tile_id in source_span]
                if "clear_rect" in label:
                    _edit_obj_canvas_label(edited, label, font)
                elif "obj_width_tiles" in label:
                    _edit_2d_obj_label(edited, label, font)
                else:
                    local_label = {**label, "tiles": label["obj_edit_tiles"]}
                    _edit_label(edited, local_label, font)
                for tile_id, tile in zip(target_span, edited):
                    tiles[tile_id] = tile
                continue
            source_ids = label["tiles"]
            edited = [[row[:] for row in tiles[tile_id]] for tile_id in source_ids]
            local_label = {**label, "tiles": tuple(range(len(source_ids)))}
            _edit_label(edited, local_label, font)
            if label.get("in_place"):
                for tile_id, tile in zip(source_ids, edited):
                    tiles[tile_id] = tile
                continue

            if "target_tiles" in label:
                target_ids = label["target_tiles"]
                if len(target_ids) != len(edited):
                    raise PauseUiError(f"{label['source']} explicit target span mismatch")
                for tile_id, tile in zip(target_ids, edited):
                    tiles[tile_id] = tile
            else:
                target_ids_list = []
                for tile in edited:
                    raw = encode_tile(tile)
                    tile_id = tile_lookup.get(raw)
                    if tile_id is None:
                        if free_cursor >= len(free_ids):
                            raise PauseUiError(f"{spec['asset_id']} has insufficient unused zero tiles")
                        tile_id = free_ids[free_cursor]
                        free_cursor += 1
                        tiles[tile_id] = tile
                        tile_lookup[raw] = tile_id
                    target_ids_list.append(tile_id)
                target_ids = tuple(target_ids_list)

            hits = 0
            for map_id in label["maps"]:
                entries = tilemaps[map_id]["entries"]
                positions = label.get("positions")
                candidates = positions if positions else (
                    (x, y) for y in range(32) for x in range(33 - len(source_ids))
                )
                for x, y in candidates:
                        base = y * 32 + x
                        actual = tuple(entries[base + index] & 0x3FF for index in range(len(source_ids)))
                        if actual != source_ids:
                            continue
                        for index, target_id in enumerate(target_ids):
                            entry = entries[base + index]
                            if label.get("maps") == ("pause_tilemap_05",):
                                # Source Latin labels reuse flipped tiles. New
                                # Korean tiles are authored in screen order, so
                                # retain only the palette bank, not H/V flips.
                                entries[base + index] = (entry & 0xF000) | target_id
                            else:
                                entries[base + index] = (entry & ~0x3FF) | target_id
                        hits += 1
            if hits != label["hits"]:
                raise PauseUiError(
                    f"{spec['asset_id']} {label['source']} tilemap hits {hits} != {label['hits']}"
                )
        modified = b"".join(encode_tile(tile) for tile in tiles)
        result.append({
            **spec,
            "labels": active_labels,
            "source_consumed": consumed,
            "source_decoded_sha256": sha256(decoded),
            "decoded": modified,
            "decoded_sha256": sha256(modified),
            "runtime_decoded": b"".join(encode_tile(tile) for tile in runtime_tiles),
            "runtime_tilemap_patches": runtime_tilemap_patches,
        })

    for tilemap in tilemaps.values():
        modified = struct.pack("<1024H", *tilemap["entries"])
        if modified == tilemap["source_decoded"]:
            continue
        result.append({
            **{key: tilemap[key] for key in ("asset_id", "source_offset", "pointer_offset", "expected_pointer")},
            "labels": (),
            "source_consumed": tilemap["source_consumed"],
            "source_decoded_sha256": tilemap["source_decoded_sha256"],
            "decoded": modified,
            "decoded_sha256": sha256(modified),
        })
    return result


OBJ_TILE_REMAP = {
    0x1CC: 664,       # LOCK -> 잠김 (shared by L1-L4 rows)
    0x37B: 537,       # SLEEP 32x8 lead sprite
    0x37F: 541,       # SLEEP final 8x8 sprite
    0x395: 600,       # MAIN DECK 32x8 lead sprite
    0x399: 604,       # MAIN DECK final 16x8 sprite
    0x39B: 569,       # STATUS 32x8 lead sprite
    0x39F: 573,       # STATUS R prompt sprite (copied unchanged)
    0x3D0: 632,       # OBJECTIVE first 32x8 sprite
    0x3D4: 636,       # OBJECTIVE second 32x8 sprite
}


def oam_table_patches(rom: bytes, include_pause: bool = True) -> list[dict]:
    """Patch Pause OBJ frame records while preserving palette/priority bits."""
    patches = []
    if include_pause:
        for offset in range(0x568A00, 0x568D00, 2):
            old = struct.unpack_from("<H", rom, offset)[0]
            source_tile = old & 0x3FF
            target_tile = OBJ_TILE_REMAP.get(source_tile)
            if target_tile is None:
                continue
            new = (old & ~0x3FF) | target_tile
            patches.append({"offset": offset, "expected": struct.pack("<H", old), "new": struct.pack("<H", new)})
        required = {0x1CC, 0x37B, 0x37F, 0x395, 0x399, 0x39B, 0x39F, 0x3D0, 0x3D4}
        found = {struct.unpack("<H", item["expected"])[0] & 0x3FF for item in patches}
        if found != required:
            raise PauseUiError(f"Pause OBJ remap coverage mismatch: {sorted(found)}")
    for offset, source_tile, target_tile in (
        (0x745A14, 0x200, 0x284),  # EASY -> 쉬움
        (0x745A1C, 0x207, 0x288),  # NORMAL -> 보통
        (0x745A24, 0x203, 0x28C),  # HARD -> 어려움
        (0x745A2C, 0x20B, 0x284),  # やさしい -> 쉬움
        (0x745A34, 0x20E, 0x288),  # ふつう -> 보통
        (0x745A3C, 0x212, 0x28C),  # むずかしい -> 어려움
    ):
        old = struct.unpack_from("<H", rom, offset)[0]
        if (old & 0x3FF) != source_tile:
            raise PauseUiError(f"file-select OBJ source mismatch at 0x{offset:X}")
        new = (old & ~0x3FF) | target_tile
        patches.append({"offset": offset, "expected": struct.pack("<H", old), "new": struct.pack("<H", new)})
    return patches


def compress_gba_lz77(data: bytes) -> bytes:
    """Encode a type-0x10 stream safe for the BIOS VRAM halfword decoder.

    A distance-one overlapping match round-trips through the byte-oriented
    verifier but does not reproduce the same bytes when the game expands this
    asset directly into VRAM.  File-select window chrome shares the unchanged
    tiles in this stream, so forbid that match form for every UI VRAM asset.
    """
    if len(data) > 0xFFFFFF:
        raise PauseUiError("GBA LZ77 input exceeds 24-bit size")
    out = bytearray((0x10, len(data) & 0xFF, (len(data) >> 8) & 0xFF, (len(data) >> 16) & 0xFF))
    chains: dict[bytes, list[int]] = defaultdict(list)
    pos = 0
    while pos < len(data):
        flag_pos = len(out)
        out.append(0)
        flags = 0
        for bit in range(7, -1, -1):
            if pos >= len(data):
                break
            best_len = 0
            best_distance = 0
            if pos + 3 <= len(data):
                key = data[pos:pos + 3]
                candidates = chains.get(key, ())
                for candidate in reversed(candidates):
                    distance = pos - candidate
                    if distance > 4096:
                        break
                    if distance < 2:
                        continue
                    length = 3
                    maximum = min(18, len(data) - pos)
                    while length < maximum and data[candidate + length] == data[pos + length]:
                        length += 1
                    if length > best_len:
                        best_len = length
                        best_distance = distance
                        if length == maximum:
                            break
            if best_len >= 3:
                flags |= 1 << bit
                encoded_distance = best_distance - 1
                out.append(((best_len - 3) << 4) | (encoded_distance >> 8))
                out.append(encoded_distance & 0xFF)
                advance = best_len
            else:
                out.append(data[pos])
                advance = 1
            for current in range(pos, min(pos + advance, len(data))):
                if current + 3 <= len(data):
                    key = data[current:current + 3]
                    chain = chains[key]
                    chain.append(current)
                    while chain and current - chain[0] > 4096:
                        chain.pop(0)
            pos += advance
        out[flag_pos] = flags
    while len(out) % 4:
        out.append(0)
    restored, _ = decompress_gba_lz77(bytes(out))
    if restored != data:
        raise PauseUiError("GBA LZ77 self-roundtrip mismatch")
    return bytes(out)


def _free_intervals(ranges: list[tuple[int, int]], occupied: list[tuple[int, int]]) -> list[tuple[int, int]]:
    free = []
    for start, end in ranges:
        cursor = start
        for used_start, used_end in sorted(occupied):
            if used_end <= cursor or used_start >= end:
                continue
            if cursor < used_start:
                free.append((cursor, min(used_start, end)))
            cursor = max(cursor, used_end)
            if cursor >= end:
                break
        if cursor < end:
            free.append((cursor, end))
    return free


def build_plan(
    rom: bytes, ranges: list[tuple[int, int]], occupied: list[tuple[int, int]],
    include_asset_ids: set[str] | None = None,
) -> list[dict]:
    assets = build_decoded_assets(rom)
    if include_asset_ids is not None:
        assets = [asset for asset in assets if asset["asset_id"] in include_asset_ids]
    free = _free_intervals(ranges, occupied)
    free_index = 0
    cursor = free[0][0]
    plan = []
    for asset in assets:
        compressed = compress_gba_lz77(asset["decoded"])
        while True:
            cursor = (cursor + 3) & ~3
            if cursor + len(compressed) <= free[free_index][1]:
                break
            free_index += 1
            if free_index >= len(free):
                raise PauseUiError("reclaimed text space cannot hold Korean Pause UI graphics")
            cursor = free[free_index][0]
        plan.append({
            **asset,
            "compressed": compressed,
            "compressed_sha256": sha256(compressed),
            "target_offset": cursor,
            "target_pointer": GBA_ROM_BASE + cursor,
        })
        cursor += len(compressed)
    return plan


def verify_image(image: bytes, plan: list[dict]) -> None:
    for asset in plan:
        pointer = struct.unpack_from("<I", image, asset["pointer_offset"])[0]
        if pointer != asset["target_pointer"]:
            raise PauseUiError(f"{asset['asset_id']} pointer mismatch")
        decoded, consumed = decompress_gba_lz77(image[asset["target_offset"]:])
        if decoded != asset["decoded"] or consumed > len(asset["compressed"]):
            raise PauseUiError(f"{asset['asset_id']} rebuilt payload mismatch")


def report_items(plan: list[dict]) -> list[dict]:
    return [{
        "asset_id": asset["asset_id"],
        "source_offset": f"0x{asset['source_offset']:06X}",
        "source_compressed_bytes": asset["source_consumed"],
        "source_decoded_sha256": asset["source_decoded_sha256"],
        "target_offset": f"0x{asset['target_offset']:06X}",
        "target_pointer": f"0x{asset['target_pointer']:08X}",
        "compressed_bytes": len(asset["compressed"]),
        "compressed_sha256": asset["compressed_sha256"],
        "decoded_sha256": asset["decoded_sha256"],
        "labels": [{"source": item["source"], "ko": item["ko"]} for item in asset["labels"]],
    } for asset in plan]


RUNTIME_HOOK_SITE = 0x07921E
RUNTIME_HOOK_EXPECTED = bytes.fromhex("04B038BC")
# Eight bytes inside a 48-byte 0xFF padding run. No aligned GBA pointer targets
# this interval, and it is within Thumb-1 BL range of the renderer epilogue.
RUNTIME_TRAMPOLINE_OFFSET = 0x11A2EC
RUNTIME_TRAMPOLINE_EXPECTED = bytes.fromhex("FFFFFFFFFFFFFFFF")


def _thumb_bl(site_offset: int, target_offset: int) -> bytes:
    delta = (GBA_ROM_BASE + target_offset) - (GBA_ROM_BASE + site_offset + 4)
    if delta & 1 or not (-0x400000 <= delta < 0x400000):
        raise PauseUiError("Pause runtime trampoline is outside Thumb BL range")
    return struct.pack("<HH", 0xF000 | ((delta >> 12) & 0x7FF),
                       0xF800 | ((delta >> 1) & 0x7FF))


def _thumb_absolute_veneer(target_offset: int) -> bytes:
    return struct.pack("<HHI", 0x4800, 0x4700, GBA_ROM_BASE + target_offset + 1)


def _runtime_blob(blob_offset: int, plan: list[dict]) -> bytes:
    assets = {item["asset_id"]: item for item in plan}
    chrome = assets["pause_map_chrome_tileset_ko"]["decoded"]
    obj_segments = []

    def add_raw(group: list, payload: bytes, destination: int) -> None:
        group.append((payload, destination))

    def add(group: list, decoded: bytes, first_tile: int, tile_count: int, vram_base: int) -> None:
        payload = decoded[first_tile * 32:(first_tile + tile_count) * 32]
        add_raw(group, payload, vram_base + first_tile * 32)

    # OBJ map chrome labels, each in a runtime-confirmed blank tile group.
    add(obj_segments, chrome, 537, 5, 0x06010000)
    add(obj_segments, chrome, 569, 5, 0x06010000)
    add(obj_segments, chrome, 600, 6, 0x06010000)
    add(obj_segments, chrome, 632, 8, 0x06010000)
    add(obj_segments, chrome, 664, 2, 0x06010000)
    segments = obj_segments
    payload_offsets = []
    payload_cursor = 0
    for payload, _ in segments:
        payload_offsets.append(payload_cursor)
        payload_cursor += len(payload)

    # Preserve all low registers while copying raw 4bpp tiles during the Pause
    # renderer. The full displaced epilogue is reproduced at the end.
    code = bytearray(struct.pack("<HHH", 0xB004, 0xBC38, 0xB5FF))
    literal_uses = []

    def emit_literal_load(register: int, kind: str, value: int) -> None:
        position = len(code)
        code.extend(struct.pack("<H", 0x4800 | (register << 8)))
        literal_uses.append((position, register, kind, value))

    labels = {}
    branches = []

    def mark(name: str) -> None:
        labels[name] = len(code)

    def emit_branch(kind: str, target: str) -> None:
        position = len(code)
        code.extend(b"\x00\x00")
        branches.append((position, kind, target))

    def emit_copy_group(group: list[tuple[bytes, int]]) -> None:
        first = segments.index(group[0])
        for index, (payload, destination) in enumerate(group, first):
            emit_literal_load(0, "payload", payload_offsets[index])
            emit_literal_load(1, "absolute", destination)
            words = len(payload) // 4
            if len(payload) % 4 or words > 255:
                raise PauseUiError("Pause runtime copy segment is not word-copy compatible")
            code.extend(struct.pack("<H", 0x2200 | words))
            loop_pos = len(code)
            code.extend(struct.pack("<HHHH", 0x6803, 0x600B, 0x3004, 0x3104))
            code.extend(struct.pack("<H", 0x3A01))
            branch_pos = len(code)
            branch_delta = loop_pos - (branch_pos + 4)
            code.extend(struct.pack("<H", 0xD100 | ((branch_delta // 2) & 0xFF)))

    # This renderer is also used outside Pause. MAIN DECK appears at one of
    # these two shadow-OAM positions on the map and status screens.
    emit_literal_load(0, "absolute", 0x03000EE0)
    code += struct.pack("<HHH", 0x8801, 0x0589, 0x0D89)
    emit_literal_load(2, "absolute", 600)
    code += struct.pack("<H", 0x4291)
    emit_branch("beq", "obj")
    emit_literal_load(0, "absolute", 0x03000EC8)
    code += struct.pack("<HHH", 0x8801, 0x0589, 0x0D89)
    code += struct.pack("<H", 0x4291)
    emit_branch("bne", "restore")

    mark("obj")
    # Copy OBJ glyphs once per Pause load. The first destination tile is blank
    # before the copy and is restored by the game's next Pause tileset load.
    obj_first = 0
    emit_literal_load(0, "payload", payload_offsets[obj_first])
    code += struct.pack("<H", 0x6802)
    emit_literal_load(1, "absolute", obj_segments[0][1])
    code += struct.pack("<HH", 0x680B, 0x429A)
    emit_branch("beq", "restore")
    emit_copy_group(obj_segments)
    emit_branch("b", "restore")

    mark("restore")
    for position, kind, target_name in branches:
        delta = labels[target_name] - (position + 4)
        if delta % 2:
            raise PauseUiError("Pause runtime branch target is not halfword aligned")
        if kind in ("beq", "bne"):
            if not (-256 <= delta <= 254):
                raise PauseUiError("Pause runtime condition branch is out of range")
            base = 0xD000 if kind == "beq" else 0xD100
            opcode = base | ((delta // 2) & 0xFF)
        else:
            if not (-2048 <= delta <= 2046):
                raise PauseUiError("Pause runtime branch is out of range")
            opcode = 0xE000 | ((delta // 2) & 0x7FF)
        struct.pack_into("<H", code, position, opcode)
    code += struct.pack("<H", 0xBDFF)  # restore r0-r7 and return to original epilogue
    while len(code) % 4:
        code += b"\x00\x00"

    literal_start = len(code)
    literals = bytearray()
    payload_start = literal_start + len(literal_uses) * 4
    for use_index, (instruction_pos, register, kind, value) in enumerate(literal_uses):
        if kind == "payload":
            literal_value = GBA_ROM_BASE + blob_offset + payload_start + value
        else:
            literal_value = value
        literal_pos = literal_start + use_index * 4
        pc = (instruction_pos + 4) & ~3
        distance = literal_pos - pc
        if distance < 0 or distance % 4 or distance // 4 > 255:
            raise PauseUiError("Pause runtime literal is outside Thumb LDR range")
        opcode = 0x4800 | (register << 8) | (distance // 4)
        struct.pack_into("<H", code, instruction_pos, opcode)
        literals += struct.pack("<I", literal_value)

    payload_blob = b"".join(payload for payload, _ in segments)
    return bytes(code + literals + payload_blob)


def build_runtime_hook_plan(
    ranges: list[tuple[int, int]], occupied: list[tuple[int, int]], plan: list[dict]
) -> dict:
    occupied = occupied + [
        (item["target_offset"], item["target_offset"] + len(item["compressed"]))
        for item in plan
    ]
    placeholder = _runtime_blob(0, plan)
    for start, end in _free_intervals(ranges, occupied):
        offset = (start + 3) & ~3
        if offset + len(placeholder) <= end:
            blob = _runtime_blob(offset, plan)
            return {
                "offset": offset,
                "blob": blob,
                "hook_offset": RUNTIME_HOOK_SITE,
                "hook_expected": RUNTIME_HOOK_EXPECTED,
                "hook_new": _thumb_bl(RUNTIME_HOOK_SITE, RUNTIME_TRAMPOLINE_OFFSET),
                "trampoline_offset": RUNTIME_TRAMPOLINE_OFFSET,
                "trampoline_expected": RUNTIME_TRAMPOLINE_EXPECTED,
                "trampoline_new": _thumb_absolute_veneer(offset),
            }
    raise PauseUiError("reclaimed text space cannot hold Pause runtime tile hook")


def verify_runtime_hook(image: bytes, hook: dict) -> None:
    if image[hook["offset"]:hook["offset"] + len(hook["blob"])] != hook["blob"]:
        raise PauseUiError("Pause runtime hook blob mismatch")
    if image[hook["hook_offset"]:hook["hook_offset"] + len(hook["hook_new"])] != hook["hook_new"]:
        raise PauseUiError("Pause runtime hook branch mismatch")
    if image[hook["trampoline_offset"]:hook["trampoline_offset"] + len(hook["trampoline_new"])] != hook["trampoline_new"]:
        raise PauseUiError("Pause runtime trampoline mismatch")
