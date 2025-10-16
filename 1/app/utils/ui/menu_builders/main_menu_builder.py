"""Builder for the application's main menu."""

import logging
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QMenuBar, QWidget

from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.menu_builders.menu_actions import ActionBuilder, MenuTexts, Shortcuts

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

    def build(self) -> QMenuBar:
        """Create and return the fully built main menu bar."""
        logger.debug("Creating main menu for theme: %s", self.theme)

        menubar = QMenuBar(cast(QWidget, self.main_window))

        # First item — unified Actions menu
        self._create_actions_menu(menubar)
        # Second item — Data menu
        self._create_data_menu(menubar)
        self._create_file_menu(menubar)
        self._create_search_menu(menubar)
        self._create_themes_menu(menubar)
        self._create_help_menu(menubar)

        return menubar

    def _get_icon(self, name: str, source: str = "main_menu"):
        """Get themed icon for the current theme."""
        return icon_cache.get_icon(name, self.theme, source)

    def _create_actions_menu(self, menubar: QMenuBar):
        """Create the '&Actions' menu as the first item, unified with context menus."""
        actions_menu = menubar.addMenu(
            QCoreApplication.translate("MainMenu", "&Actions")
        )

        if actions_menu is None:
            logger.warning("Main menu: failed to create Actions menu")
            return

        # Add section
        actions_menu.addAction(
            self.actions.create(
                MenuTexts.ADD_SECTION,
                getattr(self.main_window, "show_section_dialog", None),
                Shortcuts.ADD_SECTION,
                self._get_icon("add_section"),
            )
        )

        # Add category
        actions_menu.addAction(
            self.actions.create(
                MenuTexts.ADD_CATEGORY,
                getattr(self.main_window, "add_new_category", None),
                Shortcuts.ADD_CATEGORY,
                self._get_icon("add_category"),
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
                logger.exception("[MainMenu] Error adding link from Actions menu")

        actions_menu.addAction(
            self.actions.create(
                MenuTexts.ADD_LINK,
                _add_link_current_category,
                Shortcuts.ADD_LINK,
                self._get_icon("add_link"),
            )
        )

        actions_menu.addSeparator()

        # Undo/Redo via window's public methods
        undo_action, redo_action = self.main_window.create_undo_redo_actions()
        if undo_action and redo_action:
            undo_action.setIcon(self._get_icon("undo"))
            redo_action.setIcon(self._get_icon("redo"))

        if getattr(self.main_window, "undo_action", None) is not None:
            actions_menu.addAction(self.main_window.undo_action)
        if getattr(self.main_window, "redo_action", None) is not None:
            actions_menu.addAction(self.main_window.redo_action)

        actions_menu.addSeparator()

        # Clear favorites — before Exit
        actions_menu.addAction(
            self.actions.create(
                MenuTexts.CLEAR_FAVORITES,
                self._clear_favorites,
                icon=self._get_icon("delete"),
            )
        )

        # Exit
        actions_menu.addAction(
            self.actions.create(
                MenuTexts.EXIT,
                getattr(self.main_window, "close", None),
                icon=self._get_icon("exit"),
            )
        )

    def _create_file_menu(self, menubar: QMenuBar):
        """Create the '&File' menu."""
        file_menu = menubar.addMenu(QCoreApplication.translate("MainMenu", "&File"))

        if file_menu is None:
            logger.warning("Main menu: failed to create File menu")
            return

        # Settings
        file_menu.addAction(
            self.actions.create(
                MenuTexts.SETTINGS,
                self.main_window.show_settings_dialog,
                icon=self._get_icon("settings"),
            )
        )

        # Items moved: Import/DB/Icons — see '&Data'. Exit — in '&Actions'.

    def _create_data_menu(self, menubar: QMenuBar):
        """Create the '&Data' menu."""
        data_menu = menubar.addMenu(QCoreApplication.translate("MainMenu", "&Data"))

        if data_menu is None:
            logger.warning("Main menu: failed to create Data menu")
            return

        data_menu.addAction(
            self.actions.create(
                MenuTexts.SAVE_DATABASE,
                self._save_database,
                icon=self._get_icon("export"),
            )
        )
        data_menu.addAction(
            self.actions.create(
                MenuTexts.RESTORE_DATABASE,
                self._restore_database,
                icon=self._get_icon("dbrestore"),
            )
        )
        data_menu.addAction(
            self.actions.create(
                MenuTexts.CONNECT_DATABASE,
                self._connect_database,
                icon=self._get_icon("import"),
            )
        )

        data_menu.addSeparator()

        # Import from browser
        data_menu.addAction(
            self.actions.create(
                MenuTexts.IMPORT_BROWSER,
                self.main_window.handle_import_browser_bookmarks,
                icon=self._get_icon("import"),
            )
        )

        data_menu.addSeparator()

        # Icon operations
        data_menu.addAction(
            self.actions.create(
                MenuTexts.EXPORT_ICONS, self._save_icons, icon=self._get_icon("zip_ico")
            )
        )
        data_menu.addAction(
            self.actions.create(
                MenuTexts.IMPORT_ICONS, self._load_icons, icon=self._get_icon("add_ico")
            )
        )

    def _create_search_menu(self, menubar: QMenuBar):
        """Create the '&Search' menu."""
        search_menu = menubar.addMenu(QCoreApplication.translate("MainMenu", "&Search"))

        if search_menu is None:
            logger.warning("Main menu: failed to create Search menu")
            return
        search_menu.addAction(
            self.actions.create(
                MenuTexts.SEARCH_FILES,
                self.main_window.show_file_search_dialog,
                icon=self._get_icon("search"),
            )
        )

    def _create_themes_menu(self, menubar: QMenuBar):
        """Create the '&Themes' menu."""
        themes_menu = menubar.addMenu(QCoreApplication.translate("MainMenu", "&Themes"))

        if themes_menu is None:
            logger.warning("Main menu: failed to create Themes menu")
            return

        theme_icons = {"dark": self._get_icon("dark"), "light": self._get_icon("light")}

        for name, display_name in self.main_window.get_available_themes():
            icon = theme_icons.get(name) or self._get_icon(name)

            # Create handler with proper closure per theme
            def make_theme_handler(theme_name):
                return lambda: self.main_window.apply_theme(theme_name)

            # Translate theme name using QCoreApplication.translate
            translated_name = QCoreApplication.translate("Themes", display_name)
            action = self.actions.create(
                translated_name, make_theme_handler(name), icon=icon
            )
            themes_menu.addAction(action)

    def _create_help_menu(self, menubar: QMenuBar):
        """Create the '&Help' menu."""
        help_menu = menubar.addMenu(QCoreApplication.translate("MainMenu", "&Help"))

        if help_menu is None:
            logger.warning("Main menu: failed to create Help menu")
            return
        help_menu.addAction(
            self.actions.create(
                MenuTexts.ABOUT,
                self.main_window.show_about_dialog,
                icon=self._get_icon("help"),
            )
        )

    # Menu action handlers

    def _clear_favorites(self):
        """Clear favorites — delegated to DialogController."""
        if hasattr(self.main_window, "database_controller"):
            self.main_window.database_controller.handle_clear_favorites()

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
