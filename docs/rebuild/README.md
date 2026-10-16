# v1.0 최종판 복원과 소스 재빌드

공개 Git 소스·지원 원본 ROM·공용 글꼴 시트 2개로 v1.0을 재현합니다. 과거 게임 폴더·개인 백업·배포 ZIP은 빌드에 필요하지 않습니다.

## 별도 입력

- 일본판 AMTJ / METROID4JPN ROM: 8,388,608바이트. SHA-256은 `INPUTS.json` 참조.
- 공용 Font 폴더의 `Galmuri11-Condensed_9x12.png`, `Galmuri7_8x8.png`. 이 시트 2개는 게임 폴더 삭제 대상에 포함하지 않습니다. TTF만으로 동일 시트를 재생성하는 절차는 검증하지 않았습니다.
- Python 3.11 이상과 `requirements-rebuild.txt`의 Pillow.

```powershell
python -m pip install -r requirements-rebuild.txt
python -X utf8 -B workspace/scripts/rebuild_final.py --source-rom "D:/ROM/Metroid Fusion (Japan).gba" --font-dir "D:/Font" --output-dir "build/restored_v1_0"
```

출력은 `<output-dir>/MetroidFusion_KR_v1.0_Rebuilt.gba`입니다. 새 출력 폴더만 사용하며 기존 출력 폴더를 거부합니다. 작업은 별도 project 스냅샷에서 수행하여 원본과 체크아웃의 번역 원장을 덮어쓰지 않습니다. 하위 스크립트에는 `MF_SOURCE_ROM`, `MF_FONT_DIR` 환경 변수로 별도 입력을 지정할 수 있습니다.

## 보완한 입력과 절차

- 누락된 최종 승인 CSV `workspace/text/review/metroid_fusion_translation_ko_english_controlcodes_fixed.csv`를 보존했습니다. 이 CSV와 현재 번역 JSON이 v1.0 빌드 입력입니다. 다른 review/readability CSV는 작업 이력·대안으로 보존했으며 자동으로 병합하거나 최종판에 적용하지 않습니다.
- 기존 타이틀 참조 이미지에서 원래 빌더가 사용하는 로고 마스크와 RGB만 `approved_title_logo.png`로 고정했습니다. 원본 배경은 ROM에서 읽고, 로고를 타일·팔레트로 변환하는 기존 경로를 사용합니다. 원본 배경이 포함된 전체 참조 PNG는 공개 입력으로 필요하지 않습니다.
- 원본에서 Navigation·추가 텍스트·파일 선택의 2,411개 원문을 다시 추출합니다. 원문 JSON과 분석 보고서는 생성물이며 저장소에 포함하지 않습니다.
- 텍스트 코드 집계·번역 코퍼스·한글 폰트 보고서·정렬 dry-run 보고서를 생성합니다. 정렬 보고서는 CSV를 수정하지 않습니다. 최종 빌더가 기존 규칙으로 실제 런타임 배치를 계산합니다.
- 349개 번역·696개 포인터·2,184개 폰트 타일과 타이틀·일시정지 UI·게임 오버 그래픽을 빌드합니다. Expected Write 및 기존 검증을 거쳐 최종 SHA-256 `9f81749177e34ba1f62ae29d5dd13d57ab274850c70e230604325c626aaad2be`와 대조합니다.

이 진입점은 고정 최종판 재현용이므로 입력 번역이 달라지면 거부합니다. 새 번역 작업은 복원한 project 사본에서 별도 후보로 진행하고 기존 하위 빌더를 사용하세요. 원본·이전 검증 결과를 덮어쓰지 않습니다.

## 검증 범위

실제 소스 재빌드와 다운로드한 v1.0의 apply.ps1 적용 결과가 동일합니다. 원문·폰트·번역 코덱·타이틀·빌드 보호 조건의 정적 검사 51개를 통과했습니다. 과거 런타임 캡처를 요구하는 game_over/runtime 테스트는 이번 재현 검사 대상에서 제외했습니다. 새로운 에뮬레이터 실행·장면·전체 플레이 검수는 수행하지 않았습니다. `VERIFICATION_2026-10-16.json`을 참고하세요.
