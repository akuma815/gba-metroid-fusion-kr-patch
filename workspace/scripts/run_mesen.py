"""Mesen 2 GBA 헤드리스 실행 러너.

공백 없는 임시 경로에 ROM과 Lua를 배치해 Mesen의 --testRunner를 실행한다.
원본 ROM은 읽기 전용 입력으로만 사용한다.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MESEN = Path(r"H:\Mesen\Mesen.exe")
PROJECT = Path(__file__).resolve().parents[2]


def lua_table(shots):
    items = ", ".join(
        "{frame=%d, name=%s}" % (s["frame"], json.dumps(s["name"]))
        for s in shots
    )
    return "{" + items + "}"


def run(
    rom: Path, template: Path, out_dir: Path, shots, timeout=300,
    state_path: Path | None = None, sram_path: Path | None = None,
    watch_start: int = 0x6C0E94, watch_end: int = 0x6C0EB7,
):
    if not MESEN.is_file():
        raise SystemExit(f"Mesen.exe 없음: {MESEN}")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="mf_mesen_"))
    temp_stem = f"codex_mf_clean_{tmp.name.removeprefix('mf_mesen_')}"
    mesen_save = MESEN.parent / "Saves" / f"{temp_stem}.sav"
    try:
        # A fixed rom.gba name reuses H:/Mesen/Saves/rom.sav and silently turns
        # a nominal clean-boot test into a persisted-SRAM test. Use a unique
        # basename and remove only the save created for this runner invocation.
        rom_tmp = tmp / f"{temp_stem}.gba"
        shutil.copy2(rom, rom_tmp)
        if sram_path is not None:
            if not sram_path.is_file():
                raise SystemExit(f"SRAM file not found: {sram_path}")
            shutil.copy2(sram_path, mesen_save)
        script = template.read_text(encoding="utf-8")
        script = script.replace("@@OUT_DIR@@", str(out_dir).replace("\\", "/"))
        script = script.replace("@@SHOTS@@", lua_table(shots))
        script = script.replace("@@WATCH_START@@", f"0x{watch_start:X}")
        script = script.replace("@@WATCH_END@@", f"0x{watch_end:X}")
        if state_path is not None:
            script = script.replace("@@STATE_PATH@@", str(state_path.resolve()).replace("\\", "/"))
        script_tmp = tmp / "script.lua"
        script_tmp.write_text(script, encoding="utf-8")
        cmd = [str(MESEN), "--testRunner", str(script_tmp), str(rom_tmp), "--enableStdout"]
        print("run:", " ".join(cmd))
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        print("exit:", proc.returncode)
        if proc.stdout:
            print(proc.stdout[-6000:])
        if proc.stderr:
            print("--- stderr ---")
            print(proc.stderr[-3000:])
        return proc.returncode
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        mesen_save.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=str(PROJECT / "original" / "Metroid Fusion (Japan).gba"))
    ap.add_argument("--template", default=str(PROJECT / "workspace" / "tests" / "boot_capture.lua"))
    ap.add_argument("--out", default=str(PROJECT / "qa" / "screenshots" / "baseline"))
    ap.add_argument("--frames", default="120,300,600,900,1200")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--state")
    ap.add_argument("--sram")
    ap.add_argument("--watch-start", type=lambda value: int(value, 0), default=0x6C0E94)
    ap.add_argument("--watch-end", type=lambda value: int(value, 0), default=0x6C0EB7)
    args = ap.parse_args()
    shots = [{"frame": int(f), "name": "f"} for f in args.frames.split(",")]
    state_path = Path(args.state) if args.state else None
    sram_path = Path(args.sram) if args.sram else None
    sys.exit(run(
        Path(args.rom), Path(args.template), Path(args.out), shots,
        args.timeout, state_path, sram_path, args.watch_start, args.watch_end,
    ))


if __name__ == "__main__":
    main()
