"""Модуль для создания и настройки QApplication."""

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication


def create_application() -> QApplication:
    """
    Создает и настраивает QApplication.

    Returns:
        QApplication: Настроенный экземпляр приложения
    """
    # Включаем HiDPI-атрибуты до создания экземпляра приложения
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except Exception:
        # Безопасный фолбэк: атрибуты могут быть недоступны в некоторых окружениях/версиях
        pass

    # Создаём экземпляр приложения (тест ожидает прямой вызов конструктора)
    app = QApplication(sys.argv)

    # Базовая идентификация приложения
    app.setApplicationName("MyPyQtApp")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("MyCompany")
    # Домены используются в путях настроек/кэша на некоторых платформах
    try:
        app.setOrganizationDomain("mycompany.example")
    except Exception:
        pass

    # Базовый шрифт приложения (ожидается тестом):
    # Замечание: темы и размеры могут переопределяться позднее ThemeController'ом,
    # но здесь задаём стартовые значения по умолчанию (конфигурируемые с фолбэком).
    font_family = "Arial"
    font_size = 10
    try:
        # Опционально читаем конфиг, если доступен
        from app.config_data.base_config import get_app_config  # type: ignore

        cfg = get_app_config()
        font_cfg = getattr(cfg, "ui_font", None) or {}
        font_family = str(font_cfg.get("family", font_family))
        font_size = int(font_cfg.get("size", font_size))
    except Exception:
        # Если конфиг недоступен/содержит ошибку — используем дефолты
        pass

    try:
        app.setFont(QFont(font_family, font_size))
    except Exception:
        # В крайнем случае — безопасный дефолт
        app.setFont(QFont("Arial", 10))

    return app
