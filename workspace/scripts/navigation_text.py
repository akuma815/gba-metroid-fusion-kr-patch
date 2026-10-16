"""Extract and byte-roundtrip Fusion JP navigation conversation text."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path

from rombuild import PROJECT, load_source

FORMAT_PATH = PROJECT / "workspace" / "config" / "navigation_text_format.json"
CATALOG_PATH = PROJECT / "workspace" / "text" / "source" / "navigation_text.json"
TRANSLATION_PATH = PROJECT / "workspace" / "text" / "translation" / "navigation_ko.json"
ROM_BASE_LIMIT = 0x08000000
ROM_END_LIMIT = 0x08800000
TOKEN_RE = re.compile(r"\{(br|end|ctrl|glyph)(?::([0-9A-F]{4}))?\}")


class NavigationTextError(Exception):
    pass


def load_format() -> dict:
    cfg = json.loads(FORMAT_PATH.read_text(encoding="utf-8"))
    if cfg.get("schema_version") != 1:
        raise NavigationTextError("unsupported navigation format schema")
    if len(cfg.get("languages", [])) != 7:
        raise NavigationTextError("navigation format must declare 7 languages")
    return cfg


def number(value: str | int) -> int:
    return int(value, 0) if isinstance(value, str) else value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def character_map() -> dict[int, str]:
    mapping = {
        0x40: " ", 0x41: "!", 0x42: '"', 0x43: "#", 0x44: "$",
        0x45: "%", 0x46: "&", 0x47: "'", 0x48: "(", 0x49: ")",
        0x4A: "*", 0x4B: "+", 0x4C: ",", 0x4D: "-", 0x4E: ".",
        0x4F: "/", 0x5A: ":", 0x5B: ";", 0x5D: "=", 0x5F: "?",
    }
    mapping.update({0x50 + i: str(i) for i in range(10)})
    mapping.update({0x81 + i: chr(ord("A") + i) for i in range(26)})
    mapping[0x9B] = "["
    mapping.update({0xC1 + i: chr(ord("a") + i) for i in range(26)})
    return mapping


CHARACTERS = character_map()
REVERSE_CHARACTERS = {value: key for key, value in CHARACTERS.items()}


def decode_units(units: list[int]) -> str:
    out: list[str] = []
    for value in units:
        if value in CHARACTERS:
            out.append(CHARACTERS[value])
        elif value == 0xFE00:
            out.append("{br}")
        elif value == 0xFF00:
            out.append("{end}")
        elif value >= 0x8000:
            out.append(f"{{ctrl:{value:04X}}}")
        elif value < 0x8000:
            out.append(f"{{glyph:{value:04X}}}")
    return "".join(out)


def encode_tokens(text: str) -> list[int]:
    units: list[int] = []
    pos = 0
    while pos < len(text):
        if text[pos] == "{":
            match = TOKEN_RE.match(text, pos)
            if not match:
                raise NavigationTextError(f"invalid token at character {pos}: {text[pos:pos + 20]!r}")
            kind, raw = match.groups()
            if kind == "br":
                if raw is not None:
                    raise NavigationTextError("br token cannot have an argument")
                units.append(0xFE00)
            elif kind == "end":
                if raw is not None:
                    raise NavigationTextError("end token cannot have an argument")
                units.append(0xFF00)
            else:
                if raw is None:
                    raise NavigationTextError(f"{kind} token requires a 4-digit value")
                value = int(raw, 16)
                if kind == "ctrl" and value < 0x8000:
                    raise NavigationTextError(f"ctrl token is not a control unit: {raw}")
                if kind == "glyph" and value >= 0x8000:
                    raise NavigationTextError(f"glyph token is in the control domain: {raw}")
                units.append(value)
            pos = match.end()
            continue
        value = REVERSE_CHARACTERS.get(text[pos])
        if value is None:
            raise NavigationTextError(f"unmapped literal character at {pos}: {text[pos]!r}")
        units.append(value)
        pos += 1
    return units


def read_string(rom: bytes, offset: int, mask: int, terminator: int) -> tuple[list[int], bytes]:
    if offset < 0 or offset % 2 or offset >= len(rom):
        raise NavigationTextError(f"invalid text offset 0x{offset:X}")
    units: list[int] = []
    cursor = offset
    while cursor + 2 <= len(rom):
        value = struct.unpack_from("<H", rom, cursor)[0]
        units.append(value)
        cursor += 2
        if value & mask == terminator:
            if value != terminator:
                raise NavigationTextError(f"unexpected terminator 0x{value:04X} at 0x{cursor - 2:X}")
            return units, rom[offset:cursor]
    raise NavigationTextError(f"unterminated string at 0x{offset:X}")


def parse(rom: bytes, cfg: dict) -> dict:
    addressing = cfg["addressing"]
    text_cfg = cfg["text"]
    meta_offset = number(addressing["meta_table_offset"])
    rom_base = number(addressing["gba_rom_base"])
    entry_count = cfg["entries_per_language"]
    mask = number(text_cfg["terminator_mask"])
    terminator = number(text_cfg["terminator_value"])
    meta_raw = rom[meta_offset:meta_offset + len(cfg["languages"]) * 4]
    meta_pointers = list(struct.unpack(f"<{len(cfg['languages'])}I", meta_raw))
    languages = []
    all_ids: set[str] = set()
    total_text_bytes = 0
    all_controls: Counter[int] = Counter()

    for lang_index, lang_cfg in enumerate(cfg["languages"]):
        table_offset = number(lang_cfg["table_offset"])
        expected_meta = rom_base + table_offset
        if meta_pointers[lang_index] != expected_meta:
            raise NavigationTextError(
                f"meta pointer {lang_cfg['id']}=0x{meta_pointers[lang_index]:08X}, expected 0x{expected_meta:08X}"
            )
        table_raw = rom[table_offset:table_offset + entry_count * 4]
        if len(table_raw) != entry_count * 4:
            raise NavigationTextError(f"truncated pointer table {lang_cfg['id']}")
        pointers = list(struct.unpack(f"<{entry_count}I", table_raw))
        entries = []
        seen_targets: set[int] = set()
        previous_end = None
        for index, pointer in enumerate(pointers):
            if pointer < ROM_BASE_LIMIT or pointer >= ROM_END_LIMIT or pointer & 1:
                raise NavigationTextError(f"invalid pointer {lang_cfg['id']}/{index:03d}=0x{pointer:08X}")
            offset = pointer - rom_base
            if offset in seen_targets:
                raise NavigationTextError(f"duplicate pointer {lang_cfg['id']}/{index:03d}=0x{offset:X}")
            seen_targets.add(offset)
            if previous_end is not None and offset < previous_end:
                raise NavigationTextError(f"overlap before {lang_cfg['id']}/{index:03d}")
            units, raw = read_string(rom, offset, mask, terminator)
            tokens = decode_units(units)
            if encode_tokens(tokens) != units:
                raise NavigationTextError(f"token roundtrip failed for {lang_cfg['id']}/{index:03d}")
            entry_id = f"navigation/{lang_cfg['id']}/{index:03d}"
            if entry_id in all_ids:
                raise NavigationTextError(f"duplicate entry id {entry_id}")
            all_ids.add(entry_id)
            for value in units:
                if value >= 0x8000:
                    all_controls[value] += 1
            gap_before = None if previous_end is None else offset - previous_end
            entries.append({
                "entry_id": entry_id,
                "index": index,
                "pointer_storage_offset": f"0x{table_offset + index * 4:06X}",
                "pointer_raw_hex": table_raw[index * 4:index * 4 + 4].hex().upper(),
                "gba_address": f"0x{pointer:08X}",
                "file_offset": f"0x{offset:06X}",
                "byte_length": len(raw),
                "gap_before_bytes": gap_before,
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

    return {
        "schema_version": 1,
        "catalog_id": "fusion_jp_navigation_all_languages",
        "source": {
            "profile": "workspace/config/source_rom.json",
            "sha256": sha256(rom),
            "size_bytes": len(rom),
        },
        "format": {
            "profile": "workspace/config/navigation_text_format.json",
            "meta_table_offset": f"0x{meta_offset:06X}",
            "meta_table_raw_hex": meta_raw.hex().upper(),
            "pointer_basis": "gba_rom_address",
            "gba_rom_base": f"0x{rom_base:08X}",
            "pointer_width_bytes": 4,
            "pointer_endian": "little",
            "text_unit_width_bytes": 2,
            "text_unit_endian": "little",
            "terminator": "0xFF00",
        },
        "statistics": {
            "language_count": len(languages),
            "entries_per_language": entry_count,
            "entry_count": len(all_ids),
            "total_text_bytes": total_text_bytes,
            "observed_control_units": {
                f"0x{value:04X}": count for value, count in sorted(all_controls.items())
            },
        },
        "languages": languages,
    }


def serialize_units(units: list[int]) -> bytes:
    return struct.pack(f"<{len(units)}H", *units)


def verify_catalog(catalog: dict, rom: bytes, cfg: dict) -> dict:
    if catalog.get("schema_version") != 1:
        raise NavigationTextError("unsupported catalog schema")
    if catalog["source"]["sha256"] != sha256(rom):
        raise NavigationTextError("catalog source SHA-256 does not match ROM")
    expected_languages = cfg["languages"]
    if len(catalog.get("languages", [])) != len(expected_languages):
        raise NavigationTextError("catalog language count mismatch")
    meta_offset = number(cfg["addressing"]["meta_table_offset"])
    meta_raw = bytes.fromhex(catalog["format"]["meta_table_raw_hex"])
    if rom[meta_offset:meta_offset + len(meta_raw)] != meta_raw:
        raise NavigationTextError("meta table byte mismatch")
    ids: set[str] = set()
    checked_entries = 0
    checked_text_bytes = 0
    for lang_cfg, lang in zip(expected_languages, catalog["languages"]):
        if lang["language_id"] != lang_cfg["id"]:
            raise NavigationTextError("catalog language order mismatch")
        if lang["entry_count"] != cfg["entries_per_language"]:
            raise NavigationTextError(f"entry count mismatch for {lang['language_id']}")
        table_offset = number(lang["table_offset"])
        table_bytes = bytearray()
        for index, entry in enumerate(lang["entries"]):
            expected_id = f"navigation/{lang['language_id']}/{index:03d}"
            if entry["entry_id"] != expected_id or expected_id in ids:
                raise NavigationTextError(f"invalid or duplicate entry id {entry['entry_id']}")
            ids.add(expected_id)
            pointer_raw = bytes.fromhex(entry["pointer_raw_hex"])
            if len(pointer_raw) != 4:
                raise NavigationTextError(f"pointer width mismatch {expected_id}")
            table_bytes.extend(pointer_raw)
            storage = number(entry["pointer_storage_offset"])
            if storage != table_offset + index * 4:
                raise NavigationTextError(f"pointer storage mismatch {expected_id}")
            if rom[storage:storage + 4] != pointer_raw:
                raise NavigationTextError(f"pointer bytes changed {expected_id}")
            pointer = struct.unpack("<I", pointer_raw)[0]
            if pointer != number(entry["gba_address"]):
                raise NavigationTextError(f"pointer value mismatch {expected_id}")
            offset = number(entry["file_offset"])
            if pointer - number(cfg["addressing"]["gba_rom_base"]) != offset:
                raise NavigationTextError(f"pointer target mismatch {expected_id}")
            raw = bytes.fromhex(entry["raw_hex"])
            units = encode_tokens(entry["source_tokens"])
            rebuilt = serialize_units(units)
            if rebuilt != raw:
                raise NavigationTextError(f"token/raw roundtrip mismatch {expected_id}")
            if len(raw) != entry["byte_length"] or sha256(raw) != entry["raw_sha256"]:
                raise NavigationTextError(f"raw metadata mismatch {expected_id}")
            if rom[offset:offset + len(raw)] != raw:
                raise NavigationTextError(f"ROM text mismatch {expected_id}")
            checked_entries += 1
            checked_text_bytes += len(raw)
        table_bytes = bytes(table_bytes)
        if sha256(table_bytes) != lang["table_sha256"]:
            raise NavigationTextError(f"table hash mismatch {lang['language_id']}")
        if rom[table_offset:table_offset + len(table_bytes)] != table_bytes:
            raise NavigationTextError(f"table roundtrip mismatch {lang['language_id']}")
    if checked_entries != len(expected_languages) * cfg["entries_per_language"]:
        raise NavigationTextError("catalog population mismatch")
    return {
        "status": "pass",
        "languages": len(expected_languages),
        "entries": checked_entries,
        "pointer_bytes": checked_entries * 4,
        "text_bytes": checked_text_bytes,
        "meta_bytes": len(expected_languages) * 4,
        "source_sha256": sha256(rom),
    }


def verify_translation(catalog: dict, translation: dict) -> dict:
    expected_top = {
        "schema_version", "translation_id", "source_catalog", "source_catalog_sha256",
        "scope", "entries",
    }
    if set(translation) != expected_top:
        raise NavigationTextError(
            f"translation top-level fields mismatch: {sorted(set(translation) ^ expected_top)}"
        )
    if translation["schema_version"] != 1:
        raise NavigationTextError("unsupported translation schema")
    catalog_hash = sha256(CATALOG_PATH.read_bytes())
    if translation["source_catalog_sha256"] != catalog_hash:
        raise NavigationTextError("translation source catalog baseline is stale")
    japanese = next(lang for lang in catalog["languages"] if lang["language_id"] == "ja")
    expected_ids = [entry["entry_id"] for entry in japanese["entries"]]
    entries = translation["entries"]
    if translation["scope"] != {
        "source_language": "ja", "target_language": "ko", "entry_count": len(expected_ids)
    }:
        raise NavigationTextError("translation scope mismatch")
    if len(entries) != len(expected_ids):
        raise NavigationTextError("translation entry count mismatch")
    allowed_status = {"untranslated", "in_progress", "needs_review", "needs_human_review", "complete"}
    for index, (entry, expected_id) in enumerate(zip(entries, expected_ids)):
        expected_fields = {"entry_id", "ko", "status", "notes", "flags"}
        if set(entry) != expected_fields:
            raise NavigationTextError(f"translation entry fields mismatch at {index}")
        if entry["entry_id"] != expected_id:
            raise NavigationTextError(f"translation entry id mismatch at {index}")
        if not isinstance(entry["ko"], str) or entry["status"] not in allowed_status:
            raise NavigationTextError(f"invalid translation value at {expected_id}")
        if entry["notes"] is not None and not isinstance(entry["notes"], str):
            raise NavigationTextError(f"invalid notes at {expected_id}")
        if not isinstance(entry["flags"], list) or any(not isinstance(v, str) for v in entry["flags"]):
            raise NavigationTextError(f"invalid flags at {expected_id}")
    return {"status": "pass", "entries": len(entries), "source_catalog_sha256": catalog_hash}


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def init_translation(catalog: dict):
    if TRANSLATION_PATH.exists():
        raise NavigationTextError(f"refusing to overwrite translation asset: {TRANSLATION_PATH}")
    catalog_bytes = CATALOG_PATH.read_bytes()
    japanese = next(lang for lang in catalog["languages"] if lang["language_id"] == "ja")
    translation = {
        "schema_version": 1,
        "translation_id": "fusion_jp_navigation_ko",
        "source_catalog": "workspace/text/source/navigation_text.json",
        "source_catalog_sha256": sha256(catalog_bytes),
        "scope": {"source_language": "ja", "target_language": "ko", "entry_count": len(japanese["entries"])},
        "entries": [
            {"entry_id": entry["entry_id"], "ko": "", "status": "untranslated", "notes": None, "flags": []}
            for entry in japanese["entries"]
        ],
    }
    write_json(TRANSLATION_PATH, translation)


def rebind_translation(catalog: dict):
    if not TRANSLATION_PATH.exists():
        raise NavigationTextError(f"translation asset does not exist: {TRANSLATION_PATH}")
    translation = json.loads(TRANSLATION_PATH.read_text(encoding="utf-8"))
    japanese = next(lang for lang in catalog["languages"] if lang["language_id"] == "ja")
    expected_ids = [entry["entry_id"] for entry in japanese["entries"]]
    actual_ids = [entry.get("entry_id") for entry in translation.get("entries", [])]
    if actual_ids != expected_ids:
        raise NavigationTextError("refusing to rebind translation with a changed entry population")
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
    except (NavigationTextError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"navigation text error: {exc}")
