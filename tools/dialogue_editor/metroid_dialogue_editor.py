"""Metroid Fusion Korean dialogue/control-code editor with an exact-font preview."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from difflib import SequenceMatcher
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk


PROJECT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT / "workspace" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from font_codec import decode_tile, glyph_offsets  # noqa: E402
from hangul_glyph import outline, render_sheet_bitmap  # noqa: E402
from navigation_text import REVERSE_CHARACTERS  # noqa: E402


DEFAULT_CSV = PROJECT / "workspace" / "text" / "review" / "metroid_fusion_translation_ko_english_controlcodes_fixed.csv"
ROM_PATH = PROJECT / "original" / "Metroid Fusion (Japan).gba"
CODE_MAP_PATH = PROJECT / "workspace" / "config" / "hangul_code_map.json"
FONT_PNG = "Galmuri11-Condensed_9x12.png"
WIDTH_TABLE_OFFSET = 0x578934
WIDTH_TABLE_LAST_CODE = 0x049F

TOKEN_RE = re.compile(r"\{(?:br|end|ctrl:[0-9A-Fa-f]{4}|glyph:[0-9A-Fa-f]{4})\}")
STRICT_TOKEN_RE = re.compile(r"\{(br|end|ctrl|glyph)(?::([0-9A-Fa-f]{4}))?\}")
LAYOUT_TOKENS = {"{br}", "{ctrl:FD00}"}
EDITABLE_CSV_FIELDS = {"한국어_번역", "상태", "메모"}

PREVIEW_COLORS = {
    0x8100: (245, 245, 245),  # default
    0x8101: (255, 224, 90),   # security / warning emphasis
    0x8102: (103, 224, 255),  # place / destination emphasis
    0x8103: (255, 100, 226),  # important term emphasis
    0x8104: (145, 160, 170),  # inactive / empty entry
    0x8106: (100, 150, 255),  # security level emphasis
}

CONTROL_NAMES = {
    0x8100: ("기본색", "색상", "기본 문자색으로 복귀"),
    0x8101: ("보안/경고 강조색", "색상", "보안 및 경고 용어 강조"),
    0x8102: ("지역/목적지 강조색", "색상", "지역·시설·목적지 강조"),
    0x8103: ("핵심어 강조색", "색상", "인물·적·능력·주요 용어 강조"),
    0x8104: ("비활성/빈 항목색", "색상", "비어 있음 등 비활성 표시"),
    0x8106: ("보안 레벨 강조색", "색상", "보안 레벨·해치 강조"),
    0x8340: ("선택지 1 배치", "배치/선택", "첫 번째 선택지의 배치/선택 정보"),
    0x83A0: ("선택지 2 배치", "배치/선택", "두 번째 선택지의 배치/선택 정보"),
    0xE200: ("ADAM 화자", "화자/연출", "ADAM 화자로 전환"),
    0xE201: ("사무스 화자", "화자/연출", "사무스 화자로 전환"),
    0xE202: ("시스템/기타 화자", "화자/연출", "시스템 또는 기타 화자로 전환"),
    0xFB00: ("연출 페이지 전환", "화자/연출", "현재 페이지를 끝내고 다음 연출 페이지로 전환"),
    0xFC00: ("흐름 제어 FC00", "화자/연출", "메시지 흐름/연출 전환; 화면에는 직접 표시되지 않음"),
    0xFD00: ("페이지 넘김", "줄/페이지", "다음 메시지 페이지로 전환"),
}

SPEAKER_CONTROLS = {
    0xE200: "ADAM 컴퓨터",
    0xE201: "사무스",
    0xE202: "연방 본부",
}


@dataclass(frozen=True)
class PreviewProfile:
    key: str
    label: str
    content_width: int
    lines: int
    style: str


PREVIEW_PROFILES = {
    "dialogue": PreviewProfile("dialogue", "내비게이션 대화창", 216, 3, "dialogue"),
    "monologue": PreviewProfile("monologue", "독백 전용 화면", 216, 9, "monologue"),
    "system": PreviewProfile("system", "시스템 메시지 화면", 216, 2, "system"),
    "location": PreviewProfile("location", "지역명 화면", 216, 1, "system"),
    "file_select": PreviewProfile("file_select", "파일 선택 화면", 216, 6, "system"),
}


def preview_profile(category: str) -> PreviewProfile:
    if category == "독백":
        return PREVIEW_PROFILES["monologue"]
    if category == "시스템 메시지":
        return PREVIEW_PROFILES["system"]
    if category == "지역명":
        return PREVIEW_PROFILES["location"]
    if category in {"파일 선택", "공용 UI"}:
        return PREVIEW_PROFILES["file_select"]
    return PREVIEW_PROFILES["dialogue"]


def infer_speaker_code(speaker: str) -> int | None:
    first = speaker.split("→", 1)[0].strip()
    if "사무스" in first:
        return 0xE201
    if "연방 본부" in first:
        return 0xE202
    if "ADAM" in first or "아담" in first:
        return 0xE200
    return None


@dataclass(frozen=True)
class PreviewFrame:
    text: str
    speaker_code: int | None
    speaker_label: str
    inherited_effects: tuple[int, ...]
    controls: tuple[int, ...]


def build_preview_frames(text: str, speaker: str = "") -> list[PreviewFrame]:
    """Split pages while carrying speaker state and one-shot visual transitions."""
    current_speaker = infer_speaker_code(speaker)
    fallback_label = speaker.split("→", 1)[0].strip() or "화자 미지정"
    frames: list[PreviewFrame] = []
    for page, inherited_effects in split_preview_segments(text):
        controls = tuple(
            int(match.group(1), 16)
            for match in re.finditer(r"\{ctrl:([0-9A-Fa-f]{4})\}", page)
        )
        page_speaker = current_speaker
        for code in controls:
            if code in SPEAKER_CONTROLS:
                current_speaker = code
                page_speaker = code
                break
        frames.append(PreviewFrame(
            text=page,
            speaker_code=page_speaker,
            speaker_label=SPEAKER_CONTROLS.get(page_speaker, fallback_label),
            inherited_effects=inherited_effects,
            controls=controls,
        ))
        for code in controls:
            if code in SPEAKER_CONTROLS:
                current_speaker = code
    return frames or [PreviewFrame("", current_speaker,
                                   SPEAKER_CONTROLS.get(current_speaker, fallback_label), (), ())]


def dialogue_speaker_slots(frames: list[PreviewFrame]) -> dict[int | None, str]:
    """Assign the first two speakers in an entry to the upper/lower preview panes."""
    ordered: list[int | None] = []
    for frame in frames:
        if frame.speaker_code not in ordered:
            ordered.append(frame.speaker_code)
    slots: dict[int | None, str] = {}
    for index, code in enumerate(ordered):
        slots[code] = "top" if index % 2 == 0 else "bottom"
    return slots


def frame_line_count(frame: PreviewFrame | None) -> int | None:
    if frame is None:
        return None
    return frame.text.count("{br}") + 1


def layout_comparison(ko_frames: list[PreviewFrame], en_frames: list[PreviewFrame],
                      ja_frames: list[PreviewFrame], page_index: int) -> dict:
    groups = {"한": ko_frames, "영": en_frames, "일": ja_frames}
    pages = {name: len(frames) for name, frames in groups.items()}
    current = {
        name: frames[page_index] if 0 <= page_index < len(frames) else None
        for name, frames in groups.items()
    }
    lines = {name: frame_line_count(frame) for name, frame in current.items()}
    transitions = {
        name: ("FB00" if frame and 0xFB00 in frame.inherited_effects else "일반")
        for name, frame in current.items()
    }
    available_lines = [value for value in lines.values() if value is not None]
    available_transitions = [value for name, value in transitions.items() if current[name] is not None]
    aligned = (
        len(set(pages.values())) == 1
        and len(available_lines) == 3 and len(set(available_lines)) == 1
        and len(available_transitions) == 3 and len(set(available_transitions)) == 1
    )
    return {
        "pages": pages,
        "lines": lines,
        "transitions": transitions,
        "aligned": aligned,
    }


@dataclass(frozen=True)
class UsedToken:
    token: str
    label: str
    group: str
    description: str
    count: int = 0


def position_control_x(code: int) -> int:
    """Return the preview X coordinate selected by an 80xx indent control."""
    return 12 + (code & 0x7F)


def used_token_info(token: str, count: int = 0) -> UsedToken:
    """Describe only a token that is already present in the loaded translation."""
    normalized = normalize_tokens(token)
    if normalized == "{br}":
        return UsedToken(normalized, "줄바꿈", "줄/페이지", "같은 페이지의 다음 줄로 이동", count)
    if normalized == "{end}":
        return UsedToken(normalized, "대사 종료", "줄/페이지", "현재 대사 데이터 종료", count)
    match = STRICT_TOKEN_RE.fullmatch(normalized)
    if not match:
        return UsedToken(normalized, normalized, "기타", "인식할 수 없는 토큰", count)
    kind, value = match.groups()
    code = int(value, 16)
    if kind == "glyph":
        return UsedToken(normalized, f"특수 글리프 {code:04X}", "특수 글리프",
                         "ROM의 해당 글리프를 직접 표시", count)
    if code in CONTROL_NAMES:
        label, group, description = CONTROL_NAMES[code]
        return UsedToken(normalized, label, group, description, count)
    if 0x8000 <= code <= 0x80FF:
        indent = code & 0x7F
        x = position_control_x(code)
        return UsedToken(
            normalized,
            f"가로 시작점 X={x}px (기본 위치에서 +{indent}px)",
            "배치/선택",
            f"현재 줄은 유지하고 다음 문자의 가로 시작점을 화면 X={x}px로 이동합니다. "
            f"대화창 기본 위치 12px에서 {indent}px 들여쓴 값입니다.",
            count,
        )
    if 0x9000 <= code <= 0xBFFF:
        return UsedToken(normalized, "게임 상태·이벤트 동기화 (세부 의미 미확정)", "게임 상태",
                         "게임 상태나 이벤트를 동기화하며 문자로는 표시되지 않습니다. "
                         "이 코드 하나의 세부 조건은 아직 확인되지 않았습니다.", count)
    if 0xE000 <= code <= 0xE3FF:
        return UsedToken(normalized, "화자·음성·화면 연출 (세부 의미 미확정)", "화자/연출",
                         "화자·음성·화면 연출을 제어하며 문자로는 표시되지 않습니다. "
                         "이 코드 하나의 세부 연출은 아직 확인되지 않았습니다.", count)
    return UsedToken(normalized, "비표시 게임 제어 (세부 의미 미확정)", "기타 제어",
                     "화면에 문자를 그리지 않는 게임 제어입니다. 세부 의미는 아직 확인되지 않았습니다.", count)


def collect_used_tokens(entries: list["DialogueEntry"]) -> list[UsedToken]:
    counts: dict[str, int] = {}
    for entry in entries:
        for raw_token in TOKEN_RE.findall(entry.translation):
            token = normalize_tokens(raw_token)
            counts[token] = counts.get(token, 0) + 1
    return [used_token_info(token, count) for token, count in sorted(counts.items())]


def normalize_tokens(text: str) -> str:
    """Normalize token hex and turn literal editor newlines into game line breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "{br}")
    return re.sub(
        r"\{(ctrl|glyph):([0-9A-Fa-f]{4})\}",
        lambda match: "{" + match.group(1) + ":" + match.group(2).upper() + "}",
        text,
    )


