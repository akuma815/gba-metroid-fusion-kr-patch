"""Build the Korean Game Over prompt stored as a fixed-size LZ77 tile block."""
from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image

from hangul_glyph import sheet_bitmap
from pause_ui_graphics import compress_gba_lz77
from ui_graphics_audit import decompress_gba_lz77

PROJECT = Path(__file__).resolve().parents[2]
BITMAP_NAME = "Galmuri11-Condensed_9x12.png"
BASE_OFFSET = 0x735C88
BASE_SLOT_BYTES = 0x73B410 - BASE_OFFSET
OVERLAY_OFFSET = 0x73B6F0
OVERLAY_SLOT_BYTES = 1760
DECODED_BYTES = 6144
WIDTH = 256
LINE_HEIGHT = 16
VISIBLE_WIDTH = 240
LINES = (
    "게임을 계속하시겠습니까?",
    "예 (게임으로 복귀)",
    "아니요 (타이틀로 이동)",
)
ASCII_BITMAPS = {
    "?": (
        "  ####   ",
        " ##  ##  ",
        "     ##  ",
        "    ##   ",
        "   ##    ",
        "   ##    ",
        "         ",
        "   ##    ",
        "   ##    ",
        "         ",
        "         ",
        "         ",
    ),
    "(": (
        "    ##   ",
        "   ##    ",
        "  ##     ",
        "  ##     ",
        " ##      ",
        " ##      ",
        " ##      ",
        "  ##     ",
        "  ##     ",
        "   ##    ",
        "    ##   ",
        "         ",
    ),
    ")": (
        " ##      ",
        "  ##     ",
        "   ##    ",
        "   ##    ",
        "    ##   ",
        "    ##   ",
        "    ##   ",
        "   ##    ",
        "   ##    ",
        "  ##     ",
        " ##      ",
        "         ",
    ),
}


class GameOverGraphicsError(Exception):
    pass


def _outline(mask: list[list[int]], body: int, edge: int) -> list[list[int]]:
    height, width = len(mask), len(mask[0])
    result = [[body if mask[y][x] else 0 for x in range(width)] for y in range(height)]
    for y in range(height):
        for x in range(width):
            if mask[y][x]:
                continue
            if any(
                0 <= x + dx < width and 0 <= y + dy < height and mask[y + dy][x + dx]
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
            ):
                result[y][x] = edge
    return result


def _render_line(text: str, body: int, edge: int) -> list[list[int]]:
    advance = 9
    width = len(text) * advance
    left = (VISIBLE_WIDTH - width) // 2
    top = 2
    mask = [[0] * WIDTH for _ in range(LINE_HEIGHT)]
    x = left
    for character in text:
        if character != " ":
            if character in ASCII_BITMAPS:
                glyph = [[1 if pixel == "#" else 0 for pixel in row] for row in ASCII_BITMAPS[character]]
            else:
                glyph = sheet_bitmap(character, BITMAP_NAME)
            for gy, row in enumerate(glyph):
                for gx, value in enumerate(row):
                    if value:
                        mask[top + gy][x + gx] = 1
        x += advance
    return _outline(mask, body, edge)


def _pack_tile(pixels: list[list[int]], tile_x: int, tile_y: int) -> bytes:
    packed = bytearray()
    for y in range(8):
        row = pixels[tile_y * 8 + y]
        for x in range(0, 8, 2):
            low = row[tile_x * 8 + x]
            high = row[tile_x * 8 + x + 1]
            packed.append(low | (high << 4))
    return bytes(packed)


def build_decoded() -> bytes:
    # Prompt: yellow body with dark-red edge. Choices: white body with green edge.
    rendered = (
        _render_line(LINES[0], body=6, edge=3),
        _render_line(LINES[1], body=1, edge=9),
        _render_line(LINES[2], body=1, edge=9),
    )
    output = bytearray()
    for line in rendered:
        for tile_y in range(2):
            for tile_x in range(32):
                output.extend(_pack_tile(line, tile_x, tile_y))
    if len(output) != DECODED_BYTES:
        raise GameOverGraphicsError(f"decoded length {len(output)} != {DECODED_BYTES}")
    return bytes(output)


