from __future__ import annotations

import logging
from typing import cast

from PyQt6.QtCore import (
    QEvent,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QContextMenuEvent, QDrag, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QListView, QWidget

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.ui.dnd.mime import MimeDataParser
from app.utils.ui.dnd.pixmap import create_text_pixmap

logger = logging.getLogger("category_tiles")


class CategoryListView(QListView):
    """QListView with custom drag that serialises category id from model UserRole."""

    MIME_TYPE = app_config.settings.get_category_mime_type()
    # Activation signal on Enter/Return key
    enterActivated = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._press_pos: QPoint | None = None
        self._selected_text_color = QColor()
        self._normalize_scrollbars()

    def _get_selected_text_color(self) -> QColor:
        return QColor(self._selected_text_color)

    def _set_selected_text_color(self, value) -> None:
        color = value if isinstance(value, QColor) else QColor(str(value))
        self._selected_text_color = color if color.isValid() else QColor()
        viewport = self.viewport()
        if viewport is not None:
            viewport.update()

    selectedTextColor = pyqtProperty(
        QColor,
        fget=_get_selected_text_color,
        fset=_set_selected_text_color,
    )

    def _normalize_scrollbars(self) -> None:
        """Configure scrollbar policies without forcing inversion."""
        try:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        except Exception:
            logger.debug("CategoryListView: failed to set scrollbar policies", exc_info=True)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        # Keep selection policy explicit for DnD/context menu.
        # Right-click on an already-selected tile must preserve multi-selection.
        try:
            p = event.position().toPoint()
            self._press_pos = p
            idx = self.indexAt(p)
            if idx.isValid():
                selection_model = self.selectionModel()
                if selection_model is not None:
                    preserve_multi = False
                    try:
                        preserve_multi = (
                            event.button() == Qt.MouseButton.RightButton
                            and selection_model.isSelected(idx)
                            and len(selection_model.selectedIndexes() or []) > 1
                        )
                    except Exception:
                        preserve_multi = False
                    if preserve_multi:
                        # Keep current selection intact; only move "current" anchor.
                        selection_model.setCurrentIndex(
                            idx, QItemSelectionModel.SelectionFlag.NoUpdate
                        )
                    else:
                        self.setCurrentIndex(idx)
                        selection_model.setCurrentIndex(
                            idx, QItemSelectionModel.SelectionFlag.ClearAndSelect
                        )
                else:
                    self.setCurrentIndex(idx)
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.mousePressEvent: %s", e)
        except Exception:
            logger.exception("CategoryListView.mousePressEvent: unexpected error")
        super().mousePressEvent(event)

    def startDrag(self, supportedActions: Qt.DropAction) -> None:  # type: ignore[override]
        index = self.currentIndex()
        if not index or not index.isValid():
            logger.debug("CategoryListView.startDrag: no current index")
            return

        selection_model = self.selectionModel()
        indexes: list = []
        if selection_model is not None:
            try:
                indexes = selection_model.selectedIndexes()
            except Exception as exc:
                logger.debug(
                    "CategoryListView.startDrag: failed to collect selected indexes: %s",
                    exc,
                )
                indexes = []

        if not indexes:
            indexes = [index]

        category_ids: list[int] = []
        primary_name = index.data(Qt.ItemDataRole.DisplayRole)
        for idx in indexes:
            if not idx or not idx.isValid():
                continue
            cat_id = idx.data(Qt.ItemDataRole.UserRole)
            try:
                cat_id = int(cat_id)
            except (TypeError, ValueError):
                continue
            if cat_id in category_ids:
                continue
            category_ids.append(cat_id)

        if not category_ids:
            logger.debug("CategoryListView.startDrag: no valid category ids collected")
            return

        preview_text = self._build_drag_preview_text(indexes)
        logger.debug(
            "CategoryListView.startDrag: starting drag for categories %s (primary=%s)",
            category_ids,
            primary_name,
        )
        drag = QDrag(self)
        mime = MimeDataParser.create_mime_data(category_ids, self.MIME_TYPE)
        drag.setMimeData(mime)
        if preview_text:
            pixmap = create_text_pixmap(preview_text, single_row=False)
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        logger.debug(
            "CategoryListView.startDrag: MIME type = %s, data = %s",
            self.MIME_TYPE,
            category_ids,
        )

        result = drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        logger.debug("CategoryListView.startDrag: drag result = %s", result)

    def _build_drag_preview_text(self, indexes: list[QModelIndex]) -> str:
        names: list[str] = []
        seen = set()
        for idx in indexes:
            if not idx or not idx.isValid():
                continue
            name = idx.data(Qt.ItemDataRole.DisplayRole)
            if not isinstance(name, str):
                continue
            if name in seen:
                continue
            seen.add(name)
            names.append(name)

        total = len(names)
        if total <= 1:
            return ""

        shown = names[:2]
        remaining = total - len(shown)
        if remaining > 0:
            return f"Перетаскивается {total} элементов — {', '.join(shown)} и еще {remaining}"
        return f"Перетаскивается {total} элементов — {', '.join(shown)}"

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        # Explicitly start DnD when cursor moved enough
        try:
            if event.buttons() & Qt.MouseButton.LeftButton:
                idx = self.currentIndex()
                if idx.isValid():
                    # Threshold from system settings
                    threshold = QApplication.startDragDistance()
                    start = self._press_pos or event.position().toPoint()
                    if (
                        event.position().toPoint() - start
                    ).manhattanLength() >= threshold:
                        self.startDrag(
                            Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
                        )
                        return
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.mouseMoveEvent: %s", e)
        except Exception:
            logger.exception("CategoryListView.mouseMoveEvent: unexpected error")
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        # Activate tile on Enter/Return
        try:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                idx = self.currentIndex()
                if idx and idx.isValid():
                    try:
                        self.enterActivated.emit(idx)
                    except (RuntimeError, AttributeError) as e:
                        logger.warning(
                            "CategoryListView.keyPressEvent: failed to emit enterActivated: %s",
                            e,
                        )
                    except Exception:
                        logger.exception(
                            "CategoryListView.keyPressEvent: unexpected error on emit"
                        )
                    event.accept()
                    return
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.keyPressEvent: %s", e)
        except Exception:
            logger.exception("CategoryListView.keyPressEvent: unexpected error")
        super().keyPressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # type: ignore[override]
        # Emit context menu request without destroying existing multi-selection.
        try:
            idx = self.indexAt(event.pos())
            if idx.isValid():
                selection_model = self.selectionModel()
                if selection_model is not None:
                    preserve_multi = False
                    try:
                        preserve_multi = (
                            selection_model.isSelected(idx)
                            and len(selection_model.selectedIndexes() or []) > 1
                        )
                    except Exception:
                        preserve_multi = False
                    if preserve_multi:
                        selection_model.setCurrentIndex(
                            idx, QItemSelectionModel.SelectionFlag.NoUpdate
                        )
                    else:
                        self.setCurrentIndex(idx)
                        selection_model.setCurrentIndex(
                            idx, QItemSelectionModel.SelectionFlag.ClearAndSelect
                        )
                else:
                    self.setCurrentIndex(idx)
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.contextMenuEvent: %s", e)
        except Exception:
            logger.exception(
                "CategoryListView.contextMenuEvent: unexpected error while setting current index"
            )
        try:
            self.customContextMenuRequested.emit(event.pos())
            event.accept()
            return
        except (RuntimeError, AttributeError) as e:
            logger.warning(
                "CategoryListView.contextMenuEvent: failed to emit customContextMenuRequested: %s",
                e,
            )
        except Exception:
            logger.exception(
                "CategoryListView.contextMenuEvent: unexpected error on emit"
            )
        super().contextMenuEvent(event)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        # Guaranteed interception of QContextMenuEvent from viewport()
        try:
            if obj is self.viewport() and event.type() == QEvent.Type.ContextMenu:
                ctx_event = cast(QContextMenuEvent, event)
                pos = ctx_event.pos()
                logger.debug("Viewport eventFilter: ContextMenu at %s", pos)
                self.customContextMenuRequested.emit(pos)
                event.accept()
                return True
        except Exception as e:
            logger.debug("eventFilter failed: %s", e)
        return super().eventFilter(obj, event)
