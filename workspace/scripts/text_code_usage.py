"""Inventory confirmed Fusion JP main-text glyph/control use and provisional Hangul cells."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path

import additional_text as at
import file_select_text as fst
import navigation_text as nt
from rombuild import PROJECT, load_source

OUTPUT_PATH = PROJECT / "workspace" / "analysis" / "text_code_usage.json"
WIDTH_TABLE_OFFSET = 0x578934
WIDTH_TABLE_MAX_CODE = 0x049F


class TextCodeUsageError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def catalog_entries(catalog: dict):
    if catalog.get("catalog_id") == "fusion_jp_file_select_text_all_languages":
        for language in catalog["languages"]:
            for entry in language["entries"]:
                yield "file_select", language["language_id"], entry
        for entry in catalog["shared"]["entries"]:
            yield "file_select_shared", "shared", entry
        return
    if "languages" in catalog:
        for language in catalog["languages"]:
            for entry in language["entries"]:
                yield "navigation", language["language_id"], entry
        return
    for population in catalog["populations"]:
        for language in population["languages"]:
            for entry in language["entries"]:
                yield population["population_id"], language["language_id"], entry


def units(entry: dict) -> tuple[int, ...]:
    raw = bytes.fromhex(entry["raw_hex"])
    return struct.unpack(f"<{len(raw) // 2}H", raw)


def glyph_width(rom: bytes, code: int) -> int:
    if code <= WIDTH_TABLE_MAX_CODE:
        return rom[WIDTH_TABLE_OFFSET + code]
    return 10


def physical_tiles(code: int, width: int) -> set[int]:
    result = {code, code + 0x20}
    if width > 8:
        result.update({code + 1, code + 0x21})
    return result


def valid_fullwidth_cell(code: int) -> bool:
    return code % 2 == 0 and code & 0x20 == 0


def stride_ranges(values: list[int], step: int = 2) -> list[dict]:
    ranges: list[list[int]] = []
    for value in sorted(values):
        if not ranges or value != ranges[-1][1] + step:
            ranges.append([value, value])
        else:
            ranges[-1][1] = value
    return [
        {"start": f"0x{start:04X}", "end": f"0x{end:04X}", "count": (end - start) // step + 1}
        for start, end in ranges
    ]


def candidate_scenario(
    name: str,
    source_codes: set[int],
    preserved_languages: list[str],
    glyph_sets: dict[str, set[int]],
    rom: bytes,
) -> dict:
    preserved_tiles: set[int] = set()
    for language in preserved_languages:
        for code in glyph_sets[language]:
            preserved_tiles.update(physical_tiles(code, glyph_width(rom, code)))
    candidates = [
        code for code in sorted(source_codes)
        if valid_fullwidth_cell(code)
        and not physical_tiles(code, 12).intersection(preserved_tiles)
    ]
    return {
        "scenario_id": name,
        "status": "provisional_not_globally_safe",
        "preserved_languages": preserved_languages,
        "hangul_width_px": 12,
        "cell_footprint": ["code", "code+1", "code+0x20", "code+0x21"],
        "candidate_count": len(candidates),
        "candidate_codes": [f"0x{code:04X}" for code in candidates],
        "candidate_ranges_step_2": stride_ranges(candidates),
    }


def build_inventory(rom: bytes, nav_catalog: dict, additional_catalog: dict, file_select_catalog: dict) -> dict:
    nt.verify_catalog(nav_catalog, rom, nt.load_format())
    at.verify_catalog(additional_catalog, rom, at.load_format())
    fst.verify_catalog(file_select_catalog, rom, fst.load_format())
    counters: dict[str, Counter[int]] = defaultdict(Counter)
    population_counts: Counter[str] = Counter()
    total_entries = 0
    total_text_bytes = 0

    for catalog in (nav_catalog, additional_catalog, file_select_catalog):
        for population, language, entry in catalog_entries(catalog):
            population_counts[population] += 1
            total_entries += 1
            total_text_bytes += entry["byte_length"]
            counters[language].update(units(entry))

    language_order = [item["id"] for item in nt.load_format()["languages"]]
    shared_counter = counters["shared"]
    effective_counters = {
        language: counters[language] + shared_counter for language in language_order
    }
    glyph_sets = {
        language: {value for value in effective_counters[language] if value < 0x8000}
        for language in language_order
    }
    language_stats = []
    for language in language_order:
        counter = effective_counters[language]
        glyphs = glyph_sets[language]
        controls = {value for value in counter if value >= 0x8000}
        language_stats.append({
            "language_id": language,
            "shared_file_select_units_included": True,
            "unit_occurrences": sum(counter.values()),
            "unique_units": len(counter),
            "glyph_occurrences": sum(count for value, count in counter.items() if value < 0x8000),
            "unique_glyph_codes": len(glyphs),
            "glyph_min": f"0x{min(glyphs):04X}",
            "glyph_max": f"0x{max(glyphs):04X}",
            "unique_control_units": len(controls),
            "control_occurrences": sum(count for value, count in counter.items() if value >= 0x8000),
        })

    western = ["en", "de", "fr", "it", "es"]
    scenarios = [
        candidate_scenario(
            "replace_ja_preserve_hiragana_and_western",
            glyph_sets["ja"],
            ["ja_hiragana", *western],
            glyph_sets,
            rom,
        ),
        candidate_scenario(
            "replace_both_japanese_modes_preserve_western",
            glyph_sets["ja"] | glyph_sets["ja_hiragana"],
            western,
            glyph_sets,
            rom,
        ),
    ]

    return {
        "schema_version": 1,
        "inventory_id": "fusion_jp_confirmed_main_text_code_usage",
        "source": {
            "rom_sha256": sha256(rom),
            "navigation_catalog": "workspace/text/source/navigation_text.json",
            "navigation_catalog_sha256": sha256(nt.CATALOG_PATH.read_bytes()),
            "additional_catalog": "workspace/text/source/additional_text.json",
            "additional_catalog_sha256": sha256(at.CATALOG_PATH.read_bytes()),
            "file_select_catalog": "workspace/text/source/file_select_text.json",
            "file_select_catalog_sha256": sha256(fst.CATALOG_PATH.read_bytes()),
        },
        "scope": {
            "status": "confirmed_populations_only",
            "populations": ["navigation", "message", "location", "monologue", "file_select", "file_select_shared"],
            "entry_count": total_entries,
            "text_bytes": total_text_bytes,
            "entries_by_population_all_languages": dict(sorted(population_counts.items())),
        },
        "consumer_model": {
            "glyph_domain": "0x0000-0x7FFF",
            "control_domain": "0x8000-0xFFFF",
            "width_table_offset": "0x578934",
            "width_table_last_code": "0x049F",
            "default_width_above_table_px": 10,
            "font_tile_base_offset": "0x683AD8",
            "tile_bytes": 32,
            "bottom_row_delta_tiles": "0x20",
            "fullwidth_tile_footprint": ["code", "code+1", "code+0x20", "code+0x21"],
            "evidence": [
                "JP 0x0798EC GetCharacterWidth uses table through 0x049F and returns 10 above it",
                "JP 0x079E28 DrawLocationTextCharacters sends non-control u16 values to width and draw consumers",
                "JP NavigationConversationProcessText likewise calls GetCharacterWidth and DrawCharacter",
                "JP file-select consumers index 0x7F13FC/0x7F1418 and pass selected u16 strings to the same width/draw path",
            ],
        },
        "languages": language_stats,
        "allocation_scenarios": scenarios,
        "excluded_or_separate_consumers": [
            {
                "address": "0x7F0F84/0x7F0FE4/0x7F10C4",
                "classification": "file_select_oam_animation_pointer_tables",
                "reason": "targets are OAM frame structures and duration/pointer records, not 0xFF00-terminated text streams",
            },
            {
                "address": "0x7F1000",
                "classification": "ending_oam_or_graphics_pointer_tables",
                "reason": "ending code consumers index fixed graphics/OAM pointers; not a u16 text stream",
            },
            {
                "classification": "credits",
                "reason": "separate inline ASCII/credits renderer and graphics; not included in main-font allocation",
            },
        ],
        "limitations": [
            "Candidate cells are collision-free only against the confirmed catalog and selected preserved languages.",
            "Other hard-coded UI strings, unenumerated text consumers, and non-text tile users are not yet globally excluded.",
            "Do not assign a production Korean code map until those consumers and the translated Hangul corpus are known.",
        ],
    }


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    rom = load_source()
    nav_catalog = json.loads(nt.CATALOG_PATH.read_text(encoding="utf-8"))
    additional_catalog = json.loads(at.CATALOG_PATH.read_text(encoding="utf-8"))
    file_select_catalog = json.loads(fst.CATALOG_PATH.read_text(encoding="utf-8"))
    expected = build_inventory(rom, nav_catalog, additional_catalog, file_select_catalog)
    if args.command == "build":
        write_json(OUTPUT_PATH, expected)
        print(f"inventory: {OUTPUT_PATH}")
    else:
        actual = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        if actual != expected:
            raise TextCodeUsageError("text code usage inventory is stale or modified")
    print(json.dumps({
        "status": "pass",
        "entries": expected["scope"]["entry_count"],
        "text_bytes": expected["scope"]["text_bytes"],
        "ja_glyphs": next(x for x in expected["languages"] if x["language_id"] == "ja")["unique_glyph_codes"],
        "candidate_counts": {
            item["scenario_id"]: item["candidate_count"] for item in expected["allocation_scenarios"]
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (TextCodeUsageError, nt.NavigationTextError, at.AdditionalTextError, fst.FileSelectTextError, KeyError, ValueError, OSError) as exc:
        raise SystemExit(f"text code usage error: {exc}")
