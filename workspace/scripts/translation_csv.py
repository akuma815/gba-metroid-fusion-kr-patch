"""검토용 CSV와 빌드용 번역 JSON을 안전하게 동기화한다."""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from rombuild import PROJECT

SOURCE_DIR = PROJECT / "workspace" / "text" / "source"
TRANSLATION_DIR = PROJECT / "workspace" / "text" / "translation"
REVIEW_DIR = PROJECT / "workspace" / "text" / "review"
DEFAULT_CSV = REVIEW_DIR / "metroid_fusion_translation_review.csv"
SPEAKER_CONTEXT = PROJECT / "workspace" / "config" / "speaker_context.json"

TRANSLATION_FILES = {
    "navigation": TRANSLATION_DIR / "navigation_ko.json",
    "additional": TRANSLATION_DIR / "additional_ko.json",
    "file_select": TRANSLATION_DIR / "file_select_ko.json",
}
SOURCE_FILES = {
    "navigation": SOURCE_DIR / "navigation_text.json",
    "additional": SOURCE_DIR / "additional_text.json",
    "file_select": SOURCE_DIR / "file_select_text.json",
}

HEADERS = [
    "entry_id", "구분", "번호", "화자", "화자_근거", "일본어_원문_코드",
    "공식_영어_원문_코드", "공식_영어_참고문", "번역_기준",
    "한국어_번역", "상태", "메모", "플래그",
    "ROM_오프셋", "원문_바이트수",
]
LEGACY_HEADERS = [
    "entry_id", "구분", "번호", "화자", "화자_근거", "일본어_원문_코드",
    "공식_영어_참고문", "한국어_번역", "상태", "메모", "플래그",
    "ROM_오프셋", "원문_바이트수",
]
EDITABLE = {"한국어_번역", "상태", "메모"}
ALLOWED_STATUS = {
    "untranslated", "in_progress", "needs_review", "needs_human_review", "complete"
}
SPEAKER_TOKEN = re.compile(r"\{ctrl:(E20[0-2])\}")
CONTROL_TOKEN = re.compile(r"\{ctrl:([0-9A-F]{4})\}")
GLYPH_TOKEN = re.compile(r"\{glyph:([0-9A-F]{4})\}")
ANY_TOKEN = re.compile(r"\{(ctrl|glyph):([0-9A-F]{4})\}|\{(br|end)\}")
PRESENTATION_CONTROLS = {f"810{index:X}" for index in range(7)}
# Page boundaries are translator-owned layout. Speaker/event/end controls stay
# semantic and must still match the aligned official English entry.
LAYOUT_CONTROLS: set[str] = {"FD00"}
READABLE_GLYPHS = {"0400", "041F", "0311", "0312"}  # space, question mark, quote pair


class TranslationCsvError(Exception):
    pass


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def language_entries(container: dict, language_id: str) -> list[dict]:
    return next(item["entries"] for item in container["languages"] if item["language_id"] == language_id)


def translation_map(data: dict) -> dict[str, dict]:
    return {entry["entry_id"]: entry for entry in data["entries"]}


def readable_reference(tokens: str, speaker_names: dict[str, str]) -> str:
    text = tokens.replace("{br}", " ↵ ").replace("{end}", "")
    text = text.replace("{ctrl:FD00}", " ⟦PAGE⟧ ")
    for code, speaker in speaker_names.items():
        text = text.replace(f"{{ctrl:{code}}}", f" 【{speaker}】 ")
    # 8100~8106 are presentation spans in the aligned official English text.
    text = re.sub(r"\{ctrl:810[0-6]\}", "", text)
    text = CONTROL_TOKEN.sub(lambda m: f"⟦CTRL:{m.group(1)}⟧", text)
    known_glyphs = {"0400": " ", "041F": "?", "0311": "“"}
    text = GLYPH_TOKEN.sub(lambda m: known_glyphs.get(m.group(1), f"⟦G:{m.group(1)}⟧"), text)
    return " ".join(text.split())


def navigation_speaker(index: int, english_tokens: str, context: dict) -> tuple[str, str]:
    nav = context["navigation"]
    start, end = nav["mission_log_index_range"]
    if start <= index <= end:
        item = nav["mission_log"]
        return item["speaker"], item["basis"]
    switches = nav["speaker_switch_controls"]
    sequence = []
    for code in SPEAKER_TOKEN.findall(english_tokens):
        speaker = switches[code]
        if not sequence or sequence[-1] != speaker:
            sequence.append(speaker)
    if sequence:
        return " → ".join(sequence), nav["switch_basis"]
    item = nav["conversation_default"]
    return item["speaker"], item["basis"]


