from PyQt6.QtCore import QEvent, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QUndoStack
from PyQt6.QtWidgets import QMainWindow, QWidget

import logging
import weakref
from contextlib import suppress
from typing import TYPE_CHECKING, Optional

from app.views.widgets.protocols import SystemDialogsProtocol
from app.ui.retranslatable import ReTranslatable
from app.views.widgets.link import LinksTableView

if TYPE_CHECKING:
    # Narrowly scoped types for static analysis only
    from typing import Any, Dict, Protocol

    class StructureItem(Protocol):
        """Structure (tree) item protocol used solely for static checks.

        At runtime the concrete type may be ``QModelIndex`` or another tree-model object.
        The protocol remains empty because ``MainWindow`` only forwards the value.
        """

        ...

    LinkDict = Dict[str, Any]
    from app.controllers.ui.links.links_actions import LinksActions
    from app.controllers.ui.menu_controller import ActionController, MenuController
    from app.controllers.ui.state.ui_state_manager import UIStateManager
    from app.controllers.ui.structure.spheres_bar_controller import SpheresBarController
    from app.controllers.ui.structure.structure_ui_controller import (
        StructureUIController,
    )
    from app.controllers.ui.theme_controller import ThemeController
    from app.controllers.ui.top_panels_controller import TopPanelsController

