from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from PIL import Image


PROJECT = Path(__file__).resolve().parents[2]
REPORT = PROJECT / "workspace" / "analysis" / "file_select_background_runtime_qa.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class FileSelectBackgroundRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_fixed_runtime_evidence_hashes(self):
        for item in self.report["evidence"].values():
            if not isinstance(item, dict) or "path" not in item:
                continue
            self.assertEqual(digest(PROJECT / item["path"]), item["sha256"])

    def test_popup_deep_blue_fill_is_restored(self):
        fixed = self.report["evidence"]["v26_fixed_screen"]
        image = Image.open(PROJECT / fixed["path"]).convert("RGB")
        left, top, right, bottom = self.report["reference_observation"]["sample_rect_native_pixels"]
        navy = tuple(self.report["reference_observation"]["navy_rgb"])
        pixels = sum(
            image.getpixel((x, y)) == navy
            for y in range(top, bottom)
            for x in range(left, right)
        )
        self.assertEqual(pixels, self.report["fixed_build"]["navy_pixels_in_popup_sample_rect"])
        self.assertGreater(pixels, 3500)

    def test_window_sprite_tiles_match_original_runtime_vram(self):
        original = (PROJECT / "qa/logs/file_select_menu_state_original/vram.bin").read_bytes()
        fixed = (PROJECT / "qa/logs/file_select_menu_state_v26/vram.bin").read_bytes()
        for first in (0x0E0, 0x100, 0x120, 0x140):
            start = 0x10000 + first * 32
            end = start + 8 * 32
            self.assertEqual(fixed[start:end], original[start:end])


if __name__ == "__main__":
    unittest.main()