def make_row(
    entry: dict,
    english: dict | None,
    translated: dict,
    group: str,
    group_label: str,
    speaker: str,
    speaker_basis: str,
    speaker_names: dict[str, str],
) -> dict[str, str]:
    if english is not None:
        translation_basis = "ROM 내장 공식 영어(동일 인덱스)"
    elif entry["entry_id"] in {
        "file_select/ja/025", "file_select/ja/026", "file_select/ja/027"
    }:
        translation_basis = "일본어 글리프 + 닌텐도 공식 일본어 설명서"
    else:
        translation_basis = "미확정: 일본어 글리프 문자표 해독 필요"
    return {
        "entry_id": entry["entry_id"],
        "구분": group_label,
        "번호": str(entry["index"]),
        "화자": speaker,
        "화자_근거": speaker_basis,
        "일본어_원문_코드": entry["source_tokens"],
        "공식_영어_원문_코드": (
            english["source_tokens"] if english is not None else "※ 공식 영어 대응 항목 없음"
        ),
        "공식_영어_참고문": (
            readable_reference(english["source_tokens"], speaker_names)
            if english is not None else "※ 공식 영어 대응 항목 없음"
        ),
        "번역_기준": translation_basis,
        "한국어_번역": translated["ko"],
        "상태": translated["status"],
        "메모": translated["notes"] or "",
        "플래그": "|".join(translated["flags"]),
        "ROM_오프셋": entry["file_offset"],
        "원문_바이트수": str(entry["byte_length"]),
    }


def build_rows() -> list[dict[str, str]]:
    context = load_json(SPEAKER_CONTEXT)
    if context.get("schema_version") != 1:
        raise TranslationCsvError("unsupported speaker context schema")
    switch_names = context["navigation"]["speaker_switch_controls"]
    translations = {key: load_json(path) for key, path in TRANSLATION_FILES.items()}
    maps = {key: translation_map(value) for key, value in translations.items()}
    rows: list[dict[str, str]] = []

    nav = load_json(SOURCE_FILES["navigation"])
    nav_ja = language_entries(nav, "ja")
    nav_en = language_entries(nav, "en")
    if len(nav_ja) != len(nav_en):
        raise TranslationCsvError("navigation Japanese/English alignment mismatch")
    for ja, en in zip(nav_ja, nav_en):
        speaker, basis = navigation_speaker(ja["index"], en["source_tokens"], context)
        rows.append(make_row(
            ja, en, maps["navigation"][ja["entry_id"]], "navigation", "내비게이션",
            speaker, basis, switch_names,
        ))

    additional = load_json(SOURCE_FILES["additional"])
    labels = {"message": "시스템 메시지", "location": "지역명", "monologue": "독백"}
    for population in additional["populations"]:
        group = population["population_id"]
        ja_entries = language_entries(population, "ja")
        en_entries = language_entries(population, "en")
        fixed = context["fixed_groups"][group]
        for ja, en in zip(ja_entries, en_entries):
            rows.append(make_row(
                ja, en, maps["additional"][ja["entry_id"]], group, labels[group],
                fixed["speaker"], fixed["basis"], switch_names,
            ))

    file_select = load_json(SOURCE_FILES["file_select"])
    fs_ja = language_entries(file_select, "ja")
    fs_en = {entry["index"]: entry for entry in language_entries(file_select, "en")}
    fixed = context["fixed_groups"]["file_select"]
    for ja in fs_ja:
        en = fs_en.get(ja["index"])
        rows.append(make_row(
            ja, en, maps["file_select"][ja["entry_id"]], "file_select", "파일 선택",
            fixed["speaker"], fixed["basis"], switch_names,
        ))
    shared_fixed = context["fixed_groups"]["file_select_shared"]
    for entry in file_select["shared"]["entries"]:
        rows.append(make_row(
            entry, entry, maps["file_select"][entry["entry_id"]],
            "file_select_shared", "공용 UI", shared_fixed["speaker"],
            shared_fixed["basis"], switch_names,
        ))

    ids = [row["entry_id"] for row in rows]
    if len(ids) != 349 or len(ids) != len(set(ids)):
        raise TranslationCsvError(f"review population mismatch: rows={len(ids)} unique={len(set(ids))}")
    return rows