def build_plan(rom: bytes) -> dict:
    source_overlay = rom[OVERLAY_OFFSET:OVERLAY_OFFSET + OVERLAY_SLOT_BYTES]
    source_decoded, source_used = decompress_gba_lz77(source_overlay)
    if len(source_decoded) != DECODED_BYTES or source_used != 1759:
        raise GameOverGraphicsError("Game Over source block identity mismatch")
    decoded = build_decoded()
    overlay_compressed = compress_gba_lz77(decoded)
    if len(overlay_compressed) > OVERLAY_SLOT_BYTES:
        raise GameOverGraphicsError(
            f"compressed Game Over overlay {len(overlay_compressed)} > {OVERLAY_SLOT_BYTES}"
        )
    overlay_slot = overlay_compressed + bytes(OVERLAY_SLOT_BYTES - len(overlay_compressed))
    restored, used = decompress_gba_lz77(overlay_slot)
    if restored != decoded or used > OVERLAY_SLOT_BYTES:
        raise GameOverGraphicsError("Game Over LZ77 round-trip mismatch")

    source_base_slot = rom[BASE_OFFSET:BASE_OFFSET + BASE_SLOT_BYTES]
    source_base, base_used = decompress_gba_lz77(source_base_slot)
    if len(source_base) != 32768 or base_used != 22405:
        raise GameOverGraphicsError("Game Over base graphics identity mismatch")
    base_decoded = decoded + source_base[DECODED_BYTES:]
    base_compressed = compress_gba_lz77(base_decoded)
    if len(base_compressed) > BASE_SLOT_BYTES:
        raise GameOverGraphicsError(
            f"compressed Game Over base {len(base_compressed)} > {BASE_SLOT_BYTES}"
        )
    base_slot = base_compressed + bytes(BASE_SLOT_BYTES - len(base_compressed))
    base_restored, base_consumed = decompress_gba_lz77(base_slot)
    if base_restored != base_decoded or base_consumed > BASE_SLOT_BYTES:
        raise GameOverGraphicsError("Game Over base LZ77 round-trip mismatch")
    return {
        "base_offset": BASE_OFFSET,
        "base_slot_bytes": BASE_SLOT_BYTES,
        "source_base_slot": source_base_slot,
        "base_slot": base_slot,
        "base_compressed_bytes": len(base_compressed),
        "overlay_offset": OVERLAY_OFFSET,
        "overlay_slot_bytes": OVERLAY_SLOT_BYTES,
        "source_overlay_slot": source_overlay,
        "overlay_slot": overlay_slot,
        "overlay_compressed_bytes": len(overlay_compressed),
        "source_sha256": hashlib.sha256(source_overlay).hexdigest().upper(),
        "decoded": decoded,
        "decoded_sha256": hashlib.sha256(decoded).hexdigest().upper(),
        "lines": list(LINES),
        "font": BITMAP_NAME,
    }


def verify_image(image: bytes, plan: dict) -> None:
    base_slot = image[BASE_OFFSET:BASE_OFFSET + BASE_SLOT_BYTES]
    overlay_slot = image[OVERLAY_OFFSET:OVERLAY_OFFSET + OVERLAY_SLOT_BYTES]
    if base_slot != plan["base_slot"] or overlay_slot != plan["overlay_slot"]:
        raise GameOverGraphicsError("built Game Over slot mismatch")
    base_decoded, _ = decompress_gba_lz77(base_slot)
    overlay_decoded, _ = decompress_gba_lz77(overlay_slot)
    if base_decoded[:DECODED_BYTES] != plan["decoded"] or overlay_decoded != plan["decoded"]:
        raise GameOverGraphicsError("built Game Over decoded pixels mismatch")


def save_preview(plan: dict, path: Path) -> None:
    palette = (
        (0, 0, 0, 0), (255, 255, 255, 255), (0, 0, 0, 255), (148, 32, 24, 255),
        (205, 41, 16, 255), (238, 123, 16, 255), (255, 230, 8, 255), (106, 230, 123, 255),
        (24, 213, 74, 255), (0, 189, 0, 255), (41, 139, 115, 255), (189, 238, 189, 255),
    )
    image = Image.new("RGBA", (WIDTH, LINE_HEIGHT * 3), (0, 0, 0, 0))
    data = plan["decoded"]
    for tile_index in range(192):
        line = tile_index // 64
        within = tile_index % 64
        tx, ty = within % 32, within // 32
        tile = data[tile_index * 32:(tile_index + 1) * 32]
        for py in range(8):
            for px in range(8):
                value = tile[py * 4 + px // 2]
                index = (value >> (4 * (px & 1))) & 0xF
                if index:
                    image.putpixel((tx * 8 + px, line * 16 + ty * 8 + py), palette[index])
    path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((WIDTH * 3, LINE_HEIGHT * 9), Image.Resampling.NEAREST).save(path)