from app.controllers.ui.window_facade import WindowFacade
from app.settings import AppSettings
from app.utils.db.synchronization import signal_guard
from app.utils.ui.updates import suspend_updates
from app.views.widgets.status_bar import update_status_bar as _update_status_bar

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow, ReTranslatable):
    """Primary application window.

    Coordinates multiple controllers via ``WindowFacade``.
    Responsibilities focus on UI layout and handling Qt events.
    """
    
    shown: pyqtSignal = pyqtSignal()

    # Controllers initialized during bootstrap
    structure: "StructureUIController"
    menu_controller: "MenuController"
    action_controller: "ActionController"
    links_actions: "LinksActions"
    spheres_controller: "SpheresBarController"
    top_panels_controller: "TopPanelsController"
    ui_state: "UIStateManager"
    system_dialogs: SystemDialogsProtocol
    theme_ctrl: "ThemeController"
    
    # UI components
    table: LinksTableView
    left_panel: QWidget
    
    # Undo/Redo infrastructure
    undo_stack: Optional[QUndoStack]
    undo_action: Optional[QAction]
    redo_action: Optional[QAction]
    
    # Facade simplifies delegation logic
    facade: Optional[WindowFacade]

    def handle_import_browser_bookmarks(self) -> None:
        self.system_dialogs.handle_import_browser_bookmarks()

    # === Delegation via the facade ===
    
    def get_current_category_id(self) -> Optional[int]:
        """Return the ID of the currently selected category."""
        return self.facade.get_current_category_id() if self.facade else None

    def edit_structure_item(self, item: "StructureItem") -> None:
        """Edit a structure item."""
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
        self.table.selectAll()

    def get_selected_rows(self) -> list[int]:
        """Return indices of selected rows."""
        return self.facade.get_selected_rows() if self.facade else []

    def get_available_themes(self) -> list[tuple[str, str]]:
        """Return the list of available themes.

        Note: accesses ``theme_ctrl`` directly because it is invoked before facade initialization.
        """
        # Menu is built early (before facade), hence direct access
        return self.theme_ctrl.available() if hasattr(self, 'theme_ctrl') else []

    def apply_theme(self, theme_name: str) -> None:
        """Apply a theme immediately.

        Note: accesses ``theme_ctrl`` directly because it is invoked before facade initialization.
        """
        # Menu is used prior to facade availability, so keep direct access
        if hasattr(self, 'theme_ctrl'):
            self.theme_ctrl.apply(theme_name)

    def get_undo_stack(self) -> Optional[QUndoStack]:
        """Return the undo stack instance if available."""
        return getattr(self, "undo_stack", None)

    def create_undo_redo_actions(self) -> tuple[Optional[QAction], Optional[QAction]]:
        """Create Undo/Redo QAction instances."""
        us = getattr(self, "undo_stack", None)
        if us is None:
            return None, None

        undo_action = us.createUndoAction(self)
        undo_action.setText(self.tr("&Undo"))
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)

        redo_action = us.createRedoAction(self)
        redo_action.setText(self.tr("&Redo"))
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)

        us.undoTextChanged.connect(lambda *_: undo_action.setText(self.tr("&Undo")))
        us.redoTextChanged.connect(lambda *_: redo_action.setText(self.tr("&Redo")))

        self.undo_action = undo_action
        self.redo_action = redo_action

        # Diagnostics: track undo/redo triggers and stack state for double-activation analysis
        try:
            # Log menu/shortcut triggers
            undo_action.triggered.connect(
                lambda checked=False: logging.getLogger(__name__).debug(
                    "[UI] QAction.undo.triggered checked=%s", checked
                )
            )
            redo_action.triggered.connect(
                lambda checked=False: logging.getLogger(__name__).debug(
                    "[UI] QAction.redo.triggered checked=%s", checked
                )
            )
        except Exception:
            logger.debug(
                "MainWindow: failed to connect undo/redo triggered diagnostics",
                exc_info=True,
            )

        try:
            # Local safe callbacks via weakref to avoid touching deleted objects
            _us_ref = weakref.ref(us)

            def _on_index_changed(idx: int):
                u = _us_ref()
                if u is None:
                    return
                try:
                    can_undo = bool(u.canUndo())
                except RuntimeError:
                    return
                try:
                    can_redo = bool(u.canRedo())
                except RuntimeError:
                    return
                logging.getLogger(__name__).debug(
                    "[UndoStack] indexChanged=%s canUndo=%s canRedo=%s",
                    idx,
                    can_undo,
                    can_redo,
                )

            def _on_clean_changed(clean: bool):
                u = _us_ref()
                index_val = None
                if u is not None:
                    try:
                        index_val = u.index()
                    except RuntimeError:
                        index_val = None
                logging.getLogger(__name__).debug(
                    "[UndoStack] cleanChanged=%s index=%s", clean, index_val
                )

            us.indexChanged.connect(_on_index_changed)
            us.cleanChanged.connect(_on_clean_changed)
        except Exception:
            logger.debug(
                "MainWindow: failed to connect undo stack diagnostics (index/clean)",
                exc_info=True,
            )
        try:
            us.canUndoChanged.connect(
                lambda can: logging.getLogger(__name__).debug(
                    "[UndoStack] canUndoChanged=%s", can
                )
            )
        except Exception:
            logger.debug(
                "MainWindow: failed to connect canUndoChanged diagnostics",
                exc_info=True,
            )
        try:
            us.canRedoChanged.connect(
                lambda can: logging.getLogger(__name__).debug(
                    "[UndoStack] canRedoChanged=%s", can
                )
            )
        except Exception:
            logger.debug(
                "MainWindow: failed to connect canRedoChanged diagnostics",
                exc_info=True,
            )

        return undo_action, redo_action

    def __init__(self, settings: AppSettings, theme_ctrl: "ThemeController"):
        super().__init__()
        # Initialization moved to bootstrap; only accept core dependencies here.
        self.settings = settings
        self.theme_ctrl = theme_ctrl
        self.facade = None  # Assigned in bootstrap after controllers initialize

        # Debounce timer for search
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)  # 300 ms delay
        self._search_timer.timeout.connect(self._execute_search)
        self._pending_search = ""

        ReTranslatable.__init__(self)

    def retranslateUi(self) -> None:
        undo_action = getattr(self, "undo_action", None)
        if undo_action is not None:
            undo_action.setText(self.tr("&Undo"))
        redo_action = getattr(self, "redo_action", None)
        if redo_action is not None:
            redo_action.setText(self.tr("&Redo"))


    def _init_spheres_ui(self) -> None:
        """Initialize the spheres UI asynchronously."""
        self.spheres_controller.init()

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
        """Open the link dialog for the specified category."""
        return self.show_link_dialog(link=link, category_id=category_id)

    def _get_selected_links(self) -> list["LinkDict"]:
        """Return the list of selected links."""
        return self.facade.get_selected_links() if self.facade else []

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
        self.system_dialogs.show_about_dialog()

    def show_settings_dialog(self) -> None:
        self.system_dialogs.show_settings_dialog()

    def show_file_search_dialog(self) -> None:
        self.system_dialogs.show_file_search_dialog()

    def update_theme(self) -> None:
        """Apply the current theme and refresh the UI."""
        if self.facade:
            self.facade.update_theme()

    def update_widget_font_size(self, widget, size: int) -> None:
        """Apply a font size to a widget in a unified manner.

        Assumes the widget provides ``update_font_size(int)``.
        Safely handles missing attributes/methods and unexpected runtime errors.

        Note: the logic can be migrated into tree/table controllers later, leaving
        only delegation here.
        """
        try:
            with suppress(AttributeError, RuntimeError, TypeError, ValueError):
                if widget and hasattr(widget, "update_font_size"):
                    widget.update_font_size(size)
        except Exception:
            # Log widget type for diagnosing unexpected errors
            logger.exception(
                "MainWindow: unexpected error updating font size for %s",
                type(widget).__name__ if widget is not None else "<None>",
            )

    def apply_font_size_to_content(self, fs: int) -> None:
        """Apply font size to primary content widgets.

        Affects only tree and table widgets (user-facing preference).
        """
        if isinstance(fs, bool):  # guard against incorrect types
            return
        try:
            size = int(fs)
        except (TypeError, ValueError):
            return

        # Tree widget
        tree = getattr(self, "tree", None)
        self.update_widget_font_size(tree, size)

        # Table widget
        table = getattr(self, "table", None)
        self.update_widget_font_size(table, size)

        # Category tiles intentionally remain unchanged (independent font size)

    @signal_guard("_update_left_panel_style")
    def _update_left_panel_style(self, sphere_id: int) -> None:
        """Update left panel styling when the sphere changes."""
        current_sphere = self.left_panel.property("sphere")
        if current_sphere == str(sphere_id):
            return

        with suspend_updates(self.left_panel):
            self.left_panel.setProperty("sphere", str(sphere_id))
            self.left_panel.style().unpolish(self.left_panel)
            self.left_panel.style().polish(self.left_panel)

    def on_search(self, text: str) -> None:
        """Schedule search execution after a 300 ms debounce."""
        self._pending_search = text
        self._search_timer.start()  # Restart timer on each keystroke

    def _execute_search(self) -> None:
        """Execute the search after the debounce interval."""
        la = getattr(self, "links_actions", None)
        if la is None:
            logger.debug("MainWindow: links_actions not initialized yet")
            return
        try:
            la.on_search(self._pending_search)
        except Exception:
            logger.exception("MainWindow._execute_search failed")

    def showEvent(self, event: QEvent) -> None:
        """Emit ``shown`` signal the first time the window appears."""
        super().showEvent(event)
        if not hasattr(self, "_shown_emitted"):
            self._shown_emitted = True
            # Use queued single-shot to avoid blocking rendering if slot is heavy
            QTimer.singleShot(0, self.shown.emit)

    def closeEvent(self, event: QEvent) -> None:
        """Shut down gracefully and release resources."""
        logger.info("MainWindow.closeEvent: initiating shutdown")
        
        # ✅ ИСПРАВЛЕНИЕ: Comprehensive cleanup для предотвращения memory leaks
        self._cleanup_resources()
        
        if hasattr(self, "app_shutdown") and self.app_shutdown:
            try:
                logger.info("MainWindow.closeEvent: delegating to AppShutdownController")
                self.app_shutdown.perform_shutdown(event)
                return
            except Exception:
                logger.exception("MainWindow.closeEvent: AppShutdownController failed, falling back to base closeEvent")
        super().closeEvent(event)
    
    def _cleanup_resources(self) -> None:
        """✅ ИСПРАВЛЕНИЕ: Централизованная очистка ресурсов для предотвращения утечек памяти."""
        logger.debug("MainWindow._cleanup_resources: starting cleanup")
        
        # 1. Stop and cleanup search timer
        try:
            if hasattr(self, '_search_timer'):
                self._search_timer.stop()
                self._search_timer.timeout.disconnect()
                self._search_timer.deleteLater()
        except (AttributeError, RuntimeError):
            pass
        
        # 2. Disconnect undo/redo actions to prevent dangling references
        try:
            if hasattr(self, 'undo_action') and self.undo_action:
                self.undo_action.triggered.disconnect()
        except (AttributeError, RuntimeError, TypeError):
            pass
        
        try:
            if hasattr(self, 'redo_action') and self.redo_action:
                self.redo_action.triggered.disconnect()
        except (AttributeError, RuntimeError, TypeError):
            pass
        
        # 3. Cleanup undo stack connections
        try:
            if hasattr(self, 'undo_stack') and self.undo_stack:
                # Disconnect all signals to prevent callbacks on deleted objects
                self.undo_stack.indexChanged.disconnect()
                self.undo_stack.cleanChanged.disconnect()
                self.undo_stack.canUndoChanged.disconnect()
                self.undo_stack.canRedoChanged.disconnect()
        except (AttributeError, RuntimeError, TypeError):
            pass
        
        # 4. Cleanup facade and controllers
        try:
            if hasattr(self, 'facade') and self.facade:
                if hasattr(self.facade, 'cleanup'):
                    self.facade.cleanup()
        except Exception as e:
            logger.warning("MainWindow._cleanup_resources: facade cleanup error: %s", e)
        
        # 5. Clear table model to prevent access to deleted data
        try:
            if hasattr(self, 'table') and self.table:
                self.table.setModel(None)
        except (AttributeError, RuntimeError):
            pass
        
        logger.debug("MainWindow._cleanup_resources: cleanup completed")
