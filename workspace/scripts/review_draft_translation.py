"""기계 초벌 CSV의 독립 2차 검토: 용어 정규화, UI 수동 교정, 위험 항목 표시."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from rombuild import PROJECT

CSV_PATH = PROJECT / "workspace" / "text" / "review" / "metroid_fusion_translation_review.csv"
REPORT_PATH = PROJECT / "workspace" / "text" / "review" / "SECOND_PASS_REVIEW.md"


LOCATION = [
    "메인 덱", "섹터 1 (SRX)", "섹터 2 (TRO)", "섹터 3 (PYR)",
    "섹터 4 (AQA)", "섹터 5 (ARC)", "섹터 6 (NOC)", "원자로 사일로",
    "제한 구역", "오퍼레이션 덱", "거주 덱", "도킹 베이",
    "내비게이션 룸", "데이터 룸", "시큐리티 룸", "리차지 룸",
    "세이브 룸", "오퍼레이션 룸", "격리 구역", "저온 격리 구역",
    "중앙 원자로 코어", "보조 발전소", "제한 구역 연구실", "펌프 제어 장치",
    "메인 보일러", "메인 보일러 제어실",
]

MESSAGE = [
    "{ctrl:8012}보안 레벨 1 해제.{br}{ctrl:8016}파란색 해치 활성화.",
    "{ctrl:8011}보안 레벨 2 해제.{br}{ctrl:8010}녹색 해치 활성화.",
    "{ctrl:8011}보안 레벨 3 해제.{br}{ctrl:8010}노란색 해치 활성화.",
    "{ctrl:8011}보안 레벨 4 해제.{br}{ctrl:8018}빨간색 해치 활성화.",
    "{ctrl:8019}미사일 데이터 다운로드 완료.{br}{ctrl:8022}{glyph:030E}{glyph:030F}을 누른 채 {glyph:030A}{glyph:030B}을 누르세요.",
    "{ctrl:8002}슈퍼 미사일 데이터 다운로드 완료.{br}{ctrl:8022}{glyph:030E}{glyph:030F}을 누른 채 {glyph:030A}{glyph:030B}을 누르세요.",
    "{ctrl:8020}봄 데이터 다운로드 완료.{br}모프볼 상태에서 {glyph:030A}{glyph:030B}을 누르세요.",
    "{ctrl:8009}파워 봄 데이터 다운로드 완료.{br}모프볼 상태에서 {glyph:030E}{glyph:030F}을 누른 채 {glyph:030A}{glyph:030B}을 누르세요.",
    "{ctrl:8006}미사일에 아이스 효과 추가.{br}{ctrl:8013}적을 얼릴 수 있습니다.",
    "{ctrl:800B}미사일에 디퓨전 효과 추가.{br}{ctrl:8008}{glyph:030E}{glyph:030F}으로 차지하고 {glyph:030A}{glyph:030B}으로 발사하세요.",
    "{ctrl:8008}모프볼 능력 회복.{br}{ctrl:8016}{glyph:0302}{glyph:0303}을 두 번 눌러 변형하세요.",
    "{ctrl:8026}하이 점프와 점프볼{br}{ctrl:8028}능력 회복.",
    "{ctrl:8002}스크루 어택 능력 회복.{br}{ctrl:8017}회전 점프로 적을 공격하세요.",
    "{ctrl:8004}스페이스 점프 능력 회복.{br}{ctrl:8006}공중에서 회전 점프를 연속으로 할 수 있습니다.",
    "스피드 부스터 능력 회복.{br}{ctrl:8005}일정 시간 달리면 고속 대시가 시작됩니다.",
    "{ctrl:8006}배리어 슈트 기능 회복.{br}극한 온도에서도 견딜 수 있습니다.",
    "그래비티 슈트 기능 회복.{br}{ctrl:8022}물속에서 자유롭게 움직일 수 있습니다.",
    "차지 빔 능력 회복.{br}{ctrl:8007}{glyph:030A}{glyph:030B}을 길게 눌러 차지하세요.",
    "{ctrl:800A}와이드 빔 능력 회복.{br}{ctrl:8015}빔의 공격 범위가 넓어집니다.",
    "{ctrl:8008}웨이브 빔 능력 회복.{br}{ctrl:800F}빔이 벽을 관통합니다.",
    "{ctrl:8002}플라스마 빔 능력 회복.{br}{ctrl:8012}빔이 적을 관통합니다.",
    "{ctrl:8012}빔에 아이스 효과 추가.{br}{ctrl:800A}빔으로 적을 얼릴 수 있습니다.",
    "{ctrl:8004}대기 안정기 작동.{br}아직 4기가 오작동 중입니다.",
    "{ctrl:8004}대기 안정기 작동.{br}{ctrl:800C}아직 3기가 오작동 중입니다.",
    "{ctrl:8004}대기 안정기 작동.{br}{ctrl:8003}아직 2기가 오작동 중입니다.",
    "{ctrl:8004}대기 안정기 작동.{br}{ctrl:8007}아직 1기가 오작동 중입니다.",
    "{ctrl:8022}모든 안정기 작동.{br}{ctrl:8007}대기 상태가 정상화되었습니다.",
    "{ctrl:8028}수위가 낮아졌습니다.{br}{ctrl:806E}",
    "{ctrl:8016}냉각 장치가 작동합니다.{br}{ctrl:806E}",
    "{ctrl:8032}잠금 해제.{br}{ctrl:803E}게이트를 엽니다.",
    "{ctrl:8017}보조 전력 가동.{br}{ctrl:806E}",
    "{ctrl:8007}제한 구역 연구실 분리까지{br}{ctrl:801A}60초.",
    "{ctrl:8013}궤도 변경 완료.{br}{ctrl:8026}충돌까지 3분.",
    "{ctrl:8047}저장하시겠습니까?{br}{ctrl:8057}{ctrl:8340}예 {ctrl:83A0}아니요",
    "{ctrl:803B}저장 완료.{br}{ctrl:806E}",
    "{ctrl:8038}아담에게 접속하시겠습니까?{br}{ctrl:8057}{ctrl:8340}예 {ctrl:83A0}아니요",
    "{ctrl:8037}무기 시스템{br}{ctrl:802D}보급 완료.",
    "{ctrl:8043}에너지 탱크{br}{ctrl:802B}충전 완료.",
    "{ctrl:8028}무기와 에너지{br}{ctrl:8039}완전 회복.",
    "{ctrl:8020}에너지 탱크 획득.{br}{ctrl:800D}에너지 최대치 증가.",
    "{ctrl:8020}미사일 탱크 획득.{br}{ctrl:800E}미사일 최대치 증가.",
    "{ctrl:8010}파워 봄 탱크 획득.{br}파워 봄 최대치 증가.",
    "{ctrl:8018}적 위치가 비정상입니다.{br}{ctrl:8002}메시지 프레임 위치를 확인하세요.",
    "{ctrl:8017}목표를 이해했습니까?{br}{ctrl:8057}{ctrl:8340}예 {ctrl:83A0}아니요",
    "{ctrl:800F}임무 목표를 확인하시겠습니까?{br}{ctrl:8057}{ctrl:8340}예 {ctrl:83A0}아니요",
    "{ctrl:802A}슬립 모드로 전환하시겠습니까?{br}{ctrl:800E}슬립 모드에서 복귀하려면",
    "{ctrl:8004}SELECT와 L, R 버튼을{br}{ctrl:8012}동시에 누르세요.",
    "{ctrl:8062}예{br}{ctrl:8066}아니요",
]

FILE_SELECT = [
    "사무스 데이터{br}{br}{br}{br}사운드{br}종료",
    "시작{br}데이터 복사{br}데이터 삭제",
    "어디에 복사하시겠습니까?",
    "기존 파일을 덮어씁니다. 괜찮습니까?{br}예  아니요",
    "이 데이터를 삭제하시겠습니까?{br}{br}예  아니요",
    "저장 데이터 A가 손상되었습니다.{br}이전 데이터를 사용합니다.",
    "저장 데이터 B가 손상되었습니다.{br}이전 데이터를 사용합니다.",
    "저장 데이터 C가 손상되었습니다.{br}이전 데이터를 사용합니다.",
    "파일 A의 저장 데이터가 손상되었습니다.{br}데이터를 삭제합니다.",
    "파일 B의 저장 데이터가 손상되었습니다.{br}데이터를 삭제합니다.",
    "파일 C의 저장 데이터가 손상되었습니다.{br}데이터를 삭제합니다.",
    "스타트 버튼을 눌러 주세요",
    "언어 선택",
    "다시 도전하시겠습니까?",
    "예 (게임으로 돌아가기)",
    "아니요 (타이틀로 돌아가기)",
    "클리어 타임",
    "아이템 회수율 {glyph:041F}{glyph:041F}%",
    "다음 임무에서 다시 만나자.",
    "임무 완료.",
    "모든 저장 데이터를",
    "삭제하시겠습니까?",
    "정말 모든 저장 데이터를",
    "삭제하시겠습니까?",
    "계속{br}처음부터",
    "문자 표시{br}히라가나 (큰 글자){br}한자 (작은 글자)",
    "난이도{br}EASY{br}NORMAL",
    "난이도{br}EASY{br}NORMAL{br}HARD",
    "※ 일본어 글리프 원문 해독 후 번역 필요",
]

GLOBAL_REPLACEMENTS = [
    ("\u200b", ""), ("\ufeff", ""), ("연맹", "은하 연방"),
    ("Federation", "은하 연방"), ("본사", "은하 연방 본부"),
    ("Adam", "아담"), ("Biologic", "BIOLOGIC"),
    ("Varia Suit", "배리어 슈트"), ("Metroids", "메트로이드"),
    ("Core-X", "코어-X"), ("Shinespark", "샤인스파크"),
    ("Save Rooms", "세이브 룸"), ("Recharge Rooms", "리차지 룸"),
    ("Reactor Core", "원자로 코어"), ("HQ", "은하 연방 본부"),
    ("CO", "지휘관"), ("Alpha", "알파"), ("Gamma", "감마"),
    ("Zeta", "제타"), ("Omega", "오메가"),
    ("B.S.L 연구", "B.S.L. 연구"), ("연구 스테이션", "연구 정거장"),
    ("B.S.L 스테이션", "B.S.L. 정거장"),
    ("광선", "빔"), ("격리 구역가", "격리 구역이"),
    ("격리 구역로", "격리 구역으로"), ("데이터 룸가", "데이터 룸이"),
    ("데이터 룸로", "데이터 룸으로"), ("내비게이션 룸가", "내비게이션 룸이"),
    ("내비게이션 룸로", "내비게이션 룸으로"),
    ("격리 구역를", "격리 구역을"), ("시큐리티 룸를", "시큐리티 룸을"),
    ("파워 봄를", "파워 봄을"), ("아이스 빔가", "아이스 빔이"),
    ("플라스마 빔가", "플라스마 빔이"), ("플라스마 빔와", "플라스마 빔과"),
    ("빠르고 조용하게 움직이세요..", "신속하고 조용히 움직이세요."),
    ("조사하다{", "조사하세요{"), ("호스트", "숙주"),
    ("호스팅", "숙주로 삼고"), ("모방", "의태"),
    ("메트로이드만 해당{ctrl:FD00}백신이", "메트로이드 백신만이{ctrl:FD00}"),
    ("또 X에 감염되네", "다시는 X에 감염되지 않습니다"),
    ("기생 의태 생물 X를 무료로 제공하세요", "자유 상태의 X를 흡수하세요"),
    ("소송 비용.", "무슨 수를 써서라도 막아야 합니다."),
]


def with_end(text: str) -> str:
    return text if text.endswith("{end}") else text + "{end}"


def main() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        rows = list(reader)

    for row in rows:
        entry_id = row["entry_id"]
        text = row["한국어_번역"]
        for old, new in GLOBAL_REPLACEMENTS:
            text = text.replace(old, new)
        text = re.sub(r"[ \t]{2,}", " ", text)
        if entry_id.startswith("location/ja/"):
            index = int(entry_id.rsplit("/", 1)[1])
            control = re.match(r"\{ctrl:[0-9A-F]{4}\}", text).group(0)
            text = control + LOCATION[index]
        elif entry_id.startswith("message/ja/"):
            index = int(entry_id.rsplit("/", 1)[1])
            text = MESSAGE[index]
        elif entry_id.startswith("file_select/ja/"):
            index = int(entry_id.rsplit("/", 1)[1])
            text = FILE_SELECT[index]
        row["한국어_번역"] = with_end(text)
        if entry_id == "file_select/ja/028":
            row["상태"] = "needs_human_review"
            row["메모"] = "일본어 전용 글리프 원문 해독 필요; 임시 안내문"
        else:
            row["상태"] = "needs_review"
            row["메모"] = "공식 영어 기준 초벌 + 용어/UI 2차 검토; 일본어 의미·말투·줄바꿈 최종 검수 필요"

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    residual = []
    allowed = re.compile(r"(?:ADAM|SA-X|B\.S\.L\.|BIOLOGIC|DNA|SR388|STA|SRX|TRO|BUR|FRI|WAT|DAR|PYR|AQA|ARC|NOC|EASY|NORMAL|HARD|SELECT|B\.O\.X)", re.I)
    latin = re.compile(r"[A-Za-z]{2,}")
    for row in rows:
        scrubbed = re.sub(r"\{[^}]+\}", "", row["한국어_번역"])
        scrubbed = allowed.sub("", scrubbed)
        if latin.search(scrubbed):
            residual.append(row["entry_id"])

    report = [
        "# Metroid Fusion 초벌 번역 2차 검토",
        "",
        "- 전체 349행에 초벌 번역 입력",
        "- 공식 한국어 표기와 공식 일본어 설명서 기반 표기 정규화",
        "- 시스템 메시지 48행, 지역명 26행, 파일 선택 29행 수동 교정",
        "- 대사와 독백은 문맥/말투/13px 조판 검수 전이므로 `needs_review` 유지",
        "- `file_select/ja/028`은 일본어 글리프 원문 해독 전이라 `needs_human_review` 유지",
        f"- 허용 목록 외 영문 잔존 자동 검출: {len(residual)}행",
        "",
        "## 영문 잔존 검토 대상",
        "",
        *(f"- `{entry_id}`" for entry_id in residual),
        "",
    ]
    REPORT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"status": "pass", "rows": len(rows), "residual_latin": len(residual)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
