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

from app.config_data import app_config
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

    def build(self, mid: QHBoxLayout) -> None:
        """Build and attach the right panel (tiles + table + splitter).

        Responsibilities:
        - Create tiles area (scroll + tiles wrapper) and table area (wrapper)
        - Assemble `QStackedLayout` with tiles and table, set `window.table_container`
        - Build the right panel container with margins/spacing from UIConfig
        - Create and configure `QSplitter`, add left and right panels, set factors/sizes
        - Initialize auto-hide tree filter and focus policies per existing behavior

        Note: preserves existing behavior and UI-state wiring and metrics.
        """
        # Create the right panel container upfront to parent wrappers
        right_panel = QWidget(self.window)
        widgets = self.window.widgets

        # Category tiles - create with a valid parent hierarchy
        widgets.tiles_scroll = QScrollArea(parent=right_panel)
        tiles_scroll = widgets.tiles_scroll
        assert tiles_scroll is not None  # for type checkers
        tiles_scroll.setWidgetResizable(True)
        widgets.tiles = CategoryTiles(parent=tiles_scroll)
        tiles = widgets.tiles

        # Connect to UIStateManager
        if tiles is None:
            raise RuntimeError("CategoryTiles widget creation failed")
        tiles.category_selected.connect(
            lambda cat_id: self.window.ui_state.load_category(
                cat_id, source="CategoryTiles"
            )
        )

        tiles_scroll.setWidget(tiles)

        tiles_wrapper = QWidget(parent=right_panel)
        tiles_layout = QVBoxLayout(tiles_wrapper)
        tiles_layout.setContentsMargins(*app_config.ui.get_layout_margins("tiles"))
        tiles_layout.setSpacing(app_config.ui.get_tiles_layout_spacing())
        tiles_layout.addWidget(tiles_scroll)

        # Table
        widgets.table = LinksTableView(self.window)
        table = widgets.table
        if table is None:
            raise RuntimeError("LinksTableView creation failed")

        # Table wrapper
        table_wrapper = QWidget(parent=right_panel)
        table_layout = QVBoxLayout(table_wrapper)
        table_layout.setContentsMargins(*app_config.ui.get_layout_margins("table"))
        table_layout.setSpacing(app_config.ui.get_table_layout_spacing())
        table_layout.addWidget(table)

        # Stack
        widgets.stack = QStackedLayout()
        stack = widgets.stack
        if stack is None:
            raise RuntimeError("Failed to create stacked layout for right panel")
        stack.addWidget(tiles_wrapper)
        # API compatibility: either the table widget itself or its container
        widgets.table_container = table_wrapper
        stack.addWidget(table_wrapper)

        # Right panel container
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(*app_config.ui.get_layout_margins("right"))
        # Strictly use UIConfig API (release): method is guaranteed
        spacing = int(app_config.ui.get_right_layout_spacing())
        right_layout.setSpacing(spacing)
        right_layout.addLayout(stack)

        # Splitter
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

        splitter_sizes = app_config.ui.get_splitter_sizes()
        splitter.setSizes(splitter_sizes)
        self.window._first_structure_load = True

        # Auto-hide tree
        self.ui._setup_auto_hide_tree_filter(splitter_sizes)

        # QStackedLayout breaks standard Qt Tab navigation — exclude bottom panel from Tab
        if hasattr(self.window, "bottom_bar_container"):
            self.window.bottom_bar_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    # --- Internals ---
    def _create_splitter(self):
        # Import here to avoid extra module-level dependencies
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtWidgets import QSplitter

        from app.config_data import app_config as _cfg

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
