"""Base widgets for reuse within the AITE UI."""

import logging
from collections.abc import Iterable
from typing import Any, Callable, Optional

from PyQt6.QtCore import QCoreApplication, QEvent, QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QDropEvent, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLayout,
    QSizePolicy,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.utils.ui.dnd.link import (
    extract_source_rows_from_mime as dnd_extract_source_rows,
)
from app.utils.ui.dnd.link import (
    get_current_order as dnd_get_current_order,
)
from app.utils.ui.dnd.link import (
    get_selected_rows as dnd_get_selected_rows,
)
from app.utils.ui.dnd.link import (
    move_rows_visually as dnd_move_rows_visually,
)
from app.utils.ui.dnd.mime import MimeDataParser, get_link_mime
from app.utils.ui.dnd.pixmap import create_default_pixmap, create_text_pixmap
from app.utils.ui.icon.icon_resolver import resolve_icon_path
from app.views.widgets.protocols import LinksBusinessProtocol

logger = logging.getLogger(__name__)


class BasePanelWidget(QWidget):
    """Base panel widget with a colored ``QFrame`` container and layout."""

    def __init__(self) -> None:
        super().__init__()
        self.bg_frame = QFrame(self)
        self.panel_layout = QHBoxLayout(self.bg_frame)
        self.panel_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.panel_layout.setContentsMargins(0, 0, 0, 0)
        self.panel_layout.setSpacing(app_config.ui.get_top_bar_buttons_spacing())
        self.panel_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.bg_frame)


# DEPRECATED: Backward compatibility wrapper for tests
# Use ``BaseTopPanelWidget`` directly in new code


