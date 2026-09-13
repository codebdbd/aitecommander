import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"d:\01_Codebdbd\01_projects\aitecommander")
VENV = ROOT / ".venv" / "Scripts"
PYLUPDATE = VENV / "pylupdate6.exe"

PY_FILES = sorted(ROOT.glob("app/**/*.py"))
# Avoid command line length limits by batching or feeding files in smaller chunks if needed,
# or since this is python subprocess, there is no command line length limit in Windows createprocess
# except 32767 characters, which 422 files will easily fit (each path is ~60-80 chars: 422 * 80 = 33KB, might be close)
# Let's check: 32767 limit. Let's filter out directories or use relative paths from ROOT.

RELATIVE_PY_FILES = [str(p.relative_to(ROOT)) for p in PY_FILES]

LANGS = ["en", "ru", "de", "fr", "es", "uk"]
TS_FILES = [ROOT / "i18n" / f"app_{lang}.ts" for lang in LANGS]

print(f"Found {len(RELATIVE_PY_FILES)} .py files")

errors = []
for ts in TS_FILES:
    print(f"\n--- Updating {ts.name} ---")
    cmd = [str(PYLUPDATE), "--ts", str(ts)] + RELATIVE_PY_FILES
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print(f"[FAIL] {ts.name} (exit {result.returncode})")
        errors.append(ts.name)
    else:
        print(f"[OK] {ts.name}")

# Now compile .qm files
print("\n--- Running lrelease ---")
# We know where pylupdate6 is. Let's find lrelease. It might be in site-packages/PyQt6/Qt6/bin/lrelease.exe or similar.
# Or in pyqt6-tools if installed. Let's search inside .venv/Lib/site-packages
site_packages = ROOT / ".venv" / "Lib" / "site-packages"
lrelease_candidates = [
    ROOT / ".venv" / "Scripts" / "lrelease.exe",
    site_packages / "PyQt6" / "Qt6" / "bin" / "lrelease.exe",
    site_packages / "pyqt6_plugins" / "Qt" / "bin" / "lrelease.exe",
    Path(r"D:\01_Codebdbd\01_projects\telegram_upload\venv\Lib\site-packages\PySide6\lrelease.exe"),
]
LRELEASE = None
for c in lrelease_candidates:
    if c.exists():
        LRELEASE = c
        break

if not LRELEASE:
    # Look for it recursively in .venv
    for p in ROOT.glob(".venv/**/lrelease.exe"):
        LRELEASE = p
        break

if LRELEASE:
    print(f"Found lrelease at {LRELEASE}")
    cmd = [str(LRELEASE)] + [str(ts) for ts in TS_FILES]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print(f"[FAIL] lrelease (exit {result.returncode})")
        errors.append("lrelease")
else:
    print("lrelease.exe not found in .venv! Searching system PATH...")
    # try running without path
    try:
        result = subprocess.run(["lrelease", "-version"], capture_output=True, text=True)
        print("System lrelease found")
        cmd = ["lrelease"] + [str(ts) for ts in TS_FILES]
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
    except Exception as e:
        print(f"Could not run lrelease: {e}")
        errors.append("lrelease_not_found")

if errors:
    sys.exit(1)
