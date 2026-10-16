# Metroid Fusion GBA 한국어화

일본판 Game Boy Advance ROM을 기준으로 진행 중인 한국어화 프로젝트다. 기본 폰트 원천은 `Galmuri11-Condensed_9x12.png`이며, 9×12 비트맵 셀을 Fusion 본문 16×16 글리프에 배치하고 진행폭 12px로 쓰는 위치명 PoC가 Mesen 2.2.1에서 통과했다. 이전 TTF 13px 래스터 결과는 비교 이력으로만 보존한다. Navigation·메시지·지역명·독백·파일 선택 텍스트 2,411개를 가역 추출했으며 전역 코드 할당과 재삽입은 아직 조사 중이다.

## 기준 입력

- ROM: `original/Metroid Fusion (Japan).gba`
- 플랫폼/리전: Game Boy Advance / Japan
- 게임 코드: `AMTJ`
- 상세 식별 정보: [`workspace/config/source_rom.json`](workspace/config/source_rom.json)
- 폰트 프로파일: [`workspace/config/font_profile.json`](workspace/config/font_profile.json)

원본 ROM은 수정하지 않는다. 모든 추출·분석·빌드는 원본을 읽기 전용 기준 입력으로 사용하고 새 경로에 결과를 만든다.

## 폴더 역할

```text
Metroid Fusion/
├─ original/                 사용자 제공 원본 ROM
├─ extracted/                원본에서 재생성 가능한 추출 데이터
├─ workspace/
│  ├─ analysis/              ROM·텍스트·렌더러 조사 결과
│  ├─ config/                원본 식별자와 추후 빌드 설정
│  ├─ font/                  한글 폰트 소스·변환 사양·생성 글리프
│  ├─ text/
│  │  ├─ source/             가역 추출 원문
│  │  └─ translation/        한국어 번역 원장
│  ├─ asm/                   ARM/Thumb 훅·패치 소스
│  ├─ graphics/              번역용 그래픽 소스
│  ├─ scripts/               추출·삽입·빌드 도구
│  └─ tests/                 라운드트립·회귀 테스트
├─ work/                     일회성 조사·실험 공간
├─ build/                    재현 가능한 개발 빌드 산출물
├─ dist/                     배포용 패치·설명서·해시
├─ backups/                  로컬 백업
├─ qa/                       스크린샷·세이브·실행 로그
├─ tools/                    로컬 외부 도구
└─ docs/                     조사 기록과 인수인계 문서
```

## 작업 규칙

1. 원본 ROM과 이전 검증 산출물을 덮어쓰지 않는다.
2. 반복 작업은 `workspace/scripts`의 단일 빌드 경로로 승격한다.
3. ROM 변경은 대상 리비전 확인과 Expected Write 검증을 거친다.
4. 정적·빌드 검증과 에뮬레이터 실행 검증을 구분해 기록한다.
5. 작업 종료 시 최신 `docs/HANDOFF_*.md`에 변경 파일, 검증 결과, 미해결 항목, 재현 명령과 다음 단계를 반영한다.

현재 상태와 PoC 재현 방법은 [`docs/HANDOFF_2026-08-17.md`](docs/HANDOFF_2026-08-17.md)를 기준으로 한다.

번역 검토는 `workspace/text/review/metroid_fusion_translation_review.csv`에서 진행한다. 세 JSON의 349개 대상이 한 표에 정리되어 있으며 공식 영어 참고문, 한국어 번역, 화자·근거와 상태를 함께 비교할 수 있다. CSV 편집 후 다음 명령으로 보호 열을 검증하고 빌드용 JSON에 반영한다.

```powershell
python -X utf8 .\workspace\scripts\translation_csv.py import
python -X utf8 .\workspace\scripts\translation_csv.py verify
```

확정된 7개 언어 원문 추출, 코드 사용 집계와 무수정 왕복은 다음 명령으로 검증한다.

```powershell
python -X utf8 .\workspace\scripts\navigation_text.py verify
python -X utf8 .\workspace\scripts\additional_text.py verify
python -X utf8 .\workspace\scripts\file_select_text.py verify
python -X utf8 .\workspace\scripts\text_code_usage.py verify
python -X utf8 .\workspace\scripts\ui_graphics_audit.py verify
python -X utf8 .\workspace\scripts\translation_csv.py verify
python -X utf8 -m unittest discover -s .\workspace\tests -p 'test_*.py' -v
```
