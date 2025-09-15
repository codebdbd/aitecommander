# app/views/tiles/widget.py
from __future__ import annotations

import logging
from typing import List, Dict

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QAbstractItemView, QVBoxLayout, QWidget

from app.config_data import app_config
from app.models.categories_list_model import CategoriesListModel

from .list_view import CategoryListView
from .delegate import CategoryTileDelegate

logger = logging.getLogger("category_tiles")


class CategoryTiles(QWidget):
    category_selected: pyqtSignal = pyqtSignal(int)
    # Сигналы, которые должен обрабатывать контроллер
    editRequested: pyqtSignal = pyqtSignal(int)
    deleteRequested: pyqtSignal = pyqtSignal(int)
    addLinkRequested: pyqtSignal = pyqtSignal(int)
    contextMenuRequested: pyqtSignal = pyqtSignal(int, QPoint)

    def __init__(
        self,
        parent=None,
        structure_controller=None,
        ui_state_manager=None,
        dialog_provider=None,
    ):
        """Простой UI-компонент для отображения плиток категорий."""
        super().__init__(parent)

        self._current_item_id = None

        self.structure_controller = structure_controller
        self.ui_state_manager = ui_state_manager
        self.dialog_provider = dialog_provider

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.view = CategoryListView()
        self.view.setObjectName("categoryTiles")
        self.view.setViewMode(self.view.ViewMode.IconMode)
        self.view.setResizeMode(self.view.ResizeMode.Adjust)
        self.view.setMovement(self.view.Movement.Static)
        self.view.setMouseTracking(True)
        vp = self.view.viewport()
        try:
            vp.setMouseTracking(True)
            vp.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        except (AttributeError, RuntimeError) as e:
            logger.debug("Viewport hover setup skipped: %s", e)
        try:
            vp.installEventFilter(self)
        except (AttributeError, RuntimeError) as e:
            logger.debug("Failed to install event filter on viewport: %s", e)
        except Exception:
            logger.exception("Unexpected error installing event filter on viewport")
        self.delegate = CategoryTileDelegate(parent=self)
        # Применяем размеры плиток и иконок из конфигурации
        try:
            tile_w, tile_h = app_config.ui.get_tile_size()
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Tile size config read failed; using defaults (120x100): %s", e)
            tile_w, tile_h = (120, 100)
        try:
            icon_w, icon_h = app_config.ui.get_tile_icon_size()
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Icon size config read failed; using defaults (48x48): %s", e)
            icon_w, icon_h = (48, 48)
        try:
            spacing = int(app_config.ui.get_tile_spacing())
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Tile spacing config read failed; using default 8: %s", e)
            spacing = 8
        try:
            padding = int(app_config.ui.get_tile_padding())
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Tile padding config read failed; using default 8: %s", e)
            padding = 8

        # Передаём параметры делегату и виду
        try:
            self.delegate.icon_size = self.delegate.icon_size.__class__(int(icon_w), int(icon_h))
            self.delegate.tile_size = self.delegate.tile_size.__class__(int(tile_w), int(tile_h))
            self.delegate.padding = max(0, int(padding))
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Failed to apply delegate parameters; using existing defaults: %s", e)
        except Exception:
            logger.exception("Unexpected error applying delegate parameters")
        self.view.setItemDelegate(self.delegate)

        self.view.setUniformItemSizes(False)
        try:
            self.view.setWordWrap(True)
        except (AttributeError, RuntimeError) as e:
            logger.debug("WordWrap not supported on list widget: %s", e)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # spacing из конфигурации
        try:
            self.view.setSpacing(int(spacing))
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Failed to set spacing from config; using 8: %s", e)
            self.view.setSpacing(8)
        except Exception:
            logger.exception("Unexpected error setting spacing; forcing 8")
            self.view.setSpacing(8)

        self.view.setDragEnabled(True)
        self.view.setAcceptDrops(False)
        self.view.setDropIndicatorShown(False)
        self.view.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Контекстное меню: обрабатываем и сигнал от view, и от viewport
        # a) от view — координаты в системе view
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_context_menu)
        # b) от viewport — координаты в системе viewport
        vp = self.view.viewport()
        vp.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        vp.customContextMenuRequested.connect(self._show_context_menu)
        # Открываем категорию ТОЛЬКО по двойному клику или Enter
        try:
            self.view.doubleClicked.connect(self._on_index_activated)
        except (RuntimeError, AttributeError) as e:
            logger.warning("Failed to connect doubleClicked: %s", e)
        except Exception:
            logger.exception("Unexpected error connecting doubleClicked")
        try:
            self.view.enterActivated.connect(self._on_index_activated)
        except (RuntimeError, AttributeError) as e:
            logger.warning("Failed to connect enterActivated: %s", e)
        except Exception:
            logger.exception("Unexpected error connecting enterActivated")

        self.layout.addWidget(self.view, 1)
        # Явно включаем режим только перетаскивания (DragOnly) для стабильной работы DnD
        try:
            self.view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        except Exception as e:
            logger.debug("Failed to set DragOnly mode: %s", e)

    def update_font_size(self, fs: int) -> None:
        """Применяет централизованный размер шрифта к плиткам категорий.

        Если передан невалидный размер — сбрасывает в None (делегат возьмёт конфиг/глобальный).
        """
        try:
            if isinstance(fs, bool):
                return
            val = int(fs)
            if val > 0:
                self._font_point_size = val
            else:
                self._font_point_size = None
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("update_font_size: invalid fs=%r, resetting to None: %s", fs, e)
            self._font_point_size = None
        # Перерисовать и обновить расчёты размеров
        try:
            self.view.viewport().update()
            self.view.reset()  # пересчитать sizeHint через делегат
        except (RuntimeError, AttributeError) as e:
            logger.warning("update_font_size: repaint/reset failed: %s", e)
        except Exception:
            logger.exception("update_font_size: unexpected error during repaint/reset")

    def set_categories(self, categories: List[Dict]) -> None:
        """Обновление списка категорий через модель."""
        logger.debug("Loading %d categories", len(categories))
        model = getattr(self, "_model", None)
        if model is None:
            model = CategoriesListModel(categories)
            self._model = model
            self.view.setModel(model)
        else:
            model.set_categories(categories)

    def _on_index_activated(self, index):
        if not index or not index.isValid():
            logger.debug("No index selected")
            self._current_item_id = None
            return
        cat_id = index.data(Qt.ItemDataRole.UserRole)
        name = index.data(Qt.ItemDataRole.DisplayRole)
        if cat_id is None:
            logger.debug("No category id in UserRole for index")
            return
        self._current_item_id = int(cat_id)
        logger.debug("Selected category tile ID %s (%s)", cat_id, name)
        # Эмитим сигнал на активацию (клик/даблклик)
        try:
            self.category_selected.emit(int(cat_id))
        except Exception as e:
            logger.warning("Failed to emit category_selected: %s", e)

    def inject_dependencies(
        self, structure_controller=None, ui_state_manager=None, dialog_provider=None
    ):
        """Инжектирует зависимости после создания контроллеров."""
        if structure_controller:
            self.structure_controller = structure_controller
        if ui_state_manager:
            self.ui_state_manager = ui_state_manager
        if dialog_provider:
            self.dialog_provider = dialog_provider

    def eventFilter(self, obj, event):
        # Гарантированный перехват QContextMenuEvent из viewport()
        try:
            if obj is self.view.viewport() and event.type() == event.Type.ContextMenu:
                pos = event.pos()
                logger.debug("Viewport eventFilter: ContextMenu at %s", pos)
                self._show_context_menu(pos)
                event.accept()
                return True
        except Exception as e:
            logger.debug("eventFilter failed: %s", e)
        return super().eventFilter(obj, event)

    def _show_context_menu(self, pos: QPoint):
        """Запрашивает показ контекстного меню через контроллер (сигнал)."""
        logger.debug("Context menu requested at position %s", pos)
        index = self.view.indexAt(pos)
        source = "viewport"
        if not index.isValid():
            # Возможно, pos пришёл в координатах view — конвертируем
            vpos = self.view.viewport().mapFrom(self.view, pos)
            index = self.view.indexAt(vpos)
            source = "view"
        if not index.isValid():
            # Fallback: берём позицию курсора и маппим в viewport
            try:
                gpos = QCursor.pos()
                vpos2 = self.view.viewport().mapFromGlobal(gpos)
                index = self.view.indexAt(vpos2)
                source = "cursor"
            except (RuntimeError, AttributeError) as e:
                logger.debug("Context menu fallback mapping from cursor failed: %s", e)
            except Exception:
                logger.exception("Unexpected error during context menu cursor mapping")
        if not index.isValid():
            logger.debug("Invalid index at position")
            return

        item_id = index.data(Qt.ItemDataRole.UserRole)
        if item_id is None:
            logger.debug("No item_id found in UserRole")
            return

        self._current_item_id = int(item_id)
        logger.debug(
            "Emitting contextMenuRequested for category %s (%s)",
            item_id,
            index.data(Qt.ItemDataRole.DisplayRole),
        )
        # Определяем глобальные координаты показа
        if source == "viewport":
            global_pos = self.view.viewport().mapToGlobal(pos)
        elif source == "view":
            global_pos = self.view.mapToGlobal(pos)
        else:
            global_pos = QCursor.pos()

        # Чисто сигнальный путь: внешний контроллер строит меню
        try:
            self.contextMenuRequested.emit(int(item_id), global_pos)
        except Exception as e:
            logger.warning("Failed to emit contextMenuRequested: %s", e)

    def select_category(self, category_id: int) -> None:
        """Выбрать категорию по ID."""
        model = getattr(self, "_model", None)
        if not model:
            logger.debug("Model is not set; cannot select category")
            return
        row = model.find_row_by_id(category_id)
        if row >= 0:
            idx = model.index(row, 0)
            self.view.setCurrentIndex(idx)
            self._current_item_id = category_id
            self.view.scrollTo(idx)
            logger.debug("Selected category tile ID %s", category_id)
            return
        logger.debug("Could not find category tile ID %s", category_id)

    def get_categories_count(self) -> int:
        """Получить общее количество категорий."""
        model = getattr(self, "_model", None)
        return int(model.rowCount()) if model else 0

    # Устаревший API: эмитим только сигналы
    def _execute_edit_category(self, category_id: int):
        logger.debug("Emit editRequested for ID %s", category_id)
        self.editRequested.emit(category_id)

    def _execute_delete_category(self, category_id: int):
        logger.debug("Emit deleteRequested for ID %s", category_id)
        self.deleteRequested.emit(category_id)

    def _execute_add_link(self, category_id: int):
        logger.debug("Emit addLinkRequested for ID %s", category_id)
        self.addLinkRequested.emit(category_id)
