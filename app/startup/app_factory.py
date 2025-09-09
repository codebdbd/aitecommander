"""Модуль для создания и настройки QApplication."""

import sys

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication


def create_application() -> QApplication:
    """
    Создает и настраивает QApplication.

    Returns:
        QApplication: Настроенный экземпляр приложения
    """
    app = QApplication(sys.argv)
    app.setApplicationName("MyPyQtApp")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("MyCompany")

    # Не задаём глобальный размер шрифта здесь. Все размеры управляются через ui.fonts.*
    # и применяются в ThemeController._build_config_overrides_qss().

    return app
