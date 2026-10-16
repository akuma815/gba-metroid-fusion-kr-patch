"""Analyze the user-approved Korean CSV without changing its text."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import translation_csv as tc
from navigation_text import REVERSE_CHARACTERS
from rombuild import PROJECT

DEFAULT_CSV = tc.REVIEW_DIR / "metroid_fusion_translation_ko_english_controlcodes_fixed.csv"
OUTPUT_PATH = PROJECT / "workspace" / "analysis" / "translation_corpus.json"
CODE_USAGE_PATH = PROJECT / "workspace" / "analysis" / "text_code_usage.json"
TOKEN_RE = re.compile(r"\{(?:ctrl|glyph):[0-9A-F]{4}\}|\{br\}|\{end\}")
HANGUL_RE = re.compile(r"[가-힣]")
LITERAL_ALIAS_SEQUENCES = {
    "“": '"',
    "”": '"',
    "…": "...",
    "※": "*",
}


class TranslationCorpusError(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def split_units(text: str) -> list[str]:
    """Return the future u16 units while rejecting malformed brace syntax."""
    result: list[str] = []
    cursor = 0
    for match in TOKEN_RE.finditer(text):
        literal = text[cursor:match.start()]
        if "{" in literal or "}" in literal:
            raise TranslationCorpusError(f"malformed token near {literal!r}")
        result.extend(literal)
        result.append(match.group(0))
        cursor = match.end()
    literal = text[cursor:]
    if "{" in literal or "}" in literal:
        raise TranslationCorpusError(f"malformed token near {literal!r}")
    result.extend(literal)
    return result


def encoded_bytes(text: str) -> int:
    units = split_units(text)
    return sum(
        1 if unit.startswith("{") else len(LITERAL_ALIAS_SEQUENCES.get(unit, unit))
        for unit in units
    ) * 2


def source_populations() -> dict[str, list[dict]]:
    nav = tc.load_json(tc.SOURCE_FILES["navigation"])
    additional = tc.load_json(tc.SOURCE_FILES["additional"])
    file_select = tc.load_json(tc.SOURCE_FILES["file_select"])
    result = {
        "navigation": tc.language_entries(nav, "ja"),
        "file_select": tc.language_entries(file_select, "ja"),
        "file_select_shared": file_select["shared"]["entries"],
    }
    for population in additional["populations"]:
        result[population["population_id"]] = tc.language_entries(population, "ja")
    return result


def interval_stats(entries: list[dict]) -> tuple[int, int, list[list[int]]]:
    intervals = sorted(
        (int(entry["file_offset"], 0), int(entry["file_offset"], 0) + entry["byte_length"])
        for entry in entries
    )
    merged: list[list[int]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    occupied = sum(end - start for start, end in merged)
    span = max(end for _, end in intervals) - min(start for start, _ in intervals)
    return occupied, span, merged


def build_report(csv_path: Path) -> dict:
    rows = tc.read_csv(csv_path)
    tc.validate_rows(rows, require_editable_match=True)
    by_id = {row["entry_id"]: row for row in rows}
    literal_counts: Counter[str] = Counter()
    hangul_counts: Counter[str] = Counter()
    token_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    total_target_bytes = 0
    for row in rows:
        text = row["한국어_번역"]
        status_counts[row["상태"]] += 1
        total_target_bytes += encoded_bytes(text)
        for unit in split_units(text):
            if unit.startswith("{"):
                token_counts[unit] += 1
            else:
                literal_counts[unit] += 1
                if HANGUL_RE.fullmatch(unit):
                    hangul_counts[unit] += 1

    supported_literals = (
        set(REVERSE_CHARACTERS)
        | set(hangul_counts)
        | set(LITERAL_ALIAS_SEQUENCES)
        | {"‘", "’"}
    )
    unsupported = [char for char in sorted(literal_counts, key=ord) if char not in supported_literals]
    code_usage = tc.load_json(CODE_USAGE_PATH)
    allocation = []
    for scenario in code_usage["allocation_scenarios"]:
        candidates = scenario["candidate_count"]
        allocation.append({
            "scenario_id": scenario["scenario_id"],
            "inventory_status": scenario["status"],
            "required_hangul_syllables": len(hangul_counts),
            "candidate_count": candidates,
            "nominal_spare_cells": candidates - len(hangul_counts),
            "count_result": "fits" if candidates >= len(hangul_counts) else "overflow",
        })

    population_reports = []
    entry_overflows = []
    populations = source_populations()
    for population_id in ("navigation", "message", "location", "monologue", "file_select", "file_select_shared"):
        entries = populations[population_id]
        target_bytes = sum(encoded_bytes(by_id[entry["entry_id"]]["한국어_번역"]) for entry in entries)
        source_logical = sum(entry["byte_length"] for entry in entries)
        occupied, span, merged = interval_stats(entries)
        overflows = []
        for entry in entries:
            target = encoded_bytes(by_id[entry["entry_id"]]["한국어_번역"])
            if target > entry["byte_length"]:
                item = {
                    "entry_id": entry["entry_id"],
                    "source_bytes": entry["byte_length"],
                    "target_bytes": target,
                    "delta_bytes": target - entry["byte_length"],
                }
                overflows.append(item)
                entry_overflows.append(item)
        population_reports.append({
            "population_id": population_id,
            "entry_count": len(entries),
            "source_logical_bytes": source_logical,
            "source_occupied_union_bytes": occupied,
            "source_occupied_span_bytes": span,
            "source_occupied_ranges": [
                {"start": f"0x{start:X}", "end_exclusive": f"0x{end:X}", "bytes": end - start}
                for start, end in merged
            ],
            "target_independent_bytes": target_bytes,
            "target_minus_source_logical_bytes": target_bytes - source_logical,
            "individual_overflow_count": len(overflows),
            "fits_source_occupied_span_if_independently_repacked": target_bytes <= span,
        })

    file_entries = populations["file_select"]
    aliases = []
    for entry in file_entries:
        alias = entry.get("alias")
        if not alias:
            continue
        parent_units = split_units(by_id[alias["parent_entry_id"]]["한국어_번역"])
        child_units = split_units(by_id[entry["entry_id"]]["한국어_번역"])
        aliases.append({
            "entry_id": entry["entry_id"],
            "parent_entry_id": alias["parent_entry_id"],
            "source_delta_bytes": alias["delta_bytes"],
            "translation_is_parent_suffix": parent_units[-len(child_units):] == child_units,
        })

    source_total = sum(item["source_logical_bytes"] for item in population_reports)
    blockers = []
    if unsupported:
        blockers.append("unsupported_literal_policy_required")
    if any(item["inventory_status"] != "globally_safe" for item in allocation):
        blockers.append("hangul_cells_not_globally_safe")
    # The build repoints every file-select entry independently, so translated
    # rows do not need to preserve the source ROM's suffix-sharing relation.
    if any(
        not item["fits_source_occupied_span_if_independently_repacked"]
        for item in population_reports
    ):
        blockers.append("one_or_more_populations_require_relocation_or_more_space")

    return {
        "schema_version": 1,
        "report_id": "fusion_ko_complete_translation_corpus",
        "source": {
            "csv": str(csv_path.relative_to(PROJECT)).replace("\\", "/"),
            "csv_sha256": sha256(csv_path),
            "translation_json_sha256": {
                key: sha256(path) for key, path in tc.TRANSLATION_FILES.items()
            },
            "code_usage_inventory": str(CODE_USAGE_PATH.relative_to(PROJECT)).replace("\\", "/"),
            "code_usage_inventory_sha256": sha256(CODE_USAGE_PATH),
        },
        "corpus": {
            "entry_count": len(rows),
            "status_counts": dict(sorted(status_counts.items())),
            "unique_hangul_syllables": len(hangul_counts),
            "hangul_occurrences": sum(hangul_counts.values()),
            "unique_literal_characters": len(literal_counts),
            "literal_occurrences": sum(literal_counts.values()),
            "token_occurrences": sum(token_counts.values()),
            "source_logical_bytes": source_total,
            "target_logical_bytes": total_target_bytes,
            "target_to_source_ratio": round(total_target_bytes / source_total, 6),
            "individual_overflow_count": len(entry_overflows),
        },
        "literal_characters": [
            {"character": char, "codepoint": f"U+{ord(char):04X}", "occurrences": literal_counts[char]}
            for char in sorted(literal_counts, key=ord)
        ],
        "unsupported_literals": [
            {"character": char, "codepoint": f"U+{ord(char):04X}", "occurrences": literal_counts[char]}
            for char in unsupported
        ],
        "literal_alias_sequences": {
            f"U+{ord(char):04X}": replacement
            for char, replacement in LITERAL_ALIAS_SEQUENCES.items()
            if literal_counts[char]
        },
        "hangul_allocation": allocation,
        "storage_by_population": population_reports,
        "file_select_internal_suffix_aliases": {
            "count": len(aliases),
            "preserved_count": sum(item["translation_is_parent_suffix"] for item in aliases),
            "entries": aliases,
        },
        "largest_individual_overflows": sorted(
            entry_overflows, key=lambda item: (-item["delta_bytes"], item["entry_id"])
        )[:20],
        "build_blockers": blockers,
        "conclusion": "analysis_only_no_rom_build",
    }


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "verify"))
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    report = build_report(args.csv.resolve())
    if args.command == "generate":
        write_report(report, args.output)
    else:
        if not args.output.exists():
            raise TranslationCorpusError(f"missing report: {args.output}")
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        if existing != report:
            raise TranslationCorpusError("translation corpus report is stale")
    print(json.dumps({
        "status": "pass",
        "command": args.command,
        "entries": report["corpus"]["entry_count"],
        "unique_hangul": report["corpus"]["unique_hangul_syllables"],
        "target_bytes": report["corpus"]["target_logical_bytes"],
        "blockers": report["build_blockers"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
