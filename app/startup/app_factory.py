"""Модуль для создания и настройки QApplication.

Политика обработки ошибок:
- Ожидаемые ошибки окружения (например, недоступные атрибуты Qt,
  отсутствие модуля конфигурации) перехватываются точечно и ведут к
  безопасным значениям по умолчанию с логированием предупреждения.
- Неожиданные ошибки (в том числе логические/программные) логируются
  через logger.exception и повторно пробрасываются, чтобы запуск
  приложения завершался с явной причиной.
"""

import sys
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

# Опционально используем централизованный конфиг, если доступен
try:
    from app.config_data import app_config  # type: ignore
except Exception:  # pragma: no cover
    app_config = None  # type: ignore

logger = logging.getLogger(__name__)


def create_application() -> QApplication:
    """
    Создает и настраивает QApplication.

    Returns:
        QApplication: Настроенный экземпляр приложения
    """
    # Включаем HiDPI-атрибуты до создания экземпляра приложения (только если доступны в Qt)
    try:
        aa_enable = getattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling", None)
        if aa_enable is not None:
            QApplication.setAttribute(aa_enable, True)
        aa_pixmaps = getattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps", None)
        if aa_pixmaps is not None:
            QApplication.setAttribute(aa_pixmaps, True)
    except Exception as e:
        # Не критично: просто зафиксируем в debug, не шумим предупреждениями для Qt6
        logger.debug("[app_factory] HiDPI attribute setup skipped: %s", e, exc_info=True)

    # Создаём экземпляр приложения (тест ожидает прямой вызов конструктора)
    app = QApplication(sys.argv)

    # Базовая идентификация приложения
    app.setApplicationName("MyPyQtApp")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("MyCompany")
    # Домены используются в путях настроек/кэша на некоторых платформах
    try:
        app.setOrganizationDomain("mycompany.example")
    except (AttributeError, RuntimeError) as e:
        logger.warning("[app_factory] Не удалось задать OrganizationDomain: %s", e)

    # Базовый шрифт приложения (ожидается тестом):
    # Замечание: темы и размеры могут переопределяться позднее ThemeController'ом,
    # но здесь задаём стартовые значения по умолчанию (конфигурируемые с фолбэком).
    font_family = "Arial"
    font_size = 10
    # Опционально читаем параметры шрифта из app_config, если доступно
    try:
        if app_config is not None:
            # Ожидаем словарь ui_font = {"family": str, "size": int}, если присутствует
            ui_font = None
            try:
                ui_font = app_config.get("ui_font", None)
            except Exception:
                ui_font = None
            if isinstance(ui_font, dict):
                font_family = str(ui_font.get("family", font_family))
                try:
                    font_size = int(ui_font.get("size", font_size))
                except Exception:
                    font_size = font_size
    except Exception as e:
        logger.debug("[app_factory] app_config ui_font read failed: %s", e, exc_info=True)

    try:
        app.setFont(QFont(font_family, font_size))
    except (TypeError, RuntimeError) as e:
        # В крайнем случае — безопасный дефолт
        logger.warning(
            "[app_factory] Не удалось применить шрифт (%s, %s): %s — откат к дефолту",
            font_family,
            font_size,
            e,
        )
        app.setFont(QFont("Arial", 10))

    return app
