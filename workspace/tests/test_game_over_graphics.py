import hashlib
import json
import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace/scripts"))

import game_over_graphics as gog


class GameOverGraphicsTests(unittest.TestCase):
    def test_build_contains_korean_game_over_for_base_and_overlay(self):
        report = json.loads((PROJECT / "workspace/analysis/game_over_runtime_qa.json").read_text(encoding="utf-8"))
        rom_path = PROJECT / report["build"]["rom"]
        rom = rom_path.read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest().upper(), report["build"]["rom_sha256"])
        source = (PROJECT / "original/Metroid Fusion (Japan).gba").read_bytes()
        gog.verify_image(rom, gog.build_plan(source))

    def test_adult_and_child_runtime_captures_are_identical(self):
        report = json.loads((PROJECT / "workspace/analysis/game_over_runtime_qa.json").read_text(encoding="utf-8"))
        hashes = []
        for mode in ("adult", "child"):
            item = report["runtime"][mode]
            path = PROJECT / item["screenshot"]
            got = hashlib.sha256(path.read_bytes()).hexdigest().upper()
            self.assertEqual(got, item["sha256"])
            hashes.append(got)
        self.assertEqual(hashes[0], hashes[1])


if __name__ == "__main__":
    unittest.main()
