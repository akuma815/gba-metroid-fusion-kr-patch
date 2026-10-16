import importlib.util
import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT / "tools" / "dialogue_editor" / "metroid_dialogue_editor.py"
SPEC = importlib.util.spec_from_file_location("metroid_dialogue_editor", MODULE_PATH)
editor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = editor
SPEC.loader.exec_module(editor)


class DialogueEditorTests(unittest.TestCase):
    def test_normalize_and_pages(self):
        text = editor.normalize_tokens("첫 줄\n둘째{ctrl:fd00}다음{end}")
        self.assertEqual(text, "첫 줄{br}둘째{ctrl:FD00}다음{end}")
        self.assertEqual(editor.split_preview_pages(text), ["첫 줄{br}둘째", "다음{end}"])

    def test_token_validation(self):
        self.assertEqual(editor.token_errors("테스트{br}완료{end}"), [])
        self.assertTrue(editor.token_errors("테스트"))
        self.assertTrue(editor.token_errors("{ctrl:1234}{end}"))

    def test_token_validation_reports_page_line_and_context(self):
        issues = editor.token_validation_issues("첫줄{br}둘째{ctrl:12ZZ}{end}")
        self.assertTrue(issues)
        self.assertIn("1페이지 2줄", issues[0].message)
        self.assertIn("⟦{ctrl:12ZZ}⟧", issues[0].message)
        self.assertIsNotNone(issues[0].start)

    def test_protected_token_diagnostics_identify_missing_extra_and_order(self):
        baseline = editor.protected_tokens("{ctrl:E200}대사{ctrl:905C}{end}")

        missing = editor.protected_token_issues(baseline, "{ctrl:E200}대사{end}")
        self.assertIn("제어문 누락", missing[0].message)
        self.assertIn("{ctrl:905C}", missing[0].message)
        self.assertIn("삽입 위치", missing[0].message)

        extra = editor.protected_token_issues(
            baseline, "{ctrl:E200}대사{ctrl:905C}{ctrl:E202}{end}"
        )
        self.assertIn("추가 제어문", extra[0].message)
        self.assertIn("{ctrl:E202}", extra[0].message)
        self.assertIsNotNone(extra[0].start)

        reordered = editor.protected_token_issues(
            baseline, "{ctrl:905C}대사{ctrl:E200}{end}"
        )
        self.assertIn("제어문 순서 변경", reordered[0].message)
        self.assertIn("#1", reordered[0].message)
        self.assertIn("문자열", reordered[0].message)

    def test_layout_tokens_are_movable(self):
        left = "{ctrl:E200}문장{br}{ctrl:FD00}끝{end}"
        right = "{ctrl:E200}{br}문장끝{ctrl:FD00}{end}"
        self.assertEqual(editor.protected_tokens(left), editor.protected_tokens(right))

    def test_curly_quote_uses_build_alias(self):
        renderer = editor.GameFontPreview()
        self.assertEqual(renderer._char_glyph("‘")[1:], (renderer._width(0x47), None))
        image, _, _, _ = renderer.render("미리보기{end}")
        self.assertEqual(image.size, (480, 128))

    def test_catalog_contains_only_tokens_used_by_current_translation(self):
        path = editor.DEFAULT_CSV
        document = editor.DialogueDocument.load(path)
        catalog = editor.collect_used_tokens(document.entries)
        actual = set()
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                actual.update(editor.normalize_tokens(token) for token in editor.TOKEN_RE.findall(row["한국어_번역"]))
        self.assertEqual({item.token for item in catalog}, actual)
        self.assertTrue(all(item.count > 0 for item in catalog))

    def test_color_and_nonvisual_controls_are_reflected_in_preview(self):
        renderer = editor.GameFontPreview()
        image, _, _, _ = renderer.render("{ctrl:8103}가{ctrl:E200}{ctrl:8100}나{end}", scale=1)
        self.assertIn(editor.PREVIEW_COLORS[0x8103], image.get_flattened_data())
        self.assertIn("8103 핵심어 강조색", renderer.last_effects)
        self.assertIn("E200 ADAM 화자", renderer.last_effects)
        self.assertIn("8100 기본색", renderer.last_effects)

    def test_fb00_is_visible_and_carried_to_following_page(self):
        frames = editor.build_preview_frames(
            "{ctrl:E200}첫 장면{ctrl:FB00}{ctrl:FD00}다음 장면{end}",
            "ADAM 컴퓨터(추정)",
        )
        self.assertEqual(len(frames), 2)
        self.assertNotIn(0xFB00, frames[0].controls)
        self.assertEqual(frames[1].inherited_effects, (0xFB00,))
        self.assertEqual(frames[0].text, "{ctrl:E200}첫 장면")
        self.assertEqual(frames[1].text, "다음 장면{end}")
        renderer = editor.GameFontPreview()
        plain, _, _, _ = renderer.render("다음 장면{end}", scale=1)
        effected, _, _, _ = renderer.render(
            "다음 장면{end}", scale=1, inherited_effects=(0xFB00,)
        )
        self.assertNotEqual(plain.tobytes(), effected.tobytes())
        self.assertIn("FB00 이전 페이지 연출 이어짐", renderer.last_effects)

    def test_fb00_alone_is_a_page_break_without_blank_consecutive_page(self):
        text = "첫 페이지{ctrl:FB00}{ctrl:FD00}둘째 페이지{end}"
        self.assertEqual(editor.split_preview_pages(text), ["첫 페이지", "둘째 페이지{end}"])
        frames = editor.build_preview_frames(text)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[1].inherited_effects, (0xFB00,))

    def test_csv_keeps_raw_english_code_for_synchronized_preview(self):
        document = editor.DialogueDocument.load(editor.DEFAULT_CSV)
        entry = next(item for item in document.entries if item.entry_id == "navigation/ja/000")
        self.assertTrue(entry.english_code.startswith("{ctrl:B003}"))
        self.assertTrue(entry.japanese.startswith("{ctrl:B003}"))
        en_frames = editor.build_preview_frames(entry.english_code, entry.speaker)
        ja_frames = editor.build_preview_frames(entry.japanese, entry.speaker)
        self.assertGreater(len(en_frames), 1)
        self.assertGreater(len(ja_frames), 1)

    def test_layout_comparison_reports_page_line_and_transition_differences(self):
        aligned_text = "첫줄{br}둘째{ctrl:FB00}다음{end}"
        aligned_frames = editor.build_preview_frames(aligned_text)
        aligned = editor.layout_comparison(aligned_frames, aligned_frames, aligned_frames, 1)
        self.assertTrue(aligned["aligned"])
        self.assertEqual(aligned["pages"], {"한": 2, "영": 2, "일": 2})
        self.assertEqual(aligned["transitions"]["한"], "FB00")

        different = editor.layout_comparison(
            aligned_frames,
            editor.build_preview_frames("첫줄{end}"),
            editor.build_preview_frames("첫줄{br}둘째{end}"),
            1,
        )
        self.assertFalse(different["aligned"])
        self.assertIsNone(different["lines"]["영"])

    def test_unknown_e_control_is_not_drawn_inside_game_preview(self):
        renderer = editor.GameFontPreview()
        plain, _, _, _ = renderer.render("문장{end}", scale=1)
        controlled, _, _, _ = renderer.render("문장{ctrl:E000}{end}", scale=1)
        self.assertEqual(plain.tobytes(), controlled.tobytes())
        self.assertIn("E000", " ".join(renderer.last_effects))

    def test_english_space_uses_rom_advance_and_source_preview_scale_matches_korean(self):
        renderer = editor.GameFontPreview()
        space_code = renderer.literal_codes[" "]
        self.assertEqual(renderer._width(space_code), 6)
        space_rows, space_advance, _ = renderer._char_glyph(" ")
        latin_rows, latin_advance, _ = renderer._char_glyph("A")
        self.assertEqual((len(space_rows), len(space_rows[0]), space_advance), (16, 8, 6))
        self.assertFalse(any(value for row in space_rows for value in row))
        self.assertEqual((len(latin_rows), len(latin_rows[0]), latin_advance), (16, 8, 8))
        self.assertTrue(any(value for row in latin_rows for value in row))
        japanese_rows = renderer._code_glyph(0x0155)
        self.assertEqual((len(japanese_rows), len(japanese_rows[0])), (16, 8))
        self.assertEqual(renderer._width(0x0155), 8)
        korean, _, _, _ = renderer.render("한국어{end}", scale=2)
        english, _, _, _ = renderer.render("A B{end}", scale=2)
        japanese, _, _, _ = renderer.render("{glyph:0155}{glyph:01D2}{end}", scale=2)
        self.assertEqual(korean.size, (480, 128))
        self.assertEqual(english.size, korean.size)
        self.assertEqual(japanese.size, korean.size)

    def test_two_speaker_pages_are_assigned_to_separate_panes(self):
        frames = editor.build_preview_frames(
            "{ctrl:E200}아담{ctrl:FD00}{ctrl:E201}사무스{ctrl:FD00}{ctrl:E200}응답{end}",
            "ADAM 컴퓨터(추정) → 사무스(추정)",
        )
        slots = editor.dialogue_speaker_slots(frames)
        self.assertEqual([frame.speaker_code for frame in frames], [0xE200, 0xE201, 0xE200])
        self.assertEqual(slots[0xE200], "top")
        self.assertEqual(slots[0xE201], "bottom")

    def test_monologue_and_system_use_separate_layout_limits(self):
        monologue = editor.preview_profile("독백")
        system = editor.preview_profile("시스템 메시지")
        dialogue = editor.preview_profile("내비게이션")
        self.assertEqual((monologue.style, monologue.lines), ("monologue", 9))
        self.assertEqual((system.style, system.lines), ("system", 2))
        self.assertEqual((dialogue.style, dialogue.lines), ("dialogue", 3))
        renderer = editor.GameFontPreview()
        image, overflow, _, line_count = renderer.render(
            "첫 줄{br}둘째 줄{br}셋째 줄{end}",
            system.content_width, system.lines, scale=1, style=system.style,
        )
        self.assertEqual(image.size, (240, 48))
        self.assertEqual(line_count, 3)
        self.assertTrue(overflow)

    def test_position_control_changes_preview_cursor(self):
        renderer = editor.GameFontPreview()
        renderer.render("{ctrl:8057}테스트{end}", scale=1)
        self.assertIn("8057 가로 시작점 X=99px (기본 위치에서 +87px)", renderer.last_effects)

    def test_control_descriptions_explain_known_effect_and_uncertainty(self):
        position = editor.used_token_info("{ctrl:8012}")
        self.assertEqual(position.label, "가로 시작점 X=30px (기본 위치에서 +18px)")
        self.assertIn("현재 줄은 유지", position.description)
        unresolved = editor.used_token_info("{ctrl:905F}")
        self.assertIn("게임 상태·이벤트 동기화", unresolved.label)
        self.assertIn("아직 확인되지 않았습니다", unresolved.description)

    def test_system_position_controls_preserve_the_br_line(self):
        renderer = editor.GameFontPreview()
        self.assertEqual(renderer._position_x(0x8012), 30)
        self.assertEqual(renderer._position_x(0x804C), 88)
        image, overflow, errors, line_count = renderer.render(
            "{ctrl:8012}Security Level 1 unlocked.{br}"
            "{ctrl:8016}Blue hatches now active.{end}",
            scale=1,
            style="system",
            lines=2,
        )
        foreground = editor.PREVIEW_COLORS[0x8100]
        self.assertTrue(any(image.getpixel((x, y)) == foreground
                            for y in range(8, 24) for x in range(2, 238)))
        self.assertTrue(any(image.getpixel((x, y)) == foreground
                            for y in range(24, 40) for x in range(2, 238)))
        self.assertEqual((overflow, errors, line_count), (False, [], 2))

    def test_json_roundtrip_changes_only_editable_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.json"
            path.write_text('{"schema_version":1,"entries":[{"entry_id":"x","ko":"기존{end}","status":"needs_review","protected":7}]}', encoding="utf-8")
            document = editor.DialogueDocument.load(path)
            document.entries[0].translation = "수정{end}"
            document.save()
            value = __import__("json").loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["entries"][0]["ko"], "수정{end}")
            self.assertEqual(value["entries"][0]["protected"], 7)


if __name__ == "__main__":
    unittest.main()
