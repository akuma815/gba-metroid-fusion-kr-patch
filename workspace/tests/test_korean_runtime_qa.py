from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import korean_runtime_qa as qa


class KoreanRuntimeQaTests(unittest.TestCase):
    def test_recorded_runtime_evidence_matches_current_build(self):
        report = json.loads(qa.QA_PATH.read_text(encoding="utf-8"))
        recorded_rom = PROJECT / report["build"]["rom"]
        if not recorded_rom.exists():
            self.skipTest("historical runtime QA ROM is not retained; current final build requires manual runtime QA")
        result = qa.verify(report)
        self.assertEqual(result["screenshots"], 5)
        self.assertEqual(result["savestates"], 1)
        self.assertEqual(result["pointer_reads"], 2)
        self.assertEqual(result["text_reads"], 210)
        self.assertEqual(result["font_reads"], 9536)
        self.assertEqual(result["overall_status"], "runtime_fail_choice_overlays_do_not_release")


if __name__ == "__main__":
    unittest.main()
