"""Audit Fusion font-slot references and build a provisional Korean code map."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from rombuild import PROJECT, load_source
from ui_graphics_audit import decompress_gba_lz77

CODE_USAGE_PATH = PROJECT / "workspace" / "analysis" / "text_code_usage.json"
CORPUS_PATH = PROJECT / "workspace" / "analysis" / "translation_corpus.json"
AUDIT_PATH = PROJECT / "workspace" / "analysis" / "font_slot_audit.json"
MAP_PATH = PROJECT / "workspace" / "config" / "hangul_code_map.json"
SCENARIO_ID = "replace_both_japanese_modes_preserve_western"
FONT_BASE = 0x683AD8
FONT_BOTTOM_DELTA = 0x400
WIDTH_TABLE_OFFSET = 0x578934
WIDTH_TABLE_LAST_CODE = 0x049F
DEFAULT_WIDTH_INSTRUCTION_OFFSET = 0x079908
DEFAULT_WIDTH_EXPECTED = bytes.fromhex("0A20")  # movs r0, #10
DEFAULT_WIDTH_PATCHED = bytes.fromhex("0C20")   # movs r0, #12
KNOWN_FONT_BASE_LITERAL_OFFSETS = (0x0799AC, 0x079B28, 0x079BFC, 0x079CA0, 0x0A2754)
KNOWN_COMPRESSED_FALSE_POINTER = 0x41DA9C
KNOWN_COMPRESSED_STREAM = 0x41D200


class FontSlotAuditError(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def scenario(inventory: dict) -> dict:
    for item in inventory["allocation_scenarios"]:
        if item["scenario_id"] == SCENARIO_ID:
            return item
    raise FontSlotAuditError(f"missing allocation scenario: {SCENARIO_ID}")


def footprint(code: int) -> set[int]:
    return {code, code + 1, code + 0x20, code + 0x21}


def thumb_literal_xrefs(rom: bytes, storage_offset: int) -> list[int]:
    """Find Thumb-1 LDR literal instructions that address a word location."""
    result = []
    start = max(0, storage_offset - 0x800)
    for offset in range(start + (start & 1), storage_offset, 2):
        instruction = struct.unpack_from("<H", rom, offset)[0]
        if instruction & 0xF800 != 0x4800:
            continue
        immediate = (instruction & 0xFF) * 4
        target = ((offset + 4) & ~3) + immediate
        if target == storage_offset:
            result.append(offset)
    return result


def aligned_pointer_hits(rom: bytes, physical_tiles: set[int]) -> list[dict]:
    result = []
    font_address = 0x08000000 + FONT_BASE
    for offset in range(0, len(rom) - 3, 2):
        value = struct.unpack_from("<I", rom, offset)[0]
        delta = value - font_address
        if delta < 0 or delta % 32:
            continue
        tile = delta // 32
        if tile in physical_tiles:
            result.append({
                "storage_offset": f"0x{offset:06X}",
                "raw_value": f"0x{value:08X}",
                "physical_tile": f"0x{tile:04X}",
                "thumb_literal_xrefs": [f"0x{xref:06X}" for xref in thumb_literal_xrefs(rom, offset)],
            })
    return result


def build_audit(rom: bytes, inventory: dict) -> dict:
    selected = scenario(inventory)
    candidates = [int(value, 16) for value in selected["candidate_codes"]]
    physical_tiles: set[int] = set()
    for code in candidates:
        overlap = physical_tiles.intersection(footprint(code))
        if overlap:
            raise FontSlotAuditError(f"candidate footprint collision: 0x{code:04X}")
        physical_tiles.update(footprint(code))

    hits = aligned_pointer_hits(rom, physical_tiles)
    decoded, consumed = decompress_gba_lz77(rom[KNOWN_COMPRESSED_STREAM:])
    stream_end = KNOWN_COMPRESSED_STREAM + consumed
    for hit in hits:
        offset = int(hit["storage_offset"], 0)
        if offset == KNOWN_COMPRESSED_FALSE_POINTER and KNOWN_COMPRESSED_STREAM <= offset < stream_end:
            hit["classification"] = "word_shaped_bytes_inside_confirmed_lz77_stream"
            hit["enclosing_stream"] = {
                "offset": f"0x{KNOWN_COMPRESSED_STREAM:06X}",
                "end_exclusive": f"0x{stream_end:06X}",
                "compressed_bytes": consumed,
                "decoded_bytes": len(decoded),
            }
        elif hit["thumb_literal_xrefs"]:
            hit["classification"] = "live_thumb_literal_reference"
        else:
            hit["classification"] = "unclassified_word_shaped_occurrence"

    font_base_refs = []
    expected_value = 0x08000000 + FONT_BASE
    for offset in KNOWN_FONT_BASE_LITERAL_OFFSETS:
        value = struct.unpack_from("<I", rom, offset)[0]
        if value != expected_value:
            raise FontSlotAuditError(f"font base literal changed at 0x{offset:X}")
        xrefs = thumb_literal_xrefs(rom, offset)
        if not xrefs:
            raise FontSlotAuditError(f"font base literal has no Thumb xref at 0x{offset:X}")
        font_base_refs.append({
            "storage_offset": f"0x{offset:06X}",
            "thumb_literal_xrefs": [f"0x{xref:06X}" for xref in xrefs],
            "consumer": (
                "main_text_draw_or_tile_copy" if offset != 0x0A2754
                else "numeric_glyph_dma_codes_0x0050_and_above"
            ),
        })

    if rom[DEFAULT_WIDTH_INSTRUCTION_OFFSET:DEFAULT_WIDTH_INSTRUCTION_OFFSET + 2] != DEFAULT_WIDTH_EXPECTED:
        raise FontSlotAuditError("default-width instruction baseline changed")
    live_hits = [hit for hit in hits if hit["classification"] == "live_thumb_literal_reference"]
    unknown_hits = [hit for hit in hits if hit["classification"] == "unclassified_word_shaped_occurrence"]
    return {
        "schema_version": 1,
        "audit_id": "fusion_ko_font_slot_static_reference_audit",
        "source": {
            "rom_sha256": hashlib.sha256(rom).hexdigest().upper(),
            "code_usage_inventory": "workspace/analysis/text_code_usage.json",
            "code_usage_inventory_sha256": sha256(CODE_USAGE_PATH),
        },
        "scenario": {
            "scenario_id": SCENARIO_ID,
            "replaced_languages": ["ja", "ja_hiragana"],
            "preserved_languages": selected["preserved_languages"],
            "candidate_count": len(candidates),
            "physical_tile_count": len(physical_tiles),
            "candidate_codes": [f"0x{code:04X}" for code in candidates],
        },
        "font_consumer_model": {
            "font_base_offset": f"0x{FONT_BASE:06X}",
            "top_tile_formula": "font_base + code * 32",
            "bottom_row_delta_bytes": f"0x{FONT_BOTTOM_DELTA:X}",
            "font_base_thumb_literal_count": len(font_base_refs),
            "font_base_thumb_literals": font_base_refs,
            "numeric_consumer_reachable_codes": "observed decimal digit path based at 0x0050; outside Korean candidates",
        },
        "candidate_physical_pointer_audit": {
            "raw_aligned_address_occurrences": len(hits),
            "live_thumb_literal_references": len(live_hits),
            "unclassified_occurrences": len(unknown_hits),
            "compressed_false_positives": sum(
                hit["classification"] == "word_shaped_bytes_inside_confirmed_lz77_stream" for hit in hits
            ),
            "occurrences": hits,
        },
        "width_policy": {
            "advance_px": 12,
            "width_table_offset": f"0x{WIDTH_TABLE_OFFSET:06X}",
            "width_table_last_code": f"0x{WIDTH_TABLE_LAST_CODE:04X}",
            "default_width_instruction_offset": f"0x{DEFAULT_WIDTH_INSTRUCTION_OFFSET:06X}",
            "expected_instruction_hex": DEFAULT_WIDTH_EXPECTED.hex().upper(),
            "patched_instruction_hex": DEFAULT_WIDTH_PATCHED.hex().upper(),
            "reason": "Korean codes above 0x049F use the engine default; both Japanese modes are replaced while preserved Western glyphs stay within the width table.",
        },
        "result": {
            "status": (
                "static_reference_audit_pass_runtime_coverage_pending"
                if not live_hits and not unknown_hits else "blocked_by_external_candidate_reference"
            ),
            "direct_candidate_tile_reference_blockers": len(live_hits) + len(unknown_hits),
            "limitations": [
                "Static pointer evidence cannot prove every computed runtime code path is unreachable.",
                "All translated main-text populations and fixed UI runtime routes still require Mesen coverage after a full build.",
                "The map is provisional until the rebuilt ROM renders representative and boundary scenes without collateral glyph corruption.",
            ],
        },
    }


def build_code_map(audit: dict, corpus: dict) -> dict:
    if audit["result"]["direct_candidate_tile_reference_blockers"]:
        raise FontSlotAuditError("cannot allocate map with unresolved direct tile references")
    hangul = [
        item for item in corpus["literal_characters"]
        if 0xAC00 <= ord(item["character"]) <= 0xD7A3
    ]
    hangul.sort(key=lambda item: ord(item["character"]))
    candidates = [int(value, 16) for value in audit["scenario"]["candidate_codes"]]
    if len(hangul) != corpus["corpus"]["unique_hangul_syllables"]:
        raise FontSlotAuditError("Hangul corpus count mismatch")
    if len(hangul) > len(candidates):
        raise FontSlotAuditError("Hangul corpus exceeds candidate cells")
    mappings = [
        {
            "character": item["character"],
            "unicode": f"U+{ord(item['character']):04X}",
            "code": f"0x{code:04X}",
            "occurrences": item["occurrences"],
        }
        for item, code in zip(hangul, candidates)
    ]
    assigned = set(candidates[:len(mappings)])
    low_assigned = sorted(code for code in assigned if code <= WIDTH_TABLE_LAST_CODE)
    return {
        "schema_version": 1,
        "map_id": "fusion_ko_complete_csv_provisional_code_map",
        "status": "static_audit_pass_runtime_pending",
        "source": {
            "translation_corpus": "workspace/analysis/translation_corpus.json",
            "translation_corpus_sha256": sha256(CORPUS_PATH),
            "font_slot_audit": "workspace/analysis/font_slot_audit.json",
            "font_slot_audit_sha256": sha256(AUDIT_PATH),
            "bitmap_font": "Font/Galmuri11-Condensed_9x12.png",
            "bitmap_font_sha256": "07A9617723AA4EDBFB18442DB86419C3F2B48E4F7C6E2E33229305ADCA582AA1",
        },
        "policy": {
            "allocation_scenario": SCENARIO_ID,
            "replaced_languages": ["ja", "ja_hiragana"],
            "preserved_languages": audit["scenario"]["preserved_languages"],
            "mapping_order": "Hangul Unicode ascending to candidate code ascending",
            "advance_px": 12,
            "curly_quote_aliases": {"U+2018": "0x0047", "U+2019": "0x0047"},
            "curly_quote_rendering": "both encode as the existing straight ASCII apostrophe glyph; CSV text remains unchanged",
            "literal_sequence_aliases": corpus.get("literal_alias_sequences", {}),
            "literal_sequence_rendering": "encode unsupported typography as existing ASCII glyph sequences; CSV text remains unchanged",
            "width_table_codes_to_set_12": [f"0x{code:04X}" for code in low_assigned],
            "default_width_patch": {
                "offset": f"0x{DEFAULT_WIDTH_INSTRUCTION_OFFSET:06X}",
                "expected_hex": DEFAULT_WIDTH_EXPECTED.hex().upper(),
                "new_hex": DEFAULT_WIDTH_PATCHED.hex().upper(),
            },
        },
        "statistics": {
            "required_hangul": len(mappings),
            "candidate_cells": len(candidates),
            "unassigned_candidate_cells": len(candidates) - len(mappings),
            "assigned_codes_with_width_table_entries": len(low_assigned),
            "assigned_codes_using_default_width": len(mappings) - len(low_assigned),
        },
        "mappings": mappings,
        "unassigned_candidate_codes": [
            f"0x{code:04X}" for code in candidates if code not in assigned
        ],
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "verify"))
    args = parser.parse_args()
    rom = load_source()
    inventory = load_json(CODE_USAGE_PATH)
    corpus = load_json(CORPUS_PATH)
    audit = build_audit(rom, inventory)
    if args.command == "generate":
        write_json(AUDIT_PATH, audit)
        code_map = build_code_map(audit, corpus)
        write_json(MAP_PATH, code_map)
    else:
        if not AUDIT_PATH.exists() or not MAP_PATH.exists():
            raise FontSlotAuditError("generated audit or code map is missing")
        if load_json(AUDIT_PATH) != audit:
            raise FontSlotAuditError("font slot audit is stale")
        code_map = build_code_map(audit, corpus)
        if load_json(MAP_PATH) != code_map:
            raise FontSlotAuditError("Hangul code map is stale")
    print(json.dumps({
        "status": "pass",
        "command": args.command,
        "audit_result": audit["result"]["status"],
        "candidate_cells": audit["scenario"]["candidate_count"],
        "mapped_hangul": code_map["statistics"]["required_hangul"],
        "spare_cells": code_map["statistics"]["unassigned_candidate_cells"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