def write_csv(path: Path, rows: list[dict[str, str]], overwrite: bool = False):
    if path.exists() and not overwrite:
        raise TranslationCsvError(f"refusing to overwrite review CSV without --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames not in (HEADERS, LEGACY_HEADERS):
            raise TranslationCsvError(f"CSV columns mismatch: {reader.fieldnames}")
        rows = list(reader)
        if reader.fieldnames == LEGACY_HEADERS:
            expected = {row["entry_id"]: row for row in build_rows()}
            migrated = []
            for row in rows:
                if row["entry_id"] not in expected:
                    raise TranslationCsvError(f"unknown legacy CSV entry_id: {row['entry_id']}")
                expanded = dict(expected[row["entry_id"]])
                for field in EDITABLE:
                    expanded[field] = row[field]
                migrated.append(expanded)
            rows = migrated
    ids = [row["entry_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise TranslationCsvError("duplicate entry_id in CSV")
    return rows


def semantic_control_tokens(text: str) -> Counter:
    """조판 이동·표시 리터럴을 제외하고 의미를 바꾸는 토큰만 집계한다."""
    result = []
    for token_type, code, simple in ANY_TOKEN.findall(text):
        if simple == "br":
            continue
        if token_type == "ctrl" and (
            code in PRESENTATION_CONTROLS | LAYOUT_CONTROLS or code.startswith("80")
        ):
            continue
        if token_type == "glyph" and code in READABLE_GLYPHS:
            continue
        result.append((token_type or "simple", code or simple))
    return Counter(result)


def validate_rows(actual: list[dict[str, str]], require_editable_match: bool) -> dict[str, int]:
    expected = build_rows()
    expected_by_id = {row["entry_id"]: row for row in expected}
    if set(row["entry_id"] for row in actual) != set(expected_by_id):
        raise TranslationCsvError("CSV entry population differs from current source catalogs")
    changed = 0
    for row in actual:
        expected_row = expected_by_id[row["entry_id"]]
        for field in HEADERS:
            if field not in EDITABLE and row[field] != expected_row[field]:
                raise TranslationCsvError(f"protected CSV field changed: {row['entry_id']} / {field}")
        if row["상태"] not in ALLOWED_STATUS:
            raise TranslationCsvError(f"invalid status: {row['entry_id']} / {row['상태']}")
        if (
            row["한국어_번역"]
            and not row["공식_영어_원문_코드"].startswith("※")
            and semantic_control_tokens(row["공식_영어_원문_코드"])
            != semantic_control_tokens(row["한국어_번역"])
        ):
            raise TranslationCsvError(
                f"semantic control tokens differ from official English: {row['entry_id']}"
            )
        if any(row[field] != expected_row[field] for field in EDITABLE):
            changed += 1
            if require_editable_match:
                raise TranslationCsvError(f"CSV has unimported editable changes: {row['entry_id']}")
    return {"rows": len(actual), "editable_changes": changed}


def import_csv(path: Path) -> dict[str, int]:
    rows = read_csv(path)
    result = validate_rows(rows, require_editable_match=False)
    row_map = {row["entry_id"]: row for row in rows}
    documents = {key: load_json(file) for key, file in TRANSLATION_FILES.items()}
    changed_files = []
    for key, document in documents.items():
        changed = False
        for entry in document["entries"]:
            row = row_map[entry["entry_id"]]
            values = (row["한국어_번역"], row["상태"], row["메모"] or None)
            if values != (entry["ko"], entry["status"], entry["notes"]):
                entry["ko"], entry["status"], entry["notes"] = values
                changed = True
        if changed:
            changed_files.append(key)
    if not changed_files:
        return {**result, "updated_files": 0}

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = PROJECT / "backups" / "translation_csv" / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    for key in changed_files:
        shutil.copy2(TRANSLATION_FILES[key], backup_dir / TRANSLATION_FILES[key].name)

    temp_paths: dict[str, Path] = {}
    try:
        for key in changed_files:
            target = TRANSLATION_FILES[key]
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="", delete=False, dir=target.parent,
                prefix=target.name + ".", suffix=".tmp",
            ) as handle:
                json.dump(documents[key], handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                temp_paths[key] = Path(handle.name)
        for key in changed_files:
            temp_paths[key].replace(TRANSLATION_FILES[key])
    finally:
        for path_tmp in temp_paths.values():
            if path_tmp.exists():
                path_tmp.unlink()
    return {**result, "updated_files": len(changed_files)}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    export.add_argument("--force", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    verify.add_argument(
        "--require-synced", action="store_true",
        help="editable columns must also match the current build JSON",
    )
    import_parser = sub.add_parser("import")
    import_parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    refresh = sub.add_parser("refresh-protected")
    refresh.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()

    if args.command == "export":
        rows = build_rows()
        write_csv(args.csv, rows, overwrite=args.force)
        print(json.dumps({"status": "pass", "rows": len(rows), "csv": str(args.csv)}, ensure_ascii=False))
    elif args.command == "verify":
        result = validate_rows(read_csv(args.csv), require_editable_match=args.require_synced)
        print(json.dumps({"status": "pass", **result, "csv": str(args.csv)}, ensure_ascii=False))
    elif args.command == "refresh-protected":
        rows = read_csv(args.csv)
        result = validate_rows(rows, require_editable_match=False)
        write_csv(args.csv, rows, overwrite=True)
        print(json.dumps({"status": "pass", **result, "csv": str(args.csv)}, ensure_ascii=False))
    else:
        result = import_csv(args.csv)
        print(json.dumps({"status": "pass", **result, "csv": str(args.csv)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (TranslationCsvError, KeyError, OSError, csv.Error, json.JSONDecodeError) as exc:
        raise SystemExit(f"translation CSV error: {exc}")
