"""Center Korean system-message and location lines by changing line-start 80xx only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import korean_codec as kc
import translation_csv as tc
from navigation_text import TOKEN_RE
from rombuild import PROJECT, load_source


DEFAULT_CSV = (
    PROJECT / "workspace" / "text" / "review"
    / "metroid_fusion_translation_ko_english_controlcodes_fixed.csv"
)
REPORT_PATH = PROJECT / "workspace" / "analysis" / "text_centering.json"
WIDTH_TABLE_OFFSET = 0x578934
WIDTH_TABLE_LAST_CODE = 0x049F
CONTENT_WIDTH_PX = 216
HANGUL_ADVANCE_PX = 12
LINE_START_RE = re.compile(r"^\{ctrl:(80[0-9A-Fa-f]{2})\}")
TARGET_PREFIXES = ("message/ja/", "location/ja/")


class TextCenteringError(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def glyph_width(rom: bytes, code: int) -> int:
    if code > WIDTH_TABLE_LAST_CODE:
        return HANGUL_ADVANCE_PX
    width = rom[WIDTH_TABLE_OFFSET + code]
    return width or HANGUL_ADVANCE_PX


def line_visible_width(
    line: str,
    rom: bytes,
    mapping: dict[str, int | tuple[int, ...]],
) -> int:
    """Measure visible advances without treating any control as text."""
    width = 0
    pos = 0
    while pos < len(line):
        if line[pos] == "{":
            match = TOKEN_RE.match(line, pos)
            if not match:
                raise TextCenteringError(f"invalid token at character {pos}: {line[pos:pos + 20]!r}")
            kind, raw = match.groups()
            if kind == "glyph":
                width += glyph_width(rom, int(raw, 16))
            pos = match.end()
            continue
        value = mapping.get(line[pos])
        if value is None:
            raise TextCenteringError(f"unmapped literal: {line[pos]!r}")
        if isinstance(value, tuple):
            width += sum(glyph_width(rom, code) for code in value)
        elif 0xAC00 <= ord(line[pos]) <= 0xD7A3:
            width += HANGUL_ADVANCE_PX
        else:
            width += glyph_width(rom, value)
        pos += 1
    return width


def center_code(width_px: int, content_width_px: int = CONTENT_WIDTH_PX) -> str:
    if width_px > content_width_px:
        raise TextCenteringError(
            f"line width {width_px}px exceeds centering field {content_width_px}px"
        )
    indent = max(0, min(0x7F, (content_width_px - width_px) // 2))
    return f"{{ctrl:{0x8000 | indent:04X}}}"


def center_line_start(
    line: str,
    rom: bytes,
    mapping: dict[str, int | tuple[int, ...]],
) -> tuple[str, dict | None]:
    width = line_visible_width(line, rom, mapping)
    if width == 0:
        return line, None
    new_code = center_code(width)
    match = LINE_START_RE.match(line)
    old_code = match.group(0) if match else None
    updated = LINE_START_RE.sub(new_code, line, count=1) if match else new_code + line
    if updated == line:
        return line, None
    return updated, {
        "old_code": old_code,
        "new_code": new_code,
        "visible_width_px": width,
        "start_x_px": 12 + (int(new_code[6:10], 16) & 0x7F),
    }


def center_text(
    text: str,
    rom: bytes,
    mapping: dict[str, int | tuple[int, ...]],
) -> tuple[str, list[dict]]:
    lines = text.split("{br}")
    changes = []
    updated_lines = []
    for index, line in enumerate(lines, 1):
        updated, change = center_line_start(line, rom, mapping)
        updated_lines.append(updated)
        if change:
            changes.append({"line": index, **change})
    return "{br}".join(updated_lines), changes


def apply_rows(rows: list[dict[str, str]], rom: bytes, mapping: dict) -> list[dict]:
    changes = []
    for row in rows:
        entry_id = row["entry_id"]
        if not entry_id.startswith(TARGET_PREFIXES):
            continue
        original = row["한국어_번역"]
        updated, line_changes = center_text(original, rom, mapping)
        if updated != original:
            row["한국어_번역"] = updated
            changes.append({"entry_id": entry_id, "lines": line_changes})
    return changes


def write_csv_atomic(path: Path, rows: list[dict[str, str]]) -> Path:
    backup_dir = PROJECT / "backups" / "text_centering"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, backup)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent,
        prefix=path.name + ".", suffix=".tmp",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=tc.HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(handle.name)
    temporary.replace(path)
    return backup


def run(csv_path: Path, apply: bool) -> dict:
    rows = tc.read_csv(csv_path)
    tc.validate_rows(rows, require_editable_match=False)
    rom = load_source()
    mapping = kc.character_map(kc.load_json(kc.CODE_MAP_PATH))
    changes = apply_rows(rows, rom, mapping)
    tc.validate_rows(rows, require_editable_match=False)
    backup = write_csv_atomic(csv_path, rows) if apply and changes else None
    report = {
        "schema_version": 1,
        "report_id": "fusion_ko_system_location_line_centering",
        "mode": "apply" if apply else "dry-run",
        "csv": str(csv_path.relative_to(PROJECT)),
        "csv_sha256": sha256(csv_path) if apply else None,
        "content_width_px": CONTENT_WIDTH_PX,
        "policy": "replace or insert only the first 80xx control at each visible line start",
        "changed_entries": len(changes),
        "changed_lines": sum(len(item["lines"]) for item in changes),
        "changes": changes,
        "backup": str(backup.relative_to(PROJECT)) if backup else None,
    }
    if apply:
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("dry-run", "apply"))
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    report = run(args.csv.resolve(), args.command == "apply")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
