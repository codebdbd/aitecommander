#!/usr/bin/env python3
"""
Скрипт для завершения незавершенных переводов.

Заполняет пустые переводы на основе английского оригинала или существующих переводов.
Использует консервативный подход: копирует оригинал для технических терминов.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

# Словарь переводов для основных UI терминов
TRANSLATIONS = {
    "en": {
        "&Actions": "&Actions",
        "&File": "&File", 
        "&Data": "&Data",
        "&Search": "&Search",
        "&Themes": "&Themes",
        "&Help": "&Help",
        "Button {idx} of {total} visible buttons": "Button {idx} of {total} visible buttons",
        "Hidden button": "Hidden button",
        "Recent Links": "Recent Links",
        "Favorites": "Favorites",
        "Quick Add": "Quick Add",
    },
    "de": {
        "&Actions": "&Aktionen",
        "&File": "&Datei",
        "&Data": "&Daten", 
        "&Search": "&Suchen",
        "&Themes": "&Designs",
        "&Help": "&Hilfe",
        "Button {idx} of {total} visible buttons": "Schaltfläche {idx} von {total} sichtbaren Schaltflächen",
        "Hidden button": "Versteckte Schaltfläche",
        "Recent Links": "Aktuelle Links",
        "Favorites": "Favoriten",
        "Quick Add": "Schnell hinzufügen",
    },
    "es": {
        "&Actions": "&Acciones",
        "&File": "&Archivo",
        "&Data": "&Datos",
        "&Search": "&Buscar", 
        "&Themes": "&Temas",
        "&Help": "&Ayuda",
        "Button {idx} of {total} visible buttons": "Botón {idx} de {total} botones visibles",
        "Hidden button": "Botón oculto",
        "Recent Links": "Enlaces recientes",
        "Favorites": "Favoritos",
        "Quick Add": "Agregar rápido",
    },
    "fr": {
        "&Actions": "&Actions",
        "&File": "&Fichier",
        "&Data": "&Données",
        "&Search": "&Rechercher",
        "&Themes": "&Thèmes", 
        "&Help": "&Aide",
        "Button {idx} of {total} visible buttons": "Bouton {idx} sur {total} boutons visibles",
        "Hidden button": "Bouton masqué",
        "Recent Links": "Liens récents",
        "Favorites": "Favoris",
        "Quick Add": "Ajout rapide",
    }
}


def complete_translations(ts_file: Path, lang_code: str) -> int:
    """Завершить незавершенные переводы в .ts файле."""
    if not ts_file.exists():
        print(f"❌ Файл не найден: {ts_file}")
        return 0
    
    try:
        tree = ET.parse(ts_file)
        root = tree.getroot()
        completed_count = 0
        
        lang_translations = TRANSLATIONS.get(lang_code, {})
        
        for context in root.findall("context"):
            for message in context.findall("message"):
                translation = message.find("translation")
                if translation is None:
                    continue
                
                # Пропускаем если уже переведено
                if translation.get("type") != "unfinished":
                    continue
                
                source = message.find("source")
                if source is None or source.text is None:
                    continue
                
                source_text = source.text
                
                # Ищем перевод в словаре
                if source_text in lang_translations:
                    translation.text = lang_translations[source_text]
                    del translation.attrib["type"]  # Убираем unfinished
                    completed_count += 1
                    print(f"  ✓ '{source_text}' -> '{lang_translations[source_text]}'")
                else:
                    # Для английского языка копируем оригинал
                    if lang_code == "en":
                        translation.text = source_text
                        del translation.attrib["type"]
                        completed_count += 1
                        print(f"  ✓ '{source_text}' -> '{source_text}' (оригинал)")
        
        if completed_count > 0:
            tree.write(ts_file, encoding="utf-8", xml_declaration=True)
            print(f"✅ Завершено {completed_count} переводов в {ts_file.name}")
        else:
            print(f"ℹ️  Нет незавершенных переводов в {ts_file.name}")
        
        return completed_count
    
    except ET.ParseError as e:
        print(f"❌ Ошибка парсинга {ts_file}: {e}")
        return 0


def main() -> int:
    """Основная функция."""
    print("🔧 Завершение незавершенных переводов...\n")
    
    i18n_dir = Path(__file__).parent
    ts_files = sorted(i18n_dir.glob("app_*.ts"))
    
    if not ts_files:
        print("❌ Файлы .ts не найдены в i18n/")
        return 1
    
    total_completed = 0
    
    for ts_file in ts_files:
        lang_code = ts_file.stem.split("_")[-1]
        print(f"📝 Обработка {ts_file.name} (язык: {lang_code})")
        print("-" * 50)
        
        completed = complete_translations(ts_file, lang_code)
        total_completed += completed
        print()
    
    print("=" * 70)
    print(f"✅ Всего завершено переводов: {total_completed}")
    
    if total_completed > 0:
        print("\n📋 Следующие шаги:")
        print("  1. Перекомпилировать переводы: python update_and_report.py --compile")
        print("  2. Проверить результат: python update_and_report.py --report")
        print("  3. Протестировать в приложении")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


