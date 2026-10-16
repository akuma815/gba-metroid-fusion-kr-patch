"""Encode the approved Korean corpus and build deterministic 9x12 font writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import translation_csv as tc
from font_codec import encode_fullwidth, glyph_offsets
from hangul_glyph import outline, render_sheet_bitmap
from navigation_text import REVERSE_CHARACTERS, TOKEN_RE
from rombuild import PROJECT, load_source

CODE_MAP_PATH = PROJECT / "workspace" / "config" / "hangul_code_map.json"
FONT_PROFILE_PATH = PROJECT / "workspace" / "config" / "font_profile.json"
OUTPUT_PATH = PROJECT / "workspace" / "analysis" / "korean_font_payload.json"


class KoreanCodecError(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def character_map(code_map: dict) -> dict[str, int | tuple[int, ...]]:
    result = dict(REVERSE_CHARACTERS)
    for item in code_map["mappings"]:
        char = item["character"]
        code = int(item["code"], 0)
        if char in result or code in result.values():
            raise KoreanCodecError(f"duplicate character/code mapping: {char} 0x{code:04X}")
        result[char] = code
    for raw_unicode, raw_code in code_map["policy"]["curly_quote_aliases"].items():
        result[chr(int(raw_unicode.removeprefix("U+"), 16))] = int(raw_code, 0)
    for raw_unicode, replacement in code_map["policy"].get("literal_sequence_aliases", {}).items():
        try:
            result[chr(int(raw_unicode.removeprefix("U+"), 16))] = tuple(
                REVERSE_CHARACTERS[char] for char in replacement
            )
        except KeyError as exc:
            raise KoreanCodecError(f"literal alias uses unmapped ASCII: {replacement!r}") from exc
    return result


def encode_korean(text: str, mapping: dict[str, int | tuple[int, ...]]) -> list[int]:
    units: list[int] = []
    pos = 0
    while pos < len(text):
        if text[pos] == "{":
            match = TOKEN_RE.match(text, pos)
            if not match:
                raise KoreanCodecError(f"invalid token at character {pos}: {text[pos:pos + 20]!r}")
            kind, raw = match.groups()
            if kind == "br":
                units.append(0xFE00)
            elif kind == "end":
                units.append(0xFF00)
            else:
                if raw is None:
                    raise KoreanCodecError(f"{kind} token requires a value")
                value = int(raw, 16)
                if kind == "ctrl" and value < 0x8000:
                    raise KoreanCodecError(f"control-domain mismatch: {raw}")
                if kind == "glyph" and value >= 0x8000:
                    raise KoreanCodecError(f"glyph-domain mismatch: {raw}")
                units.append(value)
            pos = match.end()
            continue
        value = mapping.get(text[pos])
        if value is None:
            raise KoreanCodecError(f"unmapped literal at {pos}: {text[pos]!r}")
        if isinstance(value, tuple):
            units.extend(value)
        else:
            units.append(value)
        pos += 1
    if not units or units[-1] != 0xFF00:
        raise KoreanCodecError("encoded string does not end with 0xFF00")
    return units


def serialize(units: list[int]) -> bytes:
    return struct.pack(f"<{len(units)}H", *units)


def font_writes(rom: bytes, code_map: dict, profile: dict) -> list[dict]:
    font = profile["font"]
    raster = profile["raster"]
    if font["sha256"] != "07A9617723AA4EDBFB18442DB86419C3F2B48E4F7C6E2E33229305ADCA582AA1":
        raise KoreanCodecError("unexpected bitmap font identity")
    if raster["source_cell_px"] != [9, 12] or raster["placement_px"] != [1, 1]:
        raise KoreanCodecError("unsupported bitmap raster geometry")
    if raster["advance_px"] != 12:
        raise KoreanCodecError("unsupported Korean advance")
    png = Path(font["file"]).name
    writes = []
    owners: dict[int, str] = {}
    for item in code_map["mappings"]:
        char = item["character"]
        code = int(item["code"], 0)
        rows = render_sheet_bitmap(char, png, tuple(raster["cell_px"]), tuple(raster["placement_px"]))
        encoded = encode_fullwidth(outline(rows, raster["body_palette_index"], raster["outline_palette_index"]))
        offsets = glyph_offsets(code)
        for part in ("left_top", "right_top", "left_bottom", "right_bottom"):
            offset = offsets[part]
            if offset in owners:
                raise KoreanCodecError(f"font tile collision at 0x{offset:X}")
            owners[offset] = char
            new = encoded[part]
            expected = rom[offset:offset + 32]
            if len(expected) != 32:
                raise KoreanCodecError(f"font tile outside source ROM: 0x{offset:X}")
            writes.append({
                "character": char,
                "code": f"0x{code:04X}",
                "part": part,
                "offset": f"0x{offset:06X}",
                "expected_sha256": hashlib.sha256(expected).hexdigest().upper(),
                "new_sha256": hashlib.sha256(new).hexdigest().upper(),
                "new_hex": new.hex().upper(),
            })
    return writes


def build_report(rom: bytes, code_map: dict, profile: dict) -> dict:
    mapping = character_map(code_map)
    rows = tc.build_rows()
    encoded = []
    quote_alias_occurrences = 0
    for row in rows:
        text = row["한국어_번역"]
        quote_alias_occurrences += text.count("‘") + text.count("’")
        raw = serialize(encode_korean(text, mapping))
        encoded.append((row["entry_id"], raw))
    writes = font_writes(rom, code_map, profile)
    digest = hashlib.sha256()
    for item in writes:
        digest.update(int(item["offset"], 0).to_bytes(4, "little"))
        digest.update(bytes.fromhex(item["new_hex"]))
    changed_tiles = sum(item["expected_sha256"] != item["new_sha256"] for item in writes)
    return {
        "schema_version": 1,
        "report_id": "fusion_ko_bitmap_font_payload",
        "source": {
            "code_map": "workspace/config/hangul_code_map.json",
            "code_map_sha256": sha256(CODE_MAP_PATH),
            "font_profile": "workspace/config/font_profile.json",
            "font_profile_sha256": sha256(FONT_PROFILE_PATH),
        },
        "encoding": {
            "entry_count": len(encoded),
            "serialized_bytes": sum(len(raw) for _, raw in encoded),
            "all_terminated_ff00": all(raw.endswith(b"\x00\xFF") for _, raw in encoded),
            "unmapped_literals": 0,
            "curly_quote_alias_occurrences": quote_alias_occurrences,
            "curly_quote_target_code": "0x0047",
            "encoded_corpus_sha256": hashlib.sha256(
                b"".join(entry_id.encode("ascii") + b"\0" + raw for entry_id, raw in encoded)
            ).hexdigest().upper(),
        },
        "font_payload": {
            "source_bitmap": "Font/Galmuri11-Condensed_9x12.png",
            "mapped_glyphs": len(code_map["mappings"]),
            "tile_writes": len(writes),
            "changed_tiles": changed_tiles,
            "byte_identical_tiles": len(writes) - changed_tiles,
            "bytes_per_tile": 32,
            "payload_record_sha256": digest.hexdigest().upper(),
            "minimum_offset": min(item["offset"] for item in writes),
            "maximum_end_exclusive": f"0x{max(int(item['offset'], 0) + 32 for item in writes):06X}",
            "writes": writes,
        },
        "result": "static_encoding_and_font_payload_pass_runtime_pending",
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "verify"))
    args = parser.parse_args()
    report = build_report(load_source(), load_json(CODE_MAP_PATH), load_json(FONT_PROFILE_PATH))
    if args.command == "generate":
        write_json(OUTPUT_PATH, report)
    else:
        if not OUTPUT_PATH.exists() or load_json(OUTPUT_PATH) != report:
            raise KoreanCodecError("Korean font payload report is missing or stale")
    print(json.dumps({
        "status": "pass",
        "command": args.command,
        "entries": report["encoding"]["entry_count"],
        "serialized_bytes": report["encoding"]["serialized_bytes"],
        "mapped_glyphs": report["font_payload"]["mapped_glyphs"],
        "tile_writes": report["font_payload"]["tile_writes"],
        "result": report["result"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
