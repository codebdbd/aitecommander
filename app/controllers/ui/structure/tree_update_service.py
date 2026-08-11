from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QModelIndex, QObject, Qt
from PyQt6.QtGui import QIcon

from app.config_data.runtime_config import is_tree_alphabetical_sort_enabled
from app.controllers.ui.state.task_scheduler import schedule_selection_restore
from app.utils.ui.focus import get_focus_manager

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.controllers.ui.structure.tree_management import TreeManagement


class TreeUpdateService(QObject):
    """Encapsulates insert/update/delete operations for tree items."""

    def __init__(self, manager: TreeManagement, tree: Any, model: Any) -> None:
        parent = manager if isinstance(manager, QObject) else None
        super().__init__(parent=parent)
        self._manager = manager
        self._tree = tree
        self._model = model

    # --- Public API -----------------------------------------------------
    def handle_item_added(
        self, item_type: str, parent_id: int, data: dict[str, Any]
    ) -> None:
        if item_type == "section":
            self._insert_section(data)
        elif item_type == "category":
            self._insert_category(parent_id, data)
            if data.get("__from_undo__"):
                logger.info(
                    "TreeUpdateService.handle_item_added: undo category inserted parent_id=%s id=%s row=%s position=%s",
                    parent_id,
                    data.get("id"),
                    data.get("row"),
                    data.get("position"),
                )
        else:
            return
        skip_focus = bool(data.get("__from_undo__") or data.get("__skip_focus__"))
        if not skip_focus:
            self._focus_on_new_item(item_type, data.get("id"))

    def handle_item_updated(
        self, item_type: str, item_id: int, data: dict[str, Any]
    ) -> None:
        category_moved = False
        if item_type == "category" and isinstance(item_id, int):
            category_moved = self._handle_category_section_change(item_id, data or {})

        if not category_moved:
            try:
                self._model.update_item(item_type, item_id, data or {})
            except (ValueError, RuntimeError):
                logger.exception(
                    "TreeUpdateService.handle_item_updated: model update failed for %s #%s",
                    item_type,
                    item_id,
                )
                raise

        controller = getattr(self._manager, "controller", None)
        selection_handler = getattr(controller, "selection_handler", None)
        if item_type == "category" and isinstance(item_id, int) and selection_handler:
            target_section_id = self._coerce_int((data or {}).get("section_id"))
            schedule_selection_restore(
                lambda: selection_handler._restore_category_selection(  # noqa: SLF001
                    item_id,
                    target_section_id=target_section_id,
                ),
                f"restore_cat_{item_id}",
            )
            # Restore focus to tree after editing category
            try:
                manager = get_focus_manager()
                manager.set_focus(
                    self._tree, widget_name="structure_tree", origin="user_action"
                )
            except Exception:
                logger.debug(
                    "TreeUpdateService.handle_item_updated: set_focus failed",
                    exc_info=True,
                )

    def _handle_category_section_change(
        self, category_id: int, data: dict[str, Any]
    ) -> bool:
        target_section_id = self._coerce_int(data.get("section_id"))
        if target_section_id is None:
            return False

        current_section_id = self._current_category_section_id(category_id)
        if current_section_id is None or current_section_id == target_section_id:
            return False

        controller = getattr(self._manager, "controller", None)
        business = getattr(controller, "business", None)
        if business is None or not hasattr(business, "get_categories"):
            return False

        replaced_any = False
        for section_id in dict.fromkeys((current_section_id, target_section_id)):
            try:
                categories = business.get_categories(int(section_id)) or []
                self.replace_section_categories(int(section_id), categories)
                replaced_any = True
            except Exception:
                logger.exception(
                    "TreeUpdateService._handle_category_section_change: replace failed for section %s",
                    section_id,
                )
        if replaced_any:
            self._refresh_category_move_tiles(current_section_id, target_section_id)
        return replaced_any

    def _current_category_section_id(self, category_id: int) -> int | None:
        section_ids_getter = getattr(self._model, "section_ids_for_categories", None)
        if callable(section_ids_getter):
            try:
                section_ids = section_ids_getter([int(category_id)]) or []
                if section_ids:
                    return self._coerce_int(section_ids[0])
            except Exception:
                logger.debug(
                    "TreeUpdateService._current_category_section_id: section_ids lookup failed",
                    exc_info=True,
                )

        try:
            index = self._model.index_for("category", int(category_id))
            if index and index.isValid():
                node = index.internalPointer()
                parent = getattr(node, "parent", None)
                return self._coerce_int(getattr(parent, "id", None))
        except Exception:
            logger.debug(
                "TreeUpdateService._current_category_section_id: index parent lookup failed",
                exc_info=True,
            )
        return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _refresh_category_move_tiles(
        self, old_section_id: int, new_section_id: int
    ) -> None:
        for section_id in dict.fromkeys((old_section_id, new_section_id)):
            try:
                self._manager.refresh_section_tiles(int(section_id))
            except Exception:
                logger.debug(
                    "TreeUpdateService._refresh_category_move_tiles: refresh failed for section %s",
                    section_id,
                    exc_info=True,
                )

    def handle_item_deleted(self, item_type: str, item_id: int) -> None:
        try:
            if item_type == "section":
                self._model.remove_sections([int(item_id)])
            elif item_type == "category":
                self._model.remove_categories([int(item_id)])
        except Exception:
            logger.exception(
                "TreeUpdateService.handle_item_deleted: remove failed for %s #%s",
                item_type,
                item_id,
            )
        finally:
            self._post_delete_updates(item_type, item_id)
            try:
                manager = get_focus_manager()
                manager.set_focus(
                    self._tree, widget_name="structure_tree", origin="user_action"
                )
            except Exception:
                logger.debug(
                    "TreeUpdateService.handle_item_deleted: set_focus failed",
                    exc_info=True,
                )

    def handle_items_batch_deleted(self, item_type: str, item_ids: list[int]) -> None:
        try:
            if item_type == "section":
                self._model.remove_sections([int(i) for i in item_ids or []])
            elif item_type == "category":
                ids = [int(i) for i in item_ids or []]
                replaced = self._replace_touched_category_sections(ids)
                if not replaced:
                    self._model.remove_categories(ids)
            else:
                return
        except Exception:
            logger.exception(
                "TreeUpdateService.handle_items_batch_deleted: remove failed for %s count=%s",
                item_type,
                len(item_ids or []),
            )
        finally:
            try:
                self._post_delete_updates(item_type, int(item_ids[0]) if item_ids else 0)
            except Exception:
                logger.debug(
                    "TreeUpdateService.handle_items_batch_deleted: post delete updates failed",
                    exc_info=True,
                )
            try:
                manager = get_focus_manager()
                manager.set_focus(
                    self._tree, widget_name="structure_tree", origin="user_action"
                )
            except Exception:
                logger.debug(
                    "TreeUpdateService.handle_items_batch_deleted: set_focus failed",
                    exc_info=True,
                )

    def _replace_touched_category_sections(self, category_ids: list[int]) -> bool:
        if not category_ids:
            return False
        section_ids_getter = getattr(self._model, "section_ids_for_categories", None)
        if not callable(section_ids_getter):
            return False
        try:
            section_ids = [
                int(sid)
                for sid in (section_ids_getter(category_ids) or [])
                if isinstance(sid, int) and sid > 0
            ]
        except Exception:
            logger.debug(
                "TreeUpdateService._replace_touched_category_sections: section_ids lookup failed",
                exc_info=True,
            )
            return False
        if not section_ids:
            return False
        controller = getattr(self._manager, "controller", None)
        business = getattr(controller, "business", None)
        if business is None or not hasattr(business, "get_categories"):
            return False
        replaced_any = False
        for section_id in section_ids:
            try:
                categories = business.get_categories(int(section_id)) or []
                self.replace_section_categories(int(section_id), categories)
                replaced_any = True
            except Exception:
                logger.exception(
                    "TreeUpdateService._replace_touched_category_sections: replace failed for section %s",
                    section_id,
                )
        return replaced_any

    def replace_section_categories(
        self, section_id: int, categories: list[dict[str, Any]]
    ) -> None:
        try:
            replace_fn = getattr(self._model, "replace_section_categories", None)
            if callable(replace_fn):
                replace_fn(int(section_id), categories or [])
                return
        except Exception:
            logger.exception(
                "TreeUpdateService.replace_section_categories: model replace failed for section %s",
                section_id,
            )
            return

        try:
            parent_index = self._model.index_for("section", int(section_id))
        except Exception:
            parent_index = QModelIndex()
        try:
            existing_ids: list[int] = []
            if parent_index.isValid():
                total = int(self._model.rowCount(parent_index))
                for row in range(total):
                    idx = self._model.index(row, 0, parent_index)
                    if not idx.isValid():
                        continue
                    meta = self._model.data(idx, Qt.ItemDataRole.UserRole)
                    if (
                        isinstance(meta, (tuple, list))
                        and len(meta) == 2
                        and meta[0] == "category"
                        and isinstance(meta[1], int)
                    ):
                        existing_ids.append(int(meta[1]))
            if existing_ids:
                self._model.remove_categories(existing_ids)
            if categories:
                self._model.insert_categories(int(section_id), -1, categories)
        except Exception:
            logger.exception(
                "TreeUpdateService.replace_section_categories: fallback failed for section %s",
                section_id,
            )

    # --- Helpers --------------------------------------------------------
    @staticmethod
    def _row_to_index(raw_row: Any) -> int:
        try:
            return int(raw_row)
        except (TypeError, ValueError):
            return -1

    def _positioned_insert_row(
        self, parent_index: QModelIndex, desired_position: Any
    ) -> int:
        """Compute insert row based on sibling payload positions."""
        try:
            target_pos = int(desired_position)
        except (TypeError, ValueError):
            return -1
        if target_pos < 0:
            return -1
        try:
            total = int(self._model.rowCount(parent_index))
        except Exception:
            return -1
        count_before = 0
        for row in range(total):
            idx = self._model.index(row, 0, parent_index)
            if not idx.isValid():
                continue
            node = idx.internalPointer()
            payload = getattr(node, "payload", None) if node is not None else None
            pos_val = payload.get("position") if isinstance(payload, dict) else None
            try:
                pos_int = int(pos_val)
            except (TypeError, ValueError):
                continue
            if pos_int < target_pos:
                count_before += 1
        return count_before

    def _sorted_insert_row(self, parent_index: QModelIndex, item_name: Any) -> int:
        """Return row to insert item so the list stays case-insensitively sorted."""
        if not isinstance(item_name, str) or not item_name:
            try:
                return int(self._model.rowCount(parent_index))
            except Exception:
                return 0
        new_key = item_name.lower()
        try:
            total = int(self._model.rowCount(parent_index))
        except Exception:
            return 0
        for row in range(total):
            idx = self._model.index(row, 0, parent_index)
            existing = self._model.data(idx, Qt.ItemDataRole.DisplayRole)
            if isinstance(existing, str) and existing.lower() > new_key:
                return row
        return total

    @staticmethod
    def _normalize_icon_path(payload: dict[str, Any]) -> str | None:
        icon_path = payload.get("icon_path")
        if isinstance(icon_path, str):
            trimmed = icon_path.strip()
            if trimmed:
                return trimmed
        icon_hint = payload.get("icon")
        if isinstance(icon_hint, str):
            trimmed = icon_hint.strip()
            if trimmed:
                return trimmed
        return None

    @classmethod
    def _build_payload(cls, data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(data)
        icon = payload.get("icon")
        if not isinstance(icon, QIcon) or icon.isNull():
            icon = None

        icon_path = cls._normalize_icon_path(payload)
        payload["icon_path"] = icon_path

        if icon is not None:
            payload["icon"] = icon
        else:
            payload["icon"] = None
        return payload

    def _insert_section(self, data: dict[str, Any]) -> None:
        row_index = self._row_to_index(data.get("row"))
        sort_alpha = self._should_use_alphabetical_insert()
        if sort_alpha:
            row_index = self._sorted_insert_row(QModelIndex(), data.get("name"))
        else:
            if row_index < 0:
                row_index = self._positioned_insert_row(
                    QModelIndex(), data.get("position")
                )
            if row_index < 0:
                row_index = self._sorted_insert_row(QModelIndex(), data.get("name"))
        processed_data = self._build_payload(data)
        try:
            self._model.insert_sections(row_index, [processed_data])
        except (ValueError, RuntimeError):
            logger.exception("TreeUpdateService._insert_section: model insert failed")
            raise

    def _insert_category(self, parent_id: int, data: dict[str, Any]) -> None:
        row_index = self._row_to_index(data.get("row"))
        parent_index = QModelIndex()
        if hasattr(self._model, "index_for"):
            try:
                parent_index = self._model.index_for("section", int(parent_id))
            except Exception:
                parent_index = QModelIndex()
        sort_alpha = self._should_use_alphabetical_insert()
        if sort_alpha:
            row_index = self._sorted_insert_row(parent_index, data.get("name"))
        else:
            if row_index < 0:
                row_index = self._positioned_insert_row(
                    parent_index, data.get("position")
                )
            if row_index < 0:
                row_index = self._sorted_insert_row(parent_index, data.get("name"))
        processed_data = self._build_payload(data)
        try:
            self._model.insert_categories(parent_id, row_index, [processed_data])
        except (ValueError, RuntimeError):
            logger.exception("TreeUpdateService._insert_category: model insert failed")
            raise
        if not data.get("__from_undo__"):
            self._manager.refresh_section_tiles(parent_id)

    def _should_use_alphabetical_insert(self) -> bool:
        """Mirror tree snapshot sorting policy for incremental inserts."""
        try:
            if not bool(is_tree_alphabetical_sort_enabled(False)):
                return False
        except Exception:
            return False
        try:
            controller = getattr(self._manager, "controller", None)
            business = getattr(controller, "business", None)
            if business is not None and getattr(business, "_suppress_tree_sort_once", False):
                return False
        except Exception:
            return False
        return True

    def _focus_on_new_item(self, item_type: str, item_id: Any) -> None:
        if not isinstance(item_id, int):
            return
        controller = getattr(self._manager, "controller", None)
        if controller is None:
            return
        selection_handler = getattr(controller, "selection_handler", None)
        if selection_handler is None:
            return
        schedule_selection_restore(
            lambda: selection_handler._set_focus_on_new_item_by_id(item_type, item_id),  # noqa: SLF001
            f"new_{item_type}_{item_id}",
        )
        try:
            manager = get_focus_manager()
            manager.set_focus(
                self._tree, widget_name="structure_tree", origin="user_action"
            )
        except Exception:
            logger.debug(
                "TreeUpdateService._focus_on_new_item: set_focus failed",
                exc_info=True,
            )

    def _post_delete_updates(self, item_type: str, item_id: int) -> None:
        if item_type == "category":
            try:
                self._manager.refresh_tiles_for_current_selection()
            except Exception:
                logger.exception(
                    "TreeUpdateService._post_delete_updates: tiles refresh after category delete failed"
                )
        elif item_type == "section":
            try:
                model = self._tree.model()
                if model and hasattr(model, "rowCount"):
                    if int(model.rowCount(QModelIndex())) == 0:
                        self._manager.clear_tiles()
            except Exception:
                logger.exception(
                    "TreeUpdateService._post_delete_updates: tiles refresh after section delete failed"
                )
