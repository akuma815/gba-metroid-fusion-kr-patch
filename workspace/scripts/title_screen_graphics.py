"""Build a Korean title-logo BG layer from the user-approved reference image."""
from __future__ import annotations

import argparse
import hashlib
import struct
from collections import defaultdict, deque
from pathlib import Path

from PIL import Image, ImageFilter

from rombuild import PROJECT, load_source
from ui_graphics_audit import decode_tile, decompress_gba_lz77, gba_color


REFERENCE = PROJECT / "workspace" / "graphics" / "source" / "metroid_fusion_korean_title_reference.png"
REFERENCE_SHA256 = "D85BF61FB6A29DB0E8EEC99F81854CC0875532585F165BEFF65D3D55861EA208"
PREVIEW_DIR = PROJECT / "workspace" / "analysis" / "previews"

LOGO_GFX_OFFSET = 0x593BEC
LOGO_GFX_POINTER = 0x08593BEC
LOGO_GFX_POINTER_OFFSETS = (0x087708, 0x088000)
LOGO_GFX_DECODED_SHA256 = "6A7D85A9378251FBE58EB7A11A3285DF5F9ACFE65B2FC7570ED99B532755024E"
LOGO_MAP_OFFSET = 0x596E4C
LOGO_MAP_POINTER = 0x08596E4C
LOGO_MAP_POINTER_OFFSETS = (0x087710, 0x088008)
LOGO_MAP_DECODED_SHA256 = "DE33E23351F019A7DDF55866E5D4AF603126675252A3F2163FF6EA81A53C2455"
LOGO_PALETTE_OFFSET = 0x5975B0
LOGO_PALETTE_BYTES = 0x100
LOGO_PALETTE_SHA256 = "FC38291F7AE30133E8EA5E2ED665FAAF31FBD0C2AF484ECA840F85B5A3CB56C9"

SPACE_GFX_OFFSET = 0x606834
SPACE_MAP_OFFSET = 0x609D4C
SPACE_PALETTE_OFFSET = 0x609C4C
GBA_ROM_BASE = 0x08000000


class TitleGraphicsError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _rgb_from_word(value: int) -> tuple[int, int, int]:
    r, g, b, _ = gba_color(value)
    return r, g, b


def _render_background(rom: bytes) -> Image.Image:
    graphics, _ = decompress_gba_lz77(rom[SPACE_GFX_OFFSET:])
    tilemap, _ = decompress_gba_lz77(rom[SPACE_MAP_OFFSET:])
    if len(graphics) != 0x5000 or len(tilemap) != 0x800:
        raise TitleGraphicsError("title space-background source size mismatch")
    values = struct.unpack("<128H", rom[SPACE_PALETTE_OFFSET:SPACE_PALETTE_OFFSET + 0x100])
    palettes = [
        [_rgb_from_word(value) for value in values[bank * 16:(bank + 1) * 16]]
        for bank in range(8)
    ]
    tiles = [decode_tile(graphics[pos:pos + 32]) for pos in range(0, len(graphics), 32)]
    image = Image.new("RGB", (240, 160))
    entries = struct.unpack("<1024H", tilemap)
    for ty in range(20):
        for tx in range(30):
            entry = entries[ty * 32 + tx]
            tile = tiles[entry & 0x3FF]
            palette = palettes[(entry >> 12) & 7]
            hflip = bool(entry & 0x400)
            vflip = bool(entry & 0x800)
            for py in range(8):
                for px in range(8):
                    sx = 7 - px if hflip else px
                    sy = 7 - py if vflip else py
                    image.putpixel((tx * 8 + px, ty * 8 + py), palette[tile[sy][sx]])
    return image


