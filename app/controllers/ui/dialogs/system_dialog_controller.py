# app/controllers/system_dialog_controller.py

import logging

from app.config_data import app_config

from .dialog_manager import DialogManager

logger = logging.getLogger(__name__)


class SystemDialogController:
    """Контроллер для управления системными диалогами."""

    def __init__(self, main_window):
        self.main_window = main_window

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
            self.main_window.links_business,
        )

        if success:
            # Создаем резервную копию после большой операции импорта
            try:
                dc = getattr(self.main_window, "database_controller", None)
                db = getattr(dc, "db", None)
                if db is not None:
                    db.backup()
            except Exception as backup_err:
                logger.warning(
                    f"Не удалось создать резервную копию после импорта закладок: {backup_err}"
                )
            # Обновить дерево категорий и таблицу ссылок
            if hasattr(self.main_window, "structure_business"):
                self.main_window.structure_business.load_structure()
            category_id = self.main_window.get_current_category_id()
            if category_id:
                # Централизовано: обновляем таблицу через LinksTableController, без прямого UI
                try:
                    ctrl = getattr(self.main_window, "links_table_controller", None)
                    if ctrl:
                        ctrl.reload(category_id)
                    else:
                        links_business = getattr(self.main_window, "links_business", None)
                        if links_business:
                            links_business.load_links(category_id)
                except Exception as _e:
                    logger.debug("SystemDialogController: reload after import failed: %s", _e)
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
        title = app_config.get_about_title()
        text = app_config.get_about_text()
        details = getattr(app_config, "get_version", lambda: None)()
        DialogManager.show_info(
            self.main_window,
            title,
            text,
            informative_text="Спасибо, что используете наше приложение!",
            details=f"Версия: {details}" if details else None,
        )

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
