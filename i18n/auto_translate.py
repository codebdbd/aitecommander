"""
Auto-translate Qt .ts files using a simple glossary and fallback to source text.

Usage:
  python i18n/auto_translate.py --lang ru i18n/app_ru.ts
  python i18n/auto_translate.py --lang uk i18n/app_uk.ts

Notes:
- Preserves placeholders like %n, %1, %2 and ampersands & for shortcuts.
- For plural messages (<numerusform>), fills each form identically (safe default).
- Glossary is conservative: replaces common UI terms; otherwise copies source.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

# Very conservative placeholder pattern (Qt style)
PLACEHOLDER_RE = re.compile(r"%(?:\d+|n)")

# Централизованный словарь переводов для автоперевода
# Структура: {source_lang: {target_lang: [(source_term, target_term), ...]}}
TRANSLATION_GLOSSARIES = {
    "en": {
        "ru": [
            ("dark theme", "тёмная тема"),
            ("light theme", "светлая тема"),
            ("favorites", "избранное"),
            ("recent", "недавние"),
            ("settings", "настройки"),
            ("search", "поиск"),
            ("about", "о программе"),
            ("file", "файл"),
            ("open", "открыть"),
            ("save", "сохранить"),
            ("cancel", "отмена"),
            ("delete", "удалить"),
            ("edit", "изменить"),
            ("apply", "применить"),
            ("close", "закрыть"),
            ("ok", "ок"),
            ("yes", "да"),
            ("no", "нет"),
            ("undo", "отменить"),
            ("redo", "повторить"),
            ("import", "импорт"),
            ("export", "экспорт"),
            ("link", "ссылка"),
            ("section", "раздел"),
            ("category", "категория"),
        ],
        "uk": [
            ("dark theme", "темна тема"),
            ("light theme", "світла тема"),
            ("favorites", "обране"),
            ("recent", "нещодавні"),
            ("settings", "налаштування"),
            ("search", "пошук"),
            ("about", "про програму"),
            ("file", "файл"),
            ("open", "відкрити"),
            ("save", "зберегти"),
            ("cancel", "скасувати"),
            ("delete", "видалити"),
            ("edit", "редагувати"),
            ("apply", "застосувати"),
            ("close", "закрити"),
            ("ok", "гаразд"),
            ("yes", "так"),
            ("no", "ні"),
            ("undo", "скасувати"),
            ("redo", "повторити"),
            ("import", "імпорт"),
            ("export", "експорт"),
            ("link", "посилання"),
            ("section", "розділ"),
            ("category", "категорія"),
        ],
    },
    "ru": {
        "uk": [
            ("тёмная тема", "темна тема"),
            ("светлая тема", "світла тема"),
            ("избранное", "обране"),
            ("недавние", "нещодавні"),
            ("настройки", "налаштування"),
            ("поиск", "пошук"),
            ("о программе", "про програму"),
            ("файл", "файл"),
            ("открыть", "відкрити"),
            ("сохранить", "зберегти"),
            ("отмена", "скасувати"),
            ("удалить", "видалити"),
            ("изменить", "редагувати"),
            ("применить", "застосувати"),
            ("закрыть", "закрити"),
            ("да", "так"),
            ("нет", "ні"),
            ("отменить", "скасувати"),
            ("повторить", "повторити"),
            ("импорт", "імпорт"),
            ("экспорт", "експорт"),
            ("ссылка", "посилання"),
            ("раздел", "розділ"),
            ("категория", "категорія"),
        ],
    },
}


def _apply_glossary(text: str, target_lang: str, source_lang: str = "en") -> str:
    """Применить словарь переводов к тексту.

    Args:
        text: Исходный текст для перевода
        target_lang: Целевой язык (ru, uk)
        source_lang: Исходный язык (по умолчанию en)

    Returns:
        Переведенный текст или оригинал, если перевод не найден
    """
    if not text:
        return text

    lowered = text.lower()

    def replace_using(pairs: list[tuple[str, str]], src: str) -> tuple[str, bool]:
        """Заменить термины в тексте используя словарь."""
        out = src
        hit = False
        for k, v in pairs:
            if k in out:
                out = out.replace(k, v)
                hit = True
        return out, hit

    # Получаем словарь для перевода
    glossary = TRANSLATION_GLOSSARIES.get(source_lang, {}).get(target_lang, [])
    
    if not glossary:
        return text

    # Применяем перевод
    out, hit = replace_using(glossary, lowered)
    return text if not hit else _reconstruct_case(text, out)


def _reconstruct_case(original: str, lowered_out: str) -> str:
    """Reconstruct basic case by mapping words positionally from original to lowered_out.
    Conservative: splits by word boundaries and keeps punctuation/spacing from original.
    """
    # Simple fallback: if lengths differ wildly, return lowered_out with original placeholders kept
    # Replace placeholders back from original
    result = []
    for o_ch, t_ch in zip(original, lowered_out):
        if o_ch.isupper():
            result.append(t_ch.upper())
        else:
            result.append(t_ch)
    # If lowered_out longer than original, append tail
    if len(lowered_out) > len(original):
        result.append(lowered_out[len(original):])
    out = "".join(result)

    # Restore placeholders exactly from original if present
    # (naive but effective as we usually preserved text shape)
    for m in PLACEHOLDER_RE.finditer(original):
        ph = m.group(0)
        # place it back at same position if possible
        start = m.start()
        if start + len(ph) <= len(out):
            out = out[:start] + ph + out[start + len(ph):]
    return out


def _fill_translation(message: ET.Element, lang: str) -> None:
    translation = message.find("translation")
    if translation is None:
        return

    # If already finished, do not overwrite
    if translation.get("type") not in ("unfinished", None):
        return

    # Plural handling
    numerus = message.get("numerus") == "yes"
    source_el = message.find("source")
    if source_el is None or source_el.text is None:
        return
    source_text = source_el.text

    if numerus:
        # Ensure child <numerusform> elements exist
        forms = translation.findall("numerusform")
        if not forms:
            # Create 3 forms as safe default
            for _ in range(3):
                el = ET.SubElement(translation, "numerusform")
                el.text = source_text
            forms = translation.findall("numerusform")
        for el in forms:
            src = el.text or source_text
            el.text = _apply_glossary(src, lang)
        translation.attrib.pop("type", None)
        return

    # Non-plural
    dst = translation.text or source_text
    dst2 = _apply_glossary(dst, lang)
    translation.text = dst2
    translation.attrib.pop("type", None)


def auto_translate_ts(path: Path, lang: str) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    for context in root.findall("context"):
        for message in context.findall("message"):
            _fill_translation(message, lang)
    tree.write(path, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ts_file", type=Path)
    ap.add_argument("--lang", required=True, choices=["ru", "uk"], help="Target language code")
    args = ap.parse_args()

    if not args.ts_file.exists():
        print(f"File not found: {args.ts_file}", file=sys.stderr)
        return 2
    auto_translate_ts(args.ts_file, args.lang)
    print(f"Auto-translated: {args.ts_file} for lang={args.lang}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