def _reference_and_mask(background: Image.Image) -> tuple[Image.Image, Image.Image]:
    if not REFERENCE.is_file() or sha256(REFERENCE.read_bytes()) != REFERENCE_SHA256:
        raise TitleGraphicsError("Korean title reference is missing or modified")
    reference = Image.open(REFERENCE).convert("RGB").resize((240, 160), Image.Resampling.LANCZOS)
    width, height = reference.size
    seed = [[False] * width for _ in range(height)]
    for y in range(113):
        for x in range(width):
            r, g, b = reference.getpixel((x, y))
            broad = ((25 <= y <= 86 and 5 <= x <= 235) or
                     (2 <= y <= 113 and 58 <= x <= 188))
            colored_metal = g > 68 and (g - r > 8 or b - r > 15)
            silver = min(r, g, b) > 105
            gold = r > 90 and g > 68 and b < 100
            if broad and (colored_metal or silver or gold):
                seed[y][x] = True

    seen: set[tuple[int, int]] = set()
    keep: set[tuple[int, int]] = set()
    for y in range(113):
        for x in range(width):
            if not seed[y][x] or (x, y) in seen:
                continue
            queue = deque([(x, y)])
            seen.add((x, y))
            component: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.popleft()
                component.append((cx, cy))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if (0 <= nx < width and 0 <= ny < 113 and seed[ny][nx] and
                            (nx, ny) not in seen):
                        seen.add((nx, ny))
                        queue.append((nx, ny))
            if len(component) >= 5:
                keep.update(component)

    mask = Image.new("L", reference.size, 0)
    for point in keep:
        mask.putpixel(point, 255)
    mask = (mask.filter(ImageFilter.MaxFilter(7))
                .filter(ImageFilter.MinFilter(3))
                .filter(ImageFilter.MaxFilter(3)))
    for y in range(height):
        for x in range(width):
            broad = ((21 <= y <= 91 and 1 <= x <= 239) or
                     (0 <= y <= 116 and 54 <= x <= 192))
            if not broad:
                mask.putpixel((x, y), 0)
    return reference, mask


def _encode_reference_layer(rom: bytes) -> dict:
    background = _render_background(rom)
    reference, mask = _reference_and_mask(background)
    palette = rom[LOGO_PALETTE_OFFSET:LOGO_PALETTE_OFFSET + LOGO_PALETTE_BYTES]
    palette_words = struct.unpack("<128H", palette)
    # Palette 0 index 15 is overwritten by the title debug-text setup at
    # runtime.  Exclude that entry so the generated logo and the preview use
    # only stable colors.  All other non-zero entries retain their original
    # meaning, because the file-select menu inherits these palette banks.
    bank_colors: list[list[tuple[int, tuple[int, int, int]]]] = []
    for bank in range(8):
        last_index = 15 if bank == 0 else 16
        bank_colors.append([
            (index, _rgb_from_word(palette_words[bank * 16 + index]))
            for index in range(1, last_index)
        ])

    blank = bytes(32)
    tile_lookup = {blank: 0}
    tiles = [blank]
    entries = [0] * 1024
    layer = Image.new("RGBA", (240, 160), (0, 0, 0, 0))
    composite = background.convert("RGBA")
    for tile_y in range(20):
        for tile_x in range(30):
            opaque: list[tuple[int, int, tuple[int, int, int]]] = []
            for py in range(8):
                for px in range(8):
                    x, y = tile_x * 8 + px, tile_y * 8 + py
                    if mask.getpixel((x, y)):
                        opaque.append((px, py, reference.getpixel((x, y))))
            if opaque:
                bank = min(range(8), key=lambda candidate: sum(
                    min(sum((source[channel] - color[channel]) ** 2 for channel in range(3))
                        for _, color in bank_colors[candidate])
                    for _, _, source in opaque
                ))
            else:
                bank = 0
            colors = bank_colors[bank]
            indices: list[list[int]] = [[0] * 8 for _ in range(8)]
            for px, py, source in opaque:
                palette_index, color = min(colors, key=lambda item: sum(
                    (source[channel] - item[1][channel]) ** 2 for channel in range(3)
                ))
                x, y = tile_x * 8 + px, tile_y * 8 + py
                indices[py][px] = palette_index
                layer.putpixel((x, y), (*color, 255))
                composite.putpixel((x, y), (*color, 255))
            raw = bytearray()
            for row in indices:
                for x in range(0, 8, 2):
                    raw.append(row[x] | (row[x + 1] << 4))
            raw_tile = bytes(raw)
            tile_id = tile_lookup.get(raw_tile)
            if tile_id is None:
                tile_id = len(tiles)
                if tile_id >= 896:
                    raise TitleGraphicsError("Korean title exceeds the BG1 tile budget")
                tile_lookup[raw_tile] = tile_id
                tiles.append(raw_tile)
            entries[tile_y * 32 + tile_x] = tile_id | (bank << 12)

    graphics = b"".join(tiles).ljust(0x8000, b"\0")
    tilemap = struct.pack("<1024H", *entries)
    return {
        "graphics": graphics,
        "tilemap": tilemap,
        "palette": palette,
        "reference": reference,
        "mask": mask,
        "layer": layer,
        "composite": composite.convert("RGB"),
        "unique_tiles": len(tiles),
        "opaque_pixels": sum(1 for value in mask.tobytes() if value),
    }


