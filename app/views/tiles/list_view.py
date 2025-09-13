# app/views/tiles/list_view.py
from __future__ import annotations

import logging

from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QDrag, QMouseEvent
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QListView

from app.config_data import app_config
from app.utils.ui.dnd.mime import MimeDataParser

logger = logging.getLogger("category_tiles")


class CategoryListView(QListView):
    """QListView with custom drag that serialises category id from model UserRole."""

    MIME_TYPE = app_config.settings.get_category_mime_type()
    # Сигнал активации по клавише Enter/Return
    enterActivated = pyqtSignal(object)

    def mousePressEvent(self, event: QMouseEvent):
        # Гарантируем установку currentIndex по месту клика (для DnD и контекстного меню)
        try:
            p = event.position().toPoint()
            self._press_pos = p
            idx = self.indexAt(p)
            if idx.isValid():
                self.setCurrentIndex(idx)
                self.selectionModel().setCurrentIndex(
                    idx, QAbstractItemView.SelectionFlag.ClearAndSelect
                )
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.debug("CategoryListView.mousePressEvent: %s", e)
        except Exception:
            logger.exception("CategoryListView.mousePressEvent: unexpected error")
        super().mousePressEvent(event)

    def startDrag(self, supportedActions):
        index = self.currentIndex()
        if not index or not index.isValid():
            logger.debug("CategoryListView.startDrag: no current index")
            return
        cat_id = index.data(Qt.ItemDataRole.UserRole)
        if cat_id is None:
            logger.debug("CategoryListView.startDrag: no category id in UserRole")
            return

        name = index.data(Qt.ItemDataRole.DisplayRole)
        logger.debug(
            "CategoryListView.startDrag: starting drag for category %s (%s)",
            cat_id,
            name,
        )
        drag = QDrag(self)
        mime = MimeDataParser.create_mime_data([int(cat_id)], self.MIME_TYPE)
        drag.setMimeData(mime)
        logger.debug(
            "CategoryListView.startDrag: MIME type = %s, data = %s",
            self.MIME_TYPE,
            cat_id,
        )

        result = drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        logger.debug("CategoryListView.startDrag: drag result = %s", result)

    def mouseMoveEvent(self, event):
        # Явный запуск DnD при достаточном смещении курсора
        try:
            if event.buttons() & Qt.MouseButton.LeftButton:
                idx = self.currentIndex()
                if idx.isValid():
                    # Порог из системных настроек
                    threshold = QApplication.startDragDistance()
                    start = getattr(self, "_press_pos", event.position().toPoint())
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

    def keyPressEvent(self, event):
        # Активация плитки по Enter/Return
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

    def contextMenuEvent(self, event):
        # Всегда устанавливаем текущий индекс по правому клику и прокидываем сигнал
        try:
            idx = self.indexAt(event.pos())
            if idx.isValid():
                self.setCurrentIndex(idx)
                self.selectionModel().setCurrentIndex(
                    idx, QAbstractItemView.SelectionFlag.ClearAndSelect
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

    def eventFilter(self, obj, event):
        # Гарантированный перехват QContextMenuEvent из viewport()
        try:
            if obj is self.viewport() and event.type() == QEvent.Type.ContextMenu:
                pos = event.pos()
                logger.debug("Viewport eventFilter: ContextMenu at %s", pos)
                self.customContextMenuRequested.emit(pos)
                event.accept()
                return True
        except Exception as e:
            logger.debug("eventFilter failed: %s", e)
        return super().eventFilter(obj, event)
