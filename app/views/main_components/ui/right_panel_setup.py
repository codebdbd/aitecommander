# app/views/main_components/right_panel_setup.py
from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.core.settings_manager import SettingsManager
from app.utils.ui.focus import WidgetRegistry, WidgetType
from app.views.widgets.link import LinksTableView
from app.views.widgets.tiles import CategoryTiles

logger = logging.getLogger(__name__)


class RightPanelBuilder:
    """Builds the right panel using existing WindowUISetup helpers (no behavior change)."""
    def __init__(self, ui: Any) -> None:
        # ui is WindowUISetup; typed as Any to avoid circular imports
        self.ui = ui
        self.window = ui.window
        self.main_layout = ui.main_layout
        self._content_built = False
        self._placeholder: QWidget | None = None
        self._right_panel: QWidget | None = None
        self._right_layout: QVBoxLayout | None = None

    def build_shell(self, mid: QHBoxLayout) -> None:
        """Build the shell for the right panel and splitter.

        Responsibilities:
        - Create the right panel container with margins/spacing from UIConfig
        - Attach a lightweight placeholder so the first layout pass is cheap
        - Create and configure `QSplitter`, add left and right panels, set factors/sizes

        Heavy widgets (tiles/table/stack) are built later via ``finalize_content``.
        """
        right_panel = QWidget(self.window)
        right_panel.setObjectName("RightPanel")
        widgets = self.window.widgets
        self._right_panel = right_panel

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(*app_config.ui.get_layout_margins("right"))
        spacing = int(app_config.ui.get_right_layout_spacing())
        right_layout.setSpacing(spacing)
        self._right_layout = right_layout

        placeholder = QWidget(parent=right_panel)
        placeholder.setObjectName("RightPanelPlaceholder")
        placeholder.setSizePolicy(right_panel.sizePolicy())
        right_layout.addWidget(placeholder)
        self._placeholder = placeholder

        widgets.splitter = self._create_splitter()
        splitter = widgets.splitter
        if splitter is None:
            raise RuntimeError("Failed to create splitter for right panel")
        splitter.addWidget(self.window.left_panel)
        splitter.addWidget(right_panel)
        try:
            splitter.setCollapsible(0, True)
        except (RuntimeError, TypeError):
            logger.debug(
                "RightPanel: failed to set splitter collapsible(0, True)", exc_info=True
            )
        stretch_factors = app_config.ui.get_splitter_stretch_factors()
        splitter.setStretchFactor(0, stretch_factors[0])
        splitter.setStretchFactor(1, stretch_factors[1])
        mid.addWidget(splitter)

        splitter_sizes = self._get_initial_splitter_sizes()
        splitter.setSizes(splitter_sizes)
        self.window._first_structure_load = True

    def finalize_content(self) -> None:
        """Build the heavy tiles/table widgets after the shell already exists."""
        if self._content_built:
            return
        right_panel = self._right_panel
        right_layout = self._right_layout
        if right_panel is None or right_layout is None:
            raise RuntimeError("RightPanel shell must be built before content finalization")

        widgets = self.window.widgets

        widgets.tiles_scroll = QScrollArea(parent=right_panel)
        tiles_scroll = widgets.tiles_scroll
        assert tiles_scroll is not None
        tiles_scroll.setWidgetResizable(True)
        self._normalize_scrollbars(tiles_scroll)
        widgets.tiles = CategoryTiles(parent=tiles_scroll)
        tiles = widgets.tiles
        if tiles is None:
            raise RuntimeError("CategoryTiles widget creation failed")
        tiles.category_selected.connect(
            lambda cat_id: self.window.ui_state.load_category(
                cat_id, source="CategoryTiles"
            )
        )
        WidgetRegistry.register(WidgetType.CATEGORY_TILES, tiles)
        tiles_scroll.setWidget(tiles)

        tiles_wrapper = QWidget(parent=right_panel)
        tiles_layout = QVBoxLayout(tiles_wrapper)
        tiles_layout.setContentsMargins(*app_config.ui.get_layout_margins("tiles"))
        tiles_layout.setSpacing(app_config.ui.get_tiles_layout_spacing())
        tiles_layout.addWidget(tiles_scroll)

        widgets.table = LinksTableView(self.window)
        table = widgets.table
        if table is None:
            raise RuntimeError("LinksTableView creation failed")
        WidgetRegistry.register(WidgetType.LINKS_TABLE, table)

        table_wrapper = QWidget(parent=right_panel)
        table_layout = QVBoxLayout(table_wrapper)
        table_layout.setContentsMargins(*app_config.ui.get_layout_margins("table"))
        table_layout.setSpacing(app_config.ui.get_table_layout_spacing())
        table_layout.addWidget(table)

        widgets.stack = QStackedLayout()
        stack = widgets.stack
        if stack is None:
            raise RuntimeError("Failed to create stacked layout for right panel")
        stack.addWidget(tiles_wrapper)
        widgets.table_container = table_wrapper
        stack.addWidget(table_wrapper)

        if self._placeholder is not None:
            right_layout.removeWidget(self._placeholder)
            self._placeholder.setParent(None)
            self._placeholder.deleteLater()
            self._placeholder = None
        right_layout.addLayout(stack)

        splitter_sizes = app_config.ui.get_splitter_sizes()
        self.ui._setup_auto_hide_tree_filter(splitter_sizes)

        if hasattr(self.window, "bottom_bar_container"):
            self.window.bottom_bar_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._content_built = True

    # --- Internals ---
    def _create_splitter(self):
        # Import here to avoid extra module-level dependencies
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtWidgets import QSplitter

        from app.config_data.runtime_config import runtime_app_config as _cfg

        splitter = QSplitter()
        try:
            handle_w = int(_cfg.ui.get_splitter_handle_width())
        except (TypeError, ValueError):
            handle_w = 1
        try:
            splitter.setHandleWidth(max(1, handle_w))
        except Exception:
            logger.debug(
                "RightPanel: failed to set splitter handle width", exc_info=True
            )
        try:
            splitter.setOrientation(_Qt.Orientation.Horizontal)
        except Exception:
            logger.debug(
                "RightPanel: failed to set splitter orientation", exc_info=True
            )
        try:
            splitter.setChildrenCollapsible(True)
        except Exception:
            logger.debug(
                "RightPanel: failed to set children collapsible", exc_info=True
            )
        return splitter

    def _get_initial_splitter_sizes(self) -> list[int]:
        """Return persisted splitter sizes, falling back to config defaults."""
        default_sizes = app_config.ui.get_splitter_sizes()
        try:
            left = SettingsManager.get("window.splitter_left")
            right = SettingsManager.get("window.splitter_right")
            if isinstance(left, int) and isinstance(right, int) and left > 0 and right > 0:
                return [left, right]
        except Exception:
            logger.debug(
                "RightPanel: failed to read saved splitter sizes",
                exc_info=True,
            )
        return default_sizes

    @staticmethod
    def _normalize_scrollbars(area: QScrollArea) -> None:
        """Configure scrollbar policies without forcing inversion."""
        try:
            area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        except Exception:
            logger.debug("RightPanel: failed to set scrollbar policies", exc_info=True)
