import logging
from typing import TYPE_CHECKING, Any, Optional

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence, QShowEvent, QUndoStack
from PyQt6.QtWidgets import QMainWindow, QScrollArea, QSplitter, QStackedLayout, QWidget

from app.views.common.retranslatable import ReTranslatable
from app.views.widgets.link import LinksTableView
from app.views.widgets.protocols import SystemDialogsProtocol

if TYPE_CHECKING:
    # Narrowly scoped types for static analysis only
    from typing import Any, Protocol

    class StructureItem(Protocol):
        """Structure (tree) item protocol used solely for static checks.

        At runtime the concrete type may be ``QModelIndex`` or another tree-model object.
        The protocol remains empty because ``MainWindow`` only forwards the value.
        """

        ...

    LinkDict = dict[str, Any]
    from app.controllers.ui.links.links_actions import LinksActions
    from app.controllers.ui.menu_controller import MenuController
    from app.controllers.ui.state.ui_state_manager import UIStateManager
    from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
    from app.controllers.ui.structure.structure_ui_controller import (
        StructureUIController,
    )
    from app.controllers.ui.theme_controller import ThemeController
    from app.controllers.ui.top_panels_controller import TopPanelsController
    from app.views.widgets.tiles import CategoryTiles

from app.controllers.ui.window_facade import WindowFacade
from app.settings import AppSettings
from app.utils.db.synchronization import signal_guard
from app.utils.ui.updates import suspend_updates
from app.views.main_components.ui.bottom_panel_setup import retranslate_bottom_panel
from app.views.main_components.ui.window_widgets import MainWindowWidgets
from app.views.widgets.status_bar import update_status_bar as _update_status_bar

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow, ReTranslatable):
    """Primary application window.

    Coordinates multiple controllers via ``WindowFacade``.
    Responsibilities focus on UI layout and handling Qt events.
    """

    shown: pyqtSignal = pyqtSignal()

    db: Optional[Any]  # Database instance for shutdown controller
    structure: Optional["StructureUIController"]
    menu_controller: Optional["MenuController"]
    action_controller: Optional[Any]  # ActionController removed
    links_actions: Optional["LinksActions"]
    spheres_controller: Optional["SpheresBarController"]
    top_panels_controller: Optional["TopPanelsController"]
    ui_state: Optional["UIStateManager"]
    system_dialogs: Optional[SystemDialogsProtocol]
    theme_ctrl: "ThemeController"
    table: Optional[LinksTableView]
    left_panel: Optional[QWidget]
    undo_stack: Optional[QUndoStack]
    undo_action: Optional[QAction]
    redo_action: Optional[QAction]
    facade: Optional[WindowFacade]

    _SEARCH_DEBOUNCE_MS = 300

    @property
    def widgets(self) -> MainWindowWidgets:
        return self._widgets

    @property
    def tiles_scroll(self) -> QScrollArea | None:
        return self._widgets.tiles_scroll

    @tiles_scroll.setter
    def tiles_scroll(self, value: QScrollArea | None) -> None:
        self._widgets.tiles_scroll = value

    @property
    def tiles(self) -> "CategoryTiles | None":
        return self._widgets.tiles

    @tiles.setter
    def tiles(self, value: "CategoryTiles | None") -> None:
        self._widgets.tiles = value

    @property
    def table(self) -> LinksTableView | None:
        return self._widgets.table

    @table.setter
    def table(self, value: LinksTableView | None) -> None:
        self._widgets.table = value

    @property
    def table_container(self) -> QWidget | None:
        return self._widgets.table_container

    @table_container.setter
    def table_container(self, value: QWidget | None) -> None:
        self._widgets.table_container = value

    @property
    def stack(self) -> QStackedLayout | None:
        return self._widgets.stack

    @stack.setter
    def stack(self, value: QStackedLayout | None) -> None:
        self._widgets.stack = value

    @property
    def splitter(self) -> QSplitter | None:
        return self._widgets.splitter

    @splitter.setter
    def splitter(self, value: QSplitter | None) -> None:
        self._widgets.splitter = value

    def handle_import_browser_bookmarks(self) -> None:
        if self.system_dialogs:
            self.system_dialogs.handle_import_browser_bookmarks()

    def get_current_category_id(self) -> Optional[int]:
        """Return the ID of the currently selected category."""
        return self.facade.get_current_category_id() if self.facade else None

    def edit_structure_item(self, item: "StructureItem") -> None:
        """Edit a structure item."""
        if self.structure:
            self.structure.edit_item(item)

    def add_new_category(self) -> None:
        """Create a new category."""
        if self.facade:
            self.facade.add_new_category()

    def reload_structure(self) -> None:
        """Reload the entire structure tree."""
        if self.facade:
            self.facade.reload_structure()

    def reload_current_category(self) -> None:
        """Reload the currently selected category."""
        if self.facade:
            self.facade.reload_current_category()

    def get_link_at_row(self, row: int) -> "LinkDict | None":
        """Return the link at the given row index."""
        return self.facade.get_link_at_row(row) if self.facade else None

    def select_all_links(self) -> None:
        """Select all link rows."""
        if self.table is not None:
            self.table.selectAll()

    def get_selected_rows(self) -> list[int]:
        """Return indices of selected rows."""
        return self.facade.get_selected_rows() if self.facade else []

    def get_available_themes(self) -> list[tuple[str, str]]:
        """Return the list of available themes."""
        return self.theme_ctrl.available()

    def apply_theme(self, theme_name: str) -> None:
        """Apply a theme immediately."""
        self.theme_ctrl.apply(theme_name)

    def get_undo_stack(self) -> Optional[QUndoStack]:
        """Return the undo stack instance if available."""
        return getattr(self, "undo_stack", None)

    def create_undo_redo_actions(self) -> tuple[Optional[QAction], Optional[QAction]]:
        """Create Undo/Redo QAction instances."""
        us = getattr(self, "undo_stack", None)
        if us is None:
            return None, None

        from app.utils.ui.menu_builders.menu_actions import MenuTexts

        undo_action = us.createUndoAction(self)
        undo_action.setText(self.tr(MenuTexts.UNDO))
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)

        redo_action = us.createRedoAction(self)
        redo_action.setText(self.tr(MenuTexts.REDO))
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)

        us.undoTextChanged.connect(
            lambda *_: undo_action.setText(self.tr(MenuTexts.UNDO))
        )
        us.redoTextChanged.connect(
            lambda *_: redo_action.setText(self.tr(MenuTexts.REDO))
        )

        self.undo_action = undo_action
        self.redo_action = redo_action

        return undo_action, redo_action

    def __init__(self, settings: AppSettings, theme_ctrl: "ThemeController"):
        super().__init__()
        self.settings = settings
        self.theme_ctrl = theme_ctrl
        self._widgets = MainWindowWidgets()
        # Dependencies are injected after construction; initialize placeholders to avoid attribute errors.
        self.facade: Optional[WindowFacade] = None
        self.structure = None
        self.menu_controller = None
        self.action_controller = None
        self.links_actions = None
        self.spheres_controller = None
        self.top_panels_controller = None
        self.ui_state = None
        self.system_dialogs = None
        self.table = None
        self.left_panel = None
        self.undo_stack = None
        self.undo_action = None
        self.redo_action = None
        self.app_shutdown = None

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self._SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._execute_search)
        self._pending_search = ""
        self._current_sphere_id: Optional[int] = None

        ReTranslatable.__init__(self)

    def retranslateUi(self) -> None:
        undo_action = getattr(self, "undo_action", None)
        if undo_action is not None:
            undo_action.setText(self.tr("&Undo"))
        redo_action = getattr(self, "redo_action", None)
        if redo_action is not None:
            redo_action.setText(self.tr("&Redo"))
        switch_action = getattr(self, "switch_sphere_action", None)
        if switch_action is not None:
            switch_action.setText(self.tr("Switch Sphere (F6)"))
            switch_action.setToolTip(self.tr("Switch to next available sphere"))
        # switch_sphere_button now handled by retranslate_bottom_panel (unified)
        retranslate_bottom_panel(self)

    def show_link_dialog(
        self,
        link: "LinkDict | None" = None,
        category_id: int | None = None,
    ) -> bool:
        """Show the create/edit link dialog."""
        if not self.facade:
            return False

        result = self.facade.show_link_dialog(link, category_id)
        self.update_statusbar()
        return result

    def show_link_dialog_for_category(
        self, category_id: int | None = None, link: "LinkDict | None" = None
    ) -> bool:
        """Legacy convenience wrapper used by menu/tiles actions."""
        return self.show_link_dialog(link=link, category_id=category_id)

    def _edit_selected_link(self) -> bool:
        """Edit the currently selected link."""
        return self.facade.edit_selected_link() if self.facade else False

    def edit_current(self) -> None:
        """Edit the current item."""
        if self.facade:
            self.facade.edit_current()

    def delete_current(self) -> None:
        """Delete the current item."""
        if self.facade:
            self.facade.delete_current()

    def show_section_dialog(self) -> None:
        """Open the dialog for creating a section."""
        if self.facade:
            self.facade.add_new_section()

    def update_statusbar(self) -> None:
        _update_status_bar(self)

    def on_structure_item_added(
        self, item_type: str, parent_id: int, data: dict
    ) -> None:
        """Handle structure item creation events."""
        if self.facade:
            self.facade.on_structure_item_added(item_type, parent_id, data)

    @signal_guard("on_structure_item_changed")
    def on_structure_item_changed(
        self, item_type: str, item_id: int, data: dict
    ) -> None:
        """Handle structure item change events."""
        if self.facade:
            self.facade.on_structure_item_changed(item_type, item_id, data)

    def show_about_dialog(self) -> None:
        if self.system_dialogs is not None:
            self.system_dialogs.show_about_dialog()

    def show_settings_dialog(self) -> None:
        if self.system_dialogs is not None:
            self.system_dialogs.show_settings_dialog()

    def show_file_search_dialog(self) -> None:
        if self.system_dialogs is not None:
            self.system_dialogs.show_file_search_dialog()

    def update_theme(self) -> None:
        """Apply the current theme and refresh the UI."""
        if self.facade:
            self.facade.update_theme()

    def apply_font_size_to_content(self, fs: int) -> None:
        """Apply font size to tree and table widgets."""
        try:
            size = int(fs)
        except (TypeError, ValueError):
            logger.warning("MainWindow: invalid font size type: %s", type(fs).__name__)
            return

        tree = getattr(self, "tree", None)
        if tree and hasattr(tree, "update_font_size"):
            try:
                tree.update_font_size(size)
            except (AttributeError, RuntimeError) as e:
                logger.debug("MainWindow: failed to update tree font size: %s", e)

        table = getattr(self, "table", None)
        if table and hasattr(table, "update_font_size"):
            try:
                table.update_font_size(size)
            except (AttributeError, RuntimeError) as e:
                logger.debug("MainWindow: failed to update table font size: %s", e)

    @signal_guard("_update_left_panel_style")
    def _update_left_panel_style(self, sphere_id: int) -> None:
        """Update left panel styling when the sphere changes."""
        if self._current_sphere_id == sphere_id:
            return

        self._current_sphere_id = sphere_id
        if self.left_panel is not None:
            with suspend_updates(self.left_panel):  # type: ignore[arg-type]
                self.left_panel.setProperty("sphere", str(sphere_id))
                style = self.left_panel.style()
                if style is not None:
                    style.unpolish(self.left_panel)
                    style.polish(self.left_panel)

    def on_search(self, text: str) -> None:
        """Schedule search execution after debounce."""
        self._pending_search = text
        self._search_timer.start()

    def _execute_search(self) -> None:
        """Execute the search after the debounce interval."""
        la = getattr(self, "links_actions", None)
        if la is None:
            logger.debug("MainWindow: links_actions not initialized yet")
            return
        la.on_search(self._pending_search)

    def showEvent(self, event: QShowEvent | None) -> None:
        """Emit ``shown`` signal the first time the window appears."""
        super().showEvent(event)
        if not hasattr(self, "_shown_emitted"):
            self._shown_emitted = True
            QTimer.singleShot(0, self.shown.emit)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        """Shut down gracefully and release resources."""
        logger.info("MainWindow.closeEvent: initiating shutdown")

        self._cleanup_resources()

        if hasattr(self, "app_shutdown") and self.app_shutdown:
            try:
                logger.info(
                    "MainWindow.closeEvent: delegating to AppShutdownController"
                )
                self.app_shutdown.perform_shutdown(event)  # type: ignore[arg-type]
                return
            except Exception:
                logger.exception(
                    "MainWindow.closeEvent: AppShutdownController failed, falling back to base closeEvent"
                )
        super().closeEvent(event)

    def _cleanup_resources(self) -> None:
        """Centralized resource cleanup to prevent memory leaks."""
        logger.debug("MainWindow: starting cleanup")

        cleanup_tasks = [
            ("search_timer", lambda: self._cleanup_timer()),
            ("undo_stack", lambda: self._cleanup_undo_stack()),
            ("facade", lambda: self._cleanup_facade()),
            ("table", lambda: self._cleanup_table()),
        ]

        for task_name, cleanup_func in cleanup_tasks:
            try:
                cleanup_func()
            except Exception as e:
                logger.debug("MainWindow: cleanup %s failed: %s", task_name, e)

        try:
            self.widgets.clear()
        except Exception as exc:
            logger.debug(
                "MainWindow: failed to clear widget container during cleanup",
                exc_info=True,
            )

        logger.debug("MainWindow: cleanup completed")

    def _cleanup_timer(self) -> None:
        """Stop and disconnect search timer."""
        if hasattr(self, "_search_timer"):
            self._search_timer.stop()
            try:
                self._search_timer.timeout.disconnect()
            except TypeError:
                pass

    def _cleanup_undo_stack(self) -> None:
        """Disconnect undo/redo actions and stack signals."""
        for action_name in ("undo_action", "redo_action"):
            action = getattr(self, action_name, None)
            if action:
                try:
                    action.triggered.disconnect()
                except TypeError:
                    pass

        us = getattr(self, "undo_stack", None)
        if us:
            for signal in (us.undoTextChanged, us.redoTextChanged):
                try:
                    signal.disconnect()
                except TypeError:
                    pass

    def _cleanup_facade(self) -> None:
        """Cleanup facade if cleanup method exists."""
        if self.facade and hasattr(self.facade, "cleanup"):
            self.facade.cleanup()

    def _cleanup_table(self) -> None:
        """Clear table model to prevent access to deleted data."""
        table = getattr(self, "table", None)
        if table:
            table.setModel(None)
