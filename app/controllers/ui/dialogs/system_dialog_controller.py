# app/controllers/system_dialog_controller.py

import logging

from app.config_data import app_config

from .dialog_manager import DialogManager

logger = logging.getLogger(__name__)


class SetupError(Exception):
    """Ошибка настройки зависимостей SystemDialogController."""


class SystemDialogController:
    """Контроллер для управления системными диалогами."""

    def __init__(
        self,
        main_window,
        *,
        database_controller,
        links_table_controller,
        links_business,
    ):
        self.main_window = main_window
        self.database_controller = database_controller
        self.links_table_controller = links_table_controller
        self.links_business = links_business
        # Валидация обязательных зависимостей
        if self.database_controller is None:
            raise SetupError("SystemDialogController requires 'database_controller'")
        if self.links_table_controller is None:
            raise SetupError("SystemDialogController requires 'links_table_controller'")
        if self.links_business is None:
            raise SetupError("SystemDialogController requires 'links_business'")

    def handle_import_browser_bookmarks(self):
        """Импорт закладок браузера."""
        from app.utils.browser.import_browser_html import BrowserBookmarksImporter
        from app.views.dialogs.import_browser_dialog import ImportBrowserDialog

        importer = BrowserBookmarksImporter()

        # 1) Выбор файла
        path = importer.select_file(self.main_window)
        if not path:
            return

        # 2) Парсинг
        try:
            categories = importer.parse_bookmarks(path)
        except Exception as e:
            DialogManager.show_error(
                self.main_window,
                "Импорт из браузера",
                "Ошибка чтения HTML файла.",
                informative_text="Проверьте целостность файла и права доступа.",
                details=str(e),
            )
            return
        if not any(categories.values()):
            DialogManager.show_warning(
                self.main_window,
                "Импорт из браузера",
                "В файле не найдено ни одной ссылки.",
                informative_text=(
                    "Экспортируйте закладки из браузера в формате HTML и выберите корректный файл."
                ),
                details=f"file={path}",
            )
            return

        # 3) Выбор раздела
        dlg = ImportBrowserDialog(self.main_window.structure_business, self.main_window)
        if dlg.exec() != dlg.DialogCode.Accepted:  # QDialog.DialogCode.Accepted
            return
        section_id = dlg.get_selected_section_id()
        if not section_id:
            DialogManager.show_warning(
                self.main_window,
                "Импорт из браузера",
                "Не выбран раздел для импорта.",
                informative_text="Выберите раздел, в который будут добавлены категории и ссылки.",
            )
            return

        # 4) Синхронизация в БД
        success, msg, added = importer.sync_to_db(
            categories,
            section_id,
            self.main_window.structure_business,
            self.links_business,
        )

        if success:
            # Создаем резервную копию асинхронно после большой операции импорта
            try:
                db = getattr(self.database_controller, "db", None)
                if db is None:
                    raise SetupError("database_controller.db is required for backup")
                
                # Используем async backup чтобы не блокировать UI
                db.backup_async(
                    on_finished=lambda result: logger.info(f"Резервная копия создана: {result.get('backup_filename')}"),
                    on_error=lambda e, tb: logger.warning(f"Не удалось создать резервную копию: {e}")
                )
            except SetupError:
                logger.exception(
                    "SystemDialogController: backup failed due to setup error"
                )
                raise
            except Exception as backup_err:
                logger.warning(
                    f"Не удалось запустить резервное копирование: {backup_err}"
                )
            # Обновить дерево категорий и таблицу ссылок
            if hasattr(self.main_window, "structure_business"):
                self.main_window.structure_business.load_structure()
            category_id = self.main_window.get_current_category_id()
            if category_id:
                # Централизовано: обновляем таблицу через LinksTableController, без getattr/fallback
                try:
                    if not hasattr(self.links_table_controller, "reload"):
                        raise SetupError("links_table_controller must expose reload()")
                    self.links_table_controller.reload(category_id)
                except SetupError:
                    logger.exception(
                        "SystemDialogController: reload after import failed (setup error)"
                    )
                    raise
                except Exception as _e:
                    logger.debug(
                        "SystemDialogController: reload after import failed: %s", _e
                    )
            self.main_window.update_statusbar()
            DialogManager.show_info(
                self.main_window,
                "Импорт из браузера",
                msg,
            )
        else:
            DialogManager.show_error(
                self.main_window,
                "Импорт из браузера",
                "Импорт завершился с ошибкой",
                details=msg,
            )

    def show_about_dialog(self):
        """Показать диалог О программе."""
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtCore import Qt
        
        title = app_config.get_about_title()
        text = app_config.get_about_text()
        
        msg_box = QMessageBox(self.main_window)
        msg_box.setIcon(QMessageBox.Icon.NoIcon)  # Без иконки = без звука
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setTextFormat(Qt.TextFormat.PlainText)  # Важно: правильно обрабатывает \n
        msg_box.setInformativeText("Спасибо, что используете наше приложение!")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def show_settings_dialog(self):
        """Показать диалог настроек."""
        from app.views.dialogs.entity_dialogs import SettingsDialog

        dlg = SettingsDialog(
            self.main_window.settings,
            self.main_window.theme_ctrl,
            parent=self.main_window,
        )
        dlg.exec()

    def show_file_search_dialog(self):
        """Показать диалог поиска файлов."""
        from app.views.dialogs.file_search_dialog.file_search_dialog import (
            FileSearchDialog,
        )

        dialog = FileSearchDialog(self.main_window)
        dialog.exec()