@dataclass(frozen=True)
class ValidationIssue:
    message: str
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class TokenOccurrence:
    token: str
    start: int
    end: int


def describe_offset(text: str, offset: int) -> str:
    offset = max(0, min(offset, len(text)))
    prefix = text[:offset]
    page = prefix.count("{ctrl:FD00}") + 1
    page_prefix = prefix.rsplit("{ctrl:FD00}", 1)[-1]
    line = page_prefix.count("{br}") + 1
    return f"{page}페이지 {line}줄, 문자열 {offset + 1}번째"


def context_at(text: str, start: int, end: int | None = None, radius: int = 18) -> str:
    end = start if end is None else end
    left, right = max(0, start - radius), min(len(text), end + radius)
    before = text[left:start].replace("{br}", "↵").replace("{ctrl:FD00}", "⇥")
    target = text[start:end].replace("{br}", "↵").replace("{ctrl:FD00}", "⇥")
    after = text[end:right].replace("{br}", "↵").replace("{ctrl:FD00}", "⇥")
    marker = f"⟦{target}⟧" if target else "⟦삽입 위치⟧"
    return "…" + before + marker + after + "…"


def normalized_to_raw_offset(raw_text: str, normalized_offset: int) -> int:
    """Map a normalized {br}-expanded offset back to the Tk text widget."""
    raw_index = 0
    normalized_index = 0
    while raw_index < len(raw_text) and normalized_index < normalized_offset:
        if raw_text.startswith("\r\n", raw_index):
            if normalized_index + 4 >= normalized_offset:
                return raw_index
            raw_index += 2
            normalized_index += 4
        elif raw_text[raw_index] in "\r\n":
            if normalized_index + 4 >= normalized_offset:
                return raw_index
            raw_index += 1
            normalized_index += 4
        else:
            raw_index += 1
            normalized_index += 1
    return raw_index


