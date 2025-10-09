#!/usr/bin/env python3
"""
Валидатор качества переводов.

Проверяет:
1. Консистентность терминологии
2. Корректность плейсхолдеров
3. Длину переводов относительно оригинала
4. Использование правильных символов для языка
"""

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Паттерны для проверки качества
PLACEHOLDER_PATTERN = re.compile(r'%[0-9n]|\{[^}]+\}')
HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
CYRILLIC_PATTERN = re.compile(r'[а-яА-ЯіїєґІЇЄҐ]')
LATIN_PATTERN = re.compile(r'[a-zA-Z]')

# Словарь терминологии для проверки консистентности
TERMINOLOGY = {
    "ru": {
        "file": ["файл"],
        "folder": ["папка", "каталог"],
        "link": ["ссылка", "линк"],
        "search": ["поиск"],
        "settings": ["настройки", "параметры"],
        "cancel": ["отмена", "отменить"],
        "ok": ["ок", "хорошо"],
        "yes": ["да"],
        "no": ["нет"],
        "delete": ["удалить", "удаление"],
        "edit": ["изменить", "редактировать"],
        "save": ["сохранить", "сохранение"],
        "open": ["открыть", "открытие"],
        "close": ["закрыть", "закрытие"],
        "import": ["импорт", "импортировать"],
        "export": ["экспорт", "экспортировать"],
    },
    "uk": {
        "file": ["файл"],
        "folder": ["папка", "каталог"],
        "link": ["посилання", "лінк"],
        "search": ["пошук"],
        "settings": ["налаштування", "параметри"],
        "cancel": ["скасувати", "скасування"],
        "ok": ["гаразд", "ок"],
        "yes": ["так"],
        "no": ["ні"],
        "delete": ["видалити", "видалення"],
        "edit": ["редагувати", "змінити"],
        "save": ["зберегти", "збереження"],
        "open": ["відкрити", "відкриття"],
        "close": ["закрити", "закриття"],
        "import": ["імпорт", "імпортувати"],
        "export": ["експорт", "експортувати"],
    },
    "de": {
        "file": ["datei"],
        "folder": ["ordner", "verzeichnis"],
        "link": ["link", "verknüpfung"],
        "search": ["suche", "suchen"],
        "settings": ["einstellungen"],
        "cancel": ["abbrechen"],
        "ok": ["ok", "in ordnung"],
        "yes": ["ja"],
        "no": ["nein"],
        "delete": ["löschen"],
        "edit": ["bearbeiten"],
        "save": ["speichern"],
        "open": ["öffnen"],
        "close": ["schließen"],
        "import": ["importieren"],
        "export": ["exportieren"],
    },
    "es": {
        "file": ["archivo"],
        "folder": ["carpeta", "directorio"],
        "link": ["enlace", "vínculo"],
        "search": ["buscar", "búsqueda"],
        "settings": ["configuración"],
        "cancel": ["cancelar"],
        "ok": ["ok", "aceptar"],
        "yes": ["sí"],
        "no": ["no"],
        "delete": ["eliminar"],
        "edit": ["editar"],
        "save": ["guardar"],
        "open": ["abrir"],
        "close": ["cerrar"],
        "import": ["importar"],
        "export": ["exportar"],
    },
    "fr": {
        "file": ["fichier"],
        "folder": ["dossier", "répertoire"],
        "link": ["lien"],
        "search": ["recherche", "chercher"],
        "settings": ["paramètres"],
        "cancel": ["annuler"],
        "ok": ["ok", "d'accord"],
        "yes": ["oui"],
        "no": ["non"],
        "delete": ["supprimer"],
        "edit": ["modifier"],
        "save": ["enregistrer"],
        "open": ["ouvrir"],
        "close": ["fermer"],
        "import": ["importer"],
        "export": ["exporter"],
    },
}


@dataclass
class QualityIssue:
    """Проблема качества перевода."""
    severity: str  # ERROR, WARNING, INFO
    file: str
    context: str
    source: str
    translation: str
    issue_type: str
    description: str


