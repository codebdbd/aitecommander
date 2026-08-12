import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from PyQt6.QtCore import QItemSelection, QItemSelectionModel, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QShowEvent, QUndoStack
from PyQt6.QtWidgets import (
    QMainWindow,
    QMenuBar,
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

    def get_current_category_id(self) -> Optional[int]:
        """Return the ID of the currently selected category."""
        if self.facade is None:
            logger.debug("MainWindow: get_current_category_id requested before facade is initialized")
            return None
        return self.facade.get_current_category_id()

    def edit_structure_item(self, item: "StructureItem") -> None:
        """Edit a structure item."""
        if self.structure:
            self.structure.edit_item(item)

    def add_new_category(self) -> None:
        """Create a new category."""
        self._require_facade().add_new_category()

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

        from app.utils.ui.menu_builders.menu_actions import MenuTexts

        from PyQt6.QtCore import QCoreApplication

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
            from app.utils.ui.menu_builders.menu_actions import MenuTexts
            from PyQt6.QtCore import QCoreApplication

            self.undo_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.UNDO))

    def _refresh_redo_text(self) -> None:
        """Update redo action text from translations."""
        if self.redo_action:
            from app.utils.ui.menu_builders.menu_actions import MenuTexts
            from PyQt6.QtCore import QCoreApplication

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
        undo_action = getattr(self, "undo_action", None)
        if undo_action is not None:
            from app.utils.ui.menu_builders.menu_actions import MenuTexts
            from PyQt6.QtCore import QCoreApplication

            undo_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.UNDO))
        redo_action = getattr(self, "redo_action", None)
        if redo_action is not None:
            from app.utils.ui.menu_builders.menu_actions import MenuTexts
            from PyQt6.QtCore import QCoreApplication

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
        # switch_sphere_button now handled by retranslate_bottom_panel (unified)
        retranslate_bottom_panel(self)

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

    def share_category(self, category_id: int) -> None:
        """Export a category as a shareable archive."""
        self._export_structure_package("category", category_id)

    def import_category_to_section(self, section_id: int) -> None:
        """Import a category archive into a specific section."""
        self._import_structure_package("category", int(section_id))

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

    def _export_structure_package(self, package_type: str, item_id: int) -> None:

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

        from app.utils.share_paths import (
            ensure_service_root,
            get_desktop_dir,
            get_export_dir,
        )

        desktop = get_desktop_dir()
        if desktop:
            root = ensure_service_root(desktop)
            if root:
                export_dir = get_export_dir(root, package_type)
                export_dir.mkdir(parents=True, exist_ok=True)
                return _unique_path(export_dir / filename)

        dialog_title = QCoreApplication.translate(
            "StructureShare", "Choose where to save the archive"
        )
        file_filter = QCoreApplication.translate(
            "StructureShare", "ZIP archive (*.zip);;All files (*)"
        )
        return self._choose_archive_save_path(
            dialog_title=dialog_title,
            default_name=filename,
            file_filter=file_filter,
        )

    def _import_structure_package(self, package_type: str, target_id: int) -> None:
        from PyQt6.QtCore import QCoreApplication

        from app.controllers.ui.dialogs import DialogManager
        from app.utils.share_paths import (
            ensure_service_root,
            get_desktop_dir,
            get_import_dir,
        )

        sb, service = self._get_structure_share_service(
            QCoreApplication.translate("StructureShare", "Import error")
        )
        if sb is None or service is None:
            return

        start_dir = ""
        desktop = get_desktop_dir()
        if desktop:
            root = ensure_service_root(desktop)
            if root:
                start_dir = str(get_import_dir(root, package_type))

        dialog_title = QCoreApplication.translate(
            "StructureShare", "Select an archive to import"
        )
        file_filter = QCoreApplication.translate(
            "StructureShare", "ZIP archive (*.zip);;All files (*)"
        )
        archive_path = self._choose_archive_open_path(
            dialog_title=dialog_title,
            start_dir=start_dir,
            file_filter=file_filter,
        )
        if archive_path is None:
            return

        try:
            self._import_archive(
                service=service,
                package_type=package_type,
                archive_path=archive_path,
                target_id=int(target_id),
            )
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
        DialogManager.show_info(
            self,
            QCoreApplication.translate("StructureShare", "Import completed."),
            QCoreApplication.translate("StructureShare", "Import complete"),
        )

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
    ) -> None:
        if package_type == "section":
            service.import_section_archive(archive_path, target_id)
            return
        service.import_category_archive(archive_path, target_id)

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

        path_str, _ = QFileDialog.getSaveFileName(
            self, dialog_title, default_name, file_filter
        )
        if not path_str:
            return None
        return Path(path_str)

    def _choose_archive_open_path(
        self,
        *,
        dialog_title: str,
        start_dir: str,
        file_filter: str,
    ) -> Path | None:
        from PyQt6.QtWidgets import QFileDialog

        path_str, _ = QFileDialog.getOpenFileName(
            self, dialog_title, start_dir, file_filter
        )
        if not path_str:
            return None
        return Path(path_str)

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
            ("top_panels_controller", lambda: self._cleanup_top_panels_controller()),
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
