# app/controllers/system_dialog_controller.py

import logging

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from .dialog_manager import DialogManager

logger = logging.getLogger(__name__)

_ICON_STATUS_CONTEXT = "IconRefreshStatus"
_SYS_CONTEXT = "SystemDialogController"

_SYS_TITLE_BROWSER_IMPORT = QT_TRANSLATE_NOOP(_SYS_CONTEXT, "Browser Import")
_SYS_TITLE_AUTO_SAVE = QT_TRANSLATE_NOOP(_SYS_CONTEXT, "Auto-save")
_SYS_TITLE_ICON_REFRESH = QT_TRANSLATE_NOOP(_SYS_CONTEXT, "Icon Refresh")
_SYS_TITLE_BAD_URL_CHECK = QT_TRANSLATE_NOOP(_SYS_CONTEXT, "Bad URL Check")

_SYS_ERROR_READ_HTML = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Error reading HTML file."
)
_SYS_INFO_CHECK_FILE = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Check file integrity and access rights."
)
_SYS_WARN_NO_LINKS = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "No links found in file."
)
_SYS_INFO_EXPORT_HTML = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT,
    "Export bookmarks from browser in HTML format and select correct file.",
)
_SYS_WARN_NO_SECTION = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "No section selected for import."
)
_SYS_INFO_SELECT_SECTION = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Select section where categories and links will be added."
)
_SYS_AUTO_SAVE_FAILED_IMPORT = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Failed to create auto-save before import."
)
_SYS_AUTO_SAVE_FAILED_CHECK = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Failed to create auto-save before check."
)
_SYS_IMPORT_COMPLETED_ERROR = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Import completed with error"
)
_SYS_PROTOCOL_STATS = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Protocol statistics:"
)
_SYS_HTTPS_COUNT = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "HTTPS links: {count}"
)
_SYS_HTTP_COUNT = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "HTTP links: {count}"
)
_SYS_HTTPS_QUESTION = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Would you like to check URLs for HTTPS availability?"
)
_SYS_HTTPS_QUESTION_INFO = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT,
    "This will verify which HTTP links can be upgraded to HTTPS.",
)
_SYS_ICON_REFRESH_FAILED = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Failed to start icon refresh"
)
_SYS_BAD_URL_CHECK_FAILED = QT_TRANSLATE_NOOP(
    _SYS_CONTEXT, "Failed to start bad URL check"
)


