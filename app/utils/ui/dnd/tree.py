# app/utils/dnd/tree.py

"""Centralized drag & drop handler for structure tree.

Supports `StructureTreeView` (QTreeView) with model and indexes.
"""

import logging

from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QAbstractItemView

from app.config_data import app_config
from app.utils.ui.dnd.mime import MimeDataParser
from app.utils.ui.qt.roles import get_tree_tuple

from .base import TreeHandlerBase

logger = logging.getLogger(__name__)


class DragDropHandler(TreeHandlerBase):
    """Drag & drop operations handler in structure tree."""

    def accepts_mime_type(self, mime) -> bool:
        """Checks if widget accepts given MIME type."""
        return mime.hasFormat(app_config.get_link_mime_type()) or mime.hasFormat(
            app_config.get_category_mime_type()
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
                target_index = self._resolve_internal_target_index(event)
                self.tree_widget.set_drag_highlight_index(target_index)
                event.accept()
            else:
                self.tree_widget.clear_drag_highlight()
                event.ignore()
        else:
            self._handle_external_drag_move_index(event, mime)
        return

    def _resolve_internal_target_index(self, event: QDropEvent) -> QModelIndex | None:
        """Resolve which index should be highlighted during internal drag."""
        try:
            target_index: QModelIndex = self.tree_widget.indexAt(
                event.position().toPoint()
            )
        except Exception:
            return None

        if not target_index or not target_index.isValid():
            return None

        drop_pos = self.tree_widget.dropIndicatorPosition()
        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            return None

        target_type, _ = ttuple

        # OnItem drops: highlight the target itself
        if drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            return target_index if target_type in ("section", "category") else None

        # Above/Below drops on categories: highlight parent section
        if target_type == "category":
            parent_index = target_index.parent()
            if parent_index.isValid():
                parent_tuple = get_tree_tuple(parent_index, 0)
                if parent_tuple and parent_tuple[0] == "section":
                    return parent_index

        return None

    def _update_internal_drag_focus(self, event: QDropEvent) -> None:
        """Ensure target rows are highlighted during internal drags."""
        try:
            target_index: QModelIndex = self.tree_widget.indexAt(
                event.position().toPoint()
            )
        except Exception:
            return

        if not target_index or not target_index.isValid():
            return

        drop_pos = self.tree_widget.dropIndicatorPosition()
        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            return

        target_type, _ = ttuple

        if drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            if target_type == "section":
                self._focus_target_section_index(target_index)
            elif target_type == "category":
                self._focus_target_category_index(target_index)
            return

        if target_type == "category":
            parent_index = target_index.parent()
            parent_tuple = get_tree_tuple(parent_index, 0)
            if parent_tuple and parent_tuple[0] == "section":
                self._focus_target_section_index(parent_index)

    def handle_drag_leave_event(self, event) -> None:
        """Handle drag leave event."""
        self.tree_widget.clear_drag_highlight()
        event.accept()

    def handle_drop_event(self, event) -> None:
        """Main drop event handler."""
        try:
            mime = event.mimeData()

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
            if event.source() == self.tree_widget:
                self._handle_internal_drop_event_index(event)
                return
            event.ignore()
        finally:
            # Always clear highlight after drop
            self.tree_widget.clear_drag_highlight()

    # --- Index version of external dragMove ---
    def _handle_external_drag_move_index(self, event, mime) -> None:
        target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
        if not target_index or not target_index.isValid():
            event.ignore()
            return
        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            event.ignore()
            return
        target_type, _ = ttuple
        drop_pos = self.tree_widget.dropIndicatorPosition()
        valid_drop = False
        if mime.hasFormat(app_config.get_link_mime_type()):
            if target_type == "category":
                valid_drop = True
                event.accept()
            else:
                event.ignore()
        elif mime.hasFormat(app_config.get_category_mime_type()):
            if target_type == "section":
                if drop_pos in (
                    QAbstractItemView.DropIndicatorPosition.OnItem,
                    QAbstractItemView.DropIndicatorPosition.AboveItem,
                    QAbstractItemView.DropIndicatorPosition.BelowItem,
                ):
                    valid_drop = True
                    event.accept()
                else:
                    event.ignore()
            else:
                event.ignore()
        else:
            event.ignore()
        if valid_drop:
            # Use highlight instead of focus for external drags too
            self.tree_widget.set_drag_highlight_index(target_index)
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
            except Exception:
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

    def _determine_for_section_target(self, target_index: QModelIndex, model, drop_pos):
        """Compute target data when dropping OnItem over a section."""
        new_section_index = target_index
        new_section_tuple = get_tree_tuple(new_section_index, 0)
        new_section_id = new_section_tuple[1] if new_section_tuple else None
        base_row = model.rowCount(new_section_index)
        parent_for_count = new_section_index
        return new_section_id, base_row, parent_for_count

    def _determine_for_category_target(self, target_index: QModelIndex, model, drop_pos):
        """Compute target data when dropping around/on a category."""
        parent_index = target_index.parent()
        parent_tuple = get_tree_tuple(parent_index, 0)
        if not (parent_tuple and parent_tuple[0] == "section"):
            raise ValueError("invalid target")
        new_section_id = parent_tuple[1]
        tgt_row = target_index.row()
        if drop_pos == QAbstractItemView.DropIndicatorPosition.AboveItem:
            base_row = tgt_row
        elif drop_pos == QAbstractItemView.DropIndicatorPosition.BelowItem:
            base_row = tgt_row + 1
        elif drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
            base_row = model.rowCount(parent_index)
        else:
            raise ValueError("invalid target")
        parent_for_count = parent_index
        return new_section_id, base_row, parent_for_count

    def determine_target(self, event: QDropEvent) -> tuple[int, int]:
        """Determines target section and base insertion position.

        Returns (section_id, base_row) or raises ValueError for ignored cases.
        """
        target_index: QModelIndex = self.tree_widget.indexAt(event.position().toPoint())
        drop_pos = self.tree_widget.dropIndicatorPosition()
        if not target_index or not target_index.isValid():
            raise ValueError("invalid target")

        ttuple = get_tree_tuple(target_index, 0)
        if not ttuple:
            raise ValueError("invalid target")
        target_type, _ = ttuple

        model = self.tree_widget.model()

        if target_type == "section" and drop_pos in (
            QAbstractItemView.DropIndicatorPosition.OnItem,
            QAbstractItemView.DropIndicatorPosition.AboveItem,
            QAbstractItemView.DropIndicatorPosition.BelowItem,
        ):
            new_section_id, base_row, parent_for_count = self._determine_for_section_target(
                target_index, model, drop_pos
            )
        elif target_type == "category":
            new_section_id, base_row, parent_for_count = self._determine_for_category_target(
                target_index, model, drop_pos
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

    def _begin_batch_operation(self, structure_business):
        """Begin batch operation if supported."""
        if structure_business and hasattr(structure_business, "begin_batch"):
            try:
                structure_business.begin_batch()
                return True
            except Exception:
                pass
        return False

    def _move_single_category(
        self, cid, section_id, target_row, structure_business, model
    ):
        """Move single category using business logic or model."""
        if structure_business:
            try:
                result = structure_business.move_categories_batch(
                    [int(cid)], int(section_id), target_row
                )
                if isinstance(result, list):
                    return bool(result)
                elif isinstance(result, tuple) and result:
                    return True
            except Exception:
                pass

        try:
            return hasattr(model, "move_category") and model.move_category(
                int(cid), int(section_id), target_row
            )
        except Exception:
            return False

    def _emit_items_moved(self, cid, section_id, target_row):
        """Emit itemsMoved signal."""
        try:
            self.tree_widget.itemsMoved.emit(
                {
                    "type": "internal_move",
                    "source_type": "category",
                    "category_id": int(cid),
                    "section_id": int(section_id),
                    "new_row": target_row,
                }
            )
        except Exception:
            pass

    def _finalize_batch(self, batch_started, structure_business, touched_sections):
        """Finalize batch operation."""
        if batch_started:
            try:
                if touched_sections:
                    structure_business.event_service.replace_touched_sections(
                        touched_sections
                    )
                structure_business.end_batch()
            except Exception:
                pass
        elif structure_business and touched_sections:
            try:
                structure_business.event_service.replace_touched_sections(
                    touched_sections
                )
            except Exception:
                pass

    def move_categories(
        self, category_ids: list[int], section_id: int, base_row: int
    ) -> int:
        """Moves list of categories to specified section and position.

        Attempts to use atomic command for multiple items.
        Returns number of actually moved items. In single path
        generates itemsMoved signal for each successful move.
        """
        if not category_ids:
            return 0

        atomic_result = self._try_atomic_move(category_ids, section_id, base_row)
        if atomic_result is not None:
            return atomic_result

        model = self.tree_widget.model()
        main_win = self.tree_widget.window()
        structure_business = getattr(main_win, "structure_business", None)

        batch_started = self._begin_batch_operation(structure_business)
        moved_count = 0
        insert_offset = 0
        touched_sections: set[int] = set()

        for cid in category_ids:
            if not isinstance(cid, int):
                continue
            target_row = int(base_row + insert_offset)

            moved = self._move_single_category(
                cid, section_id, target_row, structure_business, model
            )
            if moved:
                moved_count += 1
                insert_offset += 1
                touched_sections.add(int(section_id))
                self._emit_items_moved(cid, section_id, target_row)

        self._finalize_batch(batch_started, structure_business, touched_sections)

        return moved_count

    def _handle_internal_drop_event_index(self, event) -> None:
        """Internal drop for QTreeView: moving categories between/within sections.

        Simplified to orchestration: selection, target calculation, move execution,
        basic error handling and signals.
        """
        # 1) Выбор категорий
        category_indices = self.get_selected_categories()
        if not category_indices:
            try:
                self.tree_widget.invalidDrop.emit("Only categories can be moved")
            except Exception:
                pass
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
            except Exception:
                pass
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
        if not (ttuple and ttuple[0] == "section" and isinstance(ttuple[1], int)):
            return False
        section_id = int(ttuple[1])
        model = getattr(self.tree_widget, "model", lambda: None)()
        base_row = (
            model.rowCount(target_index)
            if model and target_index and target_index.isValid()
            else 0
        )
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
        
        # Set focus on first moved link after table is populated
        if link_ids:
            first_link_id = link_ids[0] if link_ids else None
            if first_link_id:
                self._schedule_focus_after_table_update(first_link_id)
        return True
    
    def _schedule_focus_after_table_update(self, link_id: int) -> None:
        """Schedule focus on link after table_populated signal."""
        try:
            main_win = self.tree_widget.window()
            if not main_win:
                return
            
            # Get the target category from the last drop operation
            # The category should already be selected by the command execution
            
            table = getattr(main_win, 'links_table', None)
            if table and hasattr(table, 'table_populated'):
                def _on_populated():
                    try:
                        if hasattr(main_win, 'links_actions'):
                            main_win.links_actions.focus_on_link(link_id)
                        # Disconnect after first call
                        try:
                            table.table_populated.disconnect(_on_populated)
                        except Exception:
                            pass
                    except Exception as e:
                        logger.debug("Failed to focus on link %s: %s", link_id, e)
                
                table.table_populated.connect(_on_populated)
        except Exception as e:
            logger.debug("Failed to schedule focus after table update: %s", e)
        
        return True

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
        drop_pos = self.tree_widget.dropIndicatorPosition()
        if source_type == "section":
            # Sections not supported for moving yet
            return False
        elif source_type == "category":
            if not target_index or not target_index.isValid():
                return False
            ttuple = get_tree_tuple(target_index, 0)
            if not ttuple:
                return False
            target_type, _ = ttuple
            if drop_pos == QAbstractItemView.DropIndicatorPosition.OnItem:
                return target_type in ("section", "category")
            if target_type == "section" and drop_pos in (
                QAbstractItemView.DropIndicatorPosition.AboveItem,
                QAbstractItemView.DropIndicatorPosition.BelowItem,
            ):
                return True
            else:
                # Between elements only allowed between categories of same section
                if target_type != "category":
                    return False
                # Same parent
                return source_index.parent() == target_index.parent()
        return False
