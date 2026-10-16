from __future__ import annotations

import hashlib
import json
import os
import unittest
from pathlib import Path

from PIL import Image

PROJECT = Path(__file__).resolve().parents[2]
PROFILE = PROJECT / "workspace" / "config" / "small_font_profile.json"


class SmallFontProfileTests(unittest.TestCase):
    def test_galmuri7_bitmap_atlas_matches_profile(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        source = (Path(os.environ["MF_FONT_DIR"]) / Path(profile["font"]["file"]).name
                  if "MF_FONT_DIR" in os.environ else (PROJECT / profile["font"]["file"]).resolve())
        self.assertEqual(
            hashlib.sha256(source.read_bytes()).hexdigest().upper(),
            profile["font"]["sha256"],
        )
        with Image.open(source) as image:
            rgba = image.convert("RGBA")
        self.assertEqual(list(rgba.size), profile["raster"]["atlas_px"])

        cell_w, cell_h = profile["raster"]["source_cell_px"]
        columns = profile["raster"]["atlas_columns"]
        cells = (rgba.width // cell_w) * (rgba.height // cell_h)
        self.assertEqual(cells, profile["raster"]["atlas_cells"])
        pixels = rgba.load()
        populated = []
        for index in range(cells):
            x0 = (index % columns) * cell_w
            y0 = (index // columns) * cell_h
            populated.append(
                any(
                    pixels[x, y] == (99, 207, 99, 255)
                    for y in range(y0, y0 + cell_h)
                    for x in range(x0, x0 + cell_w)
                )
            )
        hangul = profile["raster"]["populated_hangul_cells"]
        self.assertTrue(all(populated[:hangul]))
        self.assertFalse(any(populated[hangul:]))
        self.assertEqual(cells - hangul, profile["raster"]["transparent_tail_cells"])
        self.assertEqual(
            sorted(set(rgba.get_flattened_data())),
            sorted(tuple(color) for color in profile["raster"]["rgba_palette"]),
        )


if __name__ == "__main__":
    unittest.main()
