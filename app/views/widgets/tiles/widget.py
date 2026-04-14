# app/views/tiles/widget.py
from __future__ import annotations

import logging
import os
import time

from PyQt6.QtCore import QEvent, QModelIndex, QObject, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QAbstractItemView, QVBoxLayout, QWidget

from app.config_data.runtime_config import runtime_app_config as app_config
from app.views.models import CategoriesListModel

from .delegate import CategoryTileDelegate
from .list_view import CategoryListView

logger = logging.getLogger("category_tiles")
_DIAG_TILES = str(os.getenv("APP_TILES_DIAG", "")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class CategoryTiles(QWidget):
    category_selected: pyqtSignal = pyqtSignal(int)
    # Signals expected to be handled by the controller
    editRequested: pyqtSignal = pyqtSignal(int)
    deleteRequested: pyqtSignal = pyqtSignal(int)
    addLinkRequested: pyqtSignal = pyqtSignal(int)
    contextMenuRequested: pyqtSignal = pyqtSignal(int, QPoint)

    def _setup_viewport(self, vp):
        """Setup viewport mouse tracking and event filter."""
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

    def _load_config_sizes(self):
        """Load tile and icon sizes from configuration."""
        try:
            tile_w, tile_h = app_config.ui.get_tile_size()
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Tile size config read failed: %s", e)
            tile_w, tile_h = app_config.ui.get_tile_size_safe()
        try:
            icon_w, icon_h = app_config.ui.get_tile_icon_size()
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Icon size config read failed: %s", e)
            icon_w, icon_h = app_config.ui.get_tile_icon_size_safe()
        try:
            spacing = int(app_config.ui.get_tile_spacing())
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Tile spacing config read failed: %s", e)
            spacing = app_config.ui.get_tile_spacing_safe()
        try:
            padding = int(app_config.ui.get_tile_padding())
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Tile padding config read failed: %s", e)
            padding = app_config.ui.get_tile_padding_safe()
        return tile_w, tile_h, icon_w, icon_h, spacing, padding

    def _apply_delegate_params(self, tile_w, tile_h, icon_w, icon_h, padding):
        """Apply parameters to delegate."""
        try:
            self.delegate.icon_size = self.delegate.icon_size.__class__(
                int(icon_w), int(icon_h)
            )
            self.delegate.tile_size = self.delegate.tile_size.__class__(
                int(tile_w), int(tile_h)
            )
            self.delegate.padding = max(0, int(padding))
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning(
                "Failed to apply delegate parameters; using existing defaults: %s", e
            )
        except Exception:
            logger.exception("Unexpected error applying delegate parameters")

    def _configure_view_settings(self, spacing):
        """Configure view settings."""
        self.view.setUniformItemSizes(False)
        try:
            self.view.setWordWrap(True)
        except (AttributeError, RuntimeError) as e:
            logger.debug("WordWrap not supported on list widget: %s", e)
        # Tiles support Ctrl/Shift multi-select and Select All actions.
        # SingleSelection causes Qt to collapse selection on current-index changes
        # (e.g. right-click/context-menu focus updates).
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        try:
            self.view.setSpacing(int(spacing))
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning("Failed to set spacing from config: %s", e)
            self.view.setSpacing(app_config.ui.get_tile_spacing_safe())
        except Exception:
            logger.exception("Unexpected error setting spacing; forcing fallback")
            self.view.setSpacing(app_config.ui.get_tile_spacing_safe())

    def _setup_drag_drop(self):
        """Setup drag and drop settings."""
        self.view.setDragEnabled(True)
        self.view.setAcceptDrops(False)
        self.view.setDropIndicatorShown(False)
        self.view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

    def _setup_context_menu(self):
        """Setup context menu for view and viewport."""
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_context_menu)
        vp = self.view.viewport()
        vp.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        vp.customContextMenuRequested.connect(self._show_context_menu)

    def _connect_activation_signals(self):
        """Connect activation signals."""
        try:
            self.view.clicked.connect(self._on_index_clicked)
        except (RuntimeError, AttributeError) as e:
            logger.warning("Failed to connect clicked: %s", e)
        except Exception:
            logger.exception("Unexpected error connecting clicked")
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

    def _on_index_clicked(self, index: QModelIndex) -> None:
        """Track current tile on single click without activating it."""
        if not index or not index.isValid():
            self._current_item_id = None
            return
        cat_id = index.data(Qt.ItemDataRole.UserRole)
        if cat_id is None:
            return
        try:
            self._current_item_id = int(cat_id)
        except (TypeError, ValueError):
            self._current_item_id = None

    def __init__(
        self,
        parent=None,
        structure_controller=None,
        ui_state_manager=None,
        dialog_provider=None,
    ):
        """Simple UI component for displaying category tiles."""
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
        try:
            # Batched layout reduces relayout cost on large data sets.
            self.view.setLayoutMode(self.view.LayoutMode.Batched)
            batch = int(app_config.ui.get("ui.tiles_layout_batch_size", 100))
            self.view.setBatchSize(max(10, batch))
        except Exception:
            logger.debug("CategoryTiles: failed to enable batched layout", exc_info=True)
        try:
            if bool(app_config.ui.get("ui.tiles_lazy_icons", True)):
                self.view.setUniformItemSizes(True)
        except Exception:
            logger.debug("CategoryTiles: failed to set uniform item sizes", exc_info=True)

        vp = self.view.viewport()
        self._setup_viewport(vp)

        self.delegate = CategoryTileDelegate(parent=self)
        tile_w, tile_h, icon_w, icon_h, spacing, padding = self._load_config_sizes()
        self._apply_delegate_params(tile_w, tile_h, icon_w, icon_h, padding)
        self.view.setItemDelegate(self.delegate)

        self._configure_view_settings(spacing)
        self._setup_drag_drop()
        self._setup_context_menu()
        self._connect_activation_signals()

        self.layout.addWidget(self.view, 1)
        # Explicitly enable DragOnly mode for stable DnD behavior
        try:
            self.view.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        except Exception as e:
            logger.debug("Failed to set DragOnly mode: %s", e)

    def update_font_size(self, fs: int) -> None:
        """Apply centralized font size to category tiles.

        If invalid size is passed — reset to None (delegate will use config/global).
        """
        try:
            if isinstance(fs, bool):
                return
            val = int(fs)
            if val > 0:
                self._font_point_size = val
            else:
                self._font_point_size = 0
        except (AttributeError, ValueError, TypeError) as e:
            logger.warning(
                "update_font_size: invalid fs=%r, resetting to 0: %s", fs, e
            )
            self._font_point_size = 0
        # Repaint and refresh size calculations
        try:
            self.view.viewport().update()
            self.view.reset()  # recompute sizeHint via delegate
        except (RuntimeError, AttributeError) as e:
            logger.warning("update_font_size: repaint/reset failed: %s", e)
        except Exception:
            logger.exception("update_font_size: unexpected error during repaint/reset")

    def set_categories(self, categories: list[dict]) -> None:
        """Update categories list via the model."""
        logger.debug("Loading %d categories", len(categories))
        t0 = time.perf_counter()
        t_sort_done = t0
        t_model_done = t0
        categories = categories or []
        try:
            sort_enabled = bool(
                app_config.ui.get("ui.tiles_alphabetical_sort_enabled", False)
            )
        except Exception:
            sort_enabled = False
        try:
            skip_sort = bool(app_config.ui.get("ui.tiles_skip_sort_if_sorted", True))
        except Exception:
            skip_sort = True

        if categories and sort_enabled:
            try:
                if not (skip_sort and self._is_sorted_by_name(categories)):
                    categories = sorted(
                        categories,
                        key=lambda c: str(c.get("name", "")).casefold(),
                    )
            except Exception:
                logger.debug("CategoryTiles: sorting categories failed", exc_info=True)
        t_sort_done = time.perf_counter()

        model = getattr(self, "_model", None)
        if model is None:
            model = CategoriesListModel(categories)
            self._model = model
            self.view.setModel(model)
        else:
            model.set_categories(categories)
        t_model_done = time.perf_counter()
        elapsed_ms = (t_model_done - t0) * 1000
        logger.info(
            "[Perf] Tiles.set_categories count=%s sort=%.2f ms model=%.2f ms total=%.2f ms sort_enabled=%s",
            len(categories),
            (t_sort_done - t0) * 1000.0,
            (t_model_done - t_sort_done) * 1000.0,
            elapsed_ms,
            bool(categories and sort_enabled),
        )

    @staticmethod
    def _is_sorted_by_name(categories: list[dict]) -> bool:
        """Return True if categories are already sorted by name (casefold)."""
        prev = ""
        for cat in categories:
            name = str(cat.get("name", "")).casefold()
            if name < prev:
                return False
            prev = name
        return True

    def _on_index_activated(self, index: QModelIndex) -> None:
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
        # Emit activation signal (click/double click)
        try:
            self.category_selected.emit(int(cat_id))
        except Exception as e:
            logger.warning("Failed to emit category_selected: %s", e)

    def inject_dependencies(
        self, structure_controller=None, ui_state_manager=None, dialog_provider=None
    ):
        """Inject dependencies after controllers are created."""
        if structure_controller:
            self.structure_controller = structure_controller
        if ui_state_manager:
            self.ui_state_manager = ui_state_manager
        if dialog_provider:
            self.dialog_provider = dialog_provider

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        # Guaranteed interception of QContextMenuEvent from viewport()
        try:
            if obj is self.view.viewport() and event is not None and event.type() == QEvent.Type.ContextMenu:
                pos = getattr(event, 'pos', lambda: None)()
                if pos is None:
                    return False
                logger.debug("Viewport eventFilter: ContextMenu at %s", pos)
                self._show_context_menu(pos)
                event.accept()
                return True
        except Exception as e:
            logger.debug("eventFilter failed: %s", e)
        return super().eventFilter(obj, event)

    def _show_context_menu(self, pos: QPoint):
        """Request context menu display via controller (signal)."""
        logger.debug("Context menu requested at position %s", pos)
        index = self.view.indexAt(pos)
        source = "viewport"
        if not index.isValid():
            # pos might be in view coordinates — convert
            vpos = self.view.viewport().mapFrom(self.view, pos)
            index = self.view.indexAt(vpos)
            source = "view"
        if not index.isValid():
            # Fallback: take cursor position and map to viewport
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
        # Determine global coordinates for display
        if source == "viewport":
            global_pos = self.view.viewport().mapToGlobal(pos)
        elif source == "view":
            global_pos = self.view.mapToGlobal(pos)
        else:
            global_pos = QCursor.pos()

        # Purely signal-based: external controller builds the menu
        try:
            self.contextMenuRequested.emit(int(item_id), global_pos)
        except Exception as e:
            logger.warning("Failed to emit contextMenuRequested: %s", e)

    def select_category(self, category_id: int) -> None:
        """Select category by ID."""
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
        """Get total number of categories."""
        model = getattr(self, "_model", None)
        return int(model.rowCount()) if model else 0
