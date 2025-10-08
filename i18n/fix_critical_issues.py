#!/usr/bin/env python3
"""
Quick fix script for critical i18n issues.

Fixes:
1. Broken translations in app_uk.ts (mixed languages)
2. Missing language attributes in .ts files
3. Unfinished translations with text in app_ru.ts
4. Removes vanished translations

Usage:
    python i18n/fix_critical_issues.py
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def fix_broken_ukrainian_translations(ts_file: Path) -> bool:
    """Fix specific broken translations in app_uk.ts."""
    if not ts_file.exists():
        print(f"❌ File not found: {ts_file}")
        return False
    
    try:
        tree = ET.parse(ts_file)
        root = tree.getroot()
        fixed_count = 0
        
        # Known broken translations
        fixes = {
            "⚠️ Operation cancelled": "⚠️ Операцію скасовано",
            "Cancelling operation…": "Скасування операції…",
            "❌ Error: {error}": "❌ Помилка: {error}",
            "✅ Operation completed successfully": "✅ Операцію успішно завершено",
        }
        
        for context in root.findall("context"):
            for msg in context.findall("message"):
                source = msg.find("source")
                translation = msg.find("translation")
                
                if source is None or translation is None:
                    continue
                
                source_text = source.text
                if source_text in fixes:
                    old_translation = translation.text
                    new_translation = fixes[source_text]
                    
                    if old_translation != new_translation:
                        translation.text = new_translation
                        # Remove unfinished type if present
                        if "type" in translation.attrib:
                            del translation.attrib["type"]
                        fixed_count += 1
                        print(f"  ✓ Fixed: '{source_text}' -> '{new_translation}'")
        
        if fixed_count > 0:
            tree.write(ts_file, encoding="utf-8", xml_declaration=True)
            print(f"✅ Fixed {fixed_count} broken translations in {ts_file.name}\n")
            return True
        else:
            print(f"ℹ️  No broken translations found in {ts_file.name}\n")
            return True
    
    except ET.ParseError as e:
        print(f"❌ Parse error in {ts_file}: {e}")
        return False


def add_language_attributes(ts_file: Path) -> bool:
    """Add missing language and sourcelanguage attributes."""
    try:
        tree = ET.parse(ts_file)
        root = tree.getroot()
        
        lang_code = ts_file.stem.split("_")[-1]
        locale_map = {
            "en": "en_US",
            "ru": "ru_RU",
            "uk": "uk_UA",
            "de": "de_DE",
            "es": "es_ES",
            "fr": "fr_FR",
        }
        
        modified = False
        
        if not root.get("language"):
            root.set("language", locale_map.get(lang_code, lang_code))
            modified = True
            print(f"  ✓ Added language=\"{locale_map.get(lang_code, lang_code)}\"")
        
        if not root.get("sourcelanguage"):
            root.set("sourcelanguage", "en")
            modified = True
            print(f"  ✓ Added sourcelanguage=\"en\"")
        
        if modified:
            tree.write(ts_file, encoding="utf-8", xml_declaration=True)
            print(f"✅ Updated attributes in {ts_file.name}\n")
            return True
        else:
            print(f"ℹ️  Attributes already present in {ts_file.name}\n")
            return True
    
    except ET.ParseError as e:
        print(f"❌ Parse error in {ts_file}: {e}")
        return False


def remove_unfinished_from_translated(ts_file: Path) -> bool:
    """Remove type='unfinished' from translations that have text."""
    try:
        tree = ET.parse(ts_file)
        root = tree.getroot()
        fixed_count = 0
        
        for msg in root.findall(".//message"):
            translation = msg.find("translation")
            if translation is None:
                continue
            
            # If translation has text but marked as unfinished, remove the attribute
            if translation.get("type") == "unfinished" and translation.text:
                del translation.attrib["type"]
                fixed_count += 1
        
        if fixed_count > 0:
            tree.write(ts_file, encoding="utf-8", xml_declaration=True)
            print(f"✅ Removed 'unfinished' from {fixed_count} translations in {ts_file.name}\n")
            return True
        else:
            print(f"ℹ️  No unfinished-with-text issues in {ts_file.name}\n")
            return True
    
    except ET.ParseError as e:
        print(f"❌ Parse error in {ts_file}: {e}")
        return False


def remove_vanished_translations(ts_file: Path) -> bool:
    """Remove vanished translations from .ts file."""
    try:
        tree = ET.parse(ts_file)
        root = tree.getroot()
        removed_count = 0
        
        for context in root.findall("context"):
            for msg in context.findall("message"):
                translation = msg.find("translation")
                if translation is not None and translation.get("type") == "vanished":
                    context.remove(msg)
                    removed_count += 1
        
        if removed_count > 0:
            tree.write(ts_file, encoding="utf-8", xml_declaration=True)
            print(f"✅ Removed {removed_count} vanished translations from {ts_file.name}\n")
            return True
        else:
            print(f"ℹ️  No vanished translations in {ts_file.name}\n")
            return True
    
    except ET.ParseError as e:
        print(f"❌ Parse error in {ts_file}: {e}")
        return False


def main() -> int:
    print("🔧 Fixing critical i18n issues...\n")
    print("=" * 70)
    
    i18n_dir = Path(__file__).parent
    ts_files = sorted(i18n_dir.glob("app_*.ts"))
    
    if not ts_files:
        print("❌ No .ts files found in i18n/")
        return 1
    
    success = True
    
    # Step 1: Fix broken Ukrainian translations
    print("\n📝 Step 1: Fixing broken Ukrainian translations")
    print("-" * 70)
    uk_file = i18n_dir / "app_uk.ts"
    if uk_file.exists():
        success &= fix_broken_ukrainian_translations(uk_file)
    
    # Step 2: Add language attributes to all files
    print("📝 Step 2: Adding language attributes")
    print("-" * 70)
    for ts_file in ts_files:
        success &= add_language_attributes(ts_file)
    
    # Step 3: Remove 'unfinished' from translated strings
    print("📝 Step 3: Removing 'unfinished' from translated strings")
    print("-" * 70)
    for ts_file in ts_files:
        success &= remove_unfinished_from_translated(ts_file)
    
    # Step 4: Remove vanished translations
    print("📝 Step 4: Removing vanished translations")
    print("-" * 70)
    for ts_file in ts_files:
        success &= remove_vanished_translations(ts_file)
    
    print("=" * 70)
    if success:
        print("\n✅ All critical issues fixed successfully!")
        print("\n📋 Next steps:")
        print("  1. Run: python i18n/validate_translations.py")
        print("  2. Run: python i18n/update_and_report.py --compile")
        print("  3. Run: python i18n/update_and_report.py --report")
        print("  4. Test language switching in the application")
        return 0
    else:
        print("\n❌ Some issues could not be fixed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
