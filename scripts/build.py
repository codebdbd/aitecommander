"""Build script for Aite Commander.

Produces a one-folder (onedir) distribution bundle using aitecommander.spec,
ready for packaging with Inno Setup (installer/AiteCommander.iss).

Usage:
    python scripts/build.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"


import stat
import time


def _remove_dir_robust(path: Path) -> None:
    if not path.exists():
        return
    for _ in range(5):
        try:
            for p in path.glob("**/*"):
                try:
                    p.chmod(stat.S_IWRITE)
                except Exception:
                    pass
            shutil.rmtree(path, ignore_errors=False)
            break
        except Exception:
            time.sleep(0.5)


def clean() -> None:
    targets = [BUILD, DIST / "AiteCommander", DIST / "AiteCommander.exe"]
    for d in targets:
        if d.exists():
            if d.is_dir():
                _remove_dir_robust(d)
            else:
                d.unlink(missing_ok=True)
            print(f"  removed {d}")


def build(onefile: bool = False) -> None:
    # When using a .spec file, only --noconfirm is needed (--clean conflicts with Windows async directory deletion)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        str(ROOT / "aitecommander.spec"),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\nBuild FAILED (exit code {result.returncode})")
        sys.exit(result.returncode)

    folder = DIST / "AiteCommander"
    print(f"\nBuild OK: {folder}")


def main() -> None:
    print("Building Aite Commander (one-folder distribution for installer)...")
    clean()
    build()


if __name__ == "__main__":
    main()
