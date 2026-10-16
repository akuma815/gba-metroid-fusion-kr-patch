"""Galmuri 글리프 원천을 Fusion 16x16 글리프 격자로 만든다."""
from functools import lru_cache
from pathlib import Path
import os

from PIL import Image, ImageFont

PROJECT = Path(__file__).resolve().parents[2]
FONT_DIR = Path(os.environ.get("MF_FONT_DIR", str(PROJECT.parents[1] / "Font")))

HANGUL_FIRST = 0xAC00
HANGUL_LAST = 0xD7A3
BITMAP_SHEET_SIZE = (576, 2100)
BITMAP_CELL_SIZE = (9, 12)
BITMAP_COLUMNS = 64
BITMAP_FOREGROUND = (99, 207, 99, 255)
BITMAP_BACKGROUND = (0, 0, 0, 255)
BITMAP_TRANSPARENT = (0, 0, 0, 0)


@lru_cache(maxsize=None)
def _load_bitmap_sheet(png: str) -> Image.Image:
    path = FONT_DIR / png
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if image.size != BITMAP_SHEET_SIZE:
        raise ValueError(f"bitmap sheet size {image.size} != {BITMAP_SHEET_SIZE}")
    colors = set(image.get_flattened_data())
    allowed = {BITMAP_FOREGROUND, BITMAP_BACKGROUND, BITMAP_TRANSPARENT}
    if not colors <= allowed:
        raise ValueError(f"unexpected bitmap sheet colors: {sorted(colors - allowed)}")
    return image


def sheet_bitmap(ch: str, png: str) -> list[list[int]]:
    """9x12 고정 셀 시트에서 완성형 한글 한 글자를 추출한다."""
    if len(ch) != 1 or not HANGUL_FIRST <= ord(ch) <= HANGUL_LAST:
        raise ValueError(f"not a modern precomposed Hangul syllable: {ch!r}")
    image = _load_bitmap_sheet(png)
    index = ord(ch) - HANGUL_FIRST
    cell_w, cell_h = BITMAP_CELL_SIZE
    left = (index % BITMAP_COLUMNS) * cell_w
    top = (index // BITMAP_COLUMNS) * cell_h
    pixels = list(image.crop((left, top, left + cell_w, top + cell_h)).get_flattened_data())
    if any(pixel not in {BITMAP_FOREGROUND, BITMAP_BACKGROUND} for pixel in pixels):
        raise ValueError(f"transparent or invalid pixel inside glyph U+{ord(ch):04X}")
    rows = [
        [1 if pixels[y * cell_w + x] == BITMAP_FOREGROUND else 0 for x in range(cell_w)]
        for y in range(cell_h)
    ]
    if not any(value for row in rows for value in row):
        raise ValueError(f"empty bitmap glyph U+{ord(ch):04X}")
    return rows


def render_sheet_bitmap(
    ch: str,
    png: str,
    box: tuple[int, int] = (16, 16),
    at: tuple[int, int] = (1, 1),
) -> list[list[int]]:
    glyph = sheet_bitmap(ch, png)
    w, h = box
    cell_w, cell_h = BITMAP_CELL_SIZE
    ox, oy = at
    if ox < 0 or oy < 0 or ox + cell_w > w or oy + cell_h > h:
        raise ValueError(f"9x12 bitmap cell at {at} does not fit {box}")
    out = [[0] * w for _ in range(h)]
    for y, row in enumerate(glyph):
        for x, value in enumerate(row):
            out[oy + y][ox + x] = value
    return out


def ink_bitmap(ch: str, ttf: str, size: int) -> list[list[int]]:
    font = ImageFont.truetype(str(FONT_DIR / ttf), size)
    mask = font.getmask(ch, mode="1")
    w, h = mask.size
    if w == 0 or h == 0:
        return []
    img = Image.frombuffer("L", (w, h), bytes(mask), "raw", "L", 0, 1)
    rows = [[1 if img.getpixel((x, y)) else 0 for x in range(w)] for y in range(h)]
    xs = [x for y in range(h) for x in range(w) if rows[y][x]]
    ys = [y for y in range(h) for x in range(w) if rows[y][x]]
    if not xs:
        return []
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    return [row[x0:x1 + 1] for row in rows[y0:y1 + 1]]


def render_bitmap(ch: str, ttf: str, size: int, box=(16, 16), at=(1, 3)) -> list[list[int]]:
    ink = ink_bitmap(ch, ttf, size)
    w, h = box
    out = [[0] * w for _ in range(h)]
    ox, oy = at
    for y, row in enumerate(ink):
        for x, value in enumerate(row):
            tx, ty = ox + x, oy + y
            if value and 0 <= tx < w and 0 <= ty < h:
                out[ty][tx] = 1
    return out


def outline(rows: list[list[int]], body: int, edge: int) -> list[list[int]]:
    h, w = len(rows), len(rows[0])
    out = [[body if rows[y][x] else 0 for x in range(w)] for y in range(h)]
    for y in range(h):
        for x in range(w):
            if rows[y][x]:
                continue
            if any(0 <= y + dy < h and 0 <= x + dx < w and rows[y + dy][x + dx]
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                out[y][x] = edge
    return out


def extent(rows):
    xs = [x for y, row in enumerate(rows) for x, v in enumerate(row) if v]
    ys = [y for y, row in enumerate(rows) for x, v in enumerate(row) if v]
    return (min(xs), max(xs), min(ys), max(ys)) if xs else (0, -1, 0, -1)
