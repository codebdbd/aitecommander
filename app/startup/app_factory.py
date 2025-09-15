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

logger = logging.getLogger(__name__)


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
    except (AttributeError, RuntimeError) as e:
        # Безопасный фолбэк: атрибуты могут быть недоступны в некоторых окружениях/версиях
        logger.warning("[app_factory] Не удалось установить HiDPI атрибуты: %s", e)

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
    # Опционально читаем конфиг, если доступен
    try:
        from app.config_data.base_config import get_app_config  # type: ignore
    except ImportError as e:
        logger.warning("[app_factory] Конфиг не найден: %s — используем дефолтные шрифты", e)
    else:
        try:
            cfg = get_app_config()
            font_cfg = getattr(cfg, "ui_font", None) or {}
            font_family = str(font_cfg.get("family", font_family))
            font_size = int(font_cfg.get("size", font_size))
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            logger.warning(
                "[app_factory] Некорректные параметры ui_font в конфиге: %s — используем дефолты",
                e,
            )
        except Exception as e:
            # Неожиданная ошибка в конфиге — прерываем запуск явно
            logger.exception("[app_factory] Неожиданная ошибка при чтении конфига")
            raise

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
