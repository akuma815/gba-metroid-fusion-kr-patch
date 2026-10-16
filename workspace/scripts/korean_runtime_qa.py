"""Verify that recorded Mesen evidence belongs to the current Korean QA ROM."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from rombuild import PROJECT

QA_PATH = PROJECT / "workspace" / "analysis" / "korean_runtime_qa.json"


class KoreanRuntimeQaError(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def project_path(raw: str) -> Path:
    path = PROJECT / Path(raw)
    if not path.is_file():
        raise KoreanRuntimeQaError(f"missing QA artifact: {raw}")
    return path


def parse_probe(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            raise KoreanRuntimeQaError(f"malformed probe line: {line!r}")
        key, value = line.split("=", 1)
        result[key] = value
    return result


def verify(report: dict) -> dict:
    rom = project_path(report["build"]["rom"])
    build_report_path = project_path(report["build"]["report"])
    if sha256(rom) != report["build"]["rom_sha256"]:
        raise KoreanRuntimeQaError("runtime ROM hash mismatch")
    if sha256(build_report_path) != report["build"]["report_sha256"]:
        raise KoreanRuntimeQaError("static build report hash mismatch")
    build_report = json.loads(build_report_path.read_text(encoding="utf-8"))
    if build_report["output"]["rom_sha256"] != report["build"]["rom_sha256"]:
        raise KoreanRuntimeQaError("runtime/static build identity mismatch")

    screenshot_count = 0
    screenshot_items = {
        name: item
        for name, item in report["evidence"].items()
        if name.endswith("_screenshot")
    }
    if not screenshot_items:
        raise KoreanRuntimeQaError("runtime report contains no screenshots")
    for name, item in screenshot_items.items():
        path = project_path(item["path"])
        if sha256(path) != item["sha256"]:
            raise KoreanRuntimeQaError(f"screenshot hash mismatch: {name}")
        with Image.open(path) as image:
            if image.size != (240, 160) or image.format != "PNG":
                raise KoreanRuntimeQaError(f"unexpected screenshot shape: {name}")
        screenshot_count += 1

    state_count = 0
    state_items = {
        name: item
        for name, item in report["evidence"].items()
        if name.endswith("_state")
    }
    for name, item in state_items.items():
        path = project_path(item["path"])
        if sha256(path) != item["sha256"]:
            raise KoreanRuntimeQaError(f"savestate hash mismatch: {name}")
        if path.suffix.lower() != ".mss" or path.stat().st_size < 1024:
            raise KoreanRuntimeQaError(f"unexpected savestate shape: {name}")
        source_path = project_path(item["source_state"])
        if sha256(source_path) != item["source_state_sha256"]:
            raise KoreanRuntimeQaError(f"source savestate hash mismatch: {name}")
        project_path(item["route_script"])
        state_count += 1

    probe_item = report["evidence"]["runtime_probe"]
    probe_path = project_path(probe_item["log"])
    if sha256(probe_path) != probe_item["log_sha256"]:
        raise KoreanRuntimeQaError("probe log hash mismatch")
    probe = parse_probe(probe_path)
    expected = {
        "frames": f"0-{probe_item['frames']}",
        "file_select_pointer_read_addresses": str(probe_item["file_select_pointer_read_addresses"]),
        "relocated_text_read_addresses": str(probe_item["relocated_text_read_addresses"]),
        "mapped_font_read_addresses": str(probe_item["mapped_font_read_addresses"]),
    }
    for key, value in expected.items():
        if probe.get(key) != value:
            raise KoreanRuntimeQaError(f"probe value mismatch: {key}")
    if any(int(probe[key]) <= 0 for key in expected if key != "frames"):
        raise KoreanRuntimeQaError("runtime chain contains an empty evidence set")
    return {
        "status": "pass",
        "rom_sha256": report["build"]["rom_sha256"],
        "screenshots": screenshot_count,
        "savestates": state_count,
        "pointer_reads": int(probe["file_select_pointer_read_addresses"]),
        "text_reads": int(probe["relocated_text_read_addresses"]),
        "font_reads": int(probe["mapped_font_read_addresses"]),
        "overall_status": report["overall_status"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify",))
    parser.parse_args()
    report = json.loads(QA_PATH.read_text(encoding="utf-8"))
    print(json.dumps(verify(report), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
