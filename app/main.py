# app/main.py

import sys
from PyQt6.QtWidgets import QApplication
from app.settings import AppSettings
from app.models.db import Database
from app.controllers.ui import ThemeController
from app.views.main_window import MainWindow

def main():
    # Инициализация Qt-приложения
    app = QApplication(sys.argv)

    # Загружаем настройки пользователя
    settings = AppSettings()

    # Применяем выбранную тему (QSS)
    theme_ctrl = ThemeController(settings)
    theme_ctrl.apply(settings.get_theme())

    # Подключаемся к базе данных
    db = Database()

    # Создаем и показываем главное окно
    window = MainWindow(db, settings, theme_ctrl)
    window.show()

    # Запускаем цикл обработки событий
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
