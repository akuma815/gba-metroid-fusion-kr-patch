"""Mesen Lua 프로브 실행기. MAX_FRAME과 출력 경로를 치환한다."""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MESEN = Path(r"H:\Mesen\Mesen.exe")
PROJECT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=str(PROJECT / "original" / "Metroid Fusion (Japan).gba"))
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", default=str(PROJECT / "qa" / "logs"))
    ap.add_argument("--frames", type=int, default=1200)
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="mf_probe_"))
    try:
        rom_tmp = tmp / "rom.gba"
        shutil.copy2(Path(args.rom), rom_tmp)
        src = Path(args.script).read_text(encoding="utf-8")
        src = src.replace("@@OUT_DIR@@", str(out).replace("\\", "/"))
        src = src.replace("@@MAX_FRAME@@", str(args.frames))
        script_tmp = tmp / "probe.lua"
        script_tmp.write_text(src, encoding="utf-8")
        cmd = [str(MESEN), "--testRunner", str(script_tmp), str(rom_tmp), "--enableStdout"]
        print("run:", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
        print("exit:", proc.returncode)
        if proc.stdout:
            print(proc.stdout[-8000:])
        if proc.stderr:
            print("--- stderr ---")
            print(proc.stderr[-3000:])
        sys.exit(proc.returncode)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
