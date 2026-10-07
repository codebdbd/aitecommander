# app/utils/dnd/tree.py

"""Centralized drag & drop handler for structure tree.

Supports `StructureTreeView` (QTreeView) with model and indexes.
"""

import json
import logging
from pathlib import Path
import zipfile

from PyQt6.QtCore import QModelIndex, QPersistentModelIndex, QRect, Qt, QTimer
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QAbstractItemView

from app.config_data import app_config
from app.utils.ui.dnd.mime import MimeDataParser
from app.utils.ui.qt.roles import get_tree_tuple

from .base import TreeHandlerBase

logger = logging.getLogger(__name__)


class DragDropHandler(TreeHandlerBase):
    """Drag & drop operations handler in structure tree."""

    def __init__(self, tree_widget):
        super().__init__(tree_widget)
        self._auto_expand_timer: QTimer | None = None
        self._hover_expand_index: QPersistentModelIndex | None = None

    def _arm_auto_expand_timer(self, target_index: QModelIndex) -> None:
        """Start auto-expand timer for collapsed section if not already running."""
        if not target_index.isValid():
            self._cancel_auto_expand_timer()
            return
        p_idx = QPersistentModelIndex(target_index)
        if (
            self._hover_expand_index == p_idx
            and self._auto_expand_timer
            and self._auto_expand_timer.isActive()
        ):
            return
        self._cancel_auto_expand_timer()
        self._hover_expand_index = p_idx
        timer = QTimer(self.tree_widget)
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_auto_expand_timeout)
        self._auto_expand_timer = timer
        timer.start(500)

    def _on_auto_expand_timeout(self) -> None:
        """Expand hovered section and ensure its child categories are visible."""
        p_idx = self._hover_expand_index
        self._hover_expand_index = None
        self._auto_expand_timer = None
        if not p_idx or not p_idx.isValid():
            return
        idx = QModelIndex(p_idx)
        if not self.tree_widget.isExpanded(idx):
            self.tree_widget.expand(idx)
            model = self.tree_widget.model()
            if model:
                first_child = model.index(0, 0, idx)
                if first_child.isValid():
                    self.tree_widget.scrollTo(
                        first_child, QAbstractItemView.ScrollHint.EnsureVisible
                    )

    def _cancel_auto_expand_timer(self) -> None:
        """Cancel pending auto-expand timer."""
        if self._auto_expand_timer:
            try:
                self._auto_expand_timer.stop()
                self._auto_expand_timer.deleteLater()
            except Exception:
                pass
            self._auto_expand_timer = None
        self._hover_expand_index = None

    def accepts_mime_type(self, mime) -> bool:
        """Checks if widget accepts given MIME type."""
        return (
            mime.hasFormat(app_config.get_link_mime_type())
            or mime.hasFormat(app_config.get_category_mime_type())
            or mime.hasFormat(app_config.get_section_mime_type())
            or bool(self._extract_external_link_targets(mime))
        )

    def handle_drag_enter_event(self, event) -> None:
        """Handle drag enter event."""
        mime = event.mimeData()
        if self.accepts_mime_type(mime):
            event.acceptProposedAction()
        # Note: No parent class delegation since TreeHandlerBase doesn't inherit from Qt classes

    def handle_drag_move_event(self, event) -> None:
        """Visual feedback during dragging."""
        mime = event.mimeData()
        is_internal_move = event.source() == self.tree_widget

        # Path for QTreeView (model/indexes)
        src_index = self.tree_widget.currentIndex()
        if is_internal_move:
            if (
                src_index
                and src_index.isValid()
                and self._is_valid_drop_index(src_index, event)
            ):
                # Highlight target without changing selection
                target_index, drop_pos = self._resolve_internal_target(event)
                if target_index:
                    self.tree_widget.set_drag_drop_feedback(target_index, drop_pos)
                    event.accept()
                else:
                    self.tree_widget.clear_drag_highlight()
                    event.ignore()
            else:
                self.tree_widget.clear_drag_highlight()
                event.ignore()
        else:
            self._handle_external_drag_move_index(event, mime)
        return

    def _resolve_internal_target(
        self, event: QDropEvent
    ) -> tuple[QModelIndex | None, QAbstractItemView.DropIndicatorPosition]:
        """Resolve target index and drop position (Above, Below, OnItem) for internal drag."""
        try:
            target_index: QModelIndex = self.tree_widget.indexAt(
                event.position().toPoint()
            )
        except Exception as e:
            logger.debug("Failed to resolve target index: %s", e, exc_info=True)
            return None, QAbstractItemView.DropIndicatorPosition.OnItem

        if not target_index or not target_index.isValid():
            return None, QAbstractItemView.DropIndicatorPosition.OnItem

        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            return None, QAbstractItemView.DropIndicatorPosition.OnItem

        target_type, _ = ttuple
        rect = self.tree_widget.visualRect(target_index) if hasattr(self.tree_widget, "visualRect") else None
        if isinstance(rect, QRect) and rect.height() > 0:
            pos_y = event.position().toPoint().y() - rect.top()
            is_upper_half = pos_y < (rect.height() / 2)
        else:
            drop_pos = getattr(self.tree_widget, "dropIndicatorPosition", lambda: None)()
            is_upper_half = drop_pos != QAbstractItemView.DropIndicatorPosition.BelowItem

        pos = (
            QAbstractItemView.DropIndicatorPosition.AboveItem
            if is_upper_half
            else QAbstractItemView.DropIndicatorPosition.BelowItem
        )

        cur_tuple = get_tree_tuple(self.tree_widget.currentIndex(), 0)
        source_type = cur_tuple[0] if cur_tuple else None

        if source_type == "section":
            if target_type == "section":
                return target_index, pos
            return None, QAbstractItemView.DropIndicatorPosition.OnItem

        if source_type == "category":
            if target_type == "section":
                return target_index, QAbstractItemView.DropIndicatorPosition.OnItem
            if target_type == "category":
                return target_index, pos

        return None, QAbstractItemView.DropIndicatorPosition.OnItem



    def handle_drag_leave_event(self, event) -> None:
        """Handle drag leave event."""
        self._cancel_auto_expand_timer()
        self.tree_widget.clear_drag_highlight()
        event.accept()

    def handle_drop_event(self, event) -> None:
        """Main drop event handler."""
        try:
            self._cancel_auto_expand_timer()
            mime = event.mimeData()

            if event.source() == self.tree_widget:
                self._handle_internal_drop_event_index(event)
                return

            target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
            if mime.hasFormat(app_config.get_category_mime_type()):
                if self._handle_category_drop_index(mime, target_index):
                    event.accept()
                else:
                    event.ignore()
                return
            if mime.hasFormat(app_config.get_link_mime_type()):
                if self._handle_link_drop_index(mime, target_index):
                    event.accept()
                else:
                    event.ignore()
                return
            if self._extract_external_link_targets(mime):
                if self._handle_external_url_drop_index(mime, target_index):
                    event.setDropAction(Qt.DropAction.CopyAction)
                    event.accept()
                else:
                    event.ignore()
                return
            event.ignore()
        finally:
            # Always clear highlight after drop
            self.tree_widget.clear_drag_highlight()

    # --- Index version of external dragMove ---
    @staticmethod
    def _detect_package_type(file_path: str) -> str | None:
        """Detect whether a file is a section package, category package, or neither."""
        lower = file_path.lower()
        if lower.endswith(".aitesec"):
            return "section"
        if lower.endswith(".aitecat"):
            return "category"
        if lower.endswith((".aitepack", ".zip")):
            try:
                p = Path(file_path)
                if p.is_file():
                    with zipfile.ZipFile(p, "r") as zf:
                        if "manifest.json" in zf.namelist():
                            data = json.loads(zf.read("manifest.json").decode("utf-8"))
                            pt = data.get("package_type")
                            if pt in ("section", "category"):
                                return pt
            except Exception:
                pass
        return None

    def _handle_external_drag_move_index(self, event, mime) -> None:
        target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
        targets = self._extract_external_link_targets(mime)
        pkg_type = self._detect_package_type(targets[0]) if len(targets) == 1 else None

        if not target_index or not target_index.isValid():
            self._cancel_auto_expand_timer()
            self.tree_widget.clear_drag_highlight()
            if pkg_type in ("section", "category"):
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
                return
            event.ignore()
            return
        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            self._cancel_auto_expand_timer()
            self.tree_widget.clear_drag_highlight()
            event.ignore()
            return
        target_type, _ = ttuple
        valid_drop = False
        if mime.hasFormat(app_config.get_link_mime_type()):
            if target_type == "category":
                self._cancel_auto_expand_timer()
                valid_drop = True
                event.accept()
            elif target_type == "section" and not self.tree_widget.isExpanded(target_index):
                self._arm_auto_expand_timer(target_index)
                event.acceptProposedAction()
                self.tree_widget.set_drag_drop_feedback(
                    target_index, QAbstractItemView.DropIndicatorPosition.OnItem
                )
                return
            else:
                self._cancel_auto_expand_timer()
                event.ignore()
        elif mime.hasFormat(app_config.get_category_mime_type()):
            self._cancel_auto_expand_timer()
            if target_type in ("section", "category"):
                valid_drop = True
                event.accept()
            else:
                event.ignore()
        elif targets:
            if pkg_type in ("section", "category"):
                self._cancel_auto_expand_timer()
                valid_drop = True
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
            elif target_type == "category":
                self._cancel_auto_expand_timer()
                valid_drop = True
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
            elif target_type == "section" and not self.tree_widget.isExpanded(target_index):
                self._arm_auto_expand_timer(target_index)
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
                self.tree_widget.set_drag_drop_feedback(
                    target_index, QAbstractItemView.DropIndicatorPosition.OnItem
                )
                return
            else:
                self._cancel_auto_expand_timer()
                event.ignore()
        else:
            self._cancel_auto_expand_timer()
            event.ignore()
        if valid_drop:
            # Use highlight instead of focus for external drags too
            self.tree_widget.set_drag_drop_feedback(
                target_index, QAbstractItemView.DropIndicatorPosition.OnItem
            )
        else:
            self.tree_widget.clear_drag_highlight()

    def _focus_target_category_index(self, target_index: QModelIndex):
        """Focus on target category (QTreeView)."""
        if target_index and target_index.isValid():
            self.tree_widget.setCurrentIndex(target_index)
            ttuple = get_tree_tuple(target_index, 0)
            if not ttuple:
                return
            target_type, target_id = ttuple
            if target_type == "category":
                try:
                    self.tree_widget.dragFeedback.emit(
                        {
                            "type": "focus_category_request",
                            "category_id": target_id,
                            "title": target_index.data(),
                        }
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to send dragFeedback for category %s: %s",
                        target_id,
                        e,
                    )

    def _focus_target_section_index(self, target_index: QModelIndex):
        """Focus on target section (QTreeView) during category drag."""
        if target_index and target_index.isValid():
            self.tree_widget.setCurrentIndex(target_index)
            ttuple = get_tree_tuple(target_index, 0)
            if not ttuple:
                return
            target_type, target_id = ttuple
            if target_type == "section":
                try:
                    self.tree_widget.dragFeedback.emit(
                        {
                            "type": "focus_section_request",
                            "section_id": target_id,
                            "title": target_index.data(),
                        }
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to send dragFeedback for section %s: %s",
                        target_id,
                        e,
                    )

    # --- Helpers extracted from internal DnD flow ---
    def get_selected_categories(self) -> list[QModelIndex]:
        """Returns list of selected category indexes (column 0).

        Fallback: if multiple selection is empty — uses current index.
        """
        selection_model = getattr(self.tree_widget, "selectionModel", lambda: None)()
        selected_indexes: list[QModelIndex] = []
        if selection_model and hasattr(selection_model, "selectedRows"):
            try:
                selected_indexes = selection_model.selectedRows(0) or []
            except Exception as e:
                logger.debug("Failed to get selected rows: %s", e, exc_info=True)
                selected_indexes = []

        if not selected_indexes:
            cur = self.tree_widget.currentIndex()
            if cur and cur.isValid():
                selected_indexes = [cur]

        category_indices: list[QModelIndex] = []
        for idx in selected_indexes:
            t = get_tree_tuple(idx, 0)
            if t and t[0] == "category":
                category_indices.append(idx)
        # Stable order: by ascending row in current view
        category_indices.sort(key=lambda i: i.row())
        return category_indices

    def get_selected_sections(self) -> list[QModelIndex]:
        """Returns list of selected section indexes (column 0).

        Fallback: if multiple selection is empty — uses current index.
        """
        selection_model = getattr(self.tree_widget, "selectionModel", lambda: None)()
        selected_indexes: list[QModelIndex] = []
        if selection_model and hasattr(selection_model, "selectedRows"):
            try:
                selected_indexes = selection_model.selectedRows(0) or []
            except Exception as e:
                logger.debug("Failed to get selected rows: %s", e, exc_info=True)
                selected_indexes = []

        if not selected_indexes:
            cur = self.tree_widget.currentIndex()
            if cur and cur.isValid():
                selected_indexes = [cur]

        section_indices: list[QModelIndex] = []
        for idx in selected_indexes:
            t = get_tree_tuple(idx, 0)
            if t and t[0] == "section":
                section_indices.append(idx)
        # Stable order: by ascending row in current view
        section_indices.sort(key=lambda i: i.row())
        return section_indices

    def _determine_for_section_target(self, target_index: QModelIndex, model, is_upper_half: bool = False):
        """Compute target data when dropping OnItem over a section."""
        new_section_index = target_index
        new_section_tuple = get_tree_tuple(new_section_index, 0)
        new_section_id = new_section_tuple[1] if new_section_tuple else None
        base_row = model.rowCount(new_section_index)
        parent_for_count = new_section_index
        return new_section_id, base_row, parent_for_count

    def _determine_for_category_target(self, target_index: QModelIndex, model, is_upper_half: bool):
        """Compute target data when dropping around/on a category."""
        parent_index = target_index.parent()
        parent_tuple = get_tree_tuple(parent_index, 0)
        if not (parent_tuple and parent_tuple[0] == "section"):
            raise ValueError("invalid target")
        new_section_id = parent_tuple[1]
        tgt_row = target_index.row()
        if is_upper_half:
            base_row = tgt_row
        else:
            base_row = tgt_row + 1
        parent_for_count = parent_index
        return new_section_id, base_row, parent_for_count

    def determine_target(self, event: QDropEvent) -> tuple[int, int]:
        """Determines target section and base insertion position.

        Returns (section_id, base_row) or raises ValueError for ignored cases.
        """
        target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
        if not target_index or not target_index.isValid():
            raise ValueError("invalid target")

        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            raise ValueError("invalid target")
        target_type, _ = ttuple

        model = self.tree_widget.model()
        rect = self.tree_widget.visualRect(target_index) if hasattr(self.tree_widget, "visualRect") else None
        if isinstance(rect, QRect) and rect.height() > 0:
            pos_y = event.position().toPoint().y() - rect.top()
            is_upper_half = pos_y < (rect.height() / 2)
        else:
            drop_pos = getattr(self.tree_widget, "dropIndicatorPosition", lambda: None)()
            is_upper_half = drop_pos != QAbstractItemView.DropIndicatorPosition.BelowItem

        if target_type == "section":
            new_section_id, base_row, parent_for_count = self._determine_for_section_target(
                target_index, model, is_upper_half
            )
        elif target_type == "category":
            new_section_id, base_row, parent_for_count = self._determine_for_category_target(
                target_index, model, is_upper_half
            )
        else:
            raise ValueError("invalid target")

        # Normalize base_row to [0..rowCount]
        total_rows = (
            model.rowCount(parent_for_count)
            if parent_for_count and parent_for_count.isValid()
            else 0
        )
        if not isinstance(base_row, int):
            base_row = 0
        if base_row < 0:
            base_row = 0
        if base_row > total_rows:
            base_row = total_rows

        if not isinstance(new_section_id, int):
            raise ValueError("invalid target")

        return int(new_section_id), int(base_row)

    def _collect_category_ids(self, category_indices: list[QModelIndex]) -> list[int]:
        """Extract integer category IDs from indexes in stable order."""
        ids: list[int] = []
        for idx in category_indices:
            st = get_tree_tuple(idx, 0)
            if st and isinstance(st[1], int):
                ids.append(int(st[1]))
        return ids

    def _collect_section_ids(self, section_indices: list[QModelIndex]) -> list[int]:
        """Extract integer section IDs from indexes in stable order."""
        ids: list[int] = []
        for idx in section_indices:
            st = get_tree_tuple(idx, 0)
            if st and isinstance(st[1], int):
                ids.append(int(st[1]))
        return ids

    def _schedule_focus_after_category_drop(
        self, first_category_id: int | None, source: str = "tree"
    ) -> None:
        """Schedule focus restoration on the first moved category.

        Args:
            first_category_id: ID of the category to focus on.
            source: Origin of the drop operation ("tree" for internal,
                    "tile" for drops from tiles).
        """
        if not first_category_id:
            return
        try:
            from app.controllers.ui.state.task_scheduler import (
                schedule_selection_restore,
            )

            def _restore_focus():
                try:
                    model = self.tree_widget.model()
                    if model and hasattr(model, 'index_for'):
                        cat_index = model.index_for('category', first_category_id)
                        if cat_index and cat_index.isValid():
                            self.tree_widget.setCurrentIndex(cat_index)
                            from app.utils.ui.focus import get_focus_manager
                            manager = get_focus_manager()
                            manager.set_focus(
                                self.tree_widget,
                                widget_name="structure_tree",
                                origin="user_action",
                            )
                except Exception as e:
                    logger.debug(
                        "Failed to restore focus after %s category drop: %s",
                        source,
                        e,
                    )

            schedule_selection_restore(
                _restore_focus, f"{source}_cat_drop_{first_category_id}"
            )
        except Exception as e:
            logger.debug(
                "Failed to schedule focus after %s category drop: %s", source, e
            )

    def _try_atomic_move(self, category_ids, section_id, base_row):
        """Try atomic command for undoable moves."""
        handler = getattr(self.tree_widget, "move_operations_handler", None)
        if handler:
            try:
                used_command = handler.execute_move_categories_command(
                    [int(i) for i in category_ids], int(section_id), int(base_row)
                )
                if used_command:
                    return len(category_ids)
            except Exception:
                logger.debug(
                    "Atomic move via command failed for %s -> %s",
                    category_ids,
                    section_id,
                    exc_info=True,
                )
        return None

    def move_categories(
        self, category_ids: list[int], section_id: int, base_row: int
    ) -> int:
        """Moves list of categories to specified section and position.

        Uses atomic command for undoable moves. Returns number of
        actually moved items.
        """
        if not category_ids:
            return 0

        result = self._try_atomic_move(category_ids, section_id, base_row)
        if result is not None:
            return result

        logger.warning(
            "Failed to move categories %s to section %s: command not available or failed",
            category_ids,
            section_id,
        )
        return 0

    def _handle_internal_drop_event_index(self, event) -> None:
        """Internal drop for QTreeView: moving categories between/within sections or reordering sections.

        Simplified to orchestration: selection, target calculation, move execution,
        basic error handling and signals.
        """
        section_indices = self.get_selected_sections()
        if section_indices:
            self._handle_section_reorder_index(event, section_indices)
            return

        # 1) Выбор категорий
        category_indices = self.get_selected_categories()
        if not category_indices:
            try:
                self.tree_widget.invalidDrop.emit("Only categories can be moved")
            except Exception as e:
                logger.debug("Failed to emit invalidDrop signal: %s", e, exc_info=True)
            event.ignore()
            return

        # 2) Расчёт целевого раздела и позиции
        try:
            new_section_id, base_row = self.determine_target(event)
        except ValueError:
            event.ignore()
            return

        # 3) Формирование списка ID в стабильном порядке
        ids: list[int] = self._collect_category_ids(category_indices)

        if not ids:
            event.ignore()
            return

        # 4) Перенос
        moved_count = self.move_categories(ids, int(new_section_id), int(base_row))

        # 5) Результат
        if moved_count > 0:
            event.accept()
            # Set focus on first moved category in new location
            first_category_id = ids[0] if ids else None
            self._schedule_focus_after_category_drop(first_category_id)
        else:
            try:
                self.tree_widget.invalidDrop.emit("Invalid move operation")
            except Exception as e:
                logger.debug("Failed to emit invalidDrop signal: %s", e, exc_info=True)
            event.ignore()

    def _handle_section_reorder_index(
        self, event: QDropEvent, section_indices: list[QModelIndex]
    ) -> None:
        """Handle internal drag & drop reordering of sections."""
        target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
        model = self.tree_widget.model()
        if not model:
            event.ignore()
            return

        total_sections = model.rowCount(QModelIndex())
        if not target_index or not target_index.isValid():
            target_row = total_sections
        else:
            ttuple = get_tree_tuple(target_index, 0)
            if not ttuple or ttuple[0] != "section":
                event.ignore()
                return
            rect = self.tree_widget.visualRect(target_index) if hasattr(self.tree_widget, "visualRect") else None
            if isinstance(rect, QRect) and rect.height() > 0:
                pos_y = event.position().toPoint().y() - rect.top()
                is_lower_half = pos_y >= (rect.height() / 2)
            else:
                drop_pos = getattr(self.tree_widget, "dropIndicatorPosition", lambda: None)()
                is_lower_half = drop_pos == QAbstractItemView.DropIndicatorPosition.BelowItem
            if is_lower_half:
                target_row = target_index.row() + 1
            else:
                target_row = target_index.row()

        target_row = max(0, min(target_row, total_sections))
        section_ids = self._collect_section_ids(section_indices)
        if not section_ids:
            event.ignore()
            return

        handler = getattr(self.tree_widget, "move_operations_handler", None)
        if handler and hasattr(handler, "execute_reorder_sections_command"):
            if handler.execute_reorder_sections_command(section_ids, target_row):
                event.accept()
                return
        event.ignore()

    def _handle_category_drop_index(self, mime, target_index: QModelIndex) -> bool:
        """Moving one or multiple categories (from tiles) to section for QTreeView.

        Returns:
            bool: True if move request was executed, False otherwise.
        """
        ids = MimeDataParser.extract_item_ids(mime, app_config.get_category_mime_type())
        if not ids:
            logger.warning("Failed to extract category ID from MIME data")
            return False
        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            return False
        model = getattr(self.tree_widget, "model", lambda: None)()
        if ttuple[0] == "section" and isinstance(ttuple[1], int):
            section_id = int(ttuple[1])
            base_row = (
                model.rowCount(target_index)
                if model and target_index and target_index.isValid()
                else 0
            )
        elif ttuple[0] == "category":
            parent_index = target_index.parent()
            parent_tuple = get_tree_tuple(parent_index, 0)
            if not (parent_tuple and parent_tuple[0] == "section" and isinstance(parent_tuple[1], int)):
                return False
            section_id = int(parent_tuple[1])
            base_row = (
                model.rowCount(parent_index)
                if model and parent_index and parent_index.isValid()
                else 0
            )
        else:
            return False
        try:
            moved_count = self.move_categories(
                [int(cid) for cid in ids if isinstance(cid, int)],
                section_id,
                int(base_row),
            )
        except Exception as exc:
            logger.warning(
                "Failed to move categories %s to section %s: %s", ids, section_id, exc
            )
            moved_count = 0
        if moved_count > 1:
            logger.info("Moved categories: %s to section %s", moved_count, section_id)

        # Set focus on first moved category from tiles
        if moved_count > 0 and ids:
            first_category_id = ids[0] if isinstance(ids[0], int) else None
            self._schedule_focus_after_category_drop(first_category_id, source="tile")

        return moved_count > 0

    def _handle_link_drop_index(self, mime, target_index: QModelIndex) -> bool:
        """Moving links to category (QTreeView).

        Returns:
            bool: True if move was requested, False otherwise.
        """
        ttuple = get_tree_tuple(target_index, 0)
        if not (ttuple and ttuple[0] == "category"):
            return False
        link_ids = self._extract_link_ids_from_mime(mime)
        if not link_ids:
            return False
        new_category_id = ttuple[1]
        if not isinstance(new_category_id, int):
            return False
        try:
            self.tree_widget.move_operations_handler.execute_move_links_command(
                link_ids, new_category_id
            )
        except Exception:
            logger.warning(
                "Failed to schedule move of links %s to category %s",
                link_ids,
                new_category_id,
                exc_info=True,
            )
            return False
        try:
            self.tree_widget.itemsMoved.emit(
                {
                    "type": "links_to_category",
                    "link_ids": link_ids,
                    "category_id": new_category_id,
                }
            )
        except Exception:
            logger.debug(
                "Failed to emit itemsMoved after moving links %s", link_ids, exc_info=True
            )

        # Focus is handled by MoveLinksCommand._refresh_ui
        return True

    def _handle_external_url_drop_index(self, mime, target_index: QModelIndex) -> bool:
        """Request creating links or importing packages from external drops."""
        targets = self._extract_external_link_targets(mime)
        if not targets:
            return False

        pkg_type = self._detect_package_type(targets[0]) if len(targets) == 1 else None
        ttuple = get_tree_tuple(target_index, 0) if (target_index and target_index.isValid()) else None

        # Smart Routing for share packages (.aitesec, .aitecat)
        if pkg_type in ("section", "category"):
            item_type = ttuple[0] if ttuple else None
            item_id = int(ttuple[1]) if ttuple else None
            self.tree_widget.externalLinkDropped.emit(
                {
                    "type": "external_link_to_category",
                    "item_type": item_type,
                    "item_id": item_id,
                    "category_id": None,
                    "targets": targets,
                    "urls": targets,
                    "title": target_index.data() if (target_index and target_index.isValid()) else "",
                }
            )
            return True

        if not (ttuple and ttuple[0] in ("category", "section") and isinstance(ttuple[1], int)):
            return False
        try:
            self.tree_widget.externalLinkDropped.emit(
                {
                    "type": "external_link_to_category",
                    "item_type": ttuple[0],
                    "item_id": int(ttuple[1]),
                    "category_id": int(ttuple[1]) if ttuple[0] == "category" else None,
                    "targets": targets,
                    "urls": targets,
                    "title": target_index.data(),
                }
            )
        except Exception:
            logger.warning(
                "Failed to emit external URL drop for %s %s",
                ttuple[0],
                ttuple[1],
                exc_info=True,
            )
            return False
        return True

    def _extract_external_web_urls(self, mime) -> list[str]:
        """Extract http(s) URLs from external drag MIME data."""
        return MimeDataParser.extract_external_web_urls(mime)

    def _extract_external_link_targets(self, mime) -> list[str]:
        """Extract web URLs and local paths from external drag MIME data."""
        return MimeDataParser.extract_external_link_targets(mime)

    def _extract_link_ids_from_mime(self, mime) -> list[int]:
        """Extracts link IDs from MIME data."""
        ids = MimeDataParser.extract_item_ids(mime, app_config.get_link_mime_type())
        if not ids:
            logger.warning("Failed to extract link IDs from MIME data")
        return ids

    # Index version of DnD validity check (QTreeView)
    def _is_valid_drop_index(
        self, source_index: QModelIndex, event: QDropEvent
    ) -> bool:
        stuple = get_tree_tuple(source_index, 0)
        if not stuple:
            return False
        source_type, _ = stuple
        target_index = self.tree_widget.indexAt(event.position().toPoint())
        if source_type == "section":
            if not target_index or not target_index.isValid():
                return True
            ttuple = get_tree_tuple(target_index, 0)
            if not ttuple:
                return False
            target_type, _ = ttuple
            return target_type == "section"
        elif source_type == "category":
            if not target_index or not target_index.isValid():
                return False
            ttuple = get_tree_tuple(target_index, 0)
            if not ttuple:
                return False
            target_type, _ = ttuple
            if target_type in ("section", "category"):
                return True
            return False
        return False
