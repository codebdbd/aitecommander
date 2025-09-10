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

    # Базовый шрифт приложения (ожидается тестом):
    # Замечание: темы и размеры могут переопределяться позднее ThemeController'ом,
    # но здесь задаём стартовые значения по умолчанию.
    app.setFont(QFont("Arial", 10))

    return app
