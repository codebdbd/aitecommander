"""Context menu builder for the structure tree."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtWidgets import QMenu

# Context operations service for structure
from app.services.structure_context_service import StructureContextService
from app.utils.ui.icon.cache_manager import clear_icon_cache
from app.utils.ui.menu_builders.menu_actions import (
    ActionBuilder,
    MenuTexts,
    Shortcuts,
    StructureItemType,
)
from app.utils.ui.qt.roles import get_tree_tuple

from .base import get_menu_icon

if TYPE_CHECKING:
    from app.main_window import MainWindow

logger = logging.getLogger(__name__)


class StructureMenuBuilder:
    """Context menu builder for the structure tree."""

    def __init__(self, tree_widget, main_window: "MainWindow"):
        self.tree_widget = tree_widget
        self.main_window = main_window
        self.actions = ActionBuilder(tree_widget)
        self.theme = main_window.settings.get_theme()
        # Initialize business-logic service
        dc = getattr(self.main_window, "database_controller", None)
        db = getattr(dc, "db", None)
        self._svc = StructureContextService(db)

    def build(
        self,
        item: Optional[Any],
        delete_item_cb: Callable,
        add_new_section_cb: Callable,
        sort_tree_cb: Callable,
    ) -> QMenu:
        """Build context menu for the structure tree."""
        menu = QMenu(self.tree_widget)

        if item:
            self._add_item_actions(menu, item, delete_item_cb)
        else:
            self._add_root_actions(menu, add_new_section_cb, sort_tree_cb)

        return menu

    def _add_item_actions(self, menu: QMenu, item: Any, delete_item_cb: Callable):
        """Add actions for the selected item."""
        t = get_tree_tuple(item, 0)
        if not t:
            logger.warning("Invalid item data in context menu: None")
            return
        typ, id_ = t
        if typ not in (StructureItemType.SECTION, StructureItemType.CATEGORY):
            logger.warning("Unknown item type in context menu: %s", typ)
            return

        if typ == StructureItemType.SECTION:
            self._add_section_actions(menu, item, id_, delete_item_cb)
        elif typ == StructureItemType.CATEGORY:
            self._add_category_actions(menu, item, id_, delete_item_cb)

    def _add_section_actions(
        self, menu: QMenu, item: Any, section_id: Any, delete_item_cb: Callable
    ):
        """Actions for the selected section."""
        menu.addAction(
            self.actions.create(
                MenuTexts.EDIT_SECTION,
                lambda: self.main_window.edit_structure_item(item),
                Shortcuts.EDIT,
                get_menu_icon("edit", self.theme),
            )
        )
        menu.addAction(
            self.actions.create(
                MenuTexts.ADD_CATEGORY,
                self.main_window.add_new_category,
                Shortcuts.ADD_CATEGORY,
                get_menu_icon("add_category", self.theme),
            )
        )

        # Paste category from clipboard (if clipboard data is valid)
        if self._svc.clipboard_has_pastable_category():
            menu.addAction(
                self.actions.create(
                    MenuTexts.PASTE_CATEGORY,
                    lambda: self._paste_category_from_clipboard_to_section(section_id),
                    Shortcuts.CTRL_V,
                    get_menu_icon("paste", self.theme),
                )
            )

        menu.addSeparator()

        menu.addAction(
            self.actions.create(
                MenuTexts.DELETE_SECTION,
                lambda: delete_item_cb(item),
                Shortcuts.DELETE,
                get_menu_icon("delete", self.theme),
            )
        )

        menu.addSeparator()

        # Select all categories under section
        menu.addAction(
            self.actions.create(
                MenuTexts.SELECT_ALL_CATEGORIES,
                lambda: self._select_all_categories_in_section(item),
                Shortcuts.CTRL_A,
                get_menu_icon("select_all", self.theme),
            )
        )

        menu.addSeparator()

        # Undo/Redo from main window if available
        if hasattr(self.main_window, "undo_action") and self.main_window.undo_action:
            menu.addAction(self.main_window.undo_action)
        if hasattr(self.main_window, "redo_action") and self.main_window.redo_action:
            menu.addAction(self.main_window.redo_action)

    def _add_category_actions(
        self, menu: QMenu, item: Any, category_id: Any, delete_item_cb: Callable
    ):
        """Actions for the selected category."""
        menu.addAction(
            self.actions.create(
                MenuTexts.EDIT_CATEGORY,
                lambda: self.main_window.edit_structure_item(item),
                Shortcuts.EDIT,
                get_menu_icon("edit", self.theme),
            )
        )

        def _add_link_to_category():
            handler = getattr(self.main_window, "show_link_dialog_for_category", None)
            if callable(handler):
                try:
                    handler(int(category_id) if category_id is not None else None)
                except Exception:
                    logger.exception(
                        "[CtxMenu] Failed to open link dialog for category %s",
                        category_id,
                    )

        menu.addAction(
            self.actions.create(
                MenuTexts.ADD_LINK,
                _add_link_to_category,
                Shortcuts.ADD_LINK,
                get_menu_icon("add_link", self.theme),
            )
        )

        menu.addSeparator()

        menu.addAction(
            self.actions.create(
                MenuTexts.COPY_CATEGORY,
                lambda: self._copy_category_tree_to_clipboard(item, category_id),
                Shortcuts.CTRL_C,
                get_menu_icon("copy", self.theme),
            )
        )

        menu.addSeparator()

        def _delete_action():
            try:
                selected = self._get_selected_category_nodes()
            except Exception:
                logger.exception(
                    "[CtxMenu] Failed to get selected categories for deletion; using single-item delete"
                )
                selected = []
            if len(selected) > 1:
                logger.debug(
                    "[CtxMenu] Batch delete for %s selected categories", len(selected)
                )
                try:
                    if (
                        hasattr(self.main_window, "structure")
                        and self.main_window.structure
                    ):
                        self.main_window.structure.delete_selected_item()
                        return
                except Exception:
                    logger.exception(
                        "[CtxMenu] Batch delete failed for selected categories"
                    )
            delete_item_cb(item)

        try:
            selected_count = len(self._get_selected_category_nodes())
        except Exception:
            logger.exception(
                "[CtxMenu] Failed to compute selected categories count"
            )
            selected_count = 0
        action_text_key = (
            MenuTexts.DELETE_SELECTED if selected_count > 1 else MenuTexts.DELETE_CATEGORY
        )
        menu.addAction(
            self.actions.create(
                action_text_key,
                _delete_action,
                Shortcuts.DELETE,
                get_menu_icon("delete", self.theme),
            )
        )

        menu.addSeparator()

        if hasattr(self.main_window, "undo_action") and self.main_window.undo_action:
            menu.addAction(self.main_window.undo_action)
        if hasattr(self.main_window, "redo_action") and self.main_window.redo_action:
            menu.addAction(self.main_window.redo_action)

    # --- Helper methods ---
    # Proxy helpers for readability/backward-compatibility
    def _clipboard_has_text(self) -> bool:
        return self._svc.clipboard_has_text()

    def _clipboard_has_pastable_category(self) -> bool:
        return self._svc.clipboard_has_pastable_category()

    def _copy_category_tree_to_clipboard(self, item: Any, cat_id: Any) -> None:
        """Copy a single category tree or multiple (when multi-select) to clipboard."""
        try:
            selected = self._get_selected_category_nodes()
        except Exception:
            logger.exception(
                "[Clipboard] Failed to get selected categories list; copying single"
            )
            selected = []
        if len(selected) > 1:
            ids: list[int] = []
            for it in selected:
                t = get_tree_tuple(it, 0)
                if not t:
                    continue
                _, cid = t
                try:
                    ids.append(int(cid))
                except Exception:
                    logger.exception(
                        "[Clipboard] Invalid category id in selection: %r",
                        cid,
                    )
                    continue
            if ids:
                self._svc.copy_categories_to_clipboard(ids)
                return
        # Single category
        try:
            self._svc.copy_category_tree_to_clipboard(int(cat_id))
        except Exception:
            logger.exception(
                "[Clipboard] Failed to copy category tree id=%r to clipboard", cat_id
            )


    def _copy_selected_categories_to_clipboard(self, items: list[Any]) -> None:
        """Copy several selected categories by their ids via service."""
        ids: list[int] = []
        for it in items:
            t = get_tree_tuple(it, 0)
            if not t:
                continue
            typ, cat_id = t
            if typ != StructureItemType.CATEGORY:
                continue
            try:
                ids.append(int(cat_id))
            except Exception:
                logger.exception(
                    "[Clipboard] Invalid category id in selection: %r", cat_id
                )
                continue
        if ids:
            try:
                self._svc.copy_categories_to_clipboard(ids)
            except Exception:
                logger.exception(
                    "[Clipboard] Failed to batch copy categories to clipboard: %r",
                    ids,
                )

    def _paste_category_from_clipboard_to_section(self, section_id: Any) -> None:
        """Paste one or more categories from clipboard into a section (delegates business logic to service)."""
        try:
            logger.debug("[PasteCategories] start paste into section_id=%s", section_id)

            business = getattr(self.main_window, "structure_business", None)
            struct = getattr(self.main_window, "structure", None)
            selection = getattr(struct, "selection_handler", None)
            tree_widget = getattr(self, "tree_widget", None)

            # Suppress selection/tree signals during batch operation
            try:
                try:
                    self.main_window._suppress_deletes = True
                    logger.debug("[PasteCategories] _suppress_deletes set=True")
                except Exception:
                    logger.exception(
                        "[PasteCategories] Failed to set _suppress_deletes=True"
                    )
                if selection is not None:
                    try:
                        selection.begin_suppress_selection()
                    except Exception:
                        logger.exception(
                            "[PasteCategories] Failed to begin selection suppression"
                        )
                if tree_widget is not None:
                    tree_widget.blockSignals(True)
            except Exception:
                logger.exception(
                    "[PasteCategories] Failed to block signals/start UI suppression"
                )

            created_categories: list[dict] = []
            try:
                created_categories = self._svc.paste_from_clipboard_to_section(
                    int(section_id)
                )
            finally:
                # Restore signals
                try:
                    if tree_widget is not None:
                        tree_widget.blockSignals(False)
                except Exception:
                    logger.exception(
                        "[PasteCategories] Failed to unblock tree signals"
                    )
                try:
                    if selection is not None:
                        selection.end_suppress_selection()
                except Exception:
                    logger.exception(
                        "[PasteCategories] Failed to end selection suppression"
                    )
                try:
                    self.main_window._suppress_deletes = False
                    logger.debug("[PasteCategories] _suppress_deletes set=False")
                except Exception:
                    logger.exception(
                        "[PasteCategories] Failed to set _suppress_deletes=False"
                    )

            # Incremental UI update without full reload
            if created_categories:
                try:
                    if business:
                        try:
                            clear_icon_cache()
                        except Exception:
                            logger.exception(
                                "[PasteCategories] Failed to clear icon cache"
                            )
                        try:
                            business._invalidate_categories_cache(int(section_id))
                        except Exception:
                            logger.exception(
                                "[PasteCategories] Failed to invalidate categories cache for section %r",
                                section_id,
                            )
                        try:
                            if getattr(business, "async_service", None):
                                business.async_service.schedule_structure_reload(0)
                            logger.debug(
                                "[PasteCategories] scheduled structure reload (debounced)"
                            )
                        except Exception:
                            logger.exception(
                                "[PasteCategories] Failed to schedule structure reload"
                            )
                        business.section_selected.emit(int(section_id))
                except Exception:
                    logger.exception(
                        "[PasteCategories] Failed to update UI after pasting categories"
                    )
            logger.debug(
                "[PasteCategories] done, created=%s items", len(created_categories)
            )
        except Exception:
            # Do not crash UI due to paste errors — log them
            logger.exception(
                "[PasteCategories] Category paste failed for section %r", section_id
            )

    def _select_all_categories_in_section(self, item: Any) -> None:
        """Select all categories inside a section (QTreeView-only)."""
        try:
            if not (
                hasattr(self.tree_widget, "selectionModel")
                and hasattr(self.tree_widget, "model")
            ):
                return
            model = self.tree_widget.model()
            sel_model = self.tree_widget.selectionModel()
            if not (model and sel_model):
                return
            # item — QModelIndex of category or section
            idx = item if getattr(item, "isValid", lambda: False)() else None
            if idx is None:
                return
            t = get_tree_tuple(idx, 0)
            if not t:
                return
            typ, _ = t
            section_index = idx if typ == StructureItemType.SECTION else idx.parent()
            if not (section_index and section_index.isValid()):
                return
            # Clear current selection
            sel_model.clearSelection()
            # Select all child items (categories) of the section
            row_count = model.rowCount(section_index)
            for r in range(row_count):
                child = model.index(r, 0, section_index)
                if child and child.isValid():
                    tchild = get_tree_tuple(child, 0)
                    if tchild and tchild[0] == StructureItemType.CATEGORY:
                        sel_model.select(
                            child,
                            sel_model.SelectionFlag.Select
                            | sel_model.SelectionFlag.Rows,
                        )
        except Exception:
            logger.exception("[SelectAll] Failed to select all categories in section")

    # --- Category selection helpers ---
    def _get_selected_category_nodes(self) -> list[Any]:
        """Return selected category nodes for QTreeView (QModelIndex)."""
        try:
            if hasattr(self.tree_widget, "selectionModel") and hasattr(
                self.tree_widget, "model"
            ):
                sel_model = self.tree_widget.selectionModel()
                if not sel_model:
                    return []
                rows = sel_model.selectedRows(0) or []
                return [
                    idx
                    for idx in rows
                    if (
                        get_tree_tuple(idx, 0)
                        and get_tree_tuple(idx, 0)[0] == StructureItemType.CATEGORY
                    )
                ]
        except Exception:
            logger.exception("[Selection] Failed to fetch selected category nodes")
            return []
        return []

    def _add_root_actions(
        self, menu: QMenu, add_new_section_cb: Callable, sort_tree_cb: Callable
    ):
        """Add actions for the root level."""
        menu.addAction(
            self.actions.create(
                MenuTexts.ADD_SECTION,
                add_new_section_cb,
                Shortcuts.ADD_SECTION,
                get_menu_icon("add_section", self.theme),
            )
        )

        menu.addSeparator()

        menu.addAction(
            self.actions.create(
                MenuTexts.SORT_CATEGORIES,
                sort_tree_cb,
                Shortcuts.SORT,
                get_menu_icon("sort", self.theme),
            )
        )