def _tr_sys(text: str) -> str:
    return QCoreApplication.translate(_SYS_CONTEXT, text)


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
        icon_refresh_service_factory=None,
        bad_url_check_service_factory=None,
    ):
        self.main_window = main_window
        self.database_controller = database_controller
        self.links_table_controller = links_table_controller
        self.links_business = links_business
        self._icon_refresh_service_factory = icon_refresh_service_factory
        self._bad_url_check_service_factory = bad_url_check_service_factory

        # ✅ FIX: Lazy loading dialogs
        self._about_dialog = None
        self._settings_dialog = None
        self._file_search_dialog = None
        self._icon_refresh_service = None  # Сервис обновления иконок
        self._bad_url_check_service = None  # Сервис проверки недоступных URL

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
        from app.utils.ui.async_helpers import run_async_backup

        importer = BrowserBookmarksImporter()
        path = self._select_bookmarks_file(importer)
        if not path:
            return

        categories = self._parse_bookmarks(importer, path)
        if categories is None:
            return

        if not any(categories.values()):
            DialogManager.show_warning(
                self.main_window,
                _tr_sys(_SYS_WARN_NO_LINKS),
                _tr_sys(_SYS_TITLE_BROWSER_IMPORT),
                informative_text=_tr_sys(_SYS_INFO_EXPORT_HTML),
                details=f"file={path}",
            )
            return

        section_id = self._choose_section()
        if not section_id:
            DialogManager.show_warning(
                self.main_window,
                _tr_sys(_SYS_WARN_NO_SECTION),
                _tr_sys(_SYS_TITLE_BROWSER_IMPORT),
                informative_text=_tr_sys(_SYS_INFO_SELECT_SECTION),
            )
            return

        if not self._backup_before_import(run_async_backup):
            return

        success, msg, stats = importer.sync_to_db(
            categories,
            section_id,
            self.main_window.structure_business,
            self.links_business,
        )

        self._post_import_processing(success, msg, stats, run_async_backup)

    def _show_import_result_and_offer_check(self, msg: str, stats: dict):
        """Show import result and offer Bad URL check if HTTP links found."""
        from PyQt6.QtWidgets import QMessageBox
        
        added = stats.get("added", 0)
        http_count = stats.get("http_count", 0)
        https_count = stats.get("https_count", 0)
        
        # Build detailed message
        detailed_msg = msg or ""
        stat_lines = []
        if http_count > 0 or https_count > 0:
            stat_lines.append(_tr_sys(_SYS_PROTOCOL_STATS))
            if https_count > 0:
                stat_lines.append(
                    _tr_sys(_SYS_HTTPS_COUNT).format(count=https_count)
                )
            if http_count > 0:
                stat_lines.append(_tr_sys(_SYS_HTTP_COUNT).format(count=http_count))
        if stat_lines:
            detailed_msg = (
                f"{detailed_msg}\n\n" if detailed_msg else ""
            ) + "\n".join(stat_lines)
        
        # If HTTP links found, offer to check URLs
        if http_count > 0 and added > 0:
            question_lines = [
                _tr_sys(_SYS_HTTPS_QUESTION),
                _tr_sys(_SYS_HTTPS_QUESTION_INFO),
            ]
            question_text = (
                f"{detailed_msg}\n\n" if detailed_msg else ""
            ) + "\n".join(question_lines)

            reply = DialogManager.show_custom(
                self.main_window,
                QMessageBox.Icon.Question,
                _tr_sys(_SYS_TITLE_BROWSER_IMPORT),
                question_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Run Bad URL check
                logger.info("User requested Bad URL check after import")
                self.handle_check_bad_urls()
        else:
            # Just show info without question
            DialogManager.show_info(
                self.main_window,
                detailed_msg,
                _tr_sys(_SYS_TITLE_BROWSER_IMPORT),
            )

    # --- Helpers to reduce complexity ---
    def _select_bookmarks_file(self, importer):
        """Show file selection dialog via importer and return path or None."""
        return importer.select_file(self.main_window)

    def _parse_bookmarks(self, importer, path: str):
        """Parse bookmarks from file, show error on failure; return dict or None."""
        try:
            return importer.parse_bookmarks(path)
        except Exception as e:
            DialogManager.show_error(
                self.main_window,
                _tr_sys(_SYS_ERROR_READ_HTML),
                _tr_sys(_SYS_TITLE_BROWSER_IMPORT),
                informative_text=_tr_sys(_SYS_INFO_CHECK_FILE),
                details=str(e),
            )
            return None

    def _choose_section(self) -> int | None:
        """Open section selection dialog and return selected section id."""
        from app.views.windows.dialogs.import_browser_dialog import ImportBrowserDialog

        dlg = ImportBrowserDialog(self.main_window.structure_business, self.main_window)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return None
        return dlg.get_selected_section_id()

    def _backup_before_import(self, run_async_backup) -> bool:
        """Perform async backup before importing; show error and return False on failure."""
        try:
            db = self.main_window.structure_business.db
            success, message = run_async_backup(db, parent=self.main_window)
            if not success:
                DialogManager.show_error(
                    self.main_window,
                    _tr_sys(_SYS_AUTO_SAVE_FAILED_IMPORT),
                    _tr_sys(_SYS_TITLE_AUTO_SAVE),
                    details=message or "",
                )
                return False
            return True
        except Exception as backup_err:
            DialogManager.show_error(
                self.main_window,
                _tr_sys(_SYS_AUTO_SAVE_FAILED_IMPORT),
                _tr_sys(_SYS_TITLE_AUTO_SAVE),
                details=str(backup_err),
            )
            return False

    def _post_import_processing(self, success: bool, msg: str, stats: dict, run_async_backup) -> None:
        """Finalize import: backup, refresh UI, and show results."""
        if not success:
            DialogManager.show_error(
                self.main_window,
                _tr_sys(_SYS_IMPORT_COMPLETED_ERROR),
                _tr_sys(_SYS_TITLE_BROWSER_IMPORT),
                details=msg,
            )
            return

        # Create backup asynchronously after import
        try:
            db = self.main_window.structure_business.db
            success, message = run_async_backup(db, parent=self.main_window)
            if success and message:
                logger.info("Backup completed: %s", message)
            elif not success:
                logger.warning("Backup failed: %s", message)
        except Exception as backup_err:
            logger.warning("Failed to start backup: %s", backup_err)

        # Update tree and table
        if hasattr(self.main_window, "structure_business"):
            try:
                self.main_window.structure_business.async_service.schedule_structure_reload()
            except Exception as exc:
                logger.warning(
                    "SystemDialogController: schedule_structure_reload failed: %s",
                    exc,
                    exc_info=True,
                )
        category_id = self.main_window.get_current_category_id()
        if category_id:
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

        # Ensure UI is fully updated
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        # Show result dialog and offer URL check
        self._show_import_result_and_offer_check(msg, stats)

    def show_about_dialog(self):
        """Show About dialog."""
        if self._about_dialog is None:
            from app.views.windows.dialogs.about_dialog import AboutDialog

            self._about_dialog = AboutDialog(self.main_window)

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

    def handle_refresh_icons(self):
        """Запустить фоновое обновление иконок."""
        if self._icon_refresh_service and self._icon_refresh_service.is_running():
            self._icon_refresh_service.show_dialog()
            return
        try:
            from app.views.windows.dialogs.icon_refresh_dialog import IconRefreshDialog

            service = self._new_icon_refresh_service()
            
            # Создаём диалог прогресса
            start_options = {"batch_size": 100, "delay_ms": 50, "max_workers": 10}
            dialog = IconRefreshDialog(
                service,
                parent=self.main_window,
                start_options=start_options,
            )
            service.set_dialog(dialog)  # Связываем сервис с диалогом
            dialog.refresh_started.connect(self._on_icon_refresh_started_by_user)
            
            # Подключаем обновление statusbar
            service.progress.connect(self._update_statusbar_icon_progress)
            service.finished.connect(self._on_icon_refresh_finished)
            service.error.connect(self._on_icon_refresh_error)
            
            # Показываем диалог и ждём ручного запуска
            dialog.show()
            logger.info("Icon refresh dialog opened, waiting for user action")
        
        except Exception as e:
            logger.error("Failed to start icon refresh: %s", e, exc_info=True)
            self._set_icon_refresh_busy(False)
            DialogManager.show_error(
                self.main_window,
                _tr_sys(_SYS_ICON_REFRESH_FAILED),
                _tr_sys(_SYS_TITLE_ICON_REFRESH),
                details=str(e),
            )
    
    def _update_statusbar_icon_progress(self, current: int, total: int, message: str):
        """Обновить statusbar с прогрессом обновления иконок."""
        try:
            status_bar_getter = getattr(self.main_window, "statusBar", None)
            status_bar = status_bar_getter() if callable(status_bar_getter) else None
            if status_bar is None:
                return

            base_text = QCoreApplication.translate(
                "IconRefreshStatus", "Icon refresh: {0}/{1}"
            ).format(current, total)
            extra = (message or "").replace("\n", " ").strip()
            if extra:
                status_text = f"{base_text} - {extra}"
            else:
                status_text = (
                    f"{base_text} "
                    f"{QCoreApplication.translate('IconRefreshStatus', '(click to show)')}"
                )

            status_bar.showMessage(status_text)

            if not getattr(status_bar, "_icon_refresh_click_connected", False):
                status_bar.mousePressEvent = self._on_statusbar_clicked
                status_bar._icon_refresh_click_connected = True
        except Exception as e:
            logger.debug("Failed to update statusbar: %s", e)
    
    def _on_bad_url_check_finished(self, dialog) -> None:
        """Обработчик завершения проверки битых URL — обновить таблицу."""
        try:
            # Clear statusbar hint
            try:
                status_bar = self.main_window.statusBar()
                if status_bar:
                    status_bar.showMessage("", 1)
            except Exception:
                pass

            category_id = self.main_window.get_current_category_id()
            if category_id:
                try:
                    if hasattr(self.links_table_controller, "reload"):
                        self.links_table_controller.reload(category_id)
                except Exception as e:
                    logger.debug("Failed to reload links table: %s", e)
            self.main_window.update_statusbar()
        except Exception as e:
            logger.debug("Failed to handle bad URL check finished: %s", e)

    def _on_icon_refresh_finished(self, stats: dict):
        """Обработчик завершения обновления иконок."""
        try:
            # Process events to prevent UI freeze
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
            # Reload links table to show updated icons
            updated = stats.get("updated", 0)
            if updated > 0:
                category_id = self.main_window.get_current_category_id()
                if category_id:
                    try:
                        if hasattr(self.links_table_controller, "reload"):
                            self.links_table_controller.reload(category_id)
                            logger.info("Links table reloaded after icon refresh (%s updated)", updated)
                    except Exception as e:
                        logger.debug("Failed to reload links table after icon refresh: %s", e)
            
            # Update statusbar
            status_bar_getter = getattr(self.main_window, "statusBar", None)
            status_bar = status_bar_getter() if callable(status_bar_getter) else None
            if status_bar is not None:
                status_bar.showMessage(
                    QCoreApplication.translate(
                        "IconRefreshStatus", "Icon refresh completed: {0} updated"
                    ).format(updated),
                    5000,
                )
                status_bar._icon_refresh_click_connected = False  # type: ignore[attr-defined]
            
            self._icon_refresh_service = None
            self._set_icon_refresh_busy(False)
        except Exception as e:
            logger.debug("Failed to handle icon refresh finished: %s", e)
    
    def _on_icon_refresh_error(self, error_message: str):
        """Обработчик ошибки обновления иконок."""
        try:
            # Process events to prevent UI freeze
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
            status_bar_getter = getattr(self.main_window, "statusBar", None)
            status_bar = status_bar_getter() if callable(status_bar_getter) else None
            if status_bar is not None:
                status_bar.showMessage(
                    QCoreApplication.translate(
                        "IconRefreshStatus", "Icon refresh error: {0}"
                    ).format(error_message),
                    5000,
                )
                status_bar._icon_refresh_click_connected = False  # type: ignore[attr-defined]
            self._icon_refresh_service = None
            self._set_icon_refresh_busy(False)
        except Exception as e:
            logger.debug("Failed to handle icon refresh error: %s", e)
    
    def show_icon_refresh_dialog(self):
        """Показать диалог обновления иконок если он скрыт в фоне."""
        if self._icon_refresh_service:
            self._icon_refresh_service.show_dialog()
    
    def _on_statusbar_clicked(self, event):
        """Обработчик клика по statusbar для показа скрытых диалогов."""
        # Bad URL check in background
        if self._bad_url_check_service and self._bad_url_check_service.is_running():
            self._bad_url_check_service.show_dialog()
            event.accept()
            return
        # Icon refresh in background
        if self._icon_refresh_service and self._icon_refresh_service.is_running():
            self.show_icon_refresh_dialog()
            event.accept()
            return
        # Default: pass through
        try:
            from PyQt6.QtWidgets import QStatusBar
            QStatusBar.mousePressEvent(self.main_window.statusBar(), event)
        except Exception:
            pass
    
    def show_file_search_dialog(self):
        """Show File Search dialog."""
        # ✅ ИСПРАВЛЕНИЕ: Lazy loading - создаем диалог только при первом вызове
        if self._file_search_dialog is None:
            from app.views.windows.dialogs.file_search_dialog.file_search_dialog import (
                FileSearchDialog,
            )

            self._file_search_dialog = FileSearchDialog(self.main_window)

        self._file_search_dialog.exec()
    
    def handle_check_bad_urls(self):
        """Запустить проверку недоступных URL."""
        try:
            from app.utils.ui.async_helpers import run_async_backup
            from app.views.windows.dialogs.bad_url_cleanup_dialog import (
                BadUrlCleanupDialog,
            )
            
            # Auto-save before bad URL check
            try:
                db = self.main_window.structure_business.db
                success, message = run_async_backup(db, parent=self.main_window)
                if not success:
                    DialogManager.show_error(
                        self.main_window,
                        _tr_sys(_SYS_AUTO_SAVE_FAILED_CHECK),
                        _tr_sys(_SYS_TITLE_AUTO_SAVE),
                        details=message or "",
                    )
                    return
            except Exception as backup_err:
                DialogManager.show_error(
                    self.main_window,
                    _tr_sys(_SYS_AUTO_SAVE_FAILED_CHECK),
                    _tr_sys(_SYS_TITLE_AUTO_SAVE),
                    details=str(backup_err),
                )
                return

            db = self._get_structure_db()
            service = self._new_bad_url_check_service(db)

            # Создаём диалог
            dialog = BadUrlCleanupDialog(service, db, parent=self.main_window)
            service.set_dialog(dialog)  # Связываем сервис с диалогом

            # Ensure statusbar click handler is connected for background restore
            try:
                status_bar = self.main_window.statusBar()
                if status_bar and not getattr(status_bar, "_icon_refresh_click_connected", False):
                    status_bar.mousePressEvent = self._on_statusbar_clicked
                    status_bar._icon_refresh_click_connected = True
            except Exception:
                pass
            
            # Показываем диалог сразу (до запуска проверки)
            dialog.show()
            
            # Даём диалогу отрисоваться
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
            # Подключаем finished для обновления таблицы после проверки
            service.finished.connect(
                lambda _bad_urls: self._on_bad_url_check_finished(dialog)
            )

            # Запускаем проверку (non-blocking)
            if not service.start_check(max_workers=15, timeout=5, check_ssl=True):
                logger.warning("Failed to start bad URL check")
                dialog.close()
        
        except Exception as e:
            logger.error("Failed to start bad URL check: %s", e, exc_info=True)
            DialogManager.show_error(
                self.main_window,
                _tr_sys(_SYS_BAD_URL_CHECK_FAILED),
                _tr_sys(_SYS_TITLE_BAD_URL_CHECK),
                details=str(e),
            )

    def _get_structure_db(self):
        structure_business = getattr(self.main_window, "structure_business", None)
        if structure_business is None or not hasattr(structure_business, "db"):
            raise SetupError(
                "SystemDialogController requires main_window.structure_business.db"
            )
        return structure_business.db

    def _new_icon_refresh_service(self):
        db = self._get_structure_db()
        service = self._create_icon_refresh_service(db)
        self._icon_refresh_service = service
        return service

    def _new_bad_url_check_service(self, db=None):
        current_db = db if db is not None else self._get_structure_db()
        service = self._create_bad_url_check_service(current_db)
        self._bad_url_check_service = service
        return service

    def _create_icon_refresh_service(self, db):
        """Create icon refresh service via injectable factory (for tests/wiring)."""
        if self._icon_refresh_service_factory is not None:
            return self._icon_refresh_service_factory(db, self.main_window)
        from app.controllers.services.icon_refresh_service import IconRefreshService

        return IconRefreshService(db, parent=self.main_window)

    def _create_bad_url_check_service(self, db):
        """Create bad URL check service via injectable factory (for tests/wiring)."""
        if self._bad_url_check_service_factory is not None:
            return self._bad_url_check_service_factory(db, self.main_window)
        from app.controllers.services.bad_url_check_service import BadUrlCheckService

        return BadUrlCheckService(db, parent=self.main_window)

    def _set_icon_refresh_busy(self, busy: bool) -> None:
        """Toggle manual refresh controls if available."""
        try:
            handler = getattr(self.main_window, "set_icon_refresh_busy", None)
            if callable(handler):
                handler(busy)
        except Exception:
            logger.debug("Failed to update icon refresh button state", exc_info=True)

    def _on_icon_refresh_started_by_user(self) -> None:
        """Ручной запуск обновления через диалог."""
        self._set_icon_refresh_busy(True)
        logger.info("Icon refresh started by user command")
