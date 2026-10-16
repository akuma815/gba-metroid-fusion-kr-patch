"""Render fixed UI graphics candidates from the supported Fusion JP ROM."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from PIL import Image

from font_codec import decode_tile
from rombuild import PROJECT, load_source

GAME_OVER_TEXT_OFFSET = 0x73B6F0
GAME_OVER_TEXT_BYTES = 1760
GAME_OVER_PALETTE_OFFSET = 0x73BDD0
PAUSE_TILESET_STREAMS = (
    ("pause_preloaded_tileset_a", 0x56C930),
    ("pause_preloaded_tileset_b", 0x571DF8),
)
PAUSE_TILEMAP_STREAMS = (
    ("pause_tilemap_00", 0x575328),
    ("pause_tilemap_01", 0x575424),
    ("pause_tilemap_02", 0x576800),
    ("pause_tilemap_03", 0x5769EC),
    ("pause_tilemap_04", 0x576CAC),
    ("pause_tilemap_05", 0x576FB0),
)
PAUSE_BG_PALETTE_OFFSET = 0x567E84
PAUSE_BG_PALETTE_BYTES = 512
REPORT_PATH = PROJECT / "workspace" / "analysis" / "ui_graphics_audit.json"
PREVIEW_DIR = PROJECT / "work" / "ui_audit"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def gba_color(value: int) -> tuple[int, int, int, int]:
    r = (value & 0x1F) * 255 // 31
    g = ((value >> 5) & 0x1F) * 255 // 31
    b = ((value >> 10) & 0x1F) * 255 // 31
    return r, g, b, 0 if value == 0 else 255


def decompress_gba_lz77(data: bytes) -> tuple[bytes, int]:
    """Decode BIOS LZ77 type 0x10 data and return (payload, consumed bytes)."""
    if len(data) < 4 or data[0] != 0x10:
        raise ValueError("not a GBA LZ77 type 0x10 stream")
    target_size = int.from_bytes(data[1:4], "little")
    source_pos = 4
    output = bytearray()
    while len(output) < target_size:
        if source_pos >= len(data):
            raise ValueError("truncated LZ77 flag byte")
        flags = data[source_pos]
        source_pos += 1
        for bit in range(7, -1, -1):
            if len(output) >= target_size:
                break
            if flags & (1 << bit):
                if source_pos + 2 > len(data):
                    raise ValueError("truncated LZ77 back-reference")
                first, second = data[source_pos:source_pos + 2]
                source_pos += 2
                length = (first >> 4) + 3
                distance = (((first & 0x0F) << 8) | second) + 1
                if distance > len(output):
                    raise ValueError("invalid LZ77 back-reference")
                for _ in range(length):
                    if len(output) >= target_size:
                        break
                    output.append(output[-distance])
            else:
                if source_pos >= len(data):
                    raise ValueError("truncated LZ77 literal")
                output.append(data[source_pos])
                source_pos += 1
    return bytes(output), source_pos


def render_tiles(data: bytes, palette_data: bytes, columns: int, output: Path, scale: int = 4):
    if len(data) % 32:
        raise ValueError("tile data is not 32-byte aligned")
    tile_count = len(data) // 32
    rows = (tile_count + columns - 1) // columns
    palette = [gba_color(value) for value in struct.unpack("<16H", palette_data)]
    image = Image.new("RGBA", (columns * 8, rows * 8), (24, 24, 24, 255))
    for index in range(tile_count):
        tile = decode_tile(data[index * 32:(index + 1) * 32])
        x0 = index % columns * 8
        y0 = index // columns * 8
        for y, row in enumerate(tile):
            for x, color in enumerate(row):
                image.putpixel((x0 + x, y0 + y), palette[color])
    output.parent.mkdir(parents=True, exist_ok=True)
    image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).save(output)


def render_tile_index_grid(data: bytes, output: Path, scale: int = 4):
    """Render palette indices with tile boundaries for edit-boundary auditing."""
    if len(data) % 32:
        raise ValueError("tile data is not 32-byte aligned")
    columns = 32
    tile_count = len(data) // 32
    rows = (tile_count + columns - 1) // columns
    colors = [
        (0, 0, 0), (255, 255, 255), (255, 64, 64), (64, 255, 64),
        (64, 64, 255), (255, 255, 64), (255, 64, 255), (64, 255, 255),
        (128, 128, 128), (255, 160, 64), (160, 64, 255), (64, 160, 255),
        (160, 255, 64), (255, 64, 160), (64, 255, 160), (224, 224, 224),
    ]
    image = Image.new("RGB", (columns * 8, rows * 8), colors[0])
    for index in range(tile_count):
        tile = decode_tile(data[index * 32:(index + 1) * 32])
        x0 = index % columns * 8
        y0 = index // columns * 8
        for y, row in enumerate(tile):
            for x, color in enumerate(row):
                image.putpixel((x0 + x, y0 + y), colors[color])
    image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    for x in range(0, image.width + 1, 8 * scale):
        draw.line((x, 0, x, image.height), fill=(255, 0, 0))
    for y in range(0, image.height + 1, 8 * scale):
        draw.line((0, y, image.width, y), fill=(255, 0, 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def render_tilemap(tiles: bytes, tilemap: bytes, palette_data: bytes, output: Path, scale: int = 2):
    if len(tiles) % 32 or len(tilemap) != 2048:
        raise ValueError("invalid 4bpp tiles or 32x32 tilemap size")
    decoded_tiles = [decode_tile(tiles[i:i + 32]) for i in range(0, len(tiles), 32)]
    if len(palette_data) == 32:
        values = struct.unpack("<16H", palette_data) * 16
    elif len(palette_data) == 512:
        values = struct.unpack("<256H", palette_data)
    else:
        raise ValueError("palette must contain one or sixteen GBA 16-color banks")
    palettes = [
        [gba_color(value) for value in values[bank * 16:(bank + 1) * 16]]
        for bank in range(16)
    ]
    image = Image.new("RGBA", (256, 256), (24, 24, 24, 255))
    for index, entry in enumerate(struct.unpack("<1024H", tilemap)):
        tile_index = entry & 0x3FF
        if tile_index >= len(decoded_tiles):
            continue
        hflip = bool(entry & 0x400)
        vflip = bool(entry & 0x800)
        palette = palettes[(entry >> 12) & 0xF]
        tile = decoded_tiles[tile_index]
        x0 = index % 32 * 8
        y0 = index // 32 * 8
        for y in range(8):
            for x in range(8):
                sx = 7 - x if hflip else x
                sy = 7 - y if vflip else y
                image.putpixel((x0 + x, y0 + y), palette[tile[sy][sx]])
    output.parent.mkdir(parents=True, exist_ok=True)
    image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).save(output)


def render_tilemap_grid(tiles: bytes, tilemap: bytes, palette_data: bytes, output: Path, scale: int = 4):
    render_tilemap(tiles, tilemap, palette_data, output, scale=scale)
    image = Image.open(output).convert("RGB")
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    for x in range(0, image.width + 1, 8 * scale):
        draw.line((x, 0, x, image.height), fill=(255, 0, 0))
    for y in range(0, image.height + 1, 8 * scale):
        draw.line((0, y, image.width, y), fill=(255, 0, 0))
    image.save(output)


def build_report(rom: bytes) -> dict:
    data = rom[GAME_OVER_TEXT_OFFSET:GAME_OVER_TEXT_OFFSET + GAME_OVER_TEXT_BYTES]
    decoded, consumed = decompress_gba_lz77(data)
    palette = rom[GAME_OVER_PALETTE_OFFSET:GAME_OVER_PALETTE_OFFSET + 32]
    if len(data) != GAME_OVER_TEXT_BYTES or len(palette) != 32:
        raise ValueError("truncated game-over graphics")
    assets = [
        {
            "asset_id": "game_over_japanese_text_tiles",
            "status": "confirmed_baked_graphics",
            "file_offset": f"0x{GAME_OVER_TEXT_OFFSET:06X}",
            "byte_length": len(data),
            "sha256": sha256(data),
            "format": "GBA LZ77 type 0x10 -> 4bpp 8x8 tiles",
            "compressed_bytes_consumed": consumed,
            "trailing_padding_bytes": len(data) - consumed,
            "decoded_byte_length": len(decoded),
            "decoded_sha256": sha256(decoded),
            "tile_count": len(decoded) // 32,
            "palette_offset": f"0x{GAME_OVER_PALETTE_OFFSET:06X}",
            "palette_sha256": sha256(palette),
            "consumer_evidence": [
                "The region begins with a GBA LZ77 type 0x10 header declaring 6144 decoded bytes",
                "The valid stream consumes 1759 bytes and is followed by one zero padding byte",
                "JP language-patch lineage replaces exactly this 1760-byte region for Game Over text",
                "Game Over initializes compressed/background graphics and OAM without GetCharacterWidth/DrawCharacter",
                "The region ends exactly at the referenced palette offset",
            ],
            "runtime_status": "not_yet_captured_in_mesen",
        }
    ]
    for asset_id, offset in PAUSE_TILESET_STREAMS:
        payload, used = decompress_gba_lz77(rom[offset:])
        compressed = rom[offset:offset + used]
        is_status = asset_id.endswith("_a")
        assets.append({
            "asset_id": asset_id,
            "status": "confirmed_pause_status_tileset" if is_status else "confirmed_pause_map_chrome_tileset",
            "file_offset": f"0x{offset:06X}",
            "compressed_bytes_consumed": used,
            "compressed_sha256": sha256(compressed),
            "format": "GBA LZ77 type 0x10 -> 4bpp 8x8 tiles",
            "decoded_byte_length": len(payload),
            "decoded_sha256": sha256(payload),
            "tile_count": len(payload) // 32,
            "runtime_read_range": f"0x{0x08000000 + offset + 4:08X}-0x{0x08000000 + offset + used - 1:08X}",
            "runtime_status": "read_during_pause_map_entry_not_reread_on_status_transition",
            "label_mapping_status": "confirmed_by_decoded_tilesheet_and_composed_tilemap",
            "background_palette_offset": f"0x{PAUSE_BG_PALETTE_OFFSET:06X}",
            "background_palette_sha256": sha256(rom[PAUSE_BG_PALETTE_OFFSET:PAUSE_BG_PALETTE_OFFSET + PAUSE_BG_PALETTE_BYTES]),
        })
    for asset_id, offset in PAUSE_TILEMAP_STREAMS:
        payload, used = decompress_gba_lz77(rom[offset:])
        compressed = rom[offset:offset + used]
        if asset_id == "pause_tilemap_05":
            mapping_status = "confirmed_status_screen_composition_with_tileset_a"
        elif asset_id in {"pause_tilemap_02", "pause_tilemap_03", "pause_tilemap_04"}:
            mapping_status = "confirmed_pause_map_chrome_layer_with_tileset_b"
        else:
            mapping_status = "preloaded_pause_auxiliary_tilemap_exact_layer_pending"
        assets.append({
            "asset_id": asset_id,
            "status": "confirmed_pause_entry_preloaded_tilemap_candidate",
            "file_offset": f"0x{offset:06X}",
            "compressed_bytes_consumed": used,
            "compressed_sha256": sha256(compressed),
            "format": "GBA LZ77 type 0x10 -> 32x32 u16 background tilemap candidate",
            "decoded_byte_length": len(payload),
            "decoded_sha256": sha256(payload),
            "entry_count": len(payload) // 2,
            "runtime_read_range": f"0x{0x08000000 + offset + 4:08X}-0x{0x08000000 + offset + used - 1:08X}",
            "runtime_status": "read_during_pause_map_entry_not_reread_on_status_transition",
            "screen_mapping_status": mapping_status,
        })
    return {
        "schema_version": 1,
        "source_rom_sha256": sha256(rom),
        "assets": assets,
    }


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    rom = load_source()
    expected = build_report(rom)
    if args.command == "build":
        write_json(REPORT_PATH, expected)
        data = rom[GAME_OVER_TEXT_OFFSET:GAME_OVER_TEXT_OFFSET + GAME_OVER_TEXT_BYTES]
        decoded, _ = decompress_gba_lz77(data)
        palette = rom[GAME_OVER_PALETTE_OFFSET:GAME_OVER_PALETTE_OFFSET + 32]
        for columns in (16, 32):
            render_tiles(decoded, palette, columns, PREVIEW_DIR / f"game_over_text_decoded_{columns}col.png")
        grayscale = struct.pack("<16H", *(i | (i << 5) | (i << 10) for i in range(16)))
        for asset_id, offset in PAUSE_TILESET_STREAMS:
            payload, _ = decompress_gba_lz77(rom[offset:])
            render_tiles(payload, grayscale, 32, PREVIEW_DIR / f"{asset_id}_32col.png", scale=2)
            render_tile_index_grid(payload, PREVIEW_DIR / f"{asset_id}_index_grid.png")
        decoded_tilesets = {
            asset_id: decompress_gba_lz77(rom[offset:])[0]
            for asset_id, offset in PAUSE_TILESET_STREAMS
        }
        pause_palette = rom[PAUSE_BG_PALETTE_OFFSET:PAUSE_BG_PALETTE_OFFSET + PAUSE_BG_PALETTE_BYTES]
        for map_id, map_offset in PAUSE_TILEMAP_STREAMS:
            tilemap, _ = decompress_gba_lz77(rom[map_offset:])
            for tileset_id, tiles in decoded_tilesets.items():
                render_tilemap(tiles, tilemap, pause_palette,
                               PREVIEW_DIR / f"{map_id}_with_{tileset_id}.png")
                if (map_id, tileset_id) in {
                    ("pause_tilemap_04", "pause_preloaded_tileset_b"),
                    ("pause_tilemap_05", "pause_preloaded_tileset_a"),
                }:
                    render_tilemap_grid(
                        tiles, tilemap, pause_palette,
                        PREVIEW_DIR / f"{map_id}_with_{tileset_id}_grid.png",
                    )
    else:
        actual = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        if actual != expected:
            raise SystemExit("ui graphics audit is stale or modified")
    print(json.dumps({"status": "pass", "asset": expected["assets"][0]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
