import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtCore import QItemSelection, QItemSelectionModel, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QShowEvent, QUndoStack
from PyQt6.QtWidgets import (
    QMainWindow,
    QMenuBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedLayout,
    QWidget,
)

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
from app.utils.ui.db_sync import signal_guard
from app.utils.ui.full_diag import (
    FullDiagEventFilter,
    install_on,
)
from app.utils.ui.full_diag import (
    enabled as diag_enabled,
)
from app.utils.ui.updates import suspend_updates
from app.views.main_components.ui.bottom_panel_setup import retranslate_bottom_panel
from app.views.main_components.ui.window_widgets import MainWindowWidgets
from app.views.widgets.status_bar import set_status_message
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
    action_controller: Optional[Any]
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
    cut_action: Optional[QAction]
    copy_action: Optional[QAction]
    paste_action: Optional[QAction]
    delete_action: Optional[QAction]
    select_all_action: Optional[QAction]
    _undo_actions_stack: Optional[QUndoStack]
    facade: Optional[WindowFacade]

    _SEARCH_DEBOUNCE_MS = 300

    @property
    def widgets(self) -> MainWindowWidgets:
        return self._widgets

    def _require_facade(self) -> WindowFacade:
        """Return facade or raise if it is not initialized."""
        if self.facade is None:
            raise RuntimeError("MainWindow: facade is not initialized")
        return self.facade

    def set_facade(self, facade: WindowFacade) -> None:
        """Attach WindowFacade after construction; warn on reassign."""
        if self.facade is not None and self.facade is not facade:
            logger.warning("MainWindow: facade already set, overriding existing instance")
        self.facade = facade

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

    def handle_import_text_links(self) -> None:
        if self.system_dialogs:
            self.system_dialogs.handle_import_text_links()

    def get_current_category_id(self) -> Optional[int]:
        """Return the ID of the currently selected category."""
        if self.facade is None:
            logger.debug("MainWindow: get_current_category_id requested before facade is initialized")
            return None
        return self.facade.get_current_category_id()

    def navigate_back(self) -> bool:
        ui_state = getattr(self, "ui_state", None)
        if ui_state and hasattr(ui_state, "navigate_back"):
            return bool(ui_state.navigate_back())
        return False

    def navigate_forward(self) -> bool:
        ui_state = getattr(self, "ui_state", None)
        if ui_state and hasattr(ui_state, "navigate_forward"):
            return bool(ui_state.navigate_forward())
        return False

    def update_navigation_history_state(self, can_back: bool, can_forward: bool) -> None:
        struct_widget = getattr(self, "structure_actions_widget", None)
        if struct_widget and hasattr(struct_widget, "update_navigation_state"):
            struct_widget.update_navigation_state(can_back, can_forward)

    def edit_structure_item(self, item: "StructureItem") -> None:
        """Edit a structure item."""
        if self.structure:
            self.structure.edit_item(item)

    def add_new_category(self) -> None:
        """Create a new category."""
        self._require_facade().add_new_category()

    def launch_marked_links(self) -> None:
        """Launch all marked links in the current category."""
        self._require_facade().launch_marked_links()

    def update_group_launch_action_state(self) -> None:
        """Update enabled state of the group launch button and shortcut."""
        table = getattr(self, "table", None)
        category_id = self.get_current_category_id()
        is_enabled = False
        if category_id and table is not None:
            from app.config_data.runtime_config import get_tiles_stack_index

            stack = getattr(self, "stack", None)
            is_table_active = (
                stack is None or stack.currentIndex() != get_tiles_stack_index()
            )
            if is_table_active:
                if hasattr(table, "has_marked_links"):
                    is_enabled = bool(table.has_marked_links())
                else:
                    model = table.model()
                    if model is not None:
                        for row in range(model.rowCount()):
                            link = self.get_link_at_row(row)
                            if link and bool(link.get("is_group_launch")):
                                is_enabled = True
                                break
        container = getattr(self, "bottom_bar_container", None)
        if container:
            btn = container.findChild(QPushButton, "bottomBarButton_launch_marked")
            if btn:
                btn.setEnabled(is_enabled)
    def reload_structure(self) -> None:
        """Reload the entire structure tree."""
        self._require_facade().reload_structure()

    def reload_current_category(self) -> None:
        """Reload the currently selected category."""
        self._require_facade().reload_current_category()

    def get_link_at_row(self, row: int) -> "LinkDict | None":
        """Return the link at the given row index."""
        return self._require_facade().get_link_at_row(row)

    def select_all_links(self) -> None:
        """Select all link rows."""
        table = self.table
        if table is None:
            return
        model = table.model() if hasattr(table, "model") else None
        selection_model = (
            table.selectionModel() if hasattr(table, "selectionModel") else None
        )
        if model is None or selection_model is None:
            return

        try:
            rows = int(model.rowCount())
            columns = int(model.columnCount())
        except Exception:
            logger.debug(
                "MainWindow.select_all_links: failed to inspect model", exc_info=True
            )
            table.selectAll()
            return

        if rows <= 0 or columns <= 0:
            return

        try:
            table.setUpdatesEnabled(False)
            top_left = model.index(0, 0)
            bottom_right = model.index(rows - 1, columns - 1)
            selection = QItemSelection(top_left, bottom_right)
            selection_model.select(
                selection,
                QItemSelectionModel.SelectionFlag.ClearAndSelect
                | QItemSelectionModel.SelectionFlag.Rows,
            )
            selection_model.setCurrentIndex(
                top_left,
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
        except Exception:
            logger.debug(
                "MainWindow.select_all_links: optimized selection failed",
                exc_info=True,
            )
            table.selectAll()
        finally:
            try:
                table.setUpdatesEnabled(True)
                viewport = table.viewport() if hasattr(table, "viewport") else None
                if viewport is not None:
                    viewport.update()
            except Exception:
                logger.debug(
                    "MainWindow.select_all_links: failed to restore updates",
                    exc_info=True,
                )

    def get_selected_rows(self) -> list[int]:
        """Return indices of selected rows."""
        return self._require_facade().get_selected_rows()

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

        undo_action = getattr(self, "undo_action", None)
        redo_action = getattr(self, "redo_action", None)
        if (
            undo_action is not None
            and redo_action is not None
            and getattr(self, "_undo_actions_stack", None) is us
        ):
            self._refresh_undo_text()
            self._refresh_redo_text()
            return undo_action, redo_action

        if undo_action is not None or redo_action is not None:
            self._cleanup_undo_stack()

        from PyQt6.QtCore import QCoreApplication

        from app.utils.ui.menu_builders.menu_actions import MenuTexts

        undo_action = us.createUndoAction(self)
        undo_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.UNDO))

        redo_action = us.createRedoAction(self)
        redo_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.REDO))

        us.undoTextChanged.connect(self._refresh_undo_text)
        us.redoTextChanged.connect(self._refresh_redo_text)

        self.undo_action = undo_action
        self.redo_action = redo_action
        self._undo_actions_stack = us
        try:
            action_controller = getattr(self, "action_controller", None)
            if action_controller is not None:
                action_controller._wire_undo_redo_actions()
        except Exception:
            logger.debug("MainWindow: failed to wire undo/redo actions", exc_info=True)

        return undo_action, redo_action

    def _refresh_undo_text(self) -> None:
        """Update undo action text from translations."""
        if self.undo_action:
            from PyQt6.QtCore import QCoreApplication

            from app.utils.ui.menu_builders.menu_actions import MenuTexts

            self.undo_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.UNDO))

    def _refresh_redo_text(self) -> None:
        """Update redo action text from translations."""
        if self.redo_action:
            from PyQt6.QtCore import QCoreApplication

            from app.utils.ui.menu_builders.menu_actions import MenuTexts

            self.redo_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.REDO))

    def _discard_undo_redo_actions(self) -> None:
        """Remove undo/redo actions from the window and release references."""
        for action_name in ("undo_action", "redo_action"):
            action = getattr(self, action_name, None)
            if action is None:
                continue
            try:
                self.removeAction(action)
            except Exception:
                pass
            try:
                action.deleteLater()
            except Exception:
                pass
        self.undo_action = None
        self.redo_action = None
        self._undo_actions_stack = None

    def __init__(self, settings: AppSettings, theme_ctrl: "ThemeController", facade: WindowFacade | None = None):
        super().__init__()
        # Разрешаем QSS прокрашивать фон всего окна, иначе остаётся системная рамка
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Prevent resize artifacts by ensuring proper paint events
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.setAutoFillBackground(True)
        self._full_diag_filter = None
        if diag_enabled():
            try:
                self._full_diag_filter = FullDiagEventFilter()
                install_on(self, "MainWindow", self._full_diag_filter)
            except Exception:
                logger.debug(
                    "MainWindow: failed to install FullDiagEventFilter",
                    exc_info=True,
                )
        self.settings = settings
        self.theme_ctrl = theme_ctrl
        if self.theme_ctrl is not None:
            if hasattr(self.theme_ctrl, "set_main_window"):
                self.theme_ctrl.set_main_window(self)
            else:
                self.theme_ctrl.main_window = self
        self.theme_selector = None
        self.theme_selector_container = None
        self.theme_selector_separator = None
        self._widgets = MainWindowWidgets()
        # Dependencies are injected after construction; initialize placeholders to avoid attribute errors.
        self.facade: Optional[WindowFacade] = facade
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
        self.cut_action = None
        self.copy_action = None
        self.paste_action = None
        self.delete_action = None
        self.select_all_action = None
        self._undo_actions_stack = None
        self.app_shutdown = None
        self.command_palette_controller = None
        self._menu_bar_widget: QMenuBar | None = None

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self._SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._execute_search)
        self._pending_search = ""
        self._current_sphere_id: Optional[int] = None

        ReTranslatable.__init__(self)

    # --- Menu bar management -------------------------------------------------

    def install_menu_bar_widget(self, menu_bar: QMenuBar) -> None:
        """Install menu bar in the native window slot."""
        self._menu_bar_widget = menu_bar
        super().setMenuBar(menu_bar)

    def get_menu_bar_widget(self) -> QMenuBar | None:
        return self._menu_bar_widget

    def menuBar(self) -> QMenuBar | None:  # type: ignore[override]
        return super().menuBar()

    # --- Overrides -----------------------------------------------------------

    def retranslateUi(self) -> None:
        from PyQt6.QtCore import QCoreApplication

        for button in getattr(self, "sphere_buttons", {}).values():
            name = button.property("sphereName")
            if name in ("AI", "Work", "Study", "Personal"):
                button.setToolTip(QCoreApplication.translate("SpheresBarController", name))
        undo_action = getattr(self, "undo_action", None)
        if undo_action is not None:
            from PyQt6.QtCore import QCoreApplication

            from app.utils.ui.menu_builders.menu_actions import MenuTexts

            undo_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.UNDO))
        redo_action = getattr(self, "redo_action", None)
        if redo_action is not None:
            from PyQt6.QtCore import QCoreApplication

            from app.utils.ui.menu_builders.menu_actions import MenuTexts

            redo_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.REDO))
        switch_action = getattr(self, "switch_sphere_action", None)
        if switch_action is not None:
            switch_action.setText(self.tr("Switch Sphere (F6)"))
            switch_action.setToolTip(self.tr("Switch to next available sphere"))
        action_controller = getattr(self, "action_controller", None)
        if action_controller is not None:
            try:
                action_controller.retranslate_actions()
            except Exception:
                logger.debug("MainWindow: failed to retranslate global actions", exc_info=True)
        settings_action = getattr(self, "settings_action", None)
        settings_text = QCoreApplication.translate("MenuActions", "Settings")
        if settings_action is not None:
            settings_action.setToolTip(settings_text)
        settings_btn = getattr(self, "settings_button", None)
        if settings_btn is not None:
            settings_btn.setToolTip(settings_text)
        light_action = getattr(self, "light_theme_action", None)
        light_text = QCoreApplication.translate("MenuActions", "Light themes")
        if light_action is not None:
            light_action.setToolTip(light_text)
        light_btn = getattr(self, "light_theme_button", None)
        if light_btn is not None:
            light_btn.setToolTip(light_text)
        dark_action = getattr(self, "dark_theme_action", None)
        dark_text = QCoreApplication.translate("MenuActions", "Dark themes")
        if dark_action is not None:
            dark_action.setToolTip(dark_text)
        dark_btn = getattr(self, "dark_theme_button", None)
        if dark_btn is not None:
            dark_btn.setToolTip(dark_text)
        tools_adapter = getattr(self, "tools_actions_widget", None)
        if tools_adapter and hasattr(tools_adapter, "refresh_actions"):
            tools_adapter.refresh_actions()
        # switch_sphere_button now handled by retranslate_bottom_panel (unified)
        retranslate_bottom_panel(self)

    def toggle_left_panel(self) -> None:
        """Toggle visibility of the left structure panel."""
        splitter = self.splitter
        if splitter is None:
            return
        sizes = splitter.sizes()
        if not sizes or len(sizes) < 2:
            return
        total_w = sum(sizes)
        if sizes[0] > 0:
            self._saved_left_panel_width = sizes[0]
            splitter.setCollapsible(0, True)
            splitter.setSizes([0, max(1, total_w)])
        else:
            saved_w = getattr(self, "_saved_left_panel_width", None)
            if not saved_w or saved_w <= 0:
                saved_w = 320
            splitter.setSizes([saved_w, max(1, total_w - saved_w)])
            splitter.setCollapsible(0, False)

    def switch_to_next_sphere(self) -> None:
        """Switch to the next available sphere."""
        structure = getattr(self, "structure", None)
        if structure is None or not hasattr(structure, "switch_to_next_sphere"):
            logger.warning("SwitchSphere: structure controller not available")
            return
        try:
            structure.switch_to_next_sphere()
        except Exception:
            logger.exception("SwitchSphere: failed to switch sphere")

    def show_link_dialog(
        self,
        link: "LinkDict | None" = None,
        category_id: int | None = None,
    ) -> bool:
        """Show the create/edit link dialog."""
        result = self._require_facade().show_link_dialog(link, category_id)

        self.update_statusbar()
        return result

    def show_link_dialog_for_category(
        self, category_id: int | None = None, link: "LinkDict | None" = None
    ) -> bool:
        """Legacy convenience wrapper used by menu/tiles actions."""
        return self.show_link_dialog(link=link, category_id=category_id)

    def _edit_selected_link(self) -> bool:
        """Edit the currently selected link."""
        return self._require_facade().edit_selected_link()

    def edit_current(self) -> None:
        """Edit the current item."""
        self._require_facade().edit_current()

    def delete_current(self) -> None:
        """Delete the current item."""
        self._require_facade().delete_current()

    def show_section_dialog(self) -> None:
        """Open the dialog for creating a section."""
        self._require_facade().add_new_section()

    def update_statusbar(self) -> None:
        _update_status_bar(self)

    def share_section(self, section_id: int) -> None:
        """Export a section as a shareable archive."""
        self._export_structure_package("section", section_id)

    def share_sections(self, section_ids: list[int]) -> None:
        """Export multiple sections as shareable archives."""
        if not section_ids:
            return
        unique_ids = list(dict.fromkeys(int(sid) for sid in section_ids))
        if len(unique_ids) == 1:
            self.share_section(unique_ids[0])
            return

        from PyQt6.QtCore import QCoreApplication, QUrl
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtWidgets import QFileDialog

        from app.controllers.ui.dialogs import DialogManager
        from app.services.dialog_path_service import DialogPathService

        sb, service = self._get_structure_share_service(
            QCoreApplication.translate("StructureShare", "Export error")
        )
        if sb is None or service is None:
            return

        start_dir = DialogPathService.get_downloads_dir("Share")
        dialog_title = QCoreApplication.translate(
            "StructureShare", "Choose folder to export sections"
        )
        target_dir_str = QFileDialog.getExistingDirectory(
            self, dialog_title, str(start_dir)
        )
        if not target_dir_str:
            return

        DialogPathService.remember_dir("Share", target_dir_str)
        target_dir = Path(target_dir_str)

        exported_count = 0
        used_filenames: set[str] = {
            f.name.casefold() for f in target_dir.iterdir() if f.is_file()
        }

        for sid in unique_ids:
            try:
                name = self._require_facade().resolve_export_item_name(
                    sb, "section", int(sid)
                )
                base_filename = service.build_filename("section", str(name))
                dest_filename = base_filename
                stem = Path(base_filename).stem
                suffix = Path(base_filename).suffix
                counter = 1
                while dest_filename.casefold() in used_filenames:
                    dest_filename = f"{stem} ({counter}){suffix}"
                    counter += 1
                used_filenames.add(dest_filename.casefold())

                dest_path = target_dir / dest_filename
                service.export_section_archive(int(sid), dest_path)
                exported_count += 1
            except Exception as exc:
                logger.warning(
                    "Failed to export section %s: %s", sid, exc, exc_info=True
                )

        if exported_count > 0:
            msg = QCoreApplication.translate(
                "StructureShare", "Exported {count} section(s) to:\n{path}"
            ).format(count=exported_count, path=target_dir)
            set_status_message(self, msg)
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))
            except Exception:
                pass
        else:
            DialogManager.show_error(
                self,
                QCoreApplication.translate(
                    "StructureShare", "Failed to export selected sections."
                ),
                QCoreApplication.translate("StructureShare", "Export error"),
            )

    def share_category(self, category_id: int) -> None:
        """Export a category as a shareable archive."""
        self._export_structure_package("category", category_id)

    def import_category_to_section(self, section_id: int) -> None:
        """Import a category archive into a specific section."""
        self._import_structure_package("category", int(section_id))

    def import_category_to_current_section(self) -> None:
        """Import a category archive into the current section context."""
        section_id = None
        structure_ctrl = getattr(self, "structure", None)
        if structure_ctrl and hasattr(structure_ctrl, "item_ops"):
            try:
                section_id = structure_ctrl.item_ops.ensure_section_for_category()
            except Exception:
                section_id = None
        if not section_id:
            sb = getattr(self, "structure_business", None)
            if sb and hasattr(sb, "get_target_section_id"):
                try:
                    section_id = sb.get_target_section_id()
                except Exception:
                    section_id = None
        if not section_id:
            return

        self.import_category_to_section(int(section_id))

    def import_section_to_current_sphere(self) -> None:
        """Import a section archive into the current sphere context."""
        sphere_id = None
        sb = getattr(self, "structure_business", None)
        if sb and hasattr(sb, "get_current_sphere_id"):
            try:
                sphere_id = sb.get_current_sphere_id()
            except Exception:
                sphere_id = None
        if not sphere_id:
            from PyQt6.QtCore import QCoreApplication

            self._show_share_error(
                QCoreApplication.translate(
                    "StructureShare", "Sphere not selected."
                ),
                QCoreApplication.translate(
                    "StructureShare", "Select a sphere and try again."
                ),
            )
            return
        self._import_structure_package("section", int(sphere_id))

    def _export_structure_package(
        self, package_type: str, item_id: int
    ) -> None:

        from PyQt6.QtCore import QCoreApplication

        from app.controllers.ui.dialogs import DialogManager

        sb, service = self._get_structure_share_service(
            QCoreApplication.translate("StructureShare", "Export error")
        )
        if sb is None or service is None:
            return

        name = self._require_facade().resolve_export_item_name(
            sb, package_type, int(item_id)
        )

        filename = service.build_filename(package_type, str(name))

        dest_path = self._resolve_export_path(package_type, filename)
        if dest_path is None:
            return

        try:
            self._export_archive(
                service=service,
                package_type=package_type,
                item_id=int(item_id),
                destination_path=dest_path,
            )
        except Exception as exc:
            DialogManager.show_error(
                self,
                QCoreApplication.translate(
                    "StructureShare", "Failed to export archive: {error}"
                ).format(error=exc),
                QCoreApplication.translate("StructureShare", "Export error"),
            )
            return

        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest_path.parent)))
        except Exception:
            DialogManager.show_info(
                self,
                QCoreApplication.translate(
                    "StructureShare", "Archive saved to:\n{path}"
                ).format(path=dest_path),
                QCoreApplication.translate("StructureShare", "Export complete"),
            )

    def _resolve_export_path(self, package_type: str, filename: str) -> Path | None:
        from PyQt6.QtCore import QCoreApplication

        dialog_title = QCoreApplication.translate(
            "StructureShare", "Choose where to save the archive"
        )
        if package_type == "section":
            file_filter = QCoreApplication.translate(
                "StructureShare", "Section Archive (*.aitesec);;All files (*)"
            )
        else:
            file_filter = QCoreApplication.translate(
                "StructureShare", "Category Archive (*.aitecat);;All files (*)"
            )
        return self._choose_archive_save_path(
            dialog_title=dialog_title,
            default_name=filename,
            file_filter=file_filter,
        )

    def _import_structure_package(self, package_type: str, target_id: int) -> None:
        from PyQt6.QtCore import QCoreApplication

        from app.controllers.ui.dialogs import DialogManager
        from app.utils.ui.menu_builders.menu_actions import MenuTexts

        sb, service = self._get_structure_share_service(
            QCoreApplication.translate("StructureShare", "Import error")
        )
        if sb is None or service is None:
            return

        start_dir = ""

        dialog_title = QCoreApplication.translate(
            "StructureShare", "Select an archive to import"
        )
        if package_type == "section":
            file_filter = QCoreApplication.translate(
                "StructureShare", "Section Archive (*.aitesec);;All files (*)"
            )
        else:
            file_filter = QCoreApplication.translate(
                "StructureShare", "Category Archive (*.aitecat);;All files (*)"
            )

        choose_paths = getattr(self, "_choose_archive_open_paths", None)
        archive_paths = (
            choose_paths(
                dialog_title=dialog_title,
                start_dir=start_dir,
                file_filter=file_filter,
            )
            if callable(choose_paths)
            else []
        )
        if not archive_paths:
            choose_single = getattr(self, "_choose_archive_open_path", None)
            if callable(choose_single):
                single = choose_single(
                    dialog_title=dialog_title,
                    start_dir=start_dir,
                    file_filter=file_filter,
                )
                archive_paths = [single] if single else []

        if not archive_paths:
            return

        if len(archive_paths) == 1:
            try:
                imported = self._import_structure_archive_with_undo(
                    service=service,
                    package_type=package_type,
                    archive_path=archive_paths[0],
                    target_id=int(target_id),
                )
                if not imported:
                    return
            except Exception as exc:
                DialogManager.show_error(
                    self,
                    QCoreApplication.translate(
                        "StructureShare", "Failed to import archive: {error}"
                    ).format(error=exc),
                    QCoreApplication.translate("StructureShare", "Import error"),
                )
                return

            self._refresh_structure_after_import(
                section_id=int(target_id) if package_type == "category" else None
            )
            set_status_message(
                self,
                QCoreApplication.translate("StructureShare", "Import completed."),
            )
            return

        undo_stack = self.get_undo_stack()
        if undo_stack:
            undo_stack.beginMacro(
                QCoreApplication.translate(
                    "MenuActions",
                    MenuTexts.IMPORT_SECTIONS
                    if package_type == "section"
                    else "Import categories",
                )
            )

        batch_state: dict[str, Any] = {}
        imported_count = 0
        failed_count = 0

        try:
            for p in archive_paths:
                try:
                    imported = self._import_structure_archive_with_undo(
                        service=service,
                        package_type=package_type,
                        archive_path=p,
                        target_id=int(target_id),
                        batch_state=batch_state,
                        has_multiple=True,
                    )
                    if imported:
                        imported_count += 1
                    elif batch_state.get("action") == "cancel":
                        break
                except Exception as exc:
                    logger.warning(
                        "Failed to import archive %s: %s", p, exc, exc_info=True
                    )
                    failed_count += 1
        finally:
            if undo_stack:
                undo_stack.endMacro()

        if imported_count > 0:
            self._refresh_structure_after_import(
                section_id=int(target_id) if package_type == "category" else None
            )
            set_status_message(
                self,
                QCoreApplication.translate("StructureShare", "Import completed."),
            )
        elif failed_count > 0:
            DialogManager.show_error(
                self,
                QCoreApplication.translate(
                    "StructureShare", "Failed to import selected archives."
                ),
                QCoreApplication.translate("StructureShare", "Import error"),
            )

    def _import_structure_archive_with_undo(
        self,
        *,
        service: Any,
        package_type: str,
        archive_path: Path,
        target_id: int,
        batch_state: dict[str, Any] | None = None,
        has_multiple: bool = False,
    ) -> bool:
        from PyQt6.QtCore import QCoreApplication

        from app.controllers.ui.undo.commands_structure import (
            ImportStructurePackageCmd,
        )
        from app.utils.ui.menu_builders.menu_actions import MenuTexts

        undo_stack = self.get_undo_stack()
        if undo_stack is None:
            raise RuntimeError("Undo history is unavailable")

        structure_service = self.structure_business.structure_service
        manifest = service.inspect_package(archive_path)
        item_name = str(manifest.get("item_name") or "").strip().casefold()
        items = (
            structure_service.get_sections(target_id)
            if package_type == "section"
            else structure_service.get_categories(target_id)
        )
        before_ids = {
            int(item["id"])
            for item in items
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        existing_item = next(
            (
                item
                for item in items
                if str(item.get("name") or "").strip().casefold() == item_name
            ),
            None,
        )
        before_tree = None
        if existing_item is not None:
            item_id = int(existing_item["id"])
            before_tree = (
                structure_service.export_section_tree(item_id)
                if package_type == "section"
                else structure_service.export_category_tree(item_id)
            )

        conflict_choices: dict[str, str] = {}

        def resolve_conflict(entity_type: str, name: str, copy_name: str) -> str:
            action = self._resolve_import_conflict(
                entity_type,
                name,
                copy_name,
                has_multiple=has_multiple,
                batch_state=batch_state,
            )
            conflict_choices[entity_type] = action
            return action

        if not self._import_archive(
            service=service,
            package_type=package_type,
            archive_path=archive_path,
            target_id=target_id,
            conflict_resolver=resolve_conflict,
        ):
            return False

        if conflict_choices.get(package_type) == "merge" and existing_item:
            imported_item_id = int(existing_item["id"])
            undo_before_tree = before_tree
        else:
            items_after = (
                structure_service.get_sections(target_id)
                if package_type == "section"
                else structure_service.get_categories(target_id)
            )
            added_ids = {
                int(item["id"])
                for item in items_after
                if isinstance(item, dict)
                and isinstance(item.get("id"), int)
                and int(item["id"]) not in before_ids
            }
            if len(added_ids) != 1:
                raise RuntimeError(
                    "Could not identify the imported structure item for undo"
                )
            imported_item_id = added_ids.pop()
            undo_before_tree = None

        after_tree = (
            structure_service.export_section_tree(imported_item_id)
            if package_type == "section"
            else structure_service.export_category_tree(imported_item_id)
        )
        if undo_before_tree != after_tree:
            undo_text = QCoreApplication.translate(
                "MenuActions",
                MenuTexts.IMPORT_SECTION
                if package_type == "section"
                else MenuTexts.IMPORT_CATEGORY,
            )
            undo_stack.push(
                ImportStructurePackageCmd(
                    package_type=package_type,
                    item_id=imported_item_id,
                    target_id=target_id,
                    before_tree=undo_before_tree,
                    after_tree=after_tree,
                    structure_service=structure_service,
                    main_window=self,
                    text=undo_text,
                )
            )
        return True

    def _export_archive(
        self,
        *,
        service: Any,
        package_type: str,
        item_id: int,
        destination_path: Path,
    ) -> None:
        if package_type == "section":
            service.export_section_archive(item_id, destination_path)
            return
        service.export_category_archive(item_id, destination_path)

    def _import_archive(
        self,
        *,
        service: Any,
        package_type: str,
        archive_path: Path,
        target_id: int,
        conflict_resolver: Callable[[str, str, str], str] | None = None,
    ) -> bool:
        resolver = conflict_resolver or self._resolve_import_conflict
        if package_type == "section":
            return bool(
                service.import_section_archive(
                    archive_path, target_id, conflict_resolver=resolver
                )
            )
        return bool(
            service.import_category_archive(
                archive_path, target_id, conflict_resolver=resolver
            )
        )

    def _resolve_import_conflict(
        self,
        entity_type: str,
        name: str,
        copy_name: str,
        *,
        has_multiple: bool = False,
        batch_state: dict[str, Any] | None = None,
    ) -> str:
        if batch_state and batch_state.get("apply_to_all"):
            return str(batch_state.get("action", "copy"))

        from PyQt6.QtWidgets import QDialog

        from app.views.windows.dialogs.entity_dialogs import ImportConflictDialog

        dlg = ImportConflictDialog(
            entity_type, name, copy_name, parent=self, has_multiple=has_multiple
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            action = dlg.get_action()
            if batch_state is not None and dlg.apply_to_all():
                batch_state["action"] = action
                batch_state["apply_to_all"] = True
            return action
        if batch_state is not None:
            batch_state["action"] = "cancel"
        return "cancel"

    def import_archive_file(
        self,
        archive_path: Path,
        target_type: str | None = None,
        target_id: int | None = None,
        batch_state: dict[str, Any] | None = None,
        skip_refresh: bool = False,
    ) -> bool:
        """Auto-import an archive package (.zip, .aitepack) dropped onto tree or opened."""
        from PyQt6.QtCore import QCoreApplication

        from app.controllers.ui.dialogs import DialogManager
        from app.services.structure_share_service import StructureShareService

        sb = getattr(self, "structure_business", None)
        if not sb or not hasattr(sb, "structure_service"):
            return False

        service = StructureShareService(sb.structure_service)

        try:
            manifest = service.inspect_package(archive_path)
            package_type = manifest.get("package_type")
        except Exception:
            return False

        if package_type not in ("section", "category"):
            return False

        resolved_target_id = None
        refresh_section_id = None
        target_sphere_for_switch: int | None = None

        if package_type == "section":
            if target_type == "sphere" and isinstance(target_id, int):
                resolved_target_id = target_id
            elif target_type == "section" and isinstance(target_id, int):
                sec_row = sb.structure_service.get_section_by_id(target_id) if hasattr(sb, "structure_service") else None
                resolved_target_id = sec_row.get("sphere_id") if sec_row else None
            elif target_type == "category" and isinstance(target_id, int):
                hier = sb.get_category_hierarchy(target_id) if hasattr(sb, "get_category_hierarchy") else None
                resolved_target_id = hier.get("sphere_id") if hier else None
            elif isinstance(target_id, int):
                resolved_target_id = target_id
            if resolved_target_id is None:
                if batch_state and "resolved_sphere_id" in batch_state:
                    resolved_target_id = batch_state["resolved_sphere_id"]
                else:
                    resolved_target_id = self._prompt_import_target_sphere(manifest, sb)
                    if batch_state is not None and resolved_target_id is not None:
                        batch_state["resolved_sphere_id"] = resolved_target_id
            if isinstance(resolved_target_id, int):
                target_sphere_for_switch = resolved_target_id
        elif package_type == "category":
            if target_type == "section" and isinstance(target_id, int):
                resolved_target_id = target_id
            elif target_type == "category" and isinstance(target_id, int):
                hier = sb.get_category_hierarchy(target_id)
                if hier and isinstance(hier.get("section_id"), int):
                    resolved_target_id = hier["section_id"]
            if resolved_target_id is None:
                if batch_state and "resolved_category_section_id" in batch_state:
                    resolved_target_id = batch_state["resolved_category_section_id"]
                else:
                    resolved_target_id = self._prompt_import_target_category(manifest, sb)
                    if batch_state is not None and resolved_target_id is not None:
                        batch_state["resolved_category_section_id"] = resolved_target_id
            refresh_section_id = resolved_target_id
            if isinstance(resolved_target_id, int) and hasattr(sb, "structure_service"):
                try:
                    sec_row = sb.structure_service.get_section_by_id(resolved_target_id)
                    if sec_row and isinstance(sec_row.get("sphere_id"), int):
                        target_sphere_for_switch = sec_row["sphere_id"]
                except Exception:
                    pass

        if resolved_target_id is None:
            return False

        try:
            imported = self._import_structure_archive_with_undo(
                service=service,
                package_type=package_type,
                archive_path=archive_path,
                target_id=int(resolved_target_id),
                batch_state=batch_state,
                has_multiple=bool(batch_state is not None),
            )
            if not imported:
                return True
        except Exception as exc:
            DialogManager.show_error(
                self,
                QCoreApplication.translate(
                    "StructureShare", "Failed to import archive: {error}"
                ).format(error=exc),
                QCoreApplication.translate("StructureShare", "Import error"),
            )
            return True

        if not skip_refresh:
            # Switch active sphere if target sphere differs from current
            if target_sphere_for_switch is not None:
                s_ctrl = getattr(self, "spheres_bar_controller", None)
                if s_ctrl and hasattr(s_ctrl, "switch_sphere"):
                    try:
                        s_ctrl.switch_sphere(int(target_sphere_for_switch))
                    except Exception:
                        pass

            self._refresh_structure_after_import(section_id=refresh_section_id)
            set_status_message(
                self,
                QCoreApplication.translate("StructureShare", "Import completed."),
            )
        return True

    def import_archive_files(
        self,
        archive_paths: list[Path],
        target_type: str | None = None,
        target_id: int | None = None,
    ) -> bool:
        """Auto-import multiple archive packages (.zip, .aitepack, .aitesec, .aitecat) dropped or opened."""
        if not archive_paths:
            return False
        if len(archive_paths) == 1:
            return self.import_archive_file(
                archive_paths[0], target_type=target_type, target_id=target_id
            )

        from PyQt6.QtCore import QCoreApplication

        undo_stack = self.get_undo_stack()
        if undo_stack:
            undo_stack.beginMacro(
                QCoreApplication.translate("MenuActions", "Import sections")
            )

        imported_any = False
        batch_state: dict[str, Any] = {}

        try:
            for p in archive_paths:
                try:
                    if self.import_archive_file(
                        p,
                        target_type=target_type,
                        target_id=target_id,
                        batch_state=batch_state,
                        skip_refresh=True,
                    ):
                        imported_any = True
                    if batch_state.get("action") == "cancel":
                        break
                except Exception as exc:
                    logger.warning(
                        "Failed to import archive %s: %s", p, exc, exc_info=True
                    )
        finally:
            if undo_stack:
                undo_stack.endMacro()

        if imported_any:
            target_sphere = batch_state.get("resolved_sphere_id")
            if target_sphere is not None:
                s_ctrl = getattr(self, "spheres_bar_controller", None)
                if s_ctrl and hasattr(s_ctrl, "switch_sphere"):
                    try:
                        s_ctrl.switch_sphere(int(target_sphere))
                    except Exception:
                        pass
            self._refresh_structure_after_import()
            set_status_message(
                self,
                QCoreApplication.translate("StructureShare", "Import completed."),
            )
        return imported_any

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        from app.utils.ui.dnd.mime import MimeDataParser

        targets = MimeDataParser.extract_external_link_targets(event.mimeData())
        if targets and all(
            t.lower().endswith((".aitesec", ".aitecat", ".aitepack", ".zip"))
            for t in targets
        ):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        from app.utils.ui.dnd.mime import MimeDataParser

        targets = MimeDataParser.extract_external_link_targets(event.mimeData())
        if targets and all(
            t.lower().endswith((".aitesec", ".aitecat", ".aitepack", ".zip"))
            for t in targets
        ):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        from app.utils.ui.dnd.mime import MimeDataParser

        targets = MimeDataParser.extract_external_link_targets(event.mimeData())
        if targets and all(
            t.lower().endswith((".aitesec", ".aitecat", ".aitepack", ".zip"))
            for t in targets
        ):
            from pathlib import Path

            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            paths = [Path(t) for t in targets]
            if len(paths) == 1:
                self.import_archive_file(paths[0])
            else:
                self.import_archive_files(paths)
            return
        super().dropEvent(event)

    def _refresh_structure_after_import(self, section_id: int | None = None) -> None:
        business = getattr(self, "structure_business", None)
        self._require_facade().refresh_structure_after_import(
            business, section_id=section_id
        )

    def _show_share_error(self, title: str, message: str) -> None:
        from app.controllers.ui.dialogs import DialogManager

        DialogManager.show_error(self, message, title)

    def _choose_archive_save_path(
        self,
        *,
        dialog_title: str,
        default_name: str,
        file_filter: str,
    ) -> Path | None:
        from PyQt6.QtWidgets import QFileDialog

        from app.services.dialog_path_service import DialogPathService

        start_dir = DialogPathService.get_downloads_dir("Share")
        start_path = str(Path(start_dir) / default_name)
        path_str, selected_filter = QFileDialog.getSaveFileName(
            self, dialog_title, start_path, file_filter
        )
        if not path_str:
            return None
        DialogPathService.remember_dir("Share", path_str)
        dest = Path(path_str)
        if not dest.suffix:
            ext = ".zip" if "ZIP" in selected_filter else ".aitepack"
            dest = dest.with_suffix(ext)
        return dest

    def _choose_archive_open_path(
        self,
        *,
        dialog_title: str,
        start_dir: str,
        file_filter: str,
    ) -> Path | None:
        from PyQt6.QtWidgets import QFileDialog

        from app.services.dialog_path_service import DialogPathService

        resolved_start = start_dir or DialogPathService.get_downloads_dir("Share")
        path_str, _ = QFileDialog.getOpenFileName(
            self, dialog_title, resolved_start, file_filter
        )
        if not path_str:
            return None
        DialogPathService.remember_dir("Share", path_str)
        return Path(path_str)

    def _choose_archive_open_paths(
        self,
        *,
        dialog_title: str,
        start_dir: str,
        file_filter: str,
    ) -> list[Path]:
        from PyQt6.QtWidgets import QFileDialog

        from app.services.dialog_path_service import DialogPathService

        resolved_start = start_dir or DialogPathService.get_downloads_dir("Share")
        paths_str, _ = QFileDialog.getOpenFileNames(
            self, dialog_title, resolved_start, file_filter
        )
        if not paths_str:
            return []
        DialogPathService.remember_dir("Share", paths_str[0])
        return [Path(p) for p in paths_str]

    def _get_structure_share_service(
        self, error_title: str
    ) -> tuple[Any, Any] | tuple[None, None]:
        from PyQt6.QtCore import QCoreApplication

        from app.services.structure_share_service import StructureShareService

        sb = getattr(self, "structure_business", None)
        if not sb or not hasattr(sb, "structure_service"):
            self._show_share_error(
                error_title,
                QCoreApplication.translate(
                    "StructureShare", "Structure service unavailable."
                ),
            )
            return None, None
        return sb, StructureShareService(sb.structure_service)

    def _prompt_import_target_sphere(self, manifest: dict[str, Any], sb: Any) -> int | None:
        from PyQt6.QtWidgets import QDialog

        from app.views.dialogs.import_destination_dialog import ImportDestinationDialog

        spheres = sb.get_spheres() if hasattr(sb, "get_spheres") else []
        if not spheres:
            return None
        cur_sphere_id = sb.get_current_sphere_id() if hasattr(sb, "get_current_sphere_id") else None
        item_name = (
            manifest.get("item_name")
            or manifest.get("name")
            or manifest.get("title")
            or self.tr("Section")
        )
        dlg = ImportDestinationDialog(
            self,
            package_type="section",
            item_name=str(item_name),
            spheres=spheres,
            sections_by_sphere={},
            default_sphere_id=cur_sphere_id,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.get_selected_sphere_id()
        return None

    def _prompt_import_target_category(self, manifest: dict[str, Any], sb: Any) -> int | None:
        from PyQt6.QtWidgets import QDialog

        from app.views.dialogs.import_destination_dialog import ImportDestinationDialog

        spheres = sb.get_spheres() if hasattr(sb, "get_spheres") else []
        if not spheres:
            return None
        sections_by_sphere = {}
        for sp in spheres:
            sp_id = sp.get("id")
            if sp_id is not None:
                sections_by_sphere[int(sp_id)] = (
                    sb.get_sections(int(sp_id)) if hasattr(sb, "get_sections") else []
                )
        cur_sphere_id = sb.get_current_sphere_id() if hasattr(sb, "get_current_sphere_id") else None
        item_name = (
            manifest.get("item_name")
            or manifest.get("name")
            or manifest.get("title")
            or self.tr("Category")
        )
        dlg = ImportDestinationDialog(
            self,
            package_type="category",
            item_name=str(item_name),
            spheres=spheres,
            sections_by_sphere=sections_by_sphere,
            default_sphere_id=cur_sphere_id,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.get_selected_section_id()
        return None

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

    def show_health_radar_dialog(self) -> None:
        if self.system_dialogs is not None:
            self.system_dialogs.handle_check_local_paths()

    def update_theme(self) -> None:
        """Apply the current theme and refresh the UI."""
        if self.facade:
            self.facade.update_theme()
        elif self.theme_ctrl and hasattr(self.theme_ctrl, "apply_and_refresh_ui"):
            self.theme_ctrl.apply_and_refresh_ui()

        theme_selector = getattr(self, "theme_selector", None)
        if theme_selector is not None:
            try:
                if hasattr(theme_selector, "update_theme_selection"):
                    theme_selector.update_theme_selection()
                elif hasattr(theme_selector, "retranslateUi"):
                    theme_selector.retranslateUi()
            except Exception as e:
                logger.debug("MainWindow.update_theme: failed to update theme selector: %s", e)

        if self.system_dialogs and getattr(self.system_dialogs, "_settings_dialog", None):
            try:
                self.system_dialogs._settings_dialog.update_theme_selection()
            except Exception as e:
                logger.debug("MainWindow.update_theme: failed to update settings dialog theme: %s", e)

        cp_ctrl = getattr(self, "command_palette_controller", None)
        if cp_ctrl is not None and hasattr(cp_ctrl, "refresh_theme"):
            try:
                cp_ctrl.refresh_theme()
            except Exception as e:
                logger.debug("MainWindow.update_theme: failed to update command palette theme: %s", e)

    def apply_font_size_to_content(self, fs: int) -> None:
        """Apply font size to tree and table widgets."""
        size = fs

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
        self.hide()
        
        # Принудительно заставляем Qt отрисовать сокрытие окна до блокировки главного потока
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        logger.info("MainWindow.closeEvent: initiating shutdown")

        try:
            self._cleanup_resources()
        except Exception:
            logger.exception("MainWindow.closeEvent: _cleanup_resources failed")

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
            ("command_palette_controller", lambda: self._cleanup_command_palette()),
            ("top_panels_controller", lambda: self._cleanup_top_panels_controller()),
            ("facade", lambda: self._cleanup_facade()),
            ("table", lambda: self._cleanup_table()),
        ]

        for task_name, cleanup_func in cleanup_tasks:
            try:
                cleanup_func()
            except Exception as e:
                logger.debug("MainWindow: cleanup %s failed: %s", task_name, e)

        if hasattr(self, "widgets") and hasattr(self.widgets, "clear"):
            try:
                self.widgets.clear()
            except Exception:
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
        self._discard_undo_redo_actions()

    def _cleanup_facade(self) -> None:
        """Cleanup facade if cleanup method exists."""
        if self.facade and hasattr(self.facade, "cleanup"):
            self.facade.cleanup()

    def _cleanup_top_panels_controller(self) -> None:
        """Cleanup top panels controller timers/signals if present."""
        controller = getattr(self, "top_panels_controller", None)
        if controller and hasattr(controller, "cleanup"):
            controller.cleanup()

    def _cleanup_command_palette(self) -> None:
        """Cleanup global command palette controller and OS hotkeys if present."""
        controller = getattr(self, "command_palette_controller", None)
        if controller and hasattr(controller, "cleanup"):
            controller.cleanup()

    def _cleanup_table(self) -> None:
        """Clear table model to prevent access to deleted data."""
        table = getattr(self, "table", None)
        if table:
            table.setModel(None)


def _unique_path(path: str | Path) -> Path:
    from pathlib import Path
    from uuid import uuid4

    target = Path(path)
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix or ""
    parent = target.parent
    for idx in range(1, 1000):
        candidate = parent / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
    return parent / f"{stem}_{uuid4().hex[:6]}{suffix}"
