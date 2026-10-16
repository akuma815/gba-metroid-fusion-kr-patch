"""Fusion JP 불변 원본 기반 Expected Write 빌더."""
from __future__ import annotations

import hashlib
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
SOURCE_ROM = PROJECT / "original" / "Metroid Fusion (Japan).gba"
SOURCE_SHA256 = "11c3ed10fa89d2644ea4d8e97380aa520a268340934b91883602cea668737e48"
ROM_SIZE = 8388608


class BuildError(Exception):
    pass


def load_source() -> bytes:
    data = SOURCE_ROM.read_bytes()
    if len(data) != ROM_SIZE:
        raise BuildError(f"ROM size {len(data)} != {ROM_SIZE}")
    got = hashlib.sha256(data).hexdigest()
    if got != SOURCE_SHA256:
        raise BuildError(f"unsupported source SHA-256={got}")
    return data


class RomBuilder:
    def __init__(self):
        self.source = load_source()
        self.buf = bytearray(self.source)
        self.writers: dict[int, str] = {}
        self.changes: list[tuple[int, int, str]] = []

    def write(self, offset: int, new: bytes, expected: bytes, who: str):
        end = offset + len(new)
        if offset < 0 or end > ROM_SIZE:
            raise BuildError(f"[{who}] out of range 0x{offset:X}+{len(new)}")
        actual = self.source[offset:end]
        if actual != expected:
            raise BuildError(f"[{who}] Expected Write mismatch @0x{offset:X}")
        for pos in range(offset, end):
            previous = self.writers.get(pos)
            if previous is not None and previous != who:
                raise BuildError(f"writer collision @0x{pos:X}: {previous} vs {who}")
            self.writers[pos] = who
        self.buf[offset:end] = new
        self.changes.append((offset, len(new), who))

    def verify(self):
        undeclared = [i for i, (a, b) in enumerate(zip(self.source, self.buf))
                      if a != b and i not in self.writers]
        if undeclared:
            raise BuildError(f"undeclared diff at 0x{undeclared[0]:X}")

    def save(self, path: Path):
        self.verify()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.buf)

    def summary(self):
        changed = sum(self.source[i] != self.buf[i] for i in self.writers)
        lines = [f"declared writes={len(self.changes)}, changed bytes={changed}"]
        lines.extend(f"  0x{off:06X} +{size:<4d} {who}" for off, size, who in self.changes)
        lines.append("SHA-256: " + hashlib.sha256(self.buf).hexdigest())
        return "\n".join(lines)
