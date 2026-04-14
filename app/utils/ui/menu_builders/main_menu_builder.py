"""Builder for the application's main menu."""

import logging
import time
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QCoreApplication, QPoint, QTimer
from PyQt6.QtWidgets import QApplication, QMenu, QMenuBar, QStyle, QWidget

from app.utils.ui.menu_builders.menu_actions import ActionBuilder, MenuTexts, Shortcuts

from .base import get_menu_icon

if TYPE_CHECKING:
    from app.views.windows.main_window_protocol import MainWindowProtocol

logger = logging.getLogger(__name__)


class MainMenuBuilder:
    """Builder for the application main menu."""

    def __init__(self, main_window: "MainWindowProtocol"):
        self.main_window = main_window
        parent_widget = cast(QWidget, main_window)
        self.actions = ActionBuilder(parent_widget)
        self.theme = main_window.settings.get_theme()
        self._deferred_icons: list[tuple[object, str]] = []

    def build(self) -> QMenuBar:
        """Create and return the fully built main menu bar."""
        logger.debug("Creating main menu for theme: %s", self.theme)

        menubar = QMenuBar(cast(QWidget, self.main_window))

        # Ensure undo/redo actions are initialized for use across UI (e.g., context menus)
        undo_action, redo_action = self.main_window.create_undo_redo_actions()
        if undo_action is not None:
            self._queue_icon(undo_action, "undo")
            # Add to main window to enable global shortcuts (Ctrl+Z)
            if undo_action not in self.main_window.actions():
                self.main_window.addAction(undo_action)
        if redo_action is not None:
            self._queue_icon(redo_action, "redo")
            # Add to main window to enable global shortcuts (Ctrl+Y/Ctrl+Shift+Z)
            if redo_action not in self.main_window.actions():
                self.main_window.addAction(redo_action)

        # New structure: File  Data  Help
        self._create_file_menu(menubar)
        self._create_data_menu(menubar)
        self._create_help_menu(menubar)
        self._schedule_deferred_icon_apply()
        self._schedule_menu_icon_warmup(menubar)
        self._schedule_menu_popup_warmup(menubar)
        return menubar

    def _queue_icon(self, action, icon_name: str) -> None:
        self._deferred_icons.append((action, icon_name))

    def _create_action(
        self,
        text: str,
        callback=None,
        shortcut: str | None = None,
        icon_name: str | None = None,
    ):
        action = self.actions.create(text, callback, shortcut, icon=None)
        if icon_name:
            self._queue_icon(action, icon_name)
        return action

    def _schedule_deferred_icon_apply(self, delay_ms: int = 0) -> None:
        """Attach menu icons after the initial menu structure is already built."""

        def _run() -> None:
            pending = list(self._deferred_icons)
            self._deferred_icons.clear()
            for action, icon_name in pending:
                try:
                    action.setIcon(get_menu_icon(icon_name, self.theme, "main_menu"))
                except RuntimeError:
                    return
                except Exception:
                    logger.debug(
                        "MainMenu: failed to apply deferred icon %s",
                        icon_name,
                        exc_info=True,
                    )

        try:
            QTimer.singleShot(delay_ms, _run)
        except Exception:
            logger.debug("MainMenu: failed to schedule deferred icon apply", exc_info=True)

    def _schedule_menu_icon_warmup(self, menubar: QMenuBar, delay_ms: int = 700) -> None:
        """Warm only main-menu icons after startup to reduce first-popup cost."""

        def _run() -> None:
            try:
                self._warmup_menu_icons(menubar)
            except RuntimeError:
                # Menu/window may already be deleted during shutdown.
                return
            except Exception:
                logger.debug("MainMenu: menu icon warmup failed", exc_info=True)

        try:
            QTimer.singleShot(delay_ms, _run)
        except Exception:
            logger.debug("MainMenu: failed to schedule menu icon warmup", exc_info=True)

    def _schedule_menu_popup_warmup(self, menubar: QMenuBar, delay_ms: int = 900) -> None:
        """Warm top-level QMenu pre-show path to reduce first click latency."""

        def _run() -> None:
            try:
                self._warmup_menu_popups(menubar)
            except RuntimeError:
                return
            except Exception:
                logger.debug("MainMenu: popup warmup failed", exc_info=True)

        try:
            QTimer.singleShot(delay_ms, _run)
        except Exception:
            logger.debug("MainMenu: failed to schedule popup warmup", exc_info=True)

    def _warmup_menu_icons(self, menubar: QMenuBar) -> None:
        """Force QIcon pixmap creation for menu actions without touching tree icons."""
        start = time.perf_counter()
        try:
            app = QApplication.instance()
            if app is None:
                return
            icon_size = menubar.style().pixelMetric(
                QStyle.PixelMetric.PM_SmallIconSize,
                None,
                menubar,
            )
            icon_size = int(icon_size) if int(icon_size) > 0 else 16
        except Exception:
            icon_size = 16

        warmed = 0
        seen: set[int] = set()

        for menu in self._iter_top_level_menus(menubar):
            for action in self._iter_menu_actions_recursive(menu):
                try:
                    icon = action.icon()
                    if icon.isNull():
                        continue
                    key = int(icon.cacheKey())
                    if key in seen:
                        continue
                    seen.add(key)
                    icon.pixmap(icon_size, icon_size)
                    warmed += 1
                except Exception:
                    logger.debug("MainMenu: failed to warm icon for action %r", action.text(), exc_info=True)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        logger.debug(
            "[Perf] Main menu icon warmup warmed=%d unique_icons=%d size=%d elapsed=%.2fms",
            warmed,
            len(seen),
            icon_size,
            elapsed_ms,
        )

    def _warmup_menu_popups(self, menubar: QMenuBar) -> None:
        """Precompute popup path for the first top-level menu in small GUI slices."""
        first_menu = next(self._iter_top_level_menus(menubar), None)
        if not isinstance(first_menu, QMenu):
            return

        start = time.perf_counter()
        state = {
            "menu": first_menu,
            "title": first_menu.title(),
            "actions_total": len(first_menu.actions()),
            "action_geometries": 0,
        }

        def _step1() -> None:
            menu = state["menu"]
            try:
                menu.ensurePolished()
                menu.sizeHint()
                menu.minimumSizeHint()
            except Exception:
                logger.debug(
                    "MainMenu: popup warmup step1 failed for %r",
                    state["title"],
                    exc_info=True,
                )
            QTimer.singleShot(0, _step2)

        def _step2() -> None:
            menu = state["menu"]
            try:
                for action in menu.actions():
                    if action is None:
                        continue
                    menu.actionGeometry(action)
                    state["action_geometries"] += 1
            except Exception:
                logger.debug(
                    "MainMenu: popup warmup step2 failed for %r",
                    state["title"],
                    exc_info=True,
                )
            QTimer.singleShot(0, _step3)

        def _step3() -> None:
            menu = state["menu"]
            try:
                # Warm native handle only for the first top-level popup.
                menu.winId()
            except Exception:
                logger.debug(
                    "MainMenu: popup warmup step3 failed for %r",
                    state["title"],
                    exc_info=True,
                )
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.debug(
                "[Perf] Main menu popup warmup title=%r menus=1 actions=%d action_geometries=%d elapsed=%.2fms",
                state["title"],
                state["actions_total"],
                state["action_geometries"],
                elapsed_ms,
            )

        _step1()

    @staticmethod
    def _iter_top_level_menus(menubar: QMenuBar):
        for action in menubar.actions():
            menu = action.menu()
            if isinstance(menu, QMenu):
                yield menu

    def _iter_menu_actions_recursive(self, menu: QMenu):
        for action in menu.actions():
            if action is None:
                continue
            yield action
            sub_menu = action.menu()
            if isinstance(sub_menu, QMenu):
                yield from self._iter_menu_actions_recursive(sub_menu)


    def _create_file_menu(self, menubar: QMenuBar):
        """Create the '&File' menu."""
        file_menu = menubar.addMenu(QCoreApplication.translate("MainMenu", "&File"))

        if file_menu is None:
            logger.warning("Main menu: failed to create File menu")
            return

        # Add section
        file_menu.addAction(
            self._create_action(
                MenuTexts.ADD_SECTION,
                getattr(self.main_window, "show_section_dialog", None),
                Shortcuts.ADD_SECTION,
                "add_section",
            )
        )

        # Add category
        file_menu.addAction(
            self._create_action(
                MenuTexts.ADD_CATEGORY,
                getattr(self.main_window, "add_new_category", None),
                Shortcuts.ADD_CATEGORY,
                "add_category",
            )
        )

        # Add link (for current category)
        def _add_link_current_category():
            try:
                cat_id = None
                if hasattr(self.main_window, "get_current_category_id"):
                    cat_id = self.main_window.get_current_category_id()
                if hasattr(self.main_window, "show_link_dialog_for_category"):
                    self.main_window.show_link_dialog_for_category(cat_id)
            except Exception:
                logger.exception("[MainMenu] Error adding link from File menu")

        file_menu.addAction(
            self._create_action(
                MenuTexts.ADD_LINK,
                _add_link_current_category,
                Shortcuts.ADD_LINK,
                "add_link",
            )
        )

        # Search files
        file_menu.addAction(
            self._create_action(
                MenuTexts.SEARCH_FILES,
                self.main_window.show_file_search_dialog,
                Shortcuts.SEARCH_FILES,
                "search",
            )
        )

        file_menu.addSeparator()

        # Settings
        file_menu.addAction(
            self._create_action(
                MenuTexts.SETTINGS,
                self.main_window.show_settings_dialog,
                Shortcuts.SETTINGS,
                icon_name="settings",
            )
        )

        file_menu.addSeparator()

        # Exit
        file_menu.addAction(
            self._create_action(
                MenuTexts.EXIT,
                getattr(self.main_window, "close", None),
                Shortcuts.EXIT,
                icon_name="exit",
            )
        )

    def _create_data_menu(self, menubar: QMenuBar):
        """Create the '&Data' menu with Import/Export submenus."""
        data_menu = menubar.addMenu(QCoreApplication.translate("MainMenu", "&Data"))

        if data_menu is None:
            logger.warning("Main menu: failed to create Data menu")
            return

        # Database
        data_menu.addAction(
            self._create_action(
                MenuTexts.CONNECT_DATABASE,
                self._connect_database,
                Shortcuts.CTRL_ALT_D,
                icon_name="import",
            )
        )
        data_menu.addAction(
            self._create_action(
                MenuTexts.SAVE_DATABASE,
                self._save_database,
                Shortcuts.CTRL_ALT_S,
                icon_name="export",
            )
        )
        data_menu.addAction(
            self._create_action(
                MenuTexts.RESTORE_DATABASE,
                self._restore_database,
                Shortcuts.CTRL_ALT_B,
                icon_name="dbrestore",
            )
        )

        data_menu.addSeparator()

        # Links
        data_menu.addAction(
            self._create_action(
                MenuTexts.IMPORT_BROWSER,
                self.main_window.handle_import_browser_bookmarks,
                Shortcuts.CTRL_ALT_C,
                icon_name="import",
            )
        )
        data_menu.addAction(
            self._create_action(
                QCoreApplication.translate("MainMenu", "Check Bad URLs"),
                self._check_bad_urls,
                Shortcuts.CTRL_ALT_U,
                icon_name="link_off",
            )
        )
        data_menu.addAction(
            self._create_action(
                MenuTexts.CLEAR_FAVORITES,
                self._clear_favorites,
                Shortcuts.CTRL_ALT_F,
                icon_name="delete",
            )
        )

        data_menu.addSeparator()

        # Icons
        data_menu.addAction(
            self._create_action(
                MenuTexts.IMPORT_ICONS,
                self._load_icons,
                Shortcuts.CTRL_ALT_I,
                icon_name="add_ico",
            )
        )
        data_menu.addAction(
            self._create_action(
                MenuTexts.EXPORT_ICONS,
                self._save_icons,
                Shortcuts.CTRL_ALT_E,
                icon_name="zip_ico",
            )
        )
        data_menu.addAction(
            self._create_action(
                QCoreApplication.translate("MainMenu", "Refresh Icons"),
                self._refresh_icons,
                Shortcuts.CTRL_ALT_H,
                icon_name="refresh",
            )
        )

    def _create_help_menu(self, menubar: QMenuBar):
        """Create the '&Help' menu."""
        help_menu = menubar.addMenu(QCoreApplication.translate("MainMenu", "&Help"))

        if help_menu is None:
            logger.warning("Main menu: failed to create Help menu")
            return
        help_menu.addAction(
            self._create_action(
                MenuTexts.ABOUT,
                self.main_window.show_about_dialog,
                icon_name="help",
            )
        )

    def _offset_top_level_popups(self, menubar: QMenuBar, offset: int = 8) -> None:
        """Shift top-level menus downward so popups don't overlap toolbar."""

        def _offset(menu: QMenu) -> None:
            def _shift():
                try:
                    pos = menu.pos()
                    menu.move(pos + QPoint(0, offset))
                except Exception:
                    logger.debug("MainMenu: failed to shift menu popup", exc_info=True)

            menu.aboutToShow.connect(_shift)

        for action in menubar.actions():
            menu = action.menu()
            if isinstance(menu, QMenu):
                _offset(menu)

    # Menu action handlers

    def _clear_favorites(self):
        """Clear favorites — delegated to DialogController."""
        if hasattr(self.main_window, "database_controller"):
            self.main_window.database_controller.handle_clear_favorites()

    def _refresh_icons(self):
        """Refresh icons for web links — delegated to SystemDialogController."""
        if hasattr(self.main_window, "system_dialogs"):
            self.main_window.system_dialogs.handle_refresh_icons()
    
    def _check_bad_urls(self):
        """Check bad URLs — delegated to SystemDialogController."""
        if hasattr(self.main_window, "system_dialogs"):
            self.main_window.system_dialogs.handle_check_bad_urls()
    
    def _restore_database(self):
        """Restore database — delegated to DialogController."""
        if hasattr(self.main_window, "database_controller"):
            self.main_window.database_controller.handle_restore_database()

    def _connect_database(self):
        """Connect different database — delegated to DialogController."""
        if hasattr(self.main_window, "database_controller"):
            self.main_window.database_controller.handle_connect_database()

    def _save_database(self):
        """Save database copy — delegated to DialogController."""
        if hasattr(self.main_window, "database_controller"):
            self.main_window.database_controller.handle_save_database()

    def _save_icons(self):
        """Export icons — delegated to DialogController."""
        if hasattr(self.main_window, "database_controller"):
            self.main_window.database_controller.handle_save_icons()

    def _load_icons(self):
        """Import icons — delegated to DialogController."""
        if hasattr(self.main_window, "database_controller"):
            self.main_window.database_controller.handle_load_icons()
