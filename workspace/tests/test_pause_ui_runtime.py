from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
REPORT = PROJECT / "workspace" / "analysis" / "pause_ui_runtime.json"


class PauseUiRuntimeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_evidence_files_and_log_hash(self):
        baseline = self.report["baseline"]
        self.assertTrue((PROJECT / baseline["route_script"]).is_file())
        self.assertTrue((PROJECT / baseline["probe_script"]).is_file())
        for screenshot in self.report["route"]["screenshots"].values():
            self.assertTrue((PROJECT / screenshot).is_file())
        log = self.report["probe_log"]
        data = (PROJECT / log["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest().upper(), log["sha256"])

    def test_pause_text_classification(self):
        phases = {phase["id"]: phase for phase in self.report["phases"]}
        entry = phases["pause_map_entry"]
        self.assertEqual(entry["message_entry_ids"], [
            "message/ja/045", "message/ja/046", "message/ja/047"
        ])
        self.assertEqual(entry["japanese_message_text_unique_read_addresses"], 73)
        self.assertEqual(entry["main_font_unique_read_addresses"], 5376)
        self.assertEqual(phases["status_transition_and_steady"]["main_font_unique_read_addresses"], 0)


if __name__ == "__main__":
    unittest.main()