class BaseLinksPanelWidget:
    """Deprecated shim that delegates to ``BaseTopPanelWidget``.

    The class exists solely for backward compatibility with legacy tests.
    All runtime behavior lives in ``BaseTopPanelWidget`` now.

    Migration guide:
    - Replace ``BaseLinksPanelWidget`` with ``BaseTopPanelWidget``
    - Provide the configuration object via dependency injection
    - Supply ``batch_size`` for asynchronous population
    """

    # Backward compatible signal (parent uses actionRequested)
    linkClicked: pyqtSignal = pyqtSignal(object)

    def __init__(
        self,
        main_window: Optional[QWidget] = None,
        links_business: LinksBusinessProtocol = None,
        batch_size: int = 50,
    ) -> None:
        # Import locally to avoid circular import
        from app.views.widgets.base.base_panel_widgets import BaseTopPanelWidget

        # Call unified base with specified batch_size
        BaseTopPanelWidget.__init__(
            self, main_window=main_window, config=None, batch_size=batch_size
        )

        # Store for backward compatibility with older code/tests
        self.links_business = links_business

    # Compatibility property: tests expect ``main_window`` while parent uses ``_main_window``
    @property
    def main_window(self):
        """Backward compatible accessor for main_window."""
        return self._main_window

    @main_window.setter
    def main_window(self, value):
        """Backward compatible setter for main_window."""
        self._main_window = value

    # Compatibility method: tests call ``_populate_batch()``, parent uses ``_populate_batched()``
    def _populate_batch(self) -> None:
        """Backward compatible wrapper for _process_batch()."""
        if not hasattr(self, "_pending_items") or not self._pending_items:
            self._finish_populate()
            return

        # Process one batch using parent logic
        self._process_batch()

    def _populate_panel(
        self,
        items: list[dict[str, Any]],
        create_button_func: Callable[[dict[str, Any]], Optional[QToolButton]],
    ) -> None:
        """Override to keep backward compatible logging for tests."""
        self._clear_layout()

        # Use parent logic for consistency
        if self._batch_size > 0:
            self._pending_items = list(items)
            self._create_button_func = create_button_func
            self.setUpdatesEnabled(False)
            self._populate_batch()
        else:
            # Synchronous mode – call parent logic directly
            super()._populate_panel(items, create_button_func)

    def _process_batch(self) -> None:
        """Process one batch with backward compatible logging."""
        if not self._pending_items:
            self._finish_populate()
            return

        # Use configurable batch_size instead of a hardcoded value
        batch_size = app_config.ui.get("panel_batch_size", 50)
        batch = self._pending_items[:batch_size]
        self._pending_items = self._pending_items[batch_size:]

        for _i, link in enumerate(batch):
            try:
                button = self._create_button_func(link)
            except (AttributeError, KeyError, ValueError, TypeError) as expected:
                # Catch specific exceptions instead of broad Exception
                logger.debug(
                    "Failed to create button for link %s: %s",
                    link.get("id", "unknown"),
                    expected,
                )
                continue

            if button is not None:
                self.panel_layout.addWidget(button)
            else:
                logger.debug(
                    "create_button_func returned None for: %s",
                    link.get("name", "Unknown"),
                )

        # Schedule next batch
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(0, self._populate_batch)

    def _finish_populate(self) -> None:
        """Finish population with backward compatible logging."""
        try:
            if self.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding:
                self.panel_layout.addStretch()
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to add stretch to layout: %s", e)

        self.setUpdatesEnabled(True)

        try:
            self.updateGeometry()
        except (AttributeError, RuntimeError) as e:
            # Catch specific exceptions instead of broad Exception
            logger.debug(
                "BaseLinksPanelWidget: updateGeometry failed after populate: %s",
                e,
                exc_info=True,
            )

        self._pending_items = []
        self._create_button_func = None

    def _handle_link_click_base(self, link_info: Any) -> None:
        """Emit linkClicked signal (backward compatible)."""
        logger.debug("[BaseLinksPanelWidget] link clicked: %s", link_info)
        try:
            self.linkClicked.emit(link_info)
        except (TypeError, RuntimeError):
            try:
                link_ctx = {
                    "id": getattr(link_info, "id", None)
                    or (link_info.get("id") if isinstance(link_info, dict) else None),
                    "name": getattr(link_info, "name", None)
                    or (link_info.get("name") if isinstance(link_info, dict) else None),
                    "url": getattr(link_info, "url", None)
                    or (link_info.get("url") if isinstance(link_info, dict) else None),
                }
            except Exception:
                link_ctx = {"raw": repr(link_info)}
            logger.exception("Error while emitting linkClicked; context=%s", link_ctx)
            raise

    def _find_icon(self, icon_path: str) -> str:
        """Backward compatible shim for tests that patch resolve_icon_path.

        Tests expect to patch 'app.views.widgets.base.base_widgets.resolve_icon_path'.
        This method delegates to the parent but uses the local resolve_icon_path import.
        """
        if not icon_path:
            return str(self._get_default_icon_path())
        try:
            resolved = resolve_icon_path(icon_path)
            return resolved or str(self._get_default_icon_path())
        except (OSError, FileNotFoundError, PermissionError) as e:
            logger.warning("Failed to resolve icon path '%s': %s", icon_path, e)
            return str(self._get_default_icon_path())
        except (AttributeError, ValueError, TypeError) as e:
            # Catch specific exceptions for different error types
            logger.warning("Error while resolving icon '%s': %s", icon_path, e)
            return str(self._get_default_icon_path())


