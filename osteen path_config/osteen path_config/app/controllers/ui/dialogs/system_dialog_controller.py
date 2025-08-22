# app/controllers/system_dialog_controller.py

from app.config_data import app_config

from .dialog_manager import DialogManager


class SystemDialogController:
    """Контроллер для управления системными диалогами."""
    
    def __init__(self, main_window):
        self.main_window = main_window
    
    def handle_import_browser_bookmarks(self):
        """Импорт закладок браузера."""
        from app.utils.browser.import_browser_html import import_browser_bookmarks_to_db
        success, msg = import_browser_bookmarks_to_db(
            self.main_window.structure_business, 
            self.main_window,
            self.main_window.links_business
        )
        if success:
            # Создаем резервную копию после большой операции импорта
            try:
                self.main_window.db.backup()
            except Exception as backup_err:
                import logging
                logging.warning(f"Не удалось создать резервную копию после импорта закладок: {backup_err}")
            # Обновить дерево категорий и таблицу ссылок
            if hasattr(self.main_window, 'structure_business'):
                self.main_window.structure_business.load_structure()
            category_id = self.main_window.get_current_category_id()
            if category_id:
                # ЦЕНТРАЛИЗОВАНО: Используем UIStateManager вместо прямого вызова links.load_category
                if hasattr(self.main_window, 'ui_state') and self.main_window.ui_state:
                    self.main_window.ui_state.update_category_without_stack_switch(category_id)
                else:
                    self.logger.error("UIStateManager not available in SystemDialogController")
            self.main_window.update_statusbar()
        # Ошибки и сообщения обрабатываются внутри import_browser_bookmarks_to_db
    
    def show_about_dialog(self):
        """Показать диалог О программе."""
        title = app_config.get_about_title()
        text = app_config.get_about_text()
        details = getattr(app_config, 'get_version', lambda: None)()
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
        dlg = SettingsDialog(self.main_window.settings, self.main_window.theme_ctrl, parent=self.main_window)
        dlg.exec()
    
    def show_file_search_dialog(self):
        """Показать диалог поиска файлов."""
        from app.views.dialogs.file_search_dialog.file_search_dialog import (
            FileSearchDialog,
        )
        dialog = FileSearchDialog(self.main_window)
        dialog.exec()

