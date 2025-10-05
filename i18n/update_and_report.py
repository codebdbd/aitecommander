#!/usr/bin/env python3
"""
Helper script for i18n workflow automation.

This script:
1. Runs pylupdate6 to extract translatable strings from source code
2. Analyzes .ts files to generate translation statistics
3. Provides a detailed report on i18n coverage

Usage:
    python update_and_report.py [--update] [--compile] [--report]

Options:
    --update    Run pylupdate6 to update .ts files
    --compile   Compile .ts files to .qm files using lrelease
    --report    Generate detailed translation report (default)
    --all       Run all steps (update, compile, report)
"""

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple


class TranslationStats:
    """Statistics for a single translation file."""

    def __init__(self, lang_code: str):
        self.lang_code = lang_code
        self.total_messages = 0
        self.translated = 0
        self.unfinished = 0
        self.obsolete = 0
        self.contexts: Dict[str, int] = {}

    @property
    def completion_percent(self) -> float:
        if self.total_messages == 0:
            return 0.0
        return (self.translated / self.total_messages) * 100

    def __str__(self) -> str:
        return (
            f"Language: {self.lang_code}\n"
            f"  Total messages: {self.total_messages}\n"
            f"  Translated: {self.translated} ({self.completion_percent:.1f}%)\n"
            f"  Unfinished: {self.unfinished}\n"
            f"  Obsolete: {self.obsolete}\n"
            f"  Contexts: {len(self.contexts)}"
        )


def parse_ts_file(ts_path: Path) -> TranslationStats:
    """Parse a .ts file and extract translation statistics."""
    lang_code = ts_path.stem.split("_")[-1]
    stats = TranslationStats(lang_code)

    try:
        tree = ET.parse(ts_path)
        root = tree.getroot()

        for context in root.findall("context"):
            context_name = context.find("name")
            if context_name is not None and context_name.text:
                ctx_name = context_name.text
                message_count = 0

                for message in context.findall("message"):
                    stats.total_messages += 1
                    message_count += 1

                    translation = message.find("translation")
                    if translation is not None:
                        trans_type = translation.get("type", "")
                        if trans_type == "unfinished":
                            stats.unfinished += 1
                        elif trans_type == "obsolete":
                            stats.obsolete += 1
                        elif translation.text:
                            stats.translated += 1
                        else:
                            stats.unfinished += 1

                stats.contexts[ctx_name] = message_count

    except ET.ParseError as e:
        print(f"Error parsing {ts_path}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Unexpected error parsing {ts_path}: {e}", file=sys.stderr)

    return stats


