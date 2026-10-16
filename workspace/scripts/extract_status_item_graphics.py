"""Extract the baked Status-screen item labels from the clean JP ROM."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
from pathlib import Path

from PIL import Image

from rombuild import PROJECT, load_source
from ui_graphics_audit import decompress_gba_lz77, render_tilemap, render_tilemap_grid


OUTPUT_DIR = PROJECT / "workspace" / "graphics" / "extracted" / "status_items"
TILESET_OFFSET = 0x56C930
TILEMAP_OFFSET = 0x576FB0
PALETTE_OFFSET = 0x567E84
PALETTE_BYTES = 512
EXPECTED_SOURCE_SHA256 = "11C3ED10FA89D2644EA4D8E97380AA520A268340934B91883602CEA668737E48"
EXPECTED_TILESET_DECODED_SHA256 = "8B596282600D309B49875388AD4FBA337B383CCA53556FDBB9644D3FD02C6251"
EXPECTED_TILEMAP_DECODED_SHA256 = "B2AC944020D3C8CFFFB6B92744C622E548472B27D1B60428F7418736829FFD39"

# Coordinates are in the native 256x256 composed background. The five item
# panels live below the initially visible status overview and are selected by
# BG scrolling as abilities are displayed.
PANELS = {
    "beam": (8, 168, 72, 232),
    "missile": (80, 168, 136, 216),
    "bomb": (8, 216, 88, 256),
    "suit": (152, 168, 232, 208),
    "misc": (152, 200, 232, 248),
}

LABELS = (
    ("counter", "ENERGY", "에너지", "existing_ui"),
    ("counter", "MISSILE", "미사일", "existing_ui"),
    ("counter", "P.BOMB", "파워 봄", "project_term"),
    ("category", "BEAM", "빔", "existing_ui"),
    ("beam", "CHARGE", "차지 빔", "project_term"),
    ("beam", "WIDE", "와이드 빔", "project_term"),
    ("beam", "PLASMA", "플라스마 빔", "project_term"),
    ("beam", "WAVE", "웨이브 빔", "project_term"),
    ("beam", "ICE", "아이스 빔", "project_term"),
    ("category", "MISSILE", "미사일", "existing_ui"),
    ("missile", "SUPER", "슈퍼 미사일", "project_term"),
    ("missile", "ICE", "아이스 미사일", "project_term"),
    ("missile", "DIFFUSION", "디퓨전 미사일", "project_term"),
    ("category", "BOMB", "봄", "project_term"),
    ("bomb", "POWER", "파워 봄", "project_term"),
    ("category", "SUIT", "슈트", "existing_ui"),
    ("suit", "VARIA", "배리어 슈트", "official_ja_based"),
    ("suit", "GRAVITY", "그래비티 슈트", "official_ja_based"),
    ("category", "MISC.", "기타", "translation_pending"),
    ("misc", "MORPH BALL", "모프볼", "official"),
    ("misc", "HI-JUMP", "하이 점프", "project_term"),
    ("misc", "SPEED BOOSTER", "스피드 부스터", "official"),
    ("misc", "SPACE JUMP", "스페이스 점프", "project_term"),
    ("misc", "SCREW ATTACK", "스크루 어택", "project_term"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def panel_entries(tilemap: bytes, box: tuple[int, int, int, int]) -> dict:
    entries = struct.unpack("<1024H", tilemap)
    left, top, right, bottom = box
    x0, y0 = left // 8, top // 8
    x1, y1 = right // 8, bottom // 8
    selected = [entries[y * 32 + x] for y in range(y0, y1) for x in range(x0, x1)]
    return {
        "tile_rect": [x0, y0, x1 - x0, y1 - y0],
        "entry_count": len(selected),
        "tile_ids": sorted({entry & 0x3FF for entry in selected}),
        "palette_banks": sorted({(entry >> 12) & 0xF for entry in selected}),
    }


def expected_payloads() -> tuple[bytes, bytes, bytes, bytes, bytes]:
    rom = load_source()
    if sha256(rom) != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("supported source ROM SHA-256 mismatch")
    tiles, tiles_used = decompress_gba_lz77(rom[TILESET_OFFSET:])
    tilemap, map_used = decompress_gba_lz77(rom[TILEMAP_OFFSET:])
    palette = rom[PALETTE_OFFSET:PALETTE_OFFSET + PALETTE_BYTES]
    if sha256(tiles) != EXPECTED_TILESET_DECODED_SHA256 or len(tiles) != 32768:
        raise RuntimeError("status tileset decode mismatch")
    if sha256(tilemap) != EXPECTED_TILEMAP_DECODED_SHA256 or len(tilemap) != 2048:
        raise RuntimeError("status tilemap decode mismatch")
    if len(palette) != PALETTE_BYTES:
        raise RuntimeError("status palette is truncated")
    return (
        rom[TILESET_OFFSET:TILESET_OFFSET + tiles_used],
        tiles,
        rom[TILEMAP_OFFSET:TILEMAP_OFFSET + map_used],
        tilemap,
        palette,
    )


def build() -> dict:
    compressed_tiles, tiles, compressed_map, tilemap, palette = expected_payloads()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = {
        "pause_status_tileset.lz77.bin": compressed_tiles,
        "pause_status_tileset.4bpp.bin": tiles,
        "pause_status_tilemap.lz77.bin": compressed_map,
        "pause_status_tilemap.u16le.bin": tilemap,
        "pause_status_palette.bgr555.bin": palette,
    }
    for name, data in raw_files.items():
        (OUTPUT_DIR / name).write_bytes(data)

    full_path = OUTPUT_DIR / "status_screen_composed_native.png"
    render_tilemap(tiles, tilemap, palette, full_path, scale=1)
    grid_path = OUTPUT_DIR / "status_screen_composed_grid_4x.png"
    render_tilemap_grid(tiles, tilemap, palette, grid_path, scale=4)

    with Image.open(full_path) as full:
        for panel_id, box in PANELS.items():
            native = full.crop(box)
            native.save(OUTPUT_DIR / f"panel_{panel_id}_native.png")
            native.resize(
                (native.width * 4, native.height * 4), Image.Resampling.NEAREST
            ).save(OUTPUT_DIR / f"panel_{panel_id}_4x.png")
        item_area = full.crop((0, 160, 256, 256))
        item_area.resize((1024, 384), Image.Resampling.NEAREST).save(
            OUTPUT_DIR / "status_item_area_4x.png"
        )

    csv_path = OUTPUT_DIR / "status_item_labels.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("group", "source_graphic", "ko_candidate", "term_status", "artifact_status"))
        for row in LABELS:
            writer.writerow((*row, "source_extraction"))

    panel_report = {
        panel_id: {
            "pixel_box_native": list(box),
            **panel_entries(tilemap, box),
        }
        for panel_id, box in PANELS.items()
    }
    report = {
        "schema_version": 1,
        "status": "extracted_source_graphics",
        "source_rom_sha256": EXPECTED_SOURCE_SHA256,
        "consumer": "pause status BG composed from preloaded tileset A and tilemap 05",
        "assets": {
            "tileset": {
                "rom_offset": f"0x{TILESET_OFFSET:06X}",
                "compressed_bytes": len(compressed_tiles),
                "compressed_sha256": sha256(compressed_tiles),
                "decoded_bytes": len(tiles),
                "decoded_sha256": sha256(tiles),
                "format": "GBA LZ77 type 0x10 -> 1024 x 4bpp 8x8 tiles",
            },
            "tilemap": {
                "rom_offset": f"0x{TILEMAP_OFFSET:06X}",
                "compressed_bytes": len(compressed_map),
                "compressed_sha256": sha256(compressed_map),
                "decoded_bytes": len(tilemap),
                "decoded_sha256": sha256(tilemap),
                "format": "GBA LZ77 type 0x10 -> 32x32 u16 little-endian BG entries",
            },
            "palette": {
                "rom_offset": f"0x{PALETTE_OFFSET:06X}",
                "bytes": len(palette),
                "sha256": sha256(palette),
                "format": "16 banks x 16 BGR555 colors",
            },
        },
        "panels": panel_report,
        "labels": [
            {
                "group": group,
                "source_graphic": source,
                "ko_candidate": ko,
                "term_status": status,
                "artifact_status": "source_extraction",
            }
            for group, source, ko, status in LABELS
        ],
        "output_hashes": {},
    }
    output_files = sorted(path for path in OUTPUT_DIR.iterdir() if path.is_file() and path.name != "manifest.json")
    report["output_hashes"] = {path.name: sha256(path.read_bytes()) for path in output_files}
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def verify() -> dict:
    expected_payloads()
    manifest_path = OUTPUT_DIR / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("status item extraction manifest is missing")
    report = json.loads(manifest_path.read_text(encoding="utf-8"))
    if report["status"] != "extracted_source_graphics":
        raise RuntimeError("unexpected extraction status")
    for name, expected_hash in report["output_hashes"].items():
        path = OUTPUT_DIR / name
        if not path.is_file() or sha256(path.read_bytes()) != expected_hash:
            raise RuntimeError(f"missing or stale extracted file: {name}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    report = build() if args.command == "build" else verify()
    print(json.dumps({
        "status": "pass",
        "output_dir": str(OUTPUT_DIR),
        "labels": len(report["labels"]),
        "panels": len(report["panels"]),
        "translation_status": report["status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
