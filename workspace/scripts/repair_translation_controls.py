"""Apply narrowly-scoped control-code repairs to the translation CSV."""
from __future__ import annotations

import csv
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT / "workspace/text/review/metroid_fusion_translation_ko_english_controlcodes_fixed.csv"
ENTRY_ID = "navigation/ja/050"
OLD = "{ctrl:E200}알겠습니다.{ctrl:FD00}{ctrl:E202}통신 종료.{end}"
NEW = "{ctrl:E200}알겠습니다.{ctrl:FD00}통신 종료.{end}"


def main() -> int:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not fieldnames:
        raise SystemExit("translation CSV has no header")

    matches = [row for row in rows if row["entry_id"] == ENTRY_ID]
    if len(matches) != 1:
        raise SystemExit(f"expected one {ENTRY_ID} row, found {len(matches)}")
    text = matches[0]["한국어_번역"]
    if text.count(OLD) != 1:
        raise SystemExit(f"expected control-code sequence not found in {ENTRY_ID}")
    matches[0]["한국어_번역"] = text.replace(OLD, NEW)

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"repaired {ENTRY_ID}: removed extra ctrl:E202 before 통신 종료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