class TranslationQualityValidator:
    """Валидатор качества переводов."""

    def __init__(self, i18n_dir: Path):
        self.i18n_dir = i18n_dir
        self.issues: List[QualityIssue] = []
        self.ts_files = sorted(i18n_dir.glob("app_*.ts"))

    def validate_all(self) -> bool:
        """Запустить все проверки качества."""
        if not self.ts_files:
            print("❌ Файлы .ts не найдены в i18n/")
            return False

        print(f"🔍 Проверка качества переводов в {len(self.ts_files)} файлах...\n")

        self.check_placeholder_consistency()
        self.check_translation_length()
        self.check_character_consistency()
        self.check_terminology_consistency()
        self.check_html_tags()

        return self.print_report()

    def check_placeholder_consistency(self) -> None:
        """Проверить консистентность плейсхолдеров."""
        for ts_file in self.ts_files:
            lang_code = ts_file.stem.split("_")[-1]
            
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for message in context.findall("message"):
                        source = message.find("source")
                        translation = message.find("translation")
                        
                        if source is None or translation is None:
                            continue
                        
                        source_text = source.text or ""
                        translation_text = translation.text or ""
                        
                        # Проверяем плейсхолдеры
                        source_placeholders = set(PLACEHOLDER_PATTERN.findall(source_text))
                        translation_placeholders = set(PLACEHOLDER_PATTERN.findall(translation_text))
                        
                        if source_placeholders != translation_placeholders:
                            self.issues.append(QualityIssue(
                                severity="ERROR",
                                file=ts_file.name,
                                context=ctx_text,
                                source=source_text,
                                translation=translation_text,
                                issue_type="placeholder_mismatch",
                                description=f"Плейсхолдеры не совпадают: {source_placeholders} vs {translation_placeholders}"
                            ))
            except ET.ParseError:
                pass

    def check_translation_length(self) -> None:
        """Проверить длину переводов относительно оригинала."""
        for ts_file in self.ts_files:
            lang_code = ts_file.stem.split("_")[-1]
            
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for message in context.findall("message"):
                        source = message.find("source")
                        translation = message.find("translation")
                        
                        if source is None or translation is None:
                            continue
                        
                        source_text = source.text or ""
                        translation_text = translation.text or ""
                        
                        # Проверяем длину (исключаем HTML теги и плейсхолдеры)
                        source_clean = PLACEHOLDER_PATTERN.sub("", HTML_TAG_PATTERN.sub("", source_text))
                        translation_clean = PLACEHOLDER_PATTERN.sub("", HTML_TAG_PATTERN.sub("", translation_text))
                        
                        length_ratio = len(translation_clean) / len(source_clean) if len(source_clean) > 0 else 1
                        
                        if length_ratio > 2.5:  # Перевод слишком длинный
                            self.issues.append(QualityIssue(
                                severity="WARNING",
                                file=ts_file.name,
                                context=ctx_text,
                                source=source_text,
                                translation=translation_text,
                                issue_type="translation_too_long",
                                description=f"Перевод слишком длинный (в {length_ratio:.1f} раз длиннее оригинала)"
                            ))
                        elif length_ratio < 0.3:  # Перевод слишком короткий
                            self.issues.append(QualityIssue(
                                severity="WARNING",
                                file=ts_file.name,
                                context=ctx_text,
                                source=source_text,
                                translation=translation_text,
                                issue_type="translation_too_short",
                                description=f"Перевод слишком короткий (в {1/length_ratio:.1f} раз короче оригинала)"
                            ))
            except ET.ParseError:
                pass

    def check_character_consistency(self) -> None:
        """Проверить использование правильных символов для языка."""
        for ts_file in self.ts_files:
            lang_code = ts_file.stem.split("_")[-1]
            
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for message in context.findall("message"):
                        source = message.find("source")
                        translation = message.find("translation")
                        
                        if source is None or translation is None:
                            continue
                        
                        source_text = source.text or ""
                        translation_text = translation.text or ""
                        
                        # Проверяем смешанные языки
                        if lang_code in ["ru", "uk"]:
                            # Для кириллических языков не должно быть латиницы в переводах
                            if LATIN_PATTERN.search(translation_text) and CYRILLIC_PATTERN.search(translation_text):
                                self.issues.append(QualityIssue(
                                    severity="ERROR",
                                    file=ts_file.name,
                                    context=ctx_text,
                                    source=source_text,
                                    translation=translation_text,
                                    issue_type="mixed_scripts",
                                    description="Смешанные кириллица и латиница в переводе"
                                ))
            except ET.ParseError:
                pass

    def check_terminology_consistency(self) -> None:
        """Проверить консистентность терминологии."""
        for ts_file in self.ts_files:
            lang_code = ts_file.stem.split("_")[-1]
            
            if lang_code not in TERMINOLOGY:
                continue
                
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for message in context.findall("message"):
                        source = message.find("source")
                        translation = message.find("translation")
                        
                        if source is None or translation is None:
                            continue
                        
                        source_text = source.text or ""
                        translation_text = translation.text or ""
                        
                        # Проверяем терминологию
                        source_lower = source_text.lower()
                        translation_lower = translation_text.lower()
                        
                        for term, variants in TERMINOLOGY[lang_code].items():
                            if term in source_lower:
                                # Проверяем, используется ли правильный термин в переводе
                                if not any(variant in translation_lower for variant in variants):
                                    self.issues.append(QualityIssue(
                                        severity="INFO",
                                        file=ts_file.name,
                                        context=ctx_text,
                                        source=source_text,
                                        translation=translation_text,
                                        issue_type="terminology_inconsistency",
                                        description=f"Термин '{term}' переведен нестандартно. Ожидаемые варианты: {variants}"
                                    ))
            except ET.ParseError:
                pass

    def check_html_tags(self) -> None:
        """Проверить сохранение HTML тегов."""
        for ts_file in self.ts_files:
            try:
                tree = ET.parse(ts_file)
                root = tree.getroot()
                
                for context in root.findall("context"):
                    ctx_name = context.find("name")
                    ctx_text = ctx_name.text if ctx_name is not None else "Unknown"
                    
                    for message in context.findall("message"):
                        source = message.find("source")
                        translation = message.find("translation")
                        
                        if source is None or translation is None:
                            continue
                        
                        source_text = source.text or ""
                        translation_text = translation.text or ""
                        
                        # Проверяем HTML теги
                        source_tags = set(HTML_TAG_PATTERN.findall(source_text))
                        translation_tags = set(HTML_TAG_PATTERN.findall(translation_text))
                        
                        if source_tags != translation_tags:
                            self.issues.append(QualityIssue(
                                severity="ERROR",
                                file=ts_file.name,
                                context=ctx_text,
                                source=source_text,
                                translation=translation_text,
                                issue_type="html_tag_mismatch",
                                description=f"HTML теги не совпадают: {source_tags} vs {translation_tags}"
                            ))
            except ET.ParseError:
                pass

    def print_report(self) -> bool:
        """Вывести отчет о качестве."""
        errors = [i for i in self.issues if i.severity == "ERROR"]
        warnings = [i for i in self.issues if i.severity == "WARNING"]
        infos = [i for i in self.issues if i.severity == "INFO"]
        
        if errors:
            print("🔴 ОШИБКИ:")
            for issue in errors:
                print(f"  [{issue.file}] {issue.context}")
                print(f"    {issue.issue_type}: {issue.description}")
                print(f"    Исходник: '{issue.source}'")
                print(f"    Перевод: '{issue.translation}'")
                print()
        
        if warnings:
            print("🟡 ПРЕДУПРЕЖДЕНИЯ:")
            for issue in warnings:
                print(f"  [{issue.file}] {issue.context}")
                print(f"    {issue.issue_type}: {issue.description}")
                print(f"    Исходник: '{issue.source}'")
                print(f"    Перевод: '{issue.translation}'")
                print()
        
        if infos:
            print("ℹ️  ИНФОРМАЦИЯ:")
            for issue in infos:
                print(f"  [{issue.file}] {issue.context}")
                print(f"    {issue.issue_type}: {issue.description}")
                print()
        
        if not self.issues:
            print("✅ Все проверки качества прошли успешно!")
            return True
        
        print(f"📊 Итого: {len(errors)} ошибок, {len(warnings)} предупреждений, {len(infos)} замечаний")
        return len(errors) == 0


def main() -> int:
    """Основная функция."""
    i18n_dir = Path(__file__).parent
    validator = TranslationQualityValidator(i18n_dir)
    
    success = validator.validate_all()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())


