from __future__ import annotations

import logging
from typing import cast

from PyQt6.QtCore import QEvent, QItemSelectionModel, QObject, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QDrag, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QListView, QWidget

from app.config_data import app_config
from app.utils.ui.dnd.mime import MimeDataParser

logger = logging.getLogger("category_tiles")


class CategoryListView(QListView):
    """QListView with custom drag that serialises category id from model UserRole."""

    MIME_TYPE = app_config.settings.get_category_mime_type()
    # Activation signal on Enter/Return key
    enterActivated = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._press_pos: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        # Ensure currentIndex is set at click position (for DnD and context menu)
        try:
            p = event.position().toPoint()
            self._press_pos = p
            idx = self.indexAt(p)
            if idx.isValid():
                self.setCurrentIndex(idx)
                selection_model = self.selectionModel()
                if selection_model is not None:
                    selection_model.setCurrentIndex(
                        idx, QItemSelectionModel.SelectionFlag.ClearAndSelect
                    )
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

        logger.debug(
            "CategoryListView.startDrag: starting drag for categories %s (primary=%s)",
            category_ids,
            primary_name,
        )
        drag = QDrag(self)
        mime = MimeDataParser.create_mime_data(category_ids, self.MIME_TYPE)
        drag.setMimeData(mime)
        logger.debug(
            "CategoryListView.startDrag: MIME type = %s, data = %s",
            self.MIME_TYPE,
            category_ids,
        )

        result = drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        logger.debug("CategoryListView.startDrag: drag result = %s", result)

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
        # Always set current index on right-click and emit signal
        try:
            idx = self.indexAt(event.pos())
            if idx.isValid():
                self.setCurrentIndex(idx)
                selection_model = self.selectionModel()
                if selection_model is not None:
                    selection_model.setCurrentIndex(
                        idx, QItemSelectionModel.SelectionFlag.ClearAndSelect
                    )
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
