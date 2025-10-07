"""Utilities for creating and configuring the root `QApplication` instance."""

import sys

from PyQt6.QtCore import QLocale, Qt, QTranslator
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.config_data.qt_adapters import load_and_install_translator


def create_application() -> QApplication:
    """Create and configure the main `QApplication` instance."""
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    app = QApplication(sys.argv)

    cfg = app_config
    settings_cfg = cfg.settings
    paths_cfg = cfg.paths
    ui_cfg = cfg.ui

    try:
        app.setApplicationName(settings_cfg.get_app_name())
        app.setOrganizationName(settings_cfg.get_org_name())
        app.setApplicationVersion(settings_cfg.get_app_version())
    except Exception:
        pass

    try:
        preferred_locale = settings_cfg.get_preferred_locale()
        fallback_locale = settings_cfg.get_fallback_locale()
        translator_base = settings_cfg.get_qt_translator_base()
        translations_dir = paths_cfg.get_translations_dir()

        if preferred_locale:
            QLocale.setDefault(QLocale(preferred_locale))

        if translator_base:
            translator = load_and_install_translator(
                base_name=translator_base,
                locale=preferred_locale,
                translations_dir=translations_dir,
                application=app,
                fallback_locale=fallback_locale,
            )
            if translator is not None:
                app._translator = translator  # type: ignore[attr-defined]
    except (RuntimeError, AttributeError, TypeError, ValueError):
        pass

    font = ui_cfg.get_application_font()
    if not isinstance(font, QFont):
        font = QFont("Segoe UI", 10)
    else:
        if not font.family():
            font.setFamily("Segoe UI")
        if font.pointSize() <= 0:
            font.setPointSize(10)
    app.setFont(font)

    return app
