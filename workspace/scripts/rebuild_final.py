"""Restore the released v1.0 from Git, the original ROM and two font sheets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = '11c3ed10fa89d2644ea4d8e97380aa520a268340934b91883602cea668737e48'
FINAL = '9f81749177e34ba1f62ae29d5dd13d57ab274850c70e230604325c626aaad2be'
FONTS = {
    'Galmuri11-Condensed_9x12.png': '07a9617723aa4edbfb18442db86419c3f2b48e4f7c6e2e33229305adca582aa1',
    'Galmuri7_8x8.png': 'a2be473e22a62942164c95db60f3f5aa88a99f76b525994d194e9f5f9df387ea',
}
CSV = 'metroid_fusion_translation_ko_english_controlcodes_fixed.csv'

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def require(value, message):
    if not value:
        raise RuntimeError(message)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-rom', required=True, type=Path)
    p.add_argument('--font-dir', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    a = p.parse_args()
    require(a.source_rom.stat().st_size == 8388608 and sha(a.source_rom) == SOURCE, 'Unsupported original ROM')
    for name, digest in FONTS.items():
        require(sha(a.font_dir / name) == digest, 'Font sheet differs: ' + name)
    require(sha(ROOT / 'workspace/text/review' / CSV) == '1a688d4874b24713c4921c05404cd85b383b3b6371f11eba1fcd3a245138f1cb', 'Final translation CSV differs')
    require(not a.output_dir.resolve().is_relative_to((ROOT / 'workspace').resolve()), 'Output must be outside workspace')
    a.output_dir.mkdir(parents=True, exist_ok=False)
    out = a.output_dir.resolve()
    project = out / 'project'
    for name in ['scripts', 'config', 'text/translation']:
        shutil.copytree(ROOT / 'workspace' / name, project / 'workspace' / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    review = project / 'workspace/text/review'
    review.mkdir(parents=True)
    shutil.copy2(ROOT / 'workspace/text/review' / CSV, review / CSV)
    logo = project / 'workspace/graphics/source/approved_title_logo.png'
    logo.parent.mkdir(parents=True)
    shutil.copy2(ROOT / 'workspace/graphics/source/approved_title_logo.png', logo)
    os.environ.update(MF_SOURCE_ROM=str(a.source_rom.resolve()), MF_FONT_DIR=str(a.font_dir.resolve()), PYTHONDONTWRITEBYTECODE='1')
    scripts = project / 'workspace/scripts'
    for script, command in [('navigation_text.py', 'extract'), ('additional_text.py', 'extract'),
                            ('file_select_text.py', 'extract'), ('text_code_usage.py', 'build'),
                            ('translation_corpus.py', 'generate'), ('korean_codec.py', 'generate')]:
        subprocess.run([sys.executable, '-X', 'utf8', '-B', str(scripts / script), command], cwd=project, check=True)
    sys.path.insert(0, str(scripts))
    import text_centering
    report = text_centering.run(text_centering.DEFAULT_CSV, False)
    text_centering.REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    subprocess.run([sys.executable, '-X', 'utf8', '-B', str(scripts / 'build_korean_rom.py'), 'build', '--release-v1-0'], cwd=project, check=True)
    built = project / 'build/metroid_fusion_ko_v1_0_final.gba'
    require(built.stat().st_size == 8388608 and sha(built) == FINAL, 'Final ROM differs from v1.0')
    require(sha(a.source_rom) == SOURCE, 'Original ROM changed')
    final = out / 'MetroidFusion_KR_v1.0_Rebuilt.gba'
    shutil.copy2(built, final)
    result = {'status': 'PASS', 'finalSHA256': FINAL, 'originalUnchanged': True,
              'sourceROMRequired': True, 'externalFontSheets': list(FONTS),
              'publicReleaseRequired': False, 'privateBackupRequired': False,
              'runtime': 'not newly performed'}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
