"""Command-line interface for Aite Commander localization management."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
I18N_DIR = PROJECT_ROOT / "i18n"
APP_DIR = PROJECT_ROOT / "app"
DEFAULT_LANGUAGES = ["en", "ru", "de", "es", "fr", "uk"]


def get_pylupdate() -> Path | str:
    """Locate pylupdate6 binary."""
    venv_bin = PROJECT_ROOT / ".venv" / "Scripts" / "pylupdate6.exe"
    if venv_bin.is_file():
        return venv_bin
    which = shutil.which("pylupdate6")
    if which:
        return Path(which)
    return "pylupdate6"


def get_lrelease() -> Path | str:
    """Locate lrelease binary."""
    local_bin = I18N_DIR / "lrelease.exe"
    if local_bin.is_file():
        return local_bin
    venv_bin = PROJECT_ROOT / ".venv" / "Scripts" / "lrelease.exe"
    if venv_bin.is_file():
        return venv_bin
    which = shutil.which("lrelease")
    if which:
        return Path(which)
    return "lrelease"


def get_configured_languages() -> list[str]:
    """Get list of active language codes based on app_*.ts files."""
    ts_files = sorted(I18N_DIR.glob("app_*.ts"))
    langs = []
    for f in ts_files:
        code = f.stem.replace("app_", "")
        langs.append(code)
    return langs or DEFAULT_LANGUAGES


def cmd_check(args: argparse.Namespace) -> int:
    """Validate integrity, 100% completion, and parity across all translation catalogs."""
    languages = get_configured_languages()
    print("=" * 72)
    print(f"{'Lang':<5} | {'Total':>6} | {'Done':>6} | {'%':>6} | {'Unfinished':>10} | {'Vanished':>8}")
    print("=" * 72)

    has_errors = False
    counts: list[int] = []
    missing_per_lang: dict[str, list[str]] = {}

    for lang in languages:
        ts_path = I18N_DIR / f"app_{lang}.ts"
        if not ts_path.is_file():
            print(f"ERROR: Missing catalog file: {ts_path}")
            has_errors = True
            continue

        try:
            tree = ET.parse(ts_path)
            root = tree.getroot()
        except Exception as e:
            print(f"ERROR parsing {ts_path}: {e}")
            has_errors = True
            continue

        total = 0
        done = 0
        unfinished = 0
        vanished = 0
        unfin_samples: list[str] = []

        for ctx in root.findall("context"):
            ctx_name = (ctx.find("name").text or "?") if ctx.find("name") is not None else "?"
            for msg in ctx.findall("message"):
                trans = msg.find("translation")
                if trans is None:
                    continue
                t_type = trans.get("type", "")
                if t_type in ("vanished", "obsolete"):
                    vanished += 1
                    continue

                forms = trans.findall("numerusform")
                if forms:
                    total += 1
                    if any((f.text or "").strip() for f in forms):
                        done += 1
                    else:
                        unfinished += 1
                        if len(unfin_samples) < 5:
                            src = msg.find("source")
                            unfin_samples.append(f"[{ctx_name}] {src.text if src is not None else ''}")
                    continue

                total += 1
                text = (trans.text or "").strip()
                if t_type == "unfinished" or not text:
                    unfinished += 1
                    if len(unfin_samples) < 5:
                        src = msg.find("source")
                        unfin_samples.append(f"[{ctx_name}] {src.text if src is not None else ''}")
                else:
                    done += 1

        counts.append(total)
        pct = (done / total * 100) if total else 0.0
        is_ok = (unfinished == 0 and vanished == 0)
        if not is_ok:
            has_errors = True
            if unfin_samples:
                missing_per_lang[lang] = unfin_samples

        flag = "✓" if is_ok else "✗"
        print(f"{flag} {lang:<3} | {total:>6} | {done:>6} | {pct:>5.1f}% | {unfinished:>10} | {vanished:>8}")

    print("=" * 72)

    # Parity check
    if len(set(counts)) > 1:
        print("✗ PARITY FAILURE: Message counts differ between languages!")
        has_errors = True
    elif counts:
        print(f"✓ PARITY OK: Exactly {counts[0]} messages in all {len(languages)} languages.")

    if missing_per_lang:
        print("\nUnfinished translations detected:")
        for lang, samples in missing_per_lang.items():
            print(f"  [{lang.upper()}]:")
            for s in samples:
                print(f"    - {s}")

    if has_errors:
        print("\n[RESULT] Verification FAILED. Please fix issues above.")
        return 1

    print("\n[RESULT] All catalogs are 100% complete and consistent.")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Extract translatable strings from app/ into all .ts catalogs."""
    pylupdate = get_pylupdate()
    languages = get_configured_languages()

    print(f"Running pylupdate6 on '{APP_DIR}'...")
    has_errors = False

    for lang in languages:
        ts_path = I18N_DIR / f"app_{lang}.ts"
        cmd = [str(pylupdate), str(APP_DIR), "--ts", str(ts_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[{lang.upper()}] ERROR: {res.stderr.strip()}")
            has_errors = True
        else:
            summary = [l.strip() for l in res.stdout.splitlines() if l.strip()]
            short_summary = "; ".join(summary) if summary else "No changes"
            print(f"[{lang.upper()}] {short_summary}")

    return 1 if has_errors else 0


def cmd_compile(args: argparse.Namespace) -> int:
    """Compile all .ts translation files to .qm binary catalogs."""
    lrelease = get_lrelease()
    languages = get_configured_languages()

    print(f"Compiling QM files via {Path(lrelease).name}...")
    has_errors = False

    for lang in languages:
        ts_path = I18N_DIR / f"app_{lang}.ts"
        qm_path = I18N_DIR / f"app_{lang}.qm"
        cmd = [str(lrelease), str(ts_path), "-qm", str(qm_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[{lang.upper()}] ERROR: {res.stderr.strip()}")
            has_errors = True
        else:
            lines = [l.strip() for l in res.stdout.splitlines() if "Generated" in l]
            status = lines[0] if lines else "OK"
            print(f"[{lang.upper()}] {status}")

    return 1 if has_errors else 0


def cmd_all(args: argparse.Namespace) -> int:
    """Run update -> compile -> check workflow in a single step."""
    print("Step 1/3: Updating string catalogs from source...")
    if cmd_update(args) != 0:
        return 1

    print("\nStep 2/3: Compiling binary QM files...")
    if cmd_compile(args) != 0:
        return 1

    print("\nStep 3/3: Validating integrity...")
    return cmd_check(args)


def cmd_add_language(args: argparse.Namespace) -> int:
    """Add a new language catalog."""
    code = args.code.lower().strip()
    ts_path = I18N_DIR / f"app_{code}.ts"
    if ts_path.exists():
        print(f"Language '{code}' already exists ({ts_path}).")
        return 1

    # Create empty TS file
    empty_ts = '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n<TS version="2.1">\n</TS>\n'
    ts_path.write_text(empty_ts, encoding="utf-8")
    print(f"Created {ts_path}")

    # Try to copy qtbase if available
    try:
        from PyQt6.QtCore import QLibraryInfo
        qt_trans_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        src_qtbase = Path(qt_trans_dir) / f"qtbase_{code}.qm"
        if src_qtbase.exists():
            dst_qtbase = I18N_DIR / f"qtbase_{code}.qm"
            shutil.copy2(src_qtbase, dst_qtbase)
            print(f"Copied {src_qtbase.name} to {dst_qtbase.name}")
    except Exception as e:
        print(f"Note: Could not copy qtbase_{code}.qm: {e}")

    # Populate from source code via pylupdate
    pylupdate = get_pylupdate()
    subprocess.run([str(pylupdate), str(APP_DIR), "--ts", str(ts_path)], capture_output=True)
    print(f"Extracted source strings into {ts_path.name}")
    print(f"\nLanguage '{code}' initialized. Next steps:")
    print(f"1. Add '{code}' to LanguageService._languages in i18n/language_service.py")
    print(f"2. Translate strings in {ts_path}")
    print(f"3. Run `python -m i18n compile` and `python -m i18n check`")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m i18n",
        description="Aite Commander Internationalization Management Tool",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # check
    subparsers.add_parser("check", help="Verify completeness and parity of all catalogs (CI gate)")

    # update
    subparsers.add_parser("update", help="Extract strings from source code into .ts files")

    # compile
    subparsers.add_parser("compile", help="Compile .ts files to binary .qm files")

    # all
    subparsers.add_parser("all", help="Run update, compile, and check in sequence")

    # add-language
    add_parser = subparsers.add_parser("add-language", help="Scaffold a new language catalog")
    add_parser.add_argument("code", help="2-letter ISO 639-1 language code (e.g., 'it', 'pl')")

    args = parser.parse_args(argv)

    if args.command == "check":
        return cmd_check(args)
    elif args.command == "update":
        return cmd_update(args)
    elif args.command == "compile":
        return cmd_compile(args)
    elif args.command == "all":
        return cmd_all(args)
    elif args.command == "add-language":
        return cmd_add_language(args)
    else:
        parser.print_help()
        return 0
