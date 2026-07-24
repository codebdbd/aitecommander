# app/controllers/structure/icon_handling.py

import logging
from typing import Optional

from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QIcon

from app.controllers.ui.types import StructureTreeModelProtocol
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_category_icon_path, resolve_icon_for_link, resolve_section_icon_path


class IconHandling:
    def __init__(self, controller):
        self.controller = controller
        self.tree = controller.tree
        self.business = controller.business
        self._logger = logging.getLogger(__name__)

    def _get_icon_for_item(self, item_type: str, icon_name: str) -> QIcon:
        # Centralized resolver: considers both provided icon_name and type
        try:
            if item_type == "section":
                resolved = resolve_section_icon_path(icon_name)
            elif item_type == "category":
                resolved = resolve_category_icon_path(icon_name)
            else:
                resolved = resolve_icon_for_link({"type": item_type, "icon_path": icon_name or ""})
            if resolved:
                return create_icon_from_path(resolved)
        except Exception:
            self._logger.debug(
                "IconHandling._get_icon_for_item: failed to resolve icon for %s",
                item_type,
                exc_info=True,
            )
        # Empty icon if nothing found
        return QIcon()

    def reload_icons(self) -> None:
        """Reapply icons for all tree items.

        Traverse QTreeView model and set icons via DecorationRole.
        """
        raw_model = getattr(self.tree, "model", lambda: None)()
        if raw_model is None:
            return
        if not isinstance(raw_model, StructureTreeModelProtocol):
            self._logger.error(
                "IconHandling.reload_icons: tree model does not conform to StructureTreeModelProtocol"
            )
            return

        from app.utils.ui.qt.roles import get_tree_tuple

        def iter_indexes(parent_index: Optional[QModelIndex] = None):
            parent = parent_index or QModelIndex()
            try:
                rows = raw_model.rowCount(parent)
            except Exception:
                self._logger.exception(
                    "IconHandling.reload_icons: failed to get rowCount for %s", parent
                )
                return
            for r in range(rows):
                try:
                    idx = raw_model.index(r, 0, parent)
                except Exception:
                    self._logger.exception(
                        "IconHandling.reload_icons: failed to get index (%s, %s)",
                        parent,
                        r,
                    )
                    continue
                if idx.isValid():
                    yield idx
                    yield from iter_indexes(idx)

        for idx in iter_indexes():
            try:
                tree_tuple = get_tree_tuple(idx, 0)
            except Exception:
                tree_tuple = None
            if not tree_tuple:
                self._safe_set_icon(raw_model, idx, QIcon())
                continue
            item_type, item_id = tree_tuple
            icon = self._resolve_icon(item_type, item_id)
            self._safe_set_icon(raw_model, idx, icon)

    def _resolve_icon(self, item_type: str, item_id: int) -> QIcon:
        try:
            if item_type == "section":
                data = self.business.get_section_data(item_id)
            elif item_type == "category":
                data = self.business.get_category_data(item_id)
            else:
                data = None
        except Exception:
            self._logger.exception(
                "IconHandling._resolve_icon: failed to load data for %s #%s",
                item_type,
                item_id,
            )
            data = None
        if not data:
            return QIcon()
        return self._get_icon_for_item(item_type, data.get("icon_path", ""))

    def _safe_set_icon(
        self, model: StructureTreeModelProtocol, index: QModelIndex, icon: QIcon
    ) -> None:
        try:
            model.setData(index, icon, Qt.ItemDataRole.DecorationRole)
        except Exception:
            self._logger.debug(
                "IconHandling._safe_set_icon: failed to set icon for index %s",
                index,
                exc_info=True,
            )
