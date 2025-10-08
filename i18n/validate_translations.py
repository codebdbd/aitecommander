#!/usr/bin/env python3
"""
Validation script for Qt .ts translation files.

Checks:
1. All .ts files have language attribute
2. No broken translations (mixed languages)
3. No unfinished translations with text
4. Consistent message counts across files
5. Proper numerusform counts
6. No vanished translations in production

Usage:
    python i18n/validate_translations.py
    python i18n/validate_translations.py --fix  # Auto-fix some issues
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List

# Expected numerusform counts per language
NUMERUS_FORMS = {
    "en": 2,  # 1 item / 2 items
    "ru": 3,  # 1 элемент / 2 элемента / 5 элементов
    "uk": 3,  # 1 елемент / 2 елементи / 5 елементів
    "de": 2,  # 1 Element / 2 Elemente
    "es": 2,  # 1 elemento / 2 elementos
    "fr": 2,  # 0-1 élément / 2+ éléments
}

# Pattern to detect mixed languages (Cyrillic + Latin in same word)
MIXED_LANG_PATTERN = re.compile(r'[a-zA-Z]+[а-яА-ЯіїєґІЇЄҐ]+|[а-яА-ЯіїєґІЇЄҐ]+[a-zA-Z]+')


@dataclass
class ValidationIssue:
    """Single validation issue."""
    severity: str  # ERROR, WARNING, INFO
    file: str
    line: int
    context: str
    message: str
    auto_fixable: bool = False


class TranslationValidator:
    """Validator for Qt .ts files."""

    def __init__(self, i18n_dir: Path):
        self.i18n_dir = i18n_dir
        self.issues: List[ValidationIssue] = []
        self.ts_files = sorted(i18n_dir.glob("app_*.ts"))

    def validate_all(self) -> bool:
        """Run all validation checks. Returns True if no errors."""
        if not self.ts_files:
            print("❌ No .ts files found in i18n/")
            return False

        print(f"🔍 Validating {len(self.ts_files)} translation files...\n")

        self.check_language_attributes()
        self.check_broken_translations()
        self.check_unfinished_with_text()
        self.check_message_counts()
        self.check_numerusforms()
        self.check_vanished_translations()

        return self.print_report()

    def check_language_attributes(self) -> None:
        """Check that all .ts files have language attribute."""
        for ts_file in self.ts_files:
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                lang = root.get("language")
                
                if not lang:
                    lang_code = ts_file.stem.split("_")[-1]
                    self.issues.append(ValidationIssue(
                        severity="ERROR",
                        file=ts_file.name,
                        line=3,
                        context="<TS>",
                        message=f"Missing language attribute. Expected: language=\"{lang_code}\"",
                        auto_fixable=True,
                    ))
            except ET.ParseError as e:
                self.issues.append(ValidationIssue(
                    severity="ERROR",
                    file=ts_file.name,
                    line=0,
                    context="XML",
                    message=f"Parse error: {e}",
                ))

    def check_broken_translations(self) -> None:
        """Check for translations with mixed languages."""
        for ts_file in self.ts_files:
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for msg in context.findall("message"):
                        translation = msg.find("translation")
                        if translation is None:
                            continue
                        
                        # Check direct text
                        if translation.text and MIXED_LANG_PATTERN.search(translation.text):
                            source = msg.find("source")
                            source_text = source.text if source is not None else ""
                            self.issues.append(ValidationIssue(
                                severity="ERROR",
                                file=ts_file.name,
                                line=0,
                                context=ctx_text,
                                message=f"Broken translation (mixed languages): '{translation.text}' for '{source_text}'",
                                auto_fixable=False,
                            ))
                        
                        # Check numerusforms
                        for form in translation.findall("numerusform"):
                            if form.text and MIXED_LANG_PATTERN.search(form.text):
                                source = msg.find("source")
                                source_text = source.text if source is not None else ""
                                self.issues.append(ValidationIssue(
                                    severity="ERROR",
                                    file=ts_file.name,
                                    line=0,
                                    context=ctx_text,
                                    message=f"Broken numerusform (mixed languages): '{form.text}' for '{source_text}'",
                                    auto_fixable=False,
                                ))
            except ET.ParseError:
                pass  # Already reported in check_language_attributes

    def check_unfinished_with_text(self) -> None:
        """Check for unfinished translations that have text."""
        for ts_file in self.ts_files:
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for msg in context.findall("message"):
                        translation = msg.find("translation")
                        if translation is None:
                            continue
                        
                        trans_type = translation.get("type")
                        has_text = bool(translation.text and translation.text.strip())
                        
                        if trans_type == "unfinished" and has_text:
                            source = msg.find("source")
                            source_text = source.text if source is not None else ""
                            self.issues.append(ValidationIssue(
                                severity="WARNING",
                                file=ts_file.name,
                                line=0,
                                context=ctx_text,
                                message=f"Translation marked unfinished but has text: '{translation.text}' for '{source_text}'",
                                auto_fixable=True,
                            ))
            except ET.ParseError:
                pass

    def check_message_counts(self) -> None:
        """Check that all .ts files have similar message counts."""
        counts = {}
        for ts_file in self.ts_files:
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                count = sum(1 for _ in root.findall(".//message"))
                counts[ts_file.name] = count
            except ET.ParseError:
                pass
        
        if not counts:
            return
        
        max_count = max(counts.values())
        min_count = min(counts.values())
        
        if max_count - min_count > 10:
            files_info = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            self.issues.append(ValidationIssue(
                severity="WARNING",
                file="ALL",
                line=0,
                context="Message counts",
                message=f"Large variance in message counts: {files_info}. Run 'pylupdate6 app.pro' to sync.",
                auto_fixable=False,
            ))

    def check_numerusforms(self) -> None:
        """Check that numerus messages have correct form counts."""
        for ts_file in self.ts_files:
            lang_code = ts_file.stem.split("_")[-1]
            expected_forms = NUMERUS_FORMS.get(lang_code, 2)
            
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for msg in context.findall("message"):
                        if msg.get("numerus") != "yes":
                            continue
                        
                        translation = msg.find("translation")
                        if translation is None:
                            continue
                        
                        forms = translation.findall("numerusform")
                        actual_forms = len(forms)
                        
                        if actual_forms != expected_forms:
                            source = msg.find("source")
                            source_text = source.text if source is not None else ""
                            self.issues.append(ValidationIssue(
                                severity="WARNING",
                                file=ts_file.name,
                                line=0,
                                context=ctx_text,
                                message=f"Numerus message has {actual_forms} forms, expected {expected_forms} for '{source_text}'",
                                auto_fixable=False,
                            ))
            except ET.ParseError:
                pass

    def check_vanished_translations(self) -> None:
        """Check for vanished translations (should be removed)."""
        for ts_file in self.ts_files:
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for msg in context.findall("message"):
                        translation = msg.find("translation")
                        if translation is None:
                            continue
                        
                        if translation.get("type") == "vanished":
                            source = msg.find("source")
                            source_text = source.text if source is not None else ""
                            self.issues.append(ValidationIssue(
                                severity="INFO",
                                file=ts_file.name,
                                line=0,
                                context=ctx_text,
                                message=f"Vanished translation (can be removed): '{source_text}'",
                                auto_fixable=True,
                            ))
            except ET.ParseError:
                pass

    def print_report(self) -> bool:
        """Print validation report. Returns True if no errors."""
        errors = [i for i in self.issues if i.severity == "ERROR"]
        warnings = [i for i in self.issues if i.severity == "WARNING"]
        infos = [i for i in self.issues if i.severity == "INFO"]
        
        if errors:
            print("🔴 ERRORS:")
            for issue in errors:
                print(f"  [{issue.file}] {issue.context}: {issue.message}")
            print()
        
        if warnings:
            print("🟡 WARNINGS:")
            for issue in warnings:
                print(f"  [{issue.file}] {issue.context}: {issue.message}")
            print()
        
        if infos:
            print("ℹ️  INFO:")
            for issue in infos:
                print(f"  [{issue.file}] {issue.context}: {issue.message}")
            print()
        
        if not self.issues:
            print("✅ All validation checks passed!")
            return True
        
        print(f"📊 Summary: {len(errors)} errors, {len(warnings)} warnings, {len(infos)} info")
        
        auto_fixable = sum(1 for i in self.issues if i.auto_fixable)
        if auto_fixable > 0:
            print(f"💡 {auto_fixable} issues can be auto-fixed with --fix flag")
        
        return len(errors) == 0

    def auto_fix(self) -> None:
        """Auto-fix issues where possible."""
        print("🔧 Auto-fixing issues...\n")
        
        for ts_file in self.ts_files:
            modified = False
            
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                # Fix 1: Add language attribute if missing
                if not root.get("language"):
                    lang_code = ts_file.stem.split("_")[-1]
                    locale_map = {
                        "en": "en_US",
                        "ru": "ru_RU",
                        "uk": "uk_UA",
                        "de": "de_DE",
                        "es": "es_ES",
                        "fr": "fr_FR",
                    }
                    root.set("language", locale_map.get(lang_code, lang_code))
                    if not root.get("sourcelanguage"):
                        root.set("sourcelanguage", "en")
                    modified = True
                    print(f"✓ Added language attribute to {ts_file.name}")
                
                # Fix 2: Remove type="unfinished" from translations with text
                for msg in root.findall(".//message"):
                    translation = msg.find("translation")
                    if translation is None:
                        continue
                    
                    if translation.get("type") == "unfinished" and translation.text:
                        del translation.attrib["type"]
                        modified = True
                
                # Fix 3: Remove vanished translations
                for context in root.findall("context"):
                    for msg in context.findall("message"):
                        translation = msg.find("translation")
                        if translation is not None and translation.get("type") == "vanished":
                            context.remove(msg)
                            modified = True
                
                if modified:
                    tree.write(ts_file, encoding="utf-8", xml_declaration=True)
                    print(f"✓ Fixed {ts_file.name}")
            
            except ET.ParseError as e:
                print(f"✗ Cannot fix {ts_file.name}: {e}")
        
        print("\n✅ Auto-fix complete. Re-run validation to verify.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Qt .ts translation files")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues where possible")
    args = parser.parse_args()
    
    i18n_dir = Path(__file__).parent
    validator = TranslationValidator(i18n_dir)
    
    if args.fix:
        validator.auto_fix()
        return 0
    
    success = validator.validate_all()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