def run_pylupdate(project_file: Path) -> bool:
    """Run pylupdate6 to extract strings from source files."""
    print(f"Running pylupdate6 on {project_file}...")
    
    # Parse .pro file to get source files and translation files
    sources = []
    translations = []
    
    try:
        with open(project_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                # Handle SOURCES and SOURCES +=
                if 'SOURCES' in line:
                    # Extract file paths from the line
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        files_part = parts[1].strip()
                        # Remove trailing backslash
                        files_part = files_part.rstrip('\\').strip()
                        if files_part:
                            sources.append(files_part)
                elif 'TRANSLATIONS' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        files_part = parts[1].strip()
                        files_part = files_part.rstrip('\\').strip()
                        if files_part:
                            translations.append(files_part)
                elif line and not line.startswith(('CODECFORTR', 'CODECFORSRC')):
                    # Continuation line
                    line = line.rstrip('\\').strip()
                    if line and not any(kw in line for kw in ['CODECFORTR', 'CODECFORSRC', 'TRANSLATIONS']):
                        sources.append(line)
                    elif 'TRANSLATIONS' not in line and line and any(x in line for x in ['.ts']):
                        translations.append(line)
    except Exception as e:
        print(f"Error parsing {project_file}: {e}", file=sys.stderr)
        return False
    
    if not sources:
        print("No source files found in .pro file", file=sys.stderr)
        return False
    
    if not translations:
        print("No translation files found in .pro file", file=sys.stderr)
        return False
    
    # Convert relative paths to absolute
    base_dir = project_file.parent
    source_files = []
    for src in sources:
        src_path = (base_dir / src).resolve()
        if src_path.exists():
            source_files.append(str(src_path))
    
    print(f"Found {len(source_files)} source files")
    print(f"Found {len(translations)} translation files")
    
    # Run pylupdate6 for each translation file
    success = True
    for ts_file in translations:
        ts_path = base_dir / ts_file
        print(f"\nUpdating {ts_file}...")
        
        try:
            cmd = ["pylupdate6", "--verbose", "--ts", str(ts_path)] + source_files
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            if result.returncode != 0:
                success = False
        except FileNotFoundError:
            print("Error: pylupdate6 not found. Install PyQt6-tools:", file=sys.stderr)
            print("  pip install PyQt6-tools", file=sys.stderr)
            return False
        except Exception as e:
            print(f"Error running pylupdate6: {e}", file=sys.stderr)
            success = False
    
    return success


def compile_translations(i18n_dir: Path, ts_files: List[Path]) -> bool:
    """Compile .ts files to .qm files using lrelease or Python fallback."""
    print("\nCompiling translation files...")
    success = True

    # Try to find lrelease in various locations
    lrelease_commands = [
        "lrelease",
        "lrelease-qt6",
        "lrelease6",
    ]
    
    lrelease_found = None
    for cmd in lrelease_commands:
        try:
            result = subprocess.run(
                [cmd, "-version"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                lrelease_found = cmd
                print(f"Found {cmd}: {result.stdout.strip()}")
                break
        except FileNotFoundError:
            continue
    
    if not lrelease_found:
        print("\n⚠️  lrelease not found. Trying Python-based compilation...")
        return _compile_with_python(i18n_dir, ts_files)

    for ts_file in ts_files:
        qm_file = ts_file.with_suffix(".qm")
        print(f"  {ts_file.name} -> {qm_file.name}")

        try:
            result = subprocess.run(
                [lrelease_found, str(ts_file), "-qm", str(qm_file)],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(i18n_dir),
            )
            if result.returncode != 0:
                print(f"    Error: {result.stderr}", file=sys.stderr)
                success = False
            else:
                print(f"    ✓ Compiled successfully")
        except Exception as e:
            print(f"    Error: {e}", file=sys.stderr)
            success = False

    return success


def _compile_with_python(i18n_dir: Path, ts_files: List[Path]) -> bool:
    """Fallback: compile .ts to .qm using PyQt6's QTranslator."""
    try:
        from PyQt6.QtCore import QTranslator, QCoreApplication
        import sys as _sys
        
        # Create minimal QCoreApplication
        app = QCoreApplication.instance()
        if app is None:
            app = QCoreApplication(_sys.argv)
        
        print("\nUsing PyQt6.QTranslator for compilation...")
        success = True
        
        for ts_file in ts_files:
            qm_file = ts_file.with_suffix(".qm")
            print(f"  {ts_file.name} -> {qm_file.name}")
            
            translator = QTranslator()
            if translator.load(str(ts_file)):
                # QTranslator loaded the .ts file
                # Now we need to save it as .qm
                # Unfortunately, QTranslator doesn't have a save() method
                # We need lrelease for proper compilation
                print(f"    ⚠️  Loaded but cannot save without lrelease")
                print(f"    ℹ️  Install Qt tools: https://www.qt.io/download-qt-installer")
                success = False
            else:
                print(f"    ❌ Failed to load .ts file")
                success = False
        
        if not success:
            print("\n" + "=" * 70)
            print("INSTALLATION REQUIRED")
            print("=" * 70)
            print("\nTo compile translations, install Qt Linguist tools:")
            print("\nOption 1: Install full Qt (recommended)")
            print("  Download: https://www.qt.io/download-qt-installer")
            print("  Install Qt 6.x with 'Qt Linguist' component")
            print("  Add Qt bin directory to PATH")
            print("\nOption 2: Use conda")
            print("  conda install qt")
            print("\nOption 3: Manual download")
            print("  Download Qt binaries and extract lrelease.exe")
            print("  Add to PATH or copy to i18n/ directory")
            print("=" * 70)
        
        return success
        
    except ImportError:
        print("Error: PyQt6 not installed", file=sys.stderr)
        return False


def generate_report(i18n_dir: Path) -> None:
    """Generate a detailed translation report."""
    print("\n" + "=" * 70)
    print("TRANSLATION REPORT")
    print("=" * 70 + "\n")

    ts_files = sorted(i18n_dir.glob("app_*.ts"))
    if not ts_files:
        print("No translation files found (app_*.ts)")
        return

    all_stats: List[TranslationStats] = []

    for ts_file in ts_files:
        stats = parse_ts_file(ts_file)
        all_stats.append(stats)
        print(stats)
        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total languages: {len(all_stats)}")

    if all_stats:
        avg_completion = sum(s.completion_percent for s in all_stats) / len(all_stats)
        print(f"Average completion: {avg_completion:.1f}%")

        total_contexts = len(all_stats[0].contexts) if all_stats else 0
        print(f"Total contexts: {total_contexts}")

        total_messages = all_stats[0].total_messages if all_stats else 0
        print(f"Total messages per language: {total_messages}")

    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("1. Open .ts files in Qt Linguist to translate strings:")
    print("   linguist app_en.ts")
    print("   linguist app_uk.ts")
    print()
    print("2. After translation, compile .qm files:")
    print("   python update_and_report.py --compile")
    print()
    print("3. Test language switching in the application")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="i18n workflow automation for Aite Commander"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Run pylupdate6 to extract strings",
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Compile .ts files to .qm files",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate translation report",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all steps (update, compile, report)",
    )

    args = parser.parse_args()

    # Default to report if no options specified
    if not any([args.update, args.compile, args.report, args.all]):
        args.report = True

    if args.all:
        args.update = args.compile = args.report = True

    # Get paths
    script_dir = Path(__file__).parent
    project_file = script_dir / "app.pro"
    ts_files = sorted(script_dir.glob("app_*.ts"))

    success = True

    # Step 1: Update translations
    if args.update:
        if not project_file.exists():
            print(f"Error: {project_file} not found", file=sys.stderr)
            return 1
        success = run_pylupdate(project_file)
        if not success:
            print("Failed to update translations", file=sys.stderr)
            return 1

    # Step 2: Compile translations
    if args.compile:
        if not ts_files:
            print("No .ts files found to compile", file=sys.stderr)
            return 1
        success = compile_translations(script_dir, ts_files)
        if not success:
            print("Failed to compile some translations", file=sys.stderr)
            return 1

    # Step 3: Generate report
    if args.report:
        generate_report(script_dir)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
