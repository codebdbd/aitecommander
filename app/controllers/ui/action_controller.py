"""Controller for handling user actions (edit, delete, clipboard, etc.)."""

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from app.config_data.runtime_config import get_table_stack_index, get_tiles_stack_index
from app.controllers.ui.undo.commands_structure import (
    BatchDeleteCategoriesCmd,
    DeleteCategoryCmd,
    DeleteSectionCmd,
    DeleteSectionsCmd,
    PasteCategoriesCmd,
    PasteSectionsCmd,
)
from app.core.hotkey_manager import HotkeyManager
from app.services.structure_context_service import StructureContextService
from app.utils.ui.clipboard import get_link_from_clipboard
from app.utils.ui.focus import WidgetType, get_focus_manager
from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
from app.utils.ui.menu_builders.menu_actions import MenuTexts
from app.utils.ui.qt.roles import get_tree_tuple

if TYPE_CHECKING:
    from app.views.windows.main_window_protocol import MainWindowProtocol

logger = logging.getLogger(__name__)


class ActionController(QObject):
    """Controller for handling user actions."""

    def __init__(self, main_window: "MainWindowProtocol"):
        parent = main_window if isinstance(main_window, QObject) else None
        super().__init__(parent=parent)
        self.main_window = main_window
        self._focus_manager = get_focus_manager()
        self._global_actions_ready = False
        self.cut_action: QAction | None = None
        self.copy_action: QAction | None = None
        self.paste_action: QAction | None = None
        self.delete_action: QAction | None = None
        self.select_all_action: QAction | None = None
        self._bound_selection_models: set[int] = set()
        self._structure_ctx: StructureContextService | None = None
        self._deferred_action_icons: list[tuple[QAction, str]] = []
        self._global_action_icons_applied = False
        self._clipboard_is_cut: bool = False
        self._cut_item_type: str | None = None
        self._cut_item_ids: set[int] = set()
        self._setup_state_hooks()

    def _setup_state_hooks(self) -> None:
        app = QApplication.instance()
        if not app:
            return
        try:
            app.focusChanged.connect(
                lambda _old, _new: self.update_action_states()
            )
        except Exception:
            logger.debug("ActionController: focusChanged hook failed", exc_info=True)
        try:
            clipboard = app.clipboard()
            if clipboard:
                clipboard.dataChanged.connect(self.update_action_states)
        except Exception:
            logger.debug("ActionController: clipboard hook failed", exc_info=True)

    def setup_global_actions(self) -> None:
        if self._global_actions_ready:
            return
        parent = self.main_window
        self.cut_action = QAction(parent)
        self.copy_action = QAction(parent)
        self.paste_action = QAction(parent)
        self.delete_action = QAction(parent)
        self.select_all_action = QAction(parent)

        self._configure_action(
            self.cut_action, MenuTexts.CUT, "edit.cut", "cut", self.cut_current
        )
        self._configure_action(
            self.copy_action, MenuTexts.COPY, "edit.copy", "copy", self.copy_current
        )
        self._configure_action(
            self.paste_action, MenuTexts.PASTE, "edit.paste", "paste", self.paste_current
        )
        self._configure_action(
            self.delete_action, MenuTexts.DELETE, "global.delete", "delete", self.delete_current
        )
        self._configure_action(
            self.select_all_action,
            MenuTexts.SELECT_ALL,
            "edit.select_all",
            "select_all",
            self.select_all_current,
        )

        for action in (
            self.cut_action,
            self.copy_action,
            self.paste_action,
            self.delete_action,
            self.select_all_action,
        ):
            if action and action not in self.main_window.actions():
                self.main_window.addAction(action)

        self.main_window.cut_action = self.cut_action
        self.main_window.copy_action = self.copy_action
        self.main_window.paste_action = self.paste_action
        self.main_window.delete_action = self.delete_action
        self.main_window.select_all_action = self.select_all_action
        self._wire_undo_redo_actions()

        self._global_actions_ready = True
        self._schedule_global_action_icons()
        self.update_action_states()

    def retranslate_actions(self) -> None:
        if not self._global_actions_ready:
            return
        from PyQt6.QtCore import QCoreApplication

        if self.cut_action:
            self.cut_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.CUT))
        if self.copy_action:
            self.copy_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.COPY))
        if self.paste_action:
            self.paste_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.PASTE))
        if self.delete_action:
            self.delete_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.DELETE))
        if self.select_all_action:
            self.select_all_action.setText(QCoreApplication.translate("MenuActions", MenuTexts.SELECT_ALL))

    def _configure_action(
        self,
        action: QAction,
        text: str,
        shortcut_id: str,
        icon_name: str,
        handler,
    ) -> None:
        from PyQt6.QtCore import QCoreApplication

        action.setText(QCoreApplication.translate("MenuActions", text))
        try:
            self._deferred_action_icons.append((action, icon_name))
        except Exception:
            pass
        try:
            seq = HotkeyManager.get_sequence(shortcut_id)
            if not seq.isEmpty():
                action.setShortcut(seq)
                action.setShortcutVisibleInContextMenu(True)
                if shortcut_id == "global.delete":
                    action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
                else:
                    action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        except Exception:
            logger.debug("ActionController: shortcut setup failed", exc_info=True)
        if shortcut_id == "global.delete":
            action.triggered.connect(lambda _checked=False: handler())
        else:
            action.triggered.connect(lambda _checked=False: handler())

    def _apply_global_action_icons(self) -> None:
        self.refresh_action_icons()

    def _iter_icon_actions(self) -> list[tuple[QAction, str]]:
        actions: list[tuple[QAction, str]] = []
        actions.extend(self._deferred_action_icons)
        undo_action = getattr(self.main_window, "undo_action", None)
        redo_action = getattr(self.main_window, "redo_action", None)
        if undo_action is not None:
            actions.append((undo_action, "undo"))
        if redo_action is not None:
            actions.append((redo_action, "redo"))
        return actions

    def refresh_action_icons(self) -> None:
        """Re-apply action icons for the current theme."""
        if not self._global_actions_ready:
            return
        self._global_action_icons_applied = True
        actions = self._iter_icon_actions()
        try:
            theme = self.main_window.settings.get_theme()
        except Exception:
            theme = "light"
        for action, icon_name in actions:
            try:
                action.setIcon(
                    icon_cache.get_icon(icon_name, theme, source="global_actions")
                )
            except Exception:
                logger.debug(
                    "ActionController: failed to apply deferred icon %s",
                    icon_name,
                    exc_info=True,
                )

    def _schedule_global_action_icons(self) -> None:
        if self._global_action_icons_applied:
            return
        try:
            if hasattr(self.main_window, "shown"):
                self.main_window.shown.connect(
                    self._apply_global_action_icons,
                    Qt.ConnectionType.SingleShotConnection,
                )
                return
        except Exception:
            logger.debug(
                "ActionController: failed to connect deferred icon apply",
                exc_info=True,
            )
        QTimer.singleShot(0, self._apply_global_action_icons)

    def _wire_undo_redo_actions(self) -> None:
        undo_action = getattr(self.main_window, "undo_action", None)
        if undo_action is not None:
            try:
                undo_action.triggered.disconnect()
            except Exception:
                pass
            undo_action.triggered.connect(
                lambda _checked=False: self.undo_current()
            )
        redo_action = getattr(self.main_window, "redo_action", None)
        if redo_action is not None:
            try:
                redo_action.triggered.disconnect()
            except Exception:
                pass
            redo_action.triggered.connect(
                lambda _checked=False: self.redo_current()
            )

    # --- Helpers: focus/selection/context ---
    def _get_text_widget(self):
        widget = QApplication.focusWidget()
        if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return widget
        return None

    def _text_has_selection(self, widget) -> bool:
        if isinstance(widget, QLineEdit):
            return bool(widget.hasSelectedText())
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            try:
                return widget.textCursor().hasSelection()
            except Exception:
                return False
        return False

    def _has_tree_selection(self) -> bool:
        try:
            tree = self.main_window.tree
            return bool(hasattr(tree, "currentIndex") and tree.currentIndex().isValid())
        except Exception:
            return False

    def _is_tree_focused(self) -> bool:
        """Check if structure tree has focus.
        
        Uses centralized FocusManager for consistent behavior.
        """
        return self._focus_manager.is_type_focused(WidgetType.STRUCTURE_TREE)

    def _table_has_selection(self) -> bool:
        try:
            return bool(self.main_window.links_actions.get_selected_rows())
        except Exception:
            return False

    def _is_table_focused(self) -> bool:
        """Check if links table has focus.
        
        Uses centralized FocusManager for consistent behavior.
        """
        return self._focus_manager.is_type_focused(WidgetType.LINKS_TABLE)

    def _is_tiles_focused(self) -> bool:
        """Check if category tiles have focus."""
        return self._focus_manager.is_type_focused(WidgetType.CATEGORY_TILES)

    def _is_table_stack_active(self) -> bool:
        table_stack_index = get_table_stack_index()
        try:
            stack = getattr(self.main_window, "stack", None)
            return bool(stack is not None and stack.currentIndex() == table_stack_index)
        except Exception:
            return False

    def _selected_links(self):
        try:
            return self.main_window.links_actions.get_selected_links()
        except Exception:
            return []

    def _get_structure_context_service(self) -> StructureContextService | None:
        if self._structure_ctx is not None:
            return self._structure_ctx
        dc = getattr(self.main_window, "database_controller", None)
        db = getattr(dc, "db", None)
        if db is None:
            return None
        try:
            self._structure_ctx = StructureContextService(db)
        except Exception:
            logger.debug("ActionController: failed to init StructureContextService")
            return None
        return self._structure_ctx

    def _get_tree_selected_rows(self) -> list[Any]:
        try:
            tree = self.main_window.tree
        except Exception:
            return []
        if not tree:
            return []
        sel_model = tree.selectionModel() if hasattr(tree, "selectionModel") else None
        if not sel_model:
            return []
        return sel_model.selectedRows(0) or []

    def _get_tree_selection_type(self) -> str | None:
        types: set[str] = set()
        for idx in self._get_tree_selected_rows():
            t = get_tree_tuple(idx, 0)
            if t and t[0]:
                types.add(t[0])
        if len(types) == 1:
            return next(iter(types))
        return None

    def _get_selected_tree_ids(self, item_type: str) -> list[int]:
        ids: list[int] = []
        for idx in self._get_tree_selected_rows():
            t = get_tree_tuple(idx, 0)
            if not t:
                continue
            typ, item_id = t
            if typ != item_type:
                continue
            try:
                ids.append(int(item_id))
            except Exception:
                continue
        return ids

    def _get_tiles_view(self):
        tiles = getattr(self.main_window, "tiles", None)
        view = getattr(tiles, "view", None) if tiles else None
        return view

    def _get_tiles_selected_ids(self) -> list[int]:
        view = self._get_tiles_view()
        if view is None:
            return []
        sel_model = view.selectionModel() if hasattr(view, "selectionModel") else None
        if not sel_model:
            return []
        ids: list[int] = []
        for idx in sel_model.selectedIndexes() or []:
            try:
                raw_id = idx.data(Qt.ItemDataRole.UserRole)
                if raw_id is None:
                    continue
                ids.append(int(raw_id))
            except Exception:
                continue
        return ids

    def _get_tiles_target_section_id(self) -> int | None:
        sb = getattr(self.main_window, "structure_business", None)
        if not sb:
            return None
        selected = self._get_tiles_selected_ids()
        if selected:
            try:
                hier = sb.get_category_hierarchy(int(selected[0]))
            except Exception:
                hier = None
            section_id = hier.get("section_id") if isinstance(hier, dict) else None
            if isinstance(section_id, int):
                return section_id
        try:
            return sb.get_target_section_id()
        except Exception:
            return None

    def _get_tree_target_section_id(self) -> int | None:
        try:
            tree = self.main_window.tree
        except Exception:
            return None
        if not tree or not hasattr(tree, "currentIndex"):
            return None
        idx = tree.currentIndex()
        if not (idx and idx.isValid()):
            return None
        t = get_tree_tuple(idx, 0)
        if not t:
            return None
        typ, item_id = t
        if typ == "section":
            try:
                return int(item_id)
            except Exception:
                return None
        if typ == "category":
            parent = idx.parent()
            if parent and parent.isValid():
                tparent = get_tree_tuple(parent, 0)
                if tparent and tparent[0] == "section":
                    try:
                        return int(tparent[1])
                    except Exception:
                        return None
        return None

    def _get_tree_target_category_id(self) -> int | None:
        try:
            tree = self.main_window.tree
        except Exception:
            return None
        if not tree or not hasattr(tree, "currentIndex"):
            return None
        idx = tree.currentIndex()
        if not (idx and idx.isValid()):
            return None
        t = get_tree_tuple(idx, 0)
        if not t or t[0] != "category":
            return None
        try:
            return int(t[1])
        except Exception:
            return None

    def _get_tiles_target_category_id(self) -> int | None:
        selected = self._get_tiles_selected_ids()
        return int(selected[0]) if len(selected) == 1 else None

    def _bind_selection_signals(self) -> None:
        tree = getattr(self.main_window, "tree", None)
        if tree and hasattr(tree, "selectionModel"):
            sel = tree.selectionModel()
            if sel and id(sel) not in self._bound_selection_models:
                try:
                    sel.selectionChanged.connect(self.update_action_states)
                except Exception:
                    logger.debug(
                        "ActionController: tree selection hook failed", exc_info=True
                    )
                self._bound_selection_models.add(id(sel))
        table = getattr(self.main_window, "table", None)
        if table and hasattr(table, "selectionModel"):
            sel = table.selectionModel()
            if sel and id(sel) not in self._bound_selection_models:
                try:
                    sel.selectionChanged.connect(self.update_action_states)
                except Exception:
                    logger.debug(
                        "ActionController: table selection hook failed", exc_info=True
                    )
                self._bound_selection_models.add(id(sel))

    @pyqtSlot()
    def edit_current(self) -> None:
        """Detect context and perform edit of current item."""
        # Check category tiles
        tiles_stack_index = get_tiles_stack_index()
        stack = getattr(self.main_window, "stack", None)
        tiles = getattr(self.main_window, "tiles", None)
        if (
            stack is not None
            and tiles is not None
            and stack.currentIndex() == tiles_stack_index
        ):
            current_category_id = None
            try:
                structure_ctrl = getattr(self.main_window, "structure", None)
                if structure_ctrl is not None and hasattr(structure_ctrl, "get_current_category_id"):
                    current_category_id = structure_ctrl.get_current_category_id()
            except Exception:
                logger.debug("ActionController.edit_current: get_current_category_id failed", exc_info=True)
            if isinstance(current_category_id, int):
                self.main_window.structure.handle_edit_category(current_category_id)
                return

        # 1. Direct focus: structure tree
        if self._is_tree_focused() and self._has_tree_selection():
            self.main_window.structure.edit_selected_item()
            return

        # 2. Check links table (active)
        if self._is_table_stack_active() and self._table_has_selection():
            self._edit_selected_link()
            return

        # 3. Check focus on links table
        if self._is_table_focused() and self._table_has_selection():
            self._edit_selected_link()

    @pyqtSlot()
    def delete_current(self) -> None:
        """Detect context and perform deletion of current item."""
        widget = self._get_text_widget()
        if widget is not None:
            self._delete_text_selection(widget)
            return

        # 1. Direct focus: structure tree
        if self._is_tree_focused() and self._has_tree_selection():
            self.main_window.structure.delete_selected_item()
            self.main_window.update_statusbar()
            return

        # 2. Direct focus: category tiles
        if self._is_tiles_focused():
            self._delete_tiles_selection()
            self.main_window.update_statusbar()
            return

        # 3. Direct focus or fallback: links table (only if tree is not focused)
        if (self._is_table_focused() or (self._is_table_stack_active() and not self._is_tree_focused())) and self._table_has_selection():
            links = self._selected_links()
            if links:
                self.main_window.links_actions.delete_links_with_confirmation(links)
                self.main_window.update_statusbar()
            return

    @pyqtSlot()
    def copy_current(self) -> None:
        """Copy selected items."""
        widget = self._get_text_widget()
        if widget is not None:
            try:
                widget.copy()
            except Exception:
                pass
            return

        # 1. Direct focus: structure tree
        if self._is_tree_focused() and self._has_tree_selection():
            self._copy_tree_selection()
            return

        # 2. Direct focus: category tiles
        if self._is_tiles_focused():
            self._copy_tiles_selection()
            return

        # 3. Direct focus or fallback: links table (only if tree is not focused)
        if (self._is_table_focused() or (self._is_table_stack_active() and not self._is_tree_focused())) and self._table_has_selection():
            self.main_window.links_actions.copy_selected_links()
            return

    @pyqtSlot()
    def cut_current(self) -> None:
        """Cut selected items."""
        widget = self._get_text_widget()
        if widget is not None:
            try:
                widget.cut()
            except Exception:
                pass
            return

        # 1. Direct focus: structure tree
        if self._is_tree_focused() and self._has_tree_selection():
            self._cut_tree_selection()
            return

        # 2. Direct focus: category tiles
        if self._is_tiles_focused():
            self._cut_tiles_selection()
            return

        # 3. Direct focus or fallback: links table (only if tree is not focused)
        if (self._is_table_focused() or (self._is_table_stack_active() and not self._is_tree_focused())) and self._table_has_selection():
            self.main_window.links_actions.cut_selected_links()
            return

    @pyqtSlot()
    def paste_current(self) -> None:
        """Paste items."""
        widget = self._get_text_widget()
        if widget is not None:
            try:
                widget.paste()
            except Exception:
                pass
            return

        # 1. Direct focus: structure tree
        if self._is_tree_focused():
            self._paste_into_tree()
            return

        # 2. Direct focus: category tiles
        if self._is_tiles_focused():
            self._paste_into_tiles()
            return

        # 3. Direct focus or fallback: links table (only if tree is not focused)
        if self._is_table_focused() or (self._is_table_stack_active() and not self._is_tree_focused()):
            self.main_window.links_actions.paste_links()
            return

        self.main_window.links_actions.paste_links()

    @pyqtSlot()
    def select_all_current(self) -> None:
        """Select all items in current context."""
        widget = self._get_text_widget()
        if widget is not None:
            try:
                widget.selectAll()
            except Exception:
                pass
            return

        if self._is_tree_focused():
            self._select_all_in_tree()
            return

        if self._is_tiles_focused():
            self._select_all_in_tiles()
            return

        if self._is_table_focused() or self._is_table_stack_active():
            self.main_window.select_all_links()

    @pyqtSlot()
    def clear_selection_current(self) -> None:
        """Clear selection in the current context."""
        widget = self._get_text_widget()
        if widget is not None:
            try:
                if hasattr(widget, "deselect"):
                    widget.deselect()
                else:
                    cursor = widget.textCursor()
                    cursor.clearSelection()
                    widget.setTextCursor(cursor)
            except Exception:
                pass
            return

        if self._is_tree_focused():
            tree = getattr(self.main_window, "tree", None)
            if tree and hasattr(tree, "selectionModel"):
                sel = tree.selectionModel()
                if sel:
                    sel.clearSelection()
            return

        if self._is_tiles_focused():
            view = self._get_tiles_view()
            if view and hasattr(view, "selectionModel"):
                sel = view.selectionModel()
                if sel:
                    sel.clearSelection()
            return

        if self._is_table_focused() or self._is_table_stack_active():
            table = getattr(self.main_window, "table", None)
            if table and hasattr(table, "clearSelection"):
                table.clearSelection()
    @pyqtSlot()
    def undo_current(self) -> None:
        """Undo in the current context."""
        widget = self._get_text_widget()
        if widget is not None:
            try:
                widget.undo()
            except Exception:
                pass
            return
        undo_stack = getattr(self.main_window, "undo_stack", None)
        if undo_stack:
            undo_stack.undo()

    @pyqtSlot()
    def redo_current(self) -> None:
        """Redo in the current context."""
        widget = self._get_text_widget()
        if widget is not None:
            try:
                widget.redo()
            except Exception:
                pass
            return
        undo_stack = getattr(self.main_window, "undo_stack", None)
        if undo_stack:
            undo_stack.redo()

    def _edit_selected_link(self):
        """Edit selected link."""
        if self.main_window.links_actions.edit_selected_link():
            return

    def _get_selected_links(self):
        """Get list of selected links via LinksActions facade."""
        try:
            return self.main_window.links_actions.get_selected_links()
        except Exception:
            logger.debug(
                "ActionController: failed to get selected links via facade",
                exc_info=True,
            )
            return []

    def cancel_cut(self) -> None:
        """Cancel cut operation and restore item visuals."""
        self._clipboard_is_cut = False
        self._cut_item_type = None
        self._cut_item_ids = set()
        self._clear_cut_visuals()

    def _clear_cut_visuals(self) -> None:
        tree = getattr(self.main_window, "tree", None)
        if tree and hasattr(tree, "model") and tree.model() and hasattr(tree.model(), "clear_cut_items"):
            tree.model().clear_cut_items()
        tiles = getattr(self.main_window, "tiles", None)
        tiles_view = getattr(tiles, "view", None) if tiles else None
        if tiles_view and hasattr(tiles_view, "model") and tiles_view.model() and hasattr(tiles_view.model(), "clear_cut_category_ids"):
            tiles_view.model().clear_cut_category_ids()

    def _update_cut_visuals(self) -> None:
        self._clear_cut_visuals()
        if not self._clipboard_is_cut or not self._cut_item_ids:
            return
        tree = getattr(self.main_window, "tree", None)
        if tree and hasattr(tree, "model") and tree.model() and hasattr(tree.model(), "set_cut_items"):
            tree.model().set_cut_items(self._cut_item_type, self._cut_item_ids)
        if self._cut_item_type == "category":
            tiles = getattr(self.main_window, "tiles", None)
            tiles_view = getattr(tiles, "view", None) if tiles else None
            if tiles_view and hasattr(tiles_view, "model") and tiles_view.model() and hasattr(tiles_view.model(), "set_cut_category_ids"):
                tiles_view.model().set_cut_category_ids(self._cut_item_ids)

    def _copy_tree_selection(self) -> None:
        svc = self._get_structure_context_service()
        if svc is None:
            return
        self.cancel_cut()
        selection_type = self._get_tree_selection_type()
        if selection_type == "section":
            ids = self._get_selected_tree_ids("section")
            if not ids:
                return
            if len(ids) > 1:
                svc.copy_sections_to_clipboard(ids)
            else:
                svc.copy_section_tree_to_clipboard(ids[0])
        elif selection_type == "category":
            ids = self._get_selected_tree_ids("category")
            if not ids:
                return
            if len(ids) > 1:
                svc.copy_categories_to_clipboard(ids)
            else:
                svc.copy_category_tree_to_clipboard(ids[0])

    def _cut_tree_selection(self) -> None:
        svc = self._get_structure_context_service()
        if svc is None:
            return
        selection_type = self._get_tree_selection_type()
        if selection_type == "section":
            ids = self._get_selected_tree_ids("section")
            if not ids:
                return
            if len(ids) > 1:
                svc.copy_sections_to_clipboard(ids)
            else:
                svc.copy_section_tree_to_clipboard(ids[0])
            self._clipboard_is_cut = True
            self._cut_item_type = "section"
            self._cut_item_ids = set(ids)
            self._update_cut_visuals()
        elif selection_type == "category":
            ids = self._get_selected_tree_ids("category")
            if not ids:
                return
            if len(ids) > 1:
                svc.copy_categories_to_clipboard(ids)
            else:
                svc.copy_category_tree_to_clipboard(ids[0])
            self._clipboard_is_cut = True
            self._cut_item_type = "category"
            self._cut_item_ids = set(ids)
            self._update_cut_visuals()

    def _resolve_category_paste_conflicts(
        self, target_section_id: int, trees: list[dict], is_cut: bool = False
    ) -> list[dict] | None:
        import copy
        from app.controllers.ui.conflict_resolution_session import ConflictResolutionSession

        sb = getattr(self.main_window, "structure_business", None)
        existing_cats = sb.get_categories(int(target_section_id)) or [] if sb else []
        existing_names = [str(c.get("name", "")) for c in existing_cats]
        resolved_trees = []

        allocated_names_lower = {n.lower() for n in existing_names}
        conflict_count = 0
        for t in trees:
            c_name = str((t.get("category") or {}).get("name", "")).strip()
            if not c_name:
                continue
            if c_name.lower() in allocated_names_lower:
                conflict_count += 1
            else:
                allocated_names_lower.add(c_name.lower())

        session = ConflictResolutionSession(
            self.main_window,
            operation="paste",
            total_conflicts=conflict_count,
        )
        existing_names_set = set(existing_names)
        allocated_names_lower = {n.lower() for n in existing_names}

        for tree in copy.deepcopy(trees):
            cat = dict(tree.get("category") or {})
            cat_name = str(cat.get("name", "")).strip()
            if cat_name and cat_name.lower() in allocated_names_lower:
                action, copy_name = session.resolve(
                    "category", cat_name, existing_names_set
                )
                if action == "cancel":
                    return None
                if action == "skip":
                    continue
                if action == "copy":
                    tree["category"]["name"] = copy_name
                    existing_names_set.add(copy_name)
                    allocated_names_lower.add(copy_name.lower())
                elif action == "merge":
                    target_cat = next(
                        (
                            c
                            for c in existing_cats
                            if str(c.get("name", "")).strip().lower()
                            == cat_name.lower()
                        ),
                        None,
                    )
                    if target_cat and target_cat.get("id"):
                        tree["_action"] = "merge"
                        tree["_target_category_id"] = int(target_cat["id"])
            else:
                if cat_name:
                    existing_names_set.add(cat_name)
                    allocated_names_lower.add(cat_name.lower())
            resolved_trees.append(tree)
        return resolved_trees

    def _resolve_section_paste_conflicts(
        self, sphere_id: int, trees: list[dict], is_cut: bool = False
    ) -> list[dict] | None:
        import copy
        from app.controllers.ui.conflict_resolution_session import ConflictResolutionSession

        business = getattr(self.main_window, "structure_business", None)
        existing_secs = (
            business.get_sections(int(sphere_id)) or [] if business else []
        )
        existing_names = [str(s.get("name", "")) for s in existing_secs]
        resolved_trees = []

        allocated_names_lower = {n.lower() for n in existing_names}
        conflict_count = 0
        for t in trees:
            s_name = str((t.get("section") or {}).get("name", "")).strip()
            if not s_name:
                continue
            if s_name.lower() in allocated_names_lower:
                conflict_count += 1
            else:
                allocated_names_lower.add(s_name.lower())

        session = ConflictResolutionSession(
            self.main_window,
            operation="paste",
            total_conflicts=conflict_count,
        )
        existing_names_set = set(existing_names)
        allocated_names_lower = {n.lower() for n in existing_names}

        for tree in copy.deepcopy(trees):
            sec = dict(tree.get("section") or {})
            sec_name = str(sec.get("name", "")).strip()
            if sec_name and sec_name.lower() in allocated_names_lower:
                action, copy_name = session.resolve(
                    "section", sec_name, existing_names_set
                )
                if action == "cancel":
                    return None
                if action == "skip":
                    continue
                if action == "copy":
                    tree["section"]["name"] = copy_name
                    existing_names_set.add(copy_name)
                    allocated_names_lower.add(copy_name.lower())
                elif action == "merge":
                    target_sec = next(
                        (
                            s
                            for s in existing_secs
                            if str(s.get("name", "")).strip().lower()
                            == sec_name.lower()
                        ),
                        None,
                    )
                    if target_sec and target_sec.get("id"):
                        tree["_action"] = "merge"
                        tree["_target_section_id"] = int(target_sec["id"])
            else:
                if sec_name:
                    existing_names_set.add(sec_name)
                    allocated_names_lower.add(sec_name.lower())
            resolved_trees.append(tree)
        return resolved_trees

    def _execute_paste_categories(self, target_section_id: int, is_cut: bool) -> None:
        svc = self._get_structure_context_service()
        if svc is None:
            return
        payload = svc.get_clipboard_payload()
        trees = svc.normalize_category_trees(payload)
        if not trees:
            return
        resolved_trees = self._resolve_category_paste_conflicts(
            int(target_section_id), trees, is_cut=is_cut
        )
        if resolved_trees is None:
            return
        if not resolved_trees:
            if is_cut:
                self.cancel_cut()
            return

        undo_stack = getattr(self.main_window, "undo_stack", None)
        if undo_stack is None:
            return

        if is_cut and self._cut_item_type == "category" and self._cut_item_ids:
            from app.utils.ui.dnd.categories_command import (
                MergeCategoriesCommand,
                MoveCategoriesCommand,
            )

            planned_moves: list[int] = []
            name_overrides: dict[int, str] = {}
            planned_merges: list[tuple[int, int]] = []
            for t in resolved_trees:
                cid = (t.get("category") or {}).get("id")
                if cid and cid in self._cut_item_ids:
                    if t.get("_action") == "merge" and t.get("_target_category_id"):
                        planned_merges.append(
                            (int(cid), int(t["_target_category_id"]))
                        )
                    else:
                        planned_moves.append(int(cid))
                        new_name = (t.get("category") or {}).get("name")
                        if new_name:
                            name_overrides[int(cid)] = str(new_name)

            undo_stack.beginMacro(self.tr("Paste categories"))
            try:
                for cid, tgt_id in planned_merges:
                    undo_stack.push(MergeCategoriesCommand(cid, tgt_id, self.main_window))
                if planned_moves:
                    undo_stack.push(
                        MoveCategoriesCommand(
                            planned_moves,
                            int(target_section_id),
                            0,
                            self.main_window,
                            name_overrides=name_overrides,
                        )
                    )
            finally:
                undo_stack.endMacro()
            self.cancel_cut()
            return

        undo_stack.push(
            PasteCategoriesCmd(
                resolved_trees,
                int(target_section_id),
                self.main_window,
                business=getattr(self.main_window, "structure_business", None),
                undo_manager=undo_stack,
                is_cut=False,
            )
        )
        if is_cut:
            self.cancel_cut()

    def _execute_paste_sections(self, sphere_id: int, is_cut: bool) -> None:
        svc = self._get_structure_context_service()
        if svc is None:
            return
        business = getattr(self.main_window, "structure_business", None)
        payload = svc.get_clipboard_payload()
        trees = svc.normalize_section_trees(payload)
        if not trees:
            return
        resolved_trees = self._resolve_section_paste_conflicts(
            int(sphere_id), trees, is_cut=is_cut
        )
        if resolved_trees is None:
            return
        if not resolved_trees:
            if is_cut:
                self.cancel_cut()
            return

        undo_stack = getattr(self.main_window, "undo_stack", None)
        if undo_stack is None:
            return

        if is_cut and self._cut_item_type == "section" and self._cut_item_ids:
            from app.utils.ui.dnd.section_command import (
                MergeSectionToSphereCommand,
                MoveSectionsToSphereCommand,
            )

            planned_moves: list[int] = []
            name_overrides: dict[int, str] = {}
            planned_merges: list[tuple[int, int]] = []
            for t in resolved_trees:
                sid = (t.get("section") or {}).get("id")
                if sid and sid in self._cut_item_ids:
                    if t.get("_action") == "merge" and t.get("_target_section_id"):
                        planned_merges.append(
                            (int(sid), int(t["_target_section_id"]))
                        )
                    else:
                        planned_moves.append(int(sid))
                        new_name = (t.get("section") or {}).get("name")
                        if new_name:
                            name_overrides[int(sid)] = str(new_name)
            undo_stack.beginMacro(self.tr("Paste sections"))
            try:
                for sid, tgt_id in planned_merges:
                    undo_stack.push(
                        MergeSectionToSphereCommand(sid, tgt_id, self.main_window)
                    )
                if planned_moves:
                    undo_stack.push(
                        MoveSectionsToSphereCommand(
                            planned_moves,
                            int(sphere_id),
                            self.main_window,
                            name_overrides=name_overrides,
                        )
                    )
            finally:
                undo_stack.endMacro()
            self.cancel_cut()
            return

        undo_stack.push(
            PasteSectionsCmd(
                resolved_trees,
                int(sphere_id),
                self.main_window,
                business=business,
                undo_manager=undo_stack,
                is_cut=False,
            )
        )
        if is_cut:
            self.cancel_cut()

    def _paste_into_tree(self) -> None:
        svc = self._get_structure_context_service()
        if svc is None:
            return
        is_cut = self._clipboard_is_cut
        target_section_id = self._get_tree_target_section_id()
        if target_section_id is not None and svc.clipboard_has_pastable_category():
            self._execute_paste_categories(int(target_section_id), is_cut)
            return
        if svc.clipboard_has_pastable_section():
            business = getattr(self.main_window, "structure_business", None)
            sphere_id = (
                business.get_current_sphere_id()
                if business and hasattr(business, "get_current_sphere_id")
                else None
            )
            if sphere_id:
                self._execute_paste_sections(int(sphere_id), is_cut)
                return
        target_category_id = self._get_tree_target_category_id()
        if target_category_id is not None and hasattr(self.main_window, "links_actions"):
            self.main_window.links_actions.paste_link(target_category_id=target_category_id)

    def _copy_tiles_selection(self) -> None:
        svc = self._get_structure_context_service()
        if svc is None:
            return
        self.cancel_cut()
        ids = self._get_tiles_selected_ids()
        if not ids:
            return
        if len(ids) > 1:
            svc.copy_categories_to_clipboard(ids)
        else:
            svc.copy_category_tree_to_clipboard(ids[0])

    def _cut_tiles_selection(self) -> None:
        svc = self._get_structure_context_service()
        if svc is None:
            return
        ids = self._get_tiles_selected_ids()
        if not ids:
            return
        self._clipboard_is_cut = True
        self._cut_item_type = "category"
        self._cut_item_ids = set(ids)
        self._update_cut_visuals()

    def _paste_into_tiles(self) -> None:
        svc = self._get_structure_context_service()
        if svc is None:
            return
        is_cut = self._clipboard_is_cut
        target_section_id = self._get_tiles_target_section_id()
        if target_section_id is not None and svc.clipboard_has_pastable_category():
            self._execute_paste_categories(int(target_section_id), is_cut)
            return
        if svc.clipboard_has_pastable_section():
            business = getattr(self.main_window, "structure_business", None)
            sphere_id = (
                business.get_current_sphere_id()
                if business and hasattr(business, "get_current_sphere_id")
                else None
            )
            if sphere_id:
                self._execute_paste_sections(int(sphere_id), is_cut)
                return
        target_category_id = self._get_tiles_target_category_id()
        if target_category_id is not None and hasattr(self.main_window, "links_actions"):
            self.main_window.links_actions.paste_link(target_category_id=target_category_id)

    def _select_all_in_tiles(self) -> None:
        view = self._get_tiles_view()
        if view is None:
            return
        sel_model = view.selectionModel() if hasattr(view, "selectionModel") else None
        model = view.model() if hasattr(view, "model") else None
        if not (sel_model and model):
            return
        try:
            rows = int(model.rowCount())
        except Exception:
            return
        if rows <= 0:
            return
        sel_model.clearSelection()
        from PyQt6.QtCore import QItemSelection, QItemSelectionModel

        top_left = model.index(0, 0)
        bottom_right = model.index(rows - 1, 0)
        selection = QItemSelection(top_left, bottom_right)
        sel_model.select(
            selection,
            QItemSelectionModel.SelectionFlag.Select,
        )

    def _select_all_in_tree(self) -> None:
        try:
            tree = self.main_window.structure.tree
        except Exception:
            return
        if not tree or not hasattr(tree, "currentIndex"):
            return
        idx = tree.currentIndex()
        if not (idx and idx.isValid()):
            return
        t = get_tree_tuple(idx, 0)
        if not t:
            return
        parent_idx = idx.parent()
        model = tree.model() if hasattr(tree, "model") else None
        sel_model = tree.selectionModel() if hasattr(tree, "selectionModel") else None
        if not (model and sel_model):
            return
        try:
            rows = model.rowCount(parent_idx)
        except Exception:
            return
        if rows <= 0:
            return
        sel_model.clearSelection()
        top_left = model.index(0, 0, parent_idx)
        bottom_right = model.index(rows - 1, 0, parent_idx)
        from PyQt6.QtCore import QItemSelection, QItemSelectionModel

        selection = QItemSelection(top_left, bottom_right)
        sel_model.select(
            selection,
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows,
        )

    def _delete_text_selection(self, widget) -> None:
        if isinstance(widget, QLineEdit):
            try:
                if hasattr(widget, "del_"):
                    widget.del_()
                else:
                    widget.backspace()
            except Exception:
                pass
            return
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            try:
                cursor = widget.textCursor()
                if cursor.hasSelection():
                    cursor.removeSelectedText()
                else:
                    cursor.deleteChar()
                widget.setTextCursor(cursor)
            except Exception:
                pass

    def update_action_states(self) -> None:
        if not self._global_actions_ready:
            return
        self._bind_selection_signals()
        widget = self._get_text_widget()
        has_text_sel = self._text_has_selection(widget) if widget else False

        tree_has_selection = self._has_tree_selection()
        table_has_selection = self._table_has_selection()
        tiles_has_selection = bool(self._get_tiles_selected_ids())
        tree_focused = self._is_tree_focused()
        table_focused = self._is_table_focused()
        tiles_focused = self._is_tiles_focused()
        is_table_active = table_focused or self._is_table_stack_active()

        can_copy = has_text_sel
        can_cut = has_text_sel
        can_delete = has_text_sel
        can_paste = widget is not None

        if tiles_focused:
            can_copy = tiles_has_selection
            can_cut = tiles_has_selection
            can_delete = tiles_has_selection
            svc = self._get_structure_context_service()
            can_paste = bool(
                svc
                and (svc.clipboard_has_pastable_category() or svc.clipboard_has_pastable_section())
            )
        elif tree_focused:
            selection_type = self._get_tree_selection_type()
            can_copy = bool(selection_type)
            can_cut = bool(selection_type)
            can_delete = bool(selection_type)
            svc = self._get_structure_context_service()
            can_paste = bool(
                svc
                and (svc.clipboard_has_pastable_category() or svc.clipboard_has_pastable_section())
            )
        elif is_table_active:
            can_copy = table_has_selection
            can_cut = table_has_selection
            can_delete = table_has_selection
            can_paste = bool(get_link_from_clipboard())
        else:
            if tree_has_selection:
                selection_type = self._get_tree_selection_type()
                can_copy = bool(selection_type)
                can_cut = bool(selection_type)
                can_delete = bool(selection_type)
            elif table_has_selection:
                can_copy = True
                can_cut = True
                can_delete = True
                can_paste = bool(get_link_from_clipboard())

        if self.cut_action:
            self.cut_action.setEnabled(bool(can_cut))
        if self.copy_action:
            self.copy_action.setEnabled(bool(can_copy))
        if self.paste_action:
            self.paste_action.setEnabled(bool(can_paste))
        if self.delete_action:
            self.delete_action.setEnabled(bool(can_delete))
        if self.select_all_action:
            self.select_all_action.setEnabled(
                bool(widget or tree_focused or is_table_active or tiles_focused)
            )

        try:
            if hasattr(self.main_window, "update_group_launch_action_state"):
                self.main_window.update_group_launch_action_state()
        except Exception:
            pass

