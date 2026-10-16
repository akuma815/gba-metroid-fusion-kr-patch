"""Extract and byte-roundtrip Fusion JP message, location, and monologue text."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from navigation_text import decode_units, encode_tokens, number, read_string, serialize_units
from rombuild import PROJECT, load_source

FORMAT_PATH = PROJECT / "workspace" / "config" / "additional_text_format.json"
CATALOG_PATH = PROJECT / "workspace" / "text" / "source" / "additional_text.json"
TRANSLATION_PATH = PROJECT / "workspace" / "text" / "translation" / "additional_ko.json"
ROM_BASE_LIMIT = 0x08000000
ROM_END_LIMIT = 0x08800000


class AdditionalTextError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def load_format() -> dict:
    cfg = json.loads(FORMAT_PATH.read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1:
        raise AdditionalTextError("unsupported additional text format schema")
    if len(cfg.get("languages", [])) != 7:
        raise AdditionalTextError("additional text format must declare 7 languages")
    population_ids = [item["id"] for item in cfg.get("populations", [])]
    if population_ids != ["message", "location", "monologue"]:
        raise AdditionalTextError("unexpected population order")
    return cfg


def parse(rom: bytes, cfg: dict) -> dict:
    rom_base = number(cfg["addressing"]["gba_rom_base"])
    mask = number(cfg["text"]["terminator_mask"])
    terminator = number(cfg["text"]["terminator_value"])
    populations = []
    all_ids: set[str] = set()
    all_ranges: list[tuple[int, int, str]] = []
    all_controls: Counter[int] = Counter()
    total_text_bytes = 0
    total_pointer_bytes = 0

    for pop_cfg in cfg["populations"]:
        pop_id = pop_cfg["id"]
        meta_offset = number(pop_cfg["meta_table_offset"])
        entry_count = pop_cfg["entries_per_language"]
        meta_raw = rom[meta_offset:meta_offset + len(cfg["languages"]) * 4]
        if len(meta_raw) != len(cfg["languages"]) * 4:
            raise AdditionalTextError(f"truncated meta table {pop_id}")
        meta_pointers = struct.unpack(f"<{len(cfg['languages'])}I", meta_raw)
        languages = []

        for lang_index, lang_cfg in enumerate(cfg["languages"]):
            table_pointer = meta_pointers[lang_index]
            if table_pointer < ROM_BASE_LIMIT or table_pointer >= ROM_END_LIMIT or table_pointer & 3:
                raise AdditionalTextError(
                    f"invalid meta pointer {pop_id}/{lang_cfg['id']}=0x{table_pointer:08X}"
                )
            table_offset = table_pointer - rom_base
            table_raw = rom[table_offset:table_offset + entry_count * 4]
            if len(table_raw) != entry_count * 4:
                raise AdditionalTextError(f"truncated pointer table {pop_id}/{lang_cfg['id']}")
            pointers = struct.unpack(f"<{entry_count}I", table_raw)
            entries = []
            seen_targets: set[int] = set()
            previous_end = None

            for index, pointer in enumerate(pointers):
                entry_id = f"{pop_id}/{lang_cfg['id']}/{index:03d}"
                if pointer < ROM_BASE_LIMIT or pointer >= ROM_END_LIMIT or pointer & 1:
                    raise AdditionalTextError(f"invalid pointer {entry_id}=0x{pointer:08X}")
                offset = pointer - rom_base
                if offset in seen_targets:
                    raise AdditionalTextError(f"duplicate pointer {entry_id}=0x{offset:X}")
                seen_targets.add(offset)
                if previous_end is not None and offset < previous_end:
                    raise AdditionalTextError(f"overlap before {entry_id}")
                units, raw = read_string(rom, offset, mask, terminator)
                tokens = decode_units(units)
                if encode_tokens(tokens) != units:
                    raise AdditionalTextError(f"token roundtrip failed for {entry_id}")
                if entry_id in all_ids:
                    raise AdditionalTextError(f"duplicate entry id {entry_id}")
                all_ids.add(entry_id)
                all_ranges.append((offset, offset + len(raw), entry_id))
                for value in units:
                    if value >= 0x8000:
                        all_controls[value] += 1
                entries.append({
                    "entry_id": entry_id,
                    "index": index,
                    "pointer_storage_offset": f"0x{table_offset + index * 4:06X}",
                    "pointer_raw_hex": table_raw[index * 4:index * 4 + 4].hex().upper(),
                    "gba_address": f"0x{pointer:08X}",
                    "file_offset": f"0x{offset:06X}",
                    "byte_length": len(raw),
                    "gap_before_bytes": None if previous_end is None else offset - previous_end,
                    "raw_sha256": sha256(raw),
                    "raw_hex": raw.hex().upper(),
                    "source_tokens": tokens,
                    "flags": [],
                })
                previous_end = offset + len(raw)
                total_text_bytes += len(raw)

            languages.append({
                "language_id": lang_cfg["id"],
                "name": lang_cfg["name"],
                "table_offset": f"0x{table_offset:06X}",
                "table_sha256": sha256(table_raw),
                "entry_count": len(entries),
                "unique_pointer_count": len(seen_targets),
                "text_start": entries[0]["file_offset"],
                "text_end_exclusive": f"0x{previous_end:06X}",
                "entries": entries,
            })
            total_pointer_bytes += len(table_raw)

        populations.append({
            "population_id": pop_id,
            "name": pop_cfg["name"],
            "meta_table_offset": f"0x{meta_offset:06X}",
            "meta_table_raw_hex": meta_raw.hex().upper(),
            "entries_per_language": entry_count,
            "languages": languages,
        })

    ordered_ranges = sorted(all_ranges)
    for previous, current in zip(ordered_ranges, ordered_ranges[1:]):
        if current[0] < previous[1]:
            raise AdditionalTextError(f"cross-population overlap: {previous[2]} and {current[2]}")

    return {
        "schema_version": 1,
        "catalog_id": "fusion_jp_additional_main_text_all_languages",
        "source": {
            "profile": "workspace/config/source_rom.json",
            "sha256": sha256(rom),
            "size_bytes": len(rom),
        },
        "format": {
            "profile": "workspace/config/additional_text_format.json",
            "pointer_basis": "gba_rom_address",
            "gba_rom_base": f"0x{rom_base:08X}",
            "pointer_width_bytes": 4,
            "pointer_endian": "little",
            "text_unit_width_bytes": 2,
            "text_unit_endian": "little",
            "terminator": "0xFF00",
        },
        "statistics": {
            "population_count": len(populations),
            "language_count": len(cfg["languages"]),
            "entry_count": len(all_ids),
            "pointer_bytes": total_pointer_bytes,
            "text_bytes": total_text_bytes,
            "observed_control_units": {
                f"0x{value:04X}": count for value, count in sorted(all_controls.items())
            },
        },
        "populations": populations,
    }


def verify_catalog(catalog: dict, rom: bytes, cfg: dict) -> dict:
    if catalog.get("schema_version") != 1:
        raise AdditionalTextError("unsupported catalog schema")
    if catalog["source"]["sha256"] != sha256(rom):
        raise AdditionalTextError("catalog source SHA-256 does not match ROM")
    if len(catalog.get("populations", [])) != len(cfg["populations"]):
        raise AdditionalTextError("catalog population count mismatch")
    rom_base = number(cfg["addressing"]["gba_rom_base"])
    ids: set[str] = set()
    checked_text_bytes = 0
    checked_pointer_bytes = 0
    checked_meta_bytes = 0

    for pop_cfg, population in zip(cfg["populations"], catalog["populations"]):
        pop_id = pop_cfg["id"]
        if population["population_id"] != pop_id:
            raise AdditionalTextError("catalog population order mismatch")
        meta_offset = number(population["meta_table_offset"])
        if meta_offset != number(pop_cfg["meta_table_offset"]):
            raise AdditionalTextError(f"meta table offset mismatch {pop_id}")
        meta_raw = bytes.fromhex(population["meta_table_raw_hex"])
        if len(meta_raw) != len(cfg["languages"]) * 4 or rom[meta_offset:meta_offset + len(meta_raw)] != meta_raw:
            raise AdditionalTextError(f"meta table byte mismatch {pop_id}")
        checked_meta_bytes += len(meta_raw)
        meta_pointers = struct.unpack(f"<{len(cfg['languages'])}I", meta_raw)

        for lang_index, (lang_cfg, language) in enumerate(zip(cfg["languages"], population["languages"])):
            if language["language_id"] != lang_cfg["id"]:
                raise AdditionalTextError(f"catalog language order mismatch {pop_id}")
            if language["entry_count"] != pop_cfg["entries_per_language"]:
                raise AdditionalTextError(f"entry count mismatch {pop_id}/{lang_cfg['id']}")
            table_offset = number(language["table_offset"])
            if meta_pointers[lang_index] != rom_base + table_offset:
                raise AdditionalTextError(f"meta pointer mismatch {pop_id}/{lang_cfg['id']}")
            table_bytes = bytearray()

            for index, entry in enumerate(language["entries"]):
                expected_id = f"{pop_id}/{lang_cfg['id']}/{index:03d}"
                if entry["entry_id"] != expected_id or expected_id in ids:
                    raise AdditionalTextError(f"invalid or duplicate entry id {entry['entry_id']}")
                ids.add(expected_id)
                storage = number(entry["pointer_storage_offset"])
                if storage != table_offset + index * 4:
                    raise AdditionalTextError(f"pointer storage mismatch {expected_id}")
                pointer_raw = bytes.fromhex(entry["pointer_raw_hex"])
                if len(pointer_raw) != 4 or rom[storage:storage + 4] != pointer_raw:
                    raise AdditionalTextError(f"pointer bytes changed {expected_id}")
                table_bytes.extend(pointer_raw)
                pointer = struct.unpack("<I", pointer_raw)[0]
                offset = number(entry["file_offset"])
                if pointer != number(entry["gba_address"]) or pointer - rom_base != offset:
                    raise AdditionalTextError(f"pointer target mismatch {expected_id}")
                raw = bytes.fromhex(entry["raw_hex"])
                rebuilt = serialize_units(encode_tokens(entry["source_tokens"]))
                if rebuilt != raw:
                    raise AdditionalTextError(f"token/raw roundtrip mismatch {expected_id}")
                if len(raw) != entry["byte_length"] or sha256(raw) != entry["raw_sha256"]:
                    raise AdditionalTextError(f"raw metadata mismatch {expected_id}")
                if rom[offset:offset + len(raw)] != raw:
                    raise AdditionalTextError(f"ROM text mismatch {expected_id}")
                checked_text_bytes += len(raw)

            table_bytes = bytes(table_bytes)
            if sha256(table_bytes) != language["table_sha256"]:
                raise AdditionalTextError(f"table hash mismatch {pop_id}/{lang_cfg['id']}")
            if rom[table_offset:table_offset + len(table_bytes)] != table_bytes:
                raise AdditionalTextError(f"table roundtrip mismatch {pop_id}/{lang_cfg['id']}")
            checked_pointer_bytes += len(table_bytes)

    expected_entries = sum(item["entries_per_language"] for item in cfg["populations"]) * len(cfg["languages"])
    if len(ids) != expected_entries:
        raise AdditionalTextError("catalog population mismatch")
    return {
        "status": "pass",
        "populations": len(cfg["populations"]),
        "languages": len(cfg["languages"]),
        "entries": len(ids),
        "pointer_bytes": checked_pointer_bytes,
        "text_bytes": checked_text_bytes,
        "meta_bytes": checked_meta_bytes,
        "source_sha256": sha256(rom),
    }


def japanese_entries(catalog: dict) -> list[dict]:
    result = []
    for population in catalog["populations"]:
        language = next(item for item in population["languages"] if item["language_id"] == "ja")
        result.extend(language["entries"])
    return result


def verify_translation(catalog: dict, translation: dict) -> dict:
    expected_top = {
        "schema_version", "translation_id", "source_catalog", "source_catalog_sha256",
        "scope", "entries",
    }
    if set(translation) != expected_top:
        raise AdditionalTextError(
            f"translation top-level fields mismatch: {sorted(set(translation) ^ expected_top)}"
        )
    if translation["schema_version"] != 1:
        raise AdditionalTextError("unsupported translation schema")
    catalog_hash = sha256(CATALOG_PATH.read_bytes())
    if translation["source_catalog_sha256"] != catalog_hash:
        raise AdditionalTextError("translation source catalog baseline is stale")
    expected_ids = [entry["entry_id"] for entry in japanese_entries(catalog)]
    if translation["scope"] != {
        "source_language": "ja", "target_language": "ko", "entry_count": len(expected_ids)
    }:
        raise AdditionalTextError("translation scope mismatch")
    entries = translation["entries"]
    if len(entries) != len(expected_ids):
        raise AdditionalTextError("translation entry count mismatch")
    allowed_status = {"untranslated", "in_progress", "needs_review", "needs_human_review", "complete"}
    for index, (entry, expected_id) in enumerate(zip(entries, expected_ids)):
        if set(entry) != {"entry_id", "ko", "status", "notes", "flags"}:
            raise AdditionalTextError(f"translation entry fields mismatch at {index}")
        if entry["entry_id"] != expected_id:
            raise AdditionalTextError(f"translation entry id mismatch at {index}")
        if not isinstance(entry["ko"], str) or entry["status"] not in allowed_status:
            raise AdditionalTextError(f"invalid translation value at {expected_id}")
        if entry["notes"] is not None and not isinstance(entry["notes"], str):
            raise AdditionalTextError(f"invalid notes at {expected_id}")
        if not isinstance(entry["flags"], list) or any(not isinstance(v, str) for v in entry["flags"]):
            raise AdditionalTextError(f"invalid flags at {expected_id}")
    return {"status": "pass", "entries": len(entries), "source_catalog_sha256": catalog_hash}


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def init_translation(catalog: dict):
    if TRANSLATION_PATH.exists():
        raise AdditionalTextError(f"refusing to overwrite translation asset: {TRANSLATION_PATH}")
    entries = japanese_entries(catalog)
    translation = {
        "schema_version": 1,
        "translation_id": "fusion_jp_additional_main_text_ko",
        "source_catalog": "workspace/text/source/additional_text.json",
        "source_catalog_sha256": sha256(CATALOG_PATH.read_bytes()),
        "scope": {"source_language": "ja", "target_language": "ko", "entry_count": len(entries)},
        "entries": [
            {"entry_id": entry["entry_id"], "ko": "", "status": "untranslated", "notes": None, "flags": []}
            for entry in entries
        ],
    }
    write_json(TRANSLATION_PATH, translation)


def rebind_translation(catalog: dict):
    if not TRANSLATION_PATH.exists():
        raise AdditionalTextError(f"translation asset does not exist: {TRANSLATION_PATH}")
    translation = json.loads(TRANSLATION_PATH.read_text(encoding="utf-8"))
    expected_ids = [entry["entry_id"] for entry in japanese_entries(catalog)]
    actual_ids = [entry.get("entry_id") for entry in translation.get("entries", [])]
    if actual_ids != expected_ids:
        raise AdditionalTextError("refusing to rebind translation with a changed entry population")
    translation["source_catalog_sha256"] = sha256(CATALOG_PATH.read_bytes())
    write_json(TRANSLATION_PATH, translation)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract")
    extract.add_argument("--init-translation", action="store_true")
    extract.add_argument("--rebind-translation", action="store_true")
    sub.add_parser("verify")
    args = parser.parse_args()

    rom = load_source()
    cfg = load_format()
    if args.command == "extract":
        catalog = parse(rom, cfg)
        write_json(CATALOG_PATH, catalog)
        result = verify_catalog(catalog, rom, cfg)
        if args.init_translation:
            init_translation(catalog)
        if args.rebind_translation:
            rebind_translation(catalog)
        print(f"catalog: {CATALOG_PATH}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        result = {"catalog": verify_catalog(catalog, rom, cfg)}
        if TRANSLATION_PATH.exists():
            translation = json.loads(TRANSLATION_PATH.read_text(encoding="utf-8"))
            result["translation"] = verify_translation(catalog, translation)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (AdditionalTextError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"additional text error: {exc}")
