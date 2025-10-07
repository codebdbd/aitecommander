# app/controllers/system_dialog_controller.py

import logging

from app.config_data import app_config

from .dialog_manager import DialogManager

logger = logging.getLogger(__name__)


class SetupError(Exception):
    """SystemDialogController dependency setup error."""


class SystemDialogController:
    """Controller for managing system dialogs."""

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

        # ✅ FIX: Lazy loading dialogs
        self._about_dialog = None
        self._settings_dialog = None
        self._file_search_dialog = None

        # Validate required dependencies
        if self.database_controller is None:
            raise SetupError("SystemDialogController requires 'database_controller'")
        if self.links_table_controller is None:
            raise SetupError("SystemDialogController requires 'links_table_controller'")
        if self.links_business is None:
            raise SetupError("SystemDialogController requires 'links_business'")

    def handle_import_browser_bookmarks(self):
        """Import browser bookmarks."""
        from app.utils.browser.import_browser_html import BrowserBookmarksImporter
        from app.views.windows.dialogs.import_browser_dialog import ImportBrowserDialog

        importer = BrowserBookmarksImporter()

        # 1) File selection
        path = importer.select_file(self.main_window)
        if not path:
            return

        # 2) Parsing
        try:
            categories = importer.parse_bookmarks(path)
        except Exception as e:
            DialogManager.show_error(
                self.main_window,
                "Browser Import",
                "Error reading HTML file.",
                informative_text="Check file integrity and access rights.",
                details=str(e),
            )
            return
        if not any(categories.values()):
            DialogManager.show_warning(
                self.main_window,
                "Browser Import",
                "No links found in file.",
                informative_text=(
                    "Export bookmarks from browser in HTML format and select correct file."
                ),
                details=f"file={path}",
            )
            return

        # 3) Section selection
        dlg = ImportBrowserDialog(self.main_window.structure_business, self.main_window)
        if dlg.exec() != dlg.DialogCode.Accepted:  # QDialog.DialogCode.Accepted
            return
        section_id = dlg.get_selected_section_id()
        if not section_id:
            DialogManager.show_warning(
                self.main_window,
                "Browser Import",
                "No section selected for import.",
                informative_text="Select section where categories and links will be added.",
            )
            return

        # 4) Sync to DB
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
                    on_finished=lambda result: logger.info(f"Backup created: {result.get('backup_filename')}"),
                    on_error=lambda e, tb: logger.warning(f"Failed to create backup: {e}")
                )
            except SetupError:
                logger.exception(
                    "SystemDialogController: backup failed due to setup error"
                )
                raise
            except Exception as backup_err:
                logger.warning(
                    f"Failed to start backup: {backup_err}"
                )
            # Update category tree and links table
            if hasattr(self.main_window, "structure_business"):
                self.main_window.structure_business.load_structure()
            category_id = self.main_window.get_current_category_id()
            if category_id:
                # Centralized: update table through LinksTableController, without getattr/fallback
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
                "Browser Import",
                msg,
            )
        else:
            DialogManager.show_error(
                self.main_window,
                "Browser Import",
                "Import completed with error",
                details=msg,
            )

    def show_about_dialog(self):
        """Show About dialog."""
        # ✅ ИСПРАВЛЕНИЕ: Lazy loading - создаем диалог только при первом вызове
        if self._about_dialog is None:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QMessageBox

            title = app_config.get_about_title()
            text = app_config.get_about_text()

            self._about_dialog = QMessageBox(self.main_window)
            self._about_dialog.setIcon(QMessageBox.Icon.NoIcon)  # Без иконки = без звука
            self._about_dialog.setWindowTitle(title)
            self._about_dialog.setText(text)
            self._about_dialog.setTextFormat(Qt.TextFormat.PlainText)  # Важно: правильно обрабатывает \n
            self._about_dialog.setInformativeText("Thank you for using our application!")
            self._about_dialog.setStandardButtons(QMessageBox.StandardButton.Ok)

        self._about_dialog.exec()

    def show_settings_dialog(self):
        """Show Settings dialog."""
        # ✅ ИСПРАВЛЕНИЕ: Lazy loading - создаем диалог только при первом вызове
        if self._settings_dialog is None:
            from app.views.windows.dialogs.entity_dialogs import SettingsDialog

            self._settings_dialog = SettingsDialog(
                self.main_window.settings,
                self.main_window.theme_ctrl,
                parent=self.main_window,
            )

        self._settings_dialog.exec()

    def show_file_search_dialog(self):
        """Show File Search dialog."""
        # ✅ ИСПРАВЛЕНИЕ: Lazy loading - создаем диалог только при первом вызове
        if self._file_search_dialog is None:
            from app.views.windows.dialogs.file_search_dialog.file_search_dialog import (
                FileSearchDialog,
            )

            self._file_search_dialog = FileSearchDialog(self.main_window)

        self._file_search_dialog.exec()
