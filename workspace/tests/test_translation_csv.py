from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "workspace" / "scripts"))

import translation_csv as tc


class TranslationCsvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = tc.build_rows()
        cls.by_id = {row["entry_id"]: row for row in cls.rows}

    def test_population_and_readable_reference(self):
        self.assertEqual(len(self.rows), 349)
        self.assertIn("There's been an explosion", self.by_id["navigation/ja/000"]["공식_영어_참고문"])
        self.assertIn("{ctrl:B003}", self.by_id["navigation/ja/000"]["공식_영어_원문_코드"])
        self.assertEqual(
            self.by_id["navigation/ja/000"]["번역_기준"],
            "ROM 내장 공식 영어(동일 인덱스)",
        )
        self.assertIn(
            "공식 일본어 설명서", self.by_id["file_select/ja/025"]["번역_기준"]
        )
        self.assertTrue(
            self.by_id["file_select/ja/028"]["번역_기준"].startswith("미확정")
        )
        self.assertEqual(self.by_id["monologue/ja/000"]["화자"], "사무스")
        self.assertEqual(self.by_id["message/ja/000"]["화자"], "시스템")
        self.assertEqual(
            sum(row["공식_영어_참고문"].startswith("※") for row in self.rows), 4
        )

    def test_speaker_switch_sequences(self):
        self.assertTrue(
            self.by_id["navigation/ja/050"]["화자"].startswith(
                "연방 본부(추정) → ADAM 컴퓨터(추정)"
            )
        )
        self.assertIn(
            "ADAM 컴퓨터(추정) → 사무스(추정)",
            self.by_id["navigation/ja/102"]["화자"],
        )
        self.assertIn("【사무스(추정)】", self.by_id["navigation/ja/104"]["공식_영어_참고문"])

    def test_utf8_bom_export_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.csv"
            tc.write_csv(path, self.rows)
            self.assertTrue(path.read_bytes().startswith(b"\xEF\xBB\xBF"))
            actual = tc.read_csv(path)
            self.assertEqual(tc.validate_rows(actual, require_editable_match=True)["rows"], 349)

    def test_protected_field_change_is_rejected(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["ROM_오프셋"] = "0x000000"
        with self.assertRaises(tc.TranslationCsvError):
            tc.validate_rows(rows, require_editable_match=False)

    def test_english_raw_control_change_is_rejected(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["공식_영어_원문_코드"] = rows[0]["공식_영어_원문_코드"].replace(
            "{ctrl:B003}", ""
        )
        with self.assertRaises(tc.TranslationCsvError):
            tc.validate_rows(rows, require_editable_match=False)

    def test_korean_semantic_control_change_is_rejected(self):
        rows = [dict(row) for row in self.rows]
        row = next(item for item in rows if item["entry_id"] == "navigation/ja/104")
        row["한국어_번역"] = row["한국어_번역"].replace("{ctrl:905B}", "")
        with self.assertRaises(tc.TranslationCsvError):
            tc.validate_rows(rows, require_editable_match=False)

    def test_korean_page_count_change_is_allowed_as_layout(self):
        rows = [dict(row) for row in self.rows]
        row = next(item for item in rows if item["entry_id"] == "navigation/ja/000")
        row["한국어_번역"] = row["한국어_번역"].replace("{ctrl:FD00}", "", 1)
        result = tc.validate_rows(rows, require_editable_match=False)
        self.assertEqual(result["rows"], 349)

    def test_korean_80xx_horizontal_indent_change_is_allowed_as_layout(self):
        rows = [dict(row) for row in self.rows]
        row = next(item for item in rows if item["entry_id"] == "message/ja/000")
        row["한국어_번역"] = row["한국어_번역"].replace("{ctrl:8012}", "{ctrl:8033}")
        row["한국어_번역"] = row["한국어_번역"].replace("{ctrl:8016}", "{ctrl:8033}")
        result = tc.validate_rows(rows, require_editable_match=False)
        self.assertEqual(result["rows"], 349)

    def test_korean_closing_quote_glyph_is_allowed_as_readable_text(self):
        rows = [dict(row) for row in self.rows]
        row = next(item for item in rows if item["entry_id"] == "navigation/ja/104")
        row["한국어_번역"] = row["한국어_번역"].replace(
            "{glyph:0311}", "{glyph:0311}아담{glyph:0312}", 1
        )
        result = tc.validate_rows(rows, require_editable_match=False)
        self.assertEqual(result["rows"], 349)

    def test_review_draft_can_differ_from_build_json(self):
        rows = [dict(row) for row in self.rows]
        row = next(item for item in rows if item["entry_id"] == "message/ja/027")
        row["한국어_번역"] = "{ctrl:8028}수위가 내려갔습니다.{br}{ctrl:806E}{end}"
        row["상태"] = "needs_review"
        result = tc.validate_rows(rows, require_editable_match=False)
        self.assertEqual(result["editable_changes"], 1)
        with self.assertRaises(tc.TranslationCsvError):
            tc.validate_rows(rows, require_editable_match=True)


if __name__ == "__main__":
    unittest.main()
