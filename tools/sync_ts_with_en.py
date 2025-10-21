from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

I18N_DIR = Path(__file__).resolve().parents[1] / "i18n"
EN_FILE = I18N_DIR / "app_en.ts"
TARGET_FILES = [
    I18N_DIR / "app_ru.ts",
    I18N_DIR / "app_uk.ts",
    I18N_DIR / "app_fr.ts",
    I18N_DIR / "app_es.ts",
    I18N_DIR / "app_de.ts",
]

LANGUAGE_CODES = {
    "app_en.ts": "en_GB",
    "app_ru.ts": "ru_RU",
    "app_uk.ts": "uk_UA",
    "app_fr.ts": "fr_FR",
    "app_es.ts": "es_ES",
    "app_de.ts": "de_DE",
}


def message_key(context_name: str, message: ET.Element) -> tuple:
    source = message.findtext("source") or ""
    numerus = message.get("numerus", "")
    locations = tuple(
        (loc.get("filename", ""), loc.get("line", ""))
        for loc in message.findall("location")
    )
    extracomments = tuple(
        (elem.text or "") for elem in message.findall("extracomment")
    )
    comments = tuple((elem.text or "") for elem in message.findall("comment"))
    translator_comments = tuple(
        (elem.text or "") for elem in message.findall("translatorcomment")
    )
    return (
        context_name,
        source,
        numerus,
        locations,
        extracomments,
        comments,
        translator_comments,
    )


def build_translation_map(path: Path) -> dict[tuple, ET.Element]:
    tree = ET.parse(path)
    root = tree.getroot()
    mapping: dict[tuple, ET.Element] = {}
    for context in root.findall("context"):
        name = context.findtext("name") or ""
        for message in context.findall("message"):
            key = message_key(name, message)
            translation = message.find("translation")
            if translation is None:
                continue
            mapping[key] = copy.deepcopy(translation)
    return mapping


def sync_language(path: Path, en_root: ET.Element, translation_map: dict[tuple, ET.Element]) -> None:
    new_root = copy.deepcopy(en_root)
    language_code = LANGUAGE_CODES.get(path.name)
    if language_code:
        new_root.set("language", language_code)

    for context in new_root.findall("context"):
        name = context.findtext("name") or ""
        for message in context.findall("message"):
            key = message_key(name, message)
            translation = message.find("translation")
            if translation is None:
                continue
            existing = translation_map.get(key)
            message.remove(translation)
            if existing is not None:
                message.append(copy.deepcopy(existing))
            else:
                new_translation = ET.Element("translation")
                new_translation.set("type", "unfinished")
                message.append(new_translation)

    ET.ElementTree(new_root).write(path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    en_tree = ET.parse(EN_FILE)
    en_root = en_tree.getroot()

    for target_path in TARGET_FILES:
        translation_map = build_translation_map(target_path)
        sync_language(target_path, en_root, translation_map)


if __name__ == "__main__":
    main()