def _free_intervals(ranges: list[tuple[int, int]], occupied: list[tuple[int, int]]) -> list[tuple[int, int]]:
    free: list[tuple[int, int]] = []
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


def _compress_vram_safe(data: bytes) -> bytes:
    """Encode type-0x10 without distance-one matches for BIOS VRAM output.

    The title graphics contain long zero runs.  Avoiding matches that refer
    to the other byte of a pending halfword keeps the stream
    independent of byte-buffer behavior in VRAM decompressors.
    """
    if len(data) > 0xFFFFFF:
        raise TitleGraphicsError("title asset exceeds the LZ77 size field")
    out = bytearray((0x10, len(data) & 0xFF, (len(data) >> 8) & 0xFF,
                     (len(data) >> 16) & 0xFF))
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
                for candidate in reversed(chains.get(key, ())):
                    distance = pos - candidate
                    if distance > 4096:
                        break
                    if distance < 2:
                        continue
                    maximum = min(18, len(data) - pos)
                    length = 3
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
        raise TitleGraphicsError("VRAM-safe title LZ77 self-roundtrip mismatch")
    return bytes(out)


def build_plan(rom: bytes, ranges: list[tuple[int, int]], occupied: list[tuple[int, int]]) -> dict:
    source_gfx, source_gfx_used = decompress_gba_lz77(rom[LOGO_GFX_OFFSET:])
    source_map, source_map_used = decompress_gba_lz77(rom[LOGO_MAP_OFFSET:])
    if sha256(source_gfx) != LOGO_GFX_DECODED_SHA256:
        raise TitleGraphicsError("source title-logo graphics mismatch")
    if sha256(source_map) != LOGO_MAP_DECODED_SHA256:
        raise TitleGraphicsError("source title-logo tilemap mismatch")
    source_palette = rom[LOGO_PALETTE_OFFSET:LOGO_PALETTE_OFFSET + LOGO_PALETTE_BYTES]
    if sha256(source_palette) != LOGO_PALETTE_SHA256:
        raise TitleGraphicsError("source title-logo palette mismatch")

    built = _encode_reference_layer(rom)
    assets = [
        {
            "asset_id": "title_logo_graphics_ko",
            "source_offset": LOGO_GFX_OFFSET,
            "source_pointer": LOGO_GFX_POINTER,
            "source_consumed": source_gfx_used,
            "source_decoded_sha256": sha256(source_gfx),
            "pointer_offsets": LOGO_GFX_POINTER_OFFSETS,
            "decoded": built["graphics"],
        },
        {
            "asset_id": "title_logo_tilemap_ko",
            "source_offset": LOGO_MAP_OFFSET,
            "source_pointer": LOGO_MAP_POINTER,
            "source_consumed": source_map_used,
            "source_decoded_sha256": sha256(source_map),
            "pointer_offsets": LOGO_MAP_POINTER_OFFSETS,
            "decoded": built["tilemap"],
        },
    ]
    free = _free_intervals(ranges, occupied)
    if not free:
        raise TitleGraphicsError("no reclaimed range available for Korean title")
    free_index = 0
    cursor = free[0][0]
    for asset in assets:
        compressed = _compress_vram_safe(asset["decoded"])
        while True:
            cursor = (cursor + 3) & ~3
            if cursor + len(compressed) <= free[free_index][1]:
                break
            free_index += 1
            if free_index >= len(free):
                raise TitleGraphicsError("reclaimed text space cannot hold Korean title graphics")
            cursor = free[free_index][0]
        asset.update({
            "compressed": compressed,
            "compressed_sha256": sha256(compressed),
            "decoded_sha256": sha256(asset["decoded"]),
            "target_offset": cursor,
            "target_pointer": GBA_ROM_BASE + cursor,
        })
        cursor += len(compressed)
    return {
        "assets": assets,
        "palette": built["palette"],
        "palette_sha256": sha256(built["palette"]),
        "source_palette": source_palette,
        "unique_tiles": built["unique_tiles"],
        "opaque_pixels": built["opaque_pixels"],
        "preview": built,
    }


