"""공식 영어 대본을 바탕으로 검토 CSV에 기계 초벌 번역을 채운다.

Google의 공개 번역 엔드포인트는 초벌 생성에만 사용한다. 결과는 반드시
needs_review 상태로 남기며 빌드용 JSON에는 이 스크립트가 손대지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rombuild import PROJECT

CSV_PATH = PROJECT / "workspace" / "text" / "review" / "metroid_fusion_translation_review.csv"
TERMS_PATH = PROJECT / "workspace" / "text" / "context" / "terminology_ko.json"
CACHE_PATH = PROJECT / "workspace" / "text" / "review" / ".draft_translation_cache.json"

NO_REFERENCE = "※ 공식 영어 대응 항목 없음"
TOKEN_RE = re.compile(r"⟦[^⟧]+⟧|【[^】]+】")
TERM_MARKER_RE = re.compile(r"ZXTERM\d{4}Z")

MANUAL_OVERRIDES = {
    "file_select/ja/011": "스타트 버튼을 눌러 주세요{end}",
    "file_select/ja/012": "다시 도전하시겠습니까?{end}",
    "file_select/ja/013": "다시 도전{end}",
    "file_select/ja/014": "예 (게임으로 돌아가기){end}",
    "file_select/ja/015": "아니요 (타이틀로 돌아가기){end}",
    "file_select/ja/016": "클리어 타임{end}",
    "file_select/ja/017": "아이템 회수율 {glyph:041F}{glyph:041F}%{end}",
    "file_select/ja/018": "다음 임무에서 다시 만나자.{end}",
    "file_select/ja/019": "임무 완료.{end}",
    "file_select/ja/020": "모든 저장 데이터를{end}",
    "file_select/ja/021": "삭제하시겠습니까?{end}",
    "file_select/ja/022": "정말 모든 저장 데이터를{end}",
    "file_select/ja/023": "삭제하시겠습니까?{end}",
    "file_select/ja/024": "계속{br}처음부터{end}",
    "file_select/ja/025": "문자 표시{br}히라가나 (큰 글자){br}한자 (작은 글자){end}",
    "file_select/ja/026": "난이도{br}EASY{br}NORMAL{end}",
    "file_select/ja/027": "난이도{br}EASY{br}NORMAL{br}HARD{end}",
    "file_select/ja/028": "※ 일본어 글리프 원문 해독 후 번역 필요{end}",
}

SPEAKER_TO_CONTROL = {
    "ADAM 컴퓨터(추정)": "{ctrl:E200}",
    "사무스(추정)": "{ctrl:E201}",
    "연방 본부(추정)": "{ctrl:E202}",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def protect_terms(text: str, terms: list[dict]) -> tuple[str, dict[str, str]]:
    """용어를 불투명 표식으로 바꿔 번역기가 표기를 바꾸지 못하게 한다."""
    replacements: dict[str, str] = {}
    for term in sorted(terms, key=lambda item: len(item["en"]), reverse=True):
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term["en"]) + r"(?![A-Za-z0-9])", re.I)

        def replace(_match: re.Match[str], ko=term["ko"]) -> str:
            marker = f"ZXTERM{len(replacements):04d}Z"
            replacements[marker] = ko
            return marker

        text = pattern.sub(replace, text)
    return text, replacements


def translate_google(text: str) -> str:
    query = urllib.parse.urlencode({
        "client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": text,
    })
    request = urllib.request.Request(
        "https://translate.googleapis.com/translate_a/single?" + query,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return "".join(part[0] for part in payload[0] if part and part[0])


def translate_with_retry(text: str) -> str:
    last_error = None
    for attempt in range(5):
        try:
            return translate_google(text)
        except Exception as exc:  # network retry boundary
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"translation request failed: {last_error}")


def translate_term_safe(text: str, terms: list[dict], cache: dict[str, str]) -> str:
    protected, replacements = protect_terms(text, terms)
    for attempt in range(5):
        translated = cache.get(protected)
        if translated is None or attempt:
            translated = translate_with_retry(protected)
            cache[protected] = translated
        if sorted(TERM_MARKER_RE.findall(translated)) == sorted(replacements):
            for marker, ko in replacements.items():
                translated = translated.replace(marker, ko)
            return translated
        cache.pop(protected, None)
    raise RuntimeError("terminology marker was not preserved")


def restore(text: str) -> str:
    text = text.replace("↵", "{br}")
    text = text.replace("⟦PAGE⟧", "{ctrl:FD00}")
    text = re.sub(r"⟦CTRL:([0-9A-F]{4})⟧", r"{ctrl:\1}", text)
    text = re.sub(r"⟦G:([0-9A-F]{4})⟧", r"{glyph:\1}", text)
    for speaker, control in SPEAKER_TO_CONTROL.items():
        text = text.replace(f"【{speaker}】", control)
    # 기계 번역이 제어 코드 주변에 삽입한 공백만 정리한다.
    text = re.sub(r"\s+(?=\{(?:br|ctrl:|glyph:|end))", "", text)
    text = re.sub(r"(?<=\})\s+", "", text)
    return text.strip() + ("" if text.rstrip().endswith("{end}") else "{end}")


def draft(reference: str, terms: list[dict], cache: dict[str, str]) -> str:
    # 제어 토큰은 외부 번역기에 보내지 않는다. 토큰 사이의 문장만 번역하면
    # 번역기가 토큰을 누락하거나 순서를 바꿀 가능성을 원천 차단할 수 있다.
    # 원문 줄바꿈은 영어 조판 정보이므로 문맥 번역 단계에서는 공백으로 합친다.
    # 페이지/화자/연출 코드는 경계로 보존한다.
    reference = reference.replace("↵", " ")
    parts = TOKEN_RE.split(reference)
    tokens = TOKEN_RE.findall(reference)
    output: list[str] = []
    for index, part in enumerate(parts):
        if part.strip():
            output.append(translate_term_safe(part, terms, cache))
        else:
            output.append(part)
        if index < len(tokens):
            output.append(tokens[index])
    return restore("".join(output))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    headers, rows = read_rows(args.csv)
    terms = load_json(TERMS_PATH)["terms"]
    cache = load_json(CACHE_PATH) if CACHE_PATH.exists() else {}
    pending: set[str] = set()
    for row in rows:
        reference = row["공식_영어_참고문"]
        if reference == NO_REFERENCE:
            continue
        for part in TOKEN_RE.split(reference):
            if part.strip():
                protected, _ = protect_terms(part.replace("↵", " "), terms)
                if protected not in cache:
                    pending.add(protected)
    if pending:
        print(f"prefetching {len(pending)} text segments", flush=True)
        completed = 0
        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(translate_with_retry, text): text for text in pending}
            for future in as_completed(futures):
                source = futures[future]
                cache[source] = future.result()
                completed += 1
                if completed % 100 == 0:
                    save_json(CACHE_PATH, cache)
                    print(f"translated segments {completed}/{len(pending)}", flush=True)
        save_json(CACHE_PATH, cache)
    updated = 0
    for row in rows:
        if args.limit is not None and updated >= args.limit:
            break
        entry_id = row["entry_id"]
        if entry_id in MANUAL_OVERRIDES:
            translated = MANUAL_OVERRIDES[entry_id]
            note = "영어 대응 행 부재; 화면 문자열 경계 재확인 필요"
            status = "needs_human_review"
        else:
            reference = row["공식_영어_참고문"]
            if reference == NO_REFERENCE:
                continue
            translated = draft(reference, terms, cache)
            note = "공식 영어 대본 기준 기계 초벌; 일본어 의미·말투·줄바꿈 검수 필요"
            status = "needs_review"
        row["한국어_번역"] = translated
        row["상태"] = status
        row["메모"] = note
        updated += 1
        if updated % 25 == 0:
            save_json(CACHE_PATH, cache)
            print(f"drafted {updated}/{len(rows)}")
    save_json(CACHE_PATH, cache)
    write_rows(args.csv, headers, rows)
    print(json.dumps({"status": "pass", "updated": updated, "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
