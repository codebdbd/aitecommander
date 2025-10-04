"""Utilities for creating and configuring the root `QApplication` instance."""

import sys

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.config_data.qt_adapters import load_and_install_translator


def create_application() -> QApplication:
    """Create and configure the main `QApplication` instance."""
    # Включаем HiDPI-атрибуты до создания экземпляра приложения
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except Exception:
        # Безопасный фолбэк: атрибуты могут быть недоступны в некоторых окружениях/версиях
        pass

    # Создаём экземпляр приложения (тест ожидает прямой вызов конструктора)
    app = QApplication(sys.argv)

    cfg = app_config
    settings_cfg = cfg.settings
    paths_cfg = cfg.paths
    ui_cfg = cfg.ui

    # Application identity sourced from configuration
    try:
        app.setApplicationName(settings_cfg.get_app_name())
        app.setOrganizationName(settings_cfg.get_org_name())
        app.setApplicationVersion(settings_cfg.get_app_version())
    except Exception:
        pass

    # Update locale defaults and install translator if configured
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
                # Keep a strong reference on the application instance
                app._app_translator = translator  # type: ignore[attr-defined]
    except Exception:
        # Translator is optional; fallback silently on failure
        pass

    # Базовый шрифт приложения (ожидается тестом):
    # Замечание: темы и размеры могут переопределяться позднее ThemeController'ом,
    # но здесь задаём стартовые значения по умолчанию (конфигурируемые с фолбэком).
    try:
        font = ui_cfg.get_application_font()
        if not font or not isinstance(font, QFont):
            raise TypeError("Invalid font object returned from configuration")
        if not font.family():
            font.setFamily("Segoe UI")
        if font.pointSize() <= 0:
            font.setPointSize(10)
        app.setFont(font)
    except Exception:
        # В крайнем случае — безопасный дефолт
        app.setFont(QFont("Arial", 10))

    return app