class BaseDragDropTableWidget(QTableView):
    """Base ``QTableView`` with drag-and-drop support."""

    items_reordered: pyqtSignal = pyqtSignal(list)

    MIME_TYPE = get_link_mime()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._sorting_enabled_before_drag = True
        self._sorting_disabled_for_drag: bool = False
        self._setup_drag_drop()

    def _setup_drag_drop(self) -> None:
        """Configure drag-and-drop parameters."""
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        try:
            self.viewport().setAcceptDrops(True)
            self.viewport().installEventFilter(self)
        except (AttributeError, RuntimeError) as e:
            logger.warning("_setup_drag_drop: viewport DnD setup failed: %s", e)
            raise
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        try:
            self.setDragDropOverwriteMode(False)
        except (AttributeError, RuntimeError) as e:
            logger.warning(
                "_setup_drag_drop: setDragDropOverwriteMode unsupported: %s", e
            )
        try:
            self.setDefaultDropAction(Qt.DropAction.MoveAction)
        except (AttributeError, RuntimeError) as e:
            logger.warning("_setup_drag_drop: setDefaultDropAction unsupported: %s", e)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        try:
            self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        except (AttributeError, RuntimeError) as e:
            logger.warning("_setup_drag_drop: setSelectionMode unsupported: %s", e)
        try:
            self.setDropIndicatorShown(True)
        except (AttributeError, RuntimeError) as e:
            logger.warning("_setup_drag_drop: setDropIndicatorShown unsupported: %s", e)
        self.setSortingEnabled(True)
        self.setTabKeyNavigation(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:
        """Force handling of DnD events arriving on ``viewport()``."""
        if obj is self.viewport():
            et = event.type()
            if et == QEvent.Type.DragEnter:
                self.dragEnterEvent(event)
                return event.isAccepted()
            if et == QEvent.Type.DragMove:
                self.dragMoveEvent(event)
                return event.isAccepted()
            if et == QEvent.Type.DragLeave:
                self.dragLeaveEvent(event)
                return True
            if et == QEvent.Type.Drop:
                self.dropEvent(event)
                return event.isAccepted()
        return super().eventFilter(obj, event)

    def mimeTypes(self) -> list[str]:
        """Return supported MIME types."""
        return [self.MIME_TYPE]

    def mimeData(self, items: Iterable[QModelIndex]) -> Optional[QDrag]:
        """Create MIME data for drag operations.

        ``items`` may be a list of ``QModelIndex`` objects.
        """
        try:
            item_ids = self._extract_item_ids_from_items(items)
            return MimeDataParser.create_mime_data(item_ids, self.MIME_TYPE)
        except (AttributeError, ValueError, TypeError) as e:
            # Catch specific exceptions when creating MIME data
            logger.warning("Failed to create MIME data: %s", e)
            return None

    def _extract_item_ids_from_items(self, items: Iterable[QModelIndex]) -> list[int]:
        """Extract item IDs from the selected indexes."""
        raise NotImplementedError(
            "Subclasses must implement _extract_item_ids_from_items"
        )

    def startDrag(self, supportedActions: Qt.DropAction) -> None:
        """Start a drag operation."""
        sm = self.selectionModel()
        if not sm:
            return
        items = sm.selectedIndexes()
        if not items:
            return

        self._sorting_enabled_before_drag = self.isSortingEnabled()
        if self._sorting_enabled_before_drag:
            self.setSortingEnabled(False)

        drag = QDrag(self)
        mime = self.mimeData(items)
        if mime is None:
            if self._sorting_enabled_before_drag:
                self.setSortingEnabled(True)
            return

        drag.setMimeData(mime)

        pixmap = self._create_drag_pixmap(items)
        if pixmap:
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())

        # Force move behavior
        try:
            drag.exec(Qt.DropAction.MoveAction)
        except Exception:
            drag.exec(supportedActions)

        # Do not re-enable sorting yet. ``dropEvent()`` decides whether sorting stays off
        # (manual ordering visible) or reverts to the previous state on failure.

    def dragEnterEvent(self, event: QDropEvent) -> None:
        """Handle the beginning of a drag operation."""
        if not self._sorting_disabled_for_drag:
            self._sorting_disabled_for_drag = self.isSortingEnabled()
            if self._sorting_disabled_for_drag:
                self.setSortingEnabled(False)
        try:
            if (
                self._is_internal_drop(event)
                and event.mimeData()
                and event.mimeData().hasFormat(self.MIME_TYPE)
            ):
                logger.debug("[DROP] dragEnterEvent: accept internal with our MIME")
                event.acceptProposedAction()
                return
        except Exception as exc:
            try:
                md = event.mimeData() if hasattr(event, "mimeData") else None
                formats = list(md.formats()) if md and hasattr(md, "formats") else []
                has_our_mime = bool(
                    md and hasattr(md, "hasFormat") and md.hasFormat(self.MIME_TYPE)
                )
                pos = getattr(event, "position", None)
                pos_tuple = (int(pos.x()), int(pos.y())) if pos is not None else None
                proposed = getattr(event, "proposedAction", None)
                proposed_val = proposed() if callable(proposed) else proposed
            except Exception as info_exc:
                formats, has_our_mime, pos_tuple, proposed_val = [], False, None, None
                logger.debug(
                    "[DROP] dragEnterEvent: failed to collect diagnostic info: %s",
                    info_exc,
                )
            logger.warning(
                "[DROP] dragEnterEvent: handler error: %s; mime_formats=%r has_our_mime=%s pos=%r proposed=%r",
                exc,
                formats,
                has_our_mime,
                pos_tuple,
                proposed_val,
            )
            event.ignore()
            raise
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDropEvent) -> None:
        """Support drag movements within the widget."""
        try:
            if (
                self._is_internal_drop(event)
                and event.mimeData()
                and event.mimeData().hasFormat(self.MIME_TYPE)
            ):
                logger.debug("[DROP] dragMoveEvent: accept internal with our MIME")
                event.acceptProposedAction()
                return
        except Exception as exc:
            try:
                md = event.mimeData() if hasattr(event, "mimeData") else None
                formats = list(md.formats()) if md and hasattr(md, "formats") else []
                has_our_mime = bool(
                    md and hasattr(md, "hasFormat") and md.hasFormat(self.MIME_TYPE)
                )
                pos = getattr(event, "position", None)
                pos_tuple = (int(pos.x()), int(pos.y())) if pos is not None else None
                proposed = getattr(event, "proposedAction", None)
                proposed_val = proposed() if callable(proposed) else proposed
            except Exception as info_exc:
                formats, has_our_mime, pos_tuple, proposed_val = [], False, None, None
                logger.debug(
                    "[DROP] dragMoveEvent: failed to collect diagnostic info: %s",
                    info_exc,
                )
            logger.warning(
                "[DROP] dragMoveEvent: handler error: %s; mime_formats=%r has_our_mime=%s pos=%r proposed=%r",
                exc,
                formats,
                has_our_mime,
                pos_tuple,
                proposed_val,
            )
            event.ignore()
            raise
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event: QEvent) -> None:
        """Handle leaving the drag zone."""
        if self._sorting_disabled_for_drag:
            self.setSortingEnabled(True)
            self._sorting_disabled_for_drag = False
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop for internal row reordering."""
        if not self._is_internal_drop(event):
            super().dropEvent(event)
            return

        source_rows, target_row = self._get_drop_positions(event)
        logger.debug(
            "[DROP] dropEvent: source_rows=%s, target_row=%s", source_rows, target_row
        )
        if not self._is_valid_internal_drop(source_rows, target_row):
            logger.debug("[DROP] dropEvent: invalid internal drop, ignoring")
            event.ignore()
            return

        moved = False
        try:
            self._move_rows_visually(source_rows, target_row)
            try:
                event.setDropAction(Qt.DropAction.MoveAction)
            except Exception:
                pass
            event.acceptProposedAction()
            moved = True

            ids_in_order = self._get_current_order()
            if ids_in_order:
                logger.debug(
                    "[DROP] dropEvent: items_reordered -> %s ids", len(ids_in_order)
                )
                self.items_reordered.emit(ids_in_order)
            else:
                logger.warning("[DROP] Failed to collect IDs after move")

        except Exception as e:
            logger.error("[DROP] Error while moving rows: %s", e)
            event.ignore()
        finally:
            if not moved and self._sorting_disabled_for_drag:
                self.setSortingEnabled(True)
            if hasattr(self, "horizontalHeader"):
                try:
                    if moved:
                        self.horizontalHeader().setSortIndicatorShown(False)
                except (AttributeError, RuntimeError) as e:
                    # Catch specific exceptions when setting sort indicator
                    logger.debug("Failed to set sort indicator: %s", e)
            self._sorting_disabled_for_drag = False

    def _is_internal_drop(self, event: QDropEvent) -> bool:
        """Return whether the drop originates from this view."""
        src = event.source()
        try:
            return src is self or src is self.viewport()
        except (AttributeError, RuntimeError) as e:
            # Catch specific exceptions when checking drop source
            logger.debug("Failed to determine drop source: %s", e)
            return False

    def _get_selected_rows(self) -> list[int]:
        """Return the list of selected rows."""
        return dnd_get_selected_rows(self)

    def _extract_source_rows_from_mime(self, event: QDropEvent) -> list[int]:
        """Extract source row numbers from MIME data."""
        return dnd_extract_source_rows(self, event, self.MIME_TYPE)

    def _extract_id_from_index(self, index: QModelIndex) -> int:
        """Return the item ID from the model at the given index (``UserRole``).

        The model must store either a dict with an ``id`` key or an integer identifier
        in the first column's ``UserRole``.
        """
        if not index or not index.isValid():
            raise ValueError("Invalid model index")
        data = index.data(Qt.ItemDataRole.UserRole)
        if data is None:
            raise ValueError("UserRole data is None")

    def _is_valid_internal_drop(self, source_rows: list[int], target_row: int) -> bool:
        """Validate internal drop (kept permissive for legacy behavior).

        The target row is valid if it is not -1 and the source rows are not empty.
        The target row is allowed to fall inside the original range; ``_get_drop_positions``
        adjusts the insertion point accordingly.
        """
        if target_row == -1 or not source_rows:
            return False
        # Allow the target even if it falls inside the original range; ``_get_drop_positions``
        # adjusts the insertion point accordingly.

    def _move_row_visually(self, source_row: int, target_row: int) -> None:
        """Visually move a single row (subclasses must override)."""

    def _move_rows_visually(self, source_rows: list[int], target_row: int) -> None:
        """Visually move multiple rows (centralized helper)."""
        dnd_move_rows_visually(self, source_rows, target_row)
        try:
            if hasattr(self, "viewport") and self.viewport() is not None:
                self.viewport().update()
        except (AttributeError, RuntimeError) as e:
            # Catch specific exceptions when updating viewport
            logger.debug("Failed to update viewport after row move: %s", e)

        try:
            self.update()
        except (AttributeError, RuntimeError) as e:
            # Catch specific exceptions when updating widget
            logger.debug("Failed to update widget after row move: %s", e)

    def _get_current_order(self) -> list[int]:
        """Return IDs of items in the current order (centralized helper)."""
        return dnd_get_current_order(self)

    def _create_drag_pixmap(self, items: list[QModelIndex]) -> Optional[QPixmap]:
        """Create a preview pixmap for the drag operation."""
        try:
            if items:
                rows = sorted({idx.row() for idx in items if idx and idx.isValid()})
            else:
                rows = self._get_selected_rows()

            logger.debug("[PIXMAP] rows for drag pixmap: %s", len(rows))

            if not rows:
                return None

            row_count = len(rows)

            if row_count == 1:
                return self._create_single_row_pixmap(rows[0])
            return self._create_multi_row_pixmap(row_count)

        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Failed to create drag pixmap: %s", e)
            return None

    def _create_single_row_pixmap(self, row: int) -> Optional[QPixmap]:
        """Create a pixmap for a single row selection."""
        try:
            model = getattr(self, "model", lambda: None)()
            if not model:
                return self._create_default_pixmap()

            max_columns = min(3, getattr(model, "columnCount", lambda: 0)())
            texts: list[str] = []
            for col in range(max_columns):
                idx = model.index(row, col)
                if not idx or not idx.isValid():
                    continue
                value = model.data(idx, Qt.ItemDataRole.DisplayRole)
                snippet = str(value or "").strip()
                if not snippet:
                    continue
                if len(snippet) > 40:
                    snippet = snippet[:37] + "..."
                texts.append(snippet)
            if not texts:
                return self._create_default_pixmap()
            text = " | ".join(texts)
            return self._create_text_pixmap(text, single_row=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to create single-row drag pixmap: %s", exc)
            return self._create_default_pixmap()

    def _create_multi_row_pixmap(self, count: int) -> QPixmap:
        """Create a pixmap for multi-row selection with a counter."""
        text = QCoreApplication.translate(
            "BaseDragDropTable", "%n item selected", None, count
        )
        return self._create_text_pixmap(text, single_row=False)

    def _create_text_pixmap(self, text: str, single_row: bool = True) -> QPixmap:
        """Create a styled pixmap with text."""
        return create_text_pixmap(text, single_row=single_row)

    def _create_default_pixmap(self) -> QPixmap:
        """Create a default pixmap to use as a fallback."""
        return create_default_pixmap()
