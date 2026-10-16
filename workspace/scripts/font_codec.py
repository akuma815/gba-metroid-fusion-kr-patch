"""Metroid Fusion JP 본문 폰트 4bpp 코덱과 확인용 시트 생성기."""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT = Path(__file__).resolve().parents[2]
ROM = PROJECT / "original" / "Metroid Fusion (Japan).gba"
FONT_BASE = 0x683AD8
FONT_BOTTOM_DELTA = 0x400


def decode_tile(data: bytes) -> list[list[int]]:
    if len(data) != 32:
        raise ValueError(f"4bpp tile size {len(data)} != 32")
    rows = []
    for y in range(8):
        row = []
        for b in data[y * 4:(y + 1) * 4]:
            row.extend((b & 0xF, b >> 4))
        rows.append(row)
    return rows


def encode_tile(rows: list[list[int]]) -> bytes:
    if len(rows) != 8 or any(len(row) != 8 for row in rows):
        raise ValueError("tile grid must be 8x8")
    out = bytearray()
    for row in rows:
        for x in range(0, 8, 2):
            out.append((row[x] & 0xF) | ((row[x + 1] & 0xF) << 4))
    return bytes(out)


def glyph_offsets(code: int) -> dict[str, int]:
    top = FONT_BASE + code * 32
    return {
        "left_top": top,
        "right_top": top + 32,
        "left_bottom": top + FONT_BOTTOM_DELTA,
        "right_bottom": top + FONT_BOTTOM_DELTA + 32,
    }


def decode_fullwidth(rom: bytes, code: int) -> list[list[int]]:
    o = glyph_offsets(code)
    lt = decode_tile(rom[o["left_top"]:o["left_top"] + 32])
    rt = decode_tile(rom[o["right_top"]:o["right_top"] + 32])
    lb = decode_tile(rom[o["left_bottom"]:o["left_bottom"] + 32])
    rb = decode_tile(rom[o["right_bottom"]:o["right_bottom"] + 32])
    return [lt[y] + rt[y] for y in range(8)] + [lb[y] + rb[y] for y in range(8)]


def encode_fullwidth(rows: list[list[int]]) -> dict[str, bytes]:
    if len(rows) != 16 or any(len(row) != 16 for row in rows):
        raise ValueError("glyph grid must be 16x16")
    return {
        "left_top": encode_tile([row[:8] for row in rows[:8]]),
        "right_top": encode_tile([row[8:] for row in rows[:8]]),
        "left_bottom": encode_tile([row[:8] for row in rows[8:]]),
        "right_bottom": encode_tile([row[8:] for row in rows[8:]]),
    }


def render_sheet(rom: bytes, codes: list[int], output: Path, scale: int = 8):
    cell_w, cell_h = 20, 22
    sheet = Image.new("RGB", (cell_w * len(codes), cell_h), "#202020")
    draw = ImageDraw.Draw(sheet)
    palette = {
        0: (0, 0, 0), 1: (80, 80, 80), 2: (160, 160, 160),
        3: (255, 255, 255), 4: (255, 80, 80), 5: (80, 255, 80),
        6: (80, 80, 255), 7: (255, 255, 80), 8: (255, 80, 255),
        9: (80, 255, 255), 10: (192, 96, 32), 11: (96, 192, 32),
        12: (32, 96, 192), 13: (192, 32, 96), 14: (96, 32, 192), 15: (224, 224, 224),
    }
    for idx, code in enumerate(codes):
        rows = decode_fullwidth(rom, code)
        x0 = idx * cell_w + 2
        for y, row in enumerate(rows):
            for x, value in enumerate(row):
                sheet.putpixel((x0 + x, y + 1), palette[value])
        draw.text((idx * cell_w + 1, 18), f"{code:04X}", fill="white")
        colors = sorted({v for row in rows for v in row})
        print(f"0x{code:04X}: colors={colors}")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.resize((sheet.width * scale, sheet.height * scale), Image.Resampling.NEAREST).save(output)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+", help="hex glyph start codes")
    ap.add_argument("--rom", default=str(ROM))
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=int, default=8)
    args = ap.parse_args()
    render_sheet(Path(args.rom).read_bytes(), [int(v, 16) for v in args.codes], Path(args.out), args.scale)


if __name__ == "__main__":
    main()
