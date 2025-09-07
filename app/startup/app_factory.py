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
    
    # Централизовано: фиксируем базовый размер шрифта приложения на 10 pt (DPI‑дружественно)
    app.setFont(QFont(app.font().family(), 10))
    
    return app
