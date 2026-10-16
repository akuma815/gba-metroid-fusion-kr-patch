"""Build the Metroid Fusion Korean distribution target from the clean JP ROM."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

import additional_text as at
import file_select_text as fst
import game_over_graphics as gog
import korean_codec as kc
import navigation_text as nt
import pause_ui_graphics as uig
import title_screen_graphics as tsg
import text_centering as centering
import translation_corpus as corpus
import translation_csv as tc
from font_slot_audit import DEFAULT_WIDTH_EXPECTED, DEFAULT_WIDTH_INSTRUCTION_OFFSET
from rombuild import PROJECT, ROM_SIZE, RomBuilder, load_source

OUTPUT_ROM = PROJECT / "build" / "metroid_fusion_ko_v51_status_items_only_qa.gba"
OUTPUT_REPORT = PROJECT / "build" / "metroid_fusion_ko_v51_status_items_only_qa.json"
STABLE_OUTPUT_ROM = PROJECT / "build" / "metroid_fusion_ko_pre_status_items_snapshot.gba"
STABLE_OUTPUT_REPORT = PROJECT / "build" / "metroid_fusion_ko_pre_status_items_snapshot.json"
FINAL_OUTPUT_ROM = PROJECT / "build" / "metroid_fusion_ko_v1_0_final.gba"
FINAL_OUTPUT_REPORT = PROJECT / "build" / "metroid_fusion_ko_v1_0_final.json"
GBA_ROM_BASE = 0x08000000
TARGET_LANGUAGES = ("ja", "ja_hiragana")

# file_select/ja/011-024 is one physical source string whose catalog entries
# point into suffixes. The review CSV intentionally expands those suffixes for
# readability, so the runtime representation must be rebuilt as compact
# segments instead of encoding each expanded review row independently.
FILE_SELECT_ALIAS_SEGMENTS = (
    ("file_select/ja/011", "START 버튼 입력"),
    ("file_select/ja/012", "언어 선택"),
    ("file_select/ja/013", "다시 도전{glyph:041F}"),
    ("file_select/ja/014", "예 (게임으로 복귀)"),
    ("file_select/ja/015", "아니요 (타이틀로 이동)"),
    ("file_select/ja/016", "클리어 타임"),
    ("file_select/ja/017", "아이템 회수율 {glyph:041F}{glyph:041F}%"),
    ("file_select/ja/018", "다음 임무에서 다시 만나자."),
    ("file_select/ja/019", "임무 완료."),
    ("file_select/ja/020", "모든"),
    ("file_select/ja/021", "저장 데이터를 삭제하시겠습니까{glyph:041F}"),
    ("file_select/ja/022", "정말 모든"),
    ("file_select/ja/023", "저장 데이터를 삭제하시겠습니까{glyph:041F}"),
    ("file_select/ja/024", "계속{br}처음부터{end}"),
)

# These are runtime layout corrections, not translation-source edits. The CSV
# retains review-friendly source glyphs and glosses, while the game receives
# the previously verified compact choice layouts.
RUNTIME_LAYOUT_OVERRIDES = {
    "message/ja/043": (
        "{ctrl:8017}목표 확인{glyph:041F}{br}"
        "{ctrl:8057}{ctrl:8340}예 {ctrl:83A0}아니요{end}"
    ),
    "message/ja/044": (
        "{ctrl:800F}임무 목표 확인{glyph:041F}{br}"
        "{ctrl:8057}{ctrl:8340}예 {ctrl:83A0}아니요{end}"
    ),
    "file_select/ja/025": (
        "메시지 유형{br}성인용 (한자 있음){br}어린이용 (히라가나){end}"
    ),
    "file_select/ja/026": "게임 레벨{br}EASY{br}NORMAL{end}",
    "file_select/ja/027": "게임 레벨{br}EASY{br}NORMAL{br}HARD{end}",
    "file_select/ja/028": (
        "기존 저장 데이터는 삭제됩니다.{br}"
        "계속하시겠습니까{br}예 아니요{end}"
    ),
}

class KoreanBuildError(Exception):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def language_entries(container: dict, language_id: str) -> list[dict]:
    return next(item["entries"] for item in container["languages"] if item["language_id"] == language_id)


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if start < 0 or end <= start or start % 2 or end % 2:
            raise KoreanBuildError(f"invalid reclaim interval 0x{start:X}-0x{end:X}")
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def reclaim_ranges(nav: dict, additional: dict, file_select: dict) -> list[tuple[int, int]]:
    entries: list[dict] = []
    for language_id in TARGET_LANGUAGES:
        entries.extend(language_entries(nav, language_id))
        entries.extend(language_entries(file_select, language_id))
        for population in additional["populations"]:
            entries.extend(language_entries(population, language_id))
    return merge_intervals([
        (int(entry["file_offset"], 0), int(entry["file_offset"], 0) + entry["byte_length"])
        for entry in entries
    ])


def allocate_strings(
    rows: list[dict[str, str]],
    mapping: dict[str, int],
    ranges: list[tuple[int, int]],
) -> tuple[dict[str, dict], list[dict]]:
    allocations: dict[str, dict] = {}
    used_ranges: list[dict] = []
    range_index = 0
    cursor = ranges[0][0]
    current_start = cursor
    alias_ids = {entry_id for entry_id, _ in FILE_SELECT_ALIAS_SEGMENTS}
    alias_offsets: dict[str, int] = {}
    alias_raw = bytearray()
    for entry_id, text in FILE_SELECT_ALIAS_SEGMENTS:
        alias_offsets[entry_id] = len(alias_raw)
        encoded = kc.serialize(kc.encode_korean(
            text if text.endswith("{end}") else text + "{end}", mapping
        ))
        alias_raw.extend(encoded if text.endswith("{end}") else encoded[:-2])
    alias_raw = bytes(alias_raw)
    source_rom = load_source()

    for row in rows:
        entry_id = row["entry_id"]
        if entry_id in alias_ids and entry_id != FILE_SELECT_ALIAS_SEGMENTS[0][0]:
            continue
        text = RUNTIME_LAYOUT_OVERRIDES.get(entry_id, row["한국어_번역"])
        if entry_id.startswith(centering.TARGET_PREFIXES):
            text = centering.center_text(text, source_rom, mapping)[0]
        raw = alias_raw if entry_id == FILE_SELECT_ALIAS_SEGMENTS[0][0] else kc.serialize(kc.encode_korean(text, mapping))
        while cursor + len(raw) > ranges[range_index][1]:
            if cursor > current_start:
                used_ranges.append({
                    "start": f"0x{current_start:06X}",
                    "end_exclusive": f"0x{cursor:06X}",
                    "bytes": cursor - current_start,
                })
            range_index += 1
            if range_index >= len(ranges):
                raise KoreanBuildError(f"reclaimed Japanese text space exhausted at {row['entry_id']}")
            cursor = ranges[range_index][0]
            current_start = cursor
        allocations[entry_id] = {
            "entry_id": entry_id,
            "offset": cursor,
            "gba_address": GBA_ROM_BASE + cursor,
            "raw": raw,
            "write_raw": raw,
        }
        if entry_id == FILE_SELECT_ALIAS_SEGMENTS[0][0]:
            for alias_id, _ in FILE_SELECT_ALIAS_SEGMENTS[1:]:
                delta = alias_offsets[alias_id]
                allocations[alias_id] = {
                    "entry_id": alias_id,
                    "offset": cursor + delta,
                    "gba_address": GBA_ROM_BASE + cursor + delta,
                    "raw": raw[delta:],
                    "write_raw": b"",
                    "alias_parent_entry_id": entry_id,
                    "alias_delta_bytes": delta,
                }
        cursor += len(raw)
    if cursor > current_start:
        used_ranges.append({
            "start": f"0x{current_start:06X}",
            "end_exclusive": f"0x{cursor:06X}",
            "bytes": cursor - current_start,
        })
    return allocations, used_ranges


def pointer_bindings(nav: dict, additional: dict, file_select: dict) -> list[dict]:
    result = []
    for language_id in TARGET_LANGUAGES:
        for entry in language_entries(nav, language_id):
            result.append({
                "target_entry_id": f"navigation/ja/{entry['index']:03d}",
                "source_entry": entry,
                "language_id": language_id,
            })
        for population in additional["populations"]:
            population_id = population["population_id"]
            for entry in language_entries(population, language_id):
                result.append({
                    "target_entry_id": f"{population_id}/ja/{entry['index']:03d}",
                    "source_entry": entry,
                    "language_id": language_id,
                })
        for entry in language_entries(file_select, language_id):
            result.append({
                "target_entry_id": f"file_select/ja/{entry['index']:03d}",
                "source_entry": entry,
                "language_id": language_id,
            })
    for entry in file_select["shared"]["entries"]:
        result.append({
            "target_entry_id": entry["entry_id"],
            "source_entry": entry,
            "language_id": "shared",
        })
    if len(result) != 696:
        raise KoreanBuildError(f"pointer binding count {len(result)} != 696")
    return result


def verify_built_image(
    image: bytes,
    allocations: dict[str, dict],
    bindings: list[dict],
    font_report: dict,
    code_map: dict,
    ui_plan: list[dict],
    ui_runtime_hook: dict | None,
    title_plan: dict,
    game_over_plan: dict,
) -> dict:
    if len(image) != ROM_SIZE:
        raise KoreanBuildError(f"built ROM size {len(image)} != {ROM_SIZE}")
    checked_pointers = 0
    for binding in bindings:
        source = binding["source_entry"]
        target = allocations[binding["target_entry_id"]]
        storage = int(source["pointer_storage_offset"], 0)
        actual_pointer = struct.unpack_from("<I", image, storage)[0]
        if actual_pointer != target["gba_address"]:
            raise KoreanBuildError(f"rebuilt pointer mismatch: {source['entry_id']}")
        raw = target["raw"]
        if image[target["offset"]:target["offset"] + len(raw)] != raw:
            raise KoreanBuildError(f"rebuilt text mismatch: {target['entry_id']}")
        if not raw.endswith(b"\x00\xFF"):
            raise KoreanBuildError(f"unterminated rebuilt text: {target['entry_id']}")
        checked_pointers += 1
    for item in font_report["font_payload"]["writes"]:
        offset = int(item["offset"], 0)
        raw = bytes.fromhex(item["new_hex"])
        if image[offset:offset + 32] != raw:
            raise KoreanBuildError(f"rebuilt font tile mismatch at 0x{offset:X}")
    for raw_code in code_map["policy"]["width_table_codes_to_set_12"]:
        code = int(raw_code, 0)
        if image[0x578934 + code] != 12:
            raise KoreanBuildError(f"rebuilt width mismatch for 0x{code:04X}")
    patch = code_map["policy"]["default_width_patch"]
    offset = int(patch["offset"], 0)
    if image[offset:offset + 2] != bytes.fromhex(patch["new_hex"]):
        raise KoreanBuildError("rebuilt default width instruction mismatch")
    # Both Japanese modes intentionally share every Korean target.
    grouped: dict[str, list[int]] = {}
    for binding in bindings:
        if binding["language_id"] == "shared":
            continue
        storage = int(binding["source_entry"]["pointer_storage_offset"], 0)
        grouped.setdefault(binding["target_entry_id"], []).append(struct.unpack_from("<I", image, storage)[0])
    if any(len(values) != 2 or values[0] != values[1] for values in grouped.values()):
        raise KoreanBuildError("Japanese/Japanese-Hiragana pointer sharing mismatch")
    uig.verify_image(image, ui_plan)
    if ui_runtime_hook is not None:
        uig.verify_runtime_hook(image, ui_runtime_hook)
    tsg.verify_image(image, title_plan)
    gog.verify_image(image, game_over_plan)
    return {
        "checked_pointers": checked_pointers,
        "checked_unique_strings": len(allocations),
        "checked_font_tiles": len(font_report["font_payload"]["writes"]),
        "japanese_mode_shared_targets": len(grouped),
        "pause_ui_graphics_assets": len(ui_plan),
        "title_graphics_assets": len(title_plan["assets"]),
    }


def build(
    include_status_items: bool = True,
    output_rom: Path = OUTPUT_ROM,
    build_id: str = "fusion_ko_v51_status_items_only_qa",
) -> tuple[RomBuilder, dict]:
    rom = load_source()
    nav = tc.load_json(tc.SOURCE_FILES["navigation"])
    additional = tc.load_json(tc.SOURCE_FILES["additional"])
    file_select = tc.load_json(tc.SOURCE_FILES["file_select"])
    nt.verify_catalog(nav, rom, nt.load_format())
    at.verify_catalog(additional, rom, at.load_format())
    fst.verify_catalog(file_select, rom, fst.load_format())

    csv_rows = tc.read_csv(corpus.DEFAULT_CSV)
    tc.validate_rows(csv_rows, require_editable_match=True)
    rows = tc.build_rows()
    if [row["entry_id"] for row in csv_rows] != [row["entry_id"] for row in rows]:
        raise KoreanBuildError("complete CSV row order differs from imported JSON")

    code_map = kc.load_json(kc.CODE_MAP_PATH)
    profile = kc.load_json(kc.FONT_PROFILE_PATH)
    mapping = kc.character_map(code_map)
    font_report = kc.build_report(rom, code_map, profile)
    corpus_report = tc.load_json(corpus.OUTPUT_PATH)
    if font_report["encoding"]["serialized_bytes"] != corpus_report["corpus"]["target_logical_bytes"]:
        raise KoreanBuildError("encoded corpus does not match translation corpus report")

    ranges = reclaim_ranges(nav, additional, file_select)
    allocations, used_ranges = allocate_strings(rows, mapping, ranges)
    bindings = pointer_bindings(nav, additional, file_select)
    occupied = [
        (item["offset"], item["offset"] + len(item["write_raw"]))
        for item in allocations.values() if item["write_raw"]
    ]
    # v20's status-label experiment corrupted shared low tile IDs. The current
    # status build allocates dedicated zero tiles and redirects only status
    # tilemap 05, while the map chrome and save-summary OBJ assets keep their
    # independently verified paths.
    ui_asset_ids = {
        "pause_map_chrome_tileset_ko",
        "file_select_obj_tileset_ko",
    }
    if include_status_items:
        ui_asset_ids.update({"pause_status_tileset_ko", "pause_tilemap_05"})
    ui_plan = uig.build_plan(rom, ranges, occupied, ui_asset_ids)
    title_occupied = occupied + [
        (asset["target_offset"], asset["target_offset"] + len(asset["compressed"]))
        for asset in ui_plan
    ]
    title_plan = tsg.build_plan(rom, ranges, title_occupied)
    game_over_plan = gog.build_plan(rom)
    # v13-v17's common text-renderer hook also ran on file-select/choice
    # screens and copied Pause OBJ tiles over their graphics. Keep the static
    # assets, but omit that failed runtime hook until it is gated by an actual
    # Pause state rather than inferred OAM contents.
    ui_runtime_hook = None
    builder = RomBuilder()

    for row in rows:
        allocation = allocations[row["entry_id"]]
        offset = allocation["offset"]
        raw = allocation["write_raw"]
        if not raw:
            continue
        builder.write(offset, raw, builder.source[offset:offset + len(raw)], f"text:{row['entry_id']}")

    for binding in bindings:
        source = binding["source_entry"]
        target = allocations[binding["target_entry_id"]]
        storage = int(source["pointer_storage_offset"], 0)
        expected = bytes.fromhex(source["pointer_raw_hex"])
        if builder.source[storage:storage + 4] != expected:
            raise KoreanBuildError(f"source pointer baseline mismatch: {source['entry_id']}")
        builder.write(
            storage,
            struct.pack("<I", target["gba_address"]),
            expected,
            f"pointer:{source['entry_id']}->{target['entry_id']}",
        )

    for item in font_report["font_payload"]["writes"]:
        offset = int(item["offset"], 0)
        new = bytes.fromhex(item["new_hex"])
        expected = builder.source[offset:offset + 32]
        if sha256_bytes(expected) != item["expected_sha256"]:
            raise KoreanBuildError(f"font Expected Write hash mismatch at 0x{offset:X}")
        builder.write(offset, new, expected, f"font:{item['character']}:{item['part']}")

    for raw_code in code_map["policy"]["width_table_codes_to_set_12"]:
        code = int(raw_code, 0)
        offset = 0x578934 + code
        builder.write(offset, b"\x0C", builder.source[offset:offset + 1], f"width:0x{code:04X}=12")
    patch = code_map["policy"]["default_width_patch"]
    patch_offset = int(patch["offset"], 0)
    expected_patch = bytes.fromhex(patch["expected_hex"])
    new_patch = bytes.fromhex(patch["new_hex"])
    if patch_offset != DEFAULT_WIDTH_INSTRUCTION_OFFSET or expected_patch != DEFAULT_WIDTH_EXPECTED:
        raise KoreanBuildError("default width patch specification mismatch")
    builder.write(patch_offset, new_patch, expected_patch, "default_width:10->12")

    for asset in ui_plan:
        offset = asset["target_offset"]
        compressed = asset["compressed"]
        builder.write(
            offset,
            compressed,
            builder.source[offset:offset + len(compressed)],
            f"pause_ui:{asset['asset_id']}:payload",
        )
        pointer_offset = asset["pointer_offset"]
        expected_pointer = struct.pack("<I", asset["expected_pointer"])
        builder.write(
            pointer_offset,
            struct.pack("<I", asset["target_pointer"]),
            expected_pointer,
            f"pause_ui:{asset['asset_id']}:pointer",
        )
    ui_oam_patches = uig.oam_table_patches(builder.source, include_pause=False)
    for item in ui_oam_patches:
        builder.write(
            item["offset"], item["new"], item["expected"],
            f"pause_ui:oam_table:0x{item['offset']:06X}",
        )
    for asset in title_plan["assets"]:
        offset = asset["target_offset"]
        compressed = asset["compressed"]
        builder.write(
            offset, compressed, builder.source[offset:offset + len(compressed)],
            f"title:{asset['asset_id']}:payload",
        )
        for pointer_offset in asset["pointer_offsets"]:
            builder.write(
                pointer_offset,
                struct.pack("<I", asset["target_pointer"]),
                struct.pack("<I", asset["source_pointer"]),
                f"title:{asset['asset_id']}:pointer:0x{pointer_offset:06X}",
            )
    builder.write(
        game_over_plan["base_offset"], game_over_plan["base_slot"], game_over_plan["source_base_slot"],
        "game_over:korean_prompt_and_choices:adult_child_base",
    )
    builder.write(
        game_over_plan["overlay_offset"], game_over_plan["overlay_slot"],
        game_over_plan["source_overlay_slot"], "game_over:korean_prompt_and_choices:language_overlay",
    )
    # The title palette remains live on the file-select screen and supplies the
    # deep-blue menu fill.  Re-quantize the Korean logo to the original banks;
    # never write this shared palette region.
    if title_plan["palette"] != title_plan["source_palette"]:
        raise KoreanBuildError("title build attempted to replace the shared file-select palette")
    builder.verify()

    verification = verify_built_image(
        bytes(builder.buf), allocations, bindings, font_report, code_map,
        ui_plan, ui_runtime_hook, title_plan, game_over_plan,
    )
    declared_bytes = len(builder.writers)
    changed_bytes = sum(builder.source[pos] != builder.buf[pos] for pos in builder.writers)
    report = {
        "schema_version": 1,
        "build_id": build_id,
        "status": "static_build_pass_runtime_qa_pending",
        "source": {
            "rom": "original/Metroid Fusion (Japan).gba",
            "rom_sha256": sha256_bytes(builder.source),
            "complete_csv": str(corpus.DEFAULT_CSV.relative_to(PROJECT)).replace("\\", "/"),
            "complete_csv_sha256": sha256_path(corpus.DEFAULT_CSV),
            "code_map_sha256": sha256_path(kc.CODE_MAP_PATH),
            "font_payload_sha256": sha256_path(kc.OUTPUT_PATH),
            "text_centering_report": str(centering.REPORT_PATH.relative_to(PROJECT)).replace("\\", "/"),
            "text_centering_report_sha256": sha256_path(centering.REPORT_PATH),
            "small_ui_font": os.path.relpath(uig.SMALL_FONT, PROJECT).replace("\\", "/"),
            "small_ui_font_sha256": uig.SMALL_FONT_SHA256,
            "title_reference": str((tsg.APPROVED_REFERENCE if tsg.APPROVED_REFERENCE.is_file() else tsg.REFERENCE).relative_to(PROJECT)).replace("\\", "/"),
            "title_reference_sha256": tsg.APPROVED_REFERENCE_SHA256 if tsg.APPROVED_REFERENCE.is_file() else tsg.REFERENCE_SHA256,
            "game_over_font": game_over_plan["font"],
        },
        "output": {
            "rom": str(output_rom.relative_to(PROJECT)).replace("\\", "/"),
            "rom_size": len(builder.buf),
            "rom_sha256": sha256_bytes(builder.buf),
        },
        "allocation": {
            "policy": "reclaim confirmed ja and ja_hiragana string bytes; leave all unused bytes unchanged",
            "available_ranges": [
                {"start": f"0x{start:06X}", "end_exclusive": f"0x{end:06X}", "bytes": end - start}
                for start, end in ranges
            ],
            "available_bytes": sum(end - start for start, end in ranges),
            "used_bytes": sum(len(item["write_raw"]) for item in allocations.values()),
            "remaining_bytes": (
                sum(end - start for start, end in ranges)
                - sum(len(item["write_raw"]) for item in allocations.values())
                - sum(len(item["compressed"]) for item in ui_plan)
                - sum(len(item["compressed"]) for item in title_plan["assets"])
            ),
            "pause_ui_graphics_bytes": sum(len(item["compressed"]) for item in ui_plan),
            "title_graphics_bytes": sum(len(item["compressed"]) for item in title_plan["assets"]),
            "game_over_graphics_slot_bytes": (
                game_over_plan["base_slot_bytes"] + game_over_plan["overlay_slot_bytes"]
            ),
            "pause_ui_oam_table_patches": len(ui_oam_patches),
            "pause_ui_runtime_hook_bytes": 0,
            "used_ranges": used_ranges,
            "file_select_suffix_layout": {
                "parent_entry_id": FILE_SELECT_ALIAS_SEGMENTS[0][0],
                "entry_count": len(FILE_SELECT_ALIAS_SEGMENTS),
                "physical_bytes": len(allocations[FILE_SELECT_ALIAS_SEGMENTS[0][0]]["write_raw"]),
                "policy": "derive compact runtime block from expanded review rows; preserve CSV unchanged",
            },
        },
        "writes": {
            "expected_write_operations": len(builder.changes),
            "declared_byte_positions": declared_bytes,
            "changed_byte_positions": changed_bytes,
            "text_strings": len(allocations),
            "pointer_fields": len(bindings),
            "font_tiles": len(font_report["font_payload"]["writes"]),
            "width_table_entries": len(code_map["policy"]["width_table_codes_to_set_12"]),
            "default_width_instruction": 1,
            "runtime_layout_overrides": sorted(RUNTIME_LAYOUT_OVERRIDES),
            "line_centering": {
                "populations": ["message/ja", "location/ja"],
                "content_width_px": centering.CONTENT_WIDTH_PX,
                "policy": "change only the first 80xx control at each visible line start",
            },
            "pause_ui_graphics_assets": uig.report_items(ui_plan),
            "title_graphics": tsg.report(title_plan),
            "game_over_graphics": {
                "base_offset": f"0x{game_over_plan['base_offset']:06X}",
                "base_slot_bytes": game_over_plan["base_slot_bytes"],
                "base_compressed_bytes": game_over_plan["base_compressed_bytes"],
                "overlay_offset": f"0x{game_over_plan['overlay_offset']:06X}",
                "overlay_slot_bytes": game_over_plan["overlay_slot_bytes"],
                "overlay_compressed_bytes": game_over_plan["overlay_compressed_bytes"],
                "decoded_sha256": game_over_plan["decoded_sha256"],
                "lines": game_over_plan["lines"],
                "adult_child_modes": "shared_baked_graphics",
            },
            "pause_ui_runtime_hook": {
                "status": "disabled_after_v17_choice_screen_corruption",
                "bytes": 0,
            },
        },
        "verification": verification,
        "runtime": {
            "status": "pending",
            "required": ["clean boot Korean title", "file select", "navigation", "message", "location", "monologue", "pause map", "status screen"],
        },
    }
    return builder, report


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--stable-release-snapshot", action="store_true")
    parser.add_argument("--release-v1-0", action="store_true")
    args = parser.parse_args()
    if args.stable_release_snapshot and args.release_v1_0:
        parser.error("release selectors are mutually exclusive")
    if args.stable_release_snapshot:
        output_rom = STABLE_OUTPUT_ROM
        output_report = STABLE_OUTPUT_REPORT
        builder, report = build(False, output_rom, "fusion_ko_v1_0_final")
    elif args.release_v1_0:
        output_rom = FINAL_OUTPUT_ROM
        output_report = FINAL_OUTPUT_REPORT
        builder, report = build(True, output_rom, "fusion_ko_v1_0_final")
    else:
        output_rom = OUTPUT_ROM
        output_report = OUTPUT_REPORT
        builder, report = build()
    if args.command == "build":
        builder.save(output_rom)
        write_report(output_report, report)
    else:
        if not output_rom.exists() or output_rom.read_bytes() != bytes(builder.buf):
            raise KoreanBuildError("built Korean ROM is missing or stale")
        if not output_report.exists() or json.loads(output_report.read_text(encoding="utf-8")) != report:
            raise KoreanBuildError("Korean build report is missing or stale")
    print(json.dumps({
        "status": "pass",
        "command": args.command,
        "rom": str(output_rom),
        "rom_sha256": report["output"]["rom_sha256"],
        "strings": report["writes"]["text_strings"],
        "pointers": report["writes"]["pointer_fields"],
        "font_tiles": report["writes"]["font_tiles"],
        "remaining_reclaimed_bytes": report["allocation"]["remaining_bytes"],
        "runtime": report["runtime"]["status"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
