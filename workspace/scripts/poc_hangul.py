"""Fusion JP 한글 가시성 비교 PoC.

어트랙트 데모의 위치명 `メインデッキ`가 소비하는 6개 글리프 시작 코드를
`한글표시검토`로 교체한다. 텍스트·포인터는 바꾸지 않는다.
"""
import argparse
from pathlib import Path

from font_codec import encode_fullwidth, glyph_offsets
from hangul_glyph import extent, outline, render_sheet_bitmap
from rombuild import PROJECT, RomBuilder

DEFAULT_BITMAP = "Galmuri11-Condensed_9x12.png"
WIDTH_TABLE = 0x578934

# 실제 화면의 소비 순서는 메(0192), 이(0152), 인(019D),
# 덱의 첫 글리프(01C3), 두 번째 글리프(014F), 데(0157) 순이다.
# 코드값을 일본어 표기 순서로 정렬하면 런타임 표시 순서와 어긋난다.
MAPPING = [
    (0x0192, "メ", "한"),
    (0x0152, "イ", "글"),
    (0x019D, "ン", "표"),
    (0x0157, "デ", "토"),
    (0x01C3, "ッ", "시"),
    (0x014F, "キ", "검"),
]


def install(b: RomBuilder, code: int, ch: str, at: tuple[int, int]):
    # Fusion JP navigation text uses palette index 2 for the bright body and
    # index 3 for the dark outline.  Reversing these produces hollow glyphs.
    rows = outline(render_sheet_bitmap(ch, DEFAULT_BITMAP, at=at), body=2, edge=3)
    tiles = encode_fullwidth(rows)
    offsets = glyph_offsets(code)
    for name, data in tiles.items():
        off = offsets[name]
        b.write(off, data, b.source[off:off + len(data)], f"glyph:{ch}:{name}")
    x0, x1, y0, y1 = extent(rows)
    return x1 - x0 + 1, y1 - y0 + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", default="1,1")
    ap.add_argument("--width", type=int, default=12,
                    help="대상 6코드 진행폭 (기본 12)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    at = tuple(int(v) for v in args.at.split(","))
    if len(at) != 2:
        raise SystemExit("--at must be x,y")

    b = RomBuilder()
    print(f"font={DEFAULT_BITMAP} source_cell=9x12 at={at}")
    max_width = 0
    for code, source, korean in MAPPING:
        width, height = install(b, code, korean, at)
        max_width = max(max_width, width)
        print(f"0x{code:04X} {source}->{korean}: {width}x{height}px")

    advance = args.width
    for code, _, korean in MAPPING:
        off = WIDTH_TABLE + code
        b.write(off, bytes([args.width]), bytes([8]), f"width:{korean}={args.width}")
    if max_width > advance:
        raise SystemExit(f"glyph width {max_width}px exceeds advance {advance}px")
    print(f"advance={advance}px, max glyph width={max_width}px")

    name = args.out or f"poc_Galmuri11-Condensed_bitmap_9x12_w{advance}.gba"
    output = PROJECT / "build" / name
    b.save(output)
    print(b.summary())
    print("output:", output)
    print("expected: 메인 덱 위치명 대신 `한글표시검토`")


if __name__ == "__main__":
    main()
