"""Controller for managing all application menus and handling user actions."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtCore import QModelIndex, QObject, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QListWidget, QMenu, QMenuBar, QWidget

from app.utils.ui.menu_builders import (
    CategoryMenuBuilder,
    LinksMenuBuilder,
    MainMenuBuilder,
    StructureMenuBuilder,
)
from i18n.language_service import LanguageService

if TYPE_CHECKING:
    from app.views.windows.main_window import MainWindow

logger = logging.getLogger(__name__)


class MenuController(QObject):
    """Controller for managing all application menus."""

    def __init__(self, main_window: "MainWindow"):
        super().__init__(main_window)
        self.main_window = main_window
        self._main_menu_builder = None
        self._structure_menu_builder = None
        self._links_menu_builder = None
        self._category_menu_builder = None
        self._language_service = LanguageService.instance()
        logger.info("MenuController: connecting to languageChanged signal")
        self._language_service.languageChanged.connect(self._on_language_changed)
        logger.info("MenuController: connected to languageChanged signal")
        if hasattr(self.main_window, "destroyed"):
            self.main_window.destroyed.connect(self._cleanup)

    def create_main_menu(self) -> QMenuBar:
        """Create the main menu bar."""
        if not self._main_menu_builder:
            self._main_menu_builder = MainMenuBuilder(self.main_window)
        return self._main_menu_builder.build()

    @pyqtSlot(str)
    def _on_language_changed(self, _lang_code: str) -> None:
        """Rebuild the main menu when language changes."""
        logger.info(
            "MenuController._on_language_changed called with lang_code=%s", _lang_code
        )
        try:
            logger.info("MenuController: rebuilding menu after language change")
            self.rebuild_after_language_change()
            logger.info("MenuController: menu rebuilt successfully")
        except Exception:
            logger.exception(
                "MenuController: failed to rebuild menu after language change"
            )

    def _cleanup(self) -> None:
        """Disconnect signals when window is destroyed."""
        try:
            self._language_service.languageChanged.disconnect(self._on_language_changed)
        except Exception:
            pass

    def create_structure_context_menu(
        self,
        tree_widget: QWidget,
        item: Optional[Any],
        delete_item_cb: Callable,
        add_new_section_cb: Callable,
        sort_tree_cb: Callable,
    ) -> QMenu:
        """Create context menu for the structure tree."""
        if not self._structure_menu_builder:
            self._structure_menu_builder = StructureMenuBuilder(
                tree_widget, self.main_window
            )
        return self._structure_menu_builder.build(
            item, delete_item_cb, add_new_section_cb, sort_tree_cb
        )

    def create_links_context_menu(
        self, table_widget: QWidget, idx: QModelIndex, paste_link_cb: Callable
    ) -> QMenu:
        """Create context menu for the links table."""
        if not self._links_menu_builder:
            self._links_menu_builder = LinksMenuBuilder(table_widget, self.main_window)
        return self._links_menu_builder.build(idx, paste_link_cb)

    def create_category_tile_context_menu(
        self,
        list_widget: QListWidget,
        item_id: Any,
        edit_cb: Callable,
        delete_cb: Callable,
        add_cb: Callable,
    ) -> tuple[QMenu, QAction, QAction, QAction]:
        """Create context menu for a category tile."""
        if not self._category_menu_builder:
            self._category_menu_builder = CategoryMenuBuilder(
                list_widget, self.main_window
            )
        return self._category_menu_builder.build(item_id, edit_cb, delete_cb, add_cb)

    def clear_cache(self):
        """Clear menu builders cache (e.g., after theme change)."""
        from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache

        icon_cache.clear_cache()

        # Recreate builders on next use
        self._main_menu_builder = None
        self._structure_menu_builder = None
        self._links_menu_builder = None
        self._category_menu_builder = None

    def rebuild_after_theme_change(self) -> None:
        """Rebuild the main menu after theme change.
        Encapsulates cache clearing and menu recreation.
        """
        try:
            old_menu = self.main_window.menuBar()
            if old_menu is not None:
                old_menu.deleteLater()
        except Exception as e:
            # If the menu hasn't been initialized yet or already removed
            logger.warning(
                "MenuController: failed to properly remove old menu on theme change",
                exc_info=e,
            )
            # Soft hint to the user (if there is a status bar)
            try:
                status_bar = getattr(self.main_window, "statusBar", None)
                if callable(status_bar):
                    sb = status_bar()
                    if sb is not None and hasattr(sb, "showMessage"):
                        sb.showMessage(
                            "Failed to update the old menu, attempting to rebuild...",
                            3000,
                        )
            except Exception:
                # Do not block further menu rebuild
                logger.debug("MenuController: status bar hint not shown")

        self.clear_cache()
        self.main_window.setMenuBar(self.create_main_menu())

    def rebuild_after_language_change(self) -> None:
        """Rebuild the main menu after language change."""
        try:
            old_menu = self.main_window.menuBar()
            if old_menu is not None:
                old_menu.deleteLater()
        except Exception:
            pass
        self.clear_cache()
        self.main_window.setMenuBar(self.create_main_menu())
