# app/controllers/database_controller.py

import os
import shutil
import zipfile

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.db import Database
from app.utils.db.db_error_handler import handle_db_error
from app.utils.ui.icon.path_service import icon_path_service
from app.views.dialogs.database_dialogs import DatabaseDialogs


class DatabaseController(QObject):
    """Контроллер для управления операциями с базой данных и иконками.

    Использует сигналы для уведомления UI об операциях вместо прямого
    обращения к main_window.
    """

    # Сигналы для уведомления UI
    database_restored = pyqtSignal(object)  # Database - новая БД после восстановления
    database_connected = pyqtSignal(object)  # Database - новая БД после подключения
    database_saved = pyqtSignal(str)  # str - путь к сохраненной копии
    favorites_cleared = pyqtSignal()  # Избранное очищено
    icons_exported = pyqtSignal(str)  # str - путь к экспортированному архиву
    icons_imported = pyqtSignal(int)  # int - количество импортированных иконок
    operation_error = pyqtSignal(str, str)  # str, str - заголовок, сообщение об ошибке
    operation_success = pyqtSignal(
        str, str
    )  # str, str - заголовок, сообщение об успехе

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.dialogs = DatabaseDialogs(parent)

    def handle_clear_favorites(self):
        """Обработчик очистки избранного.

        Без подтверждения и без информационного окна: сразу отправляет
        сигнал для очистки избранного. UI выполнит очистку через контроллеры.
        """
        # Отправляем сигнал - UI сам обработает очистку и обновление
        self.favorites_cleared.emit()

    def handle_restore_database(self):
        """Обработчик восстановления базы данных из резервной копии."""
        from app.views.dialogs.restore_db_dialog import RestoreDbDialog

        dlg = RestoreDbDialog(parent=self.parent())
        if dlg.exec() == dlg.DialogCode.Accepted:
            selected = dlg.get_selected_backup()
            if selected:
                self._perform_database_restore(selected)

    def _perform_database_restore(self, backup_path):
        """Выполнить восстановление базы данных.

        Только бизнес-логика восстановления. UI обновляется через сигналы.
        """
        db_path = getattr(self.db, "db_path", None)
        if not db_path:
            self.operation_error.emit("Ошибка", "Путь к базе данных не найден.")
            return

        if self.dialogs.confirm_database_restore(backup_path.name):
            try:
                # Закрываем старое подключение
                self.db.close()

                # Копируем резервную копию
                shutil.copy2(backup_path, db_path)

                # Создаем новое подключение к базе данных
                new_db = Database()
                self.db = new_db

                # Уведомляем UI через сигнал - он сам обновит все зависимости
                self.database_restored.emit(new_db)
                self.operation_success.emit(
                    "Готово", f"База восстановлена из копии:\n{backup_path.name}"
                )

            except Exception as e:
                self.operation_error.emit("Ошибка", f"Ошибка восстановления: {e}")

    def handle_connect_database(self):
        """Обработчик подключения другой базы данных."""
        db_path = getattr(self.db, "db_path", None)
        if not db_path:
            self.operation_error.emit("Ошибка", "Путь к базе данных не найден.")
            return

        file_path = self.dialogs.get_connect_file()
        if file_path:
            self._perform_database_connection(str(file_path), db_path)

    def _perform_database_connection(self, file_path: str, db_path: str):
        """Выполнить подключение базы данных.

        Только бизнес-логика подключения. UI обновляется через сигналы.
        """
        backup_path = db_path + ".bak"
        try:
            # Закрыть соединение с базой
            self.db.close()
            # Сделать резервную копию текущей базы
            shutil.copy2(db_path, backup_path)
            # Заменить файл базы
            shutil.copy2(file_path, db_path)

            # Создаем новое подключение к базе данных
            new_db = Database()
            self.db = new_db

            # Уведомляем UI через сигнал - он сам обновит все зависимости
            self.database_connected.emit(new_db)
            self.operation_success.emit("Готово", "База успешно подключена!")

        except Exception as e:
            # Используем централизованный обработчик ошибок
            if not handle_db_error(e, self):
                # В случае ошибки восстановить старую базу
                try:
                    shutil.copy2(backup_path, db_path)
                except Exception:
                    pass
                self.operation_error.emit(
                    "Ошибка",
                    f"Ошибка при подключении базы: {e}\nСтарая база восстановлена.",
                )

    def handle_save_database(self):
        """Обработчик сохранения копии базы данных."""
        db_path = getattr(self.db, "db_path", None)
        if not db_path:
            self.operation_error.emit("Ошибка", "Путь к базе данных не найден.")
            return

        default_name = (
            db_path.split("/")[-1] if "/" in db_path else db_path.split("\\")[-1]
        )
        save_path = self.dialogs.get_save_location(default_name)

        if save_path:
            try:
                shutil.copy2(db_path, str(save_path))
                self.database_saved.emit(str(save_path))
                self.operation_success.emit(
                    "Готово", f"Копия базы сохранена:\n{save_path}"
                )
            except Exception as e:
                self.operation_error.emit("Ошибка", f"Ошибка сохранения: {e}")

    def handle_save_icons(self):
        """Обработчик сохранения архива иконок."""
        icons_dir = icon_path_service.get_user_icons_dir()
        if not os.path.isdir(icons_dir):
            self.operation_error.emit("Ошибка", f"Папка иконок не найдена: {icons_dir}")
            return

        save_path = self.dialogs.get_icons_archive_location("icons.zip")

        if save_path:
            try:
                with zipfile.ZipFile(str(save_path), "w", zipfile.ZIP_DEFLATED) as zipf:
                    for fname in os.listdir(icons_dir):
                        fpath = os.path.join(icons_dir, fname)
                        if os.path.isfile(fpath):
                            zipf.write(fpath, fname)
                self.icons_exported.emit(str(save_path))
                self.operation_success.emit(
                    "Готово", f"Архив иконок сохранён в:\n{save_path}"
                )
            except Exception as e:
                self.operation_error.emit("Ошибка", f"Ошибка при создании архива: {e}")

    def handle_load_icons(self):
        """Обработчик загрузки архива иконок."""
        icons_dir = icon_path_service.get_user_icons_dir()
        if not os.path.isdir(icons_dir):
            os.makedirs(icons_dir, exist_ok=True)

        zip_path = self.dialogs.get_icons_archive_to_load()

        if zip_path:
            try:
                icon_count = 0
                with zipfile.ZipFile(zip_path, "r") as zipf:
                    zipf.extractall(icons_dir)
                    icon_count = len(zipf.namelist())
                self.icons_imported.emit(icon_count)
                self.operation_success.emit(
                    "Готово", f"Иконки успешно добавлены в: {icons_dir}"
                )
            except Exception as e:
                self.operation_error.emit("Ошибка", f"Ошибка при загрузке архива: {e}")
