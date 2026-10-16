"""Extract and byte-roundtrip Fusion JP file-select text, including suffix aliases."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from navigation_text import decode_units, encode_tokens, number, read_string, serialize_units
from rombuild import PROJECT, load_source

FORMAT_PATH = PROJECT / "workspace" / "config" / "file_select_text_format.json"
CATALOG_PATH = PROJECT / "workspace" / "text" / "source" / "file_select_text.json"
TRANSLATION_PATH = PROJECT / "workspace" / "text" / "translation" / "file_select_ko.json"
ROM_BASE_LIMIT = 0x08000000
ROM_END_LIMIT = 0x08800000


class FileSelectTextError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def load_format() -> dict:
    cfg = json.loads(FORMAT_PATH.read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1 or len(cfg.get("languages", [])) != 7:
        raise FileSelectTextError("unsupported file-select format schema")
    return cfg


def union_size(ranges: list[tuple[int, int]]) -> int:
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end - start for start, end in merged)


def parse_table(
    rom: bytes,
    table_id: str,
    table_offset: int,
    entry_count: int,
    rom_base: int,
    mask: int,
    terminator: int,
) -> tuple[dict, list[tuple[int, int]], Counter[int]]:
    table_raw = rom[table_offset:table_offset + entry_count * 4]
    if len(table_raw) != entry_count * 4:
        raise FileSelectTextError(f"truncated pointer table {table_id}")
    pointers = struct.unpack(f"<{entry_count}I", table_raw)
    entries = []
    ranges: list[tuple[int, int]] = []
    controls: Counter[int] = Counter()
    seen_targets: dict[int, str] = {}

    for index, pointer in enumerate(pointers):
        entry_id = f"{table_id}/{index:03d}"
        if pointer < ROM_BASE_LIMIT or pointer >= ROM_END_LIMIT or pointer & 1:
            raise FileSelectTextError(f"invalid pointer {entry_id}=0x{pointer:08X}")
        offset = pointer - rom_base
        if offset in seen_targets:
            raise FileSelectTextError(f"duplicate exact pointer {entry_id} and {seen_targets[offset]}")
        units, raw = read_string(rom, offset, mask, terminator)
        tokens = decode_units(units)
        if encode_tokens(tokens) != units:
            raise FileSelectTextError(f"token roundtrip failed for {entry_id}")
        parent = next(
            (item for item in entries if number(item["file_offset"]) < offset < number(item["file_offset"]) + item["byte_length"]),
            None,
        )
        flags = []
        alias = None
        if parent is not None:
            flags.append("internal_suffix_alias")
            alias = {
                "parent_entry_id": parent["entry_id"],
                "delta_bytes": offset - number(parent["file_offset"]),
            }
        for value in units:
            if value >= 0x8000:
                controls[value] += 1
        entries.append({
            "entry_id": entry_id,
            "index": index,
            "pointer_storage_offset": f"0x{table_offset + index * 4:06X}",
            "pointer_raw_hex": table_raw[index * 4:index * 4 + 4].hex().upper(),
            "gba_address": f"0x{pointer:08X}",
            "file_offset": f"0x{offset:06X}",
            "byte_length": len(raw),
            "raw_sha256": sha256(raw),
            "raw_hex": raw.hex().upper(),
            "source_tokens": tokens,
            "alias": alias,
            "flags": flags,
        })
        seen_targets[offset] = entry_id
        ranges.append((offset, offset + len(raw)))

    return ({
        "table_id": table_id,
        "table_offset": f"0x{table_offset:06X}",
        "table_sha256": sha256(table_raw),
        "entry_count": len(entries),
        "internal_suffix_alias_count": sum("internal_suffix_alias" in entry["flags"] for entry in entries),
        "entries": entries,
    }, ranges, controls)


def parse(rom: bytes, cfg: dict) -> dict:
    rom_base = number(cfg["addressing"]["gba_rom_base"])
    mask = number(cfg["text"]["terminator_mask"])
    terminator = number(cfg["text"]["terminator_value"])
    primary_meta_offset = number(cfg["primary_meta_table_offset"])
    primary_meta_raw = rom[primary_meta_offset:primary_meta_offset + 28]
    primary_meta = struct.unpack("<7I", primary_meta_raw)
    languages = []
    ranges: list[tuple[int, int]] = []
    controls: Counter[int] = Counter()

    for index, lang_cfg in enumerate(cfg["languages"]):
        table_offset = number(lang_cfg["table_offset"])
        if primary_meta[index] != rom_base + table_offset:
            raise FileSelectTextError(f"primary meta pointer mismatch {lang_cfg['id']}")
        table, table_ranges, table_controls = parse_table(
            rom, f"file_select/{lang_cfg['id']}", table_offset, lang_cfg["entry_count"],
            rom_base, mask, terminator,
        )
        table["language_id"] = lang_cfg["id"]
        table["name"] = lang_cfg["name"]
        languages.append(table)
        ranges.extend(table_ranges)
        controls.update(table_controls)

    shared_cfg = cfg["shared"]
    shared_meta_offset = number(shared_cfg["meta_table_offset"])
    shared_meta_raw = rom[shared_meta_offset:shared_meta_offset + shared_cfg["meta_pointer_count"] * 4]
    shared_meta = struct.unpack(f"<{shared_cfg['meta_pointer_count']}I", shared_meta_raw)
    shared_table_offset = number(shared_cfg["table_offset"])
    if any(pointer != rom_base + shared_table_offset for pointer in shared_meta):
        raise FileSelectTextError("shared meta pointers are not the declared shared table")
    shared, shared_ranges, shared_controls = parse_table(
        rom, shared_cfg["id"], shared_table_offset, shared_cfg["entry_count"],
        rom_base, mask, terminator,
    )
    ranges.extend(shared_ranges)
    controls.update(shared_controls)
    entry_count = sum(item["entry_count"] for item in languages) + shared["entry_count"]
    pointer_bytes = entry_count * 4
    referenced_text_bytes = sum(
        entry["byte_length"] for language in languages for entry in language["entries"]
    ) + sum(entry["byte_length"] for entry in shared["entries"])

    return {
        "schema_version": 1,
        "catalog_id": "fusion_jp_file_select_text_all_languages",
        "source": {
            "profile": "workspace/config/source_rom.json",
            "sha256": sha256(rom),
            "size_bytes": len(rom),
        },
        "format": {
            "profile": "workspace/config/file_select_text_format.json",
            "pointer_basis": "gba_rom_address",
            "gba_rom_base": f"0x{rom_base:08X}",
            "text_unit_width_bytes": 2,
            "terminator": "0xFF00",
            "alias_policy": cfg["alias_policy"],
        },
        "primary_meta_table_offset": f"0x{primary_meta_offset:06X}",
        "primary_meta_table_raw_hex": primary_meta_raw.hex().upper(),
        "shared_meta_table_offset": f"0x{shared_meta_offset:06X}",
        "shared_meta_table_raw_hex": shared_meta_raw.hex().upper(),
        "statistics": {
            "language_count": 7,
            "entry_count": entry_count,
            "pointer_bytes": pointer_bytes,
            "meta_bytes": len(primary_meta_raw) + len(shared_meta_raw),
            "referenced_text_bytes": referenced_text_bytes,
            "unique_covered_text_bytes": union_size(ranges),
            "internal_suffix_alias_count": sum(item["internal_suffix_alias_count"] for item in languages),
            "observed_control_units": {
                f"0x{value:04X}": count for value, count in sorted(controls.items())
            },
        },
        "languages": languages,
        "shared": shared,
    }


def verify_table(table: dict, rom: bytes, expected_offset: int, expected_count: int, ids: set[str]) -> dict:
    if number(table["table_offset"]) != expected_offset or table["entry_count"] != expected_count:
        raise FileSelectTextError(f"table shape mismatch {table['table_id']}")
    table_bytes = bytearray()
    alias_count = 0
    for index, entry in enumerate(table["entries"]):
        expected_id = f"{table['table_id']}/{index:03d}"
        if entry["entry_id"] != expected_id or expected_id in ids:
            raise FileSelectTextError(f"invalid or duplicate entry id {entry['entry_id']}")
        ids.add(expected_id)
        storage = number(entry["pointer_storage_offset"])
        if storage != expected_offset + index * 4:
            raise FileSelectTextError(f"pointer storage mismatch {expected_id}")
        pointer_raw = bytes.fromhex(entry["pointer_raw_hex"])
        if len(pointer_raw) != 4 or rom[storage:storage + 4] != pointer_raw:
            raise FileSelectTextError(f"pointer bytes changed {expected_id}")
        table_bytes.extend(pointer_raw)
        pointer = struct.unpack("<I", pointer_raw)[0]
        if pointer != number(entry["gba_address"]):
            raise FileSelectTextError(f"pointer value mismatch {expected_id}")
        offset = number(entry["file_offset"])
        if pointer - 0x08000000 != offset:
            raise FileSelectTextError(f"pointer target mismatch {expected_id}")
        raw = bytes.fromhex(entry["raw_hex"])
        if serialize_units(encode_tokens(entry["source_tokens"])) != raw:
            raise FileSelectTextError(f"token/raw roundtrip mismatch {expected_id}")
        if len(raw) != entry["byte_length"] or sha256(raw) != entry["raw_sha256"]:
            raise FileSelectTextError(f"raw metadata mismatch {expected_id}")
        if rom[offset:offset + len(raw)] != raw:
            raise FileSelectTextError(f"ROM text mismatch {expected_id}")
        if "internal_suffix_alias" in entry["flags"]:
            alias_count += 1
            alias = entry["alias"]
            parent = next((item for item in table["entries"] if item["entry_id"] == alias["parent_entry_id"]), None)
            if parent is None or number(parent["file_offset"]) + alias["delta_bytes"] != offset:
                raise FileSelectTextError(f"invalid suffix alias {expected_id}")
        elif entry["alias"] is not None:
            raise FileSelectTextError(f"unexpected alias metadata {expected_id}")
    table_bytes = bytes(table_bytes)
    if sha256(table_bytes) != table["table_sha256"] or rom[expected_offset:expected_offset + len(table_bytes)] != table_bytes:
        raise FileSelectTextError(f"table roundtrip mismatch {table['table_id']}")
    if alias_count != table["internal_suffix_alias_count"]:
        raise FileSelectTextError(f"alias count mismatch {table['table_id']}")
    return {"pointer_bytes": len(table_bytes), "text_bytes": sum(e["byte_length"] for e in table["entries"])}


def verify_catalog(catalog: dict, rom: bytes, cfg: dict) -> dict:
    if catalog.get("schema_version") != 1 or catalog["source"]["sha256"] != sha256(rom):
        raise FileSelectTextError("catalog source baseline mismatch")
    primary_offset = number(cfg["primary_meta_table_offset"])
    primary_raw = bytes.fromhex(catalog["primary_meta_table_raw_hex"])
    if len(primary_raw) != 28 or rom[primary_offset:primary_offset + 28] != primary_raw:
        raise FileSelectTextError("primary meta byte mismatch")
    shared_cfg = cfg["shared"]
    shared_meta_offset = number(shared_cfg["meta_table_offset"])
    shared_meta_raw = bytes.fromhex(catalog["shared_meta_table_raw_hex"])
    if len(shared_meta_raw) != 28 or rom[shared_meta_offset:shared_meta_offset + 28] != shared_meta_raw:
        raise FileSelectTextError("shared meta byte mismatch")
    ids: set[str] = set()
    pointer_bytes = 0
    referenced_text_bytes = 0
    if len(catalog["languages"]) != 7:
        raise FileSelectTextError("catalog language count mismatch")
    for lang_cfg, table in zip(cfg["languages"], catalog["languages"]):
        if table["language_id"] != lang_cfg["id"]:
            raise FileSelectTextError("language order mismatch")
        result = verify_table(table, rom, number(lang_cfg["table_offset"]), lang_cfg["entry_count"], ids)
        pointer_bytes += result["pointer_bytes"]
        referenced_text_bytes += result["text_bytes"]
    result = verify_table(
        catalog["shared"], rom, number(shared_cfg["table_offset"]), shared_cfg["entry_count"], ids
    )
    pointer_bytes += result["pointer_bytes"]
    referenced_text_bytes += result["text_bytes"]
    if len(ids) != catalog["statistics"]["entry_count"]:
        raise FileSelectTextError("catalog entry population mismatch")
    return {
        "status": "pass",
        "entries": len(ids),
        "pointer_bytes": pointer_bytes,
        "referenced_text_bytes": referenced_text_bytes,
        "meta_bytes": len(primary_raw) + len(shared_meta_raw),
        "internal_suffix_aliases": catalog["statistics"]["internal_suffix_alias_count"],
        "source_sha256": sha256(rom),
    }


def translation_source_entries(catalog: dict) -> list[dict]:
    japanese = next(item for item in catalog["languages"] if item["language_id"] == "ja")
    return [*japanese["entries"], *catalog["shared"]["entries"]]


def verify_translation(catalog: dict, translation: dict) -> dict:
    if set(translation) != {"schema_version", "translation_id", "source_catalog", "source_catalog_sha256", "scope", "entries"}:
        raise FileSelectTextError("translation top-level fields mismatch")
    catalog_hash = sha256(CATALOG_PATH.read_bytes())
    if translation["schema_version"] != 1 or translation["source_catalog_sha256"] != catalog_hash:
        raise FileSelectTextError("translation source catalog baseline is stale")
    expected_ids = [entry["entry_id"] for entry in translation_source_entries(catalog)]
    if translation["scope"] != {"source_language": "ja+shared", "target_language": "ko", "entry_count": len(expected_ids)}:
        raise FileSelectTextError("translation scope mismatch")
    if [entry.get("entry_id") for entry in translation["entries"]] != expected_ids:
        raise FileSelectTextError("translation entry population mismatch")
    allowed = {"untranslated", "in_progress", "needs_review", "needs_human_review", "complete"}
    for entry in translation["entries"]:
        if set(entry) != {"entry_id", "ko", "status", "notes", "flags"}:
            raise FileSelectTextError(f"translation entry fields mismatch {entry.get('entry_id')}")
        if not isinstance(entry["ko"], str) or entry["status"] not in allowed:
            raise FileSelectTextError(f"invalid translation value {entry['entry_id']}")
    return {"status": "pass", "entries": len(expected_ids), "source_catalog_sha256": catalog_hash}


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def init_translation(catalog: dict):
    if TRANSLATION_PATH.exists():
        raise FileSelectTextError(f"refusing to overwrite translation asset: {TRANSLATION_PATH}")
    entries = translation_source_entries(catalog)
    value = {
        "schema_version": 1,
        "translation_id": "fusion_jp_file_select_ko",
        "source_catalog": "workspace/text/source/file_select_text.json",
        "source_catalog_sha256": sha256(CATALOG_PATH.read_bytes()),
        "scope": {"source_language": "ja+shared", "target_language": "ko", "entry_count": len(entries)},
        "entries": [
            {
                "entry_id": entry["entry_id"],
                "ko": "",
                "status": "untranslated",
                "notes": None,
                "flags": list(entry["flags"])
                + (["shared_all_languages"] if entry["entry_id"].startswith("file_select_shared/") else []),
            }
            for entry in entries
        ],
    }
    write_json(TRANSLATION_PATH, value)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    extract = sub.add_parser("extract")
    extract.add_argument("--init-translation", action="store_true")
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
    except (FileSelectTextError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"file-select text error: {exc}")
