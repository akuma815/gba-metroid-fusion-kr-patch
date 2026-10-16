# 번역 검토 CSV 사용법

`metroid_fusion_translation_review.csv`는 세 번역 JSON을 한 표로 모은 사람 검토용 편집 화면이다. 현재 349행에는 공식 영어 대본 기준 초벌 번역이 들어 있으며, 빌드 기준 SSOT는 여전히 기존 JSON이다. 사람 승인 전에는 CSV를 JSON으로 가져오지 않는다.

## 열 의미

- 보호 열: `entry_id`, `구분`, `번호`, `화자`, `화자_근거`, `일본어_원문_코드`, `공식_영어_원문_코드`, `공식_영어_참고문`, `번역_기준`, `플래그`, `ROM_오프셋`, `원문_바이트수`
- 편집 가능 열: `한국어_번역`, `상태`, `메모`
- `↵`는 표시 줄바꿈, `⟦PAGE⟧`는 페이지 구분이다. 한국어 번역에는 빌드용 실제 토큰인 `{br}`, `{end}` 등을 사용한다.
- 상태 허용값: `untranslated`, `in_progress`, `needs_review`, `needs_human_review`, `complete`

일본어 문자표가 아직 해독되지 않았으므로 일본어 원문은 가역 글리프 코드로 보존한다. 초벌의 주 기준은 같은 인덱스의 ROM 내장 공식 영어다. `공식_영어_원문_코드`는 제어 토큰까지 포함한 실제 기준선이고, `공식_영어_참고문`은 사람이 읽기 쉽게 줄바꿈·페이지·화자 토큰을 표시용으로 바꾼 열이다. 두 열의 제어 코드 표현이 달라 보여도 원본 손실이 아니다.

`번역_기준`은 행별 출처를 명시한다. 345행은 ROM 내장 공식 영어, 일본어 전용 파일 선택 3행은 일본어 글리프와 닌텐도 공식 일본어 설명서, 나머지 1행은 일본어 글리프 문자표 해독이 필요한 미확정 항목이다.

검증기는 영어 대응 345행에서 의미 제어 토큰을 한국어와 대조한다. `{br}`은 한국어 조판에 맞게 이동할 수 있고, `8100~8106`은 영어 강조 범위이며, `{glyph:0400}`, `{glyph:041F}`, `{glyph:0311}`은 각각 표시용 공백·물음표·따옴표로 변환될 수 있어 비교에서 제외한다. 그 밖의 페이지·이벤트·화자·버튼 토큰은 누락·추가를 허용하지 않는다.

화자는 독백·시스템·UI 모집단은 기능으로 확인했고, 내비게이션 대화는 `workspace/config/speaker_context.json`의 근거를 따른다. `E200~E202` 전환과 기본 ADAM 표시는 공식 영어 대조에 따른 추정이므로 런타임 제어 의미가 확정되기 전에는 번역 적격 근거로 단독 사용하지 않는다.

## 명령

```powershell
# CSV 편집 내용을 세 JSON에 반영하고 원본 JSON을 backups/translation_csv/에 자동 백업
python -X utf8 .\workspace\scripts\translation_csv.py import

# 보호 열·행 수·상태·UTF-8 BOM 검증. 초벌이 JSON보다 앞서 있어도 통과
python -X utf8 .\workspace\scripts\translation_csv.py verify

# 사람 승인 후 CSV가 빌드 JSON과 완전히 동기화됐는지 엄격 검사
python -X utf8 .\workspace\scripts\translation_csv.py verify --require-synced

# JSON에서 CSV를 다시 생성. 기존 CSV 편집을 덮으므로 의도할 때만 --force 사용
python -X utf8 .\workspace\scripts\translation_csv.py export --force
```

CSV는 Excel 한글 호환을 위해 UTF-8 BOM으로 저장된다. 보호 열이 바뀌거나 행이 누락·중복되면 가져오기를 거부한다.
