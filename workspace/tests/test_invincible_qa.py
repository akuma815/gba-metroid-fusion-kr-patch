import hashlib
import json
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]


class InvincibleQaTests(unittest.TestCase):
    def test_verified_jp_addresses_and_rom_identity(self):
        report = json.loads((PROJECT / "workspace/analysis/invincible_qa.json").read_text(encoding="utf-8"))
        self.assertEqual(report["target"]["rom_title"], "METROID4JPN")
        self.assertEqual(report["target"]["game_code"], "AMTJ")
        self.assertEqual(report["addresses"]["current_energy_offset"], "0x1344")
        self.assertEqual(report["addresses"]["maximum_energy_offset"], "0x1346")
        self.assertEqual(report["addresses"]["current_missiles_offset"], "0x1348")
        self.assertEqual(report["addresses"]["maximum_missiles_offset"], "0x134A")
        rom = PROJECT / report["target"]["qa_rom"]
        self.assertEqual(hashlib.sha256(rom.read_bytes()).hexdigest().upper(), report["target"]["qa_rom_sha256"])

    def test_script_uses_current_energy_and_current_missile_write_barriers(self):
        source = (PROJECT / "workspace/tests/cheat_invincible.lua").read_text(encoding="utf-8")
        self.assertRegex(source, r"local ENERGY = 0x1344")
        self.assertRegex(source, r"local MAX_ENERGY = 0x1346")
        self.assertRegex(source, r"local MISSILES = 0x1348")
        self.assertRegex(source, r"local MAX_MISSILES = 0x134A")
        self.assertIn("emu.callbackType.write, ENERGY, ENERGY + 1", source)
        self.assertIn("emu.callbackType.write, MISSILES, MISSILES + 1", source)
        self.assertIn("local offset = address % 0x10000", source)
        self.assertIn("return protectedEnergy % 256", source)
        self.assertIn("return protectedMissiles % 256", source)
        callbacks = source.split("emu.addMemoryCallback(function(address, value)")[1:]
        self.assertEqual(len(callbacks), 2)
        for callback in callbacks:
            self.assertNotIn("emu.read(address, IW", callback)

    def test_missiles_arm_only_during_valid_gameplay_and_do_not_block_maximum(self):
        source = (PROJECT / "workspace/tests/cheat_invincible.lua").read_text(encoding="utf-8")
        self.assertIn("if armed and maximumMissiles >= 1", source)
        self.assertIn("currentMissiles >= 1 and currentMissiles <= maximumMissiles", source)
        self.assertNotIn("emu.callbackType.write, MAX_MISSILES", source)


if __name__ == "__main__":
    unittest.main()
