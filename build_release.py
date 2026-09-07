"""
Assemble the portable ValorantAimCoach release.

    .venv-build/Scripts/python build_release.py

Steps:
  1. PyInstaller (aimcoach.spec) -> build/dist/ValorantAimCoach/
  2. copy vendor/ (ffmpeg + tesseract) next to the exe
  3. drop in "READ ME FIRST.txt"
  4. zip -> ValorantAimCoach-<date>.zip

The zip is what gets attached to a GitHub Release. Nothing here is committed.
"""

import datetime as _dt
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "build" / "dist" / "ValorantAimCoach"
WORK = ROOT / "build" / "work"

READ_ME = """VALORANT AIM COACH  --  read this first
=========================================

WHAT IT DOES
  Watches one of your Valorant gameplay clips, finds every moment an enemy
  first appears, measures how far your crosshair was from their head, and
  compares you to a pool of pro match VODs. You get an HTML report with
  numbers and specific advice.

HOW TO USE
  1. Unzip this whole folder somewhere (Desktop is fine).
  2. Double-click  ValorantAimCoach.exe
  3. The first time, Windows may say "Windows protected your PC".
     Click "More info" -> "Run anyway". (The app is just unsigned, not
     dangerous -- code-signing certificates cost money.)
  4. Click "Choose clip", pick a .mp4 of your gameplay.
     A Deathmatch clip works best. A full ranked match is fine too.
  5. Click "Analyze" and wait ~30-90 minutes. You can minimise it and do
     other things; just don't close it.
  6. Part way through, a small window shows you a handful of frames and
     asks "is this a real enemy?" -- click Keep or Drop for each.
  7. When it finishes, the coaching report opens in your browser. It is
     also saved as coaching_report.html in a new coach_<clipname> folder
     next to the .exe.

REQUIREMENTS
  - 64-bit Windows 10 or 11
  - ~4 GB free disk, ~4 GB RAM
  - No graphics card needed. No internet needed.

TROUBLESHOOTING
  - "0 reveals detected": the clip had little real combat, or the detector
    struggled with it. Try a Deathmatch clip.
  - Antivirus flags it: it is a PyInstaller-packed Python app, which some
    scanners dislike. Add an exception for the folder, or check the file
    on virustotal.com.
  - Anything else: the black console window shows a log -- copy that.
"""


def run_pyinstaller():
    print("== PyInstaller ==")
    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "aimcoach.spec", "--noconfirm",
         "--distpath", str(ROOT / "build" / "dist"),
         "--workpath", str(WORK)],
        cwd=ROOT,
    )


def stage_vendor():
    print("== stage vendor/ next to exe ==")
    src = ROOT / "vendor"
    dst = DIST / "vendor"
    if not src.exists():
        raise SystemExit("vendor/ missing -- run fetch_vendor first")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def stage_docs():
    (DIST / "READ ME FIRST.txt").write_text(READ_ME, encoding="utf-8")


def make_zip() -> Path:
    stamp = _dt.date.today().strftime("%Y%m%d")
    out = ROOT / f"ValorantAimCoach-{stamp}.zip"
    if out.exists():
        out.unlink()
    print(f"== zip -> {out.name} ==")
    base = DIST.parent
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in DIST.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(base))
    mb = out.stat().st_size / 1e6
    print(f"   {mb:.0f} MB")
    return out


def main():
    run_pyinstaller()
    stage_vendor()
    stage_docs()
    unpacked = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1e6
    print(f"unpacked size: {unpacked:.0f} MB")
    make_zip()
    print("\nDone. Test:  build/dist/ValorantAimCoach/ValorantAimCoach.exe --selftest")


if __name__ == "__main__":
    main()
