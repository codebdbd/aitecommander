"""Build script for Aite Commander.

Usage:
    python scripts/build.py          # one-folder build (faster, debuggable)
    python scripts/build.py --onefile # single .exe (slower build, portable)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def clean() -> None:
    for d in (DIST, BUILD):
        if d.exists():
            shutil.rmtree(d)
            print(f"  removed {d}")


def build(onefile: bool = False) -> None:
    # When using a .spec file, only --noconfirm --clean are valid
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(ROOT / "aitecommander.spec"),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\nBuild FAILED (exit code {result.returncode})")
        sys.exit(result.returncode)

    if onefile:
        exe = DIST / "AiteCommander.exe"
        print(f"\nBuild OK: {exe}")
    else:
        folder = DIST / "AiteCommander"
        print(f"\nBuild OK: {folder}")


def main() -> None:
    onefile = "--onefile" in sys.argv
    print(f"Building Aite Commander ({'one-file' if onefile else 'one-folder'})...")
    clean()
    build(onefile=onefile)


if __name__ == "__main__":
    main()