def verify_image(image: bytes, plan: dict) -> None:
    for asset in plan["assets"]:
        for pointer_offset in asset["pointer_offsets"]:
            if struct.unpack_from("<I", image, pointer_offset)[0] != asset["target_pointer"]:
                raise TitleGraphicsError(f"{asset['asset_id']} pointer mismatch")
        decoded, consumed = decompress_gba_lz77(image[asset["target_offset"]:])
        if decoded != asset["decoded"] or consumed > len(asset["compressed"]):
            raise TitleGraphicsError(f"{asset['asset_id']} rebuilt payload mismatch")
    actual = image[LOGO_PALETTE_OFFSET:LOGO_PALETTE_OFFSET + LOGO_PALETTE_BYTES]
    if actual != plan["palette"]:
        raise TitleGraphicsError("Korean title palette mismatch")


def report(plan: dict) -> dict:
    return {
        "reference": str(REFERENCE.relative_to(PROJECT)).replace("\\", "/"),
        "reference_sha256": REFERENCE_SHA256,
        "unique_tiles": plan["unique_tiles"],
        "opaque_pixels": plan["opaque_pixels"],
        "palette_offset": f"0x{LOGO_PALETTE_OFFSET:06X}",
        "palette_sha256": plan["palette_sha256"],
        "palette_policy": "preserve original shared title and file-select palette byte-for-byte",
        "assets": [{
            "asset_id": asset["asset_id"],
            "source_offset": f"0x{asset['source_offset']:06X}",
            "source_compressed_bytes": asset["source_consumed"],
            "source_decoded_sha256": asset["source_decoded_sha256"],
            "target_offset": f"0x{asset['target_offset']:06X}",
            "target_pointer": f"0x{asset['target_pointer']:08X}",
            "pointer_offsets": [f"0x{offset:06X}" for offset in asset["pointer_offsets"]],
            "compressed_bytes": len(asset["compressed"]),
            "compressed_sha256": asset["compressed_sha256"],
            "decoded_sha256": asset["decoded_sha256"],
        } for asset in plan["assets"]],
    }


def save_previews(plan: dict) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    preview = plan["preview"]
    preview["reference"].save(PREVIEW_DIR / "title_ko_reference_240x160.png")
    preview["mask"].save(PREVIEW_DIR / "title_ko_logo_mask.png")
    preview["layer"].save(PREVIEW_DIR / "title_ko_bg1_layer.png")
    preview["composite"].save(PREVIEW_DIR / "title_ko_composite.png")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preview",))
    args = parser.parse_args()
    rom = load_source()
    plan = build_plan(rom, [(0x700000, 0x780000)], [])
    if args.command == "preview":
        save_previews(plan)
        print(f"unique_tiles={plan['unique_tiles']} opaque_pixels={plan['opaque_pixels']}")
        for asset in plan["assets"]:
            print(f"{asset['asset_id']} compressed={len(asset['compressed'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
