"""Release regressions: clean profiles and compiled Ukrainian translations."""
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QTranslator
from PyQt6.QtWidgets import QApplication, QButtonGroup, QWidget

from scripts.audit_translations import ROOT, catalog_keys, source_keys


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("name", ["AI", "Work", "Study", "Personal", "Custom"])
@pytest.mark.parametrize("stored_icon", ["", "missing.png"])
def test_sphere_icons_in_relocated_bundle(qt_app, monkeypatch, tmp_path, name, stored_icon):
    from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
    from app.core.paths.path_manager import PathManager
    from app.utils.ui.icon.path_service import icon_path_service

    bundle = tmp_path / "bundle"
    icons = bundle / "app/resources/ui_icons"
    icons.mkdir(parents=True)
    for filename in ("ai_icon.png", "work_icon.png", "study_icon.png", "personal_icon.png", "section.png"):
        shutil.copyfile(ROOT / "app/resources/ui_icons" / filename, icons / filename)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(icon_path_service, "_ui_icons_dir", None)
    assert PathManager.ui_icons_dir() == icons
    window = SimpleNamespace(structure_business=None, structure=None,
                             sphere_group=QButtonGroup(), spheres_bar=QWidget(), sphere_buttons={})
    controller = SpheresBarController(window)
    button = controller._build_button({"id": 1, "name": name, "icon_path": stored_icon})
    assert not button.icon().isNull()
    assert not button.icon().pixmap(64, 64).isNull()


def test_ukrainian_catalog_covers_source_keys():
    catalog = catalog_keys(ROOT / "i18n/app_uk.ts")
    assert not [key for key in source_keys() if not catalog.get(key)]


def test_compiled_ukrainian_matches_catalog(qt_app):
    translator = QTranslator()
    assert translator.load(str(ROOT / "i18n/app_uk.qm"))
    for context in ET.parse(ROOT / "i18n/app_uk.ts").getroot().findall("context"):
        for message in context.findall("message"):
            source = message.findtext("source")
            translation = message.find("translation")
            forms = translation.findall("numerusform")
            variants = zip((1, 2, 5), [form.text for form in forms]) if forms else [(-1, translation.text)]
            for number, expected in variants:
                assert translator.translate(context.findtext("name"), source.encode("utf-8"), None, number) == expected, source
                assert sorted(re.findall(r"\{[^{}]*\}", source)) == sorted(re.findall(r"\{[^{}]*\}", expected)), source