def token_validation_issues(text: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    pos = 0
    while pos < len(text):
        if text[pos] != "{":
            pos += 1
            continue
        match = STRICT_TOKEN_RE.match(text, pos)
        if not match:
            closing = text.find("}", pos + 1)
            end = len(text) if closing < 0 else closing + 1
            issues.append(ValidationIssue(
                f"잘못된 제어문 — {describe_offset(text, pos)} / {context_at(text, pos, end)}",
                pos, end,
            ))
            pos = end
            continue
        kind, value = match.groups()
        if kind in {"br", "end"} and value is not None:
            issues.append(ValidationIssue(
                f"{{{kind}}}에는 값을 넣을 수 없습니다 — {describe_offset(text, pos)} / "
                f"{context_at(text, pos, match.end())}", pos, match.end()))
        elif kind == "ctrl" and int(value, 16) < 0x8000:
            issues.append(ValidationIssue(
                f"ctrl 값은 8000 이상이어야 합니다 — {describe_offset(text, pos)} / "
                f"{context_at(text, pos, match.end())}", pos, match.end()))
        elif kind == "glyph" and int(value, 16) >= 0x8000:
            issues.append(ValidationIssue(
                f"glyph 값은 8000 미만이어야 합니다 — {describe_offset(text, pos)} / "
                f"{context_at(text, pos, match.end())}", pos, match.end()))
        pos = match.end()
    if not text.endswith("{end}"):
        issues.append(ValidationIssue(
            f"문장 끝에 {{end}}가 없습니다 — {describe_offset(text, len(text))} / "
            f"{context_at(text, len(text))}", len(text), len(text)))
    end_matches = list(re.finditer(r"\{end\}", text))
    if len(end_matches) > 1:
        for match in end_matches[1:]:
            issues.append(ValidationIssue(
                f"추가 {{end}}를 삭제하십시오 — {describe_offset(text, match.start())} / "
                f"{context_at(text, match.start(), match.end())}", match.start(), match.end()))
    return issues


def token_errors(text: str) -> list[str]:
    return [issue.message for issue in token_validation_issues(text)]


def protected_token_occurrences(text: str) -> list[TokenOccurrence]:
    layout = {item.lower() for item in LAYOUT_TOKENS}
    occurrences: list[TokenOccurrence] = []
    for match in TOKEN_RE.finditer(text):
        raw = match.group(0)
        token = normalize_tokens(raw)
        if token.lower() not in layout:
            occurrences.append(TokenOccurrence(token, match.start(), match.end()))
    return occurrences


def protected_token_issues(expected: list[str], current_text: str) -> list[ValidationIssue]:
    """Explain exactly which protected token is missing, extra, or reordered."""
    current = protected_token_occurrences(current_text)
    actual = [item.token for item in current]
    if expected == actual:
        return []

    if Counter(expected) == Counter(actual):
        mismatch = next(index for index, pair in enumerate(zip(expected, actual)) if pair[0] != pair[1])
        wanted, found = expected[mismatch], current[mismatch]
        wanted_at = next(index for index, token in enumerate(actual) if token == wanted and index != mismatch)
        return [ValidationIssue(
            f"제어문 순서 변경: #{mismatch + 1}은 {wanted}여야 하지만 {found.token}입니다. "
            f"{wanted}은 현재 #{wanted_at + 1}에 있습니다 — "
            f"{describe_offset(current_text, found.start)} / {context_at(current_text, found.start, found.end)}",
            found.start, found.end,
        )]

    issues: list[ValidationIssue] = []
    matcher = SequenceMatcher(a=expected, b=actual, autojunk=False)
    for operation, i1, i2, j1, j2 in matcher.get_opcodes():
        if operation == "equal":
            continue
        paired = min(i2 - i1, j2 - j1) if operation == "replace" else 0
        for offset in range(paired):
            expected_token = expected[i1 + offset]
            found = current[j1 + offset]
            issues.append(ValidationIssue(
                f"제어문 불일치: 저장 기준 #{i1 + offset + 1} {expected_token} 대신 "
                f"{found.token}이 있습니다 — {describe_offset(current_text, found.start)} / "
                f"{context_at(current_text, found.start, found.end)}",
                found.start, found.end,
            ))
        for index in range(i1 + paired, i2):
            anchor = current[j1 + paired].start if j1 + paired < len(current) else len(current_text)
            issues.append(ValidationIssue(
                f"제어문 누락: 저장 기준 #{index + 1} {expected[index]}을(를) 이 위치에 넣어야 합니다 — "
                f"{describe_offset(current_text, anchor)} / {context_at(current_text, anchor)}",
                anchor, anchor,
            ))
        for index in range(j1 + paired, j2):
            found = current[index]
            issues.append(ValidationIssue(
                f"추가 제어문: 저장 기준에 없는 {found.token}입니다 — "
                f"{describe_offset(current_text, found.start)} / {context_at(current_text, found.start, found.end)}",
                found.start, found.end,
            ))
    return issues


def protected_tokens(text: str) -> list[str]:
    """Tokens whose order affects events, speakers, emphasis, or glyph identity."""
    return [item.token for item in protected_token_occurrences(text)]


def split_preview_pages(text: str) -> list[str]:
    return [page for page, _effects in split_preview_segments(text)]


def split_preview_segments(text: str) -> list[tuple[str, tuple[int, ...]]]:
    """Split FD00/FB00 pages without creating blanks for consecutive delimiters."""
    text = normalize_tokens(text)
    segments: list[tuple[str, tuple[int, ...]]] = []
    pending_effects: tuple[int, ...] = ()
    start = 0
    delimiter_re = re.compile(r"\{ctrl:(FD00|FB00)\}")
    for match in delimiter_re.finditer(text):
        page = text[start:match.start()]
        if page:
            segments.append((page, pending_effects))
            pending_effects = ()
        if match.group(1) == "FB00":
            pending_effects = (0xFB00,)
        start = match.end()
    tail = text[start:]
    if tail or not segments:
        segments.append((tail, pending_effects))
    return segments


@dataclass
class DialogueEntry:
    entry_id: str
    category: str
    number: str
    speaker: str
    japanese: str
    english: str
    english_code: str
    translation: str
    status: str
    notes: str
    raw: dict
    translation_key: str
    status_key: str | None
    notes_key: str | None
    baseline_protected: list[str]


class DialogueDocument:
    def __init__(self, path: Path, kind: str, entries: list[DialogueEntry], payload, headers=None):
        self.path = path
        self.kind = kind
        self.entries = entries
        self.payload = payload
        self.headers = headers

    @classmethod
    def load(cls, path: Path) -> "DialogueDocument":
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return cls._load_csv(path)
        if suffix == ".json":
            return cls._load_json(path)
        raise ValueError("CSV 또는 JSON 파일만 지원합니다")

    @classmethod
    def _load_csv(cls, path: Path) -> "DialogueDocument":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            if "entry_id" not in headers or "한국어_번역" not in headers:
                raise ValueError("CSV에 entry_id와 한국어_번역 열이 필요합니다")
            rows = [dict(row) for row in reader]
        entries = [
            DialogueEntry(
                entry_id=row.get("entry_id", ""),
                category=row.get("구분", ""),
                number=row.get("번호", str(index)),
                speaker=row.get("화자", ""),
                japanese=row.get("일본어_원문_코드", ""),
                english=row.get("공식_영어_참고문") or row.get("공식_영어_원문_코드", ""),
                english_code=row.get("공식_영어_원문_코드", ""),
                translation=row.get("한국어_번역", ""),
                status=row.get("상태", ""),
                notes=row.get("메모", ""),
                raw=row,
                translation_key="한국어_번역",
                status_key="상태" if "상태" in headers else None,
                notes_key="메모" if "메모" in headers else None,
                baseline_protected=protected_tokens(row.get("한국어_번역", "")),
            )
            for index, row in enumerate(rows)
        ]
        return cls(path, "csv", entries, rows, headers)

    @classmethod
    def _load_json(cls, path: Path) -> "DialogueDocument":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = payload.get("entries") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("JSON은 entries 배열 또는 최상위 배열이어야 합니다")
        entries: list[DialogueEntry] = []
        for index, row in enumerate(rows):
            translation_key = next((key for key in ("ko", "한국어_번역", "translation", "text") if key in row), None)
            if translation_key is None:
                raise ValueError(f"JSON entries[{index}]에 ko/한국어_번역/translation/text 필드가 없습니다")
            entry_id = str(row.get("entry_id", row.get("id", index)))
            text = str(row.get(translation_key, ""))
            status_key = "status" if "status" in row else ("상태" if "상태" in row else None)
            notes_key = "notes" if "notes" in row else ("메모" if "메모" in row else None)
            entries.append(DialogueEntry(
                entry_id=entry_id,
                category=str(row.get("category", row.get("구분", entry_id.split("/", 1)[0]))),
                number=str(row.get("number", row.get("번호", index))),
                speaker=str(row.get("speaker", row.get("화자", ""))),
                japanese=str(row.get("japanese", row.get("일본어_원문_코드", ""))),
                english=str(row.get("english", row.get("공식_영어_참고문", ""))),
                english_code=str(row.get(
                    "english_code",
                    row.get("official_english_code", row.get("공식_영어_원문_코드", row.get("english", ""))),
                )),
                translation=text,
                status=str(row.get(status_key, "")) if status_key else "",
                notes=str(row.get(notes_key, "")) if notes_key else "",
                raw=row,
                translation_key=translation_key,
                status_key=status_key,
                notes_key=notes_key,
                baseline_protected=protected_tokens(text),
            ))
        return cls(path, "json", entries, payload)

    def sync(self) -> None:
        for entry in self.entries:
            entry.raw[entry.translation_key] = entry.translation
            if entry.status_key:
                entry.raw[entry.status_key] = entry.status
            if entry.notes_key:
                entry.raw[entry.notes_key] = entry.notes

    def save(self, path: Path | None = None) -> Path:
        destination = (path or self.path).resolve()
        self.sync()
        if destination.exists():
            backup_dir = PROJECT / "backups" / "dialogue_editor"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            shutil.copy2(destination, backup_dir / f"{destination.stem}_{stamp}{destination.suffix}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            if self.kind == "csv":
                with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=self.headers, lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(self.payload)
            else:
                temporary.write_text(json.dumps(self.payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        self.path = destination
        for entry in self.entries:
            entry.baseline_protected = protected_tokens(entry.translation)
        return destination


class GameFontPreview:
    def __init__(self):
        self.rom = ROM_PATH.read_bytes()
        code_map = json.loads(CODE_MAP_PATH.read_text(encoding="utf-8"))
        self.hangul_codes = {item["character"]: int(item["code"], 0) for item in code_map["mappings"]}
        self.literal_codes = dict(REVERSE_CHARACTERS)
        for raw_unicode, raw_code in code_map["policy"].get("curly_quote_aliases", {}).items():
            self.literal_codes[chr(int(raw_unicode.removeprefix("U+"), 16))] = int(raw_code, 0)
        self.literal_sequences = {
            chr(int(raw_unicode.removeprefix("U+"), 16)): replacement
            for raw_unicode, replacement in code_map["policy"].get("literal_sequence_aliases", {}).items()
        }
        self._glyph_cache: dict[tuple[str, int | str], list[list[int]]] = {}
        self.last_effects: list[str] = []

    def _char_glyph(self, char: str) -> tuple[list[list[int]] | None, int, str | None]:
        if char in self.hangul_codes:
            if ("char", char) not in self._glyph_cache:
                rows = render_sheet_bitmap(char, FONT_PNG, (16, 16), (1, 1))
                self._glyph_cache[("char", char)] = outline(rows, 2, 3)
            return self._glyph_cache[("char", char)], 12, None
        code = self.literal_codes.get(char)
        if code is None:
            return None, 12, f"미매핑 문자 {char!r} (U+{ord(char):04X})"
        return self._halfwidth_glyph(code), self._width(code), None

    def _halfwidth_glyph(self, code: int) -> list[list[int]]:
        """Decode the single 8x16 cell used by Latin literals and spaces."""
        key = ("half", code)
        if key not in self._glyph_cache:
            offsets = glyph_offsets(code)
            top = decode_tile(self.rom[offsets["left_top"]:offsets["left_top"] + 32])
            bottom = decode_tile(self.rom[offsets["left_bottom"]:offsets["left_bottom"] + 32])
            self._glyph_cache[key] = top + bottom
        return self._glyph_cache[key]

    def _code_glyph(self, code: int) -> list[list[int]]:
        key = ("code", code)
        if key not in self._glyph_cache:
            # A Japanese glyph code selects one 8x16 cell. Combining code+1
            # as a right half makes every preview cell contain two glyphs.
            self._glyph_cache[key] = self._halfwidth_glyph(code)
        return self._glyph_cache[key]

    def _width(self, code: int) -> int:
        if code <= WIDTH_TABLE_LAST_CODE:
            value = self.rom[WIDTH_TABLE_OFFSET + code]
            return value or 12
        return 12

    @staticmethod
    def _position_x(code: int) -> int:
        """Convert an 80xx text-indent control to the preview X coordinate."""
        return position_control_x(code)

    def render(self, page_text: str, content_width: int = 216, lines: int = 3, scale: int = 2,
               style: str = "dialogue", inherited_effects: tuple[int, ...] = ()):
        width, height = 240, 16 + lines * 16
        page_controls = tuple(
            int(match.group(1), 16)
            for match in re.finditer(r"\{ctrl:([0-9A-Fa-f]{4})\}", page_text)
        )
        visual_controls = inherited_effects + page_controls
        fb_effect = 0xFB00 in visual_controls
        backgrounds = {
            "dialogue": (2, 8, 10),
            "monologue": (4, 5, 13),
            "system": (10, 23, 43),
        }
        image = Image.new("RGB", (width, height),
                          (5, 22, 42) if fb_effect else backgrounds.get(style, backgrounds["dialogue"]))
        draw = ImageDraw.Draw(image)
        if style == "dialogue":
            border = (66, 215, 242) if fb_effect else (66, 219, 75)
            draw.rectangle((1, 1, width - 2, height - 2), outline=border, width=2)
        elif style == "system":
            draw.rectangle((1, 1, width - 2, height - 2), outline=(90, 145, 200), width=1)
        else:
            # Monologues are full-screen text rather than a navigation dialogue box.
            draw.line((8, 3, width - 9, 3), fill=(65, 75, 98))
        x, y = 12, 8
        line = 1
        overflow = False
        errors: list[str] = []
        self.last_effects = [f"{code:04X} 이전 페이지 연출 이어짐" for code in inherited_effects]
        foreground = PREVIEW_COLORS[0x8100]
        pos = 0
        while pos < len(page_text):
            if page_text[pos] == "{":
                match = STRICT_TOKEN_RE.match(page_text, pos)
                if not match:
                    errors.append(f"위치 {pos}: 잘못된 제어문")
                    pos += 1
                    continue
                kind, value = match.groups()
                pos = match.end()
                if kind == "br":
                    x, y, line = 12, y + 16, line + 1
                    self.last_effects.append("줄바꿈")
                elif kind == "end":
                    self.last_effects.append("대사 종료")
                    break
                elif kind == "glyph":
                    code = int(value, 16)
                    rows, advance = self._code_glyph(code), self._width(code)
                    x = self._paint_glyph(image, rows, x, y, advance, foreground)
                    self.last_effects.append(f"특수 글리프 {code:04X}")
                elif kind == "ctrl":
                    code = int(value, 16)
                    info = used_token_info(f"{{ctrl:{code:04X}}}")
                    self.last_effects.append(f"{code:04X} {info.label}")
                    if code in PREVIEW_COLORS:
                        foreground = PREVIEW_COLORS[code]
                    elif 0x8000 <= code <= 0x80FF:
                        # The low seven bits are a horizontal text indent. The
                        # control commonly follows {br}, so it must preserve the
                        # current Y/line instead of moving text back onto row 1.
                        x = self._position_x(code)
                continue
            char = page_text[pos]
            if char in self.literal_sequences:
                for replacement in self.literal_sequences[char]:
                    rows, advance, _ = self._char_glyph(replacement)
                    x = self._paint_glyph(image, rows, x, y, advance, foreground)
                pos += 1
                continue
            rows, advance, error = self._char_glyph(char)
            if error:
                errors.append(error)
                draw.rectangle((x, y, x + 9, y + 11), outline=(255, 64, 64))
            else:
                x = self._paint_glyph(image, rows, x, y, advance, foreground)
            if x - 12 > content_width:
                overflow = True
            pos += 1
        if line > lines:
            overflow = True
        if 0xFC00 in visual_controls:
            # FC00 terminates a monologue/system text beat. Show the same kind
            # of visible advance cue the editor needs for timing review.
            cx, cy = width // 2, height - 4
            draw.polygon(((cx - 4, cy - 3), (cx + 4, cy - 3), (cx, cy + 1)), fill=(245, 245, 245))
        if fb_effect:
            # FB00 changes presentation but draws no glyph. A cyan corner and
            # in-frame badge make the transition visible instead of relegating
            # it to the textual effect log.
            draw.rectangle((width - 37, 3, width - 4, 11), fill=(10, 56, 78), outline=(66, 215, 242))
            draw.text((width - 34, 3), "FB00 FX", fill=(160, 240, 255))
            draw.line((3, 3, 3, height - 4), fill=(66, 215, 242), width=2)
        if overflow:
            draw.rectangle((3, 3, width - 4, height - 4), outline=(255, 65, 65), width=1)
        return image.resize((width * scale, height * scale), Image.Resampling.NEAREST), overflow, errors, line

    @staticmethod
    def _paint_glyph(image: Image.Image, rows: list[list[int]], x: int, y: int, advance: int,
                     foreground: tuple[int, int, int] = (245, 245, 245)) -> int:
        shadow = tuple(max(24, channel // 3) for channel in foreground)
        midtone = tuple(max(40, (channel * 2) // 3) for channel in foreground)
        palette = {1: shadow, 2: foreground, 3: midtone, 4: foreground,
                   7: foreground, 8: foreground, 14: foreground, 15: foreground}
        for gy, row in enumerate(rows):
            for gx, value in enumerate(row):
                if value and 0 <= x + gx < image.width and 0 <= y + gy < image.height:
                    image.putpixel((x + gx, y + gy), palette.get(value, (245, 245, 245)))
        return x + advance


class DialogueEditor(tk.Tk):
    def __init__(self, initial_path: Path | None = None):
        super().__init__()
        self.title("Metroid Fusion 대사 조판 편집기")
        self.geometry("1560x980")
        self.minsize(1050, 720)
        self.document: DialogueDocument | None = None
        self.current_entry: DialogueEntry | None = None
        self.visible_entries: list[DialogueEntry] = []
        self.dirty = False
        self.page_index = 0
        self.preview_photos: dict[str, ImageTk.PhotoImage] = {}
        self.used_tokens: list[UsedToken] = []
        self.preview_renderer = GameFontPreview()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Control-o>", lambda _event: self.open_file())
        self.bind_all("<Control-s>", lambda _event: self.save_file())
        if initial_path and initial_path.exists():
            self.load_file(initial_path)

    def _build_ui(self):
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="열기  Ctrl+O", command=self.open_file).pack(side="left")
        ttk.Button(toolbar, text="저장  Ctrl+S", command=self.save_file).pack(side="left", padx=5)
        ttk.Button(toolbar, text="다른 이름으로 저장", command=lambda: self.save_file(save_as=True)).pack(side="left")
        self.file_label = ttk.Label(toolbar, text="파일을 여는 중...")
        self.file_label.pack(side="left", padx=14)

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(main, padding=4)
        right = ttk.Frame(main, padding=4)
        main.add(left, weight=1)
        main.add(right, weight=3)

        search_row = ttk.Frame(left)
        search_row.pack(fill="x", pady=(0, 5))
        ttk.Label(search_row, text="검색").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        ttk.Entry(search_row, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.count_label = ttk.Label(left, text="0개")
        self.count_label.pack(anchor="w", pady=(0, 4))

        self.tree = ttk.Treeview(left, columns=("kind", "speaker", "text"), show="headings", selectmode="browse")
        self.tree.heading("kind", text="구분")
        self.tree.heading("speaker", text="화자")
        self.tree.heading("text", text="번역문")
        self.tree.column("kind", width=88, stretch=False)
        self.tree.column("speaker", width=115, stretch=False)
        self.tree.column("text", width=280)
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        meta = ttk.LabelFrame(right, text="선택한 대사", padding=7)
        meta.pack(fill="x")
        self.id_label = ttk.Label(meta, text="entry_id")
        self.id_label.grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(meta, text="화자").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.speaker_label = ttk.Label(meta, text="-")
        self.speaker_label.grid(row=1, column=1, sticky="w", padx=(6, 20), pady=(5, 0))
        ttk.Label(meta, text="상태").grid(row=1, column=2, sticky="w", pady=(5, 0))
        self.status_var = tk.StringVar()
        self.status_box = ttk.Combobox(meta, textvariable=self.status_var, width=20,
                                       values=("needs_review", "needs_human_review", "reviewed", "approved"))
        self.status_box.grid(row=1, column=3, sticky="ew", padx=(6, 0), pady=(5, 0))
        self.status_box.bind("<<ComboboxSelected>>", lambda _event: self._mark_dirty())
        self.status_box.bind("<KeyRelease>", lambda _event: self._mark_dirty())
        meta.columnconfigure(3, weight=1)

        source_tabs = ttk.Notebook(right)
        source_tabs.pack(fill="x", pady=6)
        self.english_text = self._readonly_tab(source_tabs, "영문/참고")
        self.japanese_text = self._readonly_tab(source_tabs, "일문 코드")

        editor_box = ttk.LabelFrame(right, text="한국어 번역문 — Enter 키는 {br} 삽입", padding=7)
        editor_box.pack(fill="both", expand=True)
        token_bar = ttk.Frame(editor_box)
        token_bar.pack(fill="x", pady=(0, 5))
        for label, token in (("줄바꿈", "{br}"), ("페이지", "{ctrl:FD00}"), ("종료", "{end}")):
            ttk.Button(token_bar, text=label, width=7,
                       command=lambda value=token: self._insert_token(value)).pack(side="left", padx=(0, 3))
        self.control_buttons: dict[str, ttk.Menubutton] = {}
        for group, label in (("색상", "색상 코드 ▾"), ("배치/선택", "배치 코드 ▾"),
                             ("화자/연출", "화자·연출 ▾"), ("게임 상태", "상태 코드 ▾"),
                             ("기타 제어", "기타 코드 ▾"), ("특수 글리프", "특수 글리프 ▾")):
            button = ttk.Menubutton(token_bar, text=label)
            button.pack(side="left", padx=(4, 0))
            self.control_buttons[group] = button
        ttk.Button(token_bar, text="사용 코드 전체...", command=self._open_used_code_picker).pack(side="left", padx=(6, 0))

        text_frame = ttk.Frame(editor_box)
        text_frame.pack(fill="both", expand=True)
        self.translation_text = tk.Text(text_frame, wrap="word", undo=True, font=("Malgun Gothic", 12), height=11)
        edit_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.translation_text.yview)
        self.translation_text.configure(yscrollcommand=edit_scroll.set)
        self.translation_text.pack(side="left", fill="both", expand=True)
        edit_scroll.pack(side="right", fill="y")
        self.translation_text.bind("<KeyRelease>", self._on_text_change)
        self.translation_text.bind("<<Paste>>", lambda _event: self.after_idle(self._on_text_change))
        self.translation_text.bind("<Return>", self._return_as_br)
        self.translation_text.tag_configure("token", foreground="#8a2be2", font=("Consolas", 11, "bold"))
        self.translation_text.tag_configure("token_problem", foreground="#b00020", background="#ffd6d6",
                                            font=("Consolas", 11, "bold"))

        notes_row = ttk.Frame(right)
        notes_row.pack(fill="x", pady=6)
        ttk.Label(notes_row, text="메모").pack(side="left")
        self.notes_var = tk.StringVar()
        notes_entry = ttk.Entry(notes_row, textvariable=self.notes_var)
        notes_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        notes_entry.bind("<KeyRelease>", lambda _event: self._mark_dirty())

        preview = ttk.LabelFrame(right, text="게임 폰트 프리뷰", padding=7)
        preview.pack(fill="x")
        controls = ttk.Frame(preview)
        controls.pack(fill="x", pady=(0, 5))
        ttk.Button(controls, text="◀ 이전 페이지", command=lambda: self._change_page(-1)).pack(side="left")
        ttk.Button(controls, text="다음 페이지 ▶", command=lambda: self._change_page(1)).pack(side="left", padx=5)
        self.page_label = ttk.Label(controls, text="1 / 1")
        self.page_label.pack(side="left", padx=8)
        self.validation_label = ttk.Label(controls, text="")
        self.validation_label.pack(side="right")
        self.dialogue_preview = ttk.Frame(preview)
        self.dialogue_preview.pack(fill="x")
        self.top_speaker_label = ttk.Label(self.dialogue_preview, text="상단 화자", anchor="center")
        self.top_speaker_label.pack(fill="x")
        self.top_preview_canvas = tk.Canvas(self.dialogue_preview, width=480, height=128,
                                            bg="#111", highlightthickness=0)
        self.top_preview_canvas.pack(anchor="center")
        self.bottom_speaker_label = ttk.Label(self.dialogue_preview, text="하단 화자", anchor="center")
        self.bottom_speaker_label.pack(fill="x", pady=(4, 0))
        self.bottom_preview_canvas = tk.Canvas(self.dialogue_preview, width=480, height=128,
                                               bg="#111", highlightthickness=0)
        self.bottom_preview_canvas.pack(anchor="center")

        self.screen_preview = ttk.Frame(preview)
        self.screen_kind_label = ttk.Label(self.screen_preview, text="전용 화면", anchor="center")
        self.screen_kind_label.pack(fill="x")
        self.screen_preview_canvas = tk.Canvas(self.screen_preview, width=480, height=128,
                                               bg="#111", highlightthickness=0)
        self.screen_preview_canvas.pack(anchor="center")
        self.screen_preview.pack_forget()

        source_preview = ttk.LabelFrame(preview, text="원문 조판 비교 — 같은 페이지 번호", padding=5)
        source_preview.pack(fill="x", pady=(6, 0))
        source_columns = ttk.Frame(source_preview)
        source_columns.pack(anchor="center")
        english_column = ttk.Frame(source_columns)
        english_column.pack(side="left", padx=(0, 10))
        self.english_preview_label = ttk.Label(english_column, text="공식 영문", anchor="center")
        self.english_preview_label.pack(fill="x")
        self.english_preview_canvas = tk.Canvas(english_column, width=480, height=128,
                                                bg="#111", highlightthickness=0)
        self.english_preview_canvas.pack()
        japanese_column = ttk.Frame(source_columns)
        japanese_column.pack(side="left")
        self.japanese_preview_label = ttk.Label(japanese_column, text="일문", anchor="center")
        self.japanese_preview_label.pack(fill="x")
        self.japanese_preview_canvas = tk.Canvas(japanese_column, width=480, height=128,
                                                 bg="#111", highlightthickness=0)
        self.japanese_preview_canvas.pack()
        self.layout_comparison_label = ttk.Label(source_preview, text="", anchor="center", justify="center")
        self.layout_comparison_label.pack(fill="x", pady=(4, 0))
        self.control_effect_label = ttk.Label(preview, text="", justify="left", wraplength=1120)
        self.control_effect_label.pack(fill="x", pady=(5, 0))
        self.validation_detail_label = ttk.Label(preview, text="", justify="left", wraplength=1120)
        self.validation_detail_label.pack(fill="x", pady=(3, 0))

        # Reserve the preview and notes at the bottom before allowing the text
        # editor to consume the remaining vertical space.
        editor_box.pack_forget()
        notes_row.pack_forget()
        preview.pack_forget()
        preview.pack(side="bottom", fill="x")
        notes_row.pack(side="bottom", fill="x", pady=6)
        editor_box.pack(fill="both", expand=True)

    @staticmethod
    def _readonly_tab(notebook, title):
        frame = ttk.Frame(notebook)
        widget = tk.Text(frame, height=4, wrap="word", font=("Malgun Gothic", 9), background="#f4f4f4")
        widget.pack(fill="both", expand=True)
        widget.configure(state="disabled")
        notebook.add(frame, text=title)
        return widget

    def open_file(self):
        if not self._confirm_discard():
            return
        selected = filedialog.askopenfilename(initialdir=str(DEFAULT_CSV.parent),
                                              filetypes=(("번역 파일", "*.csv *.json"), ("CSV", "*.csv"), ("JSON", "*.json")))
        if selected:
            self.load_file(Path(selected))

    def load_file(self, path: Path):
        try:
            self.document = DialogueDocument.load(path)
        except Exception as exc:
            messagebox.showerror("불러오기 실패", str(exc))
            return
        self.current_entry = None
        self.dirty = False
        self.file_label.configure(text=str(path))
        self.used_tokens = collect_used_tokens(self.document.entries)
        self._refresh_control_menus()
        self._refresh_title()
        self._refresh_list(select_first=True)

    def _refresh_list(self, select_first=False):
        if not self.document:
            return
        selected_id = self.current_entry.entry_id if self.current_entry else None
        query = self.search_var.get().casefold().strip()
        self.visible_entries = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        for entry in self.document.entries:
            haystack = " ".join((entry.entry_id, entry.category, entry.speaker, entry.translation, entry.english)).casefold()
            if query and query not in haystack:
                continue
            index = len(self.visible_entries)
            self.visible_entries.append(entry)
            preview = TOKEN_RE.sub("", entry.translation).strip().replace("\n", " ")
            self.tree.insert("", "end", iid=str(index), values=(entry.category, entry.speaker, preview[:80]))
        self.count_label.configure(text=f"{len(self.visible_entries)} / {len(self.document.entries)}개")
        target = next((str(i) for i, entry in enumerate(self.visible_entries) if entry.entry_id == selected_id), None)
        if target is None and select_first and self.visible_entries:
            target = "0"
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        self._commit_current()
        self.current_entry = self.visible_entries[int(selection[0])]
        entry = self.current_entry
        self.id_label.configure(text=f"{entry.entry_id}  |  {entry.category} #{entry.number}")
        self.speaker_label.configure(text=entry.speaker or "-")
        self.status_var.set(entry.status)
        self.notes_var.set(entry.notes)
        self._set_readonly(self.english_text, entry.english)
        self._set_readonly(self.japanese_text, entry.japanese)
        self.translation_text.delete("1.0", "end")
        self.translation_text.insert("1.0", entry.translation)
        self.page_index = 0
        self._highlight_tokens()
        self._update_preview()

    @staticmethod
    def _set_readonly(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _commit_current(self):
        if not self.current_entry:
            return
        self.current_entry.translation = normalize_tokens(self.translation_text.get("1.0", "end-1c"))
        self.current_entry.status = self.status_var.get()
        self.current_entry.notes = self.notes_var.get()

    def _return_as_br(self, _event=None):
        self._insert_token("{br}")
        return "break"

    def _insert_token(self, token):
        self.translation_text.insert("insert", token)
        self.translation_text.focus_set()
        self._on_text_change()

    def _refresh_control_menus(self):
        for group, button in self.control_buttons.items():
            menu = tk.Menu(button, tearoff=False)
            items = [item for item in self.used_tokens if item.group == group]
            if not items:
                menu.add_command(label="(현재 번역에서 미사용)", state="disabled")
                button.configure(state="disabled")
            else:
                for item in items:
                    menu.add_command(label=f"{item.token}  {item.label}  ({item.count}회)",
                                     command=lambda value=item.token: self._insert_token(value))
                button.configure(state="normal")
            button.configure(menu=menu)

    def _open_used_code_picker(self):
        if not self.document:
            return
        window = tk.Toplevel(self)
        window.title("현재 번역에서 사용 중인 코드")
        window.geometry("900x600")
        window.transient(self)
        window.grab_set()

        ttk.Label(window, text="불러온 번역 텍스트에 실제 존재하는 코드만 표시합니다.", padding=(10, 8)).pack(fill="x")
        filter_row = ttk.Frame(window, padding=(10, 0, 10, 7))
        filter_row.pack(fill="x")
        ttk.Label(filter_row, text="검색").pack(side="left")
        query = tk.StringVar()
        ttk.Entry(filter_row, textvariable=query).pack(side="left", fill="x", expand=True, padx=(7, 0))

        body = ttk.Frame(window, padding=(10, 0))
        body.pack(fill="both", expand=True)
        tree = ttk.Treeview(body, columns=("token", "name", "group", "count"), show="headings", selectmode="browse")
        for key, label, width in (("token", "코드", 145), ("name", "기능", 270),
                                  ("group", "그룹", 150), ("count", "사용 횟수", 85)):
            tree.heading(key, text=label)
            tree.column(key, width=width, stretch=key == "name")
        scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        detail = ttk.Label(window, text="", padding=10, justify="left", wraplength=850)
        detail.pack(fill="x")

        visible: list[UsedToken] = []

        def refill(*_args):
            needle = query.get().casefold().strip()
            visible.clear()
            tree.delete(*tree.get_children())
            for item in self.used_tokens:
                haystack = f"{item.token} {item.label} {item.group} {item.description}".casefold()
                if needle and needle not in haystack:
                    continue
                index = len(visible)
                visible.append(item)
                tree.insert("", "end", iid=str(index), values=(item.token, item.label, item.group, item.count))
            if visible:
                tree.selection_set("0")
                tree.focus("0")
                tree.event_generate("<<TreeviewSelect>>")

        def selected_item() -> UsedToken | None:
            selection = tree.selection()
            return visible[int(selection[0])] if selection else None

        def show_detail(_event=None):
            item = selected_item()
            detail.configure(text=(f"{item.token}  —  {item.description}\n"
                                   "프리뷰에서 색상·배치는 화면에 반영되고, "
                                   "비표시 제어는 아래 실행 순서에 표시됩니다.") if item else "")

        def insert_selected(close=False):
            item = selected_item()
            if item:
                self._insert_token(item.token)
                if close:
                    window.destroy()

        query.trace_add("write", refill)
        tree.bind("<<TreeviewSelect>>", show_detail)
        tree.bind("<Double-1>", lambda _event: insert_selected(True))
        actions = ttk.Frame(window, padding=10)
        actions.pack(fill="x")
        ttk.Button(actions, text="선택 코드 삽입", command=insert_selected).pack(side="right")
        ttk.Button(actions, text="삽입하고 닫기", command=lambda: insert_selected(True)).pack(side="right", padx=6)
        ttk.Button(actions, text="닫기", command=window.destroy).pack(side="right")
        refill()

    def _on_text_change(self, _event=None):
        self._mark_dirty()
        page_count = max((len(frames) for frames in self._preview_frame_sets().values()), default=1)
        self.page_index = min(self.page_index, max(0, page_count - 1))
        self._highlight_tokens()
        self._update_preview()

    def _mark_dirty(self):
        if self.current_entry:
            self.dirty = True
            self._refresh_title()

    def _highlight_tokens(self):
        self.translation_text.tag_remove("token", "1.0", "end")
        content = self.translation_text.get("1.0", "end-1c")
        for match in TOKEN_RE.finditer(content):
            self.translation_text.tag_add("token", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def _change_page(self, delta):
        if not self.current_entry:
            return
        frame_sets = self._preview_frame_sets()
        page_count = max((len(frames) for frames in frame_sets.values()), default=1)
        self.page_index = max(0, min(page_count - 1, self.page_index + delta))
        self._update_preview()

    def _preview_frame_sets(self) -> dict[str, list[PreviewFrame]]:
        entry = self.current_entry
        if not entry:
            return {"ko": [], "en": [], "ja": []}
        ko_text = normalize_tokens(self.translation_text.get("1.0", "end-1c"))
        return {
            "ko": build_preview_frames(ko_text, entry.speaker),
            "en": build_preview_frames(entry.english_code, entry.speaker) if entry.english_code else [],
            "ja": build_preview_frames(entry.japanese, entry.speaker) if entry.japanese else [],
        }

    def _render_source_preview(self, language: str, frames: list[PreviewFrame],
                               profile: PreviewProfile, canvas: tk.Canvas,
                               label: ttk.Label) -> tuple[int | None, bool]:
        frame = frames[self.page_index] if self.page_index < len(frames) else None
        display = frame or PreviewFrame("", None, "해당 페이지 없음", (), ())
        image, overflow, _errors, line_count = self.preview_renderer.render(
            display.text, profile.content_width, profile.lines, 2, profile.style,
            display.inherited_effects,
        )
        key = "source_" + language
        self.preview_photos[key] = ImageTk.PhotoImage(image)
        canvas.configure(width=image.width, height=image.height)
        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=self.preview_photos[key])
        if frame is None:
            label.configure(text=f"{language} — {self.page_index + 1}/{len(frames)} 페이지 없음",
                            foreground="#b36b00")
            return None, False
        label.configure(
            text=f"{language} — {self.page_index + 1}/{len(frames)} | {line_count}/{profile.lines}줄",
            foreground="#b00020" if overflow else "#202020",
        )
        return line_count, overflow

    def _update_preview(self):
        if not self.current_entry:
            return
        text = normalize_tokens(self.translation_text.get("1.0", "end-1c"))
        frame_sets = self._preview_frame_sets()
        frames = frame_sets["ko"]
        profile = preview_profile(self.current_entry.category)
        page_count = max((len(items) for items in frame_sets.values()), default=1)
        self.page_index = max(0, min(self.page_index, page_count - 1))
        current = frames[self.page_index] if self.page_index < len(frames) else None

        if profile.style == "dialogue":
            self.screen_preview.pack_forget()
            if not self.dialogue_preview.winfo_manager():
                self.dialogue_preview.pack(fill="x")
            slots = dialogue_speaker_slots(frames)
            selected: dict[str, tuple[int, PreviewFrame] | None] = {"top": None, "bottom": None}
            for index in range(min(self.page_index + 1, len(frames))):
                frame = frames[index]
                selected[slots.get(frame.speaker_code, "top")] = (index, frame)

            overflow = False
            glyph_errors: list[str] = []
            line_count = 1
            current_effects: list[str] = []
            for slot, canvas, label in (
                ("top", self.top_preview_canvas, self.top_speaker_label),
                ("bottom", self.bottom_preview_canvas, self.bottom_speaker_label),
            ):
                chosen = selected[slot]
                frame = chosen[1] if chosen else PreviewFrame("", None, "대화 없음", (), ())
                image, pane_overflow, pane_errors, pane_lines = self.preview_renderer.render(
                    frame.text, profile.content_width, profile.lines, 2, profile.style,
                    frame.inherited_effects,
                )
                photo = ImageTk.PhotoImage(image)
                self.preview_photos[slot] = photo
                canvas.configure(width=image.width, height=image.height)
                canvas.delete("all")
                canvas.create_image(0, 0, anchor="nw", image=photo)
                is_current = current is not None and chosen is not None and chosen[0] == self.page_index
                label.configure(text=("▶ " if is_current else "") + f"{slot == 'top' and '상단' or '하단'}: {frame.speaker_label}")
                if is_current:
                    overflow, glyph_errors, line_count = pane_overflow, pane_errors, pane_lines
                    current_effects = list(self.preview_renderer.last_effects)
            effects = "  →  ".join(current_effects)
        else:
            self.dialogue_preview.pack_forget()
            if not self.screen_preview.winfo_manager():
                self.screen_preview.pack(fill="x")
            display = current or PreviewFrame("", None, "한국어 페이지 없음", (), ())
            image, overflow, glyph_errors, line_count = self.preview_renderer.render(
                display.text, profile.content_width, profile.lines, 2, profile.style,
                display.inherited_effects,
            )
            self.preview_photos["screen"] = ImageTk.PhotoImage(image)
            self.screen_preview_canvas.configure(width=image.width, height=image.height)
            self.screen_preview_canvas.delete("all")
            self.screen_preview_canvas.create_image(0, 0, anchor="nw", image=self.preview_photos["screen"])
            self.screen_kind_label.configure(
                text=f"{profile.label} — 한 줄 {profile.content_width}px / 최대 {profile.lines}줄"
            )
            effects = "  →  ".join(self.preview_renderer.last_effects)

        self._render_source_preview("공식 영문", frame_sets["en"], profile,
                                    self.english_preview_canvas, self.english_preview_label)
        self._render_source_preview("일문", frame_sets["ja"], profile,
                                    self.japanese_preview_canvas, self.japanese_preview_label)
        comparison = layout_comparison(frames, frame_sets["en"], frame_sets["ja"], self.page_index)
        value = lambda item: "—" if item is None else str(item)
        comparison_text = (
            f"전체 페이지  한 {comparison['pages']['한']} / 영 {comparison['pages']['영']} / 일 {comparison['pages']['일']}"
            f"   |   현재 줄  한 {value(comparison['lines']['한'])} / "
            f"영 {value(comparison['lines']['영'])} / 일 {value(comparison['lines']['일'])}"
            f"   |   경계  한 {comparison['transitions']['한']} / "
            f"영 {comparison['transitions']['영']} / 일 {comparison['transitions']['일']}"
        )
        self.layout_comparison_label.configure(
            text=comparison_text + ("   ✓ 위치 일치" if comparison["aligned"] else "   ⚠ 위치 차이"),
            foreground="#087f23" if comparison["aligned"] else "#b36b00",
        )

        self.control_effect_label.configure(
            text=("현재 페이지 제어 순서: " + effects) if effects else "현재 페이지에 제어 코드 없음"
        )
        self.page_label.configure(
            text=f"비교 {self.page_index + 1} / {page_count}  |  한국어 {self.page_index + 1} / {len(frames)}"
            f"  |  {profile.label}  |  {line_count}/{profile.lines}줄"
        )
        issues = token_validation_issues(text)
        issues.extend(protected_token_issues(self.current_entry.baseline_protected, text))
        issues.extend(ValidationIssue(error) for error in glyph_errors[:2])
        if overflow:
            issues.append(ValidationIssue(
                f"표시 영역 초과: 현재 {line_count}줄 / 허용 {profile.lines}줄, "
                f"한 줄 유효 폭 {profile.content_width}px"
            ))

        raw_text = self.translation_text.get("1.0", "end-1c")
        self.translation_text.tag_remove("token_problem", "1.0", "end")
        for issue in issues:
            if issue.start is None or issue.end is None:
                continue
            raw_start = normalized_to_raw_offset(raw_text, issue.start)
            raw_end = normalized_to_raw_offset(raw_text, issue.end)
            if raw_end == raw_start:
                raw_end = min(len(raw_text), raw_start + 1)
            self.translation_text.tag_add("token_problem", f"1.0+{raw_start}c", f"1.0+{raw_end}c")
        self.translation_text.tag_raise("token_problem")

        if issues:
            self.validation_label.configure(text=f"⚠ 문제 {len(issues)}건", foreground="#b00020")
            self.validation_detail_label.configure(
                text="\n".join(f"• {issue.message}" for issue in issues[:6]), foreground="#b00020"
            )
        else:
            self.validation_label.configure(text="제어문·글리프·표시 영역 정상", foreground="#087f23")
            self.validation_detail_label.configure(text="", foreground="#087f23")

    def save_file(self, save_as=False):
        if not self.document:
            return
        self._commit_current()
        invalid = [(entry.entry_id, token_errors(entry.translation)) for entry in self.document.entries]
        invalid = [(entry_id, errors) for entry_id, errors in invalid if errors]
        if invalid:
            sample = "\n".join(f"{entry_id}: {errors[0]}" for entry_id, errors in invalid[:8])
            messagebox.showerror("저장 중단", f"제어문 오류 {len(invalid)}건을 먼저 수정하세요.\n\n{sample}")
            return
        path = self.document.path
        if save_as:
            selected = filedialog.asksaveasfilename(initialdir=str(path.parent), initialfile=path.name,
                                                    defaultextension=path.suffix,
                                                    filetypes=((path.suffix.upper(), "*" + path.suffix),))
            if not selected:
                return
            path = Path(selected)
        try:
            saved = self.document.save(path)
        except Exception as exc:
            messagebox.showerror("저장 실패", str(exc))
            return
        self.dirty = False
        self.file_label.configure(text=str(saved))
        self._refresh_title()
        messagebox.showinfo("저장 완료", f"저장했습니다.\n{saved}\n\n기존 파일은 backups/dialogue_editor에 백업됩니다.")

    def _refresh_title(self):
        name = self.document.path.name if self.document else "파일 없음"
        self.title(("* " if self.dirty else "") + f"Metroid Fusion 대사 조판 편집기 — {name}")

    def _confirm_discard(self):
        return not self.dirty or messagebox.askyesno("저장하지 않은 변경", "저장하지 않은 변경을 버리고 계속할까요?")

    def _on_close(self):
        if self._confirm_discard():
            self.destroy()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?", default=str(DEFAULT_CSV))
    args = parser.parse_args()
    app = DialogueEditor(Path(args.file))
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
